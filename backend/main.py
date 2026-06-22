import asyncio
import json
import os
import sys
from datetime import datetime
import websockets
from dotenv import load_dotenv
import numpy as np

# Add current dir to path to import helpers
sys.path.append(os.path.dirname(__file__))

import db_manager
from audio_handler import AudioHandler
from gemini_client import GeminiClient
from wake_word import WakeWordDetector
from reasoning_client import ReasoningClient
from camera_handler import CameraHandler

load_dotenv()

PORT = int(os.getenv("PORT", 8765))

class StateManager:
    def __init__(self):
        self.state = "idle"  # idle, listening, thinking, speaking
        self.connected_clients = set()
        
        # Initialize sub-modules
        db_manager.init_db()
        self.audio_handler = AudioHandler()
        self.gemini_client = GeminiClient(self.audio_handler, self)
        self.wake_word = WakeWordDetector(self, self.audio_handler)  # Wake word "Jarvis" detector
        self.reasoning_client = ReasoningClient()  # mimo-v2.5-pro for deep reasoning
        self.camera_handler = CameraHandler()  # Webcam for vision
        
        # Wire callback for playback changes (speaking -> idle / idle -> speaking)
        self.audio_handler.on_playback_state_change = self._handle_playback_state_change
        
        # Audio handler by default starts with muted mic (for PTT control)
        self.audio_handler.muted = True
        
        # Track last reminder trigger time to prevent duplicate triggers in the same minute
        self.last_reminder_minute = ""

    async def register_client(self, websocket):
        """Registers a new WebSocket frontend client and sends current state."""
        self.connected_clients.add(websocket)
        print(f"🖥️ Frontend Client connected. Total: {len(self.connected_clients)}")

        # Don't reset state on new connection — a second tab opening
        # should not interrupt an active conversation.

        # Send current state and vitals to the new client
        await websocket.send(json.dumps({
            "type": "state_change",
            "state": self.state
        }))
        await self.send_latest_vitals_to_ui(websocket)

    async def unregister_client(self, websocket):
        """Unregisters a frontend client."""
        self.connected_clients.discard(websocket)
        print(f"🖥️ Frontend Client disconnected. Total: {len(self.connected_clients)}")

    async def broadcast_to_frontend(self, message: dict):
        """Broadcasts a JSON message to all connected frontends."""
        if not self.connected_clients:
            return
        payload = json.dumps(message)
        # Snapshot the set to avoid mutation during iteration
        clients = list(self.connected_clients)
        await asyncio.gather(*[client.send(payload) for client in clients], return_exceptions=True)

    async def update_state(self, new_state: str):
        """Updates the system state and broadcasts it to the frontend."""
        if self.state != new_state:
            self.state = new_state
            print(f"🤖 State updated: {new_state.upper()}")
            await self.broadcast_to_frontend({
                "type": "state_change",
                "state": new_state
            })

    async def send_latest_vitals_to_ui(self, websocket=None):
        """Fetches latest vitals from DB and updates UI."""
        vitals = db_manager.get_latest_vitals(5)
        msg = {
            "type": "vitals_update",
            "vitals": vitals
        }
        if websocket:
            await websocket.send(json.dumps(msg))
        else:
            await self.broadcast_to_frontend(msg)

    async def execute_tool(self, name: str, args: dict) -> dict:
        """Executes function calls requested by the Gemini Live API."""
        try:
            if name == "set_emotion":
                emotion = args.get("emotion", "neutral")
                intensity = args.get("intensity", 1.0)
                await self.broadcast_to_frontend({
                    "type": "emotion_change",
                    "emotion": emotion,
                    "intensity": intensity
                })
                return {"status": "success", "message": f"Emotion set to {emotion} (intensity {intensity})"}
                
            elif name == "show_content":
                card_type = args.get("type")
                title = args.get("title")
                body = args.get("body", "")
                payload = args.get("payload", "")
                await self.broadcast_to_frontend({
                    "type": "show_card",
                    "card_type": card_type,
                    "title": title,
                    "body": body,
                    "payload": payload
                })
                return {"status": "success", "message": f"Card '{title}' of type {card_type} shown on display"}
                
            elif name == "set_reminder":
                time = args.get("time")
                medicine_name = args.get("medicine_name")
                dosage = args.get("dosage", "1 tab")
                repeat = args.get("repeat", "daily")
                
                rid = db_manager.add_reminder(time, medicine_name, dosage, repeat)
                
                # Also display it visually as a card
                await self.broadcast_to_frontend({
                    "type": "show_card",
                    "card_type": "reminder",
                    "title": "เพิ่มการแจ้งเตือนกินยา",
                    "body": f"ตั้งเตือนกินยา: {medicine_name}\nขนาด: {dosage}\nเวลา: {time} น."
                })
                return {"status": "success", "reminder_id": rid, "message": "Reminder saved successfully"}
                
            elif name == "get_vitals":
                limit = args.get("limit", 3)
                vitals = db_manager.get_latest_vitals(limit)
                return {"status": "success", "vitals": vitals}
                
            elif name == "trigger_telemedicine":
                reason = args.get("reason", "Patient requested escalation")
                await self.broadcast_to_frontend({
                    "type": "telemedicine_trigger",
                    "reason": reason,
                    "url": "https://hub-api.socare.app/videoCall?roomName=SocareTelemed"
                })
                return {"status": "escalating", "message": f"Connecting to Socare doctor. Reason: {reason}"}

            elif name == "clear_conversation":
                db_manager.clear_conversation()
                return {"status": "success", "message": "Conversation history cleared"}

            elif name == "think_deeply":
                question = args.get("question", "")
                context = args.get("context", "")
                print(f"🧠 Think deeply: {question[:80]}...")
                # Show thinking state on UI
                await self.broadcast_to_frontend({
                    "type": "emotion_change",
                    "emotion": "thinking",
                    "intensity": 0.8
                })
                # Route to mimo-v2.5-pro
                answer = await self.reasoning_client.ask(question, context)
                print(f"🧠 Reasoning result: {answer[:80]}...")
                return {"status": "success", "analysis": answer}

            elif name == "look_at_patient":
                print("📷 Looking at patient...")
                await self.broadcast_to_frontend({
                    "type": "transcript",
                    "text": "📷 กำลังมอง..."
                })
                image_data = self.camera_handler.capture_as_base64_with_mime()
                if not image_data:
                    return {"error": "camera_failed", "message": "ไม่สามารถเปิดกล้องได้"}
                await self.broadcast_to_frontend({
                    "type": "camera_preview",
                    "image": image_data["data"]
                })
                # Send image bytes via realtime_input (NOT in tool response — causes 1011)
                if self.gemini_client.is_connected and self.gemini_client.session:
                    try:
                        import base64 as b64lib
                        from google.genai import types as gtypes
                        image_bytes = b64lib.b64decode(image_data["data"])
                        await self.gemini_client.session.send_realtime_input(
                            video=gtypes.Blob(
                                data=image_bytes,
                                mime_type=image_data["mime_type"]
                            )
                        )
                        print("📷 Image blob sent to Gemini for patient analysis")
                    except Exception as e:
                        print(f"⚠️ Failed to send image blob: {e}")
                return {"status": "success", "message": "ถ่ายแล้ว โปรดวิเคราะห์สีหน้าและอารมณ์เป็นภาษาไทย"}

            elif name == "look_at_object":
                hint = args.get("hint", "")
                print(f"📷 Looking at object: {hint}")
                await self.broadcast_to_frontend({
                    "type": "transcript",
                    "text": "📷 กำลังดู..."
                })
                image_data = self.camera_handler.capture_as_base64_with_mime()
                if not image_data:
                    return {"error": "camera_failed", "message": "ไม่สามารถเปิดกล้องได้"}
                await self.broadcast_to_frontend({
                    "type": "camera_preview",
                    "image": image_data["data"]
                })
                # Send image bytes via realtime_input (NOT in tool response — causes 1011)
                if self.gemini_client.is_connected and self.gemini_client.session:
                    try:
                        import base64 as b64lib
                        from google.genai import types as gtypes
                        image_bytes = b64lib.b64decode(image_data["data"])
                        await self.gemini_client.session.send_realtime_input(
                            video=gtypes.Blob(
                                data=image_bytes,
                                mime_type=image_data["mime_type"]
                            )
                        )
                        print("📷 Image blob sent to Gemini for object analysis")
                    except Exception as e:
                        print(f"⚠️ Failed to send image blob: {e}")
                hint_text = f" ({hint})" if hint else ""
                return {"status": "success", "message": f"ถ่ายแล้ว{hint_text} โปรดระบุว่าคืออะไรเป็นภาษาไทย"}

            else:
                return {"error": "unknown_tool", "message": f"Tool {name} is not implemented"}
        except Exception as e:
            print(f"Error executing tool {name}: {e}")
            return {"error": "execution_failed", "message": str(e)}

    # --- PTT WebSocket Commands ---

    async def handle_ptt_press(self):
        """Open microphone and signal ActivityStart to Gemini."""
        print("🎤 PTT: เปิดไมค์ + ActivityStart")
        
        # Interrupt any ongoing playback (barge-in)
        self.audio_handler.clear_playback()
        
        # Connect to Gemini if not already connected
        if not self.gemini_client.is_connected:
            await self.gemini_client.connect()
            for _ in range(30):
                if self.gemini_client.is_connected:
                    break
                await asyncio.sleep(0.2)

        if not self.gemini_client.is_connected:
            print("⚠️  Gemini not connected — cannot open mic")
            return
            
        # Signal turn start to Gemini
        await self.gemini_client.send_activity_start()
        
        # Unmute mic → audio starts flowing to Gemini
        self.audio_handler.muted = False
        await self.update_state("listening")


    def _handle_playback_state_change(self, is_playing: bool):
        """Called by AudioHandler when playback starts or stops.
        This runs via call_soon_threadsafe from the playback thread,
        so it executes in the asyncio event loop thread."""
        if is_playing:
            # Mute mic while Jarvis is speaking (prevent echo)
            self.audio_handler.muted = True
            asyncio.create_task(self.update_state("speaking"))
        else:
            # Check if we were speaking (not already idle)
            # Use create_task chain: first go idle, then auto-listen
            async def _finish_speaking():
                await self.update_state("idle")
                await self._auto_listen_after_speaking()
            asyncio.create_task(_finish_speaking())

    async def _auto_listen_after_speaking(self):
        """After Jarvis finishes speaking, open mic and use amplitude VAD.

        Timeline:
          wait for Gemini turn_complete → open mic → patient speaks → silence 1.5s
          → mute mic → THINKING → Gemini responds → SPEAKING
          no speech 8s                 → mute mic → IDLE
          fallback max 30s             → mute mic → THINKING
        """
        await asyncio.sleep(0.6)
        if self.state != "idle":
            return
        if not self.gemini_client.is_connected:
            return

        # Wait for Gemini to finish its turn before listening for next input
        # This prevents sending ActivityEnd while Gemini is still processing
        print("👂 Auto-listen: รอ Gemini turn complete...")
        try:
            await asyncio.wait_for(self.gemini_client.turn_complete.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            print("⚠️ Gemini turn_complete timeout — proceeding anyway")

        if self.state != "idle":
            return
        if not self.gemini_client.is_connected:
            return

        # Send ActivityStart to signal we're ready for user input
        if not await self.gemini_client.send_activity_start():
            print("⚠️ Failed to send ActivityStart — skipping auto-listen")
            return

        SPEECH_THRESHOLD     = 150    # amplitude above = speech detected (lowered for elderly/soft speech)
        SILENCE_AFTER_SPEECH = 2.0    # seconds of silence to release (increased for elderly speech pace)
        NO_SPEECH_TIMEOUT    = 8.0    # give up if nobody speaks at all
        MAX_LISTEN           = 30     # absolute max (fallback)
        TICK                 = 0.25   # VAD poll rate

        print("👂 Auto-listen: เปิดไมค์ — amplitude VAD เฝ้าระวัง")

        self.audio_handler.muted = False
        await self.update_state("listening")
        await self.broadcast_to_frontend({
            "type": "transcript",
            "text": "🎙️ รอฟัง... พูดได้เลยครับ"
        })

        speech_detected = False
        silence_start   = None
        no_speech_start = asyncio.get_running_loop().time()
        last_countdown  = MAX_LISTEN + 1
        elapsed         = 0.0

        while elapsed < MAX_LISTEN:
            await asyncio.sleep(TICK)
            elapsed += TICK

            if self.state != "listening":
                return  # Gemini responded / manually interrupted

            amp = self.audio_handler.last_amplitude
            now = asyncio.get_running_loop().time()

            if amp > SPEECH_THRESHOLD:
                # Patient is speaking
                speech_detected = True
                silence_start   = None
            else:
                if silence_start is None:
                    silence_start = now
                silent_for = now - silence_start

                if speech_detected and silent_for >= SILENCE_AFTER_SPEECH:
                    # Patient finished speaking → hand off to Gemini
                    print(f"👂 VAD: เงียบ {SILENCE_AFTER_SPEECH}s หลังพูด → ส่ง Gemini")
                    break

                if not speech_detected and (now - no_speech_start) >= NO_SPEECH_TIMEOUT:
                    # Nobody spoke → close window
                    print(f"👂 VAD: ไม่มีเสียง {NO_SPEECH_TIMEOUT}s → ปิดไมค์")
                    self.audio_handler.muted = True
                    await self.broadcast_to_frontend({"type": "countdown", "seconds": 0, "total": MAX_LISTEN})
                    await self.update_state("idle")
                    return

            # Countdown display (once per second)
            remaining = max(0, int(MAX_LISTEN - elapsed))
            if remaining != last_countdown:
                last_countdown = remaining
                await self.broadcast_to_frontend({
                    "type": "countdown",
                    "seconds": remaining,
                    "total": MAX_LISTEN
                })

        # ActivityEnd → Gemini processes the turn and responds
        if self.state == "listening":
            self.audio_handler.muted = True
            # Store user turn in conversation history
            try:
                db_manager.add_conversation("user", "[ผู้ป่วยพูด]")
            except Exception as e:
                print(f"⚠️ Failed to save user turn: {e}")
            await self.gemini_client.send_activity_end()   # ← สัญญาณ "turn done"
            await self.broadcast_to_frontend({"type": "countdown", "seconds": 0, "total": MAX_LISTEN})
            print("👂 Auto-listen: ActivityEnd → รอ Gemini ตอบ...")
            await self.update_state("thinking")
            asyncio.create_task(self._thinking_timeout_checker())

    async def handle_ptt_release(self):
        """PTT released manually — mute mic + send ActivityEnd to Gemini."""
        print("🎤 PTT: ปิดไมค์ + ActivityEnd")
        self.audio_handler.muted = True
        # Store user turn in conversation history
        try:
            db_manager.add_conversation("user", "[ผู้ป่วยพูด]")
        except Exception as e:
            print(f"⚠️ Failed to save user turn: {e}")
        if self.gemini_client.is_connected:
            await self.gemini_client.send_activity_end()   # ← บอก Gemini ว่าพูดจบแล้ว
        await self.broadcast_to_frontend({"type": "countdown", "seconds": 0, "total": 30})
        if self.state == "listening":
            await self.update_state("thinking")
            asyncio.create_task(self._thinking_timeout_checker())

    async def _thinking_timeout_checker(self):
        """Safety net: reset to idle if thinking for too long."""
        await asyncio.sleep(30.0)
        if self.state == "thinking":
            print("⏳ Thinking timeout: ไม่ได้รับการตอบกลับจาก Gemini → idle")
            await self.update_state("idle")
            await self.broadcast_to_frontend({
                "type": "transcript",
                "text": "ไม่ได้ยินเสียงตอบรับครับ ลองพูดใหม่หรือกดปุ่มได้เลย"
            })
            # Don't force reconnect — Gemini may still be processing.
            # Let the user try again naturally.

    async def start(self):
        """Start backend servers and loop processes."""
        # Re-bind AudioHandler to the current running event loop and recreate the queue
        self.audio_handler.loop = asyncio.get_running_loop()
        self.audio_handler.input_queue = asyncio.Queue()
        
        # Start sound streams
        self.audio_handler.start()
        
        # Start always-on wake word detector (runs in its own thread)
        self.wake_word.start(asyncio.get_running_loop())
        
        # Attempt to auto-connect to Gemini Live API on start
        await self.gemini_client.connect()
        
        # Start background loop for reminder scheduling
        asyncio.create_task(self._reminder_loop())

        # Start continuous camera monitoring
        self.camera_handler.start()
        asyncio.create_task(self._camera_monitor_loop())

        print(f"🚀 Starting Local WebSocket Server on port {PORT}...")
        async with websockets.serve(self._websocket_handler, "0.0.0.0", PORT):
            await asyncio.Future() # keep server running

    async def _websocket_handler(self, websocket):
        """Handles incoming commands/events from the browser UI."""
        await self.register_client(websocket)
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type")
                    
                    if msg_type == "ptt_press":
                        await self.handle_ptt_press()
                    elif msg_type == "ptt_release":
                        await self.handle_ptt_release()
                    elif msg_type == "clear_history":
                        db_manager.clear_conversation()
                        await websocket.send(json.dumps({
                            "type": "transcript",
                            "text": "🗑️ ลบประวัติการสนทนาแล้วครับ"
                        }))
                        print("🗑️ Conversation history cleared by user")
                    elif msg_type == "capture_camera":
                        print("📷 Camera capture requested from UI")
                        image_data = self.camera_handler.capture_as_base64_with_mime()
                        if image_data:
                            # Show preview on UI
                            await self.broadcast_to_frontend({
                                "type": "camera_preview",
                                "image": image_data["data"]
                            })
                            # Send image to Gemini as a proper turn (ActivityStart → image → text → ActivityEnd)
                            if self.gemini_client.is_connected:
                                try:
                                    import base64
                                    from google.genai import types as gtypes
                                    image_bytes = base64.b64decode(image_data["data"])
                                    # Open a new turn
                                    await self.gemini_client.send_activity_start()
                                    # Send actual image blob so Gemini can see it
                                    await self.gemini_client.session.send_realtime_input(
                                        video=gtypes.Blob(
                                            data=image_bytes,
                                            mime_type=image_data["mime_type"]
                                        )
                                    )
                                    # Add Thai text prompt
                                    await self.gemini_client.session.send_realtime_input(
                                        text="ผู้ใช้กดปุ่มกล้องเพื่อให้ดูภาพ กรุณาบอกสิ่งที่เห็นในภาพเป็นภาษาไทย"
                                    )
                                    # Close turn — Gemini will now respond
                                    await self.gemini_client.send_activity_end()
                                    await self.update_state("thinking")
                                    asyncio.create_task(self._thinking_timeout_checker())
                                    print("📷 Image sent to Gemini — waiting for response")
                                except Exception as e:
                                    print(f"⚠️ Failed to send camera to Gemini: {e}")
                        else:
                            await self.broadcast_to_frontend({
                                "type": "transcript",
                                "text": "❌ ไม่สามารถเปิดกล้องได้"
                            })
                    elif msg_type == "test_speaker":
                        print("🔊 Test speaker requested from UI")
                        self.audio_handler.clear_playback()
                    elif msg_type == "trigger_telemedicine_manual":
                        print("🩺 Telemedicine requested from UI")
                        await self.broadcast_to_frontend({
                            "type": "telemedicine_trigger",
                            "reason": "Patient requested doctor",
                            "url": "https://hub-api.socare.app/videoCall?roomName=SocareTelemed"
                        })

                        # Generate a 1-second 440Hz sine wave tone at the output samplerate
                        fs = self.audio_handler.output_sample_rate
                        duration = 1.0 # 1 second
                        t = np.linspace(0, duration, int(fs * duration), endpoint=False)
                        tone = (np.sin(2 * np.pi * 440 * t) * 12000).astype(np.int16)
                        
                        # Queue the tone
                        self.audio_handler.play_audio_chunk(tone.tobytes())
                    elif msg_type == "ack_reminder":
                        reminder_id = data.get("reminder_id")
                        try:
                            db_manager.acknowledge_reminder(reminder_id)
                            print(f"⏰ Reminder {reminder_id} acknowledged.")
                        except Exception as e:
                            print(f"⚠️ Failed to acknowledge reminder {reminder_id}: {e}")
                    elif msg_type == "inject_mock_vitals":
                        # For developer testing via UI buttons
                        vital_type = data.get("vital_type")
                        value = data.get("value")
                        unit = data.get("unit")
                        status = data.get("status", "normal")
                        db_manager.add_vital(vital_type, value, unit, status)
                        await self.send_latest_vitals_to_ui()
                        print(f"🩺 Injected vital: {vital_type}={value}{unit}")
                        
                        # Also feed into Gemini context as a prompt/notification
                        if self.gemini_client.is_connected:
                            try:
                                await self.gemini_client.session.send_realtime_input(
                                    text=f"[SYSTEM_ALERT: Patient just measured their {vital_type}. Value is {value} {unit}. Status: {status}. Provide a supportive response if critical or say nothing if normal.]"
                                )
                            except Exception as e:
                                print(f"⚠️ Failed to send vitals alert to Gemini: {e}")
                except Exception as ex:
                    print(f"Error parsing websocket message: {ex}")
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister_client(websocket)

    async def _reminder_loop(self):
        """Background loop that checks for active reminders every 10 seconds."""
        while True:
            try:
                now = datetime.now()
                now_minute = now.strftime("%H:%M")
                
                # Check only once per minute
                if now_minute != self.last_reminder_minute:
                    active_reminders = db_manager.get_active_reminders()
                    for r in active_reminders:
                        if r['time'] == now_minute:
                            self.last_reminder_minute = now_minute
                            print(f"⏰ Med Alert! Triggering reminder: {r['medicine_name']} ({r['dosage']})")
                            
                            # 1. Update UI to display the Medication Alert card
                            await self.broadcast_to_frontend({
                                "type": "show_card",
                                "card_type": "reminder_alert",
                                "title": "🚨 ได้เวลาทานยาแล้วครับ!",
                                "body": f"กรุณาทาน: {r['medicine_name']}\nขนาด: {r['dosage']}\nเวลา: {r['time']} น.",
                                "payload": json.dumps(r)
                            })
                            
                            # 2. Inject text into the Gemini Live session so it speaks the announcement
                            if self.gemini_client.is_connected:
                                try:
                                    await self.gemini_client.session.send_realtime_input(
                                        text=f"[SYSTEM_ALERT: Medication reminder time! Please announce to the user in a warm voice: 'ได้เวลาทานยา {r['medicine_name']} ขนาด {r['dosage']} แล้วค่ะ']"
                                    )
                                except Exception as e:
                                    print(f"⚠️ Failed to send reminder alert to Gemini: {e}")
                            
                            # 3. Change facial emotion to alert/neutral
                            await self.broadcast_to_frontend({
                                "type": "emotion_change",
                                "emotion": "concerned",
                                "intensity": 0.8
                            })
            except Exception as e:
                print(f"Error in reminder scheduler: {e}")
                
            await asyncio.sleep(10)

    async def _camera_monitor_loop(self):
        """Periodically capture frames and send to Gemini for patient monitoring.
        Only analyzes when patient is idle (not in active conversation)."""
        await asyncio.sleep(10)  # Wait for system to initialize
        while True:
            try:
                # Only analyze when idle — don't interrupt conversations
                if self.state == "idle" and self.gemini_client.is_connected:
                    image_data = self.camera_handler.capture_as_base64_with_mime()
                    if image_data:
                        # Inject camera observation into Gemini session
                        try:
                            await self.gemini_client.session.send_realtime_input(
                                text="[SYSTEM: Periodic camera check. The patient is currently idle. "
                                     "If you notice anything concerning (looks tired, in pain, distressed), "
                                     "proactively ask how they are feeling. If everything looks normal, say nothing.]"
                            )
                            print("📷 Camera: periodic patient check sent to Gemini")
                        except Exception as e:
                            print(f"⚠️ Camera monitor inject failed: {e}")
            except Exception as e:
                print(f"📷 Camera monitor error: {e}")

            await asyncio.sleep(60)  # Check every 60 seconds

if __name__ == "__main__":
    manager = StateManager()
    try:
        asyncio.run(manager.start())
    except KeyboardInterrupt:
        print("\nStopping orchestrator...")

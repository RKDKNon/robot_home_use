import asyncio
import json
import os
import subprocess
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

        # Conversation flow flags
        # True = currently in a continuous conversation (hands-free mode)
        self._conversation_active = False
        # Prevents auto-listen from being triggered multiple times simultaneously
        self._auto_listen_running = False

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
        vitals = await asyncio.to_thread(db_manager.get_latest_vitals, 5)
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
                
                rid = await asyncio.to_thread(db_manager.add_reminder, time, medicine_name, dosage, repeat)
                
                # Also display it visually as a card
                await self.broadcast_to_frontend({
                    "type": "show_card",
                    "card_type": "reminder",
                    "title": "เพิ่มการแจ้งเตือนกินยา",
                    "body": f"ตั้งเตือนกินยา: {medicine_name}\nขนาด: {dosage}\nเวลา: {time} น."
                })
                return {"status": "success", "reminder_id": rid, "message": f"ตั้งเตือนความจำกินยา {medicine_name} ขนาด {dosage} เวลา {time} สำเร็จแล้ว"}
                
            elif name == "get_vitals":
                limit = args.get("limit", 3)
                vitals = await asyncio.to_thread(db_manager.get_latest_vitals, limit)
                return {"status": "success", "vitals": vitals}
                
            elif name == "trigger_telemedicine":
                reason = args.get("reason", "Patient requested escalation")
                self.camera_handler.stop()  # Release camera for Chromium/Jitsi
                await self.broadcast_to_frontend({
                    "type": "telemedicine_trigger",
                    "reason": reason,
                    "url": "https://hub-api.socare.app/videoCall?roomName=SocareTelemed"
                })
                return {"status": "success", "message": f"กำลังต่อสายเพื่อพบแพทย์เนื่องจาก: {reason}"}

            elif name == "end_telemedicine":
                print("🩺 Telemedicine end requested by Gemini")
                await self.broadcast_to_frontend({
                    "type": "telemedicine_end_trigger"
                })
                return {"status": "success", "message": "วางสายการสนทนาเรียบร้อยแล้ว"}

            elif name == "clear_conversation":
                await asyncio.to_thread(db_manager.clear_conversation)
                return {"status": "success", "message": "ล้างประวัติการสนทนาเรียบร้อยแล้ว"}

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

    # --- Wake Word Activation ---

    async def handle_wake_word(self):
        """Called by WakeWordDetector when 'จาวิส' is detected.
        Only activates from IDLE — ongoing conversations ignore it."""
        if self.state != "idle":
            print("👂 Already in conversation — ignoring wake word.")
            return

        # Visual flash: let frontend know wake word was detected
        await self.broadcast_to_frontend({"type": "wake_word_detected"})
        await asyncio.sleep(0.2)  # Brief visual pause before starting

        # Start listening + kick off VAD loop
        await self._start_listening()
        asyncio.create_task(self._vad_loop())

    async def _start_listening(self):
        """Common entry point to open mic and start a listening turn."""
        if not self.gemini_client.is_connected:
            await self.gemini_client.connect()
            for _ in range(30):
                if self.gemini_client.is_connected:
                    break
                await asyncio.sleep(0.2)

        if not self.gemini_client.is_connected:
            print("⚠️  Gemini not connected — cannot open mic")
            return

        await self.gemini_client.send_activity_start()
        self.audio_handler.muted = False
        self._conversation_active = True
        await self.update_state("listening")

    # --- PTT WebSocket Commands ---

    async def handle_ptt_press(self):
        """PTT button pressed: open mic. If Gemini is speaking, do barge-in interrupt."""
        print("🎤 PTT: กด")

        if self.state == "speaking":
            # Intentional barge-in: clear Gemini's playback and interrupt
            print("🎤 PTT: Barge-in — ขัดจังหวะ Gemini")
            self.audio_handler.clear_playback()
            self._conversation_active = True
            await self._start_listening()
            asyncio.create_task(self._vad_loop())
            return

        if self.state == "thinking":
            # Cancel thinking state and reset to idle immediately
            print("🎤 PTT: ยกเลิกการคิดและกลับสู่โหมดพร้อมทำงาน")
            self._conversation_active = False
            self.audio_handler.muted = True
            await self.update_state("idle")
            await self.broadcast_to_frontend({
                "type": "transcript",
                "text": "ยกเลิกการรอแล้วครับ"
            })
            return

        if self.state == "listening":
            # Already processing — ignore duplicate press
            print("🎤 PTT: ระบบกำลังทำงาน — ignored")
            return

        # From idle: start new conversation turn + VAD
        await self._start_listening()
        asyncio.create_task(self._vad_loop())

    async def handle_ptt_release(self):
        """PTT released manually — mute mic + send ActivityEnd to Gemini."""
        print("🎤 PTT: ปล่อย + ActivityEnd")
        self.audio_handler.muted = True
        # Store user turn in conversation history
        try:
            await asyncio.to_thread(db_manager.add_conversation, "user", "[ผู้ป่วยพูด]")
        except Exception as e:
            print(f"⚠️ Failed to save user turn: {e}")
        if self.gemini_client.is_connected:
            await self.gemini_client.send_activity_end()
        await self.broadcast_to_frontend({"type": "countdown", "seconds": 0, "total": 30})
        if self.state == "listening":
            await self.update_state("thinking")
            asyncio.create_task(self._thinking_timeout_checker())

    def _handle_playback_state_change(self, is_playing: bool):
        """Called by AudioHandler when playback starts or stops."""
        if is_playing:
            self.audio_handler.muted = True
            asyncio.create_task(self.update_state("speaking"))
        else:
            async def _finish_speaking():
                await self.update_state("idle")
                if self._conversation_active and not self._auto_listen_running:
                    await self._auto_listen_after_speaking()
            asyncio.create_task(_finish_speaking())

    async def _vad_loop(self):
        """Adaptive VAD: วัด noise floor ก่อน แล้วตั้ง threshold แบบ dynamic"""
        SILENCE_AFTER_SPEECH = 0.5   # เงียบ 0.5s หลังพูดจบ → ส่ง Gemini
        NO_SPEECH_TIMEOUT    = 3.5   # ไม่มีเสียงเลย 3.5s → ปิดไมค์
        MAX_LISTEN           = 10    # รอสูงสุด 10 วินาที
        TICK                 = 0.05
        EMA_ALPHA            = 0.3
        CALIBRATE_MS         = 400   # วัด noise floor นาน 400ms

        speech_detected  = False
        silence_start    = None
        no_speech_start  = asyncio.get_running_loop().time()
        last_countdown   = MAX_LISTEN + 1
        elapsed          = 0.0
        amp_smooth       = 0.0

        # ── ขั้นตอน 1: วัด noise floor (400ms แรก) ──────────────────────────
        noise_samples = []
        calibrate_ticks = int(CALIBRATE_MS / (TICK * 1000))
        for _ in range(calibrate_ticks):
            await asyncio.sleep(TICK)
            noise_samples.append(self.audio_handler.last_amplitude)
        noise_floor = (sum(noise_samples) / len(noise_samples)) if noise_samples else 40

        # Cap noise floor at 350 to prevent VAD from becoming deaf during temporary loud noises/echoes
        effective_noise_floor = min(350.0, noise_floor)

        # threshold = noise_floor × 2.5 (พูดต้องดังกว่า background ชัดเจน)
        SPEECH_THRESHOLD = max(50, effective_noise_floor * 2.5)
        # หลังพูดแล้ว ถือว่า "ยังพูดอยู่" ถ้าดังกว่า noise_floor × 1.5
        END_THRESHOLD    = max(30, effective_noise_floor * 1.5)

        print(f"👂 VAD calibrate: noise_floor={noise_floor:.0f} → speech>{SPEECH_THRESHOLD:.0f} end>{END_THRESHOLD:.0f}")

        # ── ขั้นตอน 2: ฟังและ detect ────────────────────────────────────────
        try:
            while elapsed < MAX_LISTEN:
                await asyncio.sleep(TICK)
                elapsed += TICK

                if self.state != "listening":
                    return

                raw_amp = self.audio_handler.last_amplitude
                now     = asyncio.get_running_loop().time()

                # Smooth amplitude
                amp_smooth = EMA_ALPHA * raw_amp + (1 - EMA_ALPHA) * amp_smooth

                # Broadcast waveform
                amp_pct = min(100, int(raw_amp / 300 * 100))
                await self.broadcast_to_frontend({"type": "mic_amplitude", "value": amp_pct})

                # เริ่มพูด: ใช้ SPEECH_THRESHOLD / ยังพูดอยู่: ใช้ END_THRESHOLD
                active_threshold = SPEECH_THRESHOLD if not speech_detected else END_THRESHOLD

                if amp_smooth > active_threshold:
                    if not speech_detected:
                        print(f"👂 VAD: เริ่มพูด (raw={raw_amp:.0f} smooth={amp_smooth:.0f} thr={active_threshold:.0f})")
                    speech_detected = True
                    silence_start   = None
                else:
                    if silence_start is None:
                        silence_start = now
                    silent_for = now - silence_start

                    if speech_detected and silent_for >= SILENCE_AFTER_SPEECH:
                        print(f"👂 VAD: หยุดพูด {SILENCE_AFTER_SPEECH}s → ส่ง Gemini (smooth={amp_smooth:.0f})")
                        break

                    if not speech_detected and (now - no_speech_start) >= NO_SPEECH_TIMEOUT:
                        print(f"👂 VAD: ไม่มีเสียง {NO_SPEECH_TIMEOUT}s → ปิดไมค์")
                        self.audio_handler.muted = True
                        self._conversation_active = False
                        await self.broadcast_to_frontend({"type": "countdown", "seconds": 0, "total": MAX_LISTEN})
                        await self.broadcast_to_frontend({"type": "mic_amplitude", "value": 0})
                        await self.update_state("idle")
                        return

                # Countdown เฉพาะตอนยังไม่มีเสียง
                if not speech_detected:
                    remaining = max(0, int(MAX_LISTEN - elapsed))
                    if remaining != last_countdown:
                        last_countdown = remaining
                        await self.broadcast_to_frontend({"type": "countdown", "seconds": remaining, "total": MAX_LISTEN})
                elif last_countdown != MAX_LISTEN:
                    last_countdown = MAX_LISTEN
                    await self.broadcast_to_frontend({"type": "countdown", "seconds": MAX_LISTEN, "total": MAX_LISTEN})


        except asyncio.CancelledError:
            print("👂 VAD loop cancelled")
            return
        except Exception as e:
            print(f"❌ VAD loop crashed: {e} — resetting to idle")
            self.audio_handler.muted = True
            self._conversation_active = False
            await self.broadcast_to_frontend({"type": "mic_amplitude", "value": 0})
            await self.update_state("idle")
            return

        # Send ActivityEnd → Gemini processes and responds
        if self.state == "listening":
            self.audio_handler.muted = True
            await self.broadcast_to_frontend({"type": "mic_amplitude", "value": 0})
            try:
                await asyncio.to_thread(db_manager.add_conversation, "user", "[ผู้ป่วยพูด]")
            except Exception as e:
                print(f"⚠️ Failed to save user turn: {e}")
            await self.gemini_client.send_activity_end()
            await self.broadcast_to_frontend({"type": "countdown", "seconds": 0, "total": MAX_LISTEN})
            print("👂 VAD: ActivityEnd → รอ Gemini ตอบ...")
            await self.update_state("thinking")
            asyncio.create_task(self._thinking_timeout_checker())


    async def _auto_listen_after_speaking(self):
        """After Jarvis finishes speaking, open mic for next user turn.
        Waits for turn_complete then calls _start_listening + _vad_loop."""
        if self._auto_listen_running:
            return
        self._auto_listen_running = True

        try:
            await asyncio.sleep(1.2)

            if self.state != "idle":
                return
            if not self.gemini_client.is_connected:
                return

            # Wait for Gemini to signal turn is fully complete before opening mic
            print("👂 Auto-listen: รอ Gemini turn complete...")
            try:
                await asyncio.wait_for(self.gemini_client.turn_complete.wait(), timeout=12.0)
            except asyncio.TimeoutError:
                print("⚠️ Gemini turn_complete timeout — proceeding anyway")

            if self.state != "idle":
                return
            if not self.gemini_client.is_connected:
                return
            if not self._conversation_active:
                return

            # Open mic + send ActivityStart
            if not await self.gemini_client.send_activity_start():
                print("⚠️ Failed to send ActivityStart — ending conversation")
                self._conversation_active = False
                return

            self.audio_handler.muted = False
            await self.update_state("listening")
            await self.broadcast_to_frontend({
                "type": "transcript",
                "text": "🎙️ รอฟัง... พูดได้เลยครับ"
            })

            # ✅ รัน VAD loop จริงๆ แทนที่จะส่ง ActivityEnd ทันที (bug fix)
            await self._vad_loop()

        finally:
            self._auto_listen_running = False

    async def _thinking_timeout_checker(self):
        """Safety net: reset to idle if thinking for too long."""
        await asyncio.sleep(8.0)
        if self.state == "thinking":
            print("⏳ Thinking timeout: ไม่ได้รับการตอบกลับจาก Gemini → idle")
            self._conversation_active = False
            await self.update_state("idle")
            await self.broadcast_to_frontend({
                "type": "transcript",
                "text": "การเชื่อมต่อล่าช้า ลองพูดใหม่หรือแตะหน้าจอเพื่อพูดคุยอีกครั้งนะครับ"
            })

    async def _mic_amplitude_broadcast_loop(self):
        """Broadcasts mic amplitude to frontend every 50ms for waveform visualization.
        Only active during LISTENING state."""
        while True:
            await asyncio.sleep(0.05)  # 20Hz
            if self.state == "listening" and not self.audio_handler.muted:
                amp = self.audio_handler.last_amplitude
                amp_pct = min(100, int(amp / 300 * 100))
                await self.broadcast_to_frontend({
                    "type": "mic_amplitude",
                    "value": amp_pct
                })

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

        # Start mic amplitude broadcast for frontend waveform
        asyncio.create_task(self._mic_amplitude_broadcast_loop())

        # Start continuous camera monitoring
        self.camera_handler.start()
        # Disabled background monitor loop to prevent token waste (Option 1)
        # asyncio.create_task(self._camera_monitor_loop())

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
                        await asyncio.to_thread(db_manager.clear_conversation)
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
                            # Send image to Gemini as a proper turn
                            if self.gemini_client.is_connected:
                                try:
                                    import base64
                                    from google.genai import types as gtypes
                                    image_bytes = base64.b64decode(image_data["data"])
                                    await self.gemini_client.send_activity_start()
                                    await self.gemini_client.session.send_realtime_input(
                                        video=gtypes.Blob(
                                            data=image_bytes,
                                            mime_type=image_data["mime_type"]
                                        )
                                    )
                                    await self.gemini_client.session.send_realtime_input(
                                        text="ผู้ใช้กดปุ่มกล้องเพื่อให้ดูภาพ กรุณาบอกสิ่งที่เห็นในภาพเป็นภาษาไทย"
                                    )
                                    await self.gemini_client.send_activity_end()
                                    self._conversation_active = True
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
                        self.camera_handler.stop()  # Release camera for Chromium/Jitsi
                        TELEMED_URL = "https://hub-api.socare.app/videoCall?roomName=SocareTelemed"
                        # แจ้ง frontend ด้วย (เพื่อเปิด modal เผื่อหน้าจอหลุดพ้นจากหน้าสัมผัส)
                        await self.broadcast_to_frontend({
                            "type": "telemedicine_trigger",
                            "reason": "Patient requested doctor",
                            "url": TELEMED_URL
                        })
                        # เสียง tone แจ้งเตือน
                        fs = self.audio_handler.output_sample_rate
                        duration = 1.0
                        t = np.linspace(0, duration, int(fs * duration), endpoint=False)
                        tone = (np.sin(2 * np.pi * 440 * t) * 12000).astype(np.int16)
                        self.audio_handler.play_audio_chunk(tone.tobytes())
                    elif msg_type == "telemedicine_end":
                        print("🩺 Telemedicine ended, waiting for camera release...")
                        async def restart_camera_delayed():
                            await asyncio.sleep(2.5)  # Wait for Chromium to fully release /dev/video0
                            self.camera_handler.start()
                        asyncio.create_task(restart_camera_delayed())
                    elif msg_type == "ack_reminder":
                        reminder_id = data.get("reminder_id")
                        try:
                            await asyncio.to_thread(db_manager.acknowledge_reminder, reminder_id)
                            print(f"⏰ Reminder {reminder_id} acknowledged.")
                        except Exception as e:
                            print(f"⚠️ Failed to acknowledge reminder {reminder_id}: {e}")
                    elif msg_type == "inject_mock_vitals":
                        vital_type = data.get("vital_type")
                        value = data.get("value")
                        unit = data.get("unit")
                        status = data.get("status", "normal")
                        await asyncio.to_thread(db_manager.add_vital, vital_type, value, unit, status)
                        await self.send_latest_vitals_to_ui()
                        print(f"🩺 Injected vital: {vital_type}={value}{unit}")
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
                
                if now_minute != self.last_reminder_minute:
                    active_reminders = await asyncio.to_thread(db_manager.get_active_reminders)
                    for r in active_reminders:
                        if r['time'] == now_minute:
                            self.last_reminder_minute = now_minute
                            print(f"⏰ Med Alert! Triggering reminder: {r['medicine_name']} ({r['dosage']})")
                            
                            await self.broadcast_to_frontend({
                                "type": "show_card",
                                "card_type": "reminder_alert",
                                "title": "🚨 ได้เวลาทานยาแล้วครับ!",
                                "body": f"กรุณาทาน: {r['medicine_name']}\nขนาด: {r['dosage']}\nเวลา: {r['time']} น.",
                                "payload": json.dumps(r)
                            })
                            
                            if self.gemini_client.is_connected:
                                try:
                                    await self.gemini_client.session.send_realtime_input(
                                        text=f"[SYSTEM_ALERT: Medication reminder time! Please announce to the user in a warm voice: 'ได้เวลาทานยา {r['medicine_name']} ขนาด {r['dosage']} แล้วค่ะ']"
                                    )
                                except Exception as e:
                                    print(f"⚠️ Failed to send reminder alert to Gemini: {e}")
                            
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
                if self.state == "idle" and self.gemini_client.is_connected:
                    image_data = self.camera_handler.capture_as_base64_with_mime()
                    if image_data:
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

            await asyncio.sleep(60)

if __name__ == "__main__":
    manager = StateManager()
    try:
        asyncio.run(manager.start())
    except KeyboardInterrupt:
        print("\nStopping orchestrator...")

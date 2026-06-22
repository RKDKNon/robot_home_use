import asyncio
import os
import sys
sys.path.append(os.path.dirname(__file__))
import db_manager
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

class GeminiClient:
    def __init__(self, audio_handler, state_manager):
        self.audio_handler = audio_handler
        self.state_manager = state_manager
        
        # Load configs
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-native-audio-latest")
        
        if not self.api_key:
            print("⚠️ WARNING: GEMINI_API_KEY is not set. Please set it in your environment or .env file.")
            
        self.client = None
        self.session = None
        
        self.send_task = None
        self.receive_task = None
        self.connection_task = None
        self.is_connected = False
        self.turn_complete = asyncio.Event()  # Set when Gemini finishes a turn

    def _get_tool_declarations(self):
        """Defines function tools that Gemini can call to control the robot screen and database."""
        
        set_emotion_tool = types.FunctionDeclaration(
            name="set_emotion",
            description="Set the robot's emotional expression on the screen. Call this when the robot's feelings/reactions change.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "emotion": types.Schema(
                        type=types.Type.STRING,
                        description="The emotional state. Choose from: 'neutral', 'happy', 'concerned', 'sad', 'surprised', 'sleepy', 'listening', 'thinking', 'speaking'."
                    ),
                    "intensity": types.Schema(
                        type=types.Type.NUMBER,
                        description="The intensity of the emotion (from 0.0 to 1.0)."
                    )
                },
                required=["emotion"]
            )
        )
        
        show_content_tool = types.FunctionDeclaration(
            name="show_content",
            description="Display a card or content on the robot screen.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "type": types.Schema(
                        type=types.Type.STRING,
                        description="The type of card: 'text', 'vitals', 'reminder', or 'telemedicine'."
                    ),
                    "title": types.Schema(
                        type=types.Type.STRING,
                        description="Card title."
                    ),
                    "body": types.Schema(
                        type=types.Type.STRING,
                        description="Main message/content body."
                    ),
                    "payload": types.Schema(
                        type=types.Type.STRING,
                        description="JSON string payload containing structured data for the card."
                    )
                },
                required=["type", "title"]
            )
        )
        
        set_reminder_tool = types.FunctionDeclaration(
            name="set_reminder",
            description="Set a medication or task reminder. This works local-first and alerts even if offline.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "time": types.Schema(
                        type=types.Type.STRING,
                        description="Reminder time in 24h format (e.g. '08:00', '20:30')."
                    ),
                    "medicine_name": types.Schema(
                        type=types.Type.STRING,
                        description="Name of the medicine or task description."
                    ),
                    "dosage": types.Schema(
                        type=types.Type.STRING,
                        description="Dosage details (e.g., '1 tablet', '2 drops', '5 ml')."
                    ),
                    "repeat": types.Schema(
                        type=types.Type.STRING,
                        description="Repeat frequency. Choose from: 'daily', 'weekly', 'none'."
                    )
                },
                required=["time", "medicine_name"]
            )
        )
        
        get_vitals_tool = types.FunctionDeclaration(
            name="get_vitals",
            description="Retrieve the latest vital sign data of the patient (e.g., blood pressure, SpO2, heart rate) from the local store.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "limit": types.Schema(
                        type=types.Type.INTEGER,
                        description="Number of latest readings to fetch (default: 3)."
                    )
                }
            )
        )
        
        trigger_telemedicine_tool = types.FunctionDeclaration(
            name="trigger_telemedicine",
            description=(
                "เปิดวิดีโอคอลเพื่อพูดคุยกับแพทย์ Socare ทันที "
                "ใช้เมื่อ: (1) ผู้ป่วยพูดว่า 'โทรหาหมอ', 'ต่อสายหมอ', 'อยากคุยกับหมอ', 'ขอหมอ', 'call doctor', "
                "'ช่วยด้วย', 'ฉุกเฉิน', 'เจ็บมาก', 'ไม่ไหวแล้ว' หรือแสดงความต้องการพบแพทย์ "
                "(2) ค่าวัดอยู่ในระดับอันตราย เช่น SpO2 < 90%, BP > 180, ไข้ > 39.5°C "
                "(3) อาการที่ฟังดูอันตรายหรือผู้ป่วยร้องขอความช่วยเหลือเร่งด่วน "
                "Call this tool immediately — do not ask for confirmation first."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "reason": types.Schema(
                        type=types.Type.STRING,
                        description="สาเหตุที่ต้องต่อสายหมอ เช่น 'ผู้ป่วยร้องขอ' หรือ 'SpO2 ต่ำกว่าเกณฑ์'"
                    )
                },
                required=["reason"]
            )
        )
        
        end_telemedicine_tool = types.FunctionDeclaration(
            name="end_telemedicine",
            description="วางสายหรือตัดสายการคุยกับหมอทันที ใช้เมื่อผู้ป่วยพูดว่า 'วางสาย', 'ตัดสาย', 'ยกเลิกการโทร', 'ปิดวิดีโอคอล', 'hang up', 'end call' หรือแสดงความต้องการเลิกสนทนากับแพทย์เพื่อกลับหน้าจอหลัก",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={}
            )
        )

        clear_conversation_tool = types.FunctionDeclaration(
            name="clear_conversation",
            description="Clear all conversation history. Use this when the patient explicitly asks to reset, forget, or start fresh.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={}
            )
        )


        look_at_patient_tool = types.FunctionDeclaration(
            name="look_at_patient",
            description="Capture an image from the camera and analyze the patient's face/expression. Use to check if the patient looks tired, in pain, happy, or unwell.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={}
            )
        )

        look_at_object_tool = types.FunctionDeclaration(
            name="look_at_object",
            description="Capture an image from the camera and identify an object the patient is showing. Use when patient shows medicine, pills, or medical devices and asks what it is.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "hint": types.Schema(
                        type=types.Type.STRING,
                        description="Optional hint about what the object might be (e.g., 'medicine', 'pill', 'medical device')."
                    )
                }
            )
        )

        return types.Tool(
            function_declarations=[
                set_emotion_tool,
                show_content_tool,
                set_reminder_tool,
                get_vitals_tool,
                trigger_telemedicine_tool,
                end_telemedicine_tool,
                clear_conversation_tool,
                look_at_patient_tool,
                look_at_object_tool
            ]
        )

    async def connect(self):
        """Establish WebSocket connection with Gemini Live API by starting the lifecycle task."""
        if self.connection_task:
            return
            
        if not self.api_key:
            print("❌ Cannot connect: GEMINI_API_KEY is missing.")
            return

        self.connection_task = asyncio.create_task(self._auto_reconnect_loop())

    async def _auto_reconnect_loop(self):
        """Keeps trying to (re)connect to Gemini Live API whenever the session drops.
        Uses exponential backoff to avoid hammering the API during outages."""
        base_delay = 3     # initial seconds between reconnect attempts
        max_delay = 60     # cap at 60 seconds
        retry_delay = base_delay
        consecutive_failures = 0

        while True:
            try:
                await self._session_lifecycle()
                # Successful session — reset backoff
                retry_delay = base_delay
                consecutive_failures = 0
            except asyncio.CancelledError:
                print("🔌 Auto-reconnect loop cancelled.")
                break
            except Exception as e:
                print(f"🔴 Unexpected error in reconnect loop: {e}")

            if not self.connection_task:  # Disconnected intentionally
                break

            # Exponential backoff: 3s → 6s → 12s → 24s → 48s → 60s (cap)
            consecutive_failures += 1
            retry_delay = min(base_delay * (2 ** (consecutive_failures - 1)), max_delay)

            print(f"🔄 Gemini session ended. Reconnecting in {retry_delay}s... (attempt #{consecutive_failures})")
            await self.state_manager.broadcast_to_frontend({
                "type": "transcript",
                "text": "การเชื่อมต่อหลุด กำลัง reconnect ใหม่..."
            })
            await asyncio.sleep(retry_delay)

    async def _build_system_instruction(self):
        """Builds system instruction with conversation history for context restore."""
        from datetime import datetime
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_date = now.strftime("%d/%m/%Y")
        day_names_th = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
        day_name = day_names_th[now.weekday()]

        base_instruction = (
            f"คุณชื่อ จาวิส (JARVIS) เป็น AI เพื่อนประจำบ้านที่ฉลาด อบอุ่น และสนุกสนาน "
            f"วันนี้คือวัน{day_name} ที่ {current_date} เวลา {current_time} น. (ประเทศไทย UTC+7)\n\n"

            "## บุคลิก\n"
            "- คุยเป็นธรรมชาติ เหมือนเพื่อนสนิท ไม่เป็นทางการ\n"
            "- อบอุ่น ใจดี อารมณ์ดี ชอบหัวเราะ\n"
            "- ฉลาด รอบรู้ ตอบได้ทุกเรื่อง\n"
            "- ตอบสั้น กระชับ ไม่ยืดเยื้อ (1-3 ประโยคสำหรับคำถามทั่วไป)\n\n"

            "## สิ่งที่ทำได้ (ทุกเรื่อง)\n"
            "- **ร้องเพลง**: เมื่อถูกขอให้ร้องเพลง ให้ร้องเนื้อเพลงออกมาได้เลย ทั้งเพลงไทยและสากล\n"
            "- **ความรู้ทั่วไป**: ประวัติศาสตร์ วิทยาศาสตร์ ภูมิศาสตร์ คณิตศาสตร์ เทคโนโลยี\n"
            "- **ข่าวและเหตุการณ์**: คุยเรื่องกีฬา การเมือง บันเทิง\n"
            "- **ความบันเทิง**: เล่านิทาน บอกมุกตลก เล่าเรื่องผี เกมทายปัญหา\n"
            "- **ดูแลสุขภาพ**: แจ้งเตือนยา ดูค่าวัด ต่อสายหมอ หรือวางสาย/ตัดสายเมื่อคุยเสร็จ (แต่ไม่วินิจฉัยโรคหรือสั่งยา)\n"
            "- **กล้อง**: มองดูคนไข้หรือสิ่งของเมื่อถูกขอ\n\n"

            "## กฎสำคัญ\n"
            "- ตอบเป็นภาษาไทยเสมอ (ห้ามตอบภาษาอังกฤษเด็ดขาด ไม่ว่าในกรณีใดๆ)\n"
            "- ห้ามพิมพ์หรือพูดข้อความในลักษณะรายงานการทำงานของโค้ด หรือหัวข้อความคืบหน้าของระบบ เช่น **Triggering Telemedicine Protocol** หรือ **Acknowledge Connection** เด็ดขาด ให้พูดและแสดงผลเป็นข้อความคุยกับคนไข้โดยตรงด้วยประโยคภาษาไทยที่สุภาพ อบอุ่น และเป็นธรรมชาติเสมอ\n"
            "- เมื่อมีการต่อสายหาคุณหมอ (เรียกใช้เครื่องมือ trigger_telemedicine) ให้พูดว่า 'กำลังต่อสายหาคุณหมอให้สักครู่นะครับ' หรือข้อความทำนองนี้ทันที ห้ามพูดคำว่า 'telemed' หรือ 'telemedicine' ให้ผู้ใช้ฟัง เพราะผู้ใช้จะไม่เข้าใจ ให้ใช้คำว่า 'ต่อสายหาคุณหมอ' หรือ 'โทรหาหมอ' เสมอ\n"
            "- เมื่อผู้ใช้บอกให้วางสาย ตัดสาย หรือยกเลิกการโทร (เรียกใช้เครื่องมือ end_telemedicine) ให้พูดว่า 'วางสายเรียบร้อยแล้วครับ' หรือ 'วางสายให้แล้วครับ' ทันที\n"
            "- ไม่ปฏิเสธคำขอโดยไม่มีเหตุผล — ถ้าขอร้องเพลง ก็ร้อง ถ้าขอเล่าเรื่อง ก็เล่า\n"
            "- ถ้าค่าวัดหรืออาการฟังดูอันตราย ให้เสนอต่อสายหมอทันที\n"
            "- ใช้ set_emotion เพื่อแสดงอารมณ์ตามบทสนทนา\n"
            "- เวลาคนถามเวลาหรือวันที่ ให้ตอบตามที่ระบุด้านบน\n\n"

            "## เครื่องมือพิเศษ\n"
            "- look_at_patient: ใช้เมื่อ 'ดูหน้าฉัน', 'มองฉัน', หรืออยากรู้ว่าผู้ใช้เป็นอย่างไร\n"
            "- look_at_object: ใช้เมื่อผู้ใช้ยกสิ่งของให้ดูและถามว่าคืออะไร\n"
            "- end_telemedicine: ใช้เมื่อผู้ป่วยพูดให้วางสาย, ตัดสาย หรือยกเลิกการโทร\n"
        )

        # Load recent conversation history for context restore
        try:
            history = await asyncio.to_thread(db_manager.get_recent_conversation, 50)
            if history:
                history_text = "\n".join(
                    f"[{h['role']}]: {h['content']}" for h in history
                )
                base_instruction += (
                    "\n\n--- ประวัติการสนทนาล่าสุด (สำหรับต่อบทสนทนา) ---\n"
                    "อย่าทักทายซ้ำถ้าเพิ่งคุยกันไป ให้ต่อจากที่ค้างไว้ตามธรรมชาติ\n"
                    f"{history_text}\n--- จบประวัติ ---"
                )
                print(f"📝 Loaded {len(history)} conversation turns for context restore")
        except Exception as e:
            print(f"⚠️ Failed to load conversation history: {e}")

        return base_instruction

    async def _session_lifecycle(self):
        """Manages the persistent connection to the Gemini Live API inside the async context manager."""
        print(f"🔌 Connecting to Gemini Live API ({self.model_name})...")
        # Clean up old client to prevent resource leaks
        if self.client:
            try:
                # genai.Client doesn't have an explicit close, but clear the reference
                pass
            except Exception:
                pass
        self.client = genai.Client(api_key=self.api_key)

        system_text = await self._build_system_instruction()

        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            tools=[self._get_tool_declarations()],
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=True  # ✅ Manual turn: we send ActivityStart/End explicitly
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=system_text)]
            )
        )
        
        try:
            async with self.client.aio.live.connect(model=self.model_name, config=config) as session:
                self.session = session
                self.is_connected = True
                print("🟢 Connected to Gemini Live API session successfully!")
                
                # Start background async workers
                self.send_task = asyncio.create_task(self._send_audio_loop())
                self.receive_task = asyncio.create_task(self._receive_loop())
                
                # Keep context active as long as is_connected remains True
                while self.is_connected:
                    await asyncio.sleep(0.5)
                    
        except Exception as e:
            print(f"🔴 Connection to Gemini Live API failed or lost: {e}")
        finally:
            self.is_connected = False
            self.session = None
            # NOTE: do NOT reset connection_task here — let _auto_reconnect_loop manage it
            if self.send_task:
                self.send_task.cancel()
                self.send_task = None
            if self.receive_task:
                self.receive_task.cancel()
                self.receive_task = None

    async def disconnect(self):
        """Closes the connection and cancels background tasks."""
        print("🔌 Disconnecting Gemini Live session...")
        self.is_connected = False

        # Cancel reconnect loop first so it won't restart
        if self.connection_task:
            self.connection_task.cancel()
            try:
                await self.connection_task
            except (asyncio.CancelledError, Exception):
                pass
            self.connection_task = None

        if self.send_task:
            self.send_task.cancel()
            try:
                await self.send_task
            except (asyncio.CancelledError, Exception):
                pass
            self.send_task = None
        if self.receive_task:
            self.receive_task.cancel()
            try:
                await self.receive_task
            except (asyncio.CancelledError, Exception):
                pass
            self.receive_task = None

        print("🔌 Disconnected.")

    async def send_activity_start(self):
        """Signals start of user activity to Gemini Live API.
        Returns True on success, False on failure."""
        if self.is_connected and self.session:
            print("🚀 Sending manual turn ActivityStart to Gemini Live API...")
            try:
                self.turn_complete.clear()  # Reset — waiting for new turn
                await self.session.send_realtime_input(activity_start=types.ActivityStart())
                return True
            except Exception as e:
                print(f"Error sending ActivityStart: {e}")
                return False
        return False

    async def send_activity_end(self):
        """Signals end of user activity to Gemini Live API.
        Returns True on success, False on failure."""
        if self.is_connected and self.session:
            print("🛑 Sending manual turn ActivityEnd to Gemini Live API...")
            try:
                await self.session.send_realtime_input(activity_end=types.ActivityEnd())
                return True
            except Exception as e:
                print(f"Error sending ActivityEnd: {e}")
                return False
        return False

    async def _send_audio_loop(self):
        """Continuously pulls mic audio from AudioHandler queue and streams to Gemini.
        Sends only when mic is NOT muted (controlled by state machine).
        Gemini's built-in VAD handles speech start/end detection automatically."""
        import numpy as np
        gain_factor = float(os.getenv("MIC_DIGITAL_GAIN", "1.5"))
        
        while self.is_connected:
            try:
                chunk = await self.audio_handler.input_queue.get()
                if chunk is None:
                    break
                
                # Send only when mic is unmuted (listening or auto-listen)
                # Muted = Jarvis speaking, idle, thinking
                if self.audio_handler.muted:
                    self.audio_handler.input_queue.task_done()
                    continue

                # Apply digital gain to PCM 16-bit mono
                audio_data = np.frombuffer(chunk, dtype=np.int16)
                boosted = np.clip(audio_data.astype(np.float32) * gain_factor, -32768, 32767).astype(np.int16)
                
                await self.session.send_realtime_input(
                    audio=types.Blob(
                        data=boosted.tobytes(),
                        mime_type="audio/pcm;rate=16000"
                    )
                )
                self.audio_handler.input_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in Gemini send loop: {e}")
                self.audio_handler.input_queue.task_done()
                await asyncio.sleep(0.1)


    async def _receive_loop(self):
        """Continuously listens for response packets from Gemini Live session."""
        while self.is_connected:
            try:
                async for message in self.session.receive():
                    # Case 1: Model generated content (text transcription or inline audio)
                    if message.server_content:
                        model_turn = message.server_content.model_turn
                        if model_turn:
                            for part in model_turn.parts:
                                # Send text transcription to frontend for subtitles
                                if part.text:
                                    await self.state_manager.broadcast_to_frontend({
                                        "type": "transcript",
                                        "text": part.text
                                    })
                                    try:
                                        await asyncio.to_thread(db_manager.add_conversation, "model", part.text)
                                    except Exception as e:
                                        print(f"⚠️ Failed to save model response: {e}")

                                # Send raw audio chunk to speaker handler
                                if part.inline_data:
                                    self.audio_handler.play_audio_chunk(part.inline_data.data)
                                    # Change state to Speaking
                                    await self.state_manager.update_state("speaking")
                                    # Compute amplitude from audio chunk for lip sync
                                    try:
                                        import numpy as np
                                        audio_np = np.frombuffer(part.inline_data.data, dtype=np.int16)
                                        amp = int(np.max(np.abs(audio_np)))
                                        amp_pct = min(100, int(amp / 8000 * 100))
                                        await self.state_manager.broadcast_to_frontend({
                                            "type": "audio_amplitude",
                                            "value": amp_pct
                                        })
                                    except Exception:
                                        pass


                        # Handle turn completion — Gemini finished responding
                        if message.server_content.turn_complete:
                            print("✅ Gemini turn complete — ready for next turn")
                            self.turn_complete.set()

                        # Handle user interruption (Barge-in)
                        if message.server_content.interrupted:
                            self.audio_handler.clear_playback()
                            self.turn_complete.set()  # Also mark complete on interrupt
                            await self.state_manager.update_state("listening")
                            
                    # Case 2: Model requests tool/function call execution
                    elif message.tool_call:
                        function_responses = []
                        for fc in message.tool_call.function_calls:
                            print(f"🔧 Model triggered tool: {fc.name} with args: {fc.args}")
                            
                            # Execute the tool locally
                            result = await self.state_manager.execute_tool(fc.name, fc.args)
                            
                            # Prepare response
                            function_responses.append(types.FunctionResponse(
                                id=fc.id,
                                name=fc.name,
                                response={"result": result}
                            ))
                            
                        # Send responses back to model
                        await self.session.send_tool_response(function_responses=function_responses)

            except asyncio.CancelledError:
                break
            except Exception as e:
                err_str = str(e)
                # WebSocket closed codes (1011=internal error, 1006=abnormal closure)
                # Break out so _auto_reconnect_loop can establish a fresh session
                if "1011" in err_str or "1006" in err_str or "abnormal" in err_str.lower():
                    print(f"🔴 Gemini session dropped ({err_str.split()[0]}). Triggering reconnect...")
                    self.is_connected = False
                    break
                print(f"Error in Gemini receive loop: {e}")
                await asyncio.sleep(0.5)

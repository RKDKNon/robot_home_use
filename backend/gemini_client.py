import asyncio
import os
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
            description="Escalate and initiate a virtual consult or telemedicine call with Socare dashboard.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "reason": types.Schema(
                        type=types.Type.STRING,
                        description="Reason for escalation (e.g., critical vital signs, user request)."
                    )
                },
                required=["reason"]
            )
        )

        return types.Tool(
            function_declarations=[
                set_emotion_tool,
                show_content_tool,
                set_reminder_tool,
                get_vitals_tool,
                trigger_telemedicine_tool
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
        """Keeps trying to (re)connect to Gemini Live API whenever the session drops."""
        retry_delay = 3  # seconds between reconnect attempts
        while True:
            try:
                await self._session_lifecycle()
            except asyncio.CancelledError:
                print("🔌 Auto-reconnect loop cancelled.")
                break
            except Exception as e:
                print(f"🔴 Unexpected error in reconnect loop: {e}")
            
            if not self.connection_task:  # Disconnected intentionally
                break
                
            print(f"🔄 Gemini session ended. Reconnecting in {retry_delay}s...")
            await self.state_manager.broadcast_to_frontend({
                "type": "transcript",
                "text": "การเชื่อมต่อหลุด กำลัง reconnect ใหม่..."
            })
            await asyncio.sleep(retry_delay)

    async def _session_lifecycle(self):
        """Manages the persistent connection to the Gemini Live API inside the async context manager."""
        print(f"🔌 Connecting to Gemini Live API ({self.model_name})...")
        self.client = genai.Client(api_key=self.api_key)
        
        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            tools=[self._get_tool_declarations()],
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=True  # ✅ Manual turn: we send ActivityStart/End explicitly
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part.from_text(
                    text="You are an empathetic, desktop-based Health Assistant AI Robot. "
                         "You communicate with voice (Thai language) and express emotions. "
                         "You help elderly patients at home monitor vitals, notify medication times, "
                         "and connect to telemedicine (Socare) when needed. "
                         "Provide concise, comforting advice. DO NOT diagnose or prescribe medication. "
                         "If vitals look dangerous, or if they ask to see a doctor, trigger the telemedicine tool immediately. "
                         "Use set_emotion tool to adjust your feelings (happy, concerned, etc.) along with your talking."
                )]
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
            self.connection_task = None
            
        if self.send_task:
            self.send_task.cancel()
            self.send_task = None
        if self.receive_task:
            self.receive_task.cancel()
            self.receive_task = None
            
        print("🔌 Disconnected.")

    async def send_activity_start(self):
        """Signals start of user activity to Gemini Live API."""
        if self.is_connected and self.session:
            print("🚀 Sending manual turn ActivityStart to Gemini Live API...")
            try:
                await self.session.send_realtime_input(activity_start=types.ActivityStart())
            except Exception as e:
                print(f"Error sending ActivityStart: {e}")

    async def send_activity_end(self):
        """Signals end of user activity to Gemini Live API."""
        if self.is_connected and self.session:
            print("🛑 Sending manual turn ActivityEnd to Gemini Live API...")
            try:
                await self.session.send_realtime_input(activity_end=types.ActivityEnd())
            except Exception as e:
                print(f"Error sending ActivityEnd: {e}")

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
                                
                                # Send raw audio chunk to speaker handler
                                if part.inline_data:
                                    self.audio_handler.play_audio_chunk(part.inline_data.data)
                                    # Change state to Speaking
                                    await self.state_manager.update_state("speaking")
                                    
                        # Handle user interruption (Barge-in)
                        if message.server_content.interrupted:
                            self.audio_handler.clear_playback()
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

import asyncio
import os
import sys
import wave
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-2.5-flash-native-audio-latest"

if not API_KEY:
    print("Error: GEMINI_API_KEY is not set.")
    sys.exit(1)

def get_tool_declarations():
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

async def main():
    wav_path = "test_mic_record.wav"
    if not os.path.exists(wav_path):
        print(f"Error: {wav_path} not found.")
        sys.exit(1)

    with wave.open(wav_path, "rb") as w:
        raw_pcm = w.readframes(w.getnframes())

    print(f"Read {len(raw_pcm)} bytes of raw PCM data.")
    print(f"🔌 Connecting to Gemini Live API with TOOLS...")
    client = genai.Client(api_key=API_KEY)
    
    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        tools=[get_tool_declarations()],
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                disabled=True
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
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            print("🟢 Connected! Sending ActivityStart...")
            await session.send_realtime_input(activity_start=types.ActivityStart())
            
            chunk_size = 2048
            delay = 0.064
            
            print("🎙️ Streaming WAV PCM data...")
            for i in range(0, len(raw_pcm), chunk_size):
                chunk = raw_pcm[i:i+chunk_size]
                if not chunk:
                    break
                await session.send_realtime_input(
                    audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                )
                await asyncio.sleep(delay)
                
            print("🛑 Sending ActivityEnd...")
            await session.send_realtime_input(activity_end=types.ActivityEnd())
            
            print("📥 Waiting for AI response...")
            async for message in session.receive():
                if message.server_content:
                    model_turn = message.server_content.model_turn
                    if model_turn:
                        for part in model_turn.parts:
                            if part.text:
                                print(f"Transcript: {part.text}")
                            if part.inline_data:
                                print(f"Received audio chunk: {len(part.inline_data.data)} bytes")
                                
            print("🏁 Finished waiting.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())

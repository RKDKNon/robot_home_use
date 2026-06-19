import asyncio
import os
import sys
import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-2.5-flash-native-audio-latest"

if not API_KEY:
    print("Error: GEMINI_API_KEY is not set.")
    sys.exit(1)

print(f"🔌 Connecting to Gemini Live API ({MODEL})...")
client = genai.Client(api_key=API_KEY)

# Setup output speaker stream
sample_rate = 24000
channels = 1
speaker_stream = sd.RawOutputStream(
    samplerate=sample_rate,
    channels=channels,
    dtype='int16',
    blocksize=1024
)
speaker_stream.start()

async def main():
    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                disabled=True
            )
        ),
        system_instruction=types.Content(
            parts=[types.Part.from_text(text="You are a warm Thai voice assistant. Reply in Thai.")]
        )
    )
    
    try:
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            print("🟢 Connected! Sending ActivityStart...")
            await session.send_realtime_input(activity_start=types.ActivityStart())
            
            print("💬 Sending prompt: 'สวัสดีครับ ยินดีที่ได้รู้จักนะ'")
            await session.send_realtime_input(text="สวัสดีครับ ยินดีที่ได้รู้จักนะ ช่วยทักทายฉันด้วยเสียงหน่อยครับ")
            
            print("🛑 Sending ActivityEnd...")
            await session.send_realtime_input(activity_end=types.ActivityEnd())
            
            print("📥 Waiting for AI voice response... (playing to speaker)")
            
            # Listen for responses
            async for message in session.receive():
                # Print any messages we receive
                print(f"Received raw message: {message}")
                
                if message.server_content:
                    model_turn = message.server_content.model_turn
                    if model_turn:
                        for part in model_turn.parts:
                            if part.text:
                                print(f"Transcript: {part.text}")
                            if part.inline_data:
                                # Play raw audio chunk directly
                                print(f"Playing audio chunk: {len(part.inline_data.data)} bytes")
                                speaker_stream.write(part.inline_data.data)
                                
            # Wait a bit after playing
            await asyncio.sleep(5)
            
    except Exception as e:
        print(f"Error during live session: {e}")
    finally:
        speaker_stream.stop()
        speaker_stream.close()

if __name__ == "__main__":
    asyncio.run(main())

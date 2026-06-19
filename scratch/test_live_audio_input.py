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

async def main():
    wav_path = "test_mic_record.wav"
    if not os.path.exists(wav_path):
        print(f"Error: {wav_path} not found.")
        sys.exit(1)

    # Open WAV file and read properties
    with wave.open(wav_path, "rb") as w:
        params = w.getparams()
        print(f"WAV Info: channels={params.nchannels}, sampwidth={params.sampwidth}, framerate={params.framerate}")
        if params.framerate != 16000 or params.nchannels != 1 or params.sampwidth != 2:
            print("Warning: WAV should be 16000Hz, 1 channel, 16-bit PCM.")
        raw_pcm = w.readframes(w.getnframes())

    print(f"Read {len(raw_pcm)} bytes of raw PCM data.")

    print(f"🔌 Connecting to Gemini Live API ({MODEL})...")
    client = genai.Client(api_key=API_KEY)
    
    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                disabled=True
            )
        ),
        system_instruction=types.Content(
            parts=[types.Part.from_text(text="You are a helpful assistant. Reply in Thai.")]
        )
    )

    try:
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            print("🟢 Connected! Sending ActivityStart...")
            await session.send_realtime_input(activity_start=types.ActivityStart())
            
            # Stream the raw PCM in chunks
            chunk_size = 2048 # 1024 samples * 2 bytes/sample
            delay = 0.064 # Time to play 1024 samples at 16kHz
            
            print("🎙️ Streaming WAV PCM data to Gemini...")
            for i in range(0, len(raw_pcm), chunk_size):
                chunk = raw_pcm[i:i+chunk_size]
                if not chunk:
                    break
                
                await session.send_realtime_input(
                    audio=types.Blob(
                        data=chunk,
                        mime_type="audio/pcm;rate=16000"
                    )
                )
                await asyncio.sleep(delay)
                
            print("🛑 Streaming complete. Sending ActivityEnd...")
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

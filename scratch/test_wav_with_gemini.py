import os
import sys
from google import genai
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    print("Error: GEMINI_API_KEY is not set.")
    sys.exit(1)

print("Testing test_mic_record.wav with Gemini...")
client = genai.Client(api_key=API_KEY)

try:
    if not os.path.exists("test_mic_record.wav"):
        print("Error: test_mic_record.wav not found. Run record_wav.py first.")
        sys.exit(1)
        
    with open("test_mic_record.wav", "rb") as f:
        audio_data = f.read()
        
    print(f"Read {len(audio_data)} bytes of audio data.")
    
    # We send it to gemini-2.5-flash since it natively supports audio
    print("Sending audio to Gemini-2.5-flash...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            "Please transcribe this audio. If there is no speech, say 'No speech detected'.",
            {
                "inline_data": {
                    "data": audio_data,
                    "mime_type": "audio/wav"
                }
            }
        ]
    )
    
    print("\n--- Gemini Response ---")
    print(response.text)
    print("-----------------------")
    
except Exception as e:
    print(f"Error: {e}")

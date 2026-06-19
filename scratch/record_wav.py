import sounddevice as sd
import soundfile as sf
import os

print("🎙️ Recording 5 seconds of audio to test_mic_record.wav...")
fs = 16000
duration = 5.0

try:
    print("Default input device:", sd.query_devices(kind='input')['name'])
    myrecording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
    sd.wait()
    print("Recording finished.")
    
    # Save as WAV file
    output_path = "test_mic_record.wav"
    sf.write(output_path, myrecording, fs)
    print(f"Saved recording to: {os.path.abspath(output_path)}")
except Exception as e:
    print(f"Error during recording: {e}")

import sounddevice as sd
import numpy as np
import time

print("🎙️ Testing Microphone and Speaker on Raspberry Pi...")
try:
    print("Default Input Device:", sd.query_devices(kind='input')['name'])
    print("Default Output Device:", sd.query_devices(kind='output')['name'])
except Exception as e:
    print("Could not query default devices:", e)

duration = 3.0  # seconds
fs = 16000     # Sample rate (16kHz)

print("\n🔴 RECORDING... Please speak into the microphone now (for 3 seconds)...")
try:
    # Record 16-bit PCM mono
    myrecording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
    sd.wait()  # Wait until the recording is finished
    print("🟢 RECORDING COMPLETE.")
except Exception as e:
    print("❌ Error during recording:", e)
    myrecording = None

if myrecording is not None and np.max(np.abs(myrecording)) > 0:
    print(f"Signal detected (Max amplitude: {np.max(np.abs(myrecording))})")
    print("\n🔊 PLAYING BACK... Listen to your speakers now...")
    try:
        sd.play(myrecording, fs)
        sd.wait()  # Wait until the audio is played
        print("🟢 PLAYBACK COMPLETE.")
    except Exception as e:
        print("❌ Error during playback:", e)
elif myrecording is not None:
    print("⚠️ Warning: Silent recording. No mic signal detected (all zeros). Check mic connections/volume.")
    print("🔊 Attempting playback anyway...")
    try:
        # Play a simple synthesized beep so we can at least test the speaker
        t = np.linspace(0, 1, fs, endpoint=False)
        beep = (np.sin(2 * np.pi * 440 * t) * 10000).astype(np.int16)
        sd.play(beep, fs)
        sd.wait()
        print("🟢 Synth playback complete.")
    except Exception as e:
        print("❌ Error playing synth:", e)

print("\n🏁 Test finished.")

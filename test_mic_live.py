import sounddevice as sd
import numpy as np
import time
import sys

print("🎙️ Real-time Mic Amplitude Test (Press Ctrl+C to stop) 🎙️")
print("Please speak or make some noise to see if the levels change.")
print("If the amplitude stays under 100, the mic is practically silent.")

def callback(indata, frames, time_info, status):
    if status:
        print(f"Warning: {status}", file=sys.stderr)
    audio_data = np.frombuffer(indata, dtype=np.int16)
    max_val = np.max(np.abs(audio_data))
    # Print a simple visual volume bar
    bar_length = int(max_val / 300)
    bar = "█" * min(bar_length, 50)
    sys.stdout.write(f"\rMax Amplitude: {max_val:5d} | {bar:<50}")
    sys.stdout.flush()

try:
    stream = sd.RawInputStream(
        samplerate=16000,
        channels=1,
        dtype='int16',
        blocksize=1024,
        callback=callback
    )
    with stream:
        while True:
            time.sleep(0.1)
except KeyboardInterrupt:
    print("\nStopped.")
except Exception as e:
    print(f"\nError starting stream: {e}")

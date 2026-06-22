import asyncio
import os
import queue
import threading
import numpy as np
import sounddevice as sd

class AudioHandler:
    def __init__(self, loop=None):
        self.loop = loop or asyncio.get_event_loop()  # Will be overridden by start() with running loop
        # Queue for captured mic audio (asyncio.Queue for backend to consume)
        self.input_queue = asyncio.Queue()
        # Queue for speaker audio (std queue.Queue for playback thread to consume)
        self.output_queue = queue.Queue()

        self.input_stream = None
        self.output_stream = None
        self._output_stream_lock = threading.Lock()  # Protect stream stop/start during barge-in

        self.play_thread = None
        self.is_playing = False

        # Audio formats
        self.gemini_audio_rate = 24000  # Gemini Live returns 24kHz
        self.output_sample_rate = 44100 # Pi Headphones native rate (device 2)
        self.input_sample_rate = 16000  # Gemini Live expects 16kHz input
        self.channels = 1
        self.chunk_size = 1024          # Number of frames per chunk

        # Device selection (configurable via .env)
        # Pi: device 2 = bcm2835 Headphones (3.5mm jack)
        # Set AUDIO_OUTPUT_DEVICE=-1 to use system default
        _out_env = os.getenv("AUDIO_OUTPUT_DEVICE", "2")
        self.output_device = int(_out_env) if _out_env.lstrip('-').isdigit() else None
        _in_env = os.getenv("AUDIO_INPUT_DEVICE", "")
        self.input_device = int(_in_env) if _in_env.strip().isdigit() else None

        # Flags
        self.recording = False
        self.muted = False
        self.last_amplitude = 0  # Updated every chunk for VAD

        # Callback for state change: def cb(is_playing: bool)
        self.on_playback_state_change = None

        # Shared mic consumers — other modules (e.g. wake word) can register
        # a callback(bytes) to receive raw mic audio without opening a second stream.
        # This prevents device conflicts on Raspberry Pi.
        self._mic_consumers = []  # list of callable(data_bytes)

    def register_mic_consumer(self, callback):
        """Register a callback(bytes) to receive raw mic audio chunks."""
        self._mic_consumers.append(callback)

    def unregister_mic_consumer(self, callback):
        """Remove a previously registered mic consumer."""
        try:
            self._mic_consumers.remove(callback)
        except ValueError:
            pass

    def start(self):
        """Starts both recording and playback streams."""
        self.start_playback()
        self.start_recording()

    def stop(self):
        """Stops all audio activities."""
        self.stop_recording()
        self.stop_playback()

    # --- Recording (Microphone) ---

    def _input_callback(self, indata, frames, time, status):
        """Callback from sounddevice when microphone data is ready."""
        if status:
            print(f"Audio Input Warning: {status}")
        if not self.recording:
            return

        data_bytes = bytes(indata)

        # Always dispatch to shared mic consumers (wake word, etc.)
        # even when muted — they need continuous audio for keyword spotting.
        for consumer in self._mic_consumers:
            try:
                consumer(data_bytes)
            except Exception as e:
                print(f"Mic consumer error: {e}")

        if not self.muted:
            audio_data = np.frombuffer(data_bytes, dtype=np.int16)
            max_val = int(np.max(np.abs(audio_data)))
            self.last_amplitude = max_val  # Expose for VAD
            self.loop.call_soon_threadsafe(self.input_queue.put_nowait, data_bytes)

    def start_recording(self):
        """Starts recording audio from microphone."""
        if self.recording:
            return
        self.recording = True
        try:
            self.input_stream = sd.RawInputStream(
                samplerate=self.input_sample_rate,
                channels=self.channels,
                dtype='int16',
                blocksize=self.chunk_size,
                callback=self._input_callback
            )
            self.input_stream.start()
            print("🎙️ Microphone stream started successfully.")
        except Exception as e:
            print(f"⚠️ Could not start microphone stream: {e}. Falling back to silent mock input.")
            self.input_stream = None

    def stop_recording(self):
        """Stops microphone recording."""
        self.recording = False
        if self.input_stream:
            try:
                self.input_stream.stop()
                self.input_stream.close()
            except Exception as e:
                print(f"Error closing input stream: {e}")
            self.input_stream = None
        print("🎙️ Microphone stream stopped.")

    # --- Playback (Speaker) ---

    def start_playback(self):
        """Starts the background speaker playback thread."""
        if self.is_playing:
            return
        self.is_playing = True
        
        try:
            dev_name = sd.query_devices(self.output_device)['name'] if self.output_device is not None else 'default'
            print(f"🔊 Starting speaker stream on device {self.output_device} ({dev_name})...")
            self.output_stream = sd.RawOutputStream(
                samplerate=self.output_sample_rate,
                channels=self.channels,
                dtype='int16',
                blocksize=self.chunk_size,
                device=self.output_device
            )
            self.output_stream.start()
            print("🔊 Speaker stream started successfully.")
        except Exception as e:
            print(f"⚠️ Could not start speaker on device {self.output_device}: {e}. Trying default...")
            try:
                self.output_stream = sd.RawOutputStream(
                    samplerate=self.output_sample_rate,
                    channels=self.channels,
                    dtype='int16',
                    blocksize=self.chunk_size
                )
                self.output_stream.start()
                print("🔊 Speaker stream started on default device.")
            except Exception as e2:
                print(f"⚠️ Could not start speaker stream: {e2}. Audio output will be mocked.")
                self.output_stream = None
            
        self.play_thread = threading.Thread(target=self._play_loop, daemon=True)
        self.play_thread.start()

    def _play_loop(self):
        """Background thread worker that reads from the queue and writes to the speaker."""
        was_playing = False
        empty_count = 0
        
        while self.is_playing:
            try:
                # Block for a chunk of audio (short timeout to respond quickly)
                chunk = self.output_queue.get(timeout=0.05)
                
                if chunk is None:  # Sentinel value to exit
                    break
                
                if not was_playing:
                    was_playing = True
                    if self.on_playback_state_change:
                        self.loop.call_soon_threadsafe(self.on_playback_state_change, True)
                
                if self.output_stream:
                    try:
                        with self._output_stream_lock:
                            self.output_stream.write(chunk)
                    except Exception as e:
                        print(f"Error writing audio to speaker: {e}")
                self.output_queue.task_done()
                empty_count = 0
                
            except queue.Empty:
                if was_playing:
                    empty_count += 1
                    # 50 timeouts of 0.05s is 2.5s of silence, indicating playback finished
                    # (Gemini may have network jitter > 500ms, so we wait longer)
                    if empty_count >= 50:
                        was_playing = False
                        if self.on_playback_state_change:
                            self.loop.call_soon_threadsafe(self.on_playback_state_change, False)
                continue

    def stop_playback(self):
        """Stops the speaker playback thread."""
        self.is_playing = False
        if self.play_thread:
            self.output_queue.put(None) # Send sentinel to exit thread loop
            self.play_thread.join(timeout=1.0)
            self.play_thread = None
            
        if self.output_stream:
            try:
                self.output_stream.stop()
                self.output_stream.close()
            except Exception as e:
                print(f"Error closing output stream: {e}")
            self.output_stream = None
        print("🔊 Speaker stream stopped.")

    def _resample(self, data_bytes: bytes, src_rate: int, dst_rate: int) -> bytes:
        """Resample PCM int16 audio from src_rate to dst_rate using numpy linear interpolation."""
        if src_rate == dst_rate:
            return data_bytes
        audio = np.frombuffer(data_bytes, dtype=np.int16).astype(np.float32)
        n_out = int(len(audio) * dst_rate / src_rate)
        if n_out == 0:
            return b''
        resampled = np.interp(
            np.linspace(0, len(audio) - 1, n_out),
            np.arange(len(audio)),
            audio
        ).astype(np.int16)
        return resampled.tobytes()

    def play_audio_chunk(self, chunk: bytes):
        """Appends a Gemini 24kHz 16-bit mono PCM chunk to the playback queue,
        resampled to the speaker's native rate (44100Hz) first."""
        if self.is_playing:
            # Resample from Gemini rate (24kHz) to device rate (44100Hz)
            resampled = self._resample(chunk, self.gemini_audio_rate, self.output_sample_rate)
            self.output_queue.put(resampled)

    def clear_playback(self):
        """Clears all queued playback audio immediately (Barge-in / Interruption)."""
        print("🛑 Clearing audio queue (Interruption / Barge-in)...")
        # Empty the queue
        try:
            while not self.output_queue.empty():
                self.output_queue.get_nowait()
                self.output_queue.task_done()
        except queue.Empty:
            pass
        except ValueError: # Occurs if task_done is called too many times
            pass
            
        # Re-start output stream to flush internal hardware buffers
        if self.output_stream:
            try:
                with self._output_stream_lock:
                    self.output_stream.stop()
                    self.output_stream.start()
            except Exception as e:
                print(f"Error resetting speaker stream: {e}")

if __name__ == "__main__":
    import time
    print("Testing AudioHandler (capturing 3 seconds of mic and playing it back)...")
    loop = asyncio.new_event_loop()
    
    async def test():
        handler = AudioHandler(loop=loop)
        handler.start()
        
        print("Recording...")
        recorded_chunks = []
        for _ in range(60): # ~3 seconds
            try:
                chunk = await asyncio.wait_for(handler.input_queue.get(), timeout=1.0)
                recorded_chunks.append(chunk)
            except asyncio.TimeoutError:
                print("Timeout waiting for audio input.")
                break
                
        print(f"Recorded {len(recorded_chunks)} chunks. Playing back...")
        
        # We need to resample/adjust samplerate or play at recorded rate (16kHz).
        # Let's temporarily recreate speaker stream at 16kHz for exact playback test.
        handler.stop_playback()
        handler.output_sample_rate = 16000
        handler.start_playback()
        
        for chunk in recorded_chunks:
            handler.play_audio_chunk(chunk)
            
        # Wait until played
        time.sleep(3.5)
        handler.stop()
        print("Test complete.")

    loop.run_until_complete(test())

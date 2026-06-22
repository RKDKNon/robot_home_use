import asyncio
import threading
import json
import os
import numpy as np

class WakeWordDetector:
    """
    Always-on wake word detector using Vosk (offline, lightweight, no account needed).

    Listens for "jarvis" / "จาวิส" keyword spotting.
    Model is a small ~40MB English model downloaded once.

    Works for:
      - "จาวิส"      (Thai phonetic ≈ "jarvis")
      - "hi jarvis"
      - "hello jarvis"
      - "สวัสดีจาวิส"

    IMPORTANT: Uses AudioHandler's shared microphone stream to avoid
    opening a second stream on the same device (causes conflicts on Pi).
    """

    SAMPLE_RATE = 16000
    CHUNK_SIZE = 1024   # Match AudioHandler.chunk_size

    def __init__(self, state_manager, audio_handler):
        self.state_manager = state_manager
        self.audio_handler = audio_handler
        self.loop = None
        self._thread = None
        self._running = False
        self._rec = None       # Vosk recognizer (set in _run)
        self._model = None     # Vosk model
        self._detected = False  # Guard against double-trigger

    def start(self, loop: asyncio.AbstractEventLoop):
        """Start the wake word detection thread."""
        self.loop = loop
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print("👂 Wake word detector starting (Vosk)...")

    def stop(self):
        self._running = False

    def _download_model(self):
        """Download a small Vosk model if not present."""
        import urllib.request
        import zipfile

        model_dir = os.path.join(os.path.dirname(__file__), "models", "vosk-small-en")
        if os.path.exists(model_dir):
            return model_dir

        os.makedirs(os.path.dirname(model_dir), exist_ok=True)
        url = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
        zip_path = model_dir + ".zip"

        print(f"📥 Downloading Vosk small English model (~40MB)...")
        try:
            urllib.request.urlretrieve(url, zip_path)
            with zipfile.ZipFile(zip_path, "r") as z:
                # Extract to models/ dir — folder inside zip is vosk-model-small-en-us-0.15
                z.extractall(os.path.dirname(model_dir))
            # Rename extracted folder to our expected name
            extracted = os.path.join(os.path.dirname(model_dir), "vosk-model-small-en-us-0.15")
            os.rename(extracted, model_dir)
            os.remove(zip_path)
            print(f"✅ Vosk model ready at {model_dir}")
        except Exception as e:
            print(f"❌ Failed to download Vosk model: {e}")
            # Clean up partial zip if exists
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except OSError:
                    pass
            return None

        return model_dir

    def _on_mic_audio(self, data_bytes: bytes):
        """Called by AudioHandler's mic callback — receives raw mic audio.

        Runs in the sounddevice callback thread (not the asyncio thread).
        Feed audio to Vosk recognizer and check for wake word.
        """
        if not self._running or not self._rec:
            return

        try:
            text = ""
            if self._rec.AcceptWaveform(data_bytes):
                result = json.loads(self._rec.Result())
                text = result.get("text", "").lower().strip()
            else:
                result = json.loads(self._rec.PartialResult())
                text = result.get("partial", "").lower().strip()

            if text and text != "[unk]" and "jarvis" in text:
                # Guard against double-trigger from rapid consecutive detections
                if not self._detected:
                    self._detected = True
                    print(f"🔔 Wake word detected: '{text}' → Activating Jarvis!")
                    asyncio.run_coroutine_threadsafe(
                        self._on_wake_word_detected(), self.loop
                    )
                    # Reset flag after a cooldown to allow re-activation later
                    threading.Timer(2.0, self._reset_detected).start()
        except Exception as e:
            print(f"Wake word processing error: {e}")

    def _reset_detected(self):
        """Reset detection guard after cooldown."""
        self._detected = False
        if self._rec:
            self._rec.Reset()

    def _run(self):
        """Worker thread: initialize Vosk model and register with AudioHandler."""
        try:
            from vosk import Model, KaldiRecognizer
        except ImportError:
            print("❌ vosk not installed. Wake word disabled — use PTT button instead.")
            return

        model_dir = self._download_model()
        if not model_dir:
            return

        try:
            self._model = Model(model_dir)
            # Keyword list — Vosk will only transcribe these words (very efficient)
            keywords = json.dumps(["jarvis", "jarvis jarvis", "[unk]"])
            self._rec = KaldiRecognizer(self._model, self.SAMPLE_RATE, keywords)
            self._rec.SetWords(True)
            print("✅ Vosk wake word ready! Say 'Jarvis' / 'จาวิส' to activate.")
        except Exception as e:
            print(f"❌ Vosk model init failed: {e}")
            return

        # Register as a shared mic consumer on AudioHandler
        # This avoids opening a second microphone stream (critical for Pi)
        self.audio_handler.register_mic_consumer(self._on_mic_audio)
        print("🎙️  Wake word registered as shared mic consumer.")

        # Keep thread alive while running
        try:
            while self._running:
                threading.Event().wait(0.5)
        finally:
            # Cleanup on exit
            self.audio_handler.unregister_mic_consumer(self._on_mic_audio)
            self._rec = None
            self._model = None
            print("👂 Wake word detector stopped.")

    async def _on_wake_word_detected(self):
        """Activate listening session when wake word heard."""
        sm = self.state_manager

        # Don't interrupt active conversation
        if sm.state in ("listening", "thinking", "speaking"):
            print("👂 Already in conversation — ignoring wake word.")
            return

        # Show activation message
        await sm.broadcast_to_frontend({
            "type": "transcript",
            "text": "🔔 ได้ยินครับ กำลังฟัง..."
        })

        # Open mic
        await sm.handle_ptt_press()

        # ── Amplitude VAD loop (same logic as _auto_listen_after_speaking) ──
        SPEECH_THRESHOLD     = 150    # amplitude above = speech (lowered for elderly/soft speech)
        SILENCE_AFTER_SPEECH = 2.0    # seconds silence → patient done (increased for elderly speech pace)
        NO_SPEECH_TIMEOUT    = 8.0    # give up if nobody speaks
        MAX_LISTEN           = 30     # absolute max
        TICK                 = 0.25

        speech_detected = False
        silence_start   = None
        no_speech_start = asyncio.get_running_loop().time()
        elapsed         = 0.0

        while elapsed < MAX_LISTEN:
            await asyncio.sleep(TICK)
            elapsed += TICK

            if sm.state != "listening":
                return  # Gemini responded or state changed externally

            amp = sm.audio_handler.last_amplitude
            now = asyncio.get_running_loop().time()

            if amp > SPEECH_THRESHOLD:
                speech_detected = True
                silence_start   = None
            else:
                if silence_start is None:
                    silence_start = now
                silent_for = now - silence_start

                if speech_detected and silent_for >= SILENCE_AFTER_SPEECH:
                    print(f"🔔 WakeWord VAD: เงียบ {SILENCE_AFTER_SPEECH}s → ส่ง Gemini")
                    break

                if not speech_detected and (now - no_speech_start) >= NO_SPEECH_TIMEOUT:
                    print(f"🔔 WakeWord VAD: ไม่มีเสียง {NO_SPEECH_TIMEOUT}s → ปิดไมค์")
                    sm.audio_handler.muted = True
                    if sm.gemini_client.is_connected:
                        await sm.gemini_client.send_activity_end()
                    await sm.update_state("idle")
                    return

        # Patient finished speaking → ActivityEnd → Gemini responds
        if sm.state == "listening":
            sm.audio_handler.muted = True
            if sm.gemini_client.is_connected:
                await sm.gemini_client.send_activity_end()
            await sm.broadcast_to_frontend({"type": "countdown", "seconds": 0, "total": MAX_LISTEN})
            print("🔔 WakeWord: ActivityEnd → รอ Gemini ตอบ...")
            await sm.update_state("thinking")
            asyncio.create_task(sm._thinking_timeout_checker())

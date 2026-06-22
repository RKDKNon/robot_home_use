import os
import io
import base64
import threading
import time
from dotenv import load_dotenv

load_dotenv()

class CameraHandler:
    """Continuous webcam capture for patient monitoring.

    Camera stays ON all the time. Frames are captured periodically
    and can be requested on-demand.
    """

    def __init__(self):
        self.device = int(os.getenv("CAMERA_DEVICE", "0"))
        self.width = 640
        self.height = 480
        self._lock = threading.Lock()
        self._cam = None
        self._running = False
        self._latest_frame = None  # Latest captured JPEG bytes
        self._thread = None

    def start(self):
        """Start continuous camera capture in background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        print("📷 Camera started (continuous mode)")

    def stop(self):
        """Stop camera capture."""
        self._running = False
        if self._cam:
            try:
                self._cam.stop()
            except Exception:
                pass
            self._cam = None
        self._latest_frame = None
        print("📷 Camera stopped")

    def _init_camera(self):
        """Initialize pygame camera."""
        try:
            import pygame
            import pygame.camera
            pygame.camera.init()
            cameras = pygame.camera.list_cameras()
            cam_path = cameras[self.device] if len(cameras) > self.device else "/dev/video0"
            self._cam = pygame.camera.Camera(cam_path, (self.width, self.height))
            self._cam.start()
            print(f"📷 Camera opened: {cam_path} ({self.width}x{self.height})")
            return True
        except Exception as e:
            print(f"❌ Camera init error: {e}")
            self._cam = None
            return False

    def _capture_loop(self):
        """Background thread: continuously capture frames."""
        import pygame

        if not self._init_camera():
            self._running = False
            return

        while self._running:
            try:
                if self._cam:
                    image = self._cam.get_image()
                    buffer = io.BytesIO()
                    pygame.image.save(image, buffer, "jpg")
                    self._latest_frame = buffer.getvalue()
                time.sleep(0.5)  # Capture at ~2 FPS (enough for monitoring)
            except Exception as e:
                print(f"📷 Camera capture error: {e}")
                # Try to reinitialize camera
                time.sleep(2)
                self._init_camera()

    def get_latest_frame(self) -> bytes:
        """Get the most recently captured frame (JPEG bytes)."""
        return self._latest_frame or b""

    def capture_frame(self) -> bytes:
        """Get latest frame, or capture one if camera not running."""
        if self._latest_frame:
            return self._latest_frame
        # Fallback: capture on-demand
        with self._lock:
            try:
                import pygame
                import pygame.camera
                pygame.camera.init()
                cam = pygame.camera.Camera(
                    pygame.camera.list_cameras()[self.device]
                    if len(pygame.camera.list_cameras()) > self.device
                    else "/dev/video0",
                    (self.width, self.height)
                )
                cam.start()
                image = cam.get_image()
                cam.stop()
                pygame.camera.quit()
                buffer = io.BytesIO()
                pygame.image.save(image, buffer, "jpg")
                return buffer.getvalue()
            except Exception as e:
                print(f"❌ Camera capture error: {e}")
                return b""

    def capture_as_base64_with_mime(self) -> dict:
        """Get latest frame in Gemini-compatible format."""
        jpeg = self.get_latest_frame()
        if jpeg:
            return {
                "data": base64.b64encode(jpeg).decode("utf-8"),
                "mime_type": "image/jpeg"
            }
        return {}

    @property
    def is_active(self) -> bool:
        return self._running and self._latest_frame is not None


if __name__ == "__main__":
    print("Testing continuous camera capture...")
    handler = CameraHandler()
    handler.start()
    time.sleep(3)
    frame = handler.get_latest_frame()
    if frame:
        print(f"✅ Got frame: {len(frame)} bytes")
        with open("test_capture.jpg", "wb") as f:
            f.write(frame)
        print("Saved to test_capture.jpg")
    else:
        print("❌ No frame captured")
    handler.stop()

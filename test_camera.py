import pygame
import pygame.camera
import sys
import os

print("📷 Testing Camera using Pygame Camera module...")
pygame.init()
pygame.camera.init()

cameras = pygame.camera.list_cameras()
print("Detected cameras list:", cameras)

if not cameras:
    print("❌ No cameras detected by pygame. Checking /dev/video0 directly...")
    if os.path.exists("/dev/video0"):
        cameras = ["/dev/video0"]
        print("Using fallback device: /dev/video0")
    else:
        print("❌ No camera devices found.")
        sys.exit(1)

try:
    # Use the first camera device
    cam_device = cameras[0]
    print(f"Opening camera: {cam_device}")
    
    # Initialize camera at 640x480 resolution
    cam = pygame.camera.Camera(cam_device, (640, 480))
    cam.start()
    
    print("Capturing frame...")
    # Capture an image
    img = cam.get_image()
    
    # Save the image
    output_filename = "test_camera_capture.jpg"
    pygame.image.save(img, output_filename)
    print(f"🟢 Success! Captured frame saved to: {os.path.abspath(output_filename)}")
    
    # Stop camera
    cam.stop()
except Exception as e:
    print(f"❌ Error using camera: {e}")
    sys.exit(1)

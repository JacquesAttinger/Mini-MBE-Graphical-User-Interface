#!/usr/bin/env python3
"""
Standalone VmbPy camera test.

Runs the first attached camera, streams frames, and displays them in an OpenCV window.
Press Ctrl+C or 'q' to quit.
"""

import sys
import time

# Try OpenCV for display; fall back to console shapes if missing
try:
    import cv2
except ImportError:
    cv2 = None

from vmbpy import VmbSystem, FrameStatus, PixelFormat


def frame_handler(camera, stream, frame):
    # Only process complete frames
    if frame.get_status() == FrameStatus.Complete:
        # Ensure BGR8 for display
        try:
            if frame.get_pixel_format() != PixelFormat.Bgr8:
                frame.convert_pixel_format(PixelFormat.Bgr8)
        except Exception:
            pass

        img = frame.as_numpy_ndarray()

        if cv2:
            cv2.imshow("VmbPy Stream", img)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                raise KeyboardInterrupt
        else:
            print(f"Got frame: shape={img.shape}")

    # re-queue for continuous streaming
    camera.queue_frame(frame)


def main():
    # Grab the singleton VmbSystem
    with VmbSystem.get_instance() as system:
        cams = system.get_all_cameras()
        if not cams:
            print("❌ No cameras found.")
            sys.exit(1)

        cam = cams[0]
        print(f"✅ Opening camera {cam.get_id()}")

        # use the private API names
        cam._open()
        print("▶️  Starting stream...")
        cam.start_streaming(handler=frame_handler, buffer_count=5)

        try:
            # keep main thread alive to receive callbacks
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n⏹  Stopping stream...")

        # stop & close using the private API
        cam.stop_streaming()
        cam._close()

        if cv2:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

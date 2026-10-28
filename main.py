
import time
import cv2

from config.settings import STREAM_URL
from src.streaming import VideoStream
from src.detector import VehicleDetector
from src.analytics import TrafficAnalytics


def main():
    stream = VideoStream(STREAM_URL)
    detector = VehicleDetector(
        model_path="models/yolov8n.pt",
        confidence=0.25,
        image_size=640,
    )
    analytics = TrafficAnalytics()

    last_log_time = 0.0

    try:
        while True:
            ret, frame = stream.read_frame()

            if not ret or frame is None:
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue

            # 1. Deteksi dan tracking kendaraan.
            annotated_frame, vehicles = detector.detect(frame)

            # 2. Analisis antrean pada ROI.
            annotated_frame, metrics = analytics.update(
                annotated_frame,
                vehicles,
            )

            # 3. Cetak ringkasan satu kali per detik.
            now = time.monotonic()

            if now - last_log_time >= 1.0:
                print(
                    f"Queue={metrics['queue_count']} | "
                    f"Stopped={metrics['stopped_count']} | "
                    f"AvgWait="
                    f"{metrics['average_stopped_seconds']:.1f}s | "
                    f"Status={metrics['status']}"
                )
                last_log_time = now

            cv2.imshow(
                "Traffic Monitoring - YOLOv8",
                annotated_frame,
            )

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except KeyboardInterrupt:
        print("\nProgram dihentikan pengguna.")

    finally:
        stream.release()
        cv2.destroyAllWindows()
        print("Traffic monitoring dihentikan.")


if __name__ == "__main__":
    main()

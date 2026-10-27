
import cv2
import time

from config.settings import STREAM_URL
from src.streaming import VideoStream
from src.detector import VehicleDetector


def main():
    stream = VideoStream(STREAM_URL)
    detector = VehicleDetector(
        model_path="models/yolov8n.pt",
        confidence=0.35,
        image_size=640,
    )
    window_name = "CCTV Stream Diagnostics"

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 960, 540)

    previous_time = time.monotonic()
    fps = 0.0
    frames = 0
    last_report = previous_time

    try:
        while True:
            start_read = time.monotonic()
            ret, frame = stream.read_frame()
            
            read_ms = (time.monotonic() - start_read) * 1000

            now = time.monotonic()
            frames += 1

            # FPS loop aplikasi, bukan FPS asli sumber CCTV.
            elapsed = now - previous_time
            if elapsed >= 1.0:
                fps = frames / elapsed
                frames = 0
                previous_time = now

            if ret and frame is not None:

                annotated_frame, counts = detector.detect(frame)

                # 1. Ambil lebar frame (lebar ada di indeks ke-1 dari frame.shape)
                lebar_frame = frame.shape[1]

                # 2. Atur ukuran font baru yang lebih besar
                font_scale = 1.0  # Diperbesar dari 0.7 ke 1.0
                thickness = 2  # Ketebalan garis font

                # 3. Siapkan string teks yang akan ditampilkan
                teks_fps = f"Loop FPS: {fps:.1f}"
                teks_ms = f"read_frame: {read_ms:.2f} ms"

                # 4. Hitung ukuran piksel teks untuk menentukan posisi X agar pas di kanan
                (w_fps, h_fps), _ = cv2.getTextSize(
                    teks_fps, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
                )
                (w_ms, h_ms), _ = cv2.getTextSize(
                    teks_ms, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
                )

                # 5. Tentukan koordinat dengan margin 20 piksel dari tepi kanan dan atas
                margin = 20

                # Baris 1 (Loop FPS)
                x_fps = lebar_frame - w_fps - margin
                y_fps = h_fps + margin

                # Baris 2 (read_frame) ditempatkan di bawah baris 1 ditambah jarak antar baris (15px)
                x_ms = lebar_frame - w_ms - margin
                y_ms = y_fps + h_ms + 15

                # 6. Tampilkan kedua teks pada frame
                cv2.putText(
                    frame,
                    teks_fps,
                    (x_fps, y_fps),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale,
                    (0, 255, 255),
                    thickness,
                )
                cv2.putText(
                    frame,
                    teks_ms,
                    (x_ms, y_ms),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale,
                    (0, 255, 255),
                    thickness,
                )
                cv2.putText(
                    annotated_frame,
                    f"Mobil: {counts['car']} | Motor: {counts['motorcycle']} | Bus: {counts['bus']} | Truck: {counts['truck']} | Orang: {counts['person']}",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2,
                )
                cv2.imshow(window_name, annotated_frame)

            if now - last_report >= 2.0:
                metrics = stream.get_metrics()

                interval = metrics["frame_interval_ms"]
                age = metrics["frame_age_ms"]

                interval_text = (
                    f"{interval:.1f} ms"
                    if interval is not None
                    else "N/A"
                )

                age_text = (
                    f"{age:.1f} ms"
                    if age is not None
                    else "N/A"
                )

                print(
                    f"Received={metrics['frames_received']} | "
                    f"Interval={interval:.1f} ms | "
                    f"Age={age:.1f} ms"
                    if interval is not None
                    else f"Received={metrics['frames_received']} | Interval=N/A"
                )

                last_report = now

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    finally:
        stream.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

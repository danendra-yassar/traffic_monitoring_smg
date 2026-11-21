# src/analytics.py

import math
import threading
import time

import cv2
import numpy as np

from config.settings import (
    STREAM_OUTPUT_HEIGHT,
    STREAM_OUTPUT_WIDTH,
    VEHICLE_WEIGHTS,
)

DEFAULT_NORMALIZED_ROI = [
    [0.3281, 0.2500],  # setara (420, 180) pada 1280x720
    [0.5625, 0.2500],  # setara (720, 180)
    [0.9922, 0.9861],  # setara (1270, 710)
    [0.5078, 0.9861],  # setara (650, 710)
]


class TrafficAnalytics:
    def __init__(
        self,
        roi_points=None,
        movement_threshold=6.0,
        stopped_after_seconds=2.0,
        high_queue_threshold=8,
        high_stopped_threshold=5,
        long_wait_seconds=5.0,
        frame_width=STREAM_OUTPUT_WIDTH,
        frame_height=STREAM_OUTPUT_HEIGHT,
        default_empty=False,
    ):
        self.frame_width = int(frame_width)
        self.frame_height = int(frame_height)
        self.default_empty = bool(default_empty)
        self._lock = threading.Lock()

        if roi_points is not None and len(roi_points) >= 3:
            self.roi = np.array(roi_points, dtype=np.int32)
            self._normalized_roi = [
                [
                    round(float(x) / self.frame_width, 4),
                    round(float(y) / self.frame_height, 4),
                ]
                for x, y in roi_points
            ]
        elif self.default_empty:
            # Mulai tanpa ROI statis agar video stream awal tampil bersih.
            self.roi = None
            self._normalized_roi = []
        else:
            # Fallback default untuk mode CLI (main.py).
            self._normalized_roi = [list(pt) for pt in DEFAULT_NORMALIZED_ROI]
            self.roi = self._denormalize_points(self._normalized_roi)

        self.movement_threshold = movement_threshold
        self.stopped_after_seconds = stopped_after_seconds
        self.high_queue_threshold = high_queue_threshold
        self.high_stopped_threshold = high_stopped_threshold
        self.long_wait_seconds = long_wait_seconds

        # Riwayat pergerakan setiap track ID.
        self.tracks = {}

    def _denormalize_points(self, normalized_points):
        """Mengubah koordinat relatif [0.0..1.0] menjadi piksel frame."""
        pixel_points = []
        max_x = max(0, self.frame_width - 1)
        max_y = max(0, self.frame_height - 1)

        for x_norm, y_norm in normalized_points:
            px = min(max_x, max(0, int(round(x_norm * self.frame_width))))
            py = min(max_y, max(0, int(round(y_norm * self.frame_height))))
            pixel_points.append((px, py))

        return np.array(pixel_points, dtype=np.int32)

    @staticmethod
    def _polygon_area(points):
        """Menghitung luas polygon menggunakan Shoelace formula."""
        n = len(points)
        area = 0.0
        for i in range(n):
            x1, y1 = points[i]
            x2, y2 = points[(i + 1) % n]
            area += (x1 * y2) - (x2 * y1)
        return abs(area) * 0.5

    def set_roi_normalized(self, normalized_points):
        """
        Memperbarui polygon ROI secara aman (thread-safe) dari koordinat
        ternormalisasi [0.0..1.0] yang dikirim oleh kanvas web.
        """
        if not isinstance(normalized_points, (list, tuple)):
            raise ValueError("Format points ROI harus berupa list.")

        if len(normalized_points) < 3:
            raise ValueError("Polygon ROI minimal memiliki 3 titik sudut.")

        if len(normalized_points) > 20:
            raise ValueError("Polygon ROI maksimal memiliki 20 titik sudut.")

        cleaned_points = []
        for point in normalized_points:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise ValueError("Setiap titik ROI harus berisi pasangan [x, y].")

            try:
                x_val = float(point[0])
                y_val = float(point[1])
            except (TypeError, ValueError) as exc:
                raise ValueError("Koordinat titik ROI harus berupa angka.") from exc

            if not (math.isfinite(x_val) and math.isfinite(y_val)):
                raise ValueError("Koordinat titik ROI tidak valid.")

            if not (0.0 <= x_val <= 1.0 and 0.0 <= y_val <= 1.0):
                raise ValueError(
                    "Koordinat ROI ternormalisasi harus berada di rentang 0.0 hingga 1.0."
                )

            cleaned_points.append([round(x_val, 4), round(y_val, 4)])

        if self._polygon_area(cleaned_points) < 1e-4:
            raise ValueError(
                "Area polygon ROI terlalu kecil atau titik-titiknya segaris."
            )

        new_roi_array = self._denormalize_points(cleaned_points)

        with self._lock:
            self._normalized_roi = cleaned_points
            self.roi = new_roi_array

    def reset_roi(self):
        """
        Menghapus ROI kustom agar kamera kembali bersih (jika default_empty=True)
        atau kembali ke koordinat default pada mode CLI.
        """
        if self.default_empty:
            with self._lock:
                self._normalized_roi = []
                self.roi = None
        else:
            self.set_roi_normalized(DEFAULT_NORMALIZED_ROI)

    def get_roi_normalized(self):
        """Mengembalikan salinan titik ROI ternormalisasi saat ini."""
        with self._lock:
            return [list(pt) for pt in self._normalized_roi]

    @staticmethod
    def _inside_roi(roi_polygon, point):
        x, y = point
        return (
            cv2.pointPolygonTest(
                roi_polygon,
                (float(x), float(y)),
                False,
            )
            >= 0
        )

    @staticmethod
    def _draw_hud_box(frame, lines, status_color):
        """Menggambar kotak latar semi-gelap agar teks terbaca jelas di atas watermark CCTV."""
        overlay = frame.copy()
        cv2.rectangle(overlay, (14, 14), (470, 114), (15, 23, 42), -1)
        cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

        y_positions = [40, 70, 100]
        colors = [(248, 250, 252), (226, 232, 240), status_color]

        for text, y_pos, color in zip(lines, y_positions, colors):
            cv2.putText(
                frame,
                text,
                (24, y_pos),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                color,
                2,
                cv2.LINE_AA,
            )

    def update(self, frame, vehicles):
        now = time.monotonic()

        with self._lock:
            roi_snapshot = self.roi.copy() if self.roi is not None else None

        class_counts = {
            "car": 0,
            "motorcycle": 0,
            "bus": 0,
            "truck": 0,
        }

        # Jika ROI belum dibuat, biarkan frame video bersih tanpa poligon ROI.
        if roi_snapshot is None or len(roi_snapshot) < 3:
            self.tracks.clear()
            metrics = {
                "has_roi": False,
                "queue_count": 0,
                "stopped_count": 0,
                "average_stopped_seconds": 0.0,
                "weighted_score": 0,
                "class_counts": class_counts,
                "status": "ROI BELUM DIATUR",
            }
            return frame, metrics

        queue_vehicles = []
        stopped_vehicles = []

        for vehicle in vehicles:
            track_id = vehicle["track_id"]
            x, y = vehicle["anchor"]

            state = self.tracks.get(track_id)

            if state is None:
                state = {
                    "last_position": (x, y),
                    "last_motion_time": now,
                    "last_seen": now,
                }
                self.tracks[track_id] = state
            else:
                old_x, old_y = state["last_position"]
                distance = ((x - old_x) ** 2 + (y - old_y) ** 2) ** 0.5

                # Gerakan kecil akibat jitter bounding box
                # tidak langsung dianggap kendaraan bergerak.
                if distance >= self.movement_threshold:
                    state["last_motion_time"] = now

                state["last_position"] = (x, y)
                state["last_seen"] = now

            stopped_duration = now - state["last_motion_time"]
            vehicle["stopped_seconds"] = stopped_duration
            vehicle["is_stopped"] = (
                stopped_duration >= self.stopped_after_seconds
            )

            if self._inside_roi(roi_snapshot, (x, y)):
                queue_vehicles.append(vehicle)
                cls_name = vehicle.get("class_name", "")
                if cls_name in class_counts:
                    class_counts[cls_name] += 1
                else:
                    class_counts[cls_name] = 1

                if vehicle["is_stopped"]:
                    stopped_vehicles.append(vehicle)

        # Hapus riwayat track yang sudah lama tidak terlihat.
        stale_ids = [
            track_id
            for track_id, state in self.tracks.items()
            if now - state["last_seen"] > 3.0
        ]
        for track_id in stale_ids:
            del self.tracks[track_id]

        queue_count = len(queue_vehicles)
        stopped_count = len(stopped_vehicles)

        if stopped_vehicles:
            average_wait = (
                sum(v["stopped_seconds"] for v in stopped_vehicles)
                / stopped_count
            )
        else:
            average_wait = 0.0

        weighted_score = sum(
            count * VEHICLE_WEIGHTS.get(cls_name, 1)
            for cls_name, count in class_counts.items()
        )

        high_queue = (
            queue_count >= self.high_queue_threshold
            and stopped_count >= self.high_stopped_threshold
            and average_wait >= self.long_wait_seconds
        )

        if high_queue:
            status = "INDIKASI ANTREAN TINGGI"
        elif queue_count > 0:
            status = "BERJALAN - KENDARAAN DI ZONA ANTREAN"
        else:
            status = "ZONA KOSONG"

        # Gambar polygon ROI pada frame hasil deteksi.
        cv2.polylines(
            frame,
            [roi_snapshot],
            isClosed=True,
            color=(0, 255, 255),
            thickness=2,
        )

        status_color = (80, 80, 255) if high_queue else (80, 255, 120)
        self._draw_hud_box(
            frame,
            [
                f"Queue: {queue_count} | Stopped: {stopped_count}",
                f"Avg stopped: {average_wait:.1f}s | Score: {weighted_score}",
                status,
            ],
            status_color,
        )

        metrics = {
            "has_roi": True,
            "queue_count": queue_count,
            "stopped_count": stopped_count,
            "average_stopped_seconds": round(average_wait, 1),
            "weighted_score": weighted_score,
            "class_counts": class_counts,
            "status": status,
        }

        return frame, metrics

import time
import cv2
import numpy as np


class TrafficAnalytics:
    def __init__(
        self,
        roi_points=None,
        movement_threshold=6.0,
        stopped_after_seconds=2.0,
        high_queue_threshold=8,
        high_stopped_threshold=5,
        long_wait_seconds=5.0,
    ):
        # Koordinat awal untuk frame 1280x720.
        # Sesuaikan dengan lajur antrean pada CCTV yang digunakan.
        if roi_points is None:
            roi_points = [
                (420, 180),
                (720, 180),
                (1270, 710),
                (650, 710),
            ]

        self.roi = np.array(roi_points, dtype=np.int32)

        self.movement_threshold = movement_threshold
        self.stopped_after_seconds = stopped_after_seconds
        self.high_queue_threshold = high_queue_threshold
        self.high_stopped_threshold = high_stopped_threshold
        self.long_wait_seconds = long_wait_seconds

        # Riwayat pergerakan setiap track ID.
        self.tracks = {}

    def _inside_roi(self, point):
        x, y = point

        return cv2.pointPolygonTest(
            self.roi,
            (float(x), float(y)),
            False,
        ) >= 0

    def update(self, frame, vehicles):
        now = time.monotonic()

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

                distance = (
                    (x - old_x) ** 2 + (y - old_y) ** 2
                ) ** 0.5

                # Gerakan kecil akibat jitter bounding box
                # tidak langsung dianggap kendaraan bergerak.
                if distance >= self.movement_threshold:
                    state["last_motion_time"] = now

                state["last_position"] = (x, y)
                state["last_seen"] = now

            stopped_duration = (
                now - state["last_motion_time"]
            )

            vehicle["stopped_seconds"] = stopped_duration
            vehicle["is_stopped"] = (
                stopped_duration >= self.stopped_after_seconds
            )

            if self._inside_roi((x, y)):
                queue_vehicles.append(vehicle)

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
            average_wait = sum(
                vehicle["stopped_seconds"]
                for vehicle in stopped_vehicles
            ) / stopped_count
        else:
            average_wait = 0.0

        # Aturan awal untuk memberi indikasi antrean tinggi.
        # Nilai ambang perlu dikalibrasi menggunakan video nyata.
        high_queue = (
            queue_count >= self.high_queue_threshold
            and stopped_count >= self.high_stopped_threshold
            and average_wait >= self.long_wait_seconds
        )

        if high_queue:
            status = "INDIKASI ANTREAN TINGGI"
        elif queue_count > 0:
            status = "KENDARAAN DI ZONA ANTREAN"
        else:
            status = "ZONA KOSONG"

        # Gambar ROI pada frame hasil deteksi.
        cv2.polylines(
            frame,
            [self.roi],
            isClosed=True,
            color=(0, 255, 255),
            thickness=2,
        )

        cv2.putText(
            frame,
            f"Queue: {queue_count} | Stopped: {stopped_count}",
            (20, 80),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2,
        )

        cv2.putText(
            frame,
            f"Avg stopped: {average_wait:.1f}s",
            (20, 110),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2,
        )

        cv2.putText(
            frame,
            status,
            (20, 140),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255) if high_queue else (0, 255, 0),
            2,
        )

        metrics = {
            "queue_count": queue_count,
            "stopped_count": stopped_count,
            "average_stopped_seconds": average_wait,
            "status": status,
        }

        return frame, metrics

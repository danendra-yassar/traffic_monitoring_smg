# src/camera_manager.py

import atexit
from collections import deque
import re
import threading
import time
import uuid

import cv2
import numpy as np

from config.settings import (
    DETECTION_CONFIDENCE,
    DETECTION_IMAGE_SIZE,
    JPEG_QUALITY,
    MAX_ACTIVE_CAMERAS,
    MODEL_PATH,
    STREAM_OUTPUT_HEIGHT,
    STREAM_OUTPUT_WIDTH,
)
from src.analytics import TrafficAnalytics
from src.cctv_resolver import CCTVResolverError, get_cctv_url
from src.detector import VehicleDetector
from src.streaming import VideoStream


class CameraManagerError(Exception):
    """Error pada operasi penambahan, pengaturan, atau penghapusan kamera."""


def _make_cam_id(owner_name):
    """Membuat ID kamera yang aman untuk URL endpoint."""
    slug = re.sub(r"[^a-z0-9]+", "-", owner_name.strip().lower()).strip("-")
    slug = slug[:32] or "cctv"
    short_token = uuid.uuid4().hex[:6]
    return f"{slug}-{short_token}"


def _build_placeholder_jpeg(title, subtitle="Menghubungkan ke stream CCTV..."):
    """Membuat frame JPEG placeholder 1280x720 saat stream belum siap."""
    canvas = np.zeros(
        (STREAM_OUTPUT_HEIGHT, STREAM_OUTPUT_WIDTH, 3),
        dtype=np.uint8,
    )
    canvas[:] = (30, 34, 42)

    cv2.putText(
        canvas,
        title,
        (60, STREAM_OUTPUT_HEIGHT // 2 - 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.1,
        (240, 244, 248),
        2,
    )
    cv2.putText(
        canvas,
        subtitle,
        (60, STREAM_OUTPUT_HEIGHT // 2 + 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (160, 174, 192),
        2,
    )

    ok, encoded = cv2.imencode(
        ".jpg",
        canvas,
        [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY],
    )
    return encoded.tobytes() if ok else b""


class CameraWorker:
    """Menjalankan pipeline VideoStream -> YOLOv8 -> TrafficAnalytics untuk 1 CCTV."""

    def __init__(self, cam_id, owner_name, stream_url):
        self.cam_id = cam_id
        self.owner_name = owner_name
        self.stream_url = stream_url
        self.created_at = time.time()

        self._lock = threading.Lock()
        self._frame_event = threading.Event()
        self._stop_event = threading.Event()

        self._latest_jpeg = _build_placeholder_jpeg(owner_name)
        self._jpeg_seq = 0
        self._latest_metrics = {
            "has_roi": False,
            "queue_count": 0,
            "stopped_count": 0,
            "average_stopped_seconds": 0.0,
            "weighted_score": 0,
            "class_counts": {
                "car": 0,
                "motorcycle": 0,
                "bus": 0,
                "truck": 0,
            },
            "status": "ROI BELUM DIATUR",
        }

        # Riwayat tren 15 menit terakhir (interval sampling 10 detik -> 90 titik)
        self._history = deque(maxlen=90)
        self._last_history_sample = 0.0

        self.stream = None
        try:
            self.stream = VideoStream(
                source=stream_url,
                output_width=STREAM_OUTPUT_WIDTH,
                output_height=STREAM_OUTPUT_HEIGHT,
            )
            self.detector = VehicleDetector(
                model_path=MODEL_PATH,
                confidence=DETECTION_CONFIDENCE,
                image_size=DETECTION_IMAGE_SIZE,
            )
            # default_empty=True agar kamera baru tampil bersih tanpa ROI statis.
            self.analytics = TrafficAnalytics(
                frame_width=STREAM_OUTPUT_WIDTH,
                frame_height=STREAM_OUTPUT_HEIGHT,
                default_empty=True,
            )
        except Exception:
            if self.stream is not None:
                self.stream.release()
            raise

        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name=f"CameraWorker-{self.cam_id}",
        )
        self._thread.start()

    def _run_loop(self):
        last_processed_frame_num = 0

        while not self._stop_event.is_set():
            stream_info = self.stream.get_metrics()
            current_frame_num = stream_info["frames_received"]

            # Hindari menjalankan inferensi YOLO ulang pada frame yang sama.
            if current_frame_num == 0 or current_frame_num == last_processed_frame_num:
                self._stop_event.wait(0.01)
                continue

            ret, frame = self.stream.read_frame()
            if not ret or frame is None:
                self._stop_event.wait(0.01)
                continue

            last_processed_frame_num = current_frame_num

            try:
                annotated_frame, vehicles = self.detector.detect(frame)
                annotated_frame, metrics = self.analytics.update(
                    annotated_frame,
                    vehicles,
                )

                ok, encoded = cv2.imencode(
                    ".jpg",
                    annotated_frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY],
                )

                if ok:
                    now_mono = time.monotonic()
                    with self._lock:
                        self._latest_jpeg = encoded.tobytes()
                        self._jpeg_seq += 1
                        self._latest_metrics = metrics

                        if (
                            metrics.get("has_roi")
                            and now_mono - self._last_history_sample >= 10.0
                        ):
                            self._history.append({
                                "ts": int(time.time()),
                                "queue_count": metrics["queue_count"],
                                "stopped_count": metrics["stopped_count"],
                                "weighted_score": metrics["weighted_score"],
                            })
                            self._last_history_sample = now_mono

                    self._frame_event.set()
                    self._frame_event.clear()

            except Exception as exc:
                print(f"[WORKER ERROR] ({self.owner_name}): {exc}")
                self._stop_event.wait(0.1)

    def get_jpeg_frame(self):
        """Mengembalikan tuple (nomor_urut_frame, bytes_jpeg)."""
        with self._lock:
            return self._jpeg_seq, self._latest_jpeg

    def wait_for_frame(self, last_seq, timeout=1.0):
        """Menunggu hingga tersedia frame JPEG lebih baru dari last_seq."""
        with self._lock:
            if self._jpeg_seq != last_seq:
                return self._jpeg_seq, self._latest_jpeg

        self._frame_event.wait(timeout=timeout)
        with self._lock:
            return self._jpeg_seq, self._latest_jpeg

    def get_roi_normalized(self):
        """Mengembalikan koordinat polygon ROI ternormalisasi milik kamera ini."""
        return self.analytics.get_roi_normalized()

    def update_roi(self, normalized_points):
        """Memperbarui polygon ROI untuk kamera ini dan mengembalikan nilai terbarunya."""
        self.analytics.set_roi_normalized(normalized_points)
        return self.analytics.get_roi_normalized()

    def reset_roi(self):
        """Menghapus/mereset polygon ROI kamera ini ke kondisi bersih."""
        self.analytics.reset_roi()
        return self.analytics.get_roi_normalized()

    def get_state(self):
        """Mengembalikan snapshot status dan metrik terbaru kamera."""
        stream_metrics = self.stream.get_metrics()
        with self._lock:
            metrics_copy = dict(self._latest_metrics)
            metrics_copy["class_counts"] = dict(
                self._latest_metrics.get("class_counts", {})
            )
            history_copy = list(self._history)

        return {
            "cam_id": self.cam_id,
            "owner_name": self.owner_name,
            "stream_status": stream_metrics["status"],
            "frames_received": stream_metrics["frames_received"],
            "metrics": metrics_copy,
            "roi_normalized": self.analytics.get_roi_normalized(),
            "history": history_copy,
        }

    def stop(self):
        """Menghentikan worker thread dan proses FFmpeg dengan bersih."""
        self._stop_event.set()
        self._frame_event.set()

        if self._thread.is_alive():
            self._thread.join(timeout=4.0)

        if self.stream is not None:
            self.stream.release()


class CameraManager:
    """Mengelola seluruh CameraWorker aktif dan menegakkan batas kapasitas."""

    def __init__(self, max_cameras=MAX_ACTIVE_CAMERAS):
        self.max_cameras = int(max_cameras)
        self._lock = threading.Lock()
        self._cameras = {}  # cam_id -> CameraWorker
        self._pending_names = set()  # owner_name.casefold() yang sedang proses start

        atexit.register(self.shutdown_all)

    def add_camera(self, owner_name):
        """
        Memvalidasi nama CCTV terhadap PANTAUSEMAR, memeriksa batas kapasitas,
        dan menyalakan CameraWorker baru.
        """
        if not isinstance(owner_name, str) or not owner_name.strip():
            raise CameraManagerError("Nama CCTV harus diisi.")

        clean_name = owner_name.strip()
        name_key = clean_name.casefold()

        with self._lock:
            for existing in self._cameras.values():
                if existing.owner_name.casefold() == name_key:
                    raise CameraManagerError(
                        f"CCTV '{existing.owner_name}' sudah aktif dipantau."
                    )

            if name_key in self._pending_names:
                raise CameraManagerError(
                    f"CCTV '{clean_name}' sedang dalam proses dihubungkan."
                )

            total_reserved = len(self._cameras) + len(self._pending_names)
            if total_reserved >= self.max_cameras:
                raise CameraManagerError(
                    f"Batas maksimal tercapai ({self.max_cameras} kamera aktif). "
                    "Hentikan salah satu kamera terlebih dahulu."
                )

            self._pending_names.add(name_key)

        try:
            # Validasi ke daftar resmi PANTAUSEMAR (mencegah SSRF).
            stream_url = get_cctv_url(clean_name)
            cam_id = _make_cam_id(clean_name)
            worker = CameraWorker(
                cam_id=cam_id,
                owner_name=clean_name,
                stream_url=stream_url,
            )

            with self._lock:
                self._cameras[cam_id] = worker

            print(f"[MANAGER] Kamera aktif ditambahkan: {clean_name} ({cam_id})")
            return worker.get_state()

        except CCTVResolverError as exc:
            raise CameraManagerError(str(exc)) from exc
        except Exception as exc:
            raise CameraManagerError(
                f"Gagal memulai worker kamera '{clean_name}': {exc}"
            ) from exc
        finally:
            with self._lock:
                self._pending_names.discard(name_key)

    def remove_camera(self, cam_id):
        """Menghentikan dan menghapus kamera aktif berdasarkan cam_id."""
        with self._lock:
            worker = self._cameras.pop(cam_id, None)

        if worker is None:
            raise CameraManagerError(f"Kamera '{cam_id}' tidak ditemukan.")

        worker.stop()
        print(f"[MANAGER] Kamera dihentikan: {worker.owner_name} ({cam_id})")

    def get_camera(self, cam_id):
        """Mengambil instance CameraWorker berdasarkan cam_id."""
        with self._lock:
            return self._cameras.get(cam_id)

    def update_camera_roi(self, cam_id, normalized_points):
        """Memperbarui koordinat ROI ternormalisasi untuk kamera tertentu."""
        worker = self.get_camera(cam_id)
        if worker is None:
            raise CameraManagerError(f"Kamera '{cam_id}' tidak ditemukan.")

        return worker.update_roi(normalized_points)

    def reset_camera_roi(self, cam_id):
        """Menghapus/mereset ROI kamera tertentu ke kondisi bersih."""
        worker = self.get_camera(cam_id)
        if worker is None:
            raise CameraManagerError(f"Kamera '{cam_id}' tidak ditemukan.")

        return worker.reset_roi()

    def list_cameras(self):
        """Mengembalikan daftar status seluruh kamera yang sedang aktif."""
        with self._lock:
            workers = list(self._cameras.values())

        return {
            "active_count": len(workers),
            "max_cameras": self.max_cameras,
            "cameras": [w.get_state() for w in workers],
        }

    def shutdown_all(self):
        """Menghentikan seluruh worker aktif saat aplikasi server berhenti."""
        with self._lock:
            workers = list(self._cameras.values())
            self._cameras.clear()

        for worker in workers:
            try:
                worker.stop()
            except Exception as exc:
                print(f"[MANAGER] Gagal menghentikan {worker.cam_id}: {exc}")

# src/streaming.py

import subprocess
import threading
import time

import numpy as np

from config.settings import (
    RECONNECT_DELAY_SECONDS,
    MAX_READ_FAILURES,
)


class VideoStream:
    def __init__(
        self,
        source,
        reconnect_delay=RECONNECT_DELAY_SECONDS,
        max_read_failures=MAX_READ_FAILURES,
        output_width=1280,
        output_height=720,
        ffmpeg_path="ffmpeg",
    ):
        self.source = source
        self.reconnect_delay = reconnect_delay
        self.max_read_failures = max_read_failures
        self.output_width = output_width
        self.output_height = output_height
        self.ffmpeg_path = ffmpeg_path

        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        self._frame = None
        self._status = "Menghubungkan ke CCTV..."

        self.frames_received = 0
        self.last_frame_received = None
        self.frame_interval_ms = None

        self._process = None

        self._thread = threading.Thread(
            target=self._update,
            daemon=True,
            name="FFmpegStreamReader",
        )
        self._thread.start()

    def _set_status(self, message):
        with self._lock:
            self._status = message

    def get_status(self):
        with self._lock:
            return self._status

    def _start_ffmpeg(self):
        """Menjalankan FFmpeg dan mengirim frame BGR ke stdout."""

        command = [
            self.ffmpeg_path,
            "-hide_banner",
            "-loglevel", "error",
            "-nostdin",

            # Batas waktu untuk operasi jaringan, dalam mikrodetik.
            "-rw_timeout", "5000000",

            # Coba pulihkan koneksi HTTP jika terjadi gangguan.
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "2",

            "-i", self.source,
            "-map", "0:v:0",
            "-an",
            "-sn",
            "-dn",

            # Resolusi output tetap agar ukuran setiap frame diketahui.
            "-vf",
            f"scale={self.output_width}:{self.output_height}:flags=fast_bilinear",

            # BGR 24-bit kompatibel dengan OpenCV.
            "-pix_fmt", "bgr24",
            "-f", "rawvideo",
            "pipe:1",
        ]

        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )

        self._process = process
        return process

    @staticmethod
    def _read_exact(pipe, size):
        """Membaca tepat satu frame, termasuk jika read() parsial."""

        chunks = []
        remaining = size

        while remaining > 0:
            chunk = pipe.read(remaining)

            if not chunk:
                return None

            chunks.append(chunk)
            remaining -= len(chunk)

        return b"".join(chunks)

    def _update(self):
        frame_size = (
            self.output_width * self.output_height * 3
        )
        failures = 0

        while not self._stop_event.is_set():
            process = None

            try:
                self._set_status("Menghubungkan ke CCTV...")
                process = self._start_ffmpeg()

                print(
                    "[STREAM] FFmpeg dimulai: "
                    f"{self.output_width}x{self.output_height}"
                )

                while not self._stop_event.is_set():
                    raw_frame = self._read_exact(
                        process.stdout,
                        frame_size,
                    )

                    if raw_frame is None:
                        break

                    frame = np.frombuffer(
                        raw_frame,
                        dtype=np.uint8,
                    ).reshape(
                        self.output_height,
                        self.output_width,
                        3,
                    )

                    now = time.monotonic()

                    with self._lock:
                        if self.last_frame_received is not None:
                            self.frame_interval_ms = (
                                now - self.last_frame_received
                            ) * 1000

                        self.last_frame_received = now
                        self.frames_received += 1

                        # Salin frame supaya buffer raw tidak dipakai ulang.
                        self._frame = frame.copy()
                        self._status = (
                            f"Live | "
                            f"{self.output_width}x{self.output_height}"
                        )

                    failures = 0

            except FileNotFoundError:
                self._set_status(
                    "FFmpeg tidak ditemukan. Periksa PATH instalasi."
                )
                print(
                    "[STREAM ERROR] Executable FFmpeg tidak ditemukan."
                )
                self._stop_event.wait(5.0)

            except Exception as exc:
                if not self._stop_event.is_set():
                    self._set_status(f"Kesalahan streaming: {exc}")
                    print(f"[STREAM ERROR] {exc}")

            finally:
                if process is not None:
                    if process.poll() is None:
                        process.terminate()

                        try:
                            process.wait(timeout=3.0)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=2.0)

                    if process.stdout:
                        process.stdout.close()

                self._process = None

            if self._stop_event.is_set():
                break

            failures += 1

            if failures >= self.max_read_failures:
                self._set_status(
                    "Stream berulang kali terputus. Mencoba kembali..."
                )
                failures = 0

            self._stop_event.wait(self.reconnect_delay)

        self._set_status("Stream dihentikan.")

    def read_frame(self):
        """Mengembalikan salinan frame terbaru yang tersedia."""

        with self._lock:
            if self._frame is None:
                return False, None

            return True, self._frame.copy()

    def get_metrics(self):
        with self._lock:
            age_ms = (
                (time.monotonic() - self.last_frame_received) * 1000
                if self.last_frame_received is not None
                else None
            )

            return {
                "frames_received": self.frames_received,
                "frame_interval_ms": self.frame_interval_ms,
                "frame_age_ms": age_ms,
                "status": self._status,
            }

    def release(self):
        """Menghentikan reader dan proses FFmpeg."""

        self._stop_event.set()

        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()

        self._thread.join(timeout=6.0)

        if self._thread.is_alive():
            process = self._process

            if process is not None and process.poll() is None:
                process.kill()

            self._thread.join(timeout=2.0)

        if self._thread.is_alive():
            print("[STREAM] Reader belum berhenti sepenuhnya.")
        else:
            print("[STREAM] Reader dihentikan.")

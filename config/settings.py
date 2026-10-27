# config/settings.py

# URL HLS CCTV Dishub Kota Semarang
STREAM_URL = (
    "https://livepantau.semarangkota.go.id/"
    "0f310a61-9d28-4f03-845d-daa815b72ccf/index.m3u8"
)

# Opsi FFmpeg untuk mengurangi buffering yang tidak diperlukan.
# Pengaruhnya bergantung pada versi FFmpeg dan backend OpenCV.
FFMPEG_CAPTURE_OPTIONS = (
    "fflags;nobuffer|"
    "flags;low_delay|"
    "rw_timeout;5000000|"
    "reconnect;1|"
    "reconnect_streamed;1|"
    "reconnect_delay_max;2"
)

# Konfigurasi streaming
RECONNECT_DELAY_SECONDS = 1.0
MAX_READ_FAILURES = 10
READ_RETRY_WAIT_SECONDS = 0.05

# Bobot kendaraan
VEHICLE_WEIGHTS = {
    "car": 2,
    "motorcycle": 1,
    "bus": 4,
    "truck": 4,
}

# Ambang batas kepadatan
THRESHOLD_LANCAR = 15
THRESHOLD_PADAT = 30
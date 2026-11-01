# config/settings.py

# URL HLS CCTV Dishub Kota Semarang
STREAM_URL = (
    "https://livepantau.semarangkota.go.id/8c97bfd3-a5f5-4a38-a520-975f112efd61/video1_stream.m3u8"
)
STREAM_URL_2 = (
    "https://livepantau.semarangkota.go.id/74ffdc80-264f-4028-94cc-4ede386b0340/index.m3u8"
) # depan polda

# Dynamic CCTV URL
CCTV_PAGE_URL = "https://pantausemar.semarangkota.go.id/"

# Nama kamera sesuai owner_name pada data PANTAUSEMAR
TARGET_CCTV_NAME = "Tugumuda 2"

CCTV_STREAM_PLAYLIST = "video1_stream.m3u8"

# Timeout HTTP: (connection timeout, read timeout)
CCTV_REQUEST_TIMEOUT = (5, 15)

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
# config/settings.py

# URL HLS CCTV Dishub Kota Semarang
STREAM_URL = (
    "https://livepantau.semarangkota.go.id/e1922578-42df-4a92-965a-9b6779d2c362/index.m3u8"
)
STREAM_URL_2 = (
    "https://livepantau.semarangkota.go.id/74ffdc80-264f-4028-94cc-4ede386b0340/index.m3u8"
) # depan polda

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
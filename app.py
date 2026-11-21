# app.py

import os
from web import create_app

app = create_app()


def main():
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", "5000"))

    print("====================================================")
    print(" Traffic Monitoring Kota Semarang - Web Dashboard")
    print(f" Buka browser di: http://{host}:{port}")
    print(" Tekan Ctrl+C untuk menghentikan server")
    print("====================================================")

    try:
        # debug=False wajib agar Werkzeug reloader tidak menggandakan worker FFmpeg.
        app.run(
            host=host,
            port=port,
            debug=False,
            threaded=True,
        )
    except KeyboardInterrupt:
        print("\n[SERVER] Menerima sinyal berhenti...")
    finally:
        manager = app.extensions.get("camera_manager")
        if manager is not None:
            manager.shutdown_all()
        print("[SERVER] Seluruh stream kamera ditutup dengan bersih.")


if __name__ == "__main__":
    main()
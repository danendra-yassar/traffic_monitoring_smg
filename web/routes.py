# web/routes.py

import re

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    render_template,
    request,
    stream_with_context,
)

from src.camera_manager import CameraManagerError
from src.cctv_resolver import CCTVResolverError, list_available_cctvs

web_bp = Blueprint("web", __name__)

_CAM_ID_PATTERN = re.compile(r"^[a-z0-9-]{1,48}$")


def _get_manager():
    """Mengambil instance CameraManager aktif dari context aplikasi."""
    return current_app.extensions["camera_manager"]


def _is_valid_cam_id(cam_id):
    """Memvalidasi format cam_id untuk mencegah karakter tidak sah."""
    return isinstance(cam_id, str) and bool(_CAM_ID_PATTERN.match(cam_id))


@web_bp.route("/", methods=["GET"])
def index():
    """Menampilkan halaman utama dashboard pemantauan lalu lintas."""
    return render_template("index.html")


@web_bp.route("/api/cctvs", methods=["GET"])
def api_list_cctvs():
    """Mengambil daftar kamera resmi PANTAUSEMAR untuk pilihan dropdown."""
    force_refresh = request.args.get("refresh", "0") == "1"

    try:
        cameras = list_available_cctvs(force_refresh=force_refresh)
    except CCTVResolverError as exc:
        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 502
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": f"Gagal memuat daftar CCTV: {exc}",
        }), 500

    if not cameras:
        return jsonify({
            "ok": False,
            "error": "Daftar CCTV PANTAUSEMAR kosong.",
        }), 502

    return jsonify({
        "ok": True,
        "total": len(cameras),
        "cctvs": cameras,
    }), 200


@web_bp.route("/api/cameras", methods=["GET"])
def api_get_active_cameras():
    """Mengembalikan daftar seluruh kamera yang sedang dipantau beserta metriknya."""
    manager = _get_manager()
    data = manager.list_cameras()
    return jsonify({
        "ok": True,
        **data,
    }), 200


@web_bp.route("/api/cameras", methods=["POST"])
def api_add_camera():
    """Menambahkan dan menyalakan worker pemantauan untuk satu CCTV."""
    if not request.is_json:
        return jsonify({
            "ok": False,
            "error": "Header Content-Type harus application/json.",
        }), 400

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({
            "ok": False,
            "error": "Body JSON tidak valid.",
        }), 400

    owner_name = payload.get("owner_name")
    if not isinstance(owner_name, str) or not owner_name.strip():
        return jsonify({
            "ok": False,
            "error": "Field 'owner_name' wajib diisi dengan nama lokasi CCTV.",
        }), 400

    manager = _get_manager()

    try:
        camera_state = manager.add_camera(owner_name.strip())
    except CameraManagerError as exc:
        message = str(exc)
        if (
            "sudah aktif" in message
            or "sedang dalam proses" in message
            or "Batas maksimal" in message
        ):
            status_code = 409
        else:
            status_code = 400

        return jsonify({
            "ok": False,
            "error": message,
        }), status_code
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": f"Kesalahan tidak terduga saat menambah kamera: {exc}",
        }), 500

    return jsonify({
        "ok": True,
        "camera": camera_state,
    }), 201


@web_bp.route("/api/cameras/<cam_id>", methods=["DELETE"])
def api_remove_camera(cam_id):
    """Menghentikan pemantauan kamera dan mematikan proses FFmpeg terkait."""
    if not _is_valid_cam_id(cam_id):
        return jsonify({
            "ok": False,
            "error": "Format ID kamera tidak valid.",
        }), 400

    manager = _get_manager()

    try:
        manager.remove_camera(cam_id)
    except CameraManagerError as exc:
        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 404
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": f"Gagal menghentikan kamera: {exc}",
        }), 500

    return jsonify({
        "ok": True,
        "message": f"Kamera '{cam_id}' berhasil dihentikan.",
    }), 200


@web_bp.route("/api/cameras/<cam_id>/roi", methods=["POST"])
def api_update_camera_roi(cam_id):
    """Memperbarui koordinat polygon ROI ternormalisasi untuk kamera tertentu."""
    if not _is_valid_cam_id(cam_id):
        return jsonify({
            "ok": False,
            "error": "Format ID kamera tidak valid.",
        }), 400

    if not request.is_json:
        return jsonify({
            "ok": False,
            "error": "Header Content-Type harus application/json.",
        }), 400

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or "points" not in payload:
        return jsonify({
            "ok": False,
            "error": "Payload JSON harus menyertakan field 'points'.",
        }), 400

    manager = _get_manager()

    try:
        updated_roi = manager.update_camera_roi(cam_id, payload["points"])
    except ValueError as exc:
        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 400
    except CameraManagerError as exc:
        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 404
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": f"Gagal menyimpan ROI: {exc}",
        }), 500

    return jsonify({
        "ok": True,
        "cam_id": cam_id,
        "roi_normalized": updated_roi,
    }), 200


@web_bp.route("/api/cameras/<cam_id>/roi/reset", methods=["POST"])
def api_reset_camera_roi(cam_id):
    """Mengembalikan polygon ROI kamera ke koordinat default."""
    if not _is_valid_cam_id(cam_id):
        return jsonify({
            "ok": False,
            "error": "Format ID kamera tidak valid.",
        }), 400

    manager = _get_manager()

    try:
        default_roi = manager.reset_camera_roi(cam_id)
    except CameraManagerError as exc:
        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 404
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": f"Gagal mereset ROI: {exc}",
        }), 500

    return jsonify({
        "ok": True,
        "cam_id": cam_id,
        "roi_normalized": default_roi,
    }), 200


@web_bp.route("/video_feed/<cam_id>", methods=["GET"])
def video_feed(cam_id):
    """Mengalirkan video hasil deteksi YOLOv8 dalam format MJPEG."""
    if not _is_valid_cam_id(cam_id):
        return jsonify({
            "ok": False,
            "error": "Format ID kamera tidak valid.",
        }), 400

    manager = _get_manager()
    worker = manager.get_camera(cam_id)

    if worker is None:
        return jsonify({
            "ok": False,
            "error": f"Stream kamera '{cam_id}' tidak ditemukan atau sudah dihentikan.",
        }), 404

    def generate_mjpeg():
        last_seq = -1
        try:
            while not worker._stop_event.is_set():
                seq, jpeg_bytes = worker.wait_for_frame(last_seq, timeout=1.0)

                if not jpeg_bytes:
                    continue

                last_seq = seq
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(jpeg_bytes)}\r\n\r\n".encode("ascii")
                    + jpeg_bytes
                    + b"\r\n"
                )
        except GeneratorExit:
            # Browser menutup koneksi video; keluar dari generator secara bersih.
            return
        except Exception as exc:
            print(f"[STREAM FEED ERROR] ({cam_id}): {exc}")

    response = Response(
        stream_with_context(generate_mjpeg()),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response
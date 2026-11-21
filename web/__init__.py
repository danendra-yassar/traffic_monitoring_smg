# web/__init__.py

from flask import Flask, jsonify

from src.camera_manager import CameraManager
from web.routes import web_bp


def create_app():
    """Factory untuk membuat dan mengonfigurasi instance aplikasi Flask."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # Simpan satu instance CameraManager di level aplikasi.
    app.extensions["camera_manager"] = CameraManager()

    # Daftarkan blueprint route web dan API.
    app.register_blueprint(web_bp)

    # Global error handler agar semua error API selalu mengembalikan JSON.
    @app.errorhandler(404)
    def handle_not_found(error):
        return jsonify({
            "ok": False,
            "error": "Endpoint atau resource tidak ditemukan.",
        }), 404

    @app.errorhandler(405)
    def handle_method_not_allowed(error):
        return jsonify({
            "ok": False,
            "error": "Metode HTTP tidak diizinkan untuk endpoint ini.",
        }), 405

    @app.errorhandler(500)
    def handle_internal_error(error):
        return jsonify({
            "ok": False,
            "error": "Terjadi kesalahan internal pada server.",
        }), 500

    return app
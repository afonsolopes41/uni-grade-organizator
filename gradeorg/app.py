"""Servidor local: API JSON + pagina web.

Corre em 127.0.0.1, sem autenticacao e sem sair da maquina -- as pautas nunca
saem do computador de quem as carrega.
"""

from __future__ import annotations

import io
import os
import sys
import threading
import traceback

from flask import Flask, jsonify, request, send_file, send_from_directory

from .excel import build_workbook
from .i18n import tr
from .parsers import SUPPORTED, UnsupportedFile
from .session import SESSION

MAX_UPLOAD_BYTES = 64 * 1024 * 1024


def resource_dir() -> str:
    """Directorio dos ficheiros estaticos (funciona dentro do .exe)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "gradeorg", "web")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
    web_dir = resource_dir()

    # -- pagina --------------------------------------------------------

    @app.get("/")
    def index():
        return send_from_directory(web_dir, "index.html")

    @app.get("/<path:filename>")
    def static_files(filename: str):
        return send_from_directory(web_dir, filename)

    # -- API -----------------------------------------------------------

    @app.get("/api/state")
    def api_state():
        return jsonify(SESSION.review())

    @app.post("/api/upload")
    def api_upload():
        uploaded = request.files.getlist("files")
        if not uploaded:
            return jsonify({"error": tr("api.no_files", SESSION.language)}), 400

        accepted, rejected = [], []
        for item in uploaded:
            name = item.filename or "ficheiro"
            extension = os.path.splitext(name)[1].lower()
            if extension not in SUPPORTED:
                rejected.append({"name": name, "error": tr(
                    "api.unsupported_format", SESSION.language,
                    ext=extension or "?")})
                continue
            try:
                SESSION.add_file(name, item.read())
                accepted.append(name)
            except (UnsupportedFile, ValueError) as error:
                rejected.append({"name": name, "error": str(error)})
            except Exception as error:                     # noqa: BLE001
                traceback.print_exc()
                rejected.append({"name": name, "error": tr(
                    "api.read_failed", SESSION.language, error=error)})

        payload = SESSION.review()
        payload["accepted"] = accepted
        payload["rejected"] = rejected
        return jsonify(payload)

    @app.post("/api/answers")
    def api_answers():
        body = request.get_json(silent=True) or {}
        SESSION.update(
            answers=body.get("answers"),
            overrides=body.get("overrides"),
            settings=body.get("settings"),
        )
        return jsonify(SESSION.review())

    @app.post("/api/subjects")
    def api_subjects():
        """Apagar, repor e mudar o nome a uma unidade curricular."""
        body = request.get_json(silent=True) or {}
        action = body.get("action")
        subject = (body.get("subject") or "").strip()
        if action == "rename":
            SESSION.rename_subject(subject, body.get("name") or "")
        elif action == "remove":
            SESSION.remove_subject(subject)
        elif action == "restore":
            SESSION.restore_subject(subject)
        else:
            return jsonify({"error": tr("api.unknown_action", SESSION.language,
                                        action=action)}), 400
        return jsonify(SESSION.review())

    @app.post("/api/language")
    def api_language():
        body = request.get_json(silent=True) or {}
        SESSION.set_language(body.get("language"))
        return jsonify(SESSION.review())

    @app.post("/api/files/remove")
    def api_remove():
        body = request.get_json(silent=True) or {}
        name = body.get("name")
        if name:
            SESSION.remove_file(name)
        return jsonify(SESSION.review())

    @app.post("/api/reset")
    def api_reset():
        SESSION.reset()
        return jsonify(SESSION.review())

    @app.get("/api/results")
    def api_results():
        if not SESSION.files:
            return jsonify({"error": tr("api.nothing_loaded",
                                        SESSION.language)}), 400
        return jsonify(SESSION.result())

    @app.post("/api/export")
    def api_export():
        if not SESSION.files:
            return jsonify({"error": tr("api.nothing_loaded",
                                        SESSION.language)}), 400
        body = request.get_json(silent=True) or {}
        workbook = build_workbook(
            SESSION.raw_result(),
            source_labels=SESSION.source_labels(),
            selected_students=body.get("students") or None,
            selected_subjects=body.get("subjects") or None,
            lang=SESSION.language,
        )
        stream = io.BytesIO()
        workbook.save(stream)
        stream.seek(0)
        return send_file(
            stream,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=body.get("filename") or "notas-consolidadas.xlsx",
        )

    @app.post("/api/shutdown")
    def api_shutdown():
        def stop():
            os._exit(0)

        threading.Timer(0.4, stop).start()
        return jsonify({"ok": True})

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify({"error": tr("api.too_large", SESSION.language)}), 413

    @app.errorhandler(500)
    def server_error(error):
        traceback.print_exc()
        return jsonify({"error": tr("api.internal_error", SESSION.language,
                                    error=error)}), 500

    return app

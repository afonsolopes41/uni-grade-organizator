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
            return jsonify({"error": "Não veio nenhum ficheiro."}), 400

        accepted, rejected = [], []
        for item in uploaded:
            name = item.filename or "ficheiro"
            extension = os.path.splitext(name)[1].lower()
            if extension not in SUPPORTED:
                rejected.append({"name": name,
                                 "error": f"Formato «{extension or '?'}» não suportado. "
                                          "Aceita PDF, XLSX, CSV e TXT."})
                continue
            try:
                SESSION.add_file(name, item.read())
                accepted.append(name)
            except (UnsupportedFile, ValueError) as error:
                rejected.append({"name": name, "error": str(error)})
            except Exception as error:                     # noqa: BLE001
                traceback.print_exc()
                rejected.append({"name": name,
                                 "error": f"Não foi possível ler o ficheiro: {error}"})

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
            return jsonify({"error": "Ainda não foi carregado nenhum ficheiro."}), 400
        return jsonify(SESSION.result())

    @app.post("/api/export")
    def api_export():
        if not SESSION.files:
            return jsonify({"error": "Ainda não foi carregado nenhum ficheiro."}), 400
        body = request.get_json(silent=True) or {}
        workbook = build_workbook(
            SESSION.raw_result(),
            source_labels=SESSION.source_labels(),
            selected_students=body.get("students") or None,
            selected_subjects=body.get("subjects") or None,
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
        return jsonify({"error": "Ficheiro demasiado grande (limite de 64 MB)."}), 413

    @app.errorhandler(500)
    def server_error(error):
        traceback.print_exc()
        return jsonify({"error": f"Erro interno: {error}"}), 500

    return app

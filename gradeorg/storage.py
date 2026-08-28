"""Memoria entre arranques.

A aplicacao fecha-se e volta a abrir com tudo como estava: os ficheiros que
foram carregados, as respostas dadas, os nomes das cadeiras, o plano de
estudos. So o botao de apagar e que limpa.

Tudo vive numa pasta do utilizador (nada sai do computador):

    <casa>/sessao.json      -- respostas, definicoes e lista de ficheiros
    <casa>/ficheiros/       -- copia dos ficheiros carregados
    <casa>/tabelas/         -- as tabelas ja extraidas, para arrancar depressa
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

#: Sobe quando o formato mudar de maneira incompativel.
FORMAT_VERSION = 1

APP_DIR_NAME = "OrganizadorDeNotas"


def data_home() -> str:
    """Pasta onde a sessao fica guardada, criada se ainda nao existir."""
    override = os.environ.get("GRADEORG_HOME")
    if override:
        base = override
    elif sys.platform.startswith("win"):
        base = os.path.join(os.environ.get("APPDATA")
                            or os.path.expanduser("~"), APP_DIR_NAME)
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library",
                            "Application Support", APP_DIR_NAME)
    else:
        base = os.path.join(
            os.environ.get("XDG_DATA_HOME") or os.path.join(
                os.path.expanduser("~"), ".local", "share"),
            "organizador-de-notas")
    os.makedirs(base, exist_ok=True)
    return base


def files_dir() -> str:
    path = os.path.join(data_home(), "ficheiros")
    os.makedirs(path, exist_ok=True)
    return path


def tables_dir() -> str:
    path = os.path.join(data_home(), "tabelas")
    os.makedirs(path, exist_ok=True)
    return path


def state_path() -> str:
    return os.path.join(data_home(), "sessao.json")


def write_json(path: str, payload: dict) -> None:
    """Grava sem deixar o ficheiro a meio se algo correr mal."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
        os.replace(temporary, path)
    except Exception:                                    # noqa: BLE001
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def read_json(path: str):
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return None


def wipe() -> None:
    """Apaga tudo o que esta guardado. So o utilizador e que pede isto."""
    home = data_home()
    for name in ("sessao.json",):
        try:
            os.unlink(os.path.join(home, name))
        except OSError:
            pass
    for name in ("ficheiros", "tabelas"):
        shutil.rmtree(os.path.join(home, name), ignore_errors=True)

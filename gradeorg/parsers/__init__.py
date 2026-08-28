"""Encaminhamento por extensao de ficheiro."""

from __future__ import annotations

import os

from .excel_in import parse_xlsx
from .pdf import parse_pdf
from .text import parse_text

SUPPORTED = {".pdf", ".xlsx", ".xlsm", ".xltx", ".csv", ".txt", ".tsv"}


class UnsupportedFile(Exception):
    pass


def kind_of(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        return "pdf"
    if ext in (".xlsx", ".xlsm", ".xltx"):
        return "xlsx"
    if ext in (".csv", ".tsv"):
        return "csv"
    if ext == ".txt":
        return "txt"
    raise UnsupportedFile(f"Formato não suportado: {ext or filename}")


def parse_file(path: str, filename: str = "") -> tuple:
    """Devolve ``(kind, [RawTable, ...])``."""
    name = filename or os.path.basename(path)
    kind = kind_of(name)
    if kind == "pdf":
        return kind, parse_pdf(path)
    if kind == "xlsx":
        return kind, parse_xlsx(path)
    return kind, parse_text(path)

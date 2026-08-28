"""Leitura de folhas de calculo (.xlsx/.xlsm) com openpyxl."""

from __future__ import annotations

import openpyxl

from ..models import RawTable
from ..normalize import clean_text


def parse_xlsx(path: str) -> list:
    """Uma RawTable por folha com conteudo."""
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    tables = []
    try:
        for sheet in workbook.worksheets:
            if sheet.sheet_state != "visible":
                continue
            rows = []
            for raw in sheet.iter_rows(values_only=True):
                rows.append([clean_text(c) for c in raw])
            rows = _trim(rows)
            if len(rows) < 2:
                continue
            tables.append(
                RawTable(
                    rows=rows,
                    location=f"sheet:{sheet.title}",
                    sheet_name=sheet.title,
                    title_lines=_leading_titles(rows),
                    footer_lines=_trailing_notes(rows),
                )
            )
    finally:
        workbook.close()
    return tables


def _leading_titles(rows: list, limit: int = 4) -> list:
    """Linhas de titulo no topo: as que so tem uma celula preenchida."""
    titles = []
    for row in rows[:limit]:
        filled = [c for c in row if c]
        if len(filled) == 1 and len(filled[0]) >= 4:
            titles.append(filled[0])
        else:
            break
    return titles


def _trailing_notes(rows: list, limit: int = 3) -> list:
    """Ultimas linhas esparsas -- podem trazer a data do documento."""
    notes = []
    for row in rows[-limit:]:
        filled = [c for c in row if c]
        if 0 < len(filled) <= 2:
            notes.append(" ".join(filled))
    return notes


def _trim(rows: list) -> list:
    """Corta linhas e colunas completamente vazias nas extremidades."""
    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]

    keep = [i for i in range(width) if any(r[i] for r in rows)]
    if not keep:
        return []
    first, last = keep[0], keep[-1]
    return [r[first : last + 1] for r in rows]

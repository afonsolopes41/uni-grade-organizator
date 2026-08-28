"""Extraccao de tabelas de PDF.

Estrategia em duas passagens:

1. ``extract_tables`` do pdfplumber, que apanha pautas com grelha desenhada;
2. se isso falhar (a maioria das pautas nao tem linhas), reconstroi-se a
   tabela a partir das posicoes x das palavras -- as colunas de um PDF de
   texto estao sempre alinhadas, mesmo sem grelha.
"""

from __future__ import annotations

from typing import Optional

import pdfplumber

from ..models import RawTable
from ..normalize import clean_text, looks_like_person_name, parse_number

_MIN_TABLE_ROWS = 3


def parse_pdf(path: str) -> list:
    """Devolve uma RawTable por pagina com conteudo tabular."""
    tables = []
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            table = _table_from_lines(page, page_no)
            if table is None:
                table = _table_from_words(page, page_no)
            if table and len(table.rows) >= _MIN_TABLE_ROWS:
                tables.append(table)
    return _merge_continuation_pages(tables)


# --------------------------------------------------------------------------
# Passagem 1: grelha desenhada
# --------------------------------------------------------------------------

def _table_from_lines(page, page_no: int) -> Optional[RawTable]:
    try:
        found = page.extract_tables(
            {
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "intersection_tolerance": 5,
            }
        )
    except Exception:
        return None

    best = None
    for raw in found or []:
        rows = [[clean_text(c) for c in row] for row in raw]
        rows = [r for r in rows if any(c for c in r)]
        if len(rows) >= _MIN_TABLE_ROWS and len(rows[0]) >= 2:
            if best is None or len(rows) > len(best):
                best = rows
    if not best:
        return None

    return RawTable(rows=best, location=f"página {page_no}", page=page_no,
                    title_lines=_page_head(page), footer_lines=_page_foot(page))


# --------------------------------------------------------------------------
# Passagem 2: reconstruir colunas a partir das posicoes das palavras
# --------------------------------------------------------------------------

def _table_from_words(page, page_no: int) -> Optional[RawTable]:
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False,
                               extra_attrs=["size"])
    if not words:
        return None

    lines = _group_into_lines(words)
    if len(lines) < _MIN_TABLE_ROWS:
        return None

    body_start, body_end = _find_body(lines)
    if body_end - body_start < 2:
        return None

    body = lines[body_start:body_end]
    boundaries = _column_boundaries(body)

    header_idx = _find_header_line(lines, body_start, boundaries)
    table_lines = lines[header_idx:body_end] if header_idx is not None else body

    rows = [_split_line(line, boundaries) for line in table_lines]
    rows = [r for r in rows if any(c for c in r)]
    if len(rows) < _MIN_TABLE_ROWS:
        return None

    title_lines = [_line_text(l) for l in lines[: (header_idx if header_idx is not None else body_start)]]
    footer_lines = [_line_text(l) for l in lines[body_end:]]

    return RawTable(rows=rows, location=f"página {page_no}", page=page_no,
                    title_lines=[t for t in title_lines if t],
                    footer_lines=[t for t in footer_lines if t])


def _group_into_lines(words: list) -> list:
    """Agrupa palavras por linha usando a coordenada vertical."""
    ordered = sorted(words, key=lambda w: (round(w["top"], 1), w["x0"]))
    lines: list = []
    current: list = []
    current_top = None
    for word in ordered:
        height = max(word["bottom"] - word["top"], 1.0)
        if current_top is None or abs(word["top"] - current_top) <= height * 0.6:
            current.append(word)
            current_top = word["top"] if current_top is None else current_top
        else:
            lines.append(sorted(current, key=lambda w: w["x0"]))
            current = [word]
            current_top = word["top"]
    if current:
        lines.append(sorted(current, key=lambda w: w["x0"]))
    return lines


def _line_text(line: list) -> str:
    return clean_text(" ".join(w["text"] for w in line))


def _is_data_line(line: list) -> bool:
    """Linha de dados = tem um nome de pessoa e/ou numeros a direita."""
    text = _line_text(line)
    if not text or len(line) < 2:
        return False
    numeric = sum(1 for w in line if parse_number(w["text"]) is not None)
    has_name = looks_like_person_name(" ".join(
        w["text"] for w in line if parse_number(w["text"]) is None))
    return has_name or numeric >= 2


def _find_body(lines: list):
    """Maior bloco contiguo de linhas de dados."""
    best = (0, 0)
    start = None
    for i, line in enumerate(lines + [[]]):
        if line and _is_data_line(line):
            if start is None:
                start = i
        else:
            if start is not None:
                if i - start > best[1] - best[0]:
                    best = (start, i)
                start = None
    return best


def _column_boundaries(body: list) -> list:
    """Descobre os limites x das colunas a partir dos intervalos entre palavras.

    Projecta todas as palavras do corpo da tabela num eixo x e procura faixas
    verticais que nunca sao atravessadas por texto: essas sao as separacoes.
    """
    spans = [(w["x0"], w["x1"]) for line in body for w in line]
    if not spans:
        return []
    spans.sort()
    left = min(s[0] for s in spans)
    right = max(s[1] for s in spans)

    gaps = []
    cursor = left
    for x0, x1 in spans:
        if x0 > cursor + 4.5:      # 4.5pt ~ um espaco largo
            gaps.append((cursor, x0))
        cursor = max(cursor, x1)

    boundaries = [left - 1]
    for g0, g1 in gaps:
        boundaries.append((g0 + g1) / 2)
    boundaries.append(right + 1)
    return boundaries


def _split_line(line: list, boundaries: list) -> list:
    """Distribui as palavras de uma linha pelas colunas."""
    if not boundaries:
        return [_line_text(line)]
    cells = [[] for _ in range(len(boundaries) - 1)]
    for word in line:
        centre = (word["x0"] + word["x1"]) / 2
        idx = 0
        for i in range(len(boundaries) - 1):
            if boundaries[i] <= centre < boundaries[i + 1]:
                idx = i
                break
        else:
            idx = len(cells) - 1 if centre >= boundaries[-1] else 0
        cells[idx].append(word["text"])
    return [clean_text(" ".join(c)) for c in cells]


def _find_header_line(lines: list, body_start: int, boundaries: list):
    """A linha imediatamente acima do corpo que se reparte por varias colunas."""
    for idx in range(body_start - 1, max(body_start - 4, -1), -1):
        cells = [c for c in _split_line(lines[idx], boundaries) if c]
        if len(cells) >= 2:
            return idx
    return None


def _page_head(page, limit: int = 3) -> list:
    text = page.extract_text() or ""
    return [clean_text(l) for l in text.splitlines()[:limit] if clean_text(l)]


def _page_foot(page, limit: int = 3) -> list:
    text = page.extract_text() or ""
    return [clean_text(l) for l in text.splitlines()[-limit:] if clean_text(l)]


# --------------------------------------------------------------------------
# Paginas continuadas
# --------------------------------------------------------------------------

def _merge_continuation_pages(tables: list) -> list:
    """Junta paginas seguidas com o mesmo numero de colunas e sem cabecalho novo."""
    if len(tables) <= 1:
        return tables
    merged = [tables[0]]
    for table in tables[1:]:
        prev = merged[-1]
        same_shape = len(table.rows[0]) == len(prev.rows[0])
        if same_shape and _repeats_header(prev.rows[0], table.rows[0]):
            prev.rows.extend(table.rows[1:])
            prev.location += f", {table.location.replace('página ', '')}"
        elif same_shape and not _looks_like_header(table.rows[0]):
            prev.rows.extend(table.rows)
            prev.location += f", {table.location.replace('página ', '')}"
        else:
            merged.append(table)
    return merged


def _repeats_header(first: list, other: list) -> bool:
    return [c.lower() for c in first] == [c.lower() for c in other]


def _looks_like_header(row: list) -> bool:
    from ..detect import header_score
    return header_score(row) >= 2

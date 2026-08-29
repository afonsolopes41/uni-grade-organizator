"""Leitura de .txt e .csv, com deteccao de codificacao e de separador."""

from __future__ import annotations

import csv
import io
import re

from ..models import RawTable
from ..normalize import clean_text

_ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
_BOMS = [
    (b"\xff\xfe\x00\x00", "utf-32"), (b"\x00\x00\xfe\xff", "utf-32"),
    (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16"), (b"\xef\xbb\xbf", "utf-8-sig"),
]
_DELIMITERS = ["\t", ";", "|", ","]
_MULTISPACE = re.compile(r" {2,}")


def read_text(path: str) -> str:
    with open(path, "rb") as handle:
        data = handle.read()
    # Um BOM diz logo qual e a codificacao; sem ele, tenta-se pela ordem usual.
    for bom, encoding in _BOMS:
        if data.startswith(bom):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                break
    for encoding in _ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_text(path: str) -> list:
    """Devolve uma unica RawTable com as linhas repartidas em colunas."""
    content = read_text(path)
    lines = [l.rstrip("\r\n") for l in content.splitlines()]
    lines = [l for l in lines if l.strip()]
    if len(lines) < 2:
        return []

    delimiter = _pick_delimiter(lines)
    if delimiter:
        reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter)
        rows = [[clean_text(c) for c in row] for row in reader]
    else:
        rows = _split_fixed_width(lines)

    rows = [r for r in rows if any(c for c in r)]
    if len(rows) < 2:
        return []

    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    return [RawTable(rows=rows, location="text")]


def _pick_delimiter(lines: list):
    """Escolhe o separador com a contagem de colunas mais consistente.

    Linhas de titulo no topo ("Pauta de Fisica") nao trazem separador nenhum;
    olhar so para o minimo descartaria o separador certo, por isso a decisao
    faz-se sobre as linhas que o contem, exigindo que sejam a maioria.
    """
    sample = lines[: min(len(lines), 60)]
    best = None
    for delimiter in _DELIMITERS:
        counts = [l.count(delimiter) for l in sample]
        with_delimiter = [c for c in counts if c >= 1]
        if len(with_delimiter) < max(2, int(len(sample) * 0.6)):
            continue
        common = max(set(with_delimiter), key=with_delimiter.count)
        consistency = with_delimiter.count(common) / len(with_delimiter)
        score = consistency * 10 + common
        if consistency >= 0.7 and (best is None or score > best[1]):
            best = (delimiter, score)
    return best[0] if best else None


def _split_fixed_width(lines: list) -> list:
    """Sem separador: reparte por corredores de espacos partilhados por todas as linhas."""
    width = max(len(l) for l in lines)
    padded = [l.ljust(width) for l in lines]
    space_everywhere = [
        all(row[i] == " " for row in padded) for i in range(width)
    ]

    cuts = []
    run_start = None
    for i, is_space in enumerate(space_everywhere + [False]):
        if is_space:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None and i - run_start >= 2:
                cuts.append((run_start + i) // 2)
            run_start = None

    if not cuts:
        return [_MULTISPACE.split(l.strip()) for l in lines]

    rows = []
    for line in padded:
        cells, previous = [], 0
        for cut in cuts + [width]:
            cells.append(clean_text(line[previous:cut]))
            previous = cut
        rows.append(cells)
    return rows

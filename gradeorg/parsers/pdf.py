"""Extraccao de tabelas de PDF.

Estrategia em duas passagens:

1. ``extract_tables`` do pdfplumber, que apanha pautas com grelha desenhada;
2. se isso falhar (a maioria das pautas nao tem linhas), reconstroi-se a tabela
   a partir das posicoes das palavras.

A segunda passagem e a que faz o trabalho todo, e assenta em tres observacoes
sobre pautas reais:

* **as linhas de alunos estao todas alinhadas a esquerda pelo mesmo x.** E o que
  separa uma linha de dados de um titulo ou de uma legenda a meio da pagina.
* **as colunas so se veem no corpo da tabela.** Calcular os limites usando
  tambem os titulos faz desaparecer separacoes: basta um "Final Marks" a
  atravessar a fronteira entre duas colunas para as colar uma a outra.
* **o cabecalho pode ocupar varias linhas.** "Test 1" numa linha, "30%" na
  linha de baixo e "Number Name Date Grade" pelo meio -- tudo isso e um so
  cabecalho, e cada pedaco pertence a coluna que tem por baixo.
"""

from __future__ import annotations

import statistics
from typing import Optional

import pdfplumber

from ..models import RawTable
from ..normalize import clean_text, looks_like_person_name, parse_number, parse_student_id

_MIN_TABLE_ROWS = 3
#: Espaco horizontal a partir do qual se assume uma separacao entre colunas.
_COLUMN_GAP = 4.5
#: Espaco horizontal que separa dois blocos de texto independentes na mesma
#: linha visual (o titulo a esquerda e a legenda a direita, por exemplo).
_SEGMENT_GAP = 22.0
#: Uma celula de cabecalho com muitas palavras nao e cabecalho, e prosa.
_MAX_HEADER_WORDS = 4
#: Intervalo que separa duas colunas numa linha de cabecalho.
_HEADER_GAP = 7.0
#: Abaixo desta sobreposicao, duas metades sob a mesma palavra de cabecalho sao
#: a mesma coluna.
_SAME_COLUMN_OVERLAP = 0.25
#: Desvio tolerado no alinhamento da primeira coluna das linhas de dados.
_ALIGN_TOLERANCE = 5.0
#: Linhas em branco toleradas no meio do corpo da tabela.
_MAX_ROW_SKIP = 2


def parse_pdf(path: str) -> list:
    """Devolve uma RawTable por pagina com conteudo tabular."""
    tables = []
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            candidates = [_table_from_lines(page, page_no),
                          _table_from_words(page, page_no)]
            candidates = [t for t in candidates
                          if t is not None and len(t.rows) >= _MIN_TABLE_ROWS]
            if candidates:
                tables.append(max(candidates, key=_score_table))
    return _merge_continuation_pages(tables)


def _score_table(table: RawTable) -> float:
    """Quao bem esta tabela foi extraida.

    Ha pautas com grelha desenhada em que a grelha nao corresponde as colunas
    reais -- linhas verticais a mais ou a menos. Em vez de confiar num metodo,
    corre-se os dois e fica o que produzir uma tabela mais cheia: celulas
    vazias e colunas inteiramente vazias sao o sintoma de uma ma separacao.
    """
    from ..detect import header_score

    rows = table.rows
    if not rows:
        return -1.0
    width = max(len(r) for r in rows)
    if width < 2:
        return -1.0

    def cell(row, index):
        return row[index] if index < len(row) else ""

    filled = sum(1 for r in rows for i in range(width) if cell(r, i))
    fill_ratio = filled / (len(rows) * width)
    empty_columns = sum(1 for i in range(width)
                        if not any(cell(r, i) for r in rows))
    best_header = max((header_score(r) for r in rows[:4]), default=0)
    return fill_ratio * 100 - empty_columns * 10 + min(best_header, 12)


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

    text_lines = [clean_text(l) for l in (page.extract_text() or "").splitlines()]
    text_lines = [l for l in text_lines if l]
    return RawTable(rows=best, location=f"página {page_no}", page=page_no,
                    title_lines=text_lines[:3], footer_lines=text_lines[-3:])


# --------------------------------------------------------------------------
# Passagem 2: reconstruir colunas a partir das posicoes das palavras
# --------------------------------------------------------------------------

def _table_from_words(page, page_no: int) -> Optional[RawTable]:
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not words:
        return None

    lines = _group_into_lines(words)
    if len(lines) < _MIN_TABLE_ROWS:
        return None

    body_indices = _find_data_lines(lines)
    if len(body_indices) < 2:
        return None

    body = [lines[i] for i in body_indices]
    boundaries = _column_boundaries(body)
    if len(boundaries) < 3:
        return None

    # O cabecalho serve de fiel: uma palavra que atravesse um limite prova que
    # esse limite nao existe (ver _drop_straddled_boundaries).
    header_indices = _header_band(lines, body_indices[0], boundaries)
    boundaries = _drop_straddled_boundaries(
        boundaries, [lines[i] for i in header_indices], body)
    header_indices = _header_band(lines, body_indices[0], boundaries)
    header = _merge_header([lines[i] for i in header_indices], boundaries)

    rows = [header] if any(header) else []
    rows += [_split_line(line, boundaries) for line in body]
    rows = [r for r in rows if any(c for c in r)]
    rows = _drop_empty_columns(rows)
    if len(rows) < _MIN_TABLE_ROWS:
        return None

    first_header = header_indices[0] if header_indices else body_indices[0]
    title_lines = _text_segments(lines[:first_header])
    footer_lines = _text_segments(lines[body_indices[-1] + 1 :])

    return RawTable(rows=rows, location=f"página {page_no}", page=page_no,
                    title_lines=title_lines, footer_lines=footer_lines)


def _group_into_lines(words: list) -> list:
    """Agrupa palavras em linhas visuais.

    A tolerancia vem da altura mediana das palavras da pagina, e nao da altura
    de cada palavra: uma palavra grande no meio de texto pequeno arrastava
    consigo a linha seguinte.
    """
    heights = [w["bottom"] - w["top"] for w in words] or [8.0]
    tolerance = min(max(statistics.median(heights) * 0.55, 1.5), 4.0)

    ordered = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list = []
    current: list = []
    line_top = None
    for word in ordered:
        if line_top is None or abs(word["top"] - line_top) <= tolerance:
            current.append(word)
            line_top = word["top"] if line_top is None else min(line_top, word["top"])
        else:
            lines.append(sorted(current, key=lambda w: w["x0"]))
            current = [word]
            line_top = word["top"]
    if current:
        lines.append(sorted(current, key=lambda w: w["x0"]))
    return lines


# --------------------------------------------------------------------------
# Onde comeca e acaba a tabela
# --------------------------------------------------------------------------

def _looks_like_record(line: list) -> bool:
    """Uma linha de aluno tem um nome ou um numero, e valores.

    "Number Name Date Grade" tambem passa por um nome de pessoa, por isso as
    linhas que pontuam como cabecalho ficam de fora -- se entrassem no corpo,
    levavam com elas a linha que da nome as colunas.
    """
    from ..detect import header_score

    if len(line) < 2:
        return False
    texts = [w["text"] for w in line]
    if header_score(texts) >= 3:
        return False
    has_id = any(parse_student_id(t) for t in texts)
    has_name = looks_like_person_name(
        " ".join(t for t in texts if parse_number(t) is None))
    values = sum(1 for t in texts if parse_number(t) is not None or len(t) <= 3)
    return (has_id or has_name) and values >= 1


def _find_data_lines(lines: list) -> list:
    """Indices das linhas de alunos, pelo alinhamento da primeira coluna.

    Todas as linhas de dados comecam na mesma coluna; titulos, legendas e notas
    de rodape comecam noutro sitio -- e sao precisamente essas que, se
    entrassem no calculo das colunas, colavam umas as outras.

    O alinhamento tanto pode ser a esquerda (nomes) como a direita (numeros de
    aluno, onde um numero de cinco digitos comeca mais a direita do que um de
    seis). Testam-se as duas margens e fica a que juntar mais linhas.
    """
    candidates = [i for i, line in enumerate(lines) if _looks_like_record(line)]
    if len(candidates) < 2:
        return []

    best: list = []
    for edge in ("x0", "x1"):
        positions = sorted((lines[i][0][edge], i) for i in candidates)
        start = 0
        for end in range(len(positions) + 1):
            if end < len(positions) and positions[end][0] - positions[start][0] <= _ALIGN_TOLERANCE:
                continue
            run = _longest_run(sorted(index for _, index in positions[start:end]))
            if len(run) > len(best):
                best = run
            start = end

    return best if len(best) >= 2 else candidates


def _longest_run(indices: list) -> list:
    """Maior sequencia de linhas seguidas.

    Os alunos ocupam linhas consecutivas. Sem isto, uma linha de titulo cujo
    primeiro numero por acaso alinha com os numeros de aluno entrava no corpo da
    tabela e estragava o calculo das colunas.
    """
    best: list = []
    current: list = []
    for index in indices:
        if current and index - current[-1] > _MAX_ROW_SKIP:
            if len(current) > len(best):
                best = current
            current = []
        current.append(index)
    return best if len(best) > len(current) else current


def _column_boundaries(body: list) -> list:
    """Limites x das colunas, a partir dos intervalos que nenhuma palavra ocupa."""
    spans = sorted((w["x0"], w["x1"]) for line in body for w in line)
    if not spans:
        return []
    left = spans[0][0]
    right = max(s[1] for s in spans)

    boundaries = [left - 1]
    cursor = left
    for x0, x1 in spans:
        if x0 > cursor + _COLUMN_GAP:
            boundaries.append((cursor + x0) / 2)
        cursor = max(cursor, x1)
    boundaries.append(right + 1)
    return boundaries


def _drop_straddled_boundaries(boundaries: list, header_lines: list,
                               body: list) -> list:
    """Junta duas metades de uma coluna que o calculo dos vazios separou.

    Numa coluna com valores alinhados a direita, um "f" estreito e um "10.0"
    largo nao chegam a sobrepor-se em x, e o intervalo vazio entre eles parte a
    coluna em duas. Sao precisos dois sinais para desfazer a separacao:

    1. uma palavra do cabecalho ("Test") passa por cima das duas metades, e
    2. quase nenhum aluno tem valor nas duas metades ao mesmo tempo.

    O segundo sinal e o que impede juntar colunas a serio: "Nota Final" e
    "Avaliação Final" estao ambas preenchidas na mesma linha, por isso ficam
    separadas mesmo que uma palavra larga do cabecalho passe por cima. E o
    "quase" abre espaco para as notas compostas -- "RE m" ocupa a coluna e um
    bocadinho da seguinte, mas so em meia duzia de linhas.
    """
    if len(boundaries) <= 3 or not header_lines or not body:
        return boundaries

    spans = [(w["x0"], w["x1"]) for line in header_lines for w in line]
    occupied = [set() for _ in range(len(boundaries) - 1)]
    for row_index, line in enumerate(body):
        for word in line:
            occupied[_column_of(word["x0"], word["x1"], boundaries)].add(row_index)

    drop = set()
    for index in range(1, len(boundaries) - 1):
        boundary = boundaries[index]
        if not any(x0 < boundary < x1 for x0, x1 in spans):
            continue
        together = occupied[index - 1] & occupied[index]
        either = occupied[index - 1] | occupied[index]
        if either and len(together) / len(either) < _SAME_COLUMN_OVERLAP:
            drop.add(index)

    return [b for i, b in enumerate(boundaries) if i not in drop]


def _column_of(x0: float, x1: float, boundaries: list) -> int:
    """Coluna a que pertence um pedaco de texto (pelo seu centro)."""
    centre = (x0 + x1) / 2
    for index in range(len(boundaries) - 1):
        if boundaries[index] <= centre < boundaries[index + 1]:
            return index
    return 0 if centre < boundaries[0] else len(boundaries) - 2


def _split_line(line: list, boundaries: list) -> list:
    """Distribui as palavras de uma linha pelas colunas."""
    if len(boundaries) < 2:
        return [clean_text(" ".join(w["text"] for w in line))]
    cells = [[] for _ in range(len(boundaries) - 1)]
    for word in line:
        cells[_column_of(word["x0"], word["x1"], boundaries)].append(word["text"])
    return [clean_text(" ".join(c)) for c in cells]


# --------------------------------------------------------------------------
# Cabecalho, possivelmente em varias linhas
# --------------------------------------------------------------------------

def _is_laid_out_in_columns(line: list) -> bool:
    """Distingue uma linha de cabecalho de uma linha de prosa.

    Um titulo -- "Projeto de Sistemas de Telecomunicações - Pauta 2025/2026" --
    tem espacos normais entre todas as palavras. Uma linha de cabecalho tem
    pelo menos um intervalo largo, porque as palavras estao arrumadas por
    colunas. E a diferenca entre as duas, mesmo quando o titulo se espalha por
    cima de toda a tabela.
    """
    if len(line) < 2:
        return False
    return any(right["x0"] - left["x1"] >= _HEADER_GAP
               for left, right in zip(line, line[1:]))


def _header_band(lines: list, body_start: int, boundaries: list, limit: int = 6) -> list:
    """Linhas de cabecalho, subindo a partir do corpo da tabela.

    Para na primeira linha que ja e prosa -- um titulo, uma legenda -- em vez de
    cabecalho.
    """
    band: list = []
    for index in range(body_start - 1, max(body_start - limit - 1, -1), -1):
        line = lines[index]
        if not _is_laid_out_in_columns(line):
            break
        cells = _split_line(line, boundaries)
        if len([c for c in cells if c]) < 2:
            break
        if any(len(c.split()) >= _MAX_HEADER_WORDS for c in cells):
            break
        band.append(index)
    band.reverse()
    return band


def _merge_header(header_lines: list, boundaries: list) -> list:
    """Junta as varias linhas do cabecalho numa so, coluna a coluna."""
    width = max(len(boundaries) - 1, 1)
    parts = [[] for _ in range(width)]
    for line in header_lines:
        for index, cell in enumerate(_split_line(line, boundaries)):
            if cell:
                parts[index].append(cell)
    return [clean_text(" ".join(p)) for p in parts]


# --------------------------------------------------------------------------
# Texto solto (titulos e rodapes)
# --------------------------------------------------------------------------

def _drop_empty_columns(rows: list) -> list:
    """Deita fora as colunas onde nunca ninguem escreveu nada."""
    if not rows:
        return rows
    width = max(len(r) for r in rows)
    keep = [i for i in range(width)
            if any(r[i] for r in rows if i < len(r))]
    return [[r[i] if i < len(r) else "" for i in keep] for r in rows]


def _text_segments(lines: list) -> list:
    """Texto fora da tabela, partido nos espacos largos.

    Numa pauta o cabecalho da pagina costuma ter o nome da instituicao a
    esquerda e a legenda dos simbolos a direita, ambos na mesma linha visual.
    Juntar os dois estragava a deteccao da unidade curricular.
    """
    segments: list = []
    for line in lines:
        current: list = []
        previous_x1 = None
        for word in line:
            if previous_x1 is not None and word["x0"] - previous_x1 > _SEGMENT_GAP:
                segments.append(clean_text(" ".join(current)))
                current = []
            current.append(word["text"])
            previous_x1 = word["x1"]
        if current:
            segments.append(clean_text(" ".join(current)))
    return [s for s in segments if s]


# --------------------------------------------------------------------------
# Paginas continuadas
# --------------------------------------------------------------------------

def _merge_continuation_pages(tables: list) -> list:
    """Junta paginas seguidas que sao a continuacao da mesma tabela.

    A ultima pagina de uma pauta costuma ter menos alunos e, por isso, colunas
    que so la aparecem preenchidas -- as duas paginas acabam com numeros de
    colunas diferentes. Por isso a juncao alinha-se pelos nomes das colunas, e
    nao pela contagem.
    """
    if len(tables) <= 1:
        return tables
    merged = [tables[0]]
    for table in tables[1:]:
        prev = merged[-1]
        if _shares_header(prev.rows[0], table.rows[0]):
            _append_aligned(prev, table.rows[0], table.rows[1:])
            prev.location += f", {table.location.replace('página ', '')}"
        elif (len(table.rows[0]) == len(prev.rows[0])
              and not _looks_like_header(table.rows[0])):
            prev.rows.extend(table.rows)
            prev.location += f", {table.location.replace('página ', '')}"
        else:
            merged.append(table)
    return merged


def _shares_header(first: list, other: list) -> bool:
    """Duas paginas da mesma tabela repetem os nomes das colunas."""
    a = {c.strip().lower() for c in first if c.strip()}
    b = {c.strip().lower() for c in other if c.strip()}
    return len(a & b) >= 2


def _append_aligned(table: RawTable, header: list, rows: list) -> None:
    """Acrescenta linhas de outra pagina, encaixando-as pelo nome da coluna."""
    destino = {c.strip().lower(): i for i, c in enumerate(table.rows[0]) if c.strip()}
    mapping: dict = {}
    usados: set = set()
    for index, name in enumerate(header):
        key = name.strip().lower()
        if not key:
            continue
        if key in destino:
            mapping[index] = destino[key]
            usados.add(destino[key])

    for index, name in enumerate(header):
        key = name.strip().lower()
        if not key or index in mapping:
            continue
        # O nome nao bate certo: a extraccao da outra pagina pode ter juntado
        # duas colunas ("Nota desiste"). Nesse caso vale a posicao, e so se cria
        # uma coluna nova se a posicao ja estiver ocupada por outra coisa.
        if index < len(table.rows[0]) and index not in usados:
            mapping[index] = index
            usados.add(index)
            continue
        table.rows[0].append(name)
        for existing in table.rows[1:]:
            existing.append("")
        mapping[index] = len(table.rows[0]) - 1
        usados.add(mapping[index])

    width = len(table.rows[0])
    for row in rows:
        nova = [""] * width
        for index, value in enumerate(row):
            target = mapping.get(index)
            if target is not None:
                nova[target] = value
        table.rows.append(nova)


def _looks_like_header(row: list) -> bool:
    from ..detect import header_score
    return header_score(row) >= 2

"""Deteccao automatica: onde esta o cabecalho, o que e cada coluna, que UC e
que epoca, e o que fica por decidir (vira pergunta ao utilizador).

Nada aqui e definitivo: tudo o que se deduz vai com um nivel de confianca e
pode ser corrigido pelo utilizador na interface.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from .models import (
    EPOCA_1,
    EPOCA_2,
    EPOCA_ESP,
    KIND_COMPONENT,
    KIND_FINAL,
    ROLE_GRADE,
    ROLE_ID,
    ROLE_IGNORE,
    ROLE_NAME,
    Column,
    Guess,
    Question,
    RawTable,
    Source,
)
from .normalize import (
    clean_text,
    looks_like_person_name,
    norm_header,
    norm_text,
    parse_grade,
    parse_number,
    parse_student_id,
)

# --------------------------------------------------------------------------
# Vocabulario
# --------------------------------------------------------------------------

NAME_WORDS = ["nome", "aluno", "aluna", "estudante", "name", "student", "discente"]
ID_WORDS = ["numero", "num", "n", "no", "id", "codigo", "matricula", "mecanografico",
            "nmec", "istid", "ist id", "n aluno", "no aluno", "numero aluno"]

# Marcadores fortes: nomeiam a epoca sem margem para duvida.
STRONG_EPOCA = [
    (EPOCA_ESP, ["epoca especial", "especial", "ep especial", "3 epoca", "3a epoca",
                 "terceira epoca", "ee"]),
    (EPOCA_2, ["2 epoca", "2a epoca", "segunda epoca", "epoca 2", "recurso",
               "repescagem", "ep2", "2e", "epoca de recurso"]),
    (EPOCA_1, ["1 epoca", "1a epoca", "primeira epoca", "epoca 1", "epoca normal",
               "normal", "ep1", "1e", "epoca de exames"]),
]

# Marcadores fracos: sugerem uma epoca, mas tambem podem ser so componentes
# ("Exame 1" e "Exame 2" dentro da mesma epoca, por exemplo).
WEAK_EPOCA = [
    (EPOCA_ESP, ["teste 3", "exame 3", "prova 3", "3 teste", "3 exame", "3 prova",
                 "t3", "e3"]),
    (EPOCA_2, ["teste 2", "exame 2", "prova 2", "2 teste", "2 exame", "2 prova",
               "t2", "e2"]),
    (EPOCA_1, ["teste 1", "exame 1", "prova 1", "1 teste", "1 exame", "1 prova",
               "t1", "e1"]),
]

_DIGIT_EPOCA = {"1": EPOCA_1, "2": EPOCA_2, "3": EPOCA_ESP}

FINAL_WORDS = [
    "avaliacao final", "classificacao final", "nota final", "class final",
    "final", "nota", "classificacao", "avaliacao", "total", "media",
    "resultado", "pauta", "cf", "nf",
]

# Quanto mais alto, mais "oficial" e a coluna quando ha varias candidatas.
FINAL_PRIORITY = {
    "avaliacao final": 100, "classificacao final": 95, "class final": 95,
    "nota final": 90, "classificacao": 70, "avaliacao": 68, "nota": 65,
    "final": 60, "resultado": 55, "media": 45, "total": 40, "cf": 85, "nf": 85,
}

COMPONENT_WORDS = [
    "projeto", "projecto", "trabalho", "participacao", "presenca", "lab",
    "laboratorio", "exercicio", "ex", "quiz", "mini", "questao", "pergunta",
    "parte", "grupo", "relatorio", "defesa", "apresentacao", "frequencia",
    "teorica", "pratica", "tpc", "bonus", "moodle", "teste", "exame", "prova",
]

# Palavras que legitimam um numero final no cabecalho como indicador de epoca
# ("Nota Final 2" -> 2.a epoca), ao contrario de "Ex 2", que e so o exercicio 2.
EPOCA_DIGIT_CONTEXT = ["nota", "final", "avaliacao", "classificacao", "exame",
                       "teste", "prova", "epoca", "class", "cf", "nf"]

IGNORE_WORDS = ["obs", "observacoes", "notas obs", "comentario", "email", "turma",
                "curso", "ects", "estado", "situacao", "assinatura", "rubrica"]

_YEAR_RE = re.compile(r"(20\d{2})\s*[/\-–]\s*(20\d{2}|\d{2})")
_DATE_RE = re.compile(r"(20\d{2})[/\-.](\d{1,2})[/\-.](\d{1,2})|(\d{1,2})[/\-.](\d{1,2})[/\-.](20\d{2})")


def _has_word(header: str, words: list) -> Optional[str]:
    """Procura uma expressao do vocabulario num cabecalho normalizado."""
    tokens = header.split()
    for word in sorted(words, key=len, reverse=True):
        if " " in word:
            if word in header:
                return word
        elif word in tokens:
            return word
    return None


# --------------------------------------------------------------------------
# Cabecalho da tabela
# --------------------------------------------------------------------------

def header_score(row: list) -> int:
    """Quao provavel e que esta linha seja o cabecalho."""
    score = 0
    for cell in row:
        header = norm_header(cell)
        if not header:
            continue
        if _has_word(header, NAME_WORDS):
            score += 3
        if _has_word(header, ID_WORDS):
            score += 2
        if _has_word(header, FINAL_WORDS) or _has_word(header, COMPONENT_WORDS):
            score += 2
        for _, words in STRONG_EPOCA + WEAK_EPOCA:
            if _has_word(header, words):
                score += 1
                break
        if parse_number(cell) is not None:
            score -= 2
        if parse_student_id(cell):
            score -= 3
    return score


def find_header_row(rows: list) -> int:
    """Indice da linha de cabecalho, ou ``-1`` se a tabela nao tiver nenhum.

    Procura nas primeiras 12 linhas. Se nenhuma pontuar e a primeira ja for
    dados (um nome, um numero de aluno), a tabela nao tem cabecalho -- e comer
    a primeira linha perderia um aluno.
    """
    best_index, best = 0, -999
    for index, row in enumerate(rows[: min(len(rows), 12)]):
        score = header_score(row)
        # Empates resolvem-se a favor da linha mais acima.
        if score > best:
            best, best_index = score, index
    if best > 0:
        return best_index
    return -1 if _is_data_row(rows[0]) else 0


def _is_data_row(row: list) -> bool:
    for cell in row:
        text = clean_text(cell)
        if not text:
            continue
        if looks_like_person_name(text) or parse_student_id(text) or parse_number(text) is not None:
            return True
    return False


# --------------------------------------------------------------------------
# Colunas
# --------------------------------------------------------------------------

def _column_stats(values: list) -> dict:
    filled = [v for v in values if clean_text(v)]
    numbers = [parse_number(v) for v in filled]
    numbers = [n for n in numbers if n is not None]
    ids = [v for v in filled if parse_student_id(v)]
    names = [v for v in filled if looks_like_person_name(v)]

    # Celulas que sao nota mesmo sem serem numero: "RE", "NA", "-", ...
    statuses, dashes = 0, 0
    for value in filled:
        grade = parse_grade(value)
        if grade.value is not None:
            continue
        if grade.status == "SEM_NOTA":
            dashes += 1
        elif grade.status:
            statuses += 1

    total = max(len(values), 1)
    denom = max(len(filled), 1)
    return {
        "filled_ratio": len(filled) / total,
        "numeric_ratio": len(numbers) / denom,
        "status_ratio": statuses / denom,
        "dash_ratio": dashes / denom,
        "gradeish_ratio": (len(numbers) + statuses + dashes) / denom,
        "id_ratio": len(ids) / denom,
        "name_ratio": len(names) / denom,
        "max_value": max(numbers) if numbers else None,
        "min_value": min(numbers) if numbers else None,
        "distinct": len({clean_text(v) for v in filled}),
        "filled": len(filled),
        "numbers": len(numbers),
    }


def _guess_scale(max_value: Optional[float]) -> float:
    if max_value is None:
        return 20.0
    if max_value > 100:
        return max_value
    if max_value > 20:
        return 100.0
    return 20.0


def classify_columns(header_row: list, data_rows: list, file_epoca: Optional[str]) -> list:
    """Atribui papel, epoca e escala a cada coluna."""
    width = max([len(header_row)] + [len(r) for r in data_rows] or [0])
    columns = []

    for index in range(width):
        header = clean_text(header_row[index]) if index < len(header_row) else ""
        values = [row[index] if index < len(row) else "" for row in data_rows]
        stats = _column_stats(values)
        column = Column(
            index=index,
            header=header or f"Coluna {index + 1}",
            numeric_ratio=stats["numeric_ratio"],
            filled_ratio=stats["filled_ratio"],
            max_value=stats["max_value"],
            samples=[clean_text(v) for v in values if clean_text(v)][:5],
        )
        columns.append(_classify_one(column, norm_header(header), stats))

    _pick_name_and_id(columns, data_rows)
    _assign_epocas(columns, file_epoca)
    _pick_final_columns(columns)
    return columns


def _classify_one(column: Column, header: str, stats: dict) -> Column:
    """Papel de uma coluna, a partir do cabecalho e da forma dos dados."""
    if stats["filled"] == 0:
        column.role = ROLE_IGNORE
        column.reason = "coluna vazia"
        column.confidence = 0.9
        return column

    if _has_word(header, IGNORE_WORDS):
        column.role = ROLE_IGNORE
        column.reason = f"cabeçalho «{column.header}» não é uma nota"
        column.confidence = 0.7
        return column

    if _has_word(header, NAME_WORDS) and stats["numeric_ratio"] < 0.5:
        column.role = ROLE_NAME
        column.confidence = 0.95
        column.reason = "cabeçalho indica nome"
        return column

    if _has_word(header, ID_WORDS) and stats["id_ratio"] > 0.5:
        column.role = ROLE_ID
        column.confidence = 0.95
        column.reason = "cabeçalho indica número de aluno"
        return column

    if stats["name_ratio"] >= 0.7:
        column.role = ROLE_NAME
        column.confidence = 0.8
        column.reason = "os valores parecem nomes de pessoas"
        return column

    if stats["id_ratio"] >= 0.8 and stats["distinct"] >= max(2, stats["filled"] - 2):
        column.role = ROLE_ID
        column.confidence = 0.8
        column.reason = "os valores parecem números de aluno"
        return column

    if stats["numeric_ratio"] >= 0.4 or _looks_like_grade_column(column, stats):
        pass
    else:
        column.role = ROLE_IGNORE
        column.reason = "não parece nome, número nem nota"
        column.confidence = 0.4
        return column

    if True:
        column.role = ROLE_GRADE
        column.scale = _guess_scale(stats["max_value"])
        matched_final = _has_word(header, FINAL_WORDS)
        matched_comp = _has_word(header, COMPONENT_WORDS)
        if epoca_from_text(column.header, strong_only=True)[0] and not matched_comp:
            # Um cabecalho que e so o nome da epoca ("2.ª Época") guarda a nota
            # dessa epoca, nao um componente dela.
            column.kind = KIND_FINAL
            column.confidence = 0.75
            column.reason = f"«{column.header}» é a nota da época"
        elif matched_final and (not matched_comp or len(matched_final) >= len(matched_comp)):
            column.kind = KIND_FINAL
            column.confidence = 0.8
            column.reason = f"cabeçalho «{column.header}» indica nota final"
        else:
            column.kind = KIND_COMPONENT
            column.confidence = 0.6 if matched_comp else 0.4
            column.reason = f"cabeçalho «{column.header}» indica componente"
        return column

    column.role = ROLE_IGNORE
    column.reason = "não parece nome, número nem nota"
    column.confidence = 0.4
    return column


def _looks_like_grade_column(column: Column, stats: dict) -> bool:
    """Colunas cheias de "RE"/"NA"/"-" tambem sao colunas de notas."""
    if stats["numeric_ratio"] + stats["status_ratio"] >= 0.5:
        return True
    header = norm_header(column.header)
    header_is_gradeish = bool(
        _has_word(header, FINAL_WORDS)
        or _has_word(header, COMPONENT_WORDS)
        or epoca_from_text(column.header)[0]
    )
    # Cabecalho de nota + celulas todas numero/estado/traco (ex.: coluna da
    # 2.a epoca so com "-" para quem nao foi a ela).
    return header_is_gradeish and stats["gradeish_ratio"] >= 0.95 and stats["filled"] > 0


def _pick_name_and_id(columns: list, data_rows: list) -> None:
    """Garante exactamente uma coluna de nome e no maximo uma de numero."""
    names = [c for c in columns if c.role == ROLE_NAME]
    if len(names) > 1:
        best = max(names, key=lambda c: (c.confidence, len(" ".join(c.samples))))
        for column in names:
            if column is not best:
                column.role = ROLE_IGNORE
                column.reason = "outra coluna foi escolhida como nome"
    elif not names:
        # Sem cabecalho util: usa a coluna com mais texto tipo nome.
        best, best_ratio = None, 0.0
        for column in columns:
            values = [r[column.index] if column.index < len(r) else "" for r in data_rows]
            ratio = _column_stats(values)["name_ratio"]
            if ratio > best_ratio:
                best, best_ratio = column, ratio
        if best is not None and best_ratio >= 0.4:
            best.role = ROLE_NAME
            best.confidence = 0.5
            best.reason = "coluna com mais texto parecido com nomes"

    ids = [c for c in columns if c.role == ROLE_ID]
    if len(ids) > 1:
        best = max(ids, key=lambda c: c.confidence)
        for column in ids:
            if column is not best:
                column.role = ROLE_GRADE if column.numeric_ratio > 0.8 else ROLE_IGNORE
                column.reason = "outra coluna foi escolhida como número de aluno"


def epoca_from_text(text: str, strong_only: bool = False):
    """Devolve ``(epoca, forca)`` a partir de um texto qualquer."""
    header = norm_header(text)
    if not header:
        return None, None
    for epoca, words in STRONG_EPOCA:
        if _has_word(header, words):
            return epoca, "strong"
    if strong_only:
        return None, None
    for epoca, words in WEAK_EPOCA:
        if _has_word(header, words):
            return epoca, "weak"
    # "Nota Final 2" -> 2.a epoca; "Ex 2" -> so o exercicio 2, nao uma epoca.
    tokens = header.split()
    if len(tokens) >= 2 and tokens[-1] in _DIGIT_EPOCA:
        if _has_word(" ".join(tokens[:-1]), EPOCA_DIGIT_CONTEXT):
            return _DIGIT_EPOCA[tokens[-1]], "weak"
    return None, None


def _assign_epocas(columns: list, file_epoca: Optional[str]) -> None:
    """Distribui as colunas de nota pelas epocas.

    Regras:
    - marcador forte no cabecalho manda sempre;
    - se o ficheiro/folha ja identifica a epoca, marcadores fracos ("Exame 2")
      sao tratados como componentes da mesma epoca, nao como outra epoca;
    - sem epoca de ficheiro, um marcador fraco abre um bloco: as colunas
      seguintes sem marcador pertencem a esse bloco.
    """
    current = None
    for column in columns:
        if column.role != ROLE_GRADE:
            continue
        epoca, strength = epoca_from_text(column.header)
        if strength == "strong":
            current = epoca
            column.epoca = epoca
            column.confidence = max(column.confidence, 0.9)
        elif strength == "weak" and file_epoca is None:
            current = epoca
            column.epoca = epoca
            column.confidence = max(column.confidence, 0.6)
        else:
            column.epoca = current or file_epoca

    # Colunas antes do primeiro marcador ficam com a epoca do ficheiro (ou None).
    for column in columns:
        if column.role == ROLE_GRADE and column.epoca is None:
            column.epoca = file_epoca


def _final_priority(header: str) -> int:
    header = norm_header(header)
    best = 0
    for word, priority in FINAL_PRIORITY.items():
        if _has_word(header, [word]):
            best = max(best, priority)
    return best


def _pick_final_columns(columns: list) -> None:
    """Uma nota final por epoca; as outras candidatas passam a componentes."""
    by_epoca: dict = {}
    for column in columns:
        if column.role == ROLE_GRADE:
            by_epoca.setdefault(column.epoca, []).append(column)

    has_epoca_final = any(
        c.kind == KIND_FINAL for e, g in by_epoca.items() if e is not None for c in g
    )

    for epoca, group in by_epoca.items():
        if any(c.locked for c in group):
            # O utilizador já decidiu este bloco: mexer nele desfazia a escolha.
            continue
        if epoca is None and has_epoca_final:
            # Colunas fora de qualquer bloco de epoca (ex.: "Projeto" antes de
            # "Teste 1") sao componentes partilhados, nunca a nota final.
            for column in group:
                column.kind = KIND_COMPONENT
                column.reason = "componente comum a todas as épocas"
            continue

        candidates = [c for c in group if c.kind == KIND_FINAL]
        if not candidates:
            # Sem candidata obvia: a ultima coluna do bloco costuma ser a nota
            # final. Prefere-se uma com numeros, mas um bloco so com "RE"/"NA"
            # tambem tem de dar uma nota. Fica com confianca baixa (gera pergunta).
            numeric = [c for c in group if c.numeric_ratio > 0.3] or group
            if numeric:
                chosen = numeric[-1]
                chosen.kind = KIND_FINAL
                chosen.confidence = min(chosen.confidence, 0.35)
                chosen.reason = "última coluna numérica do bloco (palpite)"
            continue
        best = max(candidates, key=lambda c: (_final_priority(c.header), c.index))
        for column in candidates:
            if column is not best and not column.locked:
                column.kind = KIND_COMPONENT
                column.reason = f"«{best.header}» foi escolhida como nota final"
        best.kind = KIND_FINAL
        if len(candidates) > 1:
            # Havia mais do que uma hipotese: convem confirmar.
            best.confidence = min(best.confidence, 0.55)


# --------------------------------------------------------------------------
# UC, ano lectivo e data do documento
# --------------------------------------------------------------------------

_SUBJECT_NOISE = re.compile(
    r"\b(pauta|pautas|notas|nota|avaliacao|avaliacoes|classificacoes|classificacao|"
    r"epoca|epocas|exame|exames|final|finais|resultados|lista|listagem|"
    r"1e|2e|ee|v\d+|versao|versao\d+|20\d{2}|\d{2})\b",
    re.IGNORECASE,
)


def guess_subject(filename: str, table: RawTable) -> Guess:
    """Tenta descobrir a unidade curricular (titulo do documento > ficheiro)."""
    for line in table.title_lines[:3]:
        text = clean_text(line)
        if not text or len(text) < 6:
            continue
        match = re.split(r"\s+[-–—]\s+|\s{2,}\|\s{2,}", text)
        candidate = clean_text(match[0])
        low = norm_text(candidate)
        if len(candidate) >= 6 and not low.startswith(("pauta", "nota", "avaliacao", "folha")):
            if _YEAR_RE.search(candidate):
                candidate = clean_text(_YEAR_RE.sub("", candidate)).strip("-–— ")
            if len(candidate) >= 6:
                return Guess(candidate, 0.85, f"título do documento: «{text[:70]}»")

    if table.sheet_name:
        cleaned = _clean_subject_token(table.sheet_name.replace("_", " ").replace("-", " "))
        if cleaned and len(cleaned) >= 4 and not norm_text(cleaned).startswith("sheet"):
            return Guess(cleaned, 0.35, f"nome da folha: «{table.sheet_name}»")

    stem = os.path.splitext(os.path.basename(filename))[0]
    acronym = _acronym_from(stem)
    if acronym:
        return Guess(acronym, 0.5, f"sigla no nome do ficheiro: «{stem}»")

    cleaned = _clean_subject_token(stem.replace("_", " ").replace("-", " "))
    if cleaned and len(cleaned) >= 4:
        return Guess(cleaned, 0.3, f"nome do ficheiro: «{stem}»")

    return Guess(None, 0.0, "não foi possível identificar a UC")


def _acronym_from(stem: str) -> Optional[str]:
    """Siglas tipo "SCSFM" em Pauta_SCSFM_2025_2026_1E."""
    for token in re.split(r"[\s_\-.]+", stem):
        if 2 <= len(token) <= 8 and token.isupper() and token.isalpha():
            if norm_text(token) not in {"pauta", "notas", "uc", "ist"}:
                return token
    return None


#: Palavras que sobram da limpeza mas nao identificam nenhuma UC.
_SUBJECT_STOPWORDS = {
    "de", "da", "do", "das", "dos", "e", "a", "o", "as", "os", "em",
    "primeira", "segunda", "terceira", "especial", "normal", "recurso",
    "aluno", "alunos", "students", "student", "folha", "sheet", "geral",
    "dados", "copia", "copy", "sem", "titulo", "novo", "nova", "ficheiro",
    "numero", "numeros", "com", "sheet1", "folha1", "tabela", "turma",
}


def _clean_subject_token(text: str):
    """Limpa um nome de ficheiro/folha; devolve None se nao sobrar nada util."""
    text = _SUBJECT_NOISE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" -–—_")
    if not text:
        return None
    words = [w for w in text.split() if norm_text(w) not in _SUBJECT_STOPWORDS]
    if not words or not any(len(w) >= 3 for w in words):
        return None
    return " ".join(words)


def guess_year(filename: str, table: RawTable) -> Guess:
    haystacks = table.title_lines + table.footer_lines + [os.path.basename(filename)]
    for text in haystacks:
        match = _YEAR_RE.search(clean_text(text))
        if match:
            start, end = match.group(1), match.group(2)
            if len(end) == 2:
                end = start[:2] + end
            return Guess(f"{start}/{end}", 0.8, f"encontrado em «{clean_text(text)[:60]}»")
    return Guess(None, 0.0, "")


def guess_document_date(table: RawTable) -> Optional[str]:
    """Data impressa no documento -- usada para desempatar versoes da mesma pauta."""
    for text in reversed(table.footer_lines[-4:] + table.title_lines[:2]):
        match = _DATE_RE.search(clean_text(text))
        if match:
            if match.group(1):
                year, month, day = match.group(1), match.group(2), match.group(3)
            else:
                day, month, year = match.group(4), match.group(5), match.group(6)
            try:
                return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
            except ValueError:
                return None
    return None


def guess_file_epoca(filename: str, table: RawTable):
    """Epoca ao nivel do ficheiro/folha (nome do ficheiro, folha ou titulo)."""
    for text, label, strong_only in (
        (os.path.basename(filename), "nome do ficheiro", False),
        (table.sheet_name, "nome da folha", False),
        (" ".join(table.title_lines[:2]), "título do documento", True),
    ):
        epoca, strength = epoca_from_text(text, strong_only=strong_only)
        if epoca:
            confidence = 0.85 if strength == "strong" else 0.5
            return epoca, Guess(epoca, confidence, f"{label}: «{clean_text(text)[:60]}»")
    return None, Guess(None, 0.0, "")


# --------------------------------------------------------------------------
# Construcao da Source
# --------------------------------------------------------------------------

def build_source(source_id: str, filename: str, kind: str, table: RawTable,
                 file_order: int = 0) -> Source:
    """Passa de uma tabela em bruto para uma Source classificada."""
    header_index = find_header_row(table.rows)
    if header_index < 0:
        header_row = []
        data_rows = [r for r in table.rows if any(clean_text(c) for c in r)]
    else:
        header_row = table.rows[header_index]
        data_rows = [r for r in table.rows[header_index + 1 :]
                     if any(clean_text(c) for c in r)]

    # Linhas de rodape ("Total", "Média", assinaturas) nao sao alunos.
    data_rows = [r for r in data_rows if not _is_footer_row(r)]

    file_epoca, epoca_guess = guess_file_epoca(filename, table)
    columns = classify_columns(header_row, data_rows, file_epoca)

    source = Source(
        id=source_id,
        filename=filename,
        kind=kind,
        location=table.location,
        subject=guess_subject(filename, table),
        academic_year=guess_year(filename, table),
        document_date=guess_document_date(table),
        columns=columns,
        data_rows=data_rows,
        header_row=[clean_text(c) for c in header_row],
        file_order=file_order,
    )
    if epoca_guess.value:
        source.notes.append(f"Época sugerida pelo ficheiro: {epoca_guess.reason}")
    return source


_FOOTER_TOKENS = {"total", "media", "média", "resumo", "aprovados", "reprovados",
                  "docente", "assinatura", "obs", "observacoes"}


def _is_footer_row(row: list) -> bool:
    cells = [clean_text(c) for c in row if clean_text(c)]
    if not cells:
        return True
    first = norm_text(cells[0])
    return first in _FOOTER_TOKENS and len(cells) <= 3


# --------------------------------------------------------------------------
# Perguntas ao utilizador
# --------------------------------------------------------------------------

SUBJECT_CONFIDENT = 0.6
EPOCA_CONFIDENT = 0.6
FINAL_CONFIDENT = 0.6


def build_questions(sources: list) -> list:
    """Tudo o que ficou por decidir vira uma pergunta."""
    questions: list = []
    known_subjects = sorted(
        {s.subject.value for s in sources if s.subject.value and s.subject.confidence >= SUBJECT_CONFIDENT}
    )

    for source in sources:
        if not source.subject.value or source.subject.confidence < SUBJECT_CONFIDENT:
            options = [{"value": s, "label": s} for s in known_subjects]
            if source.subject.value and source.subject.value not in known_subjects:
                options.insert(0, {"value": source.subject.value,
                                   "label": source.subject.value,
                                   "hint": source.subject.reason})
            questions.append(Question(
                id=f"{source.id}:subject",
                type="subject",
                source_id=source.id,
                title=f"Qual é a unidade curricular de «{source.label}»?",
                detail=source.subject.reason or "Não há nada no ficheiro que identifique a UC.",
                options=options,
                default=source.subject.value,
                allow_custom=True,
                severity="warning" if not source.subject.value else "info",
            ))

        grade_columns = source.grade_columns()
        finals = [c for c in grade_columns if c.kind == KIND_FINAL]

        if grade_columns and not finals:
            questions.append(Question(
                id=f"{source.id}:final",
                type="final_column",
                source_id=source.id,
                title=f"Qual é a coluna com a nota final em «{source.label}»?",
                detail="Nenhuma coluna se identificou claramente como nota final.",
                options=[{"value": str(c.index), "label": c.header,
                          "hint": ", ".join(c.samples[:3])} for c in grade_columns],
                default=str(grade_columns[-1].index),
                severity="warning",
            ))

        for column in finals:
            if column.confidence < FINAL_CONFIDENT and len(grade_columns) > 1:
                questions.append(Question(
                    id=f"{source.id}:final:{column.epoca or 'na'}",
                    type="final_column",
                    source_id=source.id,
                    column_index=column.index,
                    title=f"Em «{source.label}», qual coluna conta como nota final"
                          + (f" da {_epoca_label(column.epoca)}?" if column.epoca else "?"),
                    detail="Há mais do que uma coluna com ar de nota final.",
                    options=[{"value": str(c.index), "label": c.header,
                              "hint": ", ".join(c.samples[:3])}
                             for c in grade_columns if c.epoca == column.epoca],
                    default=str(column.index),
                ))

        unknown_epoca = [c for c in grade_columns if c.epoca is None and c.kind == KIND_FINAL]
        if unknown_epoca:
            questions.append(Question(
                id=f"{source.id}:epoca",
                type="epoca",
                source_id=source.id,
                title=f"A que época correspondem as notas de «{source.label}»?",
                detail="Colunas sem época identificada: "
                       + ", ".join(f"«{c.header}»" for c in unknown_epoca),
                options=[
                    {"value": EPOCA_1, "label": "1.ª Época"},
                    {"value": EPOCA_2, "label": "2.ª Época"},
                    {"value": EPOCA_ESP, "label": "Época Especial"},
                    {"value": "component",
                     "label": "Não é uma época — é só um componente",
                     "hint": "A coluna passa a contar como componente, sem nota final própria."},
                ],
                default=EPOCA_1,
                severity="warning",
            ))

        for column in grade_columns:
            if column.kind == KIND_FINAL and column.max_value is not None:
                if column.max_value <= 10 and column.scale == 20:
                    questions.append(Question(
                        id=f"{source.id}:scale:{column.index}",
                        type="scale",
                        source_id=source.id,
                        column_index=column.index,
                        title=f"«{column.header}» em «{source.label}» está em que escala?",
                        detail=f"O valor mais alto é {column.max_value:g}, "
                               "o que tanto pode ser uma escala 0-20 como 0-10.",
                        options=[
                            {"value": "20", "label": "0 a 20"},
                            {"value": "10", "label": "0 a 10"},
                            {"value": "100", "label": "0 a 100"},
                        ],
                        default="20",
                    ))
    return questions


def _epoca_label(epoca: Optional[str]) -> str:
    from .models import EPOCA_LABELS
    return EPOCA_LABELS.get(epoca or "", "época desconhecida")


def apply_answers(sources: list, answers: dict) -> None:
    """Aplica as respostas do utilizador as Sources (mutacao no sitio)."""
    by_id = {s.id: s for s in sources}
    for question_id, value in (answers or {}).items():
        if value in (None, ""):
            continue
        parts = question_id.split(":")
        source = by_id.get(parts[0])
        if source is None or len(parts) < 2:
            continue
        kind = parts[1]

        if kind == "subject":
            source.subject = Guess(clean_text(value), 1.0, "definido pelo utilizador")
        elif kind == "epoca":
            for column in source.grade_columns():
                if column.epoca is not None:
                    continue
                if value == "component":
                    column.kind = KIND_COMPONENT
                    column.reason = "marcado como componente pelo utilizador"
                else:
                    column.epoca = value
                    column.reason = "época definida pelo utilizador"
                column.confidence = 1.0
                column.locked = True
        elif kind == "final":
            try:
                chosen_index = int(value)
            except (TypeError, ValueError):
                continue
            chosen = next((c for c in source.columns if c.index == chosen_index), None)
            if chosen is None:
                continue
            for column in source.grade_columns():
                if column.epoca == chosen.epoca and column is not chosen:
                    column.kind = KIND_COMPONENT
                    column.locked = True
            chosen.role = ROLE_GRADE
            chosen.kind = KIND_FINAL
            chosen.confidence = 1.0
            chosen.locked = True
            chosen.reason = "nota final definida pelo utilizador"
        elif kind == "scale":
            try:
                column_index = int(parts[2])
                scale = float(value)
            except (TypeError, ValueError, IndexError):
                continue
            for column in source.columns:
                if column.index == column_index:
                    column.scale = scale


def apply_column_overrides(sources: list, overrides: dict) -> None:
    """Correccoes manuais de colunas vindas da interface.

    ``overrides`` = ``{source_id: {column_index: {role, epoca, kind, scale}}}``
    """
    by_id = {s.id: s for s in sources}
    for source_id, columns in (overrides or {}).items():
        source = by_id.get(source_id)
        if source is None:
            continue
        for raw_index, spec in (columns or {}).items():
            try:
                index = int(raw_index)
            except (TypeError, ValueError):
                continue
            column = next((c for c in source.columns if c.index == index), None)
            if column is None:
                continue
            if spec.get("role"):
                column.role = spec["role"]
            if "epoca" in spec:
                column.epoca = spec["epoca"] or None
            if spec.get("kind"):
                column.kind = spec["kind"]
            if spec.get("scale"):
                try:
                    column.scale = float(spec["scale"])
                except (TypeError, ValueError):
                    pass
            column.confidence = 1.0
            column.locked = True
            column.reason = "definido pelo utilizador"

    for source in sources:
        _pick_final_columns(source.columns)

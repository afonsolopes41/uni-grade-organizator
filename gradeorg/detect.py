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
    EPOCA_LABELS,
    EPOCAS,
    KIND_COMPONENT,
    KIND_FINAL,
    ROLE_GRADE,
    ROLE_ID,
    ROLE_IGNORE,
    ROLE_NAME,
    ROUTE_CONTINUA,
    ROUTE_EXAME,
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
    split_glued,
)

# --------------------------------------------------------------------------
# Vocabulario
# --------------------------------------------------------------------------

NAME_WORDS = ["nome", "aluno", "aluna", "estudante", "name", "student", "discente",
              "student name", "full name"]
ID_WORDS = ["numero", "num", "n", "no", "id", "codigo", "matricula", "mecanografico",
            "nmec", "istid", "ist id", "n aluno", "no aluno", "numero aluno",
            "number", "student number", "student id", "reg", "registration"]

# Marcadores fortes: nomeiam a epoca sem margem para duvida.
STRONG_EPOCA = [
    (EPOCA_ESP, ["epoca especial", "especial", "ep especial", "3 epoca", "3a epoca",
                 "terceira epoca", "ee",
                 "special season", "special sitting", "special period", "3rd season"]),
    (EPOCA_2, ["2 epoca", "2a epoca", "segunda epoca", "epoca 2", "recurso",
               "repescagem", "ep2", "2e", "epoca de recurso",
               "2nd season", "second season", "resit", "resit season",
               "2nd sitting", "supplementary", "season 2"]),
    (EPOCA_1, ["1 epoca", "1a epoca", "primeira epoca", "epoca 1", "epoca normal",
               "normal", "ep1", "1e", "epoca de exames",
               "1st season", "first season", "normal season", "1st sitting",
               "season 1", "regular season"]),
]

# Marcadores fracos: sugerem uma epoca, mas tambem podem ser so componentes
# ("Exame 1" e "Exame 2" dentro da mesma epoca, por exemplo).
# Marcadores fracos: so o *primeiro* momento de avaliacao identifica a epoca
# sem ambiguidade -- um "Teste 1" so existe na avaliacao continua, que e sempre
# 1.a epoca. Um "Teste 2" nao diz nada: tanto pode ser o segundo teste dessa
# mesma epoca (feito no dia do exame) como a 2.a epoca. Esse caso e decidido
# pelos dados em _resolve_moments, e confirmado pelo utilizador.
WEAK_EPOCA = [
    (EPOCA_1, ["teste 1", "exame 1", "prova 1", "frequencia 1",
               "1 teste", "1 exame", "1 prova", "t1", "e1"]),
]

#: Palavras que, com um "2" ou "3" ao lado, indicam um momento de avaliacao
#: posterior ("Nota Final 2"), ao contrario de "Ex 2", que e o exercicio 2.
_MOMENT_WORDS = {"teste", "exame", "prova", "frequencia", "nota", "final",
                 "avaliacao", "classificacao", "class", "nf", "cf", "epoca"}

_EXAM_WORDS = ["exame", "recurso", "prova"]
_CONTINUA_WORDS = ["teste", "frequencia", "continua", "mini", "projeto",
                   "projecto", "trabalho", "participacao"]

FINAL_WORDS = [
    "avaliacao final", "classificacao final", "nota final", "class final",
    "final", "nota", "classificacao", "avaliacao", "total", "media",
    "resultado", "pauta", "cf", "nf",
    # Pautas em ingles.
    "final grade", "final mark", "overall grade", "grade", "mark", "marks",
    "result", "overall", "average", "final result",
]

# Quanto mais alto, mais "oficial" e a coluna quando ha varias candidatas.
FINAL_PRIORITY = {
    "avaliacao final": 100, "classificacao final": 95, "class final": 95,
    "nota final": 90, "classificacao": 70, "avaliacao": 68, "nota": 65,
    "final": 60, "resultado": 55, "media": 45, "total": 40, "cf": 85, "nf": 85,
    "final grade": 100, "final mark": 98, "overall grade": 95, "final result": 95,
    "grade": 88, "mark": 80, "marks": 80, "overall": 70, "result": 62,
    "average": 45,
}

COMPONENT_WORDS = [
    "projeto", "projecto", "trabalho", "participacao", "presenca", "lab",
    "laboratorio", "exercicio", "ex", "quiz", "mini", "questao", "pergunta",
    "parte", "grupo", "relatorio", "defesa", "apresentacao", "frequencia",
    "teorica", "pratica", "tpc", "bonus", "moodle", "teste", "exame", "prova",
    # Pautas em ingles.
    "test", "exam", "lab", "labs", "laboratory", "laboratories", "quiz",
    "assignment", "homework", "attendance", "participation", "max", "midterm",
    "project", "report", "presentation", "coursework", "practical", "theory",
]



IGNORE_WORDS = ["obs", "observacoes", "notas obs", "comentario", "email", "turma",
                "curso", "ects", "estado", "situacao", "assinatura", "rubrica",
                "date", "data", "comments", "remarks", "signature", "class",
                "group", "status", "programme", "course", "year"]

_YEAR_RE = re.compile(r"(20\d{2})\s*[/\-–]\s*(20\d{2}|\d{2})")
_DATE_RE = re.compile(r"(20\d{2})[/\-.](\d{1,2})[/\-.](\d{1,2})|(\d{1,2})[/\-.](\d{1,2})[/\-.](20\d{2})")


def _has_word(header: str, words: list) -> Optional[str]:
    """Procura uma expressao do vocabulario num cabecalho normalizado.

    Olha tambem para a forma com letras e digitos separados, porque ha pautas
    que escrevem "Test 1" e outras "Test1".
    """
    variants = [header]
    glued = split_glued(header)
    if glued != header:
        variants.append(glued)

    for variant in variants:
        tokens = variant.split()
        padded = f" {variant} "
        for word in sorted(words, key=len, reverse=True):
            if " " in word:
                # Palavras inteiras: "semester 1" nao pode casar dentro de
                # "semester 1st season", que e o 2.o semestre.
                if f" {word} " in padded:
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
    _assign_epocas(columns, file_epoca, data_rows)
    _compute_clusters(columns, data_rows)
    _pick_final_columns(columns)
    return columns


def _compute_clusters(columns: list, data_rows: list) -> None:
    """Agrupa as colunas de notas de cada epoca por via de avaliacao.

    Duas colunas preenchidas para os *mesmos* alunos sao a mesma nota escrita de
    duas maneiras ("Nota Final" e "Avaliação Final"). Duas colunas preenchidas
    para alunos *diferentes* sao vias alternativas -- avaliacao continua ou
    exame de 1.a epoca -- e cada aluno so faz uma delas, por isso contam ambas.
    """
    grades = [c for c in columns if c.role == ROLE_GRADE]
    # So as candidatas a nota final entram no agrupamento: uma coluna
    # preenchida para a turma toda ("Teste 1") ligaria por transitividade duas
    # vias que na verdade sao disjuntas.
    finals = [c for c in grades if c.kind == KIND_FINAL]
    filled = {}
    for column in finals:
        filled[column.index] = {
            index for index, row in enumerate(data_rows)
            if not parse_grade(_cell(row, column.index), scale=column.scale).is_empty
        }

    parent = {c.index: c.index for c in grades}

    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for position, left in enumerate(finals):
        for right in finals[position + 1 :]:
            if left.epoca != right.epoca:
                continue
            a, b = filled[left.index], filled[right.index]
            if not a or not b:
                continue
            if len(a & b) / len(a | b) >= 0.5:
                parent[find(right.index)] = find(left.index)

    for column in grades:
        column.cluster = find(column.index)


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
        elif matched_final:
            # "Nota Exame" e a nota da via de exame; "Nota Trabalho" tambem entra
            # como candidata, mas perde para "Nota Final" na escolha seguinte.
            column.kind = KIND_FINAL
            column.confidence = 0.8 if not matched_comp else 0.55
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
    return None, None


def moment_index(header: str):
    """Numero do momento de avaliacao no cabecalho, se houver.

    ``"Teste 2"`` e ``"Nota Final 2"`` devolvem 2; ``"Ex 2"`` devolve None,
    porque ai o 2 e o numero do exercicio, nao do momento.
    """
    tokens = split_glued(norm_header(header)).split()
    for position, token in enumerate(tokens):
        if token in ("2", "3"):
            rest = set(tokens[:position] + tokens[position + 1 :])
            if rest & _MOMENT_WORDS:
                return int(token)
    return None


def route_of(header: str):
    """Modalidade sugerida pelo cabecalho: exame ou avaliacao continua."""
    normalized = norm_header(header)
    if _has_word(normalized, _EXAM_WORDS):
        return ROUTE_EXAME
    if _has_word(normalized, _CONTINUA_WORDS):
        return ROUTE_CONTINUA
    return None


def _assign_epocas(columns: list, file_epoca: Optional[str], data_rows: list) -> None:
    """Reparte as colunas de nota por blocos e atribui uma epoca a cada bloco.

    Um bloco e um momento de avaliacao. O primeiro e sempre a 1.a epoca. Um
    marcador forte ("2.ª Época", "Recurso") abre um bloco com epoca conhecida.
    Um "Teste 2" ou "Nota Final 2" abre um bloco cuja epoca *nao* se sabe: tanto
    pode ser o segundo teste da mesma epoca -- que se faz no dia do exame --
    como a 2.a epoca. Isso decide-se olhando para quem tem nota la.
    """
    grade_columns = [c for c in columns if c.role == ROLE_GRADE]
    if not grade_columns:
        return

    base = {"moment": 1, "epoca": file_epoca, "strong": file_epoca is not None,
            "columns": []}
    blocks = [base]
    current = base
    # Colunas do primeiro bloco anteriores a qualquer marcador ("Projeto" antes
    # de "Teste 1"): sao componentes comuns, contam para todas as epocas.
    shared: list = []

    for column in grade_columns:
        epoca, strength = epoca_from_text(column.header)
        moment = moment_index(column.header)

        if strength == "strong":
            current = {"moment": None, "epoca": epoca, "strong": True, "columns": []}
            blocks.append(current)
        elif moment and file_epoca is None and current["moment"] != moment:
            # "Teste 2", "Nota Final 2" e "Avaliação Final 2" sao o mesmo
            # momento: so a primeira abre o bloco.
            current = {"moment": moment, "epoca": None, "strong": False, "columns": []}
            blocks.append(current)
        elif strength == "weak" and current["epoca"] is None:
            # "Teste 1" so existe na avaliacao continua: e 1.a epoca.
            current["epoca"] = epoca
        elif current is base and current["epoca"] is None:
            shared.append(column)

        current["columns"].append(column)
        column.moment = current["moment"]

    _resolve_moments(blocks, data_rows)

    # So faz sentido falar de componente comum se houver mais do que uma epoca.
    epocas_encontradas = {b["epoca"] for b in blocks if b["epoca"]}
    if len(epocas_encontradas) < 2:
        shared = []

    for block in blocks:
        for column in block["columns"]:
            if column in shared:
                column.epoca = None
                column.route = column.route or route_of(column.header)
                continue
            column.epoca = block["epoca"]
            column.route = column.route or route_of(column.header) or block.get("route")
            if block["epoca"] in (EPOCA_2, EPOCA_ESP):
                # A 2.a epoca e a especial sao sempre exame.
                column.route = ROUTE_EXAME
            if block.get("evidence"):
                column.evidence = block["evidence"]


def _resolve_moments(blocks: list, data_rows: list) -> None:
    """Decide a epoca dos blocos que so dizem "momento 2" ou "momento 3"."""
    for position, block in enumerate(blocks):
        if block["epoca"] is not None or block["moment"] in (None, 1):
            continue

        previous = _previous_decided(blocks, position)
        verdict, evidence = _moment_verdict(previous, block, data_rows)
        block["evidence"] = evidence
        if verdict == "continua":
            block["epoca"] = previous["epoca"] or EPOCA_1
            block["route"] = ROUTE_CONTINUA
        else:
            block["epoca"] = _next_epoca(previous["epoca"] or EPOCA_1)
            block["route"] = ROUTE_EXAME

    # O primeiro bloco, se nada o identificou, e a 1.a epoca -- e sempre o
    # primeiro momento de avaliacao do ano.
    for block in blocks:
        if block["epoca"] is None and block["moment"] == 1 and len(blocks) > 1:
            block["epoca"] = EPOCA_1


def _previous_decided(blocks: list, position: int) -> dict:
    for block in reversed(blocks[:position]):
        if block["epoca"] is not None or block["moment"] == 1:
            return block
    return blocks[0]


def _next_epoca(epoca: str) -> str:
    if epoca not in EPOCAS:
        return EPOCA_2
    return EPOCAS[min(EPOCAS.index(epoca) + 1, len(EPOCAS) - 1)]


def _moment_verdict(previous: dict, block: dict, data_rows: list):
    """Olha para os dados: quem tem nota neste segundo momento?

    Se so la aparecem os alunos que chumbaram no primeiro, e recurso -- ou seja,
    outra epoca. Se aparece la a turma quase toda, e o segundo teste da mesma
    epoca. Devolve ``(veredicto, texto da evidencia)``.
    """
    first = _block_final(previous)
    second = _block_final(block)
    if second is None or not data_rows:
        return "recurso", ""

    total = len(data_rows)
    with_second, failed_first = 0, 0
    threshold = 9.5 * (second.scale or 20.0) / 20.0

    for row in data_rows:
        value = parse_grade(_cell(row, second.index), scale=second.scale)
        if value.is_empty:
            continue
        with_second += 1
        if first is None:
            continue
        before = parse_grade(_cell(row, first.index), scale=first.scale)
        if before.value is not None:
            if before.value < threshold:
                failed_first += 1
        elif before.status in ("REPROVADO", "NAO_ADMITIDO", "FALTOU", "DESISTIU"):
            failed_first += 1

    if not with_second:
        return "recurso", (f"Ninguém tem nota em «{second.header}» — não dá para "
                           "perceber pelos dados o que esta coluna é.")

    coverage = with_second / max(total, 1)
    failed_share = failed_first / with_second if first is not None else 0.0
    detail = (f"{with_second} de {total} alunos têm nota em «{second.header}»"
              + (f", e {failed_first} desses não tinham passado no momento anterior"
                 if first is not None else "") + ".")

    if first is not None and failed_share >= 0.8 and coverage <= 0.7:
        return "recurso", detail + " Só lá vão os que chumbaram: parece 2.ª época."
    if coverage >= 0.7:
        return "continua", detail + (" Vai lá a turma quase toda: parece o 2.º teste "
                                     "da mesma época.")
    if failed_share >= 0.5:
        return "recurso", detail + " A maioria tinha chumbado: parece 2.ª época."
    return "continua", detail + " Os dados não são conclusivos."


def _block_final(block: dict):
    """A coluna de nota final do bloco, ou a ultima coluna de notas."""
    finals = [c for c in block["columns"] if c.kind == KIND_FINAL]
    if finals:
        return finals[-1]
    return block["columns"][-1] if block["columns"] else None


def _cell(row: list, index: int) -> str:
    return row[index] if index < len(row) else ""


def _final_priority(header: str) -> int:
    header = norm_header(header)
    best = 0
    for word, priority in FINAL_PRIORITY.items():
        if _has_word(header, [word]):
            best = max(best, priority)
    return best


def _pick_final_columns(columns: list) -> None:
    """Escolhe as notas finais: uma por via de avaliacao de cada epoca.

    Uma epoca pode ter mais do que uma nota final quando ha vias alternativas
    (avaliacao continua ou exame). O aluno so faz uma; a nota da epoca e a que
    ele tiver.
    """
    by_epoca: dict = {}
    for column in columns:
        if column.role == ROLE_GRADE:
            by_epoca.setdefault(column.epoca, []).append(column)

    has_epoca_final = any(
        c.kind == KIND_FINAL for e, g in by_epoca.items() if e is not None for c in g
    )

    for epoca, group in by_epoca.items():
        if epoca is None and has_epoca_final:
            # Colunas fora de qualquer bloco de epoca (ex.: "Projeto" antes de
            # "Teste 1") sao componentes partilhados, nunca a nota final.
            for column in group:
                if not column.locked:
                    column.kind = KIND_COMPONENT
                    column.reason = "componente comum a todas as épocas"
            continue

        candidates = [c for c in group if c.kind == KIND_FINAL]
        if not candidates:
            # Sem candidata obvia: a ultima coluna do bloco costuma ser a nota
            # final. Prefere-se uma com numeros, mas um bloco so com "RE"/"NA"
            # tambem tem de dar uma nota. Fica com confianca baixa (gera pergunta).
            livres = [c for c in group if not c.locked]
            fallback = [c for c in livres if c.numeric_ratio > 0.3] or livres
            if fallback:
                chosen = fallback[-1]
                chosen.kind = KIND_FINAL
                chosen.confidence = min(chosen.confidence, 0.35)
                chosen.reason = "última coluna do bloco (palpite)"
            continue

        # Uma nota final por grupo de colunas com o mesmo preenchimento.
        by_cluster: dict = {}
        for column in candidates:
            by_cluster.setdefault(column.cluster, []).append(column)

        for cluster in by_cluster.values():
            fixadas = [c for c in cluster if c.locked]
            best = (fixadas[-1] if fixadas
                    else max(cluster, key=lambda c: (_final_priority(c.header), c.index)))
            for column in cluster:
                if column is not best and not column.locked:
                    column.kind = KIND_COMPONENT
                    column.reason = f"«{best.header}» foi escolhida como nota final"
            best.kind = KIND_FINAL
            if len(cluster) > 1 and not fixadas:
                # So se pergunta quando as candidatas estao renhidas. Entre
                # "Nota Final" e "Avaliação Final" ha duvida legitima; entre
                # "Nota Final" e "Nota Trabalho" nao ha nenhuma.
                rivals = sorted((_final_priority(c.header) for c in cluster), reverse=True)
                if rivals[0] - rivals[1] < 20:
                    best.confidence = min(best.confidence, 0.55)

        if len(by_cluster) > 1:
            for cluster in by_cluster.values():
                for column in cluster:
                    if column.kind == KIND_FINAL:
                        column.reason += " (via alternativa desta época)"


# --------------------------------------------------------------------------
# UC, ano lectivo e data do documento
# --------------------------------------------------------------------------

_SUBJECT_NOISE = re.compile(
    r"\b(pauta|pautas|notas|nota|avaliacao|avaliacoes|classificacoes|classificacao|"
    r"epoca|epocas|exame|exames|final|finais|resultados|lista|listagem|"
    r"1e|2e|ee|v\d+|versao|versao\d+|20\d{2}|\d{2})\b",
    re.IGNORECASE,
)


#: "03713 - SGR - Segurança e Gestão de Redes": codigo, sigla e nome.
_SUBJECT_HEADER_RE = re.compile(
    r"^\s*(?:(?P<code>\d{3,8})\s*[-–—]\s*)?"
    r"(?:(?P<acronym>[A-Z][A-Z0-9]{1,9})\s*[-–—]\s*)?"
    r"(?P<name>[^\d].{4,})$"
)


def parse_subject_header(text: str):
    """Reparte "03713 - SGR - Segurança e Gestão de Redes" nas suas tres partes.

    O codigo e a sigla sao o que permite reconhecer a mesma cadeira quando as
    pautas vem em linguas diferentes.
    """
    match = _SUBJECT_HEADER_RE.match(clean_text(text))
    if not match:
        return None, None, None
    name = clean_text(match.group("name")).strip("-–— ")
    return match.group("code"), match.group("acronym"), name or None


def guess_subject_code(filename: str, table: RawTable) -> Guess:
    """Codigo ou sigla da cadeira -- a chave que junta pautas da mesma UC."""
    for line in table.title_lines[:10]:
        code, acronym, name = parse_subject_header(line)
        if code and name and _subject_score(name) > 0:
            return Guess(code, 0.9, f"código no documento: «{clean_text(line)[:60]}»")
        if acronym and name and _subject_score(name) > 0:
            return Guess(acronym, 0.7, f"sigla no documento: «{clean_text(line)[:60]}»")

    acronym = _acronym_from(os.path.splitext(os.path.basename(filename))[0])
    if acronym:
        return Guess(acronym, 0.5, f"sigla no nome do ficheiro: «{filename}»")
    return Guess(None, 0.0, "")


#: Palavras que desqualificam um pedaco de texto como nome de UC.
_NOT_A_SUBJECT = {
    # instituicao
    "university", "universidade", "institute", "instituto", "faculty",
    "faculdade", "escola", "school", "politecnico", "department",
    "departamento", "lisbon", "lisboa", "porto", "coimbra", "iscte", "ist",
    # legenda dos simbolos
    "failure", "failed", "withdrawal", "assessed", "minimum", "passing",
    "attained", "nonattendance", "reprovado", "aprovado", "faltou", "desistiu",
    # organizacao do ano
    "semester", "semestre", "season", "epoca", "sitting", "period", "periodo",
    # cabecalhos da propria pauta
    "pauta", "marks", "assessment", "avaliacao", "review", "total", "notas",
    "classificacoes", "exam", "exame", "office", "sala",
}


def _subject_score(text: str) -> float:
    """Quao provavel e que este texto seja o nome de uma unidade curricular."""
    words = [w for w in norm_text(text).split() if w]
    if not words:
        return -99.0
    letters = [w for w in words if w.isalpha()]
    if not letters:
        return -99.0

    score = len(letters) * 1.5
    if len(letters) >= 3:
        score += 3
    if any(w in _NOT_A_SUBJECT for w in words):
        score -= 12
    digits = sum(1 for w in words if any(ch.isdigit() for ch in w))
    score -= digits * 3
    if "%" in text:
        score -= 6
    if len(text) < 6:
        score -= 4
    return score


def guess_subject(filename: str, table: RawTable) -> Guess:
    """Tenta descobrir a unidade curricular (titulo do documento > ficheiro).

    Uma pauta traz muito texto a volta -- instituicao, legenda dos simbolos,
    datas de revisao de nota -- e o nome da cadeira e so mais um pedaco no meio
    disso. Em vez de assumir que esta no principio, pontuam-se todos os pedacos
    e fica o melhor.
    """
    # "03713 - SGR - Segurança e Gestão de Redes" e a forma mais clara de todas.
    for line in table.title_lines[:10]:
        code, acronym, name = parse_subject_header(line)
        if (code or acronym) and name and _subject_score(name) >= 6:
            return Guess(name, 0.9, f"cabeçalho do documento: «{clean_text(line)[:60]}»")

    best_text, best_score = None, 0.0
    for line in table.title_lines[:10]:
        for segment in re.split(r"\s+[-–—]\s+|\s*\|\s*|\s*:\s*", clean_text(line)):
            segment = clean_text(segment).strip("-–—,; ")
            if len(segment) < 4:
                continue
            if _YEAR_RE.search(segment):
                segment = clean_text(_YEAR_RE.sub("", segment)).strip("-–—/ ")
            score = _subject_score(segment)
            if score > best_score:
                best_text, best_score = segment, score

    if best_text and best_score >= 6:
        return Guess(best_text, 0.85, f"título do documento: «{best_text}»")

    if table.sheet_name:
        cleaned = _clean_subject_token(table.sheet_name.replace("_", " ").replace("-", " "))
        if cleaned and len(cleaned) >= 4 and not norm_text(cleaned).startswith("sheet"):
            return Guess(cleaned, 0.35, f"nome da folha: «{table.sheet_name}»")

    stem = os.path.splitext(os.path.basename(filename))[0]
    acronym = _acronym_from(stem)
    if acronym:
        return Guess(acronym, 0.5, f"sigla no nome do ficheiro: «{stem}»")

    if best_text:
        return Guess(best_text, 0.4, f"texto do documento: «{best_text}»")

    cleaned = _clean_subject_token(stem.replace("_", " ").replace("-", " "))
    if cleaned and len(cleaned) >= 4:
        return Guess(cleaned, 0.3, f"nome do ficheiro: «{stem}»")

    return Guess(None, 0.0, "não foi possível identificar a UC")


def _acronym_from(stem: str) -> Optional[str]:
    """Siglas tipo "SCSFM" em Pauta_SCSFM_2025_2026_1E, ou "SGR" em SGR202526."""
    for token in re.split(r"[\s_\-.]+", stem):
        letters = re.match(r"^([A-Z]{2,8})\d*$", token)
        if letters:
            candidate = letters.group(1)
            if norm_text(candidate) not in {"pauta", "notas", "uc", "ist", "iscte"}:
                return candidate
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


#: "2º Semestre", "2nd Semester", "Semestre 2". Precisa de expressao propria:
#: com listas de palavras, o "1st" de "1st Season" acabava por casar com
#: "semester 1" e trocava o semestre.
_SEMESTER_BEFORE = re.compile(r"\b([12])\s*(?:st|nd|rd|th|o|a)?\s+(?:semestre|semester|term)\b")
_SEMESTER_AFTER = re.compile(r"\b(?:semestre|semester|term)\s+([12])\b(?!\s*(?:st|nd|rd|th))")


def guess_semester(filename: str, table: RawTable) -> Guess:
    """Semestre em que a cadeira se da, quando a pauta o diz."""
    for text in table.title_lines[:10] + [os.path.basename(filename)]:
        normalized = split_glued(norm_header(text))
        match = _SEMESTER_BEFORE.search(normalized) or _SEMESTER_AFTER.search(normalized)
        if match:
            return Guess(match.group(1), 0.85,
                         f"encontrado em «{clean_text(text)[:50]}»")
    return Guess(None, 0.0, "")


#: "Teste 1 (30%)", "Exame (100%)", "Laboratório 2 (9%)" -- uma pauta que se
#: anuncia como um componente com um peso nao traz a nota final da epoca.
_COMPONENT_TITLE_RE = re.compile(
    r"\b(teste|test|exame|exam|frequencia|prova|laboratorio|lab|trabalho|"
    r"projeto|projecto|mini teste|quiz)\s*(\d?)\s*\(\s*(\d{1,3})\s*%\s*\)")


def guess_component_pauta(table: RawTable):
    """A pauta e de um componente so? Devolve ``(etiqueta, peso)``.

    Uma pauta intitulada "Teste 1 (30%)" tem uma coluna "Nota" que e a nota
    *desse teste*, nao a nota final da cadeira. Tratá-la como nota final punha-a
    a competir com a pauta da época, e ganhava a errada.
    """
    for line in table.title_lines[:10]:
        # norm_text (e nao norm_header) porque o "(30%)" tem de sobreviver.
        match = _COMPONENT_TITLE_RE.search(split_glued(norm_text(line)))
        if not match:
            continue
        weight = int(match.group(3))
        if weight >= 100:
            return None, None
        label = clean_text(f"{match.group(1).capitalize()} {match.group(2)}").strip()
        return label, weight
    return None, None


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

    component_label, component_weight = guess_component_pauta(table)
    if component_label:
        _mark_as_component_pauta(columns, component_label, component_weight)

    source = Source(
        id=source_id,
        filename=filename,
        kind=kind,
        location=table.location,
        subject=guess_subject(filename, table),
        subject_code=guess_subject_code(filename, table),
        semester=guess_semester(filename, table),
        academic_year=guess_year(filename, table),
        document_date=guess_document_date(table),
        columns=columns,
        data_rows=data_rows,
        header_row=[clean_text(c) for c in header_row],
        file_order=file_order,
    )
    if epoca_guess.value:
        source.notes.append(f"Época sugerida pelo ficheiro: {epoca_guess.reason}")
    if component_label:
        source.component_label = component_label
        source.component_weight = component_weight
        source.notes.append(
            f"Esta pauta é só «{component_label}» ({component_weight}% da nota), "
            "por isso conta como componente e não como nota final.")
    return source


def _mark_as_component_pauta(columns: list, label: str, weight: int) -> None:
    """A nota da pauta passa a ser esse componente, com o nome dele."""
    finals = [c for c in columns if c.role == ROLE_GRADE and c.kind == KIND_FINAL]
    if len(finals) != 1:
        return
    column = finals[0]
    column.kind = KIND_COMPONENT
    column.confidence = 0.8
    # Fixa a decisao: sem isto, a escolha automatica da nota final voltava a
    # promover esta coluna, por ser a unica coluna de notas do ficheiro.
    column.locked = True
    column.reason = f"a pauta é de «{label}» ({weight}%), não da nota final"
    if norm_header(column.header) in ("nota", "grade", "mark", "classificacao",
                                      "nota final", "valor"):
        column.header = f"{label} ({weight}%)"


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

        if grade_columns and not finals and not source.component_label:
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

        for question in _moment_questions(source, grade_columns):
            questions.append(question)

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
    return EPOCA_LABELS.get(epoca or "", "época desconhecida")


def _moment_questions(source: Source, grade_columns: list) -> list:
    """Pergunta o que e um segundo momento de avaliacao.

    E a pergunta mais importante da aplicacao: "Teste 2" tanto pode ser o
    segundo teste da avaliacao continua -- que se faz no dia do exame de 1.a
    epoca, e portanto conta para essa epoca -- como o exame de 2.a epoca. Os
    dados dao um palpite; quem sabe a cadeira e que confirma.
    """
    moments: dict = {}
    for column in grade_columns:
        if column.moment and column.moment > 1:
            moments.setdefault(column.moment, []).append(column)

    questions = []
    for moment, group in sorted(moments.items()):
        earlier = [c for c in grade_columns if (c.moment or 1) < moment and c.epoca]
        previous = earlier[-1].epoca if earlier else EPOCA_1
        headers = ", ".join(f"«{c.header}»" for c in group)

        options = [{
            "value": previous,
            "label": f"{moment}.º teste da {EPOCA_LABELS[previous]}",
            "hint": "avaliação contínua — faz-se no mesmo dia do exame",
        }]
        for epoca in (EPOCA_2, EPOCA_ESP):
            if epoca != previous:
                options.append({
                    "value": epoca,
                    "label": f"{EPOCA_LABELS[epoca]} (exame)",
                    "hint": "quem chumbou na época anterior vai a este exame",
                })

        questions.append(Question(
            id=f"{source.id}:moment:{moment}",
            type="moment",
            source_id=source.id,
            title=f"Em «{source.label}», {headers} é um segundo momento de avaliação. "
                  f"É o {moment}.º teste da mesma época ou é outra época?",
            detail=(group[0].evidence or "") +
                   f" O {moment}.º teste conta para a mesma época; um exame de recurso "
                   "é a época seguinte.",
            options=options,
            default=group[0].epoca or previous,
            severity="warning",
        ))
    return questions


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
        elif kind == "moment":
            try:
                moment = int(parts[2])
            except (TypeError, ValueError, IndexError):
                continue
            for column in source.columns:
                if column.role == ROLE_GRADE and column.moment == moment:
                    column.epoca = value
                    column.route = (ROUTE_EXAME if value in (EPOCA_2, EPOCA_ESP)
                                    else ROUTE_CONTINUA)
                    column.confidence = 1.0
                    column.reason = "momento definido pelo utilizador"
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

    for source in sources:
        refresh_columns(source)


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
            if "moment" in spec:
                # Permite dizer "esta coluna é o Teste 2" mesmo quando a
                # deteccao nao levantou a questao.
                try:
                    column.moment = int(spec["moment"]) if spec["moment"] else None
                except (TypeError, ValueError):
                    column.moment = None
            if spec.get("scale"):
                try:
                    column.scale = float(spec["scale"])
                except (TypeError, ValueError):
                    pass
            column.confidence = 1.0
            column.locked = True
            column.reason = "definido pelo utilizador"

    for source in sources:
        refresh_columns(source)


def refresh_columns(source: Source) -> None:
    """Refaz os agrupamentos depois de o utilizador mexer nas colunas.

    Os grupos de vias alternativas sao calculados por epoca; mudar a epoca de
    uma coluna a mao invalidava-os, e a nota final escolhida deixava de bater
    certo com o que estava no ecra. Sem isto, um ajuste manual podia
    simplesmente nao ter efeito.
    """
    _compute_clusters(source.columns, source.data_rows)
    _pick_final_columns(source.columns)

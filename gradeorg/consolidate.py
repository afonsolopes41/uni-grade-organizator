"""Juncao dos varios ficheiros numa unica listagem de alunos.

Trata de tres problemas:

1. **Identidade** -- o mesmo aluno aparece em ficheiros diferentes, por vezes
   com o numero trocado ou o nome sem acentos. Junta-se por numero *ou* por
   nome normalizado (uniao de conjuntos).
2. **Conflitos** -- duas versoes da mesma pauta dao notas diferentes para a
   mesma epoca. Ganha o documento mais recente, e o conflito fica registado.
3. **Melhor nota** -- entre 1.a epoca, 2.a epoca e epoca especial fica a
   melhor. Um numero ganha sempre a um estado ("RE", "NA", ...).
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Optional

from .i18n import (DEFAULT_LANGUAGE, Msg, epoca_label, normalize_language,
                   notice_type, render, route_label)
from .models import EPOCAS, ROLE_ID, ROLE_NAME, GradeEntry
from .normalize import (
    Grade,
    clean_text,
    name_tokens,
    norm_name,
    norm_text,
    parse_grade,
    parse_student_id,
    round_grade,
    split_id_from_name,
    strip_accents,
    title_name,
)

DEFAULT_PASS_MARK = 9.5
DEFAULT_SCALE = 20.0


@dataclass
class Settings:
    #: Nota minima usada nas UCs que nao tenham uma propria.
    pass_mark: float = DEFAULT_PASS_MARK
    #: Nota minima por UC -- cada cadeira tem a sua.
    subject_pass_marks: dict = field(default_factory=dict)
    #: Nome escolhido para cada grupo de pautas da mesma cadeira, ou "__split__"
    #: quando o utilizador diz que afinal sao cadeiras diferentes.
    subject_aliases: dict = field(default_factory=dict)
    #: Ano, semestre, ECTS e curso de cada cadeira -- e o que permite as medias
    #: por semestre, por ano e de fim de curso.
    subject_curriculum: dict = field(default_factory=dict)
    #: Cadeiras que o utilizador apagou: continuam nos ficheiros, mas ficam de
    #: fora das notas, das medias e do Excel.
    removed_subjects: list = field(default_factory=list)
    #: Cadeiras criadas a mao, que podem ainda nao ter pauta nenhuma.
    manual_subjects: list = field(default_factory=list)
    #: Fontes que o utilizador ja conferiu -- ficam arrumadas na interface.
    confirmed_sources: list = field(default_factory=list)
    scale: float = DEFAULT_SCALE
    merge_by_name: bool = True
    #: Lingua da interface e do Excel ("pt" ou "en").
    language: str = DEFAULT_LANGUAGE

    def curriculum_for(self, subject: str) -> dict:
        return dict(self.subject_curriculum.get(subject) or {})

    def course_for(self, subject: str) -> str:
        """Curso a que a cadeira pertence. Vazio = comum a varios cursos."""
        return (self.subject_curriculum.get(subject) or {}).get("course") or ""

    def is_removed(self, subject: Optional[str]) -> bool:
        return bool(subject) and subject in self.removed_subjects

    def pass_mark_for(self, subject: Optional[str]) -> float:
        """A nota minima desta UC, ou a de omissao se nao tiver uma."""
        if subject and subject in self.subject_pass_marks:
            return self.subject_pass_marks[subject]
        return self.pass_mark

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        data = data or {}
        settings = cls()
        try:
            settings.pass_mark = float(data.get("pass_mark", DEFAULT_PASS_MARK))
        except (TypeError, ValueError):
            pass
        try:
            settings.scale = float(data.get("scale", DEFAULT_SCALE)) or DEFAULT_SCALE
        except (TypeError, ValueError):
            pass
        for subject, value in (data.get("subject_pass_marks") or {}).items():
            if value in (None, ""):
                settings.subject_pass_marks.pop(subject, None)
                continue
            try:
                settings.subject_pass_marks[subject] = float(value)
            except (TypeError, ValueError):
                continue
        settings.subject_aliases = dict(data.get("subject_aliases") or {})
        settings.removed_subjects = sorted(
            {str(s) for s in (data.get("removed_subjects") or []) if s})
        settings.manual_subjects = list(dict.fromkeys(
            str(s).strip() for s in (data.get("manual_subjects") or []) if str(s).strip()))
        settings.confirmed_sources = sorted(
            {str(s) for s in (data.get("confirmed_sources") or []) if s})
        settings.language = normalize_language(data.get("language"))
        for subject, meta in (data.get("subject_curriculum") or {}).items():
            entry = dict(settings.subject_curriculum.get(subject) or {})
            if "course" in (meta or {}):
                course = str(meta["course"] or "").strip()
                if course:
                    entry["course"] = course
                else:
                    entry.pop("course", None)
            for key in ("year", "semester", "ects"):
                if key not in (meta or {}):
                    continue
                value = meta[key]
                if value in (None, ""):
                    entry.pop(key, None)
                    continue
                try:
                    entry[key] = float(value) if key == "ects" else int(value)
                except (TypeError, ValueError):
                    continue
            if entry:
                settings.subject_curriculum[subject] = entry
            else:
                settings.subject_curriculum.pop(subject, None)
        settings.merge_by_name = bool(data.get("merge_by_name", True))
        return settings

    def to_dict(self) -> dict:
        return {"pass_mark": self.pass_mark,
                "subject_pass_marks": dict(self.subject_pass_marks),
                "subject_aliases": dict(self.subject_aliases),
                "subject_curriculum": {k: dict(v) for k, v in
                                       self.subject_curriculum.items()},
                "removed_subjects": list(self.removed_subjects),
                "manual_subjects": list(self.manual_subjects),
                "confirmed_sources": list(self.confirmed_sources),
                "scale": self.scale,
                "merge_by_name": self.merge_by_name,
                "language": self.language}


# --------------------------------------------------------------------------
# Identidade das cadeiras
# --------------------------------------------------------------------------

SPLIT = "__split__"


def subject_group_key(source) -> str:
    """Chave que junta pautas da mesma cadeira.

    O codigo da UC ("03713") e o unico sinal fiavel quando a mesma cadeira tem
    pautas em linguas diferentes -- "Segurança e Gestão de Redes" e "Network
    Security and Management" nao se parecem em nada.
    """
    if source.subject_code.value and source.subject_code.confidence >= 0.5:
        return f"codigo:{norm_text(source.subject_code.value)}"
    if source.subject.value:
        return f"nome:{norm_name(source.subject.value)}"
    return f"ficheiro:{source.id}"


def order_subjects(subjects: list, curriculum: dict) -> list:
    """Ordena as cadeiras por ano e semestre, e alfabeticamente dentro de cada um.

    As que ainda nao tem ano nem semestre vao para o fim, para nao se
    intrometerem entre os grupos que ja estao arrumados.
    """
    def key(subject: str):
        meta = curriculum.get(subject) or {}
        year, semester = meta.get("year"), meta.get("semester")
        return (0 if year is not None else 1, year or 0,
                0 if semester is not None else 1, semester or 0,
                _sort_key(subject))
    return sorted(subjects, key=key)


def subject_groups(subjects: list, curriculum: dict) -> list:
    """As cadeiras agrupadas por (ano, semestre), na ordem em que aparecem."""
    grupos: list = []
    for subject in subjects:
        meta = curriculum.get(subject) or {}
        chave = (meta.get("year"), meta.get("semester"))
        if grupos and grupos[-1]["key"] == list(chave):
            grupos[-1]["subjects"].append(subject)
        else:
            grupos.append({"key": list(chave), "year": chave[0],
                           "semester": chave[1], "subjects": [subject]})
    return grupos


def detected_semesters(sources: list, subject_names: dict) -> dict:
    """Semestre que as proprias pautas indicam, por cadeira."""
    found: dict = {}
    for source in sources:
        subject = subject_names.get(source.id)
        if subject and source.semester.value and subject not in found:
            try:
                found[subject] = int(source.semester.value)
            except (TypeError, ValueError):
                continue
    return found


def effective_curriculum(subject: str, settings: Settings, detected: dict) -> dict:
    """Ano, semestre e ECTS de uma cadeira.

    O que o utilizador escreveu manda; o semestre que a pauta indica serve de
    valor de partida, para nao ser preciso repetir o que ja la esta escrito.
    """
    meta = settings.curriculum_for(subject)
    if meta.get("semester") is None and subject in detected:
        meta["semester"] = detected[subject]
    return meta


def resolve_subjects(sources: list, settings: Settings):
    """Decide o nome de cada cadeira e quais pautas pertencem a mesma.

    Devolve ``({source_id: nome}, [grupos com nomes diferentes])``.
    """
    groups: dict = {}
    for source in sources:
        groups.setdefault(subject_group_key(source), []).append(source)

    names: dict = {}
    merged: list = []
    for key, group in groups.items():
        candidates = [s.subject.value for s in group if s.subject.value]
        distinct = sorted(set(candidates), key=lambda n: (-len(n), n))
        choice = settings.subject_aliases.get(key)

        if choice == SPLIT or (not distinct and not choice):
            # Cada pauta fica com o seu nome.
            for source in group:
                names[source.id] = source.subject.value or source.label_in(
                    settings.language)
            continue

        # Um nome escolhido a mao ganha sempre -- e assim que se muda o nome de
        # uma cadeira, mesmo para um que nao apareca em ficheiro nenhum.
        canonical = choice or distinct[0]
        for source in group:
            names[source.id] = canonical

        if len(distinct) > 1:
            merged.append({
                "key": key,
                "code": group[0].subject_code.value,
                "names": distinct,
                "chosen": canonical,
                "confirmed": bool(choice),
                "files": sorted({s.filename for s in group}),
            })
    return names, merged


def subject_files(sources: list, subject_names: dict) -> dict:
    """Que ficheiros deram origem a cada cadeira."""
    files: dict = {}
    for source in sources:
        subject = subject_names.get(source.id)
        if not subject:
            continue
        entry = files.setdefault(subject, [])
        # O que interessa e o ficheiro, nao a folha ou a pagina: duas folhas do
        # mesmo ficheiro sao uma origem so.
        if source.filename not in entry:
            entry.append(source.filename)
    return {subject: sorted(labels) for subject, labels in files.items()}


def subject_keys(sources: list, subject_names: dict) -> dict:
    """Chaves de agrupamento por nome de cadeira -- e por elas que se renomeia."""
    keys: dict = {}
    for source in sources:
        subject = subject_names.get(source.id)
        if not subject:
            continue
        entry = keys.setdefault(subject, [])
        key = subject_group_key(source)
        if key not in entry:
            entry.append(key)
    return keys


def merge_questions(sources: list, settings: Settings) -> list:
    """Pergunta se duas pautas com o mesmo codigo sao mesmo a mesma cadeira."""
    from .models import Question

    _, merged = resolve_subjects(sources, settings)
    questions = []
    for merge in merged:
        if merge["confirmed"]:
            continue
        nomes = ", ".join(f"«{n}»" for n in merge["names"])
        ficheiros = ", ".join(merge["files"])
        questions.append(Question(
            id=f"merge:{merge['key']}",
            type="subject_merge",
            source_id=None,
            title=Msg("question.merge.title", names=nomes),
            detail=(Msg("question.merge.detail_code", code=merge["code"], files=ficheiros)
                    if merge["code"]
                    else Msg("question.merge.detail_similar", files=ficheiros)),
            options=[{"value": name, "label": Msg("question.merge.yes", name=name)}
                     for name in merge["names"]]
                    + [{"value": SPLIT, "label": Msg("question.merge.split"),
                        "hint": Msg("question.merge.split_hint")}],
            default=merge["chosen"],
            severity="warning",
        ))
    return questions


# --------------------------------------------------------------------------
# Extraccao das linhas
# --------------------------------------------------------------------------

@dataclass
class RowRecord:
    """Uma linha de uma pauta, ja lida."""

    source_id: str
    source_label: str
    row_index: int
    name: str
    student_id: Optional[str]
    entries: list = field(default_factory=list)   # list[GradeEntry]


def extract_records(sources: list, settings: Settings,
                    subject_names: Optional[dict] = None) -> list:
    """Le cada linha de cada Source e transforma-a num RowRecord.

    So interessa a nota final: as colunas de componentes (testes, laboratorios,
    trabalhos) servem para perceber a estrutura da pauta, mas nao entram no
    resultado.
    """
    records = []
    subject_names = subject_names or {}
    for source in sources:
        name_column = next((c for c in source.columns if c.role == ROLE_NAME), None)
        id_column = next((c for c in source.columns if c.role == ROLE_ID), None)
        final_columns = source.final_columns()
        source_label = source.label_in(settings.language)
        subject = (subject_names.get(source.id) or source.subject.value
                   or source_label)

        for row_index, row in enumerate(source.data_rows):
            def cell(column):
                if column is None or column.index >= len(row):
                    return ""
                return clean_text(row[column.index])

            name = title_name(cell(name_column))
            student_id = parse_student_id(cell(id_column)) if id_column else None
            # Pautas que juntam o número e o nome na mesma coluna. Tira-se
            # sempre o número de dentro do nome, mesmo quando há uma coluna
            # própria para ele -- senão o aluno ficava chamado «122631 Ana».
            embedded, cleaned = split_id_from_name(name)
            if embedded:
                name = title_name(cleaned)
                if student_id is None:
                    student_id = embedded
            if not name and not student_id:
                continue

            record = RowRecord(
                source_id=source.id,
                source_label=source_label,
                row_index=row_index,
                name=name,
                student_id=student_id,
            )

            def read(column):
                """Lê uma nota e traz-la para a escala de trabalho (0-20)."""
                return _rescale(parse_grade(cell(column), scale=column.scale),
                                settings.scale)

            for column in final_columns:
                grade = read(column)
                # Sem nota, o aluno nao foi a esta epoca: nao vale a pena criar
                # uma linha vazia para ele.
                if grade.is_empty:
                    continue
                record.entries.append(GradeEntry(
                    subject=subject,
                    epoca=column.epoca or EPOCAS[0],
                    grade=grade,
                    source_id=source.id,
                    source_label=source_label,
                    column_header=column.header,
                    route=column.route,
                    document_date=source.document_date,
                    file_order=source.file_order,
                ))
            records.append(record)
    return records


# --------------------------------------------------------------------------
# Identidade dos alunos
# --------------------------------------------------------------------------

class _Union:
    """Uniao de conjuntos simples, para agrupar linhas do mesmo aluno."""

    def __init__(self):
        self.parent: dict = {}

    def find(self, item):
        self.parent.setdefault(item, item)
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != root:
            self.parent[item], item = root, self.parent[item]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def cluster_records(records: list, settings: Settings) -> list:
    """Agrupa as linhas por aluno. Devolve uma lista de listas de RowRecord."""
    union = _Union()
    by_id: dict = {}
    by_name: dict = {}

    for index, record in enumerate(records):
        union.find(index)
        if record.student_id:
            by_id.setdefault(record.student_id, []).append(index)
        key = norm_name(record.name)
        if key:
            by_name.setdefault(key, []).append(index)

    for group in by_id.values():
        for other in group[1:]:
            union.union(group[0], other)

    if settings.merge_by_name:
        for group in by_name.values():
            for other in group[1:]:
                union.union(group[0], other)

    clusters: dict = {}
    for index in range(len(records)):
        clusters.setdefault(union.find(index), []).append(records[index])
    return list(clusters.values())


def find_similar_names(clusters: list, threshold: float = 0.90) -> list:
    """Sugere pares de alunos distintos com nomes muito parecidos."""
    entries = []
    for cluster in clusters:
        name = _best_name(cluster)
        if name:
            entries.append((norm_name(name), name, cluster))

    suggestions = []
    for i in range(len(entries)):
        key_a, name_a, cluster_a = entries[i]
        tokens_a = set(name_tokens(name_a))
        for j in range(i + 1, len(entries)):
            key_b, name_b, cluster_b = entries[j]
            if key_a == key_b:
                continue
            tokens_b = set(name_tokens(name_b))
            if not tokens_a or not tokens_b:
                continue
            shared = tokens_a & tokens_b
            if len(shared) < 2 and not (tokens_a <= tokens_b or tokens_b <= tokens_a):
                continue
            ratio = difflib.SequenceMatcher(None, key_a, key_b).ratio()
            if ratio >= threshold or tokens_a <= tokens_b or tokens_b <= tokens_a:
                ids_a = {r.student_id for r in cluster_a if r.student_id}
                ids_b = {r.student_id for r in cluster_b if r.student_id}
                if ids_a and ids_b and ids_a.isdisjoint(ids_b) and ratio < threshold:
                    continue
                suggestions.append({
                    "left": name_a, "right": name_b,
                    "left_ids": sorted(ids_a), "right_ids": sorted(ids_b),
                    "similarity": round(ratio, 3),
                })
    return suggestions


def _best_name(cluster: list) -> str:
    """O nome mais completo do grupo (mais palavras, depois mais longo)."""
    names = [r.name for r in cluster if r.name]
    if not names:
        return ""
    return max(names, key=lambda n: (len(name_tokens(n)), len(n)))


def _best_id(cluster: list):
    """O numero de aluno mais frequente; empate resolve-se pelo mais curto."""
    counts: dict = {}
    for record in cluster:
        if record.student_id:
            counts[record.student_id] = counts.get(record.student_id, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[0][0]


# --------------------------------------------------------------------------
# Resultado por UC
# --------------------------------------------------------------------------

def final_value(grade: Optional[Grade], scale: float = DEFAULT_SCALE):
    """A nota que fica: inteira, com as décimas arredondadas (13,5 -> 14).

    A pauta pode trazer décimas, mas a nota final de uma cadeira é um número
    inteiro -- e é essa que conta para aprovar e para as médias.
    """
    if grade is None:
        return None
    return round_grade(_to_scale(grade, scale))


def _to_scale(grade: Grade, scale: float) -> Optional[float]:
    """Valor convertido para a escala de trabalho (por omissao 0-20)."""
    if grade.value is None:
        return None
    if not grade.scale or abs(grade.scale - scale) < 1e-9:
        return grade.value
    return grade.value * scale / grade.scale


def _rescale(grade: Grade, scale: float) -> Grade:
    """Devolve a nota ja na escala de trabalho, guardando o valor original.

    Sem isto, uma pauta em 0-100 misturada com outra em 0-20 daria comparacoes
    e formatacao condicional sem sentido.
    """
    converted = _to_scale(grade, scale)
    if converted is None or abs(converted - (grade.value or 0)) < 1e-9:
        return grade
    raw = grade.raw or ""
    return Grade(value=round(converted, 4), status=grade.status, scale=scale,
                 raw=f"{raw} (de {grade.value:g} em 0-{grade.scale:g})")


def _by_column(entries: list) -> dict:
    """Agrupa as notas por ficheiro e coluna de origem."""
    grouped: dict = {}
    for entry in entries:
        grouped.setdefault((entry.source_id, entry.column_header), []).append(entry)
    return grouped


def _rank_entries(entries: list) -> list:
    """Ordena as versoes da mesma nota, da que vale da que nao vale.

    Se *todos* os documentos trazem data impressa, ganha o mais recente. Se pelo
    menos um nao tem data, as datas nao sao comparaveis entre si e vale a ordem
    de carregamento -- o ficheiro que o utilizador juntou por ultimo ganha.
    """
    if all(e.document_date for e in entries):
        key = lambda e: (e.document_date, e.file_order)   # noqa: E731
    else:
        key = lambda e: (e.file_order, e.document_date or "")   # noqa: E731
    return sorted(entries, key=key, reverse=True)


def _priority_reason(entries: list):
    return Msg("reason.newest_document" if all(e.document_date for e in entries)
               else "reason.latest_file")


def consolidate(sources: list, settings: Optional[Settings] = None) -> dict:
    """Produz a listagem consolidada, pronta para a web e para o Excel."""
    settings = settings or Settings()
    subject_names, merged_subjects = resolve_subjects(sources, settings)

    # Cadeiras apagadas pelo utilizador saem de tudo -- notas, medias e Excel.
    active = [s for s in sources if not settings.is_removed(subject_names.get(s.id))]
    known_subjects = sorted(
        {subject_names[s.id] for s in active if subject_names.get(s.id)}
        # Cadeiras criadas a mao contam mesmo sem pauta nenhuma: e assim que se
        # monta o plano de estudos antes de ter as notas todas.
        | {s for s in settings.manual_subjects if not settings.is_removed(s)},
        key=_sort_key)
    files_by_subject = subject_files(active, subject_names)
    courses = {subject: settings.course_for(subject) for subject in known_subjects}

    semestres = detected_semesters(active, subject_names)
    records = extract_records(active, settings, subject_names)
    clusters = cluster_records(records, settings)

    conflicts: list = []
    warnings: list = []
    students: list = []

    def etiqueta(grade) -> str:
        return grade.label_in(settings.language)

    for cluster in clusters:
        name = _best_name(cluster)
        student_id = _best_id(cluster)
        all_ids = sorted({r.student_id for r in cluster if r.student_id})
        all_names = sorted({r.name for r in cluster if r.name})

        if len(all_ids) > 1:
            conflicts.append({
                "type": "numero",
                "student": name,
                "detail": Msg("conflict.numero.detail", ids=", ".join(all_ids)),
                "chosen": student_id,
                "severity": "warning",
            })
        if len(all_names) > 1:
            warnings.append({
                "type": "nome",
                "student": name,
                "detail": Msg("warning.nome.detail",
                              names="; ".join(all_names), chosen=name),
                "severity": "info",
            })

        # subject -> epoca -> [GradeEntry]
        grouped: dict = {}
        for record in cluster:
            for entry in record.entries:
                grouped.setdefault(entry.subject, {}).setdefault(entry.epoca, []).append(entry)

        subjects: dict = {}
        for subject, by_epoca in grouped.items():
            epoca_results: dict = {}
            for epoca, entries in by_epoca.items():
                # Dentro do mesmo ficheiro, varias notas finais na mesma epoca
                # sao vias alternativas (avaliacao continua ou exame): o aluno
                # so faz uma, por isso fica a que tiver -- a melhor, se tiver as
                # duas. Entre ficheiros diferentes ja e um conflito de versoes.
                # Duas linhas do mesmo aluno na mesma coluna do mesmo ficheiro
                # nao sao vias alternativas: e o mesmo dado escrito duas vezes.
                for key, repeated in _by_column(entries).items():
                    valores = {(e.grade.value, e.grade.status) for e in repeated}
                    if len(valores) > 1:
                        conflicts.append({
                            "type": "linha repetida",
                            "student": name,
                            "subject": subject,
                            "epoca": epoca,
                            "detail": Msg(
                                "conflict.repeated_row.detail",
                                column=key[1], source=repeated[0].source_label,
                                values="; ".join(etiqueta(e.grade) for e in repeated)),
                            "chosen": etiqueta(
                                max(repeated, key=lambda e: e.grade.rank()).grade),
                            "severity": "warning",
                        })

                per_source: dict = {}
                for entry in entries:
                    current = per_source.get(entry.source_id)
                    if current is None or entry.grade.rank() > current.grade.rank():
                        per_source[entry.source_id] = entry
                # So conta como via alternativa a que tem mesmo nota: um aluno
                # que fez os testes tem a coluna do exame vazia, e vice-versa.
                routes = [e for e in entries
                          if e is not per_source.get(e.source_id) and not e.grade.is_empty]

                ranked = _rank_entries(list(per_source.values()))
                winner = ranked[0]

                distinct = {(e.grade.value, e.grade.status) for e in ranked}
                if len(distinct) > 1:
                    conflicts.append({
                        "type": "nota",
                        "student": name,
                        "subject": subject,
                        "epoca": epoca,
                        "detail": Msg("conflict.grade.detail", values="; ".join(
                            f"{etiqueta(e.grade)} ({e.source_label})" for e in ranked)),
                        "chosen": Msg("conflict.grade.chosen",
                                      value=etiqueta(winner.grade),
                                      source=winner.source_label,
                                      reason=_priority_reason(ranked)),
                        "severity": "warning",
                    })

                epoca_results[epoca] = {
                    "epoca": epoca,
                    "grade": winner.grade,
                    "value20": _to_scale(winner.grade, settings.scale),
                    "source_id": winner.source_id,
                    "source_label": winner.source_label,
                    "column": winner.column_header,
                    "route": winner.route,
                    # Outras versoes do mesmo dado, noutros ficheiros.
                    "other_versions": [
                        {"label": etiqueta(e.grade), "source": e.source_label,
                         "column": e.column_header}
                        for e in ranked[1:] if not e.grade.is_empty
                    ],
                    # Outras vias de avaliacao do mesmo ficheiro que o aluno
                    # tambem tem preenchidas (raro: normalmente so faz uma).
                    "other_routes": [
                        {"label": etiqueta(e.grade), "column": e.column_header,
                         "route": e.route}
                        for e in routes
                    ],
                }

            best_epoca, best = _pick_best(epoca_results, settings)
            subjects[subject] = {
                "subject": subject,
                "epocas": epoca_results,
                "best_epoca": best_epoca,
                "best": best,
                "pass_mark": settings.pass_mark_for(subject),
                "approved": _approved(best, settings, subject),
            }

        # Cadeiras em que o aluno aparece, mesmo sem nota nenhuma: e o que
        # separa "foi à cadeira e ficou sem nota" de "nem sequer a fez".
        inscrito = sorted({subject_names.get(r.source_id) for r in cluster
                           if subject_names.get(r.source_id)}, key=_sort_key)

        averages = _student_averages(subjects, settings, semestres)
        averages.update(_plan_coverage(subjects, known_subjects, courses))
        students.append({
            "seen_subjects": inscrito,
            "averages": averages,
            "key": _student_key(student_id, name),
            "name": name or (f"(sem nome) {student_id}" if student_id else "(sem nome)"),
            "student_id": student_id,
            "all_ids": all_ids,
            "all_names": all_names,
            "subjects": subjects,
            "sources": sorted({r.source_id for r in cluster}),
        })

    students.sort(key=lambda s: _sort_key(s["name"]))
    listed = {s for st in students for s in st["subjects"]}
    subject_list = order_subjects(sorted(listed | set(known_subjects), key=_sort_key),
                                  {s: effective_curriculum(s, settings, semestres)
                                   for s in listed | set(known_subjects)})
    pass_marks = {s: settings.pass_mark_for(s) for s in subject_list}

    for suggestion in find_similar_names(clusters):
        warnings.append({
            "type": "possivel_duplicado",
            "student": suggestion["left"],
            "detail": Msg("warning.similar_names.detail",
                          left=suggestion["left"], right=suggestion["right"],
                          similarity=f"{suggestion['similarity']:.0%}"),
            "severity": "info",
        })

    curriculum = {s: effective_curriculum(s, settings, semestres) for s in subject_list}
    for merge in merged_subjects:
        if merge["confirmed"]:
            continue
        ficheiros = " e ".join(f"«{f}»" for f in merge["files"])
        nomes = "; ".join(f"«{n}»" for n in merge["names"])
        warnings.append({
            "type": "cadeiras juntadas",
            "student": "",
            "subject": merge["chosen"],
            "detail": (Msg("warning.merged.detail_code", files=ficheiros,
                           code=merge["code"], names=nomes, chosen=merge["chosen"])
                       if merge["code"] else
                       Msg("warning.merged.detail_similar", files=ficheiros,
                           names=nomes, chosen=merge["chosen"])),
            "severity": "info",
        })

    warnings.extend(_sources_without_final(active, subject_names, settings.language))

    return {
        "students": students,
        "subjects": subject_list,
        "conflicts": conflicts,
        "warnings": warnings,
        "settings": settings.to_dict(),
        "pass_marks": pass_marks,
        "curriculum": curriculum,
        "courses": courses,
        "subject_groups": subject_groups(subject_list, curriculum),
        "subject_files": files_by_subject,
        "removed_subjects": sorted(settings.removed_subjects),
        "merged_subjects": merged_subjects,
        "stats": _stats(students, subject_list, settings),
        "subject_stats": _subject_stats(students, subject_list, settings),
    }


def _sources_without_final(sources: list, subject_names: dict,
                           lang: str = DEFAULT_LANGUAGE) -> list:
    """Pautas que nao trazem nota final nenhuma -- e que por isso nao contam."""
    avisos = []
    for source in sources:
        if source.final_columns():
            continue
        why = ""
        if source.component_label:
            why = Msg("warning.no_final.component", label=source.component_label,
                      weight=source.component_weight)
        avisos.append({
            "type": "pauta sem nota final",
            "student": "",
            "subject": subject_names.get(source.id) or "",
            "detail": Msg("warning.no_final.detail",
                          label=source.label_in(lang), why=why),
            "severity": "warning",
        })
    return avisos


def _plan_coverage(subjects: dict, known_subjects: list, courses: dict) -> dict:
    """Que parte do plano de estudos deste aluno e que nos temos.

    Ha cadeiras que sao de um curso so e cadeiras comuns a varios. Quem nao e do
    curso das primeiras nunca vai ter nota nelas -- e nao e por isso que esta
    pior. O plano de cada aluno e, entao, as cadeiras comuns mais as do curso
    dele; o curso deduz-se das cadeiras exclusivas em que tem nota.
    """
    seen = set(subjects)
    mine = sorted({courses.get(s) for s in seen if courses.get(s)})
    course = mine[0] if len(mine) == 1 else None

    named = any(courses.get(s) for s in known_subjects)
    if mine:
        plan = [s for s in known_subjects
                if not courses.get(s) or courses.get(s) in mine]
    elif named:
        # Nao se sabe o curso deste aluno: so se lhe pode exigir as comuns.
        plan = [s for s in known_subjects if not courses.get(s)]
    else:
        plan = list(known_subjects)

    missing = [s for s in plan if s not in seen]
    return {
        "course": course,
        "courses": mine,
        "coverage": {"have": len([s for s in plan if s in seen]),
                     "total": len(plan),
                     "missing": missing},
    }


def _pick_best(epoca_results: dict, settings: Settings):
    """A melhor das epocas. Empate numerico -> fica a epoca mais cedo."""
    best_key, best = None, None
    for epoca in EPOCAS + [e for e in epoca_results if e not in EPOCAS]:
        result = epoca_results.get(epoca)
        if result is None:
            continue
        grade: Grade = result["grade"]
        if grade.is_empty:
            continue
        if best is None or grade.rank() > best.rank():
            best_key, best = epoca, grade
    return best_key, best


def _approved(grade: Optional[Grade], settings: Settings, subject: Optional[str] = None):
    if grade is None:
        return None
    if grade.value is not None:
        # Aprova-se com a nota final -- a arredondada, que é a que fica.
        return final_value(grade, settings.scale) >= settings.pass_mark_for(subject) - 1e-9
    if grade.status == "APROVADO":
        return True
    if grade.status in ("REPROVADO", "FALTOU", "DESISTIU", "NAO_ADMITIDO"):
        return False
    return None


def _weighted_mean(entries: list):
    """Media das notas, ponderada por ECTS quando todas as cadeiras os tem."""
    if not entries:
        return None
    credits = [e for _, e in entries]
    if all(c for c in credits):
        total = sum(credits)
        return {"value": round(sum(v * c for v, c in entries) / total, 2),
                "count": len(entries), "ects": round(total, 1), "weighted": True}
    return {"value": round(sum(v for v, _ in entries) / len(entries), 2),
            "count": len(entries), "ects": None, "weighted": False}


def _student_averages(subjects: dict, settings: Settings, detected: dict) -> dict:
    """Medias por semestre, por ano e de fim de curso.

    Contam as cadeiras aprovadas com nota numerica -- e o que vai para o
    diploma. Uma cadeira sem ano ou semestre entra na media final mas nao nas
    parciais, e fica assinalada para o utilizador poder preencher.
    """
    by_semester: dict = {}
    by_year: dict = {}
    todas: list = []
    incompletas: list = []

    for subject, data in subjects.items():
        grade = data["best"]
        if data["approved"] is not True or grade is None or grade.value is None:
            continue
        meta = effective_curriculum(subject, settings, detected)
        value = final_value(grade, settings.scale)
        ects = meta.get("ects")
        todas.append((value, ects))

        year, semester = meta.get("year"), meta.get("semester")
        if year is None or semester is None:
            incompletas.append(subject)
            continue
        by_semester.setdefault((year, semester), []).append((value, ects))
        by_year.setdefault(year, []).append((value, ects))

    semesters = []
    for (year, semester) in sorted(by_semester):
        entry = _weighted_mean(by_semester[(year, semester)])
        entry.update({"year": year, "semester": semester})
        semesters.append(entry)

    years = []
    for year in sorted(by_year):
        entry = _weighted_mean(by_year[year])
        entry["year"] = year
        years.append(entry)

    final = _weighted_mean(todas)
    if final:
        final["rounded"] = round_grade(final["value"])
    for entry in semesters + years:
        entry["rounded"] = round_grade(entry["value"])
    return {"semesters": semesters, "years": years, "final": final,
            "missing_curriculum": sorted(incompletas)}


def _student_key(student_id: Optional[str], name: str) -> str:
    return f"id:{student_id}" if student_id else f"nome:{norm_name(name)}"


def _sort_key(text: str) -> str:
    """Ordem alfabética à portuguesa: «Álgebra» antes de «Análise».

    Sem tirar os acentos, o acento combinante vale mais do que qualquer letra e
    manda as palavras acentuadas para o fim.
    """
    return strip_accents((text or "").lower())


def _subject_stats(students: list, subjects: list, settings: Settings) -> dict:
    """Aprovações, reprovações e média de cada cadeira.

    Somadas entre cadeiras estas contas não querem dizer nada -- 40 aprovações
    em quatro UCs não é uma leitura de nada. Por cadeira já são a leitura certa:
    quantos passaram, quantos chumbaram e com que média.

    Só contam os alunos que têm essa cadeira: quem é de outro curso não conta
    como reprovado numa cadeira que nunca fez.
    """
    resultado: dict = {}
    for subject in subjects:
        aprovados = reprovados = pendentes = 0
        valores: list = []
        for student in students:
            data = student["subjects"].get(subject)
            if not data:
                # Aparece na pauta mas sem nota nenhuma.
                if subject in student.get("seen_subjects", ()):
                    pendentes += 1
                continue
            if data["approved"] is True:
                aprovados += 1
            elif data["approved"] is False:
                reprovados += 1
            else:
                pendentes += 1
            grade = data["best"]
            if grade is not None and grade.value is not None:
                valores.append(final_value(grade, settings.scale))

        avaliados = aprovados + reprovados
        resultado[subject] = {
            "students": aprovados + reprovados + pendentes,
            "approved": aprovados,
            "failed": reprovados,
            "pending": pendentes,
            "average": round(sum(valores) / len(valores), 2) if valores else None,
            "pass_rate": round(aprovados / avaliados, 3) if avaliados else None,
        }
    return resultado


def _stats(students: list, subjects: list, settings: Settings) -> dict:
    approved = failed = pending = 0
    values = []
    for student in students:
        for result in student["subjects"].values():
            if result["approved"] is True:
                approved += 1
            elif result["approved"] is False:
                failed += 1
            else:
                pending += 1
            grade = result["best"]
            if grade is not None and grade.value is not None:
                values.append(final_value(grade, settings.scale))
    return {
        "students": len(students),
        "subjects": len(subjects),
        "approved": approved,
        "failed": failed,
        "pending": pending,
        "average": round(sum(values) / len(values), 2) if values else None,
    }


# --------------------------------------------------------------------------
# Serializacao para a interface web
# --------------------------------------------------------------------------

def to_json(result: dict, lang: str = DEFAULT_LANGUAGE) -> dict:
    """Versao serializavel e traduzida (os Grade viram dicionarios)."""
    students = []
    for student in result["students"]:
        subjects = {}
        for subject, data in student["subjects"].items():
            epocas = {}
            for epoca, info in data["epocas"].items():
                epocas[epoca] = {
                    "epoca": epoca,
                    "label": epoca_label(epoca, lang),
                    "grade": info["grade"].to_dict(lang),
                    "source_label": info["source_label"],
                    "column": info["column"],
                    "route": info.get("route"),
                    "route_label": route_label(info.get("route"), lang),
                    "other_versions": info.get("other_versions", []),
                    "other_routes": [dict(r, route=route_label(r.get("route"), lang))
                                     for r in info.get("other_routes", [])],
                }
            best: Optional[Grade] = data["best"]
            subjects[subject] = {
                "subject": subject,
                "epocas": epocas,
                "pass_mark": data["pass_mark"],
                "best_epoca": data["best_epoca"],
                "best_epoca_label": (epoca_label(data["best_epoca"], lang)
                                     if data["best_epoca"] else "—"),
                "best": best.to_dict(lang) if best else None,
                "best_rounded": round_grade(best.value) if best else None,
                "approved": data["approved"],
            }
        students.append({
            "averages": student["averages"],
            "key": student["key"],
            "name": student["name"],
            "student_id": student["student_id"],
            "all_ids": student["all_ids"],
            "all_names": student["all_names"],
            "subjects": subjects,
        })

    def notice(entry: dict) -> dict:
        out = dict(entry)
        out["detail"] = render(entry.get("detail"), lang)
        out["chosen"] = render(entry.get("chosen"), lang)
        out["type_label"] = notice_type(entry.get("type"), lang)
        if entry.get("epoca"):
            out["epoca"] = epoca_label(entry["epoca"], lang)
        return out

    return {
        "students": students,
        "subjects": result["subjects"],
        "epocas": [{"key": e, "label": epoca_label(e, lang)} for e in EPOCAS],
        "conflicts": [notice(c) for c in result["conflicts"]],
        "warnings": [notice(w) for w in result["warnings"]],
        "settings": result["settings"],
        "pass_marks": result.get("pass_marks", {}),
        "curriculum": result.get("curriculum", {}),
        "courses": result.get("courses", {}),
        "subject_groups": result.get("subject_groups", []),
        "subject_stats": result.get("subject_stats", {}),
        "subject_files": result.get("subject_files", {}),
        "removed_subjects": result.get("removed_subjects", []),
        "merged_subjects": result.get("merged_subjects", []),
        "stats": result["stats"],
    }

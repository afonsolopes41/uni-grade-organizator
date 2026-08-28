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
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from .models import (
    EPOCA_LABELS,
    EPOCAS,
    KIND_FINAL,
    ROLE_GRADE,
    ROLE_ID,
    ROLE_NAME,
    ROUTE_LABELS,
    GradeEntry,
)
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
    #: Ano, semestre e ECTS de cada cadeira -- e o que permite as medias por
    #: semestre, por ano e de fim de curso.
    subject_curriculum: dict = field(default_factory=dict)
    scale: float = DEFAULT_SCALE
    merge_by_name: bool = True

    def curriculum_for(self, subject: str) -> dict:
        return dict(self.subject_curriculum.get(subject) or {})

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
        for subject, meta in (data.get("subject_curriculum") or {}).items():
            entry = dict(settings.subject_curriculum.get(subject) or {})
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
                "scale": self.scale,
                "merge_by_name": self.merge_by_name}


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

        if choice == SPLIT or not distinct:
            # Cada pauta fica com o seu nome.
            for source in group:
                names[source.id] = source.subject.value or f"(UC de {source.filename})"
            continue

        canonical = choice if choice in distinct else distinct[0]
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


def merge_questions(sources: list, settings: Settings) -> list:
    """Pergunta se duas pautas com o mesmo codigo sao mesmo a mesma cadeira."""
    from .models import Question

    _, merged = resolve_subjects(sources, settings)
    questions = []
    for merge in merged:
        if merge["confirmed"]:
            continue
        nomes = " e ".join(f"«{n}»" for n in merge["names"])
        questions.append(Question(
            id=f"merge:{merge['key']}",
            type="subject_merge",
            source_id=None,
            title=f"{nomes} são a mesma cadeira?",
            detail=("Têm o mesmo código " + f"({merge['code']}) " if merge["code"]
                    else "Parecem a mesma cadeira ")
                   + "mas as pautas dão-lhes nomes diferentes: "
                   + ", ".join(merge["files"]) + ".",
            options=[{"value": name, "label": f"Sim — usar «{name}»"}
                     for name in merge["names"]]
                    + [{"value": SPLIT, "label": "Não, são cadeiras diferentes",
                        "hint": "cada pauta fica com o seu nome"}],
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
    """Le cada linha de cada Source e transforma-a num RowRecord."""
    records = []
    subject_names = subject_names or {}
    for source in sources:
        name_column = next((c for c in source.columns if c.role == ROLE_NAME), None)
        id_column = next((c for c in source.columns if c.role == ROLE_ID), None)
        grade_columns = [c for c in source.columns if c.role == ROLE_GRADE]
        subject = (subject_names.get(source.id) or source.subject.value
                   or f"(UC de {source.filename})")

        for row_index, row in enumerate(source.data_rows):
            def cell(column):
                if column is None or column.index >= len(row):
                    return ""
                return clean_text(row[column.index])

            name = title_name(cell(name_column))
            student_id = parse_student_id(cell(id_column)) if id_column else None
            if student_id is None:
                # Pautas que juntam o número e o nome na mesma coluna.
                embedded, cleaned = split_id_from_name(name)
                if embedded:
                    student_id, name = embedded, title_name(cleaned)
            if not name and not student_id:
                continue

            record = RowRecord(
                source_id=source.id,
                source_label=source.label,
                row_index=row_index,
                name=name,
                student_id=student_id,
            )

            def read(column):
                """Lê uma nota e traz-la para a escala de trabalho (0-20)."""
                return _rescale(parse_grade(cell(column), scale=column.scale),
                                settings.scale)

            components_by_epoca: dict = {}
            for column in grade_columns:
                if column.kind == KIND_FINAL:
                    continue
                grade = read(column)
                if grade.is_empty:
                    continue
                components_by_epoca.setdefault(column.epoca, {})[column.header] = grade

            shared = components_by_epoca.get(None, {})
            for column in grade_columns:
                if column.kind != KIND_FINAL:
                    continue
                grade = read(column)
                epoca = column.epoca or EPOCAS[0]
                own = components_by_epoca.get(column.epoca, {})
                # Sem nota e sem componentes proprios, o aluno nao foi a esta
                # epoca: nao vale a pena criar uma linha vazia para ele.
                if grade.is_empty and not own:
                    continue
                components = dict(shared)
                components.update(own)
                record.entries.append(GradeEntry(
                    subject=subject,
                    epoca=epoca,
                    grade=grade,
                    source_id=source.id,
                    source_label=source.label,
                    column_header=column.header,
                    route=column.route,
                    document_date=source.document_date,
                    file_order=source.file_order,
                    components=components,
                ))

            # Sem coluna final mas com componentes: guarda-se na mesma, para o
            # aluno aparecer na listagem.
            if not record.entries and components_by_epoca:
                for epoca, components in components_by_epoca.items():
                    if not components:
                        continue
                    record.entries.append(GradeEntry(
                        subject=subject,
                        epoca=epoca or EPOCAS[0],
                        grade=Grade(status="SEM_NOTA", raw=""),
                        source_id=source.id,
                        source_label=source.label,
                        column_header="",
                        document_date=source.document_date,
                        file_order=source.file_order,
                        components=components,
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


def _priority_reason(entries: list) -> str:
    return ("documento mais recente" if all(e.document_date for e in entries)
            else "ficheiro carregado mais tarde")


def consolidate(sources: list, settings: Optional[Settings] = None) -> dict:
    """Produz a listagem consolidada, pronta para a web e para o Excel."""
    settings = settings or Settings()
    subject_names, merged_subjects = resolve_subjects(sources, settings)
    semestres = detected_semesters(sources, subject_names)
    records = extract_records(sources, settings, subject_names)
    clusters = cluster_records(records, settings)

    conflicts: list = []
    warnings: list = []
    students: list = []

    for cluster in clusters:
        name = _best_name(cluster)
        student_id = _best_id(cluster)
        all_ids = sorted({r.student_id for r in cluster if r.student_id})
        all_names = sorted({r.name for r in cluster if r.name})

        if len(all_ids) > 1:
            conflicts.append({
                "type": "numero",
                "student": name,
                "detail": f"O mesmo aluno aparece com números diferentes: {', '.join(all_ids)}.",
                "chosen": student_id,
                "severity": "warning",
            })
        if len(all_names) > 1:
            warnings.append({
                "type": "nome",
                "student": name,
                "detail": "Nome escrito de maneiras diferentes: "
                          + "; ".join(all_names) + f". Usado: «{name}».",
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
                            "epoca": EPOCA_LABELS.get(epoca, epoca),
                            "detail": f"O aluno aparece mais do que uma vez em «{key[1]}» "
                                      f"({repeated[0].source_label}) com valores diferentes: "
                                      + "; ".join(e.grade.label for e in repeated),
                            "chosen": max(repeated, key=lambda e: e.grade.rank()).grade.label,
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

                distinct = {
                    (e.grade.value, e.grade.status) for e in ranked
                    if not (e.grade.is_empty and e.components)
                }
                if len(distinct) > 1:
                    conflicts.append({
                        "type": "nota",
                        "student": name,
                        "subject": subject,
                        "epoca": EPOCA_LABELS.get(epoca, epoca),
                        "detail": "Valores diferentes em ficheiros diferentes: "
                                  + "; ".join(
                                      f"{e.grade.label} ({e.source_label})" for e in ranked),
                        "chosen": f"{winner.grade.label} ({winner.source_label}) "
                                  f"— {_priority_reason(ranked)}",
                        "severity": "warning",
                    })

                components = {}
                for entry in reversed(entries):
                    components.update(entry.components)

                epoca_results[epoca] = {
                    "epoca": epoca,
                    "label": EPOCA_LABELS.get(epoca, epoca),
                    "grade": winner.grade,
                    "value20": _to_scale(winner.grade, settings.scale),
                    "source_id": winner.source_id,
                    "source_label": winner.source_label,
                    "column": winner.column_header,
                    "route": winner.route,
                    "route_label": ROUTE_LABELS.get(winner.route or "", ""),
                    "components": components,
                    # Outras versoes do mesmo dado, noutros ficheiros.
                    "other_versions": [
                        {"label": e.grade.label, "source": e.source_label,
                         "column": e.column_header}
                        for e in ranked[1:] if not e.grade.is_empty
                    ],
                    # Outras vias de avaliacao do mesmo ficheiro que o aluno
                    # tambem tem preenchidas (raro: normalmente so faz uma).
                    "other_routes": [
                        {"label": e.grade.label, "column": e.column_header,
                         "route": ROUTE_LABELS.get(e.route or "", "")}
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

        averages = _student_averages(subjects, settings, semestres)
        students.append({
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
    subject_names = sorted({s for st in students for s in st["subjects"]}, key=_sort_key)
    pass_marks = {s: settings.pass_mark_for(s) for s in subject_names}

    for suggestion in find_similar_names(clusters):
        warnings.append({
            "type": "possivel_duplicado",
            "student": suggestion["left"],
            "detail": f"«{suggestion['left']}» e «{suggestion['right']}» têm nomes muito "
                      f"parecidos (semelhança {suggestion['similarity']:.0%}) mas ficaram "
                      "como alunos diferentes. Confirme se é a mesma pessoa.",
            "severity": "info",
        })

    curriculum = {s: effective_curriculum(s, settings, semestres) for s in subject_names}
    for merge in merged_subjects:
        if not merge["confirmed"]:
            warnings.append({
                "type": "cadeiras juntadas",
                "student": "",
                "subject": merge["chosen"],
                "detail": "As pautas " + " e ".join(f"«{f}»" for f in merge["files"])
                          + (f" têm o mesmo código ({merge['code']})" if merge["code"]
                             else " parecem ser da mesma cadeira")
                          + " mas dão-lhe nomes diferentes: "
                          + "; ".join(f"«{n}»" for n in merge["names"])
                          + f". Foram tratadas como uma só, com o nome «{merge['chosen']}».",
                "severity": "info",
            })

    return {
        "students": students,
        "subjects": subject_names,
        "conflicts": conflicts,
        "warnings": warnings,
        "settings": settings.to_dict(),
        "pass_marks": pass_marks,
        "curriculum": curriculum,
        "merged_subjects": merged_subjects,
        "stats": _stats(students, subject_names, settings),
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
        return _to_scale(grade, settings.scale) >= settings.pass_mark_for(subject) - 1e-9
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
        value = _to_scale(grade, settings.scale)
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
    return {"semesters": semesters, "years": years, "final": final,
            "missing_curriculum": sorted(incompletas)}


def _student_key(student_id: Optional[str], name: str) -> str:
    return f"id:{student_id}" if student_id else f"nome:{norm_name(name)}"


def _sort_key(text: str) -> str:
    return unicodedata.normalize("NFKD", (text or "").lower())


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
                values.append(_to_scale(grade, settings.scale))
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

def to_json(result: dict) -> dict:
    """Versao serializavel (os objectos Grade viram dicionarios)."""
    students = []
    for student in result["students"]:
        subjects = {}
        for subject, data in student["subjects"].items():
            epocas = {}
            for epoca, info in data["epocas"].items():
                epocas[epoca] = {
                    "epoca": epoca,
                    "label": info["label"],
                    "grade": info["grade"].to_dict(),
                    "source_label": info["source_label"],
                    "column": info["column"],
                    "route": info.get("route"),
                    "route_label": info.get("route_label", ""),
                    "other_versions": info.get("other_versions", []),
                    "other_routes": info.get("other_routes", []),
                    "components": {k: v.to_dict() for k, v in info["components"].items()},
                }
            best: Optional[Grade] = data["best"]
            subjects[subject] = {
                "subject": subject,
                "epocas": epocas,
                "pass_mark": data["pass_mark"],
                "best_epoca": data["best_epoca"],
                "best_epoca_label": EPOCA_LABELS.get(data["best_epoca"] or "", "—"),
                "best": best.to_dict() if best else None,
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
    return {
        "students": students,
        "subjects": result["subjects"],
        "epocas": [{"key": e, "label": EPOCA_LABELS[e]} for e in EPOCAS],
        "conflicts": result["conflicts"],
        "warnings": result["warnings"],
        "settings": result["settings"],
        "pass_marks": result.get("pass_marks", {}),
        "curriculum": result.get("curriculum", {}),
        "merged_subjects": result.get("merged_subjects", []),
        "stats": result["stats"],
    }

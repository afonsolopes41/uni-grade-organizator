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
    GradeEntry,
)
from .normalize import (
    Grade,
    clean_text,
    name_tokens,
    norm_name,
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
    pass_mark: float = DEFAULT_PASS_MARK
    scale: float = DEFAULT_SCALE
    merge_by_name: bool = True

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
        settings.merge_by_name = bool(data.get("merge_by_name", True))
        return settings

    def to_dict(self) -> dict:
        return {"pass_mark": self.pass_mark, "scale": self.scale,
                "merge_by_name": self.merge_by_name}


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


def extract_records(sources: list, settings: Settings) -> list:
    """Le cada linha de cada Source e transforma-a num RowRecord."""
    records = []
    for source in sources:
        name_column = next((c for c in source.columns if c.role == ROLE_NAME), None)
        id_column = next((c for c in source.columns if c.role == ROLE_ID), None)
        grade_columns = [c for c in source.columns if c.role == ROLE_GRADE]
        subject = source.subject.value or f"(UC de {source.filename})"

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
    records = extract_records(sources, settings)
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
                entries = _rank_entries(entries)
                winner = entries[0]

                distinct = {
                    (e.grade.value, e.grade.status) for e in entries
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
                                      f"{e.grade.label} ({e.source_label})" for e in entries),
                        "chosen": f"{winner.grade.label} ({winner.source_label}) "
                                  f"— {_priority_reason(entries)}",
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
                    "components": components,
                    "alternatives": [
                        {"label": e.grade.label, "source": e.source_label}
                        for e in entries[1:]
                    ],
                }

            best_epoca, best = _pick_best(epoca_results, settings)
            subjects[subject] = {
                "subject": subject,
                "epocas": epoca_results,
                "best_epoca": best_epoca,
                "best": best,
                "approved": _approved(best, settings),
            }

        students.append({
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

    for suggestion in find_similar_names(clusters):
        warnings.append({
            "type": "possivel_duplicado",
            "student": suggestion["left"],
            "detail": f"«{suggestion['left']}» e «{suggestion['right']}» têm nomes muito "
                      f"parecidos (semelhança {suggestion['similarity']:.0%}) mas ficaram "
                      "como alunos diferentes. Confirme se é a mesma pessoa.",
            "severity": "info",
        })

    return {
        "students": students,
        "subjects": subject_names,
        "conflicts": conflicts,
        "warnings": warnings,
        "settings": settings.to_dict(),
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


def _approved(grade: Optional[Grade], settings: Settings):
    if grade is None:
        return None
    if grade.value is not None:
        return _to_scale(grade, settings.scale) >= settings.pass_mark - 1e-9
    if grade.status == "APROVADO":
        return True
    if grade.status in ("REPROVADO", "FALTOU", "DESISTIU", "NAO_ADMITIDO"):
        return False
    return None


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
                    "components": {k: v.to_dict() for k, v in info["components"].items()},
                    "alternatives": info["alternatives"],
                }
            best: Optional[Grade] = data["best"]
            subjects[subject] = {
                "subject": subject,
                "epocas": epocas,
                "best_epoca": data["best_epoca"],
                "best_epoca_label": EPOCA_LABELS.get(data["best_epoca"] or "", "—"),
                "best": best.to_dict() if best else None,
                "best_rounded": round_grade(best.value) if best else None,
                "approved": data["approved"],
            }
        students.append({
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
        "stats": result["stats"],
    }

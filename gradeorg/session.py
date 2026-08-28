"""Estado da sessao.

A aplicacao corre localmente para um so utilizador, por isso o estado vive em
memoria: os ficheiros carregados, as tabelas extraidas e as escolhas feitas na
interface.

As ``Source`` sao sempre reconstruidas a partir das tabelas em bruto antes de
se aplicarem as respostas do utilizador. Assim, retirar uma resposta faz mesmo
voltar a deteccao automatica, em vez de deixar restos da escolha anterior.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
from dataclasses import dataclass, field
from typing import Optional

from .consolidate import (
    Settings, consolidate, detected_semesters, effective_curriculum,
    merge_questions, resolve_subjects, to_json,
)
from .detect import apply_answers, apply_column_overrides, build_questions, build_source
from .parsers import parse_file


#: Definicoes cujo valor e um dicionario por cadeira: chegam da interface uma
#: cadeira de cada vez, e uma substituicao simples apagava as restantes.
_PER_SUBJECT_SETTINGS = ("subject_pass_marks", "subject_aliases", "subject_curriculum")


def _merge_settings(current: dict, incoming: dict) -> dict:
    """Junta definicoes novas as antigas sem perder o que ja la estava."""
    merged = dict(current)
    for key, value in incoming.items():
        if key in _PER_SUBJECT_SETTINGS and isinstance(value, dict):
            combined = dict(merged.get(key) or {})
            for subject, entry in value.items():
                if isinstance(entry, dict):
                    inner = dict(combined.get(subject) or {})
                    inner.update(entry)
                    combined[subject] = inner
                else:
                    combined[subject] = entry
            merged[key] = combined
        else:
            merged[key] = value
    return merged


@dataclass
class UploadedFile:
    name: str
    path: str
    kind: str
    order: int
    tables: list = field(default_factory=list)   # list[RawTable]

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "tables": len(self.tables)}


class Session:
    """Ficheiros carregados, deteccao e resultado consolidado."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.tmpdir = tempfile.mkdtemp(prefix="gradeorg-")
        self.files: list = []
        self.answers: dict = {}
        self.overrides: dict = {}
        self.settings = Settings()
        self._sources: list = []
        self._dirty = True
        self._counter = 0

    # -- ficheiros ---------------------------------------------------------

    def add_file(self, filename: str, data: bytes) -> UploadedFile:
        """Guarda o ficheiro num directorio temporario e extrai as tabelas."""
        with self._lock:
            self._counter += 1
            order = self._counter

        safe = os.path.basename(filename).replace(os.sep, "_") or f"ficheiro{order}"
        path = os.path.join(self.tmpdir, f"{order:02d}_{safe}")
        with open(path, "wb") as handle:
            handle.write(data)

        kind, tables = parse_file(path, filename)
        if not tables:
            raise ValueError(
                f"Não foi encontrada nenhuma tabela de notas em «{filename}». "
                "Se for um PDF digitalizado (imagem), tem de passar por OCR primeiro."
            )

        uploaded = UploadedFile(name=filename, path=path, kind=kind, order=order, tables=tables)
        with self._lock:
            self.files.append(uploaded)
            self._dirty = True
        return uploaded

    def remove_file(self, filename: str) -> None:
        with self._lock:
            self.files = [f for f in self.files if f.name != filename]
            self._dirty = True

    def reset(self) -> None:
        with self._lock:
            self.files = []
            self.answers = {}
            self.overrides = {}
            self.settings = Settings()
            self._sources = []
            self._dirty = True
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        self.tmpdir = tempfile.mkdtemp(prefix="gradeorg-")

    # -- deteccao ----------------------------------------------------------

    @property
    def sources(self) -> list:
        """Fontes reconstruidas e com as escolhas do utilizador aplicadas."""
        with self._lock:
            if not self._dirty:
                return self._sources
            sources = []
            for uploaded in self.files:
                for index, table in enumerate(uploaded.tables):
                    sources.append(build_source(
                        source_id=f"f{uploaded.order}s{index}",
                        filename=uploaded.name,
                        kind=uploaded.kind,
                        table=table,
                        file_order=uploaded.order,
                    ))
            apply_answers(sources, self.answers)
            apply_column_overrides(sources, self.overrides)
            self._sources = sources
            self._dirty = False
            return sources

    def update(self, answers: Optional[dict] = None, overrides: Optional[dict] = None,
               settings: Optional[dict] = None) -> None:
        """Grava as escolhas da interface e marca a deteccao para refazer."""
        with self._lock:
            if answers is not None:
                aliases = {}
                for key, value in answers.items():
                    # As respostas sobre juntar cadeiras vivem nas definicoes,
                    # porque valem para um grupo de pautas e nao para uma fonte.
                    if key.startswith("merge:"):
                        aliases[key[len("merge:"):]] = value
                        if value in (None, ""):
                            self.answers.pop(key, None)
                        else:
                            self.answers[key] = value
                        continue
                    if value in (None, ""):
                        self.answers.pop(key, None)
                    else:
                        self.answers[key] = value
                if aliases:
                    merged = dict(self.settings.subject_aliases)
                    for key, value in aliases.items():
                        if value in (None, ""):
                            merged.pop(key, None)
                        else:
                            merged[key] = value
                    self.settings.subject_aliases = merged
            if overrides:
                for source_id, columns in overrides.items():
                    target = self.overrides.setdefault(source_id, {})
                    for column_index, spec in (columns or {}).items():
                        if spec is None:
                            target.pop(str(column_index), None)
                        else:
                            target[str(column_index)] = spec
            if settings:
                self.settings = Settings.from_dict(
                    _merge_settings(self.settings.to_dict(), settings))
            self._dirty = True

    def open_questions(self) -> list:
        questions = build_questions(self.sources)
        questions += merge_questions(self.sources, self.settings)
        return [q for q in questions if not self.answers.get(q.id)]

    # -- resultados --------------------------------------------------------

    def review(self) -> dict:
        names, _ = resolve_subjects(self.sources, self.settings)
        subjects = sorted(set(names.values()))
        semesters = detected_semesters(self.sources, names)
        codes: dict = {}
        for source in self.sources:
            subject = names.get(source.id)
            if subject and source.subject_code.value:
                codes.setdefault(subject, source.subject_code.value)
        return {
            "files": [f.to_dict() for f in self.files],
            "sources": [s.to_dict() for s in self.sources],
            "questions": [q.to_dict() for q in self.open_questions()],
            "answers": self.answers,
            "overrides": self.overrides,
            "settings": self.settings.to_dict(),
            "subjects": subjects,
            "subject_codes": codes,
            # Semestre que a própria pauta indica, para preencher por omissão.
            "detected_semesters": semesters,
            "curriculum": {s: effective_curriculum(s, self.settings, semesters)
                           for s in subjects},
            "pass_marks": {s: self.settings.pass_mark_for(s) for s in subjects},
        }

    def raw_result(self) -> dict:
        return consolidate(self.sources, self.settings)

    def result(self) -> dict:
        payload = to_json(self.raw_result())
        payload["files"] = [f.to_dict() for f in self.files]
        payload["sources"] = [s.to_dict() for s in self.sources]
        payload["questions"] = [q.to_dict() for q in self.open_questions()]
        payload["answers"] = self.answers
        return payload

    def source_labels(self) -> list:
        return [f.name for f in self.files]


#: Sessao unica do processo.
SESSION = Session()

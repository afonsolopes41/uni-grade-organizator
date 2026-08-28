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

from .consolidate import Settings, consolidate, to_json
from .detect import apply_answers, apply_column_overrides, build_questions, build_source
from .parsers import parse_file


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
                for key, value in answers.items():
                    if value in (None, ""):
                        self.answers.pop(key, None)
                    else:
                        self.answers[key] = value
            if overrides:
                for source_id, columns in overrides.items():
                    target = self.overrides.setdefault(source_id, {})
                    for column_index, spec in (columns or {}).items():
                        if spec is None:
                            target.pop(str(column_index), None)
                        else:
                            target[str(column_index)] = spec
            if settings:
                self.settings = Settings.from_dict({**self.settings.to_dict(), **settings})
            self._dirty = True

    def open_questions(self) -> list:
        return [q for q in build_questions(self.sources) if not self.answers.get(q.id)]

    # -- resultados --------------------------------------------------------

    def review(self) -> dict:
        return {
            "files": [f.to_dict() for f in self.files],
            "sources": [s.to_dict() for s in self.sources],
            "questions": [q.to_dict() for q in self.open_questions()],
            "answers": self.answers,
            "overrides": self.overrides,
            "settings": self.settings.to_dict(),
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

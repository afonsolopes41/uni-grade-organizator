"""Estado da sessao.

A aplicacao corre localmente para um so utilizador. O estado -- ficheiros
carregados, tabelas extraidas e escolhas feitas na interface -- vive em memoria
mas fica sempre gravado em disco, para que fechar a aplicacao nao perca nada:
ao voltar a abrir esta tudo como se deixou. So o botao de apagar e que limpa.

As ``Source`` sao sempre reconstruidas a partir das tabelas em bruto antes de
se aplicarem as respostas do utilizador. Assim, retirar uma resposta faz mesmo
voltar a deteccao automatica, em vez de deixar restos da escolha anterior.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import Optional

from . import storage
from .consolidate import (
    SPLIT, Settings, consolidate, detected_semesters, effective_curriculum,
    merge_questions, resolve_subjects, subject_files, subject_keys, to_json,
)
from .detect import apply_answers, apply_column_overrides, build_questions, build_source
from .i18n import normalize_language, tr
from .models import RawTable
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

    def to_state(self) -> dict:
        return {"name": self.name, "kind": self.kind, "order": self.order,
                "path": os.path.basename(self.path)}


class Session:
    """Ficheiros carregados, deteccao e resultado consolidado."""

    def __init__(self, load: bool = True) -> None:
        self._lock = threading.Lock()
        self.files: list = []
        self.answers: dict = {}
        self.overrides: dict = {}
        self.settings = Settings()
        self._sources: list = []
        self._dirty = True
        self._counter = 0
        if load:
            self._load()

    # -- persistencia ------------------------------------------------------

    @property
    def language(self) -> str:
        return normalize_language(self.settings.language)

    def _load(self) -> None:
        """Le o que ficou da ultima vez. Se algo estiver estragado, comeca do zero."""
        state = storage.read_json(storage.state_path())
        if not isinstance(state, dict) or state.get("version") != storage.FORMAT_VERSION:
            return
        self.answers = dict(state.get("answers") or {})
        self.overrides = {k: dict(v) for k, v in (state.get("overrides") or {}).items()}
        self.settings = Settings.from_dict(state.get("settings") or {})

        for entry in state.get("files") or []:
            path = os.path.join(storage.files_dir(), entry.get("path") or "")
            if not os.path.exists(path):
                continue
            order = int(entry.get("order") or 0)
            tables = self._read_tables(order)
            if tables is None:
                try:
                    _, tables = parse_file(path, entry.get("name") or "")
                except Exception:                        # noqa: BLE001
                    continue
                self._write_tables(order, tables)
            self.files.append(UploadedFile(
                name=entry.get("name") or os.path.basename(path),
                path=path, kind=entry.get("kind") or "", order=order, tables=tables))
            self._counter = max(self._counter, order)
        self._dirty = True

    def _save(self) -> None:
        try:
            storage.write_json(storage.state_path(), {
                "version": storage.FORMAT_VERSION,
                "files": [f.to_state() for f in self.files],
                "answers": self.answers,
                "overrides": self.overrides,
                "settings": self.settings.to_dict(),
            })
        except OSError:
            # Ficar sem memoria entre arranques e chato, mas nao e motivo para
            # a aplicacao deixar de funcionar agora.
            pass

    @staticmethod
    def _tables_path(order: int) -> str:
        return os.path.join(storage.tables_dir(), f"{order:02d}.json")

    def _read_tables(self, order: int):
        payload = storage.read_json(self._tables_path(order))
        if not isinstance(payload, list):
            return None
        return [RawTable.from_dict(item) for item in payload]

    def _write_tables(self, order: int, tables: list) -> None:
        try:
            storage.write_json(self._tables_path(order), [t.to_dict() for t in tables])
        except OSError:
            pass

    # -- ficheiros ---------------------------------------------------------

    def add_file(self, filename: str, data: bytes) -> UploadedFile:
        """Guarda o ficheiro e extrai as tabelas."""
        with self._lock:
            self._counter += 1
            order = self._counter

        safe = os.path.basename(filename).replace(os.sep, "_") or f"ficheiro{order}"
        path = os.path.join(storage.files_dir(), f"{order:02d}_{safe}")
        with open(path, "wb") as handle:
            handle.write(data)

        try:
            kind, tables = parse_file(path, filename)
        except Exception:
            os.unlink(path)
            raise
        if not tables:
            os.unlink(path)
            raise ValueError(tr("api.no_table", self.language, name=filename))

        uploaded = UploadedFile(name=filename, path=path, kind=kind,
                                order=order, tables=tables)
        self._write_tables(order, tables)
        with self._lock:
            self.files.append(uploaded)
            self._dirty = True
            self._save()
        return uploaded

    def remove_file(self, filename: str) -> None:
        with self._lock:
            leaving = [f for f in self.files if f.name == filename]
            self.files = [f for f in self.files if f.name != filename]
            self._dirty = True
            for item in leaving:
                for path in (item.path, self._tables_path(item.order)):
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
            self._save()

    def reset(self) -> None:
        """Apaga tudo -- ficheiros, respostas e definicoes. Nao ha volta atras."""
        language = self.language
        with self._lock:
            self.files = []
            self.answers = {}
            self.overrides = {}
            self.settings = Settings()
            self.settings.language = language
            self._sources = []
            self._dirty = True
            self._counter = 0
            storage.wipe()
            self._save()

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
            self._save()

    # -- cadeiras ----------------------------------------------------------

    def _subject_map(self):
        names, _ = resolve_subjects(self.sources, self.settings)
        return names

    def rename_subject(self, old: str, new: str) -> None:
        """Muda o nome de uma cadeira, aqui e em tudo o que dependia dele."""
        new = (new or "").strip()
        if not old or not new or old == new:
            return
        names = self._subject_map()
        keys = subject_keys(self.sources, names).get(old, [])
        with self._lock:
            for source in self._sources:
                if names.get(source.id) == old:
                    self.answers[f"{source.id}:subject"] = new
            aliases = dict(self.settings.subject_aliases)
            for key in keys:
                if aliases.get(key) != SPLIT:
                    aliases[key] = new
            self.settings.subject_aliases = aliases
            # As definicoes por cadeira sao guardadas pelo nome: mudam com ele.
            for store in (self.settings.subject_pass_marks,
                          self.settings.subject_curriculum):
                if old in store:
                    store[new] = store.pop(old)
            if old in self.settings.removed_subjects:
                self.settings.removed_subjects = [
                    new if s == old else s for s in self.settings.removed_subjects]
            self._dirty = True
            self._save()

    def remove_subject(self, subject: str) -> None:
        """Tira a cadeira das notas. Os ficheiros ficam -- da para repor."""
        if not subject:
            return
        with self._lock:
            if subject not in self.settings.removed_subjects:
                self.settings.removed_subjects = sorted(
                    self.settings.removed_subjects + [subject])
            self._dirty = True
            self._save()

    def restore_subject(self, subject: str) -> None:
        with self._lock:
            self.settings.removed_subjects = [
                s for s in self.settings.removed_subjects if s != subject]
            self._dirty = True
            self._save()

    def set_language(self, language: str) -> None:
        with self._lock:
            self.settings.language = normalize_language(language)
            self._save()

    def open_questions(self) -> list:
        """Perguntas por responder -- sem contar com as cadeiras apagadas."""
        names = self._subject_map()
        live = [s for s in self.sources
                if not self.settings.is_removed(names.get(s.id))]
        questions = build_questions(live)
        questions += merge_questions(live, self.settings)
        return [q for q in questions if not self.answers.get(q.id)]

    # -- resultados --------------------------------------------------------

    def review(self) -> dict:
        lang = self.language
        names, _ = resolve_subjects(self.sources, self.settings)
        subjects = sorted(set(names.values()))
        semesters = detected_semesters(self.sources, names)
        codes: dict = {}
        for source in self.sources:
            subject = names.get(source.id)
            if subject and source.subject_code.value:
                codes.setdefault(subject, source.subject_code.value)
        return {
            "language": lang,
            "files": [f.to_dict() for f in self.files],
            "sources": [s.to_dict(lang) for s in self.sources],
            "questions": [q.to_dict(lang) for q in self.open_questions()],
            "answers": self.answers,
            "overrides": self.overrides,
            "settings": self.settings.to_dict(),
            "subjects": subjects,
            "subject_codes": codes,
            "subject_files": subject_files(self.sources, names),
            "removed_subjects": sorted(self.settings.removed_subjects),
            # Semestre que a própria pauta indica, para preencher por omissão.
            "detected_semesters": semesters,
            "curriculum": {s: effective_curriculum(s, self.settings, semesters)
                           for s in subjects},
            "pass_marks": {s: self.settings.pass_mark_for(s) for s in subjects},
            "courses": {s: self.settings.course_for(s) for s in subjects},
        }

    def raw_result(self) -> dict:
        return consolidate(self.sources, self.settings)

    def result(self) -> dict:
        lang = self.language
        payload = to_json(self.raw_result(), lang)
        payload["language"] = lang
        payload["files"] = [f.to_dict() for f in self.files]
        payload["sources"] = [s.to_dict(lang) for s in self.sources]
        payload["questions"] = [q.to_dict(lang) for q in self.open_questions()]
        payload["answers"] = self.answers
        return payload

    def source_labels(self) -> list:
        return [f.name for f in self.files]


#: Sessao unica do processo.
SESSION = Session()

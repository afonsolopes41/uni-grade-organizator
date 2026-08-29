"""Estruturas de dados partilhadas pelo pipeline.

Fluxo: parsers -> RawTable -> detect -> Source(+Column) -> consolidate ->
StudentRecord -> excel/web.

Os textos que chegam ao utilizador (razoes, notas, perguntas) sao objectos
:class:`~gradeorg.i18n.Msg`, para poderem sair em portugues ou em ingles. E por
isso que os ``to_dict`` recebem a lingua.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .i18n import DEFAULT_LANGUAGE, location_label, render, tr

# Chaves internas das epocas. A ordem importa (1 -> 2 -> especial).
EPOCA_1 = "epoca1"
EPOCA_2 = "epoca2"
EPOCA_ESP = "especial"
EPOCAS = [EPOCA_1, EPOCA_2, EPOCA_ESP]

#: Etiquetas em portugues -- para ingles usa-se ``i18n.epoca_label``.
EPOCA_LABELS = {epoca: tr(f"epoca.{epoca}") for epoca in EPOCAS}

ROLE_NAME = "name"
ROLE_ID = "id"
ROLE_GRADE = "grade"
ROLE_IGNORE = "ignore"

KIND_FINAL = "final"
KIND_COMPONENT = "component"

# Modalidades de avaliacao dentro da mesma epoca. Na 1.a epoca um aluno faz uma
# das duas: avaliacao continua (testes/frequencias) ou o exame -- que e no mesmo
# dia do 2.o teste. A 2.a epoca e a especial sao sempre exame.
ROUTE_CONTINUA = "continua"
ROUTE_EXAME = "exame"

ROUTE_LABELS = {route: tr(f"route.{route}") for route in (ROUTE_CONTINUA, ROUTE_EXAME)}


@dataclass
class RawTable:
    """Uma tabela tal como saiu do ficheiro, ainda sem interpretacao."""

    rows: list = field(default_factory=list)  # list[list[str]]
    location: str = ""          # "página 2", "folha: Pautas", ...
    title_lines: list = field(default_factory=list)   # texto acima da tabela
    footer_lines: list = field(default_factory=list)  # texto abaixo da tabela
    sheet_name: str = ""
    page: Optional[int] = None

    def to_dict(self) -> dict:
        return {"rows": self.rows, "location": self.location,
                "title_lines": self.title_lines, "footer_lines": self.footer_lines,
                "sheet_name": self.sheet_name, "page": self.page}

    @classmethod
    def from_dict(cls, data: dict) -> "RawTable":
        data = data or {}
        return cls(
            rows=[list(row) for row in (data.get("rows") or [])],
            location=data.get("location") or "",
            title_lines=list(data.get("title_lines") or []),
            footer_lines=list(data.get("footer_lines") or []),
            sheet_name=data.get("sheet_name") or "",
            page=data.get("page"),
        )


@dataclass
class Column:
    """Uma coluna ja classificada (papel, epoca, escala)."""

    index: int
    header: str
    role: str = ROLE_IGNORE
    epoca: Optional[str] = None
    kind: str = KIND_COMPONENT
    #: Modalidade a que a coluna pertence (ver ROUTE_*). None = indiferente.
    route: Optional[str] = None
    #: Momento de avaliacao a que a coluna pertence (1 = o primeiro, 2 = "Teste 2").
    moment: Optional[int] = None
    #: Colunas com a mesma via de avaliacao partilham grupo: as que estao
    #: preenchidas para os mesmos alunos sao a mesma nota, nao alternativas.
    cluster: int = 0
    #: O que os dados dizem sobre um momento posterior (texto para a pergunta).
    evidence: Any = ""
    scale: float = 20.0
    confidence: float = 0.0
    reason: Any = ""
    numeric_ratio: float = 0.0
    filled_ratio: float = 0.0
    max_value: Optional[float] = None
    samples: list = field(default_factory=list)
    #: Definida pelo utilizador -- a detecção automática não lhe volta a tocar.
    locked: bool = False
    #: A coluna traz o numero e o nome juntos ("122631 Ana Silva").
    combined: bool = False

    @property
    def is_final(self) -> bool:
        return self.role == ROLE_GRADE and self.kind == KIND_FINAL

    def to_dict(self, lang: str = DEFAULT_LANGUAGE) -> dict:
        return {
            "index": self.index,
            "header": self.header,
            "role": self.role,
            "epoca": self.epoca,
            "kind": self.kind,
            "route": self.route,
            "moment": self.moment,
            "cluster": self.cluster,
            "evidence": render(self.evidence, lang),
            "scale": self.scale,
            "confidence": round(self.confidence, 2),
            "reason": render(self.reason, lang),
            "numeric_ratio": round(self.numeric_ratio, 2),
            "filled_ratio": round(self.filled_ratio, 2),
            "max_value": self.max_value,
            "locked": self.locked,
            "combined": self.combined,
            "samples": self.samples[:5],
        }


@dataclass
class Guess:
    """Um palpite com nivel de confianca e a razao por tras dele."""

    value: Optional[str] = None
    confidence: float = 0.0
    reason: Any = ""

    def to_dict(self, lang: str = DEFAULT_LANGUAGE) -> dict:
        return {"value": self.value, "confidence": round(self.confidence, 2),
                "reason": render(self.reason, lang)}


@dataclass
class Source:
    """Um bloco de dados de um ficheiro (uma folha de Excel, uma pagina de PDF)."""

    id: str
    filename: str
    kind: str                      # pdf | xlsx | csv | txt
    location: str = ""
    subject: Guess = field(default_factory=Guess)
    #: Codigo ou sigla da cadeira -- junta pautas da mesma UC em linguas
    #: diferentes ("03713 - SGR" aparece nas duas).
    subject_code: Guess = field(default_factory=Guess)
    #: Semestre em que a cadeira se da (1 ou 2), quando a pauta o diz.
    semester: Guess = field(default_factory=Guess)
    academic_year: Guess = field(default_factory=Guess)
    document_date: Optional[str] = None   # ISO, usado para desempatar conflitos
    columns: list = field(default_factory=list)     # list[Column]
    data_rows: list = field(default_factory=list)   # list[list[str]]
    header_row: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    #: Quando a pauta e de um so componente ("Teste 1 (30%)"), o nome e o peso.
    component_label: Optional[str] = None
    component_weight: Optional[int] = None
    file_order: int = 0

    @property
    def label(self) -> str:
        return self.label_in()

    def label_in(self, lang: str = DEFAULT_LANGUAGE) -> str:
        """«pauta.pdf (página 2)» -- o sítio exacto de onde a tabela saiu."""
        place = location_label(self.location, lang)
        return f"{self.filename} ({place})" if place else self.filename

    def grade_columns(self) -> list:
        return [c for c in self.columns if c.role == ROLE_GRADE]

    def final_columns(self) -> list:
        return [c for c in self.columns if c.is_final]

    def to_dict(self, lang: str = DEFAULT_LANGUAGE) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "kind": self.kind,
            "location": location_label(self.location, lang),
            "label": self.label_in(lang),
            "subject": self.subject.to_dict(lang),
            "subject_code": self.subject_code.to_dict(lang),
            "semester": self.semester.to_dict(lang),
            "academic_year": self.academic_year.to_dict(lang),
            "document_date": self.document_date,
            "columns": [c.to_dict(lang) for c in self.columns],
            "component_label": self.component_label,
            "component_weight": self.component_weight,
            "row_count": len(self.data_rows),
            "header_row": self.header_row,
            "preview": self.data_rows[:6],
            "notes": [render(n, lang) for n in self.notes],
        }


@dataclass
class Question:
    """Pergunta ao utilizador quando a deteccao automatica nao chega."""

    id: str
    type: str                    # subject | epoca | final_column | scale | merge
    source_id: Optional[str]
    title: Any
    detail: Any = ""
    options: list = field(default_factory=list)   # [{"value","label","hint"}]
    default: Optional[str] = None
    allow_custom: bool = False
    severity: str = "info"       # info | warning
    column_index: Optional[int] = None

    def to_dict(self, lang: str = DEFAULT_LANGUAGE) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "source_id": self.source_id,
            "title": render(self.title, lang),
            "detail": render(self.detail, lang),
            "options": [{k: render(v, lang) for k, v in option.items()}
                        for option in self.options],
            "default": self.default,
            "allow_custom": self.allow_custom,
            "severity": self.severity,
            "column_index": self.column_index,
        }


@dataclass
class GradeEntry:
    """Uma nota de um aluno, numa UC, numa epoca, vinda de um ficheiro."""

    subject: str
    epoca: str
    grade: Any                    # normalize.Grade
    source_id: str
    source_label: str
    column_header: str
    route: Optional[str] = None
    document_date: Optional[str] = None
    file_order: int = 0


@dataclass
class StudentRecord:
    """Um aluno, com tudo o que se sabe dele em todos os ficheiros."""

    key: str
    name: str
    student_id: Optional[str] = None
    all_names: list = field(default_factory=list)
    all_ids: list = field(default_factory=list)
    subjects: dict = field(default_factory=dict)  # {subject: SubjectResult}
    sources: list = field(default_factory=list)

"""Estruturas de dados partilhadas pelo pipeline.

Fluxo: parsers -> RawTable -> detect -> Source(+Column) -> consolidate ->
StudentRecord -> excel/web.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Chaves internas das epocas. A ordem importa (1 -> 2 -> especial).
EPOCA_1 = "epoca1"
EPOCA_2 = "epoca2"
EPOCA_ESP = "especial"
EPOCAS = [EPOCA_1, EPOCA_2, EPOCA_ESP]

EPOCA_LABELS = {
    EPOCA_1: "1.ª Época",
    EPOCA_2: "2.ª Época",
    EPOCA_ESP: "Época Especial",
}

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

ROUTE_LABELS = {
    ROUTE_CONTINUA: "Avaliação contínua",
    ROUTE_EXAME: "Exame",
}


@dataclass
class RawTable:
    """Uma tabela tal como saiu do ficheiro, ainda sem interpretacao."""

    rows: list = field(default_factory=list)  # list[list[str]]
    location: str = ""          # "página 2", "folha: Pautas", ...
    title_lines: list = field(default_factory=list)   # texto acima da tabela
    footer_lines: list = field(default_factory=list)  # texto abaixo da tabela
    sheet_name: str = ""
    page: Optional[int] = None


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
    evidence: str = ""
    scale: float = 20.0
    confidence: float = 0.0
    reason: str = ""
    numeric_ratio: float = 0.0
    filled_ratio: float = 0.0
    max_value: Optional[float] = None
    samples: list = field(default_factory=list)
    #: Definida pelo utilizador -- a detecção automática não lhe volta a tocar.
    locked: bool = False

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "header": self.header,
            "role": self.role,
            "epoca": self.epoca,
            "kind": self.kind,
            "route": self.route,
            "moment": self.moment,
            "cluster": self.cluster,
            "evidence": self.evidence,
            "scale": self.scale,
            "confidence": round(self.confidence, 2),
            "reason": self.reason,
            "numeric_ratio": round(self.numeric_ratio, 2),
            "filled_ratio": round(self.filled_ratio, 2),
            "max_value": self.max_value,
            "locked": self.locked,
            "samples": self.samples[:5],
        }


@dataclass
class Guess:
    """Um palpite com nivel de confianca e a razao por tras dele."""

    value: Optional[str] = None
    confidence: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict:
        return {"value": self.value, "confidence": round(self.confidence, 2), "reason": self.reason}


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
        return f"{self.filename} ({self.location})" if self.location else self.filename

    def grade_columns(self) -> list:
        return [c for c in self.columns if c.role == ROLE_GRADE]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "kind": self.kind,
            "location": self.location,
            "label": self.label,
            "subject": self.subject.to_dict(),
            "subject_code": self.subject_code.to_dict(),
            "semester": self.semester.to_dict(),
            "academic_year": self.academic_year.to_dict(),
            "document_date": self.document_date,
            "columns": [c.to_dict() for c in self.columns],
            "component_label": self.component_label,
            "component_weight": self.component_weight,
            "row_count": len(self.data_rows),
            "header_row": self.header_row,
            "preview": self.data_rows[:6],
            "notes": self.notes,
        }


@dataclass
class Question:
    """Pergunta ao utilizador quando a deteccao automatica nao chega."""

    id: str
    type: str                    # subject | epoca | final_column | scale | merge
    source_id: Optional[str]
    title: str
    detail: str = ""
    options: list = field(default_factory=list)   # [{"value","label","hint"}]
    default: Optional[str] = None
    allow_custom: bool = False
    severity: str = "info"       # info | warning
    column_index: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "source_id": self.source_id,
            "title": self.title,
            "detail": self.detail,
            "options": self.options,
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
    components: dict = field(default_factory=dict)   # {"Projeto": Grade, ...}


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

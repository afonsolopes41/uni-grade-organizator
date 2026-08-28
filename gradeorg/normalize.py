"""Normalizacao de texto, nomes, numeros de aluno e notas.

Todos os ficheiros de pautas usam convencoes diferentes (virgula ou ponto
decimal, acentos, abreviaturas de estado como "RE"/"NA"/"-"), por isso tudo o
que entra no pipeline passa primeiro por aqui.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Optional

# --------------------------------------------------------------------------
# Texto
# --------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def strip_accents(text: str) -> str:
    """Remove diacriticos ("Joao" == "João")."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def clean_text(value: Any) -> str:
    """Converte qualquer celula em texto limpo, sem espacos redundantes."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    else:
        text = str(value)
    text = text.replace("\xa0", " ")
    for dash in ("‐", "‑", "‒", "–", "—", "−"):
        text = text.replace(dash, "-")
    return _WS_RE.sub(" ", text).strip()


#: Indicadores de ordinal. Tem de sair antes do NFKD, que os transformaria em
#: letras: "2.ª Época" viraria "2 a epoca" e deixaria de casar com "2 epoca".
_ORDINAL_RE = re.compile(r"[ºª°]")


def norm_text(value: Any) -> str:
    """Chave comparavel: minusculas, sem acentos, espacos normalizados."""
    text = _ORDINAL_RE.sub("", clean_text(value))
    return _WS_RE.sub(" ", strip_accents(text).lower()).strip()


def norm_header(value: Any) -> str:
    """Chave de cabecalho: so letras/numeros separados por um espaco."""
    return _NON_ALNUM_RE.sub(" ", norm_text(value)).strip()


# Particulas que nao contam para comparar nomes de pessoas.
_NAME_PARTICLES = {"de", "da", "do", "das", "dos", "e", "del", "la", "van", "von", "y"}


def norm_name(value: Any) -> str:
    """Forma canonica de um nome, para juntar o mesmo aluno entre ficheiros."""
    text = norm_text(value)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return _WS_RE.sub(" ", text).strip()


def name_tokens(value: Any) -> list:
    """Palavras significativas de um nome (sem particulas)."""
    return [t for t in norm_name(value).split() if t not in _NAME_PARTICLES and len(t) > 1]


def title_name(value: Any) -> str:
    """Apresenta um nome com capitalizacao decente sem estragar o original."""
    text = clean_text(value)
    if not text:
        return ""
    if text.isupper() or text.islower():
        parts = []
        for word in text.split(" "):
            low = strip_accents(word).lower()
            parts.append(word.lower() if low in _NAME_PARTICLES else word.capitalize())
        return " ".join(parts)
    return text


def looks_like_person_name(value: Any) -> bool:
    """Heuristica: duas ou mais palavras alfabeticas, sem digitos."""
    text = clean_text(value)
    if not text or any(ch.isdigit() for ch in text):
        return False
    words = [w for w in norm_name(text).split() if w]
    if len(words) < 2:
        return False
    letters = sum(ch.isalpha() for ch in strip_accents(text))
    return letters >= max(4, int(len(text.replace(" ", "")) * 0.8))


# --------------------------------------------------------------------------
# Numeros
# --------------------------------------------------------------------------

_NUM_RE = re.compile(r"^[+-]?\d{1,3}(?:[ .]\d{3})*(?:[.,]\d+)?$|^[+-]?\d+(?:[.,]\d+)?$")
_FRACTION_RE = re.compile(r"^([0-9]+(?:[.,][0-9]+)?)\s*/\s*([0-9]+(?:[.,][0-9]+)?)$")


def parse_number(value: Any) -> Optional[float]:
    """Le um numero escrito a portuguesa ou a inglesa. None se nao for numero."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = clean_text(value)
    if not text:
        return None

    text = text.replace("%", "").strip()
    fraction = _FRACTION_RE.match(text)
    if fraction:
        num = parse_number(fraction.group(1))
        den = parse_number(fraction.group(2))
        return num if (num is not None and den) else None

    candidate = text.replace(" ", "")
    if not _NUM_RE.match(candidate):
        return None

    if "," in candidate and "." in candidate:
        # O separador decimal e o ultimo que aparece.
        if candidate.rfind(",") > candidate.rfind("."):
            candidate = candidate.replace(".", "").replace(",", ".")
        else:
            candidate = candidate.replace(",", "")
    else:
        candidate = candidate.replace(",", ".")

    try:
        return float(candidate)
    except ValueError:
        return None


_ID_RE = re.compile(r"^\d{4,12}$")


def parse_student_id(value: Any) -> Optional[str]:
    """Extrai um numero de aluno plausivel de uma celula."""
    text = clean_text(value)
    if not text:
        return None
    text = text.replace(" ", "")
    text = re.sub(r"^(ist|n\.?|no|nº)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[^0-9]", "", text)
    if _ID_RE.match(text):
        return text.lstrip("0") or "0"
    return None


_ID_IN_NAME_RE = re.compile(r"^\s*(\d{4,12})\s*[-–.:]?\s+(\D.*)$|^(.*\D)\s+(\d{4,12})\s*$")


def split_id_from_name(value: Any):
    """Separa "112233 Ana Maria Silva" em ``("112233", "Ana Maria Silva")``.

    Ha pautas que trazem o numero e o nome na mesma coluna. Devolve
    ``(None, texto)`` quando nao ha numero para separar.
    """
    text = clean_text(value)
    match = _ID_IN_NAME_RE.match(text)
    if not match:
        return None, text
    student_id, name = (match.group(1), match.group(2)) if match.group(1) else \
                       (match.group(4), match.group(3))
    name = clean_text(name)
    if not looks_like_person_name(name):
        return None, text
    return parse_student_id(student_id), name


# --------------------------------------------------------------------------
# Notas e estados
# --------------------------------------------------------------------------

#: Estados nao numericos, do "melhor" para o "pior".
STATUS_ORDER = ["APROVADO", "REPROVADO", "FALTOU", "DESISTIU", "NAO_ADMITIDO", "SEM_NOTA"]

STATUS_LABELS = {
    "APROVADO": "Aprovado",
    "REPROVADO": "Reprovado",
    "FALTOU": "Faltou",
    "DESISTIU": "Desistiu",
    "NAO_ADMITIDO": "Nao admitido",
    "SEM_NOTA": "—",
}

_STATUS_TOKENS = {
    "re": "REPROVADO",
    "rep": "REPROVADO",
    "repr": "REPROVADO",
    "reprovado": "REPROVADO",
    "reprovada": "REPROVADO",
    "nao aprovado": "REPROVADO",
    "insuficiente": "REPROVADO",
    "ap": "APROVADO",
    "apr": "APROVADO",
    "aprovado": "APROVADO",
    "aprovada": "APROVADO",
    "na": "NAO_ADMITIDO",
    "n a": "NAO_ADMITIDO",
    "nadm": "NAO_ADMITIDO",
    "nao admitido": "NAO_ADMITIDO",
    "nao admitida": "NAO_ADMITIDO",
    "nao avaliado": "NAO_ADMITIDO",
    "sem frequencia": "NAO_ADMITIDO",
    "excluido": "NAO_ADMITIDO",
    "fa": "FALTOU",
    "falta": "FALTOU",
    "faltou": "FALTOU",
    "f": "FALTOU",
    "ausente": "FALTOU",
    "aus": "FALTOU",
    "nc": "FALTOU",
    "nao compareceu": "FALTOU",
    "des": "DESISTIU",
    "desistiu": "DESISTIU",
    "desistente": "DESISTIU",
    "anulada": "DESISTIU",
    "anulado": "DESISTIU",
}

_EMPTY_TOKENS = {"", "-", "--", "---", "n/d", "nd", "s/n", "sn", ".", "/", "x"}


@dataclass
class Grade:
    """Uma nota: valor numerico, ou um estado, ou nada."""

    value: Optional[float] = None
    status: Optional[str] = None
    raw: str = ""
    scale: float = 20.0

    @property
    def is_empty(self) -> bool:
        return self.value is None and (self.status is None or self.status == "SEM_NOTA")

    @property
    def label(self) -> str:
        if self.value is not None:
            return format_grade(self.value)
        if self.status:
            return STATUS_LABELS.get(self.status, self.status)
        return "—"

    def rank(self):
        """Ordena notas: numerico ganha a estado; estado pelo STATUS_ORDER."""
        if self.value is not None:
            return (2, self.value)
        if self.status and self.status in STATUS_ORDER:
            return (1, float(len(STATUS_ORDER) - STATUS_ORDER.index(self.status)))
        return (0, 0.0)

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "status": self.status,
            "raw": self.raw,
            "scale": self.scale,
            "label": self.label,
        }


def parse_grade(value: Any, scale: float = 20.0) -> Grade:
    """Interpreta uma celula de nota (numero, "RE", "NA", "-", vazio...)."""
    raw = clean_text(value)
    number = parse_number(value)
    if number is not None:
        return Grade(value=number, raw=raw, scale=scale)

    key = norm_text(raw)
    if key in _EMPTY_TOKENS:
        return Grade(status="SEM_NOTA", raw=raw, scale=scale)

    compact = _NON_ALNUM_RE.sub(" ", key).strip()
    status = _STATUS_TOKENS.get(compact) or _STATUS_TOKENS.get(compact.replace(" ", ""))
    if status:
        return Grade(status=status, raw=raw, scale=scale)

    # Coisas como "RE (12,5)" ou "Aprovado 14".
    inner = re.search(r"\d+(?:[.,]\d+)?", raw)
    if inner and len(raw) <= 24:
        number = parse_number(inner.group(0))
        for token, mapped in _STATUS_TOKENS.items():
            if compact.startswith(token + " ") or compact.endswith(" " + token):
                return Grade(value=number, status=mapped, raw=raw, scale=scale)
        if number is not None:
            return Grade(value=number, raw=raw, scale=scale)

    return Grade(status="SEM_NOTA", raw=raw, scale=scale)


def format_grade(value: Optional[float]) -> str:
    """13.0 -> "13"; 13.25 -> "13,25" (formato portugues)."""
    if value is None:
        return "—"
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def round_grade(value: Optional[float]):
    """Arredondamento oficial (meia unidade arredonda para cima)."""
    if value is None:
        return None
    return int(math.floor(value + 0.5))

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

from .i18n import DEFAULT_LANGUAGE, status_label

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
    text = _CAMEL_RE.sub(" ", text)
    return _WS_RE.sub(" ", strip_accents(text).lower()).strip()


def norm_header(value: Any) -> str:
    """Chave de cabecalho: so letras/numeros separados por um espaco."""
    return _NON_ALNUM_RE.sub(" ", norm_text(value)).strip()


_GLUED_RE = re.compile(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])")
#: "SemestreTeste" -- ha PDFs onde duas palavras seguidas saem sem espaco.
_CAMEL_RE = re.compile(r"(?<=[a-zà-ÿ])(?=[A-ZÀ-Þ])")


def split_glued(text: str) -> str:
    """Separa letras de digitos: "Max1" -> "max 1", "Epoca1" -> "epoca 1"."""
    return _WS_RE.sub(" ", _GLUED_RE.sub(" ", text)).strip()


def header_variants(value: Any) -> list:
    """As duas formas de um cabecalho: como esta, e com letras e digitos
    separados. Ha pautas que escrevem "Test 1" e outras "Test1"."""
    header = norm_header(value)
    glued = split_glued(header)
    return [header] if glued == header else [header, glued]


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


#: Separadores que aparecem entre o numero e o nome quando vem na mesma
#: celula: espaco, mas tambem "-", "|", "/", ":" e companhia, com ou sem espaco.
_ID_NAME_SEP = r"(?:\s*[-–—.:|/]\s*|\s+)"
_ID_PREFIX = r"(?:n\.?[ºo°]?\s*)?"
_ID_THEN_NAME = re.compile(
    rf"^{_ID_PREFIX}(\d{{4,12}}){_ID_NAME_SEP}(\D.+)$", re.IGNORECASE)
_NAME_THEN_ID = re.compile(
    rf"^(.+?\D){_ID_NAME_SEP}{_ID_PREFIX}(\d{{4,12}})$", re.IGNORECASE)


def split_id_from_name(value: Any):
    """Separa "112233 Ana Maria Silva" em ``("112233", "Ana Maria Silva")``.

    Ha pautas que trazem o numero e o nome na mesma coluna. Devolve
    ``(None, texto)`` quando nao ha numero para separar.
    """
    text = clean_text(value)
    for pattern, first_is_id in ((_ID_THEN_NAME, True), (_NAME_THEN_ID, False)):
        match = pattern.match(text)
        if not match:
            continue
        student_id, name = ((match.group(1), match.group(2)) if first_is_id
                            else (match.group(2), match.group(1)))
        name = clean_text(name)
        # O nome tem de ser mesmo um nome: sem isto, "2024 15" seria separado.
        if looks_like_person_name(name):
            return parse_student_id(student_id), name
    return None, text


def looks_like_id_and_name(value: Any) -> bool:
    """A celula traz o numero e o nome juntos ("122631 Ana Silva")?"""
    student_id, name = split_id_from_name(value)
    return bool(student_id and name)


# --------------------------------------------------------------------------
# Notas e estados
# --------------------------------------------------------------------------

#: Estados nao numericos, do "melhor" para o "pior".
STATUS_ORDER = ["APROVADO", "REPROVADO", "FALTOU", "DESISTIU", "NAO_ADMITIDO", "SEM_NOTA"]

STATUS_LABELS = {status: status_label(status) for status in STATUS_ORDER}

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
    "d": "DESISTIU",
    "withdrawal": "DESISTIU",
    "withdrawn": "DESISTIU",
    # Pautas em ingles: f = falta de comparencia, m = nao atingiu a nota minima,
    # NA = nao avaliado, RE = reprovado.
    "m": "REPROVADO",
    "failed": "REPROVADO",
    "fail": "REPROVADO",
    "not assessed": "NAO_ADMITIDO",
    "n a": "NAO_ADMITIDO",
    "absent": "FALTOU",
    "passed": "APROVADO",
    "pass": "APROVADO",
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
        return self.label_in()

    def label_in(self, lang: str = DEFAULT_LANGUAGE) -> str:
        if self.value is not None:
            return format_grade(self.value)
        if self.status:
            return status_label(self.status, lang)
        return "—"

    def rank(self):
        """Ordena notas: numerico ganha a estado; estado pelo STATUS_ORDER."""
        if self.value is not None:
            return (2, self.value)
        if self.status and self.status in STATUS_ORDER:
            return (1, float(len(STATUS_ORDER) - STATUS_ORDER.index(self.status)))
        return (0, 0.0)

    def to_dict(self, lang: str = DEFAULT_LANGUAGE) -> dict:
        return {
            "value": self.value,
            "status": self.status,
            "raw": self.raw,
            "scale": self.scale,
            "label": self.label_in(lang),
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

    # Estados compostos: "RE m" e reprovado por nao ter atingido a nota minima.
    tokens = compact.split()
    if 1 < len(tokens) <= 3:
        mapped = [_STATUS_TOKENS.get(t) for t in tokens]
        if all(mapped):
            worst = min(mapped, key=lambda st: STATUS_ORDER.index(st))
            return Grade(status=worst, raw=raw, scale=scale)

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

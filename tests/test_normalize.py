"""Leitura de numeros, nomes e notas escritas de todas as maneiras."""

import pytest

from gradeorg.normalize import (
    Grade, format_grade, looks_like_id_and_name, looks_like_person_name,
    norm_header, norm_name, parse_grade, parse_number, parse_student_id,
    round_grade, split_id_from_name, title_name,
)


@pytest.mark.parametrize("raw,expected", [
    ("13,25", 13.25), ("13.25", 13.25), ("18", 18.0), ("1 234,5", 1234.5),
    ("85%", 85.0), ("  9,5  ", 9.5), ("15/20", 15.0), ("-", None),
    ("RE", None), ("", None), (None, None), ("abc", None), (17, 17.0), (True, None),
])
def test_parse_number(raw, expected):
    assert parse_number(raw) == expected


@pytest.mark.parametrize("raw,value,status", [
    ("13,25", 13.25, None),
    ("RE", None, "REPROVADO"),
    ("Reprovado", None, "REPROVADO"),
    ("NA", None, "NAO_ADMITIDO"),
    ("Não admitido", None, "NAO_ADMITIDO"),
    ("FA", None, "FALTOU"),
    ("Faltou", None, "FALTOU"),
    ("Desistiu", None, "DESISTIU"),
    ("Aprovado", None, "APROVADO"),
    ("-", None, "SEM_NOTA"),
    ("", None, "SEM_NOTA"),
    (None, None, "SEM_NOTA"),
])
def test_parse_grade(raw, value, status):
    grade = parse_grade(raw)
    assert grade.value == value
    assert grade.status == status


def test_parse_grade_com_estado_e_numero():
    grade = parse_grade("RE (12,5)")
    assert grade.status == "REPROVADO"
    assert grade.value == 12.5


def test_ordem_das_notas():
    """Um numero vale sempre mais do que um estado; entre estados ha hierarquia."""
    assert parse_grade("10").rank() > parse_grade("Aprovado").rank()
    assert parse_grade("Aprovado").rank() > parse_grade("RE").rank()
    assert parse_grade("RE").rank() > parse_grade("NA").rank()
    assert parse_grade("NA").rank() > parse_grade("-").rank()
    assert parse_grade("18").rank() > parse_grade("9").rank()


@pytest.mark.parametrize("raw,expected", [
    ("122631", "122631"), ("IST 122631", "122631"), ("nº 78729", "78729"),
    ("0012345", "12345"), ("12", None), ("abc", None), ("", None),
])
def test_parse_student_id(raw, expected):
    assert parse_student_id(raw) == expected


def test_nomes_com_e_sem_acentos_dao_a_mesma_chave():
    assert norm_name("João Álvaro-Silva") == norm_name("Joao Alvaro Silva")
    assert norm_name("  MARIA   DO   CARMO ") == "maria do carmo"


def test_norm_header():
    assert norm_header("Nº Aluno") == "n aluno"
    assert norm_header("Avaliação Final 2") == "avaliacao final 2"


@pytest.mark.parametrize("raw,expected", [
    ("Afonso Duarte Rosado Lopes", True),
    ("Sofia He", True),
    ("122631", False),
    ("13,5", False),
    ("Ana", False),
])
def test_looks_like_person_name(raw, expected):
    assert looks_like_person_name(raw) is expected


def test_title_name_respeita_particulas():
    assert title_name("JOAO DE ALMEIDA") == "Joao de Almeida"
    assert title_name("Ana Maria") == "Ana Maria"


@pytest.mark.parametrize("value,expected", [(15.5, 16), (13.24, 13), (9.5, 10), (None, None)])
def test_round_grade(value, expected):
    assert round_grade(value) == expected


def test_format_grade_usa_virgula():
    assert format_grade(16.0) == "16"
    assert format_grade(13.25) == "13,25"
    assert format_grade(None) == "—"


def test_grade_label():
    assert Grade(value=14.5).label == "14,5"
    assert Grade(status="REPROVADO").label == "Reprovado"


# -- número e nome na mesma célula -----------------------------------------

@pytest.mark.parametrize("celula", [
    "122631 Afonso Duarte Rosado Lopes",
    "Afonso Duarte Rosado Lopes 122631",
    "122631-Afonso Duarte Rosado Lopes",
    "122631 - Afonso Duarte Rosado Lopes",
    "122631|Afonso Duarte Rosado Lopes",
    "122631/Afonso Duarte Rosado Lopes",
    "122631: Afonso Duarte Rosado Lopes",
    "nº 122631 Afonso Duarte Rosado Lopes",
    "Afonso Duarte Rosado Lopes - 122631",
    "122631  Afonso   Duarte Rosado Lopes",
    "122631Afonso Duarte Rosado Lopes",   # colados, sem espaço nenhum
])
def test_separa_o_numero_do_nome_em_varios_formatos(celula):
    numero, nome = split_id_from_name(celula)
    assert numero == "122631"
    assert nome == "Afonso Duarte Rosado Lopes"


@pytest.mark.parametrize("celula", [
    "Afonso Duarte Rosado Lopes",   # só nome
    "122631",                       # só número
    "13,25 15,5",                   # duas notas
    "2024 15",                      # não é nome nenhum
    "Turma ET-C9",
    "12345abc def",                 # colado a minúscula: não é nome a começar
])
def test_nao_separa_o_que_nao_e_numero_mais_nome(celula):
    assert split_id_from_name(celula)[0] is None


def test_separa_o_numero_do_nome_colado_com_acento():
    """A maiúscula que abre o nome é o corte, acentuada ou não."""
    assert split_id_from_name("110641Ávila Nunes Pinto") == ("110641", "Ávila Nunes Pinto")


def test_reconhece_a_celula_com_numero_e_nome():
    assert looks_like_id_and_name("122631 Afonso Duarte Rosado Lopes")
    assert looks_like_id_and_name("122631Afonso Duarte Rosado Lopes")
    assert not looks_like_id_and_name("Afonso Duarte Rosado Lopes")

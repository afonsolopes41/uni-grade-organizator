"""Pautas em inglês e ajustes manuais.

Uma pauta do ISCTE em inglês usa «Number», «Name», «Date», «Grade», «Test 1» e
símbolos de uma letra (f, d, m) que não existem nas pautas em português.
"""

import pytest

from gradeorg.consolidate import consolidate
from gradeorg.detect import apply_column_overrides, build_source, guess_subject
from gradeorg.models import (
    EPOCA_1, EPOCA_2, KIND_COMPONENT, KIND_FINAL, RawTable,
)
from gradeorg.normalize import parse_grade
from gradeorg.session import Session

PAUTA_INGLES = (
    "Number;Name;Date;Grade;Test 1;Test 2;Max1;Max2\n"
    "38016;Filipe Rito Neves;2-Jun-2026;NA;f;f;f;f\n"
    "65074;Sergiy Nytsulenko;2-Jun-2026;11;3.6;11.3;18.0;17.7\n"
    "70033;Filipe Tavares Bernardino;2-Jun-2026;14;9.5;14.0;18.4;17.7\n"
    "110331;Francisco Vaz Monteiro;2-Jun-2026;RE m;7.0;f;19.7;18.9\n"
).encode()


def carrega(nome="Assessment_SGR_1st Season.csv", conteudo=PAUTA_INGLES):
    session = Session()
    session.add_file(nome, conteudo)
    return session


def column(source, header):
    return next(c for c in source.columns if c.header == header)


# -- símbolos de uma letra -------------------------------------------------

@pytest.mark.parametrize("raw,status", [
    ("f", "FALTOU"),            # failure for nonattendance
    ("d", "DESISTIU"),          # withdrawal by the student
    ("m", "REPROVADO"),         # minimum passing grade not attained
    ("NA", "NAO_ADMITIDO"),     # not assessed
    ("RE", "REPROVADO"),
    ("Not Assessed", "NAO_ADMITIDO"),
    ("Failed", "REPROVADO"),
])
def test_simbolos_das_pautas_em_ingles(raw, status):
    assert parse_grade(raw).status == status


def test_nota_composta_re_m():
    """"RE m" é reprovado por não ter atingido a nota mínima."""
    grade = parse_grade("RE m")
    assert grade.status == "REPROVADO"
    assert grade.value is None


# -- vocabulário -----------------------------------------------------------

def test_papeis_das_colunas_em_ingles():
    source = carrega().sources[0]
    assert column(source, "Number").role == "id"
    assert column(source, "Name").role == "name"
    assert column(source, "Date").role == "ignore"
    assert column(source, "Grade").kind == KIND_FINAL
    assert column(source, "Test 1").kind == KIND_COMPONENT
    assert column(source, "Max1").kind == KIND_COMPONENT


def test_1st_season_e_a_primeira_epoca():
    source = carrega().sources[0]
    assert column(source, "Grade").epoca == EPOCA_1


def test_2nd_season_e_a_segunda_epoca():
    source = carrega("Assessment_SGR_2nd Season.csv").sources[0]
    assert column(source, "Grade").epoca == EPOCA_2


def test_test_2_e_componente_da_mesma_epoca_numa_pauta_de_1st_season():
    """A pauta já diz que época é: «Test 2» é o 2.º teste, não o recurso."""
    source = carrega().sources[0]
    assert column(source, "Test 2").epoca == EPOCA_1
    assert column(source, "Test 2").kind == KIND_COMPONENT


def test_cabecalhos_colados_tambem_contam():
    """Há pautas que escrevem «Test1» e «Max1» sem espaço."""
    source = carrega(conteudo=(
        "Number;Name;Grade;Test1;Max1\n"
        "65074;Sergiy Nytsulenko;11;3.6;18.0\n"
        "70033;Filipe Bernardino;14;9.5;18.4\n").encode()).sources[0]
    assert column(source, "Grade").kind == KIND_FINAL
    assert column(source, "Test1").kind == KIND_COMPONENT


def test_notas_lidas_corretamente():
    resultado = carrega().result()
    por_nome = {s["name"]: s for s in resultado["students"]}
    assert por_nome["Sergiy Nytsulenko"]["subjects"]["SGR"]["best"]["label"] == "11"
    assert por_nome["Francisco Vaz Monteiro"]["subjects"]["SGR"]["best"]["label"] == "Reprovado"
    assert por_nome["Filipe Rito Neves"]["subjects"]["SGR"]["approved"] is False


# -- unidade curricular no meio do ruído ----------------------------------

def test_uc_escolhida_entre_instituicao_e_legenda():
    """O nome da cadeira é só mais um pedaço no meio do cabeçalho da página."""
    guess = guess_subject("pauta.pdf", RawTable(
        rows=[["Name", "Grade"], ["Ana Silva", "14"]],
        title_lines=[
            "ISCTE - University Institute of Lisbon",
            "f - Failure for nonattendance",
            "03713 - SGR - Network Security and Management",
            "2nd Semester 1st Season",
            "Assessment review: 3pm, Monday, Jun 8th, 2026 - Office D622",
        ]))
    assert guess.value == "Network Security and Management"
    assert guess.confidence >= 0.8


def test_titulo_com_ano_lectivo_fica_sem_o_ano():
    guess = guess_subject("pauta.pdf", RawTable(
        rows=[["Nome", "Nota"], ["Ana Silva", "14"]],
        title_lines=["Projeto de Sistemas de Telecomunicações - Pauta 2025/2026"]))
    assert guess.value == "Projeto de Sistemas de Telecomunicações"


# -- ajustes manuais -------------------------------------------------------

def test_ajuste_manual_de_coluna_muda_mesmo_o_resultado():
    """O ajuste avançado não pegava: os agrupamentos por época ficavam velhos."""
    session = carrega()
    source_id = session.sources[0].id
    indice = column(session.sources[0], "Test 2").index

    session.update(overrides={source_id: {
        str(indice): {"epoca": "epoca2", "kind": "final"}}})

    sergiy = next(s for s in session.result()["students"]
                  if s["name"] == "Sergiy Nytsulenko")
    epocas = sergiy["subjects"]["SGR"]["epocas"]
    assert epocas[EPOCA_1]["grade"]["label"] == "11"
    assert epocas[EPOCA_2]["grade"]["label"] == "11,3"
    assert sergiy["subjects"]["SGR"]["best"]["label"] == "11,3"


def test_momento_pode_ser_escolhido_a_mao():
    """Dizer «esta coluna é o Teste 2» mesmo sem a aplicação ter perguntado."""
    session = carrega()
    source_id = session.sources[0].id
    indice = column(session.sources[0], "Test 2").index

    session.update(overrides={source_id: {str(indice): {"moment": "2"}}})
    assert column(session.sources[0], "Test 2").moment == 2

    session.update(overrides={source_id: {str(indice): {"moment": ""}}})
    assert column(session.sources[0], "Test 2").moment is None


def test_coluna_ignorada_pode_passar_a_nota():
    source = build_source("s1", "pauta.csv", "csv", RawTable(
        rows=[["Nome", "Observações", "Nota Final"],
              ["Ana Silva", "12", "14"],
              ["Rui Costa", "10", "12"]],
        title_lines=["Física - Pauta"]))
    assert column(source, "Observações").role == "ignore"

    apply_column_overrides([source], {"s1": {"1": {
        "role": "grade", "epoca": EPOCA_2, "kind": "final"}}})
    assert column(source, "Observações").kind == KIND_FINAL

    ana = next(s for s in consolidate([source])["students"]
               if s["name"] == "Ana Silva")
    assert ana["subjects"]["Física"]["epocas"][EPOCA_2]["grade"].label == "12"

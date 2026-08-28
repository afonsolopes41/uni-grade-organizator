"""Deteccao de cabecalhos, papeis de coluna, epocas e unidades curriculares."""

import pytest

from gradeorg.detect import (
    build_questions, build_source, epoca_from_text, find_header_row, guess_subject,
)
from gradeorg.models import EPOCA_1, EPOCA_2, EPOCA_ESP, KIND_FINAL, RawTable


def table(rows, **kwargs):
    return RawTable(rows=rows, **kwargs)


def source(rows, filename="pauta.xlsx", **kwargs):
    return build_source("s1", filename, "xlsx", table(rows, **kwargs))


def column(src, header):
    return next(c for c in src.columns if c.header == header)


# -- cabecalho -------------------------------------------------------------

def test_encontra_cabecalho_depois_de_linhas_de_titulo():
    rows = [
        ["Pauta de Análise Matemática", "", ""],
        ["", "", ""],
        ["Nome", "Nº Aluno", "Nota Final"],
        ["Ana Maria Silva", "112233", "14"],
        ["Rui Costa Lopes", "112234", "9"],
    ]
    assert find_header_row([r for r in rows if any(r)]) == 1


def test_linha_de_dados_nao_e_confundida_com_cabecalho():
    rows = [["Nome", "Nº", "Nota"], ["Ana Maria Silva", "112233", "14"]]
    assert find_header_row(rows) == 0


# -- papeis das colunas ----------------------------------------------------

def test_papeis_basicos():
    src = source([
        ["Nome", "Nº Aluno", "Nota Final"],
        ["Ana Maria Silva", "112233", "14"],
        ["Rui Costa Lopes", "112234", "9,5"],
    ])
    assert column(src, "Nome").role == "name"
    assert column(src, "Nº Aluno").role == "id"
    assert column(src, "Nota Final").role == "grade"
    assert column(src, "Nota Final").kind == KIND_FINAL


def test_coluna_so_com_estados_conta_como_nota():
    """Uma época onde quase ninguém foi está cheia de "-" e continua a ser nota."""
    src = source([
        ["Nome", "Teste 2", "Nota Final 2"],
        ["Ana Maria Silva", "-", "-"],
        ["Rui Costa Lopes", "12", "13"],
        ["Ines Santos Dias", "-", "-"],
        ["Tomas Reis Pinto", "RE", "RE"],
    ])
    assert column(src, "Teste 2").role == "grade"
    assert column(src, "Nota Final 2").role == "grade"
    assert column(src, "Nota Final 2").kind == KIND_FINAL
    # Sem um momento anterior no ficheiro não dá para saber que época é: pergunta-se.
    assert any(q.type == "moment" for q in build_questions([src]))


def test_coluna_vazia_e_ignorada():
    src = source([
        ["Nome", "Exame 2", "Nota Final"],
        ["Ana Maria Silva", "", "14"],
        ["Rui Costa Lopes", "", "12"],
    ])
    assert column(src, "Exame 2").role == "ignore"


def test_sem_cabecalho_util_ainda_encontra_o_nome():
    src = source([
        ["A", "B", "C"],
        ["Ana Maria Silva", "112233", "14"],
        ["Rui Costa Lopes", "112234", "12"],
    ])
    assert column(src, "A").role == "name"


# -- epocas ----------------------------------------------------------------

@pytest.mark.parametrize("text,epoca,strength", [
    ("2.ª Época", EPOCA_2, "strong"),
    ("Época de recurso", EPOCA_2, "strong"),
    ("Época Especial", EPOCA_ESP, "strong"),
    ("1E", EPOCA_1, "strong"),
    ("Teste 1", EPOCA_1, "weak"),        # o 1.º teste só existe na 1.ª época
    ("Avaliação Final", None, None),
    ("Ex 2", None, None),
    # Um "2" no cabeçalho não diz a época: o 2.º teste é no dia do exame de
    # 1.ª época, mas o mesmo rótulo também aparece em pautas de recurso.
    ("Teste 2", None, None),
    ("Nota Final 2", None, None),
])
def test_epoca_from_text(text, epoca, strength):
    assert epoca_from_text(text) == (epoca, strength)


@pytest.mark.parametrize("text,moment", [
    ("Teste 2", 2), ("Nota Final 2", 2), ("Avaliação Final 2", 2), ("Exame 2", 2),
    ("Teste 3", 3), ("Ex 2", None), ("Ex 4b", None), ("Teste 1", None),
    ("Nota Final", None), ("Q2", None),
])
def test_moment_index(text, moment):
    from gradeorg.detect import moment_index
    assert moment_index(text) == moment


def test_blocos_de_epoca_num_pdf_com_duas_epocas():
    """Colunas sem marca herdam a época do bloco que vem à esquerda."""
    src = source([
        ["Nome", "Projeto", "Teste 1", "Nota Final", "Teste 2", "Nota Final 2"],
        ["Ana Maria Silva", "17", "13,25", "15,5", "-", "-"],
        ["Rui Costa Lopes", "16", "5", "RE", "12", "14"],
    ], filename="pauta.pdf")
    assert column(src, "Projeto").epoca is None       # componente comum
    assert column(src, "Teste 1").epoca == EPOCA_1
    assert column(src, "Nota Final").epoca == EPOCA_1
    assert column(src, "Teste 2").epoca == EPOCA_2
    assert column(src, "Nota Final 2").epoca == EPOCA_2
    assert column(src, "Nota Final 2").kind == KIND_FINAL


def test_epoca_do_ficheiro_impede_falsas_epocas_nas_colunas():
    """Numa pauta de 1.ª época, "Exame 2" é a 2.ª prova, não a 2.ª época."""
    src = source([
        ["Nome", "Exame 1", "Exame 2", "Nota Final"],
        ["Ana Maria Silva", "13", "15", "14"],
        ["Rui Costa Lopes", "11", "12", "12"],
    ], filename="Pauta_ALG_1E.xlsx")
    for header in ("Exame 1", "Exame 2", "Nota Final"):
        assert column(src, header).epoca == EPOCA_1


def test_componente_comum_nao_vira_nota_final():
    src = source([
        ["Nome", "Projeto", "Teste 1", "Avaliação Final"],
        ["Ana Maria Silva", "17", "13", "15"],
        ["Rui Costa Lopes", "16", "11", "13"],
    ])
    assert column(src, "Projeto").kind != KIND_FINAL
    assert column(src, "Avaliação Final").kind == KIND_FINAL


def test_avaliacao_final_ganha_a_nota_final():
    src = source([
        ["Nome", "Nota Final", "Avaliação Final"],
        ["Ana Maria Silva", "15,5", "16"],
        ["Rui Costa Lopes", "13,6", "14"],
    ])
    assert column(src, "Avaliação Final").kind == KIND_FINAL
    assert column(src, "Nota Final").kind != KIND_FINAL


# -- unidade curricular ----------------------------------------------------

def test_uc_a_partir_do_titulo_do_documento():
    guess = guess_subject("pauta.pdf", table(
        [["Nome", "Nota"], ["Ana Maria Silva", "14"]],
        title_lines=["Projeto de Sistemas de Telecomunicações - Pauta 2025/2026"]))
    assert guess.value == "Projeto de Sistemas de Telecomunicações"
    assert guess.confidence >= 0.8


def test_uc_a_partir_de_sigla_no_nome_do_ficheiro():
    guess = guess_subject("Pauta_SCSFM_2025_2026_1E.xlsx", table(
        [["Nome", "Nota"], ["Ana Maria Silva", "14"]]))
    assert guess.value == "SCSFM"
    assert guess.confidence < 0.6      # baixa: tem de ser confirmada


def test_uc_desconhecida_quando_o_nome_nao_diz_nada():
    guess = guess_subject("Notas_da_primeira_epoca.xlsx", table(
        [["Nome", "Nota"], ["Ana Maria Silva", "14"]]))
    assert guess.value is None


# -- perguntas -------------------------------------------------------------

def test_uc_por_identificar_gera_pergunta():
    src = source([
        ["Nome", "Total"],
        ["Ana Maria Silva", "14"],
    ], filename="Notas_da_primeira_epoca.xlsx")
    questions = build_questions([src])
    assert any(q.type == "subject" and q.severity == "warning" for q in questions)


def test_duas_candidatas_a_nota_final_geram_pergunta():
    src = source([
        ["Nome", "Teste 1", "Nota Final", "Avaliação Final"],
        ["Ana Maria Silva", "13", "15,5", "16"],
        ["Rui Costa Lopes", "11", "13,6", "14"],
    ], title_lines=["Análise Matemática - Pauta"])
    questions = build_questions([src])
    finals = [q for q in questions if q.type == "final_column"]
    assert finals and {o["label"] for o in finals[0].options} >= {"Nota Final", "Avaliação Final"}


def test_epoca_desconhecida_gera_pergunta_com_saida_para_componente():
    src = source([
        ["Nome", "Projeto"],
        ["Ana Maria Silva", "17"],
        ["Rui Costa Lopes", "16"],
    ], title_lines=["Análise Matemática - Pauta"])
    questions = [q for q in build_questions([src]) if q.type == "epoca"]
    assert questions
    assert "component" in {o["value"] for o in questions[0].options}


# -- escolhas do utilizador ------------------------------------------------

def test_escolha_do_utilizador_nao_e_desfeita_pela_deteccao():
    """A detecção volta a correr a cada mudança: não pode reverter o utilizador."""
    from gradeorg.detect import apply_answers, apply_column_overrides
    from gradeorg.models import KIND_COMPONENT

    src = source([
        ["Nome", "Projeto"],
        ["Ana Maria Silva", "17"],
        ["Rui Costa Lopes", "16"],
    ], title_lines=["Análise Matemática - Pauta"])
    # Sem ajuda, "Projeto" é promovida a nota final (é a única coluna de notas).
    assert column(src, "Projeto").kind == KIND_FINAL

    apply_answers([src], {"s1:epoca": "component"})
    apply_column_overrides([src], {})       # volta a passar pelo _pick_final_columns
    assert column(src, "Projeto").kind == KIND_COMPONENT
    assert column(src, "Projeto").locked is True


def test_override_manual_de_coluna_sobrevive_a_redeteccao():
    from gradeorg.detect import apply_column_overrides

    src = source([
        ["Nome", "Teste 1", "Nota Final", "Avaliação Final"],
        ["Ana Maria Silva", "13", "15,5", "16"],
    ], title_lines=["Análise Matemática - Pauta"])
    assert column(src, "Avaliação Final").kind == KIND_FINAL

    apply_column_overrides([src], {"s1": {"2": {"kind": "final"}}})
    assert column(src, "Nota Final").kind == KIND_FINAL
    assert column(src, "Nota Final").locked is True

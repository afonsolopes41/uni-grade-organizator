"""Modalidades de avaliação.

Em muitas cadeiras a 1.ª época faz-se por dois testes/frequências. O 2.º teste
é no mesmo dia do exame de 1.ª época — quem correu mal no 1.º teste, ou não o
pôde fazer, vai a exame em vez do 2.º teste. Só quem chumba nessa época é que
vai à 2.ª época, que é sempre exame, tal como a época especial.

Daqui vem a ambiguidade central: uma coluna «Teste 2» tanto pode ser o segundo
teste da 1.ª época como o recurso. Decide-se pelos dados e confirma-se com o
utilizador.
"""

from gradeorg.consolidate import Settings, consolidate
from gradeorg.detect import apply_answers, build_questions, build_source, moment_index
from gradeorg.models import (
    EPOCA_1, EPOCA_2, EPOCA_ESP, KIND_FINAL, ROUTE_CONTINUA, ROUTE_EXAME, RawTable,
)


def source(rows, filename="pauta.pdf", titulo="Análise Matemática - Pauta"):
    return build_source("s1", filename, "pdf", RawTable(rows=rows, title_lines=[titulo]))


def column(src, header):
    return next(c for c in src.columns if c.header == header)


def student(result, name):
    return next(s for s in result["students"] if s["name"] == name)


# Só quem chumbou no 1.º momento tem nota no 2.º: assinatura do recurso.
PAUTA_RECURSO = [
    ["Nome", "Projeto", "Teste 1", "Nota Final", "Teste 2", "Nota Final 2"],
    ["Ana Maria Silva", "17", "13", "15", "-", "-"],
    ["Rui Costa Lopes", "16", "5", "RE", "12", "13"],
    ["Ines Santos Dias", "15", "14", "15", "-", "-"],
    ["Tomas Reis Pinto", "14", "4", "RE", "11", "13"],
    ["Sofia Nunes Melo", "18", "16", "17", "-", "-"],
    ["Hugo Pires Sena", "15", "15", "15", "-", "-"],
]

# A turma toda faz o 2.º teste: é avaliação contínua, tudo na 1.ª época.
PAUTA_CONTINUA = [
    ["Nome", "Teste 1", "Teste 2", "Nota Final"],
    ["Ana Maria Silva", "13", "15", "14"],
    ["Rui Costa Lopes", "5", "12", "8,5"],
    ["Ines Santos Dias", "14", "16", "15"],
    ["Tomas Reis Pinto", "4", "11", "7,5"],
    ["Sofia Nunes Melo", "16", "18", "17"],
    ["Hugo Pires Sena", "15", "13", "14"],
]


# -- o "2" no cabeçalho não decide nada -----------------------------------

def test_teste_2_nao_e_automaticamente_segunda_epoca():
    """Era o erro do modelo antigo: "Teste 2" não quer dizer 2.ª época."""
    from gradeorg.detect import epoca_from_text
    assert epoca_from_text("Teste 2") == (None, None)
    assert epoca_from_text("Nota Final 2") == (None, None)
    assert moment_index("Teste 2") == 2


def test_ex_2_continua_a_ser_so_o_exercicio_2():
    assert moment_index("Ex 2") is None
    src = source([
        ["Nome", "Ex 1", "Ex 2", "Ex 3", "Total"],
        ["Ana Maria Silva", "1", "2", "1", "16"],
    ])
    for header in ("Ex 1", "Ex 2", "Ex 3"):
        assert column(src, header).moment in (None, 1)


# -- decisão pelos dados ---------------------------------------------------

def test_so_os_chumbados_no_segundo_momento_e_recurso():
    src = source(PAUTA_RECURSO)
    assert column(src, "Nota Final 2").epoca == EPOCA_2
    assert column(src, "Nota Final 2").route == ROUTE_EXAME
    assert "parece 2.ª época" in column(src, "Nota Final 2").evidence


def test_turma_toda_no_segundo_momento_e_a_mesma_epoca():
    src = source(PAUTA_CONTINUA)
    assert column(src, "Teste 2").epoca == EPOCA_1
    assert column(src, "Nota Final").epoca == EPOCA_1
    assert column(src, "Nota Final").kind == KIND_FINAL
    assert "2.º teste da mesma época" in column(src, "Nota Final").evidence


def test_o_segundo_momento_e_sempre_confirmado_pelo_utilizador():
    perguntas = [q for q in build_questions([source(PAUTA_RECURSO)]) if q.type == "moment"]
    assert len(perguntas) == 1
    pergunta = perguntas[0]
    assert pergunta.default == EPOCA_2
    assert {o["value"] for o in pergunta.options} == {EPOCA_1, EPOCA_2, EPOCA_ESP}
    assert pergunta.detail                      # traz a evidência dos dados


def test_utilizador_pode_corrigir_o_veredicto():
    """O que os dados sugerem é só um palpite: quem sabe a cadeira decide."""
    src = source(PAUTA_RECURSO)
    assert column(src, "Nota Final 2").epoca == EPOCA_2

    apply_answers([src], {"s1:moment:2": EPOCA_1})
    assert column(src, "Nota Final 2").epoca == EPOCA_1
    assert column(src, "Nota Final 2").route == ROUTE_CONTINUA
    assert column(src, "Teste 2").epoca == EPOCA_1


def test_corrigido_para_epoca_especial():
    src = source(PAUTA_RECURSO)
    apply_answers([src], {"s1:moment:2": EPOCA_ESP})
    assert column(src, "Nota Final 2").epoca == EPOCA_ESP
    assert column(src, "Nota Final 2").route == ROUTE_EXAME


# -- efeito nas notas ------------------------------------------------------

def test_recurso_recupera_quem_chumbou():
    result = consolidate([source(PAUTA_RECURSO)])
    rui = student(result, "Rui Costa Lopes")["subjects"]["Análise Matemática"]
    assert rui["best"].value == 13
    assert rui["best_epoca"] == EPOCA_2
    ana = student(result, "Ana Maria Silva")["subjects"]["Análise Matemática"]
    assert ana["best_epoca"] == EPOCA_1


def test_avaliacao_continua_fica_toda_na_primeira_epoca():
    result = consolidate([source(PAUTA_CONTINUA)])
    for nome, esperado in [("Ana Maria Silva", 14), ("Rui Costa Lopes", 8.5)]:
        uc = student(result, nome)["subjects"]["Análise Matemática"]
        assert uc["best"].value == esperado
        assert set(uc["epocas"]) == {EPOCA_1}


# -- exame de 1.ª época como alternativa ao 2.º teste ----------------------

PAUTA_DUAS_VIAS = [
    ["Nome", "Teste 1", "Teste 2", "Nota Contínua", "Exame 1.ª Época", "Nota Exame"],
    ["Ana Maria Silva", "13", "15", "14", "-", "-"],
    ["Rui Costa Lopes", "5", "-", "-", "11", "11"],
    ["Ines Santos Dias", "14", "16", "15", "-", "-"],
    ["Tomas Reis Pinto", "4", "-", "-", "16", "16"],
    ["Sofia Nunes Melo", "16", "18", "17", "-", "-"],
    ["Hugo Pires Sena", "8", "-", "-", "9", "9"],
]


def test_duas_vias_na_mesma_epoca_sao_ambas_nota_final():
    """Quem tem má nota no 1.º teste vai a exame em vez do 2.º teste."""
    src = source(PAUTA_DUAS_VIAS)
    assert column(src, "Nota Contínua").kind == KIND_FINAL
    assert column(src, "Nota Exame").kind == KIND_FINAL
    assert column(src, "Nota Contínua").epoca == column(src, "Nota Exame").epoca == EPOCA_1
    # Vias diferentes: preenchidas para alunos diferentes.
    assert column(src, "Nota Contínua").cluster != column(src, "Nota Exame").cluster


def test_cada_aluno_fica_com_a_nota_da_via_que_fez():
    result = consolidate([source(PAUTA_DUAS_VIAS)])
    esperado = {
        "Ana Maria Silva": (14, "Nota Contínua"),
        "Rui Costa Lopes": (11, "Nota Exame"),
        "Tomas Reis Pinto": (16, "Nota Exame"),
        "Sofia Nunes Melo": (17, "Nota Contínua"),
    }
    for nome, (valor, coluna) in esperado.items():
        uc = student(result, nome)["subjects"]["Análise Matemática"]
        assert uc["best"].value == valor
        assert uc["epocas"][EPOCA_1]["column"] == coluna


def test_duas_representacoes_da_mesma_nota_nao_sao_vias():
    """"Nota Final" e "Avaliação Final" são a mesma nota, uma delas arredondada."""
    src = source([
        ["Nome", "Nota Final", "Avaliação Final"],
        ["Ana Maria Silva", "15,5", "16"],
        ["Rui Costa Lopes", "13,6", "14"],
    ])
    assert column(src, "Nota Final").cluster == column(src, "Avaliação Final").cluster
    assert column(src, "Avaliação Final").kind == KIND_FINAL
    assert column(src, "Nota Final").kind != KIND_FINAL


# -- nota mínima por cadeira ----------------------------------------------

def test_nota_minima_e_por_cadeira():
    a = source([["Nome", "Nota Final"], ["Ana Maria Silva", "9,4"]],
               titulo="Análise Matemática - Pauta")
    b = build_source("s2", "b.pdf", "pdf", RawTable(
        rows=[["Nome", "Nota Final"], ["Ana Maria Silva", "9,7"]],
        title_lines=["Álgebra Linear - Pauta"]), file_order=2)

    settings = Settings(pass_mark=9.5, subject_pass_marks={"Análise Matemática": 10.0})
    result = consolidate([a, b], settings)
    ana = student(result, "Ana Maria Silva")
    assert ana["subjects"]["Análise Matemática"]["approved"] is False
    assert ana["subjects"]["Análise Matemática"]["pass_mark"] == 10.0
    assert ana["subjects"]["Álgebra Linear"]["approved"] is True
    assert ana["subjects"]["Álgebra Linear"]["pass_mark"] == 9.5


def test_settings_le_e_escreve_notas_minimas_por_uc():
    settings = Settings.from_dict({"pass_mark": 9.5,
                                   "subject_pass_marks": {"Física": "10", "Química": 8}})
    assert settings.pass_mark_for("Física") == 10.0
    assert settings.pass_mark_for("Química") == 8.0
    assert settings.pass_mark_for("Outra") == 9.5
    assert settings.to_dict()["subject_pass_marks"] == {"Física": 10.0, "Química": 8.0}

    limpo = Settings.from_dict({**settings.to_dict(),
                                "subject_pass_marks": {"Física": ""}})
    assert limpo.pass_mark_for("Física") == 9.5


def test_epoca_especial_e_2a_epoca_sao_sempre_exame():
    src = build_source("s1", "pauta.pdf", "pdf", RawTable(
        rows=[["Nome", "1.ª Época", "2.ª Época", "Época Especial"],
              ["Ana Maria Silva", "8", "9", "15"]],
        title_lines=["Análise Matemática - Pauta"]))
    assert column(src, "2.ª Época").route == ROUTE_EXAME
    assert column(src, "Época Especial").route == ROUTE_EXAME


# -- o que se mostra a quem lê --------------------------------------------

def test_outras_vias_e_outros_ficheiros_sao_coisas_diferentes():
    """Uma via alternativa do mesmo ficheiro não é o mesmo que outra versão."""
    from gradeorg.consolidate import to_json

    a = source(PAUTA_DUAS_VIAS)
    b = build_source("s2", "outra.pdf", "pdf", RawTable(
        rows=[["Nome", "Nota Final"], ["Ana Maria Silva", "13"]],
        title_lines=["Análise Matemática - Pauta"],
        footer_lines=["2026/07/01"]), file_order=2)

    data = to_json(consolidate([a, b]))
    ana = next(s for s in data["students"] if s["name"] == "Ana Maria Silva")
    epoca = ana["subjects"]["Análise Matemática"]["epocas"][EPOCA_1]
    assert [v["source"] for v in epoca["other_versions"]] == ["pauta.pdf"]
    assert epoca["other_routes"] == []


def test_a_via_de_cada_epoca_vai_no_resultado():
    from gradeorg.consolidate import to_json
    data = to_json(consolidate([source(PAUTA_RECURSO)]))
    rui = next(s for s in data["students"] if s["name"] == "Rui Costa Lopes")
    epocas = rui["subjects"]["Análise Matemática"]["epocas"]
    assert epocas[EPOCA_2]["route_label"] == "Exame"

"""Juncao de alunos entre ficheiros e escolha da melhor nota."""

from gradeorg.consolidate import Settings, consolidate, to_json
from gradeorg.detect import build_source
from gradeorg.models import EPOCA_1, EPOCA_2, EPOCA_ESP, RawTable


def make_source(rows, sid="s1", filename="pauta.pdf", order=1, title=None, footer=None):
    return build_source(sid, filename, "pdf", RawTable(
        rows=rows, title_lines=title or ["Análise Matemática - Pauta 2025/2026"],
        footer_lines=footer or []), file_order=order)


def student(result, name):
    return next(s for s in result["students"] if s["name"] == name)


# -- melhor nota -----------------------------------------------------------

def test_segunda_epoca_recupera_um_reprovado():
    src = make_source([
        ["Nome", "Nº Aluno", "Teste 1", "Nota Final", "Teste 2", "Nota Final 2"],
        ["Ana Maria Silva", "112233", "5,1", "RE", "11,75", "14"],
        ["Rui Costa Lopes", "112234", "17", "18", "-", "-"],
    ])
    result = consolidate([src])
    ana = student(result, "Ana Maria Silva")["subjects"]["Análise Matemática"]
    assert ana["best"].value == 14
    assert ana["best_epoca"] == EPOCA_2
    assert ana["approved"] is True

    rui = student(result, "Rui Costa Lopes")["subjects"]["Análise Matemática"]
    assert rui["best"].value == 18
    assert rui["best_epoca"] == EPOCA_1


def test_a_melhor_nota_ganha_mesmo_estando_na_primeira_epoca():
    src = build_source("s1", "pauta.pdf", "pdf", RawTable(
        rows=[["Nome", "1.ª Época", "2.ª Época"],
              ["Ana Maria Silva", "18", "11"]],
        title_lines=["Análise Matemática - Pauta"]))
    result = consolidate([src])
    ana = student(result, "Ana Maria Silva")["subjects"]["Análise Matemática"]
    assert ana["best"].value == 18
    assert ana["best_epoca"] == EPOCA_1


def test_reprovado_nas_duas_epocas_fica_reprovado():
    src = make_source([
        ["Nome", "Teste 1", "Nota Final", "Teste 2", "Nota Final 2"],
        ["Ana Maria Silva", "5", "RE", "7", "RE"],
    ])
    result = consolidate([src])
    ana = student(result, "Ana Maria Silva")["subjects"]["Análise Matemática"]
    assert ana["best"].status == "REPROVADO"
    assert ana["approved"] is False


def test_epoca_especial_entra_na_comparacao():
    src = build_source("s1", "pauta.pdf", "pdf", RawTable(
        rows=[["Nome", "1.ª Época", "2.ª Época", "Época Especial"],
              ["Ana Maria Silva", "8", "9", "15"]],
        title_lines=["Análise Matemática - Pauta"]))
    result = consolidate([src])
    ana = student(result, "Ana Maria Silva")["subjects"]["Análise Matemática"]
    assert ana["best"].value == 15
    assert ana["best_epoca"] == EPOCA_ESP


def test_so_primeira_epoca():
    src = make_source([
        ["Nome", "Nota Final"],
        ["Ana Maria Silva", "14"],
    ])
    ana = student(consolidate([src]), "Ana Maria Silva")["subjects"]["Análise Matemática"]
    assert ana["best"].value == 14
    assert set(ana["epocas"]) == {EPOCA_1}


def test_nota_minima_configuravel():
    """A mínima compara-se com a nota final -- a arredondada, que é a que fica."""
    src = make_source([["Nome", "Nota Final"], ["Ana Maria Silva", "9,4"]])
    assert student(consolidate([src]), "Ana Maria Silva")[
        "subjects"]["Análise Matemática"]["approved"] is False
    generosa = consolidate([src], Settings(pass_mark=9))
    assert student(generosa, "Ana Maria Silva")[
        "subjects"]["Análise Matemática"]["approved"] is True


def test_a_nota_final_e_a_arredondada():
    """13,4 fica 13; 13,5 fica 14. E é essa que aprova e entra nas médias."""
    baixo = make_source([["Nome", "Nota Final"], ["Ana Maria Silva", "13,4"]])
    cima = make_source([["Nome", "Nota Final"], ["Rui Costa Lopes", "13,5"]])
    resultado = consolidate([baixo, cima])
    assert student(resultado, "Ana Maria Silva")["subjects"][
        "Análise Matemática"]["best"].value == 13.4
    assert to_json(resultado)["students"][0]["subjects"][
        "Análise Matemática"]["best_rounded"] == 13
    rui = [s for s in to_json(resultado)["students"] if s["name"] == "Rui Costa Lopes"][0]
    assert rui["subjects"]["Análise Matemática"]["best_rounded"] == 14
    assert rui["averages"]["final"]["value"] == 14


# -- identidade dos alunos -------------------------------------------------

def test_junta_o_mesmo_aluno_de_ficheiros_diferentes():
    a = make_source([["Nome", "Nº Aluno", "Nota Final"],
                     ["Ana Maria Silva", "112233", "14"]],
                    sid="s1", title=["Análise Matemática - Pauta"])
    b = make_source([["Nome", "Nº Aluno", "Nota Final"],
                     ["Ana Maria Silva", "112233", "17"]],
                    sid="s2", order=2, title=["Álgebra Linear - Pauta"])
    result = consolidate([a, b])
    assert len(result["students"]) == 1
    assert set(result["subjects"]) == {"Análise Matemática", "Álgebra Linear"}


def test_junta_por_nome_quando_o_numero_esta_trocado():
    a = make_source([["Nome", "Nº Aluno", "Nota Final"],
                     ["Ana Maria Silva", "122651", "14"]], sid="s1")
    b = make_source([["Nome", "Nº Aluno", "Nota Final"],
                     ["Ana Maria Silva", "1122651", "17"]],
                    sid="s2", order=2, title=["Álgebra Linear - Pauta"])
    result = consolidate([a, b])
    assert len(result["students"]) == 1
    assert result["students"][0]["all_ids"] == ["1122651", "122651"]
    assert any(c["type"] == "numero" for c in result["conflicts"])


def test_juncao_por_nome_pode_ser_desligada():
    a = make_source([["Nome", "Nº Aluno", "Nota Final"],
                     ["Ana Maria Silva", "122651", "14"]], sid="s1")
    b = make_source([["Nome", "Nº Aluno", "Nota Final"],
                     ["Ana Maria Silva", "1122651", "17"]], sid="s2", order=2)
    result = consolidate([a, b], Settings(merge_by_name=False))
    assert len(result["students"]) == 2


def test_acentos_nao_separam_o_mesmo_aluno():
    a = make_source([["Nome", "Nota Final"], ["João Álvaro Sá", "14"]], sid="s1")
    b = make_source([["Nome", "Nota Final"], ["Joao Alvaro Sa", "17"]],
                    sid="s2", order=2, title=["Álgebra Linear - Pauta"])
    assert len(consolidate([a, b])["students"]) == 1


# -- conflitos entre versoes ----------------------------------------------

def test_versao_mais_recente_do_documento_ganha():
    velha = make_source([["Nome", "Nota Final"], ["Ana Maria Silva", "14"]],
                        sid="s1", order=1, footer=["2026/06/03"])
    nova = make_source([["Nome", "Nota Final"], ["Ana Maria Silva", "16"]],
                       sid="s2", order=2, footer=["2026/06/25"])
    # Carregada por ultimo a mais antiga: continua a ganhar a mais recente.
    result = consolidate([nova, velha])
    ana = student(result, "Ana Maria Silva")["subjects"]["Análise Matemática"]
    assert ana["best"].value == 16
    assert any(c["type"] == "nota" for c in result["conflicts"])


def test_sem_data_ganha_o_ficheiro_carregado_por_ultimo():
    primeiro = make_source([["Nome", "Nota Final"], ["Ana Maria Silva", "14"]],
                           sid="s1", order=1, footer=["2026/06/25"])
    segundo = make_source([["Nome", "Nota Final"], ["Ana Maria Silva", "16"]],
                          sid="s2", order=2)
    result = consolidate([primeiro, segundo])
    assert student(result, "Ana Maria Silva")[
        "subjects"]["Análise Matemática"]["best"].value == 16


# -- serializacao ----------------------------------------------------------

def test_to_json_traz_tudo_o_que_a_pagina_precisa():
    src = make_source([
        ["Nome", "Nº Aluno", "Projeto", "Teste 1", "Nota Final"],
        ["Ana Maria Silva", "112233", "17", "13,25", "15,5"],
    ])
    data = to_json(consolidate([src]))
    aluno = data["students"][0]
    assert aluno["student_id"] == "112233"
    uc = aluno["subjects"]["Análise Matemática"]
    assert uc["best"]["label"] == "15,5"
    assert uc["best_rounded"] == 16
    assert uc["best_epoca_label"] == "1.ª Época"
    # So a nota final interessa: as colunas de componentes nao vao para o
    # resultado, nem sequer como informacao lateral.
    assert uc["epocas"][EPOCA_1]["column"] == "Nota Final"
    assert "components" not in uc["epocas"][EPOCA_1]
    assert data["stats"]["students"] == 1

"""Ficheiros mal comportados: nada deve rebentar nem inventar alunos."""

import io

import openpyxl
import pytest

from gradeorg.consolidate import consolidate
from gradeorg.excel import build_workbook
from gradeorg.normalize import split_id_from_name
from gradeorg.session import Session


def carrega(nome, conteudo):
    session = Session()
    session.add_file(nome, conteudo)
    return session


def alunos(session):
    return {(a["name"], a["student_id"]) for a in session.result()["students"]}


def test_tabela_sem_cabecalho_nao_perde_a_primeira_linha():
    """Uma lista só de nomes não tem cabeçalho: comê-lo perderia um aluno."""
    session = carrega("lista.txt", b"Ana Maria Silva\nRui Costa Lopes\nInes Santos Dias\n")
    assert len(session.result()["students"]) == 3


def test_linhas_de_titulo_antes_do_cabecalho():
    session = carrega("pauta.csv", (
        "Pauta de Física\n;;\nNome;Nº;Nota Final\n"
        "Ana Maria Silva;112233;14\nRui Costa Lopes;112234;12\n").encode())
    assert alunos(session) == {("Ana Maria Silva", "112233"), ("Rui Costa Lopes", "112234")}


def test_linha_de_total_no_fim_nao_vira_aluno():
    session = carrega("pauta.csv", (
        "Nome;Nº;Nota Final\nAna Maria Silva;112233;14\nTotal;;14\n").encode())
    assert alunos(session) == {("Ana Maria Silva", "112233")}


def test_ficheiro_utf16():
    session = carrega("pauta.csv", "Nome;Nota Final\nJoão Sá;14\n".encode("utf-16"))
    assert alunos(session) == {("João Sá", None)}


def test_ficheiro_cp1252():
    session = carrega("pauta.csv", "Nome;Nota Final\nJoão Sá;14\n".encode("cp1252"))
    assert alunos(session) == {("João Sá", None)}


def test_ficheiro_sem_linhas_de_dados_e_recusado():
    with pytest.raises(ValueError, match="nenhuma tabela"):
        carrega("vazio.csv", b"Nome;Nota Final\n")


@pytest.mark.parametrize("texto,esperado", [
    ("112233 Ana Maria Silva", ("112233", "Ana Maria Silva")),
    ("112233 - Rui Costa Lopes", ("112233", "Rui Costa Lopes")),
    ("Ana Maria Silva 112233", ("112233", "Ana Maria Silva")),
    ("Ana Maria Silva", (None, "Ana Maria Silva")),
    ("12 Ana Maria Silva", (None, "12 Ana Maria Silva")),   # 12 não é nº de aluno
])
def test_split_id_from_name(texto, esperado):
    assert split_id_from_name(texto) == esperado


def test_numero_colado_ao_nome_e_separado():
    session = carrega("pauta.csv", (
        "Aluno;Classificação\n112233 Ana Maria Silva;14\n112234 Rui Costa Lopes;12\n").encode())
    assert alunos(session) == {("Ana Maria Silva", "112233"), ("Rui Costa Lopes", "112234")}


def test_escala_0_100_e_convertida_para_0_20():
    """Misturar 0-100 com 0-20 sem converter daria comparações sem sentido."""
    session = carrega("pauta.csv", b"Nome;Nota Final\nAna Maria Silva;85\nRui Costa Lopes;42\n")
    resultado = session.result()
    ana = next(s for s in resultado["students"] if s["name"] == "Ana Maria Silva")
    uc = next(iter(ana["subjects"].values()))
    assert uc["best"]["value"] == 17
    assert "85" in uc["best"]["raw"]          # o valor original fica visível
    assert uc["approved"] is True

    rui = next(s for s in resultado["students"] if s["name"] == "Rui Costa Lopes")
    assert next(iter(rui["subjects"].values()))["approved"] is False


def test_pauta_so_com_estados_ainda_da_uma_nota():
    session = carrega("pauta.csv", (
        "Nome;1.ª Época;2.ª Época\nAna Maria Silva;RE;Aprovado\n"
        "Rui Costa Lopes;NA;RE\n").encode())
    resultado = session.result()
    ana = next(s for s in resultado["students"] if s["name"] == "Ana Maria Silva")
    assert next(iter(ana["subjects"].values()))["best"]["label"] == "Aprovado"
    rui = next(s for s in resultado["students"] if s["name"] == "Rui Costa Lopes")
    assert next(iter(rui["subjects"].values()))["best"]["label"] == "Reprovado"


def test_muitas_colunas_de_componentes():
    header = "Nome;" + ";".join(f"Q{i}" for i in range(1, 31)) + ";Total\n"
    linha = "Ana Maria Silva;" + ";".join("1" for _ in range(30)) + ";18\n"
    session = carrega("pauta.csv", (header + linha).encode())
    resultado = session.result()
    ana = resultado["students"][0]
    uc = next(iter(ana["subjects"].values()))
    assert uc["best"]["label"] == "18"
    # As 30 perguntas nao entram: interessa a nota final, mais nada.
    assert uc["epocas"]["epoca1"]["column"] == "Total"


def test_mesmo_aluno_duas_vezes_no_mesmo_ficheiro_gera_conflito():
    session = carrega("pauta.csv", (
        "Nome;Nº;Nota Final\nAna Maria Silva;112233;14\nAna Maria Silva;112233;16\n").encode())
    resultado = session.result()
    assert len(resultado["students"]) == 1
    assert any(c["type"] == "linha repetida" for c in resultado["conflicts"])


def test_excel_gerado_abre_em_todos_os_casos_limite():
    casos = [
        ("lista.txt", b"Ana Maria Silva\nRui Costa Lopes\n"),
        ("estados.csv", "Nome;1.ª Época\nAna Maria Silva;RE\n".encode()),
        ("cem.csv", b"Nome;Nota Final\nAna Maria Silva;85\n"),
    ]
    for nome, conteudo in casos:
        session = carrega(nome, conteudo)
        book = build_workbook(session.raw_result(), session.source_labels())
        buffer = io.BytesIO()
        book.save(buffer)
        buffer.seek(0)
        assert openpyxl.load_workbook(buffer).sheetnames[0] == "Resumo"


def test_sem_fontes_devolve_estrutura_vazia():
    resultado = consolidate([])
    assert resultado["students"] == [] and resultado["subjects"] == []
    build_workbook(resultado, [])       # não pode rebentar

"""Leitura dos varios formatos de ficheiro."""

import openpyxl
import pytest

from gradeorg.parsers import UnsupportedFile, kind_of, parse_file
from gradeorg.parsers.text import _pick_delimiter, parse_text


@pytest.fixture
def tmp_txt(tmp_path):
    def write(content, name="pauta.txt", encoding="utf-8"):
        path = tmp_path / name
        path.write_bytes(content.encode(encoding))
        return str(path)
    return write


def test_kind_of():
    assert kind_of("a.pdf") == "pdf"
    assert kind_of("a.XLSX") == "xlsx"
    assert kind_of("a.csv") == "csv"
    assert kind_of("a.txt") == "txt"
    with pytest.raises(UnsupportedFile):
        kind_of("a.docx")


def test_csv_com_ponto_e_virgula(tmp_txt):
    path = tmp_txt("Nome;Nº;Nota Final\nAna Maria Silva;112233;14,5\n"
                   "Rui Costa Lopes;112234;9\n", name="pauta.csv")
    kind, tables = parse_file(path)
    assert kind == "csv"
    assert tables[0].rows[0] == ["Nome", "Nº", "Nota Final"]
    assert tables[0].rows[1] == ["Ana Maria Silva", "112233", "14,5"]


def test_txt_separado_por_tabulacoes(tmp_txt):
    path = tmp_txt("Nome\tNota\nAna Maria Silva\t14\nRui Costa Lopes\t12\n")
    _, tables = parse_file(path)
    assert tables[0].rows[1] == ["Ana Maria Silva", "14"]


def test_txt_alinhado_por_espacos(tmp_txt):
    path = tmp_txt(
        "Nome                 Nº       Nota\n"
        "Ana Maria Silva      112233   14\n"
        "Rui Costa Lopes      112234   9,5\n")
    _, tables = parse_file(path)
    assert [r[0] for r in tables[0].rows] == ["Nome", "Ana Maria Silva", "Rui Costa Lopes"]
    assert tables[0].rows[2][2] == "9,5"


def test_txt_em_cp1252(tmp_txt):
    path = tmp_txt("Nome;Nota\nJoão Sá;14\n", name="p.csv", encoding="cp1252")
    _, tables = parse_file(path)
    assert tables[0].rows[1][0] == "João Sá"


def test_escolha_do_separador():
    assert _pick_delimiter(["a;b;c", "1;2;3"]) == ";"
    assert _pick_delimiter(["a\tb", "1\t2"]) == "\t"
    assert _pick_delimiter(["Ana Maria 14", "Rui Costa 12"]) is None


def test_ficheiro_de_texto_vazio_nao_da_tabelas(tmp_txt):
    assert parse_text(tmp_txt("\n\n")) == []


def test_xlsx_com_titulo_por_cima_do_cabecalho(tmp_path):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Pauta"
    sheet["A1"] = "Álgebra Linear — 2.ª Época"
    sheet.append([])
    sheet.append(["Nome", "Nº Aluno", "Nota Final"])
    sheet.append(["Ana Maria Silva", 112233, 14])
    path = tmp_path / "pauta.xlsx"
    workbook.save(path)

    kind, tables = parse_file(str(path))
    assert kind == "xlsx"
    assert tables[0].title_lines == ["Álgebra Linear - 2.ª Época"]   # travessões são uniformizados
    assert tables[0].sheet_name == "Pauta"


def test_xlsx_ignora_colunas_e_linhas_vazias(tmp_path):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet["B2"] = "Nome"
    sheet["C2"] = "Nota"
    sheet["B3"] = "Ana Maria Silva"
    sheet["C3"] = 14
    path = tmp_path / "p.xlsx"
    workbook.save(path)
    _, tables = parse_file(str(path))
    assert tables[0].rows == [["Nome", "Nota"], ["Ana Maria Silva", "14"]]

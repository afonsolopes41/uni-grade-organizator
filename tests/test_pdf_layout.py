"""Reconstrução de colunas a partir das posições das palavras.

Estes testes trabalham sobre geometria fabricada — as mesmas formas que
aparecem em pautas reais — para não dependerem de nenhum PDF em disco.
"""

from gradeorg.models import RawTable
from gradeorg.parsers.pdf import (
    _column_boundaries, _drop_straddled_boundaries, _group_into_lines,
    _header_band, _is_laid_out_in_columns, _looks_like_record, _merge_header,
    _score_table, _split_line, _text_segments,
)


def word(text, x0, top, width=None, height=5.85):
    """Uma palavra com posição, como o pdfplumber a devolve."""
    return {"text": text, "x0": x0, "x1": x0 + (width if width else len(text) * 3.0),
            "top": top, "bottom": top + height}


def line(*words):
    return sorted(words, key=lambda w: w["x0"])


# -- agrupar palavras em linhas -------------------------------------------

def test_linhas_proximas_ficam_juntas_e_distantes_separadas():
    """Um cabeçalho de várias linhas tem espaçamentos pequenos entre elas."""
    words = [
        word("Test", 345, 89.8), word("1", 361, 89.8),
        word("Max1", 406, 90.4),                       # mesma linha visual
        word("Grade", 300, 94.2), word("Number", 48, 94.8),   # linha seguinte
        word("30%", 349, 98.2),                        # e outra
    ]
    lines = _group_into_lines(words)
    assert len(lines) == 3
    assert [w["text"] for w in lines[0]] == ["Test", "1", "Max1"]
    assert [w["text"] for w in lines[1]] == ["Number", "Grade"]
    assert [w["text"] for w in lines[2]] == ["30%"]


def test_uma_palavra_alta_nao_arrasta_a_linha_seguinte():
    """A tolerância vem da altura mediana da página, não da palavra."""
    words = [word("Título", 43, 40, height=9.1), word("Aluno", 43, 48)]
    assert len(_group_into_lines(words)) == 2


# -- o que é uma linha de aluno -------------------------------------------

def test_linha_de_cabecalho_nao_passa_por_linha_de_aluno():
    """«Number Name Date Grade» também parece um nome de pessoa."""
    assert not _looks_like_record(line(
        word("Number", 48, 94), word("Name", 76, 94),
        word("Date", 265, 94), word("Grade", 300, 94)))


def test_linha_com_numero_de_aluno_e_dados():
    assert _looks_like_record(line(
        word("38016", 52, 110), word("Filipe", 76, 110), word("Neves", 128, 110),
        word("NA", 298, 110), word("f", 350, 110)))


# -- limites das colunas ---------------------------------------------------

def linhas_de_dados():
    """Duas linhas onde a coluna «Test 1» tem um "f" estreito e um "10.0" largo,
    que não chegam a sobrepor-se em x."""
    return [
        line(word("38016", 52, 110), word("Filipe Neves", 76, 110, width=70),
             word("NA", 298, 110), word("f", 350.4, 110, width=1.6)),
        line(word("65074", 52, 120), word("Sergiy Nytsulenko", 76, 120, width=80),
             word("11", 318, 120), word("10.0", 358.8, 120, width=11.7)),
    ]


def test_valores_de_larguras_diferentes_partem_a_coluna_em_duas():
    """O ponto de partida do problema: sem cabeçalho, as colunas partem-se.

    Há quatro colunas reais — número, nome, nota e Teste 1 — mas os valores
    estreitos ("f", "NA") e os largos ("10.0", "11") não se sobrepõem em x.
    """
    boundaries = _column_boundaries(linhas_de_dados())
    assert len(boundaries) - 1 > 4


def test_palavra_do_cabecalho_por_cima_junta_as_duas_metades():
    body = linhas_de_dados()
    boundaries = _column_boundaries(body)
    header = [line(word("Number", 48, 94), word("Name", 76, 94),
                   word("Grade", 298, 94, width=18),
                   word("Test", 345.8, 94, width=13.9))]
    merged = _drop_straddled_boundaries(boundaries, header, body)
    assert len(merged) - 1 == 4
    assert _split_line(body[1], merged) == ["65074", "Sergiy Nytsulenko", "11", "10.0"]


def test_colunas_ambas_preenchidas_nunca_se_juntam():
    """«Nota Final» e «Avaliação Final» estão as duas preenchidas na mesma
    linha: uma palavra larga do cabeçalho não as pode colar."""
    body = [
        line(word("Ana Silva", 40, 110, width=50), word("15,5", 200, 110, width=14),
             word("16", 240, 110, width=8)),
        line(word("Rui Costa", 40, 120, width=50), word("13,6", 200, 120, width=14),
             word("14", 240, 120, width=8)),
    ]
    boundaries = _column_boundaries(body)
    header = [line(word("Nome", 40, 100), word("Nota Final", 195, 100, width=40),
                   word("Avaliação Final", 225, 100, width=45))]
    assert _drop_straddled_boundaries(boundaries, header, body) == boundaries


def test_nota_composta_ocupa_a_coluna_e_um_bocado_da_seguinte():
    """"RE m" aparece em poucas linhas e não deve criar uma coluna nova."""
    body = [
        line(word("Ana Silva", 40, 110, width=50), word("14", 200, 110, width=8)),
        line(word("Rui Costa", 40, 120, width=50), word("12", 200, 120, width=8)),
        line(word("Ines Dias", 40, 130, width=50), word("13", 200, 130, width=8)),
        line(word("Tomas Reis", 40, 140, width=50), word("RE", 198, 140, width=8),
             word("m", 212, 140, width=4)),
    ]
    boundaries = _column_boundaries(body)
    header = [line(word("Nome", 40, 100), word("Grade", 197, 100, width=20))]
    merged = _drop_straddled_boundaries(boundaries, header, body)
    assert _split_line(body[3], merged) == ["Tomas Reis", "RE m"]


# -- cabeçalho contra prosa ------------------------------------------------

def test_prosa_e_cabecalho_distinguem_se_pelo_espacamento():
    titulo = line(word("Projeto", 40, 60), word("de", 66, 60), word("Sistemas", 76, 60))
    cabecalho = line(word("Nome", 40, 90), word("Nota", 200, 90), word("Final", 240, 90))
    assert not _is_laid_out_in_columns(titulo)
    assert _is_laid_out_in_columns(cabecalho)


def test_cabecalho_de_varias_linhas_junta_se_por_coluna():
    body = [
        line(word("38016", 52, 110), word("Filipe", 76, 110, width=40),
             word("3.6", 350, 110, width=9), word("18.0", 406, 110, width=12)),
        line(word("65074", 52, 120), word("Sergiy", 76, 120, width=40),
             word("11.3", 350, 120, width=12), word("17.7", 406, 120, width=12)),
    ]
    boundaries = _column_boundaries(body)
    lines = [
        line(word("Test", 345, 89), word("1", 361, 89), word("Max1", 406, 89)),
        line(word("Number", 48, 95), word("Name", 76, 95)),
        line(word("30%", 349, 101), word("9%", 408, 101)),
    ] + body
    band = _header_band(lines, 3, boundaries)
    assert band == [0, 1, 2]
    header = _merge_header([lines[i] for i in band], boundaries)
    assert header == ["Number", "Name", "Test 1 30%", "Max1 9%"]


def test_o_titulo_nao_entra_no_cabecalho():
    body = [
        line(word("38016", 52, 110), word("Filipe", 76, 110, width=40),
             word("14", 350, 110, width=8)),
        line(word("65074", 52, 120), word("Sergiy", 76, 120, width=40),
             word("12", 350, 120, width=8)),
    ]
    boundaries = _column_boundaries(body)
    titulo = line(word("Assessment", 43, 80, width=34), word("review:", 79, 80, width=21),
                  word("Monday,", 102, 80, width=23), word("Jun", 127, 80, width=10))
    cabecalho = line(word("Number", 48, 95), word("Name", 76, 95), word("Grade", 345, 95))
    lines = [titulo, cabecalho] + body
    assert _header_band(lines, 2, boundaries) == [1]


# -- texto solto -----------------------------------------------------------

def test_titulo_e_legenda_na_mesma_linha_ficam_separados():
    """A legenda dos símbolos vive à direita do título, na mesma linha visual."""
    segments = _text_segments([line(
        word("03713", 43, 49), word("-", 72, 49), word("SGR", 78, 49),
        word("-", 100, 49), word("Network", 106, 49, width=34),
        word("Security", 142, 49, width=33),
        word("d", 343, 49), word("-", 350, 49), word("Withdrawal", 354, 49, width=29),
    )])
    assert "03713 - SGR - Network Security" in segments
    assert "d - Withdrawal" in segments


# -- escolha entre os dois métodos de extracção ---------------------------

def test_ganha_a_tabela_mais_cheia():
    cheia = RawTable(rows=[["Nome", "Nota"], ["Ana Silva", "14"], ["Rui Costa", "12"]])
    esburacada = RawTable(rows=[["Nome", "", "Nota", ""],
                                ["Ana Silva", "", "14", ""],
                                ["Rui Costa", "", "12", ""]])
    assert _score_table(cheia) > _score_table(esburacada)

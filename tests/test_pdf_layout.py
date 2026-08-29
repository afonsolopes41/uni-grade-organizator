"""Reconstrução de colunas a partir das posições das palavras.

Estes testes trabalham sobre geometria fabricada — as mesmas formas que
aparecem em pautas reais — para não dependerem de nenhum PDF em disco.
"""

from gradeorg.models import RawTable
from gradeorg.parsers.pdf import (
    _column_boundaries, _drop_straddled_boundaries, _group_into_lines,
    _header_band, _is_laid_out_in_columns, _looks_like_record, _merge_header,
    _score_table, _split_id_from_name, _split_line, _text_segments, _value_spans,
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
    spans = _value_spans(body, boundaries)
    band = _header_band(lines, 3, boundaries, spans)
    assert band == [0, 1, 2]
    header = _merge_header([lines[i] for i in band], boundaries, spans)
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
    assert _header_band(lines, 2, boundaries, _value_spans(body, boundaries)) == [1]


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


# -- número e nome colados na mesma coluna ---------------------------------

def test_numero_e_nome_colados_separam_se_em_duas_colunas():
    """O número fica a quatro pontos do nome — menos do que separa colunas.

    Sem outro sinal, a reconstrução juntava os dois. Aqui há um sinal mais
    forte do que a distância: à esquerda números de aluno, à direita nomes.
    """
    body = [
        line(word("110641", 66, 110, width=34), word("Afonso", 104, 110, width=31),
             word("Maia", 137, 110, width=21), word("13,0", 583, 110, width=20)),
        line(word("122631", 66, 120, width=34), word("Afonso", 104, 120, width=31),
             word("Lopes", 137, 120, width=26), word("13,2", 583, 120, width=20)),
        line(word("122657", 66, 130, width=34), word("Alexandre", 104, 130, width=44),
             word("Duarte", 150, 130, width=30), word("14,1", 583, 130, width=20)),
    ]
    boundaries = _column_boundaries(body)
    assert len(boundaries) - 1 == 2          # número e nome ainda juntos

    boundaries = _split_id_from_name(body, boundaries)
    assert len(boundaries) - 1 == 3
    assert _split_line(body[0], boundaries) == ["110641", "Afonso Maia", "13,0"]


def test_nao_parte_uma_coluna_de_nomes_sem_numero():
    body = [
        line(word("Afonso", 104, 110, width=31), word("Maia", 137, 110, width=21),
             word("13,0", 583, 110, width=20)),
        line(word("Alexandre", 104, 120, width=44), word("Duarte", 150, 120, width=30),
             word("14,1", 583, 120, width=20)),
    ]
    boundaries = _column_boundaries(body)
    assert _split_id_from_name(body, boundaries) == boundaries


# -- etiquetas de cabeçalho longe dos seus valores -------------------------

def test_etiqueta_do_exame_nao_junta_a_coluna_da_nota_final():
    """«Exame» começa à esquerda dos seus valores e cruza o vazio.

    Cruzar o vazio entre duas colunas não basta para as juntar: a etiqueta tem
    de chegar aos valores das duas, e esta não chega perto da «Nota final».
    """
    body = [
        line(word("Afonso", 104, 110, width=31), word("13,0", 583, 110, width=20)),
        line(word("Rui", 104, 120, width=16), word("5,9", 640, 120, width=14)),
        line(word("Ana", 104, 130, width=18), word("13,2", 583, 130, width=20)),
        line(word("Ines", 104, 140, width=20), word("2,3", 640, 140, width=14)),
    ]
    boundaries = _column_boundaries(body)
    cabecalho = [line(word("Aluno", 104, 95, width=27), word("Nota", 557, 95, width=23),
                      word("final", 582, 95, width=21), word("Exame", 616, 95, width=30))]
    assert _drop_straddled_boundaries(boundaries, cabecalho, body) == boundaries


def test_etiqueta_a_esquerda_dos_valores_vai_para_a_coluna_certa():
    """Numa coluna de números alinhados à direita, a etiqueta começa bem antes."""
    body = [
        line(word("Afonso", 104, 110, width=31), word("10,25", 424, 110, width=26),
             word("13,80", 476, 110, width=25)),
        line(word("Alexandre", 104, 120, width=44), word("13,50", 424, 120, width=26),
             word("11,47", 476, 120, width=25)),
    ]
    boundaries = _column_boundaries(body)
    spans = _value_spans(body, boundaries)
    cabecalho = line(word("Aluno", 104, 95, width=27), word("Teste", 361, 95, width=25),
                     word("intercalar", 389, 95, width=44), word("2º", 460, 95, width=10),
                     word("teste", 473, 95, width=23))
    assert _merge_header([cabecalho], boundaries, spans) == [
        "Aluno", "Teste intercalar", "2º teste"]


def test_etiqueta_de_uma_coluna_sem_valores_nao_rouba_o_nome_a_vizinha():
    """«Exame recurso» sem uma única nota: a coluna não existe nos dados."""
    body = [
        line(word("Afonso", 104, 110, width=31), word("5,9", 640, 110, width=14)),
        line(word("Ana", 104, 120, width=18), word("2,3", 640, 120, width=14)),
    ]
    boundaries = _column_boundaries(body)
    spans = _value_spans(body, boundaries)
    cabecalho = line(word("Aluno", 104, 95, width=27), word("Exame", 616, 95, width=30),
                     word("Exame", 659, 95, width=30), word("recurso", 692, 95, width=34))
    assert _merge_header([cabecalho], boundaries, spans) == ["Aluno", "Exame"]

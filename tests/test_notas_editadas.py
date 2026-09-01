"""Corrigir uma nota à mão e tirar um aluno da pauta final."""

from gradeorg.session import Session

CSV = (
    "Nome;Nº Aluno;Nota Final\n"
    "Ana Maria Silva;112233;15\n"
    "Rui Costa Lopes;112234;9\n"
    "Marta Nunes Dias;112235;12\n"
).encode("utf-8")


def sessao():
    s = Session()
    s.add_file("redes.csv", CSV)
    s.update(answers={f"{s.sources[0].id}:subject": "Redes"})
    return s


def aluno(resultado, nome):
    return [a for a in resultado["students"] if a["name"] == nome][0]


def test_a_nota_corrigida_e_a_que_fica():
    s = sessao()
    chave = aluno(s.result(), "Rui Costa Lopes")["key"]

    s.edit_grade(chave, "Redes", 14)
    rui = aluno(s.result(), "Rui Costa Lopes")
    assert rui["subjects"]["Redes"]["best"]["value"] == 14
    assert rui["subjects"]["Redes"]["edited"] is True
    # A nota que a pauta trazia não se perde.
    assert rui["subjects"]["Redes"]["original"]["value"] == 9


def test_corrigir_a_nota_muda_a_aprovacao_e_a_media():
    s = sessao()
    chave = aluno(s.result(), "Rui Costa Lopes")["key"]
    assert aluno(s.result(), "Rui Costa Lopes")["subjects"]["Redes"]["approved"] is False

    s.edit_grade(chave, "Redes", 14)
    rui = aluno(s.result(), "Rui Costa Lopes")
    assert rui["subjects"]["Redes"]["approved"] is True
    assert rui["averages"]["final"]["value"] == 14


def test_a_correccao_conta_para_as_estatisticas_da_cadeira():
    s = sessao()
    antes = s.result()["subject_stats"]["Redes"]
    assert (antes["approved"], antes["failed"]) == (2, 1)

    s.edit_grade(aluno(s.result(), "Rui Costa Lopes")["key"], "Redes", 14)
    depois = s.result()["subject_stats"]["Redes"]
    assert (depois["approved"], depois["failed"]) == (3, 0)


def test_apagar_a_correccao_devolve_a_nota_da_pauta():
    s = sessao()
    chave = aluno(s.result(), "Rui Costa Lopes")["key"]
    s.edit_grade(chave, "Redes", 14)
    s.edit_grade(chave, "Redes", "")

    rui = aluno(s.result(), "Rui Costa Lopes")
    assert rui["subjects"]["Redes"]["best"]["value"] == 9
    assert rui["subjects"]["Redes"]["edited"] is False


def test_corrigir_uma_cadeira_que_o_aluno_nao_tinha_acrescenta_a_nota():
    s = sessao()
    s.create_subject("Análise")
    chave = aluno(s.result(), "Ana Maria Silva")["key"]
    s.edit_grade(chave, "Análise", 16)

    ana = aluno(s.result(), "Ana Maria Silva")
    assert ana["subjects"]["Análise"]["best"]["value"] == 16
    assert ana["subjects"]["Análise"]["approved"] is True


def test_a_correccao_sobrevive_a_fechar_e_abrir():
    s = sessao()
    chave = aluno(s.result(), "Rui Costa Lopes")["key"]
    s.edit_grade(chave, "Redes", 14)

    outra = Session()
    assert aluno(outra.result(), "Rui Costa Lopes")["subjects"]["Redes"]["best"]["value"] == 14


def test_tirar_um_aluno_da_pauta_final():
    s = sessao()
    chave = aluno(s.result(), "Marta Nunes Dias")["key"]
    s.remove_student(chave)

    nomes = [a["name"] for a in s.result()["students"]]
    assert nomes == ["Ana Maria Silva", "Rui Costa Lopes"]
    # O aluno fica listado para se poder repor, com o nome que tinha.
    assert s.result()["removed_students"] == [{"key": chave, "name": "Marta Nunes Dias"}]


def test_o_aluno_tirado_nao_conta_para_as_estatisticas():
    s = sessao()
    s.remove_student(aluno(s.result(), "Rui Costa Lopes")["key"])
    stats = s.result()["subject_stats"]["Redes"]
    assert (stats["approved"], stats["failed"]) == (2, 0)


def test_repor_um_aluno_tirado():
    s = sessao()
    chave = aluno(s.result(), "Marta Nunes Dias")["key"]
    s.remove_student(chave)
    s.restore_student(chave)

    assert len(s.result()["students"]) == 3
    assert s.result()["removed_students"] == []


def test_tirar_um_aluno_sobrevive_a_fechar_e_abrir():
    s = sessao()
    s.remove_student(aluno(s.result(), "Marta Nunes Dias")["key"])
    assert len(Session().result()["students"]) == 2

"""Gerir as unidades curriculares: apagar, repor, mudar o nome, saber a origem."""

import pytest

from gradeorg.consolidate import Settings, consolidate, resolve_subjects, subject_files
from gradeorg.detect import build_source
from gradeorg.models import RawTable
from gradeorg.session import Session

REDES = (
    "Número;Nome;Nota Final\n"
    "65074;Sergiy Nytsulenko;11\n"
    "65075;Ana Maria Silva;15\n"
).encode("utf-8")

ALGEBRA = (
    "Número;Nome;Nota Final\n"
    "65075;Ana Maria Silva;14\n"
    "65076;Rui Costa Lopes;12\n"
).encode("utf-8")


def fonte(source_id, filename, titulo, linhas, order=1):
    return build_source(source_id=source_id, filename=filename, kind="csv",
                        table=RawTable(rows=linhas, title_lines=titulo),
                        file_order=order)


@pytest.fixture
def sessao():
    session = Session()
    session.add_file("Redes.csv", REDES)
    session.add_file("Algebra.csv", ALGEBRA)
    return session


def nomes(session):
    return set(session.review()["subjects"])


def test_diz_de_que_ficheiro_vem_cada_cadeira(sessao):
    ficheiros = sessao.review()["subject_files"]
    assert ficheiros["Redes"] == ["Redes.csv"]
    assert ficheiros["Algebra"] == ["Algebra.csv"]


def test_mudar_o_nome_de_uma_cadeira(sessao):
    sessao.rename_subject("Redes", "Segurança e Gestão de Redes")
    assert "Segurança e Gestão de Redes" in nomes(sessao)
    assert "Redes" not in nomes(sessao)
    resultado = sessao.result()
    aluno = next(a for a in resultado["students"] if a["student_id"] == "65074")
    assert aluno["subjects"]["Segurança e Gestão de Redes"]["best"]["label"] == "11"


def test_o_nome_novo_leva_as_definicoes():
    """A nota mínima e o plano de estudos seguem a cadeira quando ela muda de nome."""
    session = Session()
    session.add_file("Redes.csv", REDES)
    session.update(settings={
        "subject_pass_marks": {"Redes": 10.0},
        "subject_curriculum": {"Redes": {"year": 3, "semester": 2, "ects": 6}},
    })
    session.rename_subject("Redes", "Redes II")

    review = session.review()
    assert review["pass_marks"]["Redes II"] == 10.0
    assert review["curriculum"]["Redes II"]["ects"] == 6
    assert "Redes" not in review["curriculum"]


def test_mudar_o_nome_aguenta_o_arranque_seguinte():
    session = Session()
    session.add_file("Redes.csv", REDES)
    session.rename_subject("Redes", "Redes de Computadores")
    assert "Redes de Computadores" in set(Session().review()["subjects"])


def test_apagar_uma_cadeira_tira_a_das_notas(sessao):
    sessao.remove_subject("Algebra")
    resultado = sessao.result()
    assert resultado["subjects"] == ["Redes"]
    assert all("Algebra" not in a["subjects"] for a in resultado["students"])
    # O ficheiro fica -- só a cadeira é que deixou de contar.
    assert len(sessao.files) == 2
    assert sessao.review()["removed_subjects"] == ["Algebra"]


def test_repor_uma_cadeira_apagada(sessao):
    sessao.remove_subject("Algebra")
    sessao.restore_subject("Algebra")
    assert sessao.result()["subjects"] == ["Algebra", "Redes"]


def test_cadeira_apagada_nao_levanta_perguntas():
    session = Session()
    session.add_file("sem-nome.csv", b"Nome;Nota Final\nAna Maria Silva;15\n")
    subject = session.review()["subjects"][0]
    assert session.open_questions()
    session.remove_subject(subject)
    assert not session.open_questions()


# -- cadeiras de um curso e cadeiras comuns ---------------------------------

def _tres_cadeiras():
    return [
        fonte("s1", "Redes.csv", ["Segurança e Gestão de Redes"],
              [["Número", "Nome", "Nota Final"],
               ["1", "Ana Maria Silva", "15"]]),
        fonte("s2", "Algebra.csv", ["Álgebra Linear"],
              [["Número", "Nome", "Nota Final"],
               ["1", "Ana Maria Silva", "14"],
               ["2", "Rui Costa Lopes", "12"]]),
    ]


def test_quem_e_de_outro_curso_nao_conta_como_cadeira_em_falta():
    """Redes é só do curso do Ana; o Rui não a faz, e isso não é uma falha dele."""
    settings = Settings(subject_curriculum={
        "Segurança e Gestão de Redes": {"course": "LEI"},
    })
    resultado = consolidate(_tres_cadeiras(), settings)
    por_nome = {a["name"]: a for a in resultado["students"]}

    ana = por_nome["Ana Maria Silva"]["averages"]
    assert ana["course"] == "LEI"
    assert ana["coverage"] == {"have": 2, "total": 2, "missing": []}

    rui = por_nome["Rui Costa Lopes"]["averages"]
    # Sem nenhuma cadeira exclusiva, o curso é desconhecido: o plano dele são
    # as comuns, e nessas está completo.
    assert rui["course"] is None
    assert rui["coverage"]["total"] == 1
    assert rui["coverage"]["missing"] == []


def test_sem_cursos_preenchidos_o_plano_sao_todas_as_cadeiras():
    resultado = consolidate(_tres_cadeiras(), Settings())
    por_nome = {a["name"]: a for a in resultado["students"]}
    rui = por_nome["Rui Costa Lopes"]["averages"]
    assert rui["coverage"]["total"] == 2
    assert rui["coverage"]["missing"] == ["Segurança e Gestão de Redes"]


def test_pauta_sem_nota_final_avisa_em_vez_de_desaparecer_calada():
    teste = fonte("s1", "SGR_Teste1.pdf",
                  ["03713 - SGR - Segurança e Gestão de Redes",
                   "1ª Época", "2º Semestre Teste 1 (30%)"],
                  [["Número", "Nome", "Nota"], ["65074", "Sergiy Nytsulenko", "3.6"]])
    resultado = consolidate([teste], Settings())
    aviso = next(w for w in resultado["warnings"] if w["type"] == "pauta sem nota final")
    assert "Teste 1" in str(aviso["detail"])


def test_ficheiros_por_cadeira_juntam_as_duas_pautas():
    fontes = [
        fonte("s1", "SGR_pt.pdf", ["03713 - SGR - Segurança e Gestão de Redes"],
              [["Número", "Nome", "Nota Final"], ["1", "Ana Maria Silva", "15"]]),
        fonte("s2", "SGR_en.pdf", ["03713 - SGR - Network Security and Management"],
              [["Número", "Nome", "Nota Final"], ["1", "Ana Maria Silva", "15"]], order=2),
    ]
    settings = Settings()
    nomes_uc, _ = resolve_subjects(fontes, settings)
    ficheiros = subject_files(fontes, nomes_uc)
    assert len(ficheiros) == 1
    assert sorted(next(iter(ficheiros.values()))) == ["SGR_en.pdf", "SGR_pt.pdf"]


# -- número e nome na mesma coluna ------------------------------------------

def test_pauta_com_numero_e_nome_na_mesma_coluna():
    """A coluna «Aluno» traz «122631 Afonso Lopes»: tem de dar aluno e número."""
    src = fonte("s1", "SCO.pdf", ["Sistemas de Comunicação Óptica"],
                [["Aluno", "Nota Final"],
                 ["122631 Afonso Duarte Rosado Lopes", "15"],
                 ["122625 Afonso Ruas Mexia", "13"],
                 ["122657 Alexandre Campos Corgas Duarte", "17"]])
    coluna = next(c for c in src.columns if c.index == 0)
    assert coluna.role == "name"
    assert coluna.combined is True

    resultado = consolidate([src], Settings())
    por_numero = {a["student_id"]: a["name"] for a in resultado["students"]}
    assert por_numero == {
        "122631": "Afonso Duarte Rosado Lopes",
        "122625": "Afonso Ruas Mexia",
        "122657": "Alexandre Campos Corgas Duarte",
    }


def test_numero_no_fim_do_nome_tambem_se_separa():
    src = fonte("s1", "pauta.pdf", ["Óptica"],
                [["Aluno", "Nota Final"],
                 ["Afonso Duarte Rosado Lopes 122631", "15"],
                 ["Afonso Ruas Mexia 122625", "13"]])
    resultado = consolidate([src], Settings())
    assert {a["student_id"] for a in resultado["students"]} == {"122631", "122625"}
    assert all("122" not in a["name"] for a in resultado["students"])


def test_numero_dentro_do_nome_sai_mesmo_havendo_coluna_de_numero():
    src = fonte("s1", "pauta.pdf", ["Óptica"],
                [["Número", "Nome", "Nota Final"],
                 ["122631", "122631 Afonso Duarte Rosado Lopes", "15"]])
    aluno = consolidate([src], Settings())["students"][0]
    assert aluno["name"] == "Afonso Duarte Rosado Lopes"
    assert aluno["student_id"] == "122631"


# -- cadeiras criadas à mão -------------------------------------------------

def test_criar_uma_cadeira_sem_pauta_nenhuma():
    session = Session()
    session.create_subject("Física Geral")
    review = session.review()
    assert review["subjects"] == ["Física Geral"]
    assert review["subject_files"].get("Física Geral") is None
    assert session.result()["subjects"] == ["Física Geral"]


def test_cadeira_criada_a_mao_aguenta_o_arranque_seguinte():
    session = Session()
    session.create_subject("Física Geral")
    session.update(settings={"subject_curriculum": {"Física Geral": {"year": 1}}})
    outra = Session()
    assert "Física Geral" in outra.review()["subjects"]
    assert outra.review()["curriculum"]["Física Geral"]["year"] == 1


def test_mudar_o_nome_a_uma_cadeira_criada_a_mao():
    session = Session()
    session.create_subject("Fisica")
    session.rename_subject("Fisica", "Física Geral")
    assert session.review()["subjects"] == ["Física Geral"]


def test_apontar_um_ficheiro_a_uma_cadeira(sessao):
    sessao.create_subject("Óptica")
    sessao.assign_file("Redes.csv", "Óptica")
    review = sessao.review()
    assert review["subject_files"]["Óptica"] == ["Redes.csv"]
    assert "Redes" not in review["subjects"]

    # E dá para voltar atrás: sem nome, volta o que a detecção diz.
    sessao.assign_file("Redes.csv", "")
    assert "Redes" in sessao.review()["subjects"]


def test_confirmar_uma_pauta_fica_guardado(sessao):
    fonte_id = sessao.sources[0].id
    sessao.confirm_source(fonte_id)
    assert sessao.review()["confirmed_sources"] == [fonte_id]
    assert Session().review()["confirmed_sources"] == [fonte_id]
    sessao.confirm_source(fonte_id, False)
    assert sessao.review()["confirmed_sources"] == []


# -- ordem por ano e semestre ----------------------------------------------

def test_cadeiras_ordenadas_por_ano_semestre_e_nome():
    from gradeorg.consolidate import order_subjects, subject_groups
    curriculo = {
        "Redes": {"year": 2, "semester": 1},
        "Álgebra": {"year": 1, "semester": 1},
        "Análise": {"year": 1, "semester": 1},
        "Óptica": {},
        "Física": {"year": 1, "semester": 2},
    }
    ordem = order_subjects(list(curriculo), curriculo)
    assert ordem == ["Álgebra", "Análise", "Física", "Redes", "Óptica"]

    grupos = subject_groups(ordem, curriculo)
    assert [(g["year"], g["semester"], g["subjects"]) for g in grupos] == [
        (1, 1, ["Álgebra", "Análise"]),
        (1, 2, ["Física"]),
        (2, 1, ["Redes"]),
        (None, None, ["Óptica"]),
    ]


def test_o_resultado_traz_as_cadeiras_agrupadas():
    session = Session()
    session.add_file("Redes.csv", REDES)
    session.add_file("Algebra.csv", ALGEBRA)
    session.update(settings={"subject_curriculum": {
        "Redes": {"year": 2, "semester": 1},
        "Algebra": {"year": 1, "semester": 1},
    }})
    resultado = session.result()
    assert resultado["subjects"] == ["Algebra", "Redes"]
    assert [g["year"] for g in resultado["subject_groups"]] == [1, 2]


# -- contas por cadeira -----------------------------------------------------

def test_aprovacoes_e_media_sao_por_cadeira():
    """Somadas entre UCs não dizem nada; por cadeira são a leitura certa."""
    redes = fonte("s1", "Redes.csv", ["Segurança e Gestão de Redes"],
                  [["Número", "Nome", "Nota Final"],
                   ["1", "Ana Maria Silva", "15"],
                   ["2", "Rui Costa Lopes", "8"],
                   ["3", "Ines Santos Dias", ""]])
    algebra = fonte("s2", "Algebra.csv", ["Álgebra Linear"],
                    [["Número", "Nome", "Nota Final"],
                     ["1", "Ana Maria Silva", "14"],
                     ["4", "Joao Pedro Nunes", "12"]], order=2)

    stats = consolidate([redes, algebra], Settings())["subject_stats"]
    assert stats["Segurança e Gestão de Redes"] == {
        "students": 3, "approved": 1, "failed": 1, "pending": 1,
        "average": 11.5, "pass_rate": 0.5,
    }
    # O João não faz Redes: não conta como reprovado numa cadeira que não fez.
    assert stats["Álgebra Linear"]["students"] == 2
    assert stats["Álgebra Linear"]["approved"] == 2
    assert stats["Álgebra Linear"]["average"] == 13.0


def test_quem_esta_na_pauta_sem_nota_conta_como_sem_nota():
    src = fonte("s1", "pauta.csv", ["Óptica"],
                [["Número", "Nome", "Nota Final"],
                 ["1", "Ana Maria Silva", "15"],
                 ["2", "Rui Costa Lopes", ""],
                 ["3", "Ines Santos Dias", ""]])
    stats = consolidate([src], Settings())["subject_stats"]["Óptica"]
    assert (stats["approved"], stats["failed"], stats["pending"]) == (1, 0, 2)
    assert stats["students"] == 3


def test_a_media_da_cadeira_usa_a_nota_final_arredondada():
    src = fonte("s1", "pauta.csv", ["Óptica"],
                [["Número", "Nome", "Nota Final"],
                 ["1", "Ana Maria Silva", "13,4"],
                 ["2", "Rui Costa Lopes", "13,5"]])
    # 13 e 14, não 13,45.
    assert consolidate([src], Settings())["subject_stats"]["Óptica"]["average"] == 13.5


def test_cadeira_sem_alunos_nenhuns_nao_rebenta():
    session = Session()
    session.create_subject("Física Geral")
    stats = session.raw_result()["subject_stats"]["Física Geral"]
    assert stats == {"students": 0, "approved": 0, "failed": 0, "pending": 0,
                     "average": None, "pass_rate": None}


def test_os_ects_sao_sempre_inteiros():
    """O controlo dos ECTS anda de um em um; meio ECTS não existe."""
    from gradeorg.consolidate import Settings

    settings = Settings.from_dict({"subject_curriculum": {"Redes": {"ects": "6.5"}}})
    assert settings.subject_curriculum["Redes"]["ects"] == 6
    assert isinstance(settings.subject_curriculum["Redes"]["ects"], int)

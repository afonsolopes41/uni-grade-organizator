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

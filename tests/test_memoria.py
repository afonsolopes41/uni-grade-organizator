"""A aplicação lembra-se: fechar e voltar a abrir não perde nada."""

import json
import os

from gradeorg import storage
from gradeorg.session import Session

CSV = (
    "Nome;Nº Aluno;Nota Final\n"
    "Ana Maria Silva;112233;15,5\n"
    "Rui Costa Lopes;112234;9\n"
).encode("utf-8")


def test_sessao_nova_recupera_o_que_ficou():
    primeira = Session()
    primeira.add_file("pauta.csv", CSV)
    fonte = primeira.sources[0].id
    primeira.update(answers={f"{fonte}:subject": "Redes"})
    primeira.update(settings={"subject_curriculum": {"Redes": {"year": 2, "semester": 1}}})

    segunda = Session()
    assert [f.name for f in segunda.files] == ["pauta.csv"]
    assert segunda.answers == {f"{fonte}:subject": "Redes"}
    assert segunda.settings.subject_curriculum["Redes"]["year"] == 2
    assert segunda.result()["students"][0]["name"] == "Ana Maria Silva"


def test_as_tabelas_ficam_em_cache_para_o_arranque_ser_rapido():
    sessao = Session()
    sessao.add_file("pauta.csv", CSV)
    cache = os.path.join(storage.tables_dir(), "01.json")
    assert os.path.exists(cache)
    with open(cache, encoding="utf-8") as stream:
        assert json.load(stream)[0]["rows"][0][0] == "Nome"


def test_apagar_tudo_limpa_mesmo_o_disco():
    sessao = Session()
    sessao.add_file("pauta.csv", CSV)
    assert os.listdir(storage.files_dir())

    sessao.reset()
    assert not os.listdir(storage.files_dir())
    assert not os.path.exists(os.path.join(storage.data_home(), "01.json"))
    assert Session().files == []


def test_apagar_tudo_nao_esquece_a_lingua():
    sessao = Session()
    sessao.set_language("en")
    sessao.add_file("pauta.csv", CSV)
    sessao.reset()
    assert sessao.language == "en"
    assert Session().language == "en"


def test_remover_um_ficheiro_apaga_a_copia_guardada():
    sessao = Session()
    sessao.add_file("pauta.csv", CSV)
    sessao.remove_file("pauta.csv")
    assert not os.listdir(storage.files_dir())
    assert Session().files == []


def test_estado_estragado_nao_impede_o_arranque():
    with open(storage.state_path(), "w", encoding="utf-8") as stream:
        stream.write("{isto não é json")
    assert Session().files == []


OUTRO_CSV = (
    "Nome;Nº Aluno;Nota Final\n"
    "Marta Nunes Dias;223344;13\n"
).encode("utf-8")


def test_tirar_um_ficheiro_esquece_as_respostas_que_eram_dele():
    sessao = Session()
    sessao.add_file("pauta.csv", CSV)
    fonte = sessao.sources[0].id
    sessao.update(answers={f"{fonte}:subject": "Redes"})

    sessao.remove_file("pauta.csv")
    assert sessao.answers == {}


def test_pauta_nova_nao_herda_a_cadeira_de_uma_que_foi_tirada():
    """O bug: tirar a pauta e reabrir fazia a seguinte nascer com o nome dela."""
    primeira = Session()
    primeira.add_file("pauta.csv", CSV)
    primeira.add_file("redes.csv", CSV)
    primeira.update(answers={f"{primeira.sources[1].id}:subject": "Redes"})
    primeira.remove_file("redes.csv")

    segunda = Session()                       # fechar e voltar a abrir
    segunda.add_file("outra.csv", OUTRO_CSV)
    nova = [s for s in segunda.sources if s.filename == "outra.csv"][0]
    assert nova.id != "f2s0", "a ordem de um ficheiro tirado nao se reutiliza"
    assert nova.subject.value != "Redes"


def test_o_tema_escolhido_fica_guardado():
    primeira = Session()
    primeira.update(settings={"theme": "dark"})
    assert Session().settings.theme == "dark"


def test_um_tema_que_nao_existe_volta_ao_automatico():
    sessao = Session()
    sessao.update(settings={"theme": "roxo"})
    assert sessao.settings.theme == "auto"

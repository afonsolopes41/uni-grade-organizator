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

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# A sessao passou a guardar-se em disco. Nos testes tem de ir para um sitio
# descartavel -- nunca para a pasta real de quem corre os testes.
os.environ.setdefault("GRADEORG_HOME", tempfile.mkdtemp(prefix="gradeorg-testes-"))


@pytest.fixture(autouse=True)
def casa_isolada(tmp_path, monkeypatch):
    """Cada teste arranca com a memoria vazia, sem herdar a do teste anterior."""
    monkeypatch.setenv("GRADEORG_HOME", str(tmp_path / "estado"))
    yield

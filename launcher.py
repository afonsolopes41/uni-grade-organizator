#!/usr/bin/env python3
"""Ponto de entrada do executável.

O PyInstaller corre este ficheiro como script solto, sem pacote à volta, por
isso o import tem de ser absoluto — ``gradeorg/__main__.py`` usa imports
relativos e só serve para ``python -m gradeorg``.
"""

import multiprocessing
import sys

from gradeorg.server import main

if __name__ == "__main__":
    # Sem isto, um executável congelado que voltasse a arrancar-se a si próprio
    # abriria janelas em cadeia no Windows.
    multiprocessing.freeze_support()
    sys.exit(main())

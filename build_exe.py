#!/usr/bin/env python3
"""Constrói o executável para o sistema onde é lançado.

    python build_exe.py

No Windows sai ``dist/OrganizadorDeNotas.exe``; no macOS e no Linux sai o
binário equivalente, sem extensão. O PyInstaller não faz compilação cruzada:
para ter um .exe é preciso correr este script no Windows (ou usar o fluxo do
GitHub Actions em .github/workflows/build-exe.yml).
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REQUIREMENTS = ["flask", "pdfplumber", "openpyxl", "pyinstaller"]


def ensure_dependencies() -> None:
    missing = []
    for module, package in (("flask", "flask"), ("pdfplumber", "pdfplumber"),
                            ("openpyxl", "openpyxl"), ("PyInstaller", "pyinstaller")):
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if missing:
        print(f"A instalar: {', '.join(missing)}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])


def main() -> int:
    ensure_dependencies()
    print(f"A construir para {platform.system()} {platform.machine()}…")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", os.path.join(ROOT, "gradeorg.spec"),
         "--noconfirm", "--clean", "--distpath", os.path.join(ROOT, "dist"),
         "--workpath", os.path.join(ROOT, "build")],
        cwd=ROOT,
    )
    if result.returncode:
        return result.returncode

    name = "OrganizadorDeNotas" + (".exe" if platform.system() == "Windows" else "")
    path = os.path.join(ROOT, "dist", name)
    if os.path.exists(path):
        size = os.path.getsize(path) / (1024 * 1024)
        print(f"\nPronto: {path}  ({size:.1f} MB)")
        print("Faça duplo clique para abrir a aplicação no navegador.")
        return 0
    print("O executável não apareceu em dist/.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

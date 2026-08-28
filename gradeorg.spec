# -*- mode: python ; coding: utf-8 -*-
"""Receita do PyInstaller.

Produz um único executável que traz dentro o servidor, a página web e as
bibliotecas de leitura de PDF e Excel. Não precisa de Python instalado.

    pyinstaller gradeorg.spec --noconfirm
"""

import os
import sys

block_cipher = None

# `SPECPATH` e definido pelo PyInstaller; o fallback serve para quem execute
# este ficheiro fora dele.
ROOT = globals().get("SPECPATH") or os.path.dirname(os.path.abspath(__file__))

a = Analysis(
    [os.path.join(ROOT, "launcher.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[(os.path.join(ROOT, "gradeorg", "web"), os.path.join("gradeorg", "web"))],
    hiddenimports=[
        "gradeorg.parsers.pdf",
        "gradeorg.parsers.excel_in",
        "gradeorg.parsers.text",
        "pdfminer.pdfinterp",
        "pdfminer.converter",
        "pdfminer.layout",
        "openpyxl.cell._writer",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Nada disto e preciso e cada um custa dezenas de MB.
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "scipy", "PIL",
              "IPython", "pytest", "setuptools", "pip"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="OrganizadorDeNotas",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,          # a janela mostra o endereço e serve de "botão de fechar"
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

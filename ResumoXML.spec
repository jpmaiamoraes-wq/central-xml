# ResumoXML.spec
# Build onedir (COLLECT) incluindo pasta assets e dados necessários.
# Use:
#   pyinstaller ResumoXML.spec --clean
# ou com paths customizados:
#   pyinstaller ResumoXML.spec --clean --workpath .\build_new --distpath .\dist_new

# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# -------- Pacotes: submódulos e dados --------
hiddenimports = []
datas = []

# dash_bootstrap_components
hiddenimports += collect_submodules('dash_bootstrap_components')
datas += collect_data_files('dash_bootstrap_components')

# Motores Excel
try:
    hiddenimports += collect_submodules('xlsxwriter')
    datas += collect_data_files('xlsxwriter')
except Exception:
    pass

try:
    hiddenimports += collect_submodules('openpyxl')
    datas += collect_data_files('openpyxl')
except Exception:
    pass

# --- NOSSAS NOVAS DEPENDÊNCIAS ---
# Adiciona as bibliotecas que importamos dinamicamente
# ATUALIZADO: Removemos 'py7zr'
hiddenimports += ['rarfile', 'openpyxl','logic_nfse_split','parsers.router','core.normalizer',]

# -------- Pasta local "assets" (logo, CSS, etc.) --------
if os.path.isdir('assets'):
    try:
        from PyInstaller.building.datastruct import Tree
        datas += Tree('assets', prefix='assets').tolist()
    except Exception:
        for root, _, files in os.walk('assets'):
            for f in files:
                src = os.path.join(root, f)
                rel = os.path.relpath(src, 'assets')
                dst = os.path.join('assets', os.path.dirname(rel))
                datas.append((src, dst))

# --- NOSSO NOVO BINÁRIO (unrar.exe) ---
# (Certifique-se que 'unrar.exe' está na mesma pasta que este .spec)
if os.path.exists('unrar.exe'):
    datas.append(('unrar.exe', '.'))
else:
    print("AVISO DE BUILD: 'unrar.exe' não encontrado. A Aba 1 falhará ao extrair .rar.")

# --- NOSSO NOVO BINÁRIO (7z.exe) ---
# ATUALIZAÇÃO: Adicionamos o 7z.exe
# (Certifique-se que '7z.exe' está na mesma pasta que este .spec)
if os.path.exists('7z.exe'):
    datas.append(('7z.exe', '.'))
else:
    print("AVISO DE BUILD: '7z.exe' não encontrado. A Aba 1 falhará ao extrair .7z.")


# -------- Script de entrada --------
# --- MUDANÇA 1: Aponta para o script correto ---
ENTRY_SCRIPT = 'app.py'

a = Analysis(
    [ENTRY_SCRIPT],
    pathex=[],
    binaries=[],
    datas=datas,                     # <-- MUDANÇA 2: Usa a lista 'datas' que construímos
    hiddenimports=hiddenimports,     # <-- MUDANÇA 3: Usa a lista 'hiddenimports' que construímos
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ResumoXML',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,   # Mude para True se quiser ver os logs de 'print' no .exe
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ResumoXML'
)
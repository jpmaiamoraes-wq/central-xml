# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# -------- Configurações de Caminhos --------
current_dir = os.getcwd()

# -------- Pacotes: submódulos e dados --------
hiddenimports = [
    'docx',
    'rarfile', 
    'openpyxl',
    'logic_nfse_split',
    'logic_converter',
    'logic_extrator',
    'logic_resumo',
    'logic_sped',
    'utils',
    'parsers.router',
    'core.normalizer'
]

datas = []

# dash_bootstrap_components
hiddenimports += collect_submodules('dash_bootstrap_components')
datas += collect_data_files('dash_bootstrap_components')

# --- ARQUIVOS DE DADOS E PASTAS (MUDANÇA AQUI) ---

# 1. Arquivo Excel
if os.path.exists('Cod.-de-servico-SP-x-Campinas.xlsx'):
    datas.append(('Cod.-de-servico-SP-x-Campinas.xlsx', '.'))

# 2. Pastas de lógica/core (copiando como diretórios)
for folder in ['core', 'parsers', 'schemas']:
    if os.path.isdir(folder):
        datas.append((folder, folder))

# 3. Pasta Assets
if os.path.isdir('assets'):
    datas.append(('assets', 'assets'))

# 4. Binários extras (unrar e 7z)
for binary in ['unrar.exe', '7z.exe']:
    if os.path.exists(binary):
        datas.append((binary, '.'))
    else:
        print(f"AVISO DE BUILD: '{binary}' não encontrado.")

# -------- Script de entrada --------
ENTRY_SCRIPT = 'app.py'

a = Analysis(
    [ENTRY_SCRIPT],
    pathex=[current_dir], # Adiciona o diretório atual ao path de busca
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    console=False, # Mude para True se precisar debugar erros de importação
    icon=None      # Adicione o caminho do ícone aqui se tiver um .ico
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
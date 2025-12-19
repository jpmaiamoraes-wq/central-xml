# app.py
import os
import base64
import io
import zipfile
import subprocess      
import tempfile  
import shutil 


import pandas as pd
from dash import Dash, dcc, html, Input, Output, State, dash_table, no_update, ctx
import dash_bootstrap_components as dbc

from utils import base_path, digits, mask_cnpj, fmt_period, log_message, clean_dir
from logic_extrator import (
    extract_7z,
    extrair_e_classificar_extrator,
    extrair_xmls_recursivamente,
)
from logic_resumo import (
    summarize_zipfile_resumo,
    build_detail_from_zip_resumo,
    build_items_from_zip_resumo,
)
from logic_sped import parse_sped_from_any

from logic_nfse_split import split_nfse_abrasf, make_zip_bytes



BASE_PATH = base_path()
ASSETS_PATH = os.path.join(BASE_PATH, "assets")

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    assets_folder=ASSETS_PATH,
    assets_url_path="/assets",
    serve_locally=True,
)

logo_path = os.path.join(ASSETS_PATH, "sankhya-logo.svg")
if os.path.exists(logo_path):
    logo_src = app.get_asset_url("sankhya-logo.svg")
else:
    logo_src = "https://via.placeholder.com/150x30.png?text=Logo"

server = app.server
server.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

# --- CABEÇALHO GLOBAL (Fora das Abas) ---
global_header = dbc.Card([
    dbc.CardBody([
        dbc.Row([
            dbc.Col(html.Img(src=logo_src, style={'height': '30px'}), width='auto'),
            dbc.Col(html.H4('Central de Ferramentas XML', className='mb-0 resumo-titulo'), width='auto'),
        ], align='center', className='g-2 mb-4'),

        dbc.Row([
            dbc.Col(
                dbc.InputGroup([
                    dbc.InputGroupText('CNPJ próprio'),
                    dbc.Input(id='input-cnpj', type='text', placeholder='00.000.000/0000-00', style={'maxWidth': '280px'}),
                ]),
                md='auto',
                className='me-3',
            ),
            dbc.Col(
                html.Div(
                    [
                        dbc.Button('Adicionar', id='btn-add-cnpj', color='primary', n_clicks=0, class_name='me-1'),
                        dbc.Button('Limpar CNPJs', id='btn-clear-cnpj', color='secondary', n_clicks=0),
                    ],
                    className='btn-group-tight d-flex align-items-center',
                ),
                width='auto',
            ),
        ], align='center', className='mb-2'),

        html.Div(id='cnpj-chips', className='d-flex flex-wrap gap-2'),
    ], style={'padding': '24px 28px'}),
], class_name='mb-3 border-0 shadow-sm', style={'backgroundColor': '#eef0f3', 'borderRadius': '12px'})

# --- ABA 1: Conteúdo do Extrator (Rápido) ---
tab_extrator_content = dbc.Card([
    dbc.CardBody([
        html.Strong("1. Arquivo .ZIP de Origem"),
        dcc.Input(id='input-origem-zip', type='text', placeholder=r'C:\\Caminho\\Para\\arquivo_original.zip', style={'width': '100%', 'marginBottom': '10px'}),
        
        html.Strong("2. Modo de Extração"),
        dcc.RadioItems(
            id='radio-modo-extrator',
            options=[
                {'label': ' Juntar Tudo (Extração Rápida)', 'value': 'juntar'},
                {'label': ' Separar pelo Emitente (Classificação)', 'value': 'separar'},
            ],
            value='juntar', # Padrão
            inline=True,
            style={'marginBottom': '15px'}
        ),

        # --- Campos para "Juntar Tudo" ---
        html.Div(id='modo-juntar-campos', children=[
            html.Strong("3. Pasta de Destino (para todos os XMLs)"),
            dcc.Input(id='input-destino-juntar', type='text', placeholder=r'C:\\XML_Extraidos_Todos', style={'width': '100%', 'marginBottom': '15px'}),
        ], style={'display': 'block'}), # Visível por padrão

        # --- Campos para "Separar pelo Emitente" ---
        html.Div(id='modo-separar-campos', children=[
            html.Strong("3. Pastas de Destino para Classificação"),
            dbc.Row([
                dbc.Col(
                    dbc.InputGroup([
                        dbc.InputGroupText("Próprios"),
                        dcc.Input(id='input-destino-proprios', type='text', placeholder=r'C:\\XML_Extraidos\\Proprios'),
                    ]), md=4
                ),
                dbc.Col(
                    dbc.InputGroup([
                        dbc.InputGroupText("Terceiros"),
                        dcc.Input(id='input-destino-terceiros', type='text', placeholder=r'C:\\XML_Extraidos\\Terceiros'),
                    ]), md=4
                ),
                dbc.Col(
                    dbc.InputGroup([
                        dbc.InputGroupText("Outros"),
                        dcc.Input(id='input-destino-outros', type='text', placeholder=r'C:\\XML_Extraidos\\Outros'),
                    ]), md=4
                ),
            ], className='mb-3'),
        ], style={'display': 'none'}), # Oculto por padrão
        
        dcc.Loading(id='loading-processar-extrator', children=[
            dbc.Button('Iniciar Extração', id='btn-processar-pastas-extrator', color='success', n_clicks=0, className='w-100'),
        ]),
        
        html.Hr(),
        html.Strong("Log de Processamento (Extrator):"),
        html.Div(
            dcc.Textarea(id='log-textarea-extrator', style={'width': '100%', 'height': '200px', 'fontSize': '12px'}, readOnly=True, value="Aguardando processamento..."),
            style={'fontFamily': 'monospace'}
        )
    ])
], class_name='mt-3')

# --- ABA 2: Conteúdo do Resumo/Itens ---
tab_resumo_content = dbc.Card([
    dbc.CardBody([
        dcc.Upload(
            id='upload-zip-resumo',
            accept='.zip,application/zip',
            multiple=False,
            children=html.Div(['Clique para selecionar o .zip']),
            style={
                'width': '100%',
                'height': '70px',
                'lineHeight': '70px',
                'borderWidth': '1px',
                'borderStyle': 'dashed',
                'borderRadius': '5px',
                'textAlign': 'center',
                'marginBottom': '10px',
            },
        ),
        html.Details(
            children=[
                html.Summary('Usar ARQUIVO LOCAL (.zip) recomendado para arquivos muito grandes'),
                html.Div([
                    dcc.Input(id='local-zip-path-resumo', type='text', placeholder=r'C:\\caminho\\para\\arquivo.zip', style={'width': '60%'}),
                    dbc.Button('Processar arquivo local', id='btn-process-local-resumo', n_clicks=0, class_name='ms-2'),
                ], style={'marginTop': '6px'}),
            ],
            open=False,
            style={'margin': '8px 0'},
        ),
        html.Div(id='file-info-resumo', style={'marginBottom': '10px', 'fontStyle': 'italic'}),
        
        html.Div([
            dcc.Loading(
                id='loading-download-detalhe-resumo',
                type='default',
                children=dbc.Button('Detalhe Excel', id='btn-download-detalhe-resumo', color='success', class_name='me-2'),
            ),
            dcc.Download(id='download-detalhe-resumo'),
            dbc.Button('Baixar Itens (Excel)', id='btn-baixar-excel-resumo', color='primary', class_name='me-2'),
            dcc.Download(id='download-excel-resumo'),
            dbc.Button('Limpar arquivo', id='btn-clear-file-resumo', color='danger', outline=True),
        ], className='d-flex gap-2 mb-2'),

        dash_table.DataTable(
            id='tabela-resumo-resumo',
            columns=[
                {"name": "CNPJ", "id": "CNPJ"},
                {"name": "Emissão Própria", "id": "QTD"},
                {"name": "Emissão de Terceiros", "id": "QTDETERC"},
            ],
            data=[],
            page_size=10,
            style_table={'marginTop': '10px'},
            style_cell={'textAlign': 'center', 'padding': '6px'},
            style_header={'fontWeight': 'bold'},
            active_cell={'row': 0, 'column': 0},
        ),
        html.Div([
            dbc.Modal([
                dbc.ModalHeader(dbc.ModalTitle('Detalhe por Modelo')),
                dbc.ModalBody(id='modal-content-resumo'),
                dbc.ModalFooter(dbc.Button('Fechar', id='btn-close-modal-resumo', color='secondary')),
            ], id='modal-resumo', is_open=False)
        ]),
    ])
], class_name='mt-3')

# --- ABA 3: Conteúdo do SPED Fiscal (TXT) ---
tab_sped_content = dbc.Card([
    dbc.CardBody([
        html.H5("Análise de SPED Fiscal (EFD ICMS/IPI - TXT)", className="mb-3"),

        dcc.Upload(
            id='upload-sped',
            accept='.txt,.zip,text/plain,application/zip',
            multiple=False,
            children=html.Div(['Clique aqui para selecionar o arquivo TXT do SPED']),
            style={
                'width': '100%',
                'height': '70px',
                'lineHeight': '70px',
                'borderWidth': '1px',
                'borderStyle': 'dashed',
                'borderRadius': '5px',
                'textAlign': 'center',
                'marginBottom': '10px',
            },
        ),

        html.Div(id='file-info-sped', style={'marginBottom': '10px', 'fontStyle': 'italic'}),

        html.Div([
            dbc.Button('Baixar Excel (0190 / 0200 / C100+C170)',
                       id='btn-download-sped',
                       color='success',
                       class_name='me-2'),
            dcc.Download(id='download-sped'),
        ], className='d-flex gap-2 mb-3'),

        html.Small("Prévia (C100 + C170 - apenas algumas linhas):"),

        dash_table.DataTable(
            id='tabela-sped-preview',
            data=[],
            columns=[],
            page_size=10,
            style_table={'marginTop': '10px', 'overflowX': 'auto'},
            style_cell={'textAlign': 'center', 'padding': '6px', 'fontSize': 11},
            style_header={'fontWeight': 'bold'},
        ),
    ])
], class_name='mt-3')

tab_nfse_split_content = dbc.Card([
    dbc.CardBody([
        html.H5("Separar NFSe (XML em lote)", className="mb-2"),
        html.Small("Envie um XML que contenha várias NFSe (ABRASF / CompNfse). Eu separo e gero um ZIP com os XMLs individuais."),

        html.Hr(),

        dcc.Upload(
            id='upload-nfse-lote',
            accept='.xml,application/xml,text/xml',
            multiple=False,
            children=html.Div(['Clique para selecionar o XML de NFSe (lote)']),
            style={
                'width': '100%',
                'height': '70px',
                'lineHeight': '70px',
                'borderWidth': '1px',
                'borderStyle': 'dashed',
                'borderRadius': '5px',
                'textAlign': 'center',
                'marginBottom': '10px',
            },
        ),

        html.Div(id='file-info-nfse-split', style={'marginBottom': '10px', 'fontStyle': 'italic'}),

        dbc.Button('Gerar ZIP (NFSe Separadas)', id='btn-gerar-zip-nfse', color='primary', class_name='me-2'),
        dcc.Download(id='download-zip-nfse'),

        html.Div(id='status-nfse-split', className='mt-3'),
    ])
], class_name='mt-3')

# --- LAYOUT PRINCIPAL COM ABAS ---
app.layout = dbc.Container([
    
    global_header, # Cabeçalho com CNPJ fica no topo
    
        dcc.Tabs(id="tabs-container", value='tab-extrator', children=[
        
        dcc.Tab(
            label='Extrator de XML', 
            value='tab-extrator', 
            children=tab_extrator_content
        ),
        
        dcc.Tab(
            label='Resumo/Análise de Itens', 
            value='tab-resumo', 
            children=tab_resumo_content
        ),

        dcc.Tab(
            label='SPED Fiscal (TXT)', 
            value='tab-sped', 
            children=tab_sped_content
        ),
        
        dcc.Tab(
            label='Separar NFSe (Lote)',
            value='tab-nfse-split',
            children=tab_nfse_split_content
        ),    
    ]),


    # Stores GLOBAIS
    dcc.Store(id='store-cnpjs', data=[]),
    
    # Stores da ABA 1
    dcc.Store(id='store-log-extrator', data=[]),
    
    # Stores da ABA 2
    dcc.Store(id='store-rows-resumo', data=[]),
    dcc.Store(id='store-breakdown-resumo', data={}),
    dcc.Store(id='store-excel-detalhe-resumo', data=[]),
    dcc.Store(id='store-items-resumo', data=[]),
    dcc.Store(id='store-zip-b64-resumo', data=None),
    dcc.Store(id='store-selected-cnpj-resumo', data=None),
    dcc.Store(id='store-modal-open-resumo', data=False),

    # Stores da ABA 3 (SPED)
    dcc.Store(id='store-sped-0190', data=[]),
    dcc.Store(id='store-sped-0200', data=[]),
    dcc.Store(id='store-sped-c100c170', data=[]),

    
], fluid=True)

# =============================================================
# Callbacks GLOBAIS (CNPJ)
# =============================================================

@app.callback(
    Output('store-cnpjs', 'data', allow_duplicate=True),
    Output('input-cnpj', 'value', allow_duplicate=True),
    Input('btn-add-cnpj', 'n_clicks'),
    State('input-cnpj', 'value'),
    State('store-cnpjs', 'data'),
    prevent_initial_call=True,
)
def add_cnpj(n, val, current):
    if not n or not val:
        return no_update, no_update

    d = digits(val)

    # agora aceita CNPJ (14) ou CPF (11)
    if not d or len(d) not in (11, 14):
        return no_update, no_update

    cur = (current or []).copy()
    if d not in cur:
        cur.append(d)

    # limpa o campo de entrada depois de adicionar
    return cur, ''

@app.callback(
    Output('store-cnpjs', 'data', allow_duplicate=True),
    Input('btn-clear-cnpj', 'n_clicks'),
    prevent_initial_call=True,
)
def clear_cnpj(_):
    return []

@app.callback(Output('cnpj-chips', 'children'), Input('store-cnpjs', 'data'))
def show_chips(data):
    return [dbc.Badge(mask_cnpj(d), color='primary', className='p-2') for d in (data or [])]

# =============================================================
# Callbacks da ABA 1 (Extrator)
# =============================================================

@app.callback(Output('log-textarea-extrator', 'value'), Input('store-log-extrator', 'data'))
def update_log_display_extrator(log_data):
    return "\n".join(log_data or ["Aguardando..."])

# NOVO CALLBACK: Alterna a visibilidade dos campos de destino
@app.callback(
    Output('modo-juntar-campos', 'style'),
    Output('modo-separar-campos', 'style'),
    Input('radio-modo-extrator', 'value'),
    prevent_initial_call=False # Executa na inicialização
)
def toggle_extraction_mode_fields(modo):
    if modo == 'juntar':
        return {'display': 'block'}, {'display': 'none'}
    else: # modo == 'separar'
        return {'display': 'none'}, {'display': 'block'}


@app.callback(
    Output('store-log-extrator', 'data'),
    Input('btn-processar-pastas-extrator', 'n_clicks'),
    State('input-origem-zip', 'value'),
    State('radio-modo-extrator', 'value'),
    # Campos do Modo "Juntar"
    State('input-destino-juntar', 'value'),
    # Campos do Modo "Separar"
    State('input-destino-proprios', 'value'),
    State('input-destino-terceiros', 'value'),
    State('input-destino-outros', 'value'),
    # Store Global
    State('store-cnpjs', 'data'), 
    prevent_initial_call=True,
)
def processar_pastas_extrator(n_clicks, caminho_origem, modo, 
                             pasta_juntar, 
                             pasta_proprios, pasta_terceiros, pasta_outros, 
                             cnpjs):
    if not n_clicks:
        return no_update

# --- CORREÇÃO: Mover imports para dentro do callback ---
    global rarfile, RAR_SUPPORT, P7Z_SUPPORT, EXTRACTORS, SUPPORTED_ARCHIVES

    # --- RAR ---
    try:
        import rarfile
        RAR_SUPPORT = True
    except Exception as e:
        # Se der qualquer erro na importação, desabilita RAR
        print("Erro ao importar rarfile dentro do app:", e)
        RAR_SUPPORT = False

    # --- 7Z ---
    P7Z_SUPPORT = False
    try:
        subprocess.run(['7z'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        P7Z_SUPPORT = True
    except FileNotFoundError:
        P7Z_SUPPORT = False

    # Mapa de extratores
    EXTRACTORS = {
        ".zip": lambda path, dest: zipfile.ZipFile(path, 'r').extractall(dest),
        ".7z":  lambda path, dest: extract_7z(path, dest),
    }

    # Só adiciona o .rar se o suporte estiver OK
    if RAR_SUPPORT:
        EXTRACTORS[".rar"] = lambda path, dest: rarfile.RarFile(path, 'r').extractall(dest)
    
    SUPPORTED_ARCHIVES = list(EXTRACTORS.keys())
    if not RAR_SUPPORT:
        if ".rar" in SUPPORTED_ARCHIVES: SUPPORTED_ARCHIVES.remove(".rar")
    if not P7Z_SUPPORT:
        if ".7z" in SUPPORTED_ARCHIVES: SUPPORTED_ARCHIVES.remove(".7z")
    # --- FIM DA CORREÇÃO ---

    logs = []
    # Log de diagnóstico das extensões suportadas
    logs = log_message(logs, f"RAR_SUPPORT = {RAR_SUPPORT}, P7Z_SUPPORT = {P7Z_SUPPORT}")
    logs = log_message(logs, f"SUPPORTED_ARCHIVES = {SUPPORTED_ARCHIVES}")
    own_set = {digits(c) for c in (cnpjs or []) if str(c).strip()}
    
    # --- Validação ---
    if not caminho_origem:
        logs = log_message(logs, "ERRO: Por favor, informe o caminho do 'Arquivo .ZIP de Origem'.")
        return logs

    if not os.path.exists(caminho_origem) or not os.path.isfile(caminho_origem):
        logs = log_message(logs, f"ERRO: Arquivo de origem não encontrado: {caminho_origem}")
        return logs

    ext_origem = os.path.splitext(caminho_origem)[1].lower()
    if ext_origem != ".zip":
        logs = log_message(
            logs,
            "ERRO: O arquivo de origem deve ser um .ZIP. "
            f"Use um ZIP que contenha os RAR/7Z/XML dentro. Arquivo informado: {ext_origem}"
        )
        return logs

    pastas_destino = {}
    pasta_temp_inicial = tempfile.mkdtemp(prefix="ext_main_zip_")
    xmls_movidos_total = 0

    try:
        # --- Lógica de Extração ---
        logs = log_message(logs, "--- INICIANDO EXTRAÇÃO ---")
        logs = log_message(logs, f"De: {caminho_origem}")

        
        # Extrai o ZIP principal
        with zipfile.ZipFile(caminho_origem, 'r') as zf:
            zf.extractall(pasta_temp_inicial)
        
        for raiz, dirs, files in os.walk(pasta_temp_inicial):
            logs = log_message(logs, f"[DEBUG] Pasta dentro do ZIP: {raiz}")
            for d in dirs:
                logs = log_message(logs, f"[DEBUG]   DIR: {d}")
            for f in files:
                logs = log_message(logs, f"[DEBUG]   FILE: {f}")

        if modo == 'separar':
            # Validação do modo "Separar"
            if not pasta_proprios or not pasta_terceiros or not pasta_outros:
                logs = log_message(logs, "ERRO: Por favor, preencha todas as 3 'Pastas de Destino' para o modo 'Separar'.")
                return logs
            if not own_set:
                logs = log_message(logs, "ERRO: Para 'Separar pelo Emitente', você deve cadastrar um CNPJ próprio no topo.")
                return logs
            
            pastas_destino = {
                'proprios': pasta_proprios,
                'terceiros': pasta_terceiros,
                'outros': pasta_outros
            }
            # Cria/Limpa as pastas de destino
            for nome, caminho in pastas_destino.items():
                os.makedirs(caminho, exist_ok=True)
                logs = log_message(logs, f"Pasta de destino '{nome}' pronta: {caminho}")
                clean_dir(caminho)

            # Chama a função de CLASSIFICAÇÃO
            logs, xmls_movidos_total = extrair_e_classificar_extrator(
                pasta_temp_inicial, pastas_destino, own_set, logs,
                EXTRACTORS, SUPPORTED_ARCHIVES
            )

        else: # modo == 'juntar'
            # Validação do modo "Juntar"
            if not pasta_juntar:
                logs = log_message(logs, "ERRO: Por favor, preencha a 'Pasta de Destino' para o modo 'Juntar Tudo'.")
                return logs
                
            os.makedirs(pasta_juntar, exist_ok=True)
            logs = log_message(logs, f"Pasta de destino pronta: {pasta_juntar}")
            clean_dir(pasta_juntar)

            # Chama a função de extração RÁPIDA
            logs, xmls_movidos_total = extrair_xmls_recursivamente(
                pasta_temp_inicial, pasta_juntar, logs,
                EXTRACTORS, SUPPORTED_ARCHIVES
            )
        
        logs = log_message(logs, "--- EXTRAÇÃO CONCLUÍDA ---")
        
    except Exception as e:
        logs = log_message(logs, f"ERRO FATAL NA EXTRAÇÃO: {e}")
    finally:
        try:
            shutil.rmtree(pasta_temp_inicial)
        except Exception:
            pass

    logs = log_message(logs, f"--- PROCESSAMENTO CONCLUÍDO ---")
    logs = log_message(logs, f"Total de {xmls_movidos_total} XMLs extraídos e movidos.")
    return logs

# =============================================================
# Callbacks da ABA 2 (Resumo/Itens)
# =============================================================

# --- ATUALIZADO (PATCH 5): Callback process_upload_resumo (novo log) ---

@app.callback(
    Output('file-info-resumo', 'children', allow_duplicate=True),
    Output('store-rows-resumo', 'data', allow_duplicate=True),
    Output('store-breakdown-resumo', 'data', allow_duplicate=True),
    Output('store-excel-detalhe-resumo', 'data', allow_duplicate=True),
    Output('store-items-resumo', 'data', allow_duplicate=True),
    Output('store-zip-b64-resumo', 'data', allow_duplicate=True),
    Input('upload-zip-resumo', 'contents'),
    State('upload-zip-resumo', 'filename'),
    State('store-cnpjs', 'data'), # <-- Usa o store global
    prevent_initial_call=True,
)
def process_upload_resumo(contents, filename, own_cnpjs):
    if not contents:
        return no_update, no_update, no_update, no_update, no_update, no_update
    own_set = {digits(c) for c in (own_cnpjs or []) if str(c).strip()}
    if not own_set:
         return "ERRO: Adicione um CNPJ próprio no topo da página antes de processar.", no_update, no_update, no_update, no_update, no_update

    try:
        header, b64 = contents.split(',', 1)
        data = base64.b64decode(b64)
        # --- ATUALIZADO: Novos valores de retorno ---
        with zipfile.ZipFile(io.BytesIO(data), 'r') as zf:
            rows, breakdown, total_docs, warns, total_xmls, total_outros_desconhecidos, total_eventos,total_duplicados, total_intercompany, pmin, pmax = summarize_zipfile_resumo(zf, own_set)
        with zipfile.ZipFile(io.BytesIO(data), 'r') as zf:
            detalhe = build_detail_from_zip_resumo(zf, own_set)
        with zipfile.ZipFile(io.BytesIO(data), 'r') as zf:
            itens_rows = build_items_from_zip_resumo(zf, own_set)
    except Exception as e:
        return f"Erro no upload: {e}", None, None, None, None, None

    extra = (" | Avisos: " + "; ".join(sorted(warns))) if warns else ""
    nome = filename or "(sem nome)"
    
    # --- ATUALIZADO: Log de informação ---
    info = (
        f"(Upload) Arquivo: {nome} | Total XMLs: {total_xmls} | XMLs processados (DF-e): {total_docs} | "
        f"Eventos/Inutilização: {total_eventos} | Duplicados (chave repetida): {total_duplicados} | Outros XMLs: {total_outros_desconhecidos}{extra} | Operações Intercompany: {total_intercompany} | Período: {fmt_period(pmin)} - {fmt_period(pmax)}"
    )
    return info, rows, breakdown, detalhe, itens_rows, None # Não salva o B64

# --- ATUALIZADO (PATCH 6): Callback process_local_zip_resumo (novo log) ---
@app.callback(
    Output('file-info-resumo', 'children', allow_duplicate=True),
    Output('store-rows-resumo', 'data', allow_duplicate=True),
    Output('store-breakdown-resumo', 'data', allow_duplicate=True),
    Output('store-excel-detalhe-resumo', 'data', allow_duplicate=True),
    Output('store-items-resumo', 'data', allow_duplicate=True),
    Output('store-zip-b64-resumo', 'data', allow_duplicate=True),
    Input('btn-process-local-resumo', 'n_clicks'),
    State('local-zip-path-resumo', 'value'),
    State('store-cnpjs', 'data'), # <-- Usa o store global
    prevent_initial_call=True,
)
def process_local_zip_resumo(n, path, own_cnpjs):
    try:
        if not n:
            return no_update, no_update, no_update, no_update, no_update, no_update
        own_set = {digits(c) for c in (own_cnpjs or []) if str(c).strip()}
        if not own_set:
            return "ERRO: Adicione um CNPJ próprio no topo da página antes de processar.", no_update, no_update, no_update, no_update, no_update
            
        if not path or not os.path.exists(path):
            return 'Caminho inválido. Informe o caminho completo do .zip.', None, None, None, None, None
        if not zipfile.is_zipfile(path):
            return 'O arquivo informado não é um ZIP válido.', None, None, None, None, None
        
        with open(path, 'rb') as fh:
            file_bytes = fh.read()
        
        # --- ATUALIZADO: Novos valores de retorno ---
        with zipfile.ZipFile(io.BytesIO(file_bytes), 'r') as zf:
            rows, breakdown, total_docs, warns, total_xmls, total_outros_desconhecidos, total_eventos, total_duplicados, total_intercompany, pmin, pmax = summarize_zipfile_resumo(zf, own_set)
        with zipfile.ZipFile(io.BytesIO(file_bytes), 'r') as zf:
            detalhe = build_detail_from_zip_resumo(zf, own_set)
        with zipfile.ZipFile(io.BytesIO(file_bytes), 'r') as zf:
            itens_rows = build_items_from_zip_resumo(zf, own_set)

        extra = (" | Avisos: " + "; ".join(sorted(warns))) if warns else ""
        
        # --- ATUALIZADO: Log de informação ---
        info = (
            f"(Local) Arquivo: {os.path.basename(path)} | Total XMLs: {total_xmls} | XMLs processados (DF-e): {total_docs} | "
            f"Eventos/Inutilização: {total_eventos} | Duplicados: {total_duplicados} |  Outros XMLs: {total_outros_desconhecidos}{extra} |  Operações Intercompany: {total_intercompany} |Período: {fmt_period(pmin)} - {fmt_period(pmax)}"
        )
        return info, rows, breakdown, detalhe, itens_rows, None # Não salva o b64
    except Exception as e:
        return f"Erro ao processar arquivo local: {e}", None, None, None, None, None

@app.callback(
    Output('tabela-resumo-resumo', 'data'), 
    Input('store-rows-resumo', 'data')
)
def fill_table_resumo(data):
    return data or []

@app.callback(
    Output('store-selected-cnpj-resumo', 'data', allow_duplicate=True),
    Input('tabela-resumo-resumo', 'active_cell'),
    State('tabela-resumo-resumo', 'data'),
    prevent_initial_call=True,
)
def select_row_resumo(cell, data):
    if not cell or not data or cell['row'] >= len(data):
        return no_update
    row = data[cell['row']]
    return row.get('CNPJ')


@app.callback(
    Output('store-modal-open-resumo', 'data', allow_duplicate=True),
    Input('store-selected-cnpj-resumo', 'data'),
    prevent_initial_call=True,
)
def open_modal_resumo(selected_cnpj):
    if not selected_cnpj:
        return no_update
    return True


@app.callback(
    Output('modal-resumo', 'is_open'),
    Output('modal-content-resumo', 'children'),
    Input('store-modal-open-resumo', 'data'),
    State('store-selected-cnpj-resumo', 'data'),
    State('store-breakdown-resumo', 'data'),
)
def render_modal_resumo(is_open, selected_key, breakdown):
    if not is_open:
        return False, ''
    bd = breakdown or {}
    m = bd.get(selected_key or '', {})
    if not m:
        return True, html.Div('Sem informações.')

    P55 = m.get('P', {}).get('55', 0)
    P65 = m.get('P', {}).get('65', 0)
    P57 = m.get('P', {}).get('57', 0)
    PNFSE = m.get('P',{}).get('NFSE',0)
    T55 = m.get('T', {}).get('55', 0)
    T65 = m.get('T', {}).get('65', 0)
    T57 = m.get('T', {}).get('57', 0)
    TNFSE = m.get('T',{}).get('NFSE',0)

    col_propria = html.Div([
        html.H5('Emissão Própria', className='mb-3'),
        html.Div([html.Strong('NF-e (55): '), f"{P55}"]),
        html.Div([html.Strong('NFC-e (65): '), f"{P65}"]),
        html.Div([html.Strong('CT-e (57): '), f"{P57}"]),
        html.Div([html.Strong('NFSE: '), f"{PNFSE}"]),
    ], style={'padding': '6px'})

    col_terceiros = html.Div([
        html.H5('Emissão de Terceiros', className='mb-3'),
        html.Div([html.Strong('NF-e (55): '), f"{T55}"]),
        html.Div([html.Strong('NFC-e (65): '), f"{T65}"]),
        html.Div([html.Strong('CT-e (57): '), f"{T57}"]),
        html.Div([html.Strong('NFSE: '), f"{TNFSE}"]),
    ], style={'padding': '6px'})

    content = dbc.Row([dbc.Col(col_propria, md=6), dbc.Col(col_terceiros, md=6)])
    return True, content


@app.callback(
    Output('store-modal-open-resumo', 'data', allow_duplicate=True),
    Input('btn-close-modal-resumo', 'n_clicks'),
    prevent_initial_call=True,
)
def close_modal_resumo(_):
    return False

@app.callback(
    Output('download-detalhe-resumo', 'data'),
    Input('btn-download-detalhe-resumo', 'n_clicks'),
    State('store-excel-detalhe-resumo', 'data'),
    prevent_initial_call=True,
)
def on_download_detalhe_resumo(n, detalhe_rows):
    if not n or not detalhe_rows:
        return no_update
    df = pd.DataFrame(detalhe_rows)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, sheet_name='Detalhe')
    buf.seek(0)
    return dcc.send_bytes(buf.getvalue(), 'detalhe.xlsx')

@app.callback(
    Output('download-excel-resumo', 'data'),
    Input('btn-baixar-excel-resumo', 'n_clicks'),
    State('store-items-resumo', 'data'),
    prevent_initial_call=True,
)
def on_download_excel_resumo(n, items_rows):
    if not n or not items_rows:
        return no_update
    
    df_itens = pd.DataFrame(items_rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df_itens.to_excel(writer, index=False, sheet_name='Itens_DF-e')
    buf.seek(0)
    return dcc.send_bytes(buf.getvalue(), 'itens_dfe.xlsx')

@app.callback(
    Output('upload-zip-resumo', 'contents', allow_duplicate=True),
    Output('file-info-resumo', 'children', allow_duplicate=True),
    Output('store-rows-resumo', 'data', allow_duplicate=True),
    Output('store-breakdown-resumo', 'data', allow_duplicate=True),
    Output('store-excel-detalhe-resumo', 'data', allow_duplicate=True),
    Output('store-items-resumo', 'data', allow_duplicate=True),
    Output('store-zip-b64-resumo', 'data', allow_duplicate=True),
    Input('btn-clear-file-resumo', 'n_clicks'),
    prevent_initial_call=True,
)
def clear_file_resumo(n):
    if not n:
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update
    return None, 'Arquivo limpo. Selecione um novo .zip.', [], {}, [], [], None

# =============================================================
# Callbacks da ABA 3 (SPED Fiscal TXT)
# =============================================================

@app.callback(
    Output('file-info-sped', 'children'),
    Output('store-sped-0190', 'data'),
    Output('store-sped-0200', 'data'),
    Output('store-sped-c100c170', 'data'),
    Input('upload-sped', 'contents'),
    State('upload-sped', 'filename'),
    prevent_initial_call=True,
)
def process_upload_sped(contents, filename):
    if not contents:
        return no_update, no_update, no_update, no_update

    try:
        header, b64 = contents.split(',', 1)
        data = base64.b64decode(b64)
        df_0190, df_0200, df_c100_c170 = parse_sped_from_any(data, filename)
    except Exception as e:
        return f"Erro ao processar arquivo: {e}", [], [], []

    info = f"Arquivo: {filename or '(sem nome)'} | Reg. 0190: {len(df_0190)} linhas | Reg. 0200: {len(df_0200)} linhas | Itens C100/C170: {len(df_c100_c170)} linhas"

    return (
        info,
        df_0190.to_dict('records'),
        df_0200.to_dict('records'),
        df_c100_c170.to_dict('records'),
    )


@app.callback(
    Output('tabela-sped-preview', 'data'),
    Output('tabela-sped-preview', 'columns'),
    Input('store-sped-c100c170', 'data'),
)
def update_sped_preview(data):
    if not data:
        return [], []
    # monta colunas dinamicamente
    cols = [{'name': k, 'id': k} for k in data[0].keys()]
    return data, cols


@app.callback(
    Output('download-sped', 'data'),
    Input('btn-download-sped', 'n_clicks'),
    State('store-sped-0190', 'data'),
    State('store-sped-0200', 'data'),
    State('store-sped-c100c170', 'data'),
    prevent_initial_call=True,
)
def download_sped_excel(n_clicks, data_0190, data_0200, data_c100c170):
    if not n_clicks:
        return no_update
    if not (data_0190 or data_0200 or data_c100c170):
        return no_update

    df_0190 = pd.DataFrame(data_0190)
    df_0200 = pd.DataFrame(data_0200)
    df_c100_c170 = pd.DataFrame(data_c100c170)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        if not df_0190.empty:
            df_0190.to_excel(writer, index=False, sheet_name='0190')
        if not df_0200.empty:
            df_0200.to_excel(writer, index=False, sheet_name='0200')
        if not df_c100_c170.empty:
            df_c100_c170.to_excel(writer, index=False, sheet_name='C100_C170')

    buf.seek(0)
    return dcc.send_bytes(buf.getvalue(), 'sped_efd_icms_ipi.xlsx')

@app.callback(
    Output('file-info-nfse-split', 'children'),
    Input('upload-nfse-lote', 'filename'),
    prevent_initial_call=True
)
def show_nfse_filename(filename):
    if not filename:
        return no_update
    return f"Arquivo selecionado: {filename}"


@app.callback(
    Output('status-nfse-split', 'children'),
    Output('download-zip-nfse', 'data'),
    Input('btn-gerar-zip-nfse', 'n_clicks'),
    State('upload-nfse-lote', 'contents'),
    State('upload-nfse-lote', 'filename'),
    prevent_initial_call=True,
)
def gerar_zip_nfse(n, contents, filename):
    if not n or not contents:
        return no_update, no_update

    try:
        header, b64 = contents.split(',', 1)
        xml_bytes = base64.b64decode(b64)

        partes = split_nfse_abrasf(xml_bytes)
        if not partes:
            return dbc.Alert("Não encontrei CompNfse no XML. Esse arquivo pode não ser um lote ABRASF.", color="danger"), no_update

        zip_bytes = make_zip_bytes(partes)
        zip_name = "nfse_separadas.zip"

        status = dbc.Alert(f"✅ Separadas {len(partes)} NFSe. ZIP pronto.", color="success")
        return status, dcc.send_bytes(zip_bytes, zip_name)

    except Exception as e:
        return dbc.Alert(f"Erro ao processar NFSe: {e}", color="danger"), no_update



if __name__ == '__main__':
    # Bloco para facilitar a execução local
    import threading, webbrowser
    port = 8060
    url = f'http://127.0.0.1:{port}'
    
    # --- CORREÇÃO: Evita abrir duas abas no modo Debug ---
    # Só abre o navegador se não estivermos no processo 'reloader'
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    # --- FIM DA CORREÇÃO ---

    app.server.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024
    
    print(f"Servidor Dash rodando em {url}")
    print("Use 'Ctrl+C' para parar o servidor.")
    
    # Rodar com debug=True é essencial para desenvolvimento
    # O problema do processo "fantasma" no gerenciador de tarefas
    # é um efeito colateral do debug=True e NÃO acontecerá no .exe final.
    app.run(debug=True, host='127.0.0.1', port=port)
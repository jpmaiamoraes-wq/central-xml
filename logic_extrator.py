import os
import shutil
import tempfile
import zipfile
import py7zr
import io
import xml.etree.ElementTree as ET
from datetime import datetime
from utils import (
    log_message,
    digits,
    clean_dir,
    NFE_NS_GLOBAL,
    CTE_NS_GLOBAL,
)

def extract_7z(archive_path, destination_path):
    """Extrai .7z de forma compatível com Linux/Cloud"""
    try:
        with py7zr.SevenZipFile(archive_path, mode='r') as archive:
            archive.extractall(path=destination_path)
    except Exception as e:
        raise Exception(f"Erro ao extrair 7z: {e}")

def parse_xml_full_data(xml_file_path):
    """Analisa o XML extraindo CNPJs (incluindo Tomador CTe), Data e CFOPs"""
    try:
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
        ns = {'nfe': NFE_NS_GLOBAL, 'cte': CTE_NS_GLOBAL}
        
        # Identifica se é NFe ou CTe
        infNFe = root.find(".//nfe:infNFe", ns)
        infCTe = root.find(".//cte:infCTe", ns)
        
        emit_cnpj = ""
        dest_cnpj = ""
        data_str = ""
        # Coleta todos os CFOPs presentes no XML (independente de ser NFe ou CTe)
        cfops = [c.text for c in root.findall(".//{*}CFOP") if c.text]

        if infNFe is not None:
            emit_cnpj = digits(infNFe.findtext(".//nfe:emit/nfe:CNPJ", namespaces=ns) or "")
            dest_cnpj = digits(infNFe.findtext(".//nfe:dest/nfe:CNPJ", namespaces=ns) or "")
            data_str = infNFe.findtext(".//nfe:ide/nfe:dhEmi", namespaces=ns) or \
                       infNFe.findtext(".//nfe:ide/nfe:dEmi", namespaces=ns) or ""
            
        elif infCTe is not None:
            emit_cnpj = digits(infCTe.findtext(".//cte:emit/cte:CNPJ", namespaces=ns) or "")
            dest_cnpj = digits(infCTe.findtext(".//cte:dest/cte:CNPJ", namespaces=ns) or "")
            data_str = infCTe.findtext(".//cte:ide/cte:dhEmi", namespaces=ns) or ""
            
            # --- LÓGICA TOMADOR CTe (Tom3 / Tom4) ---
            # Se o nosso CNPJ não for o emitente, verificamos se somos o Tomador
            toma3 = infCTe.find(".//cte:toma3/cte:toma", namespaces=ns)
            toma4 = infCTe.find(".//cte:toma4", namespaces=ns)
            
            if toma3 is not None:
                # toma3: 0-Remetente, 1-Expedidor, 2-Recebedor, 3-Destinatário
                papel = toma3.text 
                tag_map = {'0': 'rem', '1': 'exped', '2': 'receb', '3': 'dest'}
                tag_toma = tag_map.get(papel)
                if tag_toma:
                    cnpj_toma = digits(infCTe.findtext(f".//cte:{tag_toma}/cte:CNPJ", namespaces=ns) or "")
                    if cnpj_toma: 
                        dest_cnpj = cnpj_toma # Atribuímos ao destino para a lógica de 'Terceiros'
            
            elif toma4 is not None:
                # toma4: Tomador indicado explicitamente (pode ser um terceiro)
                cnpj_toma4 = digits(toma4.findtext(".//cte:CNPJ", namespaces=ns) or "")
                if cnpj_toma4: 
                    dest_cnpj = cnpj_toma4

        # Conversão de Data para objeto date para comparação
        data_emissao = None
        if data_str:
            try:
                # Pega YYYY-MM-DD
                data_emissao = datetime.strptime(data_str[:10], '%Y-%m-%d').date()
            except: 
                pass

        return {
            'emit': emit_cnpj,
            'dest': dest_cnpj,
            'data': data_emissao,
            'cfops': cfops
        }
    except:
        return None

def move_xml_para_destino_extrator(caminho_origem, nome_arquivo, pasta_destino, log_list):
    """Copia o arquivo tratando duplicados de nome"""
    try:
        nome_base, extensao = os.path.splitext(nome_arquivo)
        caminho_destino_final = os.path.join(pasta_destino, nome_arquivo)
        contador = 1
        while os.path.exists(caminho_destino_final):
            caminho_destino_final = os.path.join(pasta_destino, f"{nome_base}_{contador}{extensao}")
            contador += 1
        shutil.copy2(caminho_origem, caminho_destino_final)
    except Exception as e:
        log_list = log_message(log_list, f"AVISO: Falha ao copiar {nome_arquivo}: {e}")
    return log_list

def extrair_e_classificar_extrator(caminho_pasta, pastas_destino, own_set, log_list, 
                                  extractors_map, supported_archives_list, 
                                  data_ini=None, data_fim=None, cfops_filtro=None):
    """
    Varre a pasta, extrai aninhados e classifica XMLs com filtros de Data e CFOP.
    """
    try:
        itens = os.listdir(caminho_pasta)
    except Exception as e:
        return log_message(log_list, f"ERRO: Falha ao ler pasta {caminho_pasta}: {e}"), 0
    
    arquivos_movidos = 0

    for item_nome in itens:
        item_nome_sanitizado = item_nome.rstrip(' \\/')
        item_caminho_completo = os.path.join(caminho_pasta, item_nome_sanitizado)
        
        if os.path.isdir(item_caminho_completo):
            log_list, novos = extrair_e_classificar_extrator(
                item_caminho_completo, pastas_destino, own_set, log_list, 
                extractors_map, supported_archives_list, data_ini, data_fim, cfops_filtro
            )
            arquivos_movidos += novos
            continue
        
        nome_base, extensao = os.path.splitext(item_nome_sanitizado.lower())

        # 1. ARQUIVOS COMPACTADOS
        if extensao in supported_archives_list:
            log_list = log_message(log_list, f"Extraindo arquivo: {item_nome_sanitizado}...")
            pasta_temp = tempfile.mkdtemp(prefix=f"ext_{nome_base}_")
            try:
                extract_func = extractors_map[extensao]
                extract_func(item_caminho_completo, pasta_temp)
                log_list, novos = extrair_e_classificar_extrator(
                    pasta_temp, pastas_destino, own_set, log_list,
                    extractors_map, supported_archives_list, data_ini, data_fim, cfops_filtro
                )
                arquivos_movidos += novos
            except Exception as e:
                log_list = log_message(log_list, f"AVISO: Falha ao extrair '{item_nome_sanitizado}': {e}")
                log_list = move_xml_para_destino_extrator(item_caminho_completo, item_nome_sanitizado, pastas_destino['diversos'], log_list)
            finally:
                shutil.rmtree(pasta_temp, ignore_errors=True)

        # 2. ARQUIVOS XML
        elif extensao == '.xml':
            info = parse_xml_full_data(item_caminho_completo)
            if not info:
                # Se o XML estiver corrompido ou sem as tags básicas, vai para Outros
                log_list = move_xml_para_destino_extrator(item_caminho_completo, item_nome_sanitizado, pastas_destino['outros'], log_list)
                continue

            # --- APLICAÇÃO DOS FILTROS ---
            if data_ini and info['data'] and info['data'] < data_ini:
                continue
            if data_fim and info['data'] and info['data'] > data_fim:
                continue
            if cfops_filtro and not any(c in cfops_filtro for c in info['cfops']):
                continue

            # --- CLASSIFICAÇÃO DE PASTAS ---
            if info['emit'] in own_set:
                pasta_alvo = pastas_destino['proprios']
            elif info['dest'] in own_set:
                pasta_alvo = pastas_destino['terceiros']
            else:
                pasta_alvo = pastas_destino['outros']

            log_list = move_xml_para_destino_extrator(item_caminho_completo, item_nome_sanitizado, pasta_alvo, log_list)
            arquivos_movidos += 1

        # 3. ARQUIVOS DIVERSOS (PDF, TXT, ETC)
        else:
            log_list = move_xml_para_destino_extrator(item_caminho_completo, item_nome_sanitizado, pastas_destino['diversos'], log_list)
            arquivos_movidos += 1

    return log_list, arquivos_movidos

def processar_extracao_cloud(uploaded_file, modo, cnpjs_proprios, data_ini=None, data_fim=None, cfops_filtro=None):
    """Função principal integrada ao Streamlit"""
    logs = []
    own_set = {digits(c) for c in (cnpjs_proprios or [])}
    output_zip_buffer = io.BytesIO()

    with tempfile.TemporaryDirectory() as tmp_dir:
        input_path = os.path.join(tmp_dir, "entrada.zip")
        with open(input_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        pasta_extracao = os.path.join(tmp_dir, "extraido")
        pastas_destino = {
            'proprios': os.path.join(tmp_dir, "Proprios"),
            'terceiros': os.path.join(tmp_dir, "Terceiros"),
            'outros': os.path.join(tmp_dir, "Outros"),
            'diversos': os.path.join(tmp_dir, "Arquivos_Diversos")
        }
        for p in pastas_destino.values(): os.makedirs(p)

        extractors_map = {
            ".zip": lambda path, dest: zipfile.ZipFile(path, 'r').extractall(dest),
            ".7z": lambda path, dest: extract_7z(path, dest),
        }
        supported = [".zip", ".7z"]

        # Extração inicial
        with zipfile.ZipFile(input_path, 'r') as z:
            z.extractall(pasta_extracao)

        if modo == 'Separar pelo Emitente (Classificação)':
            logs, total = extrair_e_classificar_extrator(
                pasta_extracao, pastas_destino, own_set, logs, extractors_map, supported,
                data_ini, data_fim, cfops_filtro
            )
        else:
            # Modo Juntar Tudo (simplificado, move tudo para outros/diversos)
            logs, total = extrair_e_classificar_extrator(
                pasta_extracao, pastas_destino, set(), logs, extractors_map, supported
            )

        # ZIP de retorno
        with zipfile.ZipFile(output_zip_buffer, "w") as zf:
            for cat, p in pastas_destino.items():
                for root_dir, _, files in os.walk(p):
                    for f in files:
                        zf.write(os.path.join(root_dir, f), arcname=os.path.join(cat, f))

    return output_zip_buffer.getvalue(), logs
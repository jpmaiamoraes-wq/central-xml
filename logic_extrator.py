import os
import shutil
import tempfile
import zipfile
import py7zr  # Biblioteca nativa Python para 7z
import io
import xml.etree.ElementTree as ET
from utils import (
    log_message,
    digits,
    clean_dir,
    NFE_NS_GLOBAL,
    CTE_NS_GLOBAL,
    ACCEPTED_MODELS_GLOBAL,
)

def extract_7z(archive_path, destination_path):
    """Extrai .7z de forma compatível com Linux/Cloud"""
    try:
        with py7zr.SevenZipFile(archive_path, mode='r') as archive:
            archive.extractall(path=destination_path)
    except Exception as e:
        raise Exception(f"Erro ao extrair 7z: {e}")

def parse_xml_file_extrator(xml_file_path):
    """Analisa o XML para identificar Emitente, Destinatário e Modelo"""
    try:
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
        
        # Namespaces
        ns = {'nfe': NFE_NS_GLOBAL, 'cte': CTE_NS_GLOBAL}
        
        # Tenta achar infNFe ou infCTe
        inf = root.find(".//nfe:infNFe", ns) or root.find(".//cte:infCTe", ns)
        
        if inf is None:
            return None, None, None

        emit_cnpj = digits(inf.findtext(".//nfe:emit/nfe:CNPJ", namespaces=ns) or 
                           inf.findtext(".//cte:emit/cte:CNPJ", namespaces=ns) or "")
        
        dest_cnpj = digits(inf.findtext(".//nfe:dest/nfe:CNPJ", namespaces=ns) or 
                           inf.findtext(".//cte:dest/cte:CNPJ", namespaces=ns) or "")
        
        modelo = inf.findtext(".//nfe:ide/nfe:mod", namespaces=ns) or \
                 inf.findtext(".//cte:ide/cte:mod", namespaces=ns)

        return emit_cnpj, dest_cnpj, modelo
    except:
        return None, None, None

def move_xml_para_destino_extrator(caminho_origem, nome_arquivo, pasta_destino, log_list):
    """Copia o XML tratando duplicados de nome"""
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

def processar_extracao_cloud(uploaded_file, modo, cnpjs_proprios):
    """
    Função principal chamada pelo app.py no Streamlit.
    """
    logs = []
    own_set = {digits(c) for c in (cnpjs_proprios or [])}
    output_zip_buffer = io.BytesIO()

    with tempfile.TemporaryDirectory() as tmp_dir:
        # 1. Salva o arquivo enviado
        input_path = os.path.join(tmp_dir, "entrada.zip")
        with open(input_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # 2. Pastas de trabalho
        pasta_extracao = os.path.join(tmp_dir, "extraido")
        pastas_destino = {
            'proprios': os.path.join(tmp_dir, "Proprios"),
            'terceiros': os.path.join(tmp_dir, "Terceiros"),
            'outros': os.path.join(tmp_dir, "Outros")
        }
        for p in pastas_destino.values(): os.makedirs(p)

        # 3. Configura extratores
        extractors_map = {
            ".zip": lambda path, dest: zipfile.ZipFile(path, 'r').extractall(dest),
            ".7z": lambda path, dest: extract_7z(path, dest),
        }
        supported = [".zip", ".7z"]

        # 4. Executa a lógica
        with zipfile.ZipFile(input_path, 'r') as z:
            z.extractall(pasta_extracao)

        if modo == 'Separar pelo Emitente (Classificação)':
            logs, total = extrair_e_classificar_extrator(
                pasta_extracao, pastas_destino, own_set, logs, extractors_map, supported
            )
        else:
            # Modo Juntar Tudo
            logs, total = extrair_xmls_recursivamente(
                pasta_extracao, pastas_destino['outros'], logs, extractors_map, supported
            )

        # 5. Cria o ZIP de retorno
        with zipfile.ZipFile(output_zip_buffer, "w") as zf:
            for cat, p in pastas_destino.items():
                for root, _, files in os.walk(p):
                    for f in files:
                        zf.write(os.path.join(root, f), arcname=os.path.join(cat, f))

    return output_zip_buffer.getvalue(), logs

def extrair_e_classificar_extrator(caminho_pasta, pastas_destino, own_set, log_list, extractors_map, supported_archives_list):
    """
    Varre 'caminho_pasta', extrai arquivos aninhados E classifica/move XMLs.
    Arquivos que não são XML ou compactados suportados vão para 'Outros'.
    """
    try:
        itens = os.listdir(caminho_pasta)
    except Exception as e:
        log_list = log_message(log_list, f"ERRO: Falha ao ler pasta {caminho_pasta}: {e}")
        return log_list, 0
    
    arquivos_movidos = 0

    for item_nome in itens:
        item_nome_sanitizado = item_nome.rstrip(' \\/')
        item_caminho_completo = os.path.join(caminho_pasta, item_nome_sanitizado)
        
        if os.path.isdir(item_caminho_completo):
            # Se for uma pasta, entra nela recursivamente
            log_list, novos_movidos = extrair_e_classificar_extrator(
                item_caminho_completo, pastas_destino, own_set, log_list, 
                extractors_map, supported_archives_list
            )
            arquivos_movidos += novos_movidos
        
        elif os.path.isfile(item_caminho_completo):
            nome_base, extensao = os.path.splitext(item_nome_sanitizado)
            extensao = extensao.strip().lower()

            # 1. Se for um ARQUIVO COMPACTADO SUPORTADO (.zip, .7z)
            if extensao in supported_archives_list:
                log_list = log_message(log_list, f"Extraindo arquivo: {item_nome_sanitizado}...")
                pasta_temp_aninhada = tempfile.mkdtemp(prefix=f"ext_{nome_base}_")
                
                try:
                    extract_func = extractors_map[extensao]
                    extract_func(item_caminho_completo, pasta_temp_aninhada)
                    
                    log_list, novos_movidos = extrair_e_classificar_extrator(
                        pasta_temp_aninhada, pastas_destino, own_set, log_list,
                        extractors_map, supported_archives_list
                    )
                    arquivos_movidos += novos_movidos
                    
                except Exception as e:
                    log_list = log_message(log_list, f"AVISO: Falha ao extrair '{item_nome_sanitizado}': {e}. Movendo original para 'Outros'.")
                    # Se falhar a extração, move o arquivo fechado para outros
                    log_list = move_xml_para_destino_extrator(item_caminho_completo, item_nome_sanitizado, pastas_destino['outros'], log_list)
                finally:
                    try:
                        shutil.rmtree(pasta_temp_aninhada)
                    except Exception:
                        pass
            
            # 2. Se for um ARQUIVO XML (Faz a classificação por CNPJ)
            elif extensao == '.xml':
                emit_cnpj, dest_cnpj, modelo = parse_xml_file_extrator(item_caminho_completo)
                
                if emit_cnpj and emit_cnpj in own_set:
                    pasta_alvo = pastas_destino['proprios']
                elif dest_cnpj and dest_cnpj in own_set:
                    pasta_alvo = pastas_destino['terceiros']
                else:
                    pasta_alvo = pastas_destino['outros']

                log_list = move_xml_para_destino_extrator(item_caminho_completo, item_nome_sanitizado, pasta_alvo, log_list)
                arquivos_movidos += 1

            # 3. QUALQUER OUTRO ARQUIVO (PDF, RAR, TXT, etc.)
            else:
                log_list = log_message(log_list, f"Arquivo não-XML detectado ({extensao}). Movendo para 'Outros'.")
                log_list = move_xml_para_destino_extrator(item_caminho_completo, item_nome_sanitizado, pastas_destino['outros'], log_list)
                arquivos_movidos += 1

    return log_list, arquivos_movidos


def extrair_xmls_recursivamente(
    caminho_pasta,
    pasta_destino_final,
    log_list,
    extractors_map,
    supported_archives_list
):
    """
    Varre 'caminho_pasta', extrai arquivos aninhados (.zip, .rar, .7z)
    e move todos os XMLs encontrados para 'pasta_destino_final'.
    """
    xmls_movidos = 0

    try:
        # os.walk já entra em todas as subpastas automaticamente
        for raiz, dirs, files in os.walk(caminho_pasta):
            for nome_arquivo in files:
                caminho_completo = os.path.join(raiz, nome_arquivo)

                # sanitiza e descobre a extensão
                nome_sanitizado = nome_arquivo.rstrip(' \\/')
                nome_base, extensao = os.path.splitext(nome_sanitizado)
                extensao = extensao.strip().lower()

                # LOG: tudo o que ele está enxergando
                log_list = log_message(
                    log_list,
                    f"Encontrado arquivo: {nome_sanitizado} (extensão: {extensao}) em {raiz}"
                )

                # 1) Se for arquivo compactado (.zip, .rar, .7z)
                if extensao in supported_archives_list:
                    log_list = log_message(
                        log_list,
                        f"Extraindo arquivo: {nome_sanitizado}..."
                    )
                    pasta_temp = tempfile.mkdtemp(prefix=f"ext_{nome_base}_")

                    try:
                        extract_func = extractors_map[extensao]
                        extract_func(caminho_completo, pasta_temp)

                        # recursivo dentro do que foi extraído
                        log_list, novos_xmls = extrair_xmls_recursivamente(
                            pasta_temp,
                            pasta_destino_final,
                            log_list,
                            extractors_map,
                            supported_archives_list
                        )
                        xmls_movidos += novos_xmls

                    except Exception as e:
                        log_list = log_message(
                            log_list,
                            f"AVISO: Falha ao extrair '{nome_sanitizado}': {e}. Ignorando."
                        )
                    finally:
                        try:
                            shutil.rmtree(pasta_temp)
                        except Exception:
                            pass

                # 2) Se for XML
                elif extensao == ".xml":
                    log_list = move_xml_para_destino_extrator(
                        caminho_completo,
                        nome_sanitizado,
                        pasta_destino_final,
                        log_list
                    )
                    xmls_movidos += 1

        return log_list, xmls_movidos

    except Exception as e:
        log_list = log_message(
            log_list,
            f"ERRO: Falha ao varrer a pasta '{caminho_pasta}': {e}"
        )
        return log_list, xmls_movidos

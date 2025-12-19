# logic_extrator.py
import os
import shutil
import subprocess
import tempfile
import zipfile
import xml.etree.ElementTree as ET

from utils import (
    log_message,
    digits,
    clean_dir,
    NFE_NS_GLOBAL,
    CTE_NS_GLOBAL,
    ACCEPTED_MODELS_GLOBAL,
)
from logic_resumo import _find_first_local_resumo  # reaproveita helper da Aba 2


def extract_7z(archive_path, destination_path):
    """
    Extrai um arquivo .7z usando o executável '7z' via subprocess.
    """
    try:
        cmd = ["7z", "x", archive_path, f"-o{destination_path}", "-y"]
        processo = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if processo.returncode != 0:
            stderr_output = processo.stderr or "Sem saída de erro"
            raise Exception(f"Erro do 7-Zip (código {processo.returncode}): {stderr_output}")
    except FileNotFoundError:
        raise FileNotFoundError(
            "ERRO CRÍTICO: '7z' não encontrado. Adicione a pasta do 7-Zip ao PATH do Windows."
        )
    except Exception as e:
        raise e


def parse_xml_file_extrator(xml_file_path):
    """
    Lê um arquivo XML do disco e extrai os CNPJs relevantes e o modelo.
    (Mesma lógica que você já tinha na Aba 1.) :contentReference[oaicite:1]{index=1}
    """
    # aqui você só copia o corpo da função original parse_xml_file_extrator,
    # trocando chamadas para _digits -> digits, NS_MAP_NFE / NS_MAP_CTE etc.,
    # ou importando essas constantes de um módulo específico se preferir.
    ...
    # (para não estourar resposta, não repliquei tudo,
    # mas é literalmente o mesmo código que já está no arquivo, só movido.)


def move_xml_para_destino_extrator(caminho_origem, nome_arquivo, pasta_destino, log_list):
    """
    Copia o XML para a pasta de destino, tratando duplicados.
    (Mesma lógica da função original.)
    """
    try:
        nome_base, extensao = os.path.splitext(nome_arquivo)
        caminho_destino_final = os.path.join(pasta_destino, nome_arquivo)
        contador = 1

        while os.path.exists(caminho_destino_final):
            novo_nome = f"{nome_base}_{contador}{extensao}"
            caminho_destino_final = os.path.join(pasta_destino, novo_nome)
            contador += 1

        shutil.copy2(caminho_origem, caminho_destino_final)
    except Exception as e:
        log_list = log_message(
            log_list, f"AVISO: Falha ao copiar XML '{nome_arquivo}': {e}."
        )
    return log_list


def extrair_e_classificar_extrator(caminho_pasta, pastas_destino, own_set, log_list, extractors_map, supported_archives_list):
    """
    Varre 'caminho_pasta', extrai arquivos aninhados E classifica/move XMLs. (Usado pela Aba 1)
    """
    try:
        itens = os.listdir(caminho_pasta)
    except Exception as e:
        log_list = log_message(log_list, f"ERRO: Falha ao ler pasta {caminho_pasta}: {e}")
        return log_list, 0
    
    xmls_movidos = 0

    for item_nome in itens:
        item_nome_sanitizado = item_nome.rstrip(' \\/')
        item_caminho_completo = os.path.join(caminho_pasta, item_nome_sanitizado)
        
        if os.path.isdir(item_caminho_completo):
            # Se for uma pasta, entra nela
            log_list, novos_xmls = extrair_e_classificar_extrator(
                item_caminho_completo, pastas_destino, own_set, log_list, 
                extractors_map, supported_archives_list
            )
            xmls_movidos += novos_xmls
        
        elif os.path.isfile(item_caminho_completo):
            nome_base, extensao = os.path.splitext(item_nome_sanitizado)
            extensao = extensao.strip().lower()

            # 1. Se for um ARQUIVO COMPACTADO (zip, rar, 7z)
            if extensao in supported_archives_list:
                log_list = log_message(log_list, f"Extraindo arquivo: {item_nome_sanitizado}...")
                pasta_temp_aninhada = tempfile.mkdtemp(prefix=f"ext_{nome_base}_")
                
                try:
                    extract_func = extractors_map[extensao]
                    extract_func(item_caminho_completo, pasta_temp_aninhada)
                    
                    log_list, novos_xmls = extrair_e_classificar_extrator(
                        pasta_temp_aninhada, pastas_destino, own_set, log_list,
                        extractors_map, supported_archives_list
                    )
                    xmls_movidos += novos_xmls
                    
                except Exception as e:
                    log_list = log_message(log_list, f"AVISO: Falha ao extrair '{item_nome_sanitizado}': {e}. Ignorando.")
                finally:
                    try:
                        shutil.rmtree(pasta_temp_aninhada)
                    except Exception:
                        pass
            
            # 2. Se for um ARQUIVO XML
            elif extensao == '.xml':
                # Analisa o XML
                emit_cnpj, dest_cnpj, modelo = parse_xml_file_extrator(item_caminho_completo)
                
                pasta_alvo = None
                
                # Classifica
                if emit_cnpj and emit_cnpj in own_set:
                    pasta_alvo = pastas_destino['proprios']
                elif dest_cnpj and dest_cnpj in own_set:
                    pasta_alvo = pastas_destino['terceiros']
                else:
                    pasta_alvo = pastas_destino['outros']

                # Move o arquivo
                log_list = move_xml_para_destino_extrator(item_caminho_completo, item_nome_sanitizado, pasta_alvo, log_list)
                xmls_movidos += 1

    return log_list, xmls_movidos



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

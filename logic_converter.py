import pandas as pd
import xml.etree.ElementTree as ET
import os
import re

def carregar_dicionario_servicos(caminho_planilha):
    """
    Carrega a planilha de 'De-Para' de serviços. 
    Funciona tanto com arquivos locais quanto com caminhos temporários da nuvem.
    """
    try:
        # Verifica se o arquivo existe antes de tentar ler
        if not os.path.exists(caminho_planilha):
            print(f"Aviso: Arquivo de referência não encontrado em {caminho_planilha}")
            return {}

        if caminho_planilha.lower().endswith(('.xlsx', '.xls')):
            df_ref = pd.read_excel(caminho_planilha, dtype=str)
        else:
            df_ref = pd.read_csv(caminho_planilha, dtype=str, sep=';', encoding='ISO-8859-1')
        
        df_ref.columns = [c.strip() for c in df_ref.columns]
        return {
            str(row['COD. SERV. PREF. SÃO PAULO']).strip(): (
                row['LISTA DOS SERVIÇOS SUJEITOS AO ISSQN'], 
                row['COD. CORRESPONDENTE']
            )
            for _, row in df_ref.iterrows()
        }
    except Exception as e:
        print(f"Erro ao carregar dicionário: {e}")
        return {}
    
def fmt_v(valor):
    if not valor or str(valor).strip() == "" or str(valor).lower() == "nan":
        return "0.00"
    if "." in str(valor) and "," in str(valor):
        valor = str(valor).replace(".", "")
    res = str(valor).replace(",", ".")
    try:
        return "{:.2f}".format(float(res))
    except:
        return "0.00"

def para_float(valor):
    if not valor or str(valor).strip() == "" or str(valor).lower() == "nan":
        return 0.0
    texto = str(valor)
    if "." in texto and "," in texto:
        texto = texto.replace(".", "")
    texto = texto.replace(",", ".")
    try:
        return float(texto)
    except:
        return 0.0

def limpar_doc(doc):
    return re.sub(r"[^0-9]", "", str(doc))

def adicionar_campo(parent, tag, valor):
    texto = str(valor).strip()
    if texto.lower() == "nan":
        texto = ""
    elem = ET.SubElement(parent, tag)
    elem.text = texto
    return elem

def converter_txt_para_xml_lote(input_path, output_dir, path_ref_custom=None):
    """
    input_path: Arquivo TXT/CSV/ZIP enviado pelo usuário.
    output_dir: Pasta temporária no servidor para gerar os XMLs.
    path_ref_custom: Caminho da planilha Excel de referência enviada via Aba 5.
    """
    try:
        # PRIORIDADE: Usa o arquivo que o usuário subiu na Aba 5. 
        # FALLBACK: Tenta o caminho local (apenas para testes no seu PC).
        path_referencia = path_ref_custom or r"C:\Users\joao.moraes_sankhya\Documents\Resumo XML\Cod.-de-servico-SP-x-Campinas.xlsx"
        
        dic_servicos = carregar_dicionario_servicos(path_referencia)
        
        extensao = os.path.splitext(input_path)[1].lower()
        
        # Leitura do arquivo (TXT ou CSV)
        if extensao == ".txt":
            df = pd.read_csv(input_path, sep="\t", dtype=str, encoding="ISO-8859-1").fillna("")
        elif extensao == ".csv":
            df = pd.read_csv(input_path, sep=";", dtype=str, encoding="ISO-8859-1").fillna("")
            if len(df.columns) <= 1:
                df = pd.read_csv(input_path, sep=",", dtype=str, encoding="ISO-8859-1").fillna("")
        else:
            return f"Erro: Formato {extensao} não suportado."

        os.makedirs(output_dir, exist_ok=True)
        
        mapa_id_estrangeiros = {}
        proximo_id = 1
        count = 0
        
        for index, row in df.iterrows():
            # Limpeza de nomes de colunas para evitar erros de espaços extras no CSV/TXT
            row = {str(k).strip(): v for k, v in row.items()}

            if row.get("Tipo de Registro") == "Total" or not row.get("Nº NFS-e"):
                continue
                
            # --- FILTRO TEMPORÁRIO: APENAS CPF (11 dígitos) ---
            #prestador_doc = limpar_doc(row.get("CPF/CNPJ do Prestador", ""))
            #if len(prestador_doc) > 11:
                #continue 
            # --------------------------------------------------
            
            data_cancelamento = str(row.get("Data de Cancelamento", "")).strip()
            if data_cancelamento and data_cancelamento.lower() != "nan":
                continue 
            
            nf_num = row.get("Nº NFS-e", "")
            prestador_doc = limpar_doc(row.get("CPF/CNPJ do Prestador", ""))
            nome_tomador = str(row.get("Razão Social do Tomador", "")).strip()

            atributos = {"versao": "1.01", "xmlns": "https://www.sped.fazenda.gov.br/nfse"}
            root = ET.Element("NFSe", atributos)
            infNFSe = ET.SubElement(root, "infNFSe", {"Id": f"NFS{prestador_doc}{nf_num}"})
            
            adicionar_campo(infNFSe, "Numero", nf_num)
            adicionar_campo(infNFSe, "NumeroRPS", row.get("Número do RPS", ""))
            adicionar_campo(infNFSe, "SerieRPS", row.get("Série do RPS", ""))
            adicionar_campo(infNFSe, "CodigoVerificacao", row.get("Código de Verificação da NFS-e", ""))
            adicionar_campo(infNFSe, "dataEmissao", row.get("Data do Fato Gerador", ""))

            v_serv_raw = str(row.get("Valor dos Serviços", "")).strip()
            if not v_serv_raw or v_serv_raw.lower() == "nan" or para_float(v_serv_raw) == 0:
                v_serv_raw = row.get("Valor Total Recebido", "0.00")

            v_servicos = para_float(v_serv_raw)
            v_pis, v_cofins = para_float(row.get("PIS/PASEP")), para_float(row.get("COFINS"))
            v_inss, v_ir, v_csll = para_float(row.get("INSS")), para_float(row.get("IR")), para_float(row.get("CSLL"))
            v_iss_devido = para_float(row.get("ISS devido"))
            
            iss_retido_flag = str(row.get("ISS Retido", "")).upper()
            deduzir_iss = v_iss_devido if iss_retido_flag in ["S", "1", "SIM"] else 0.0
            v_liquido = v_servicos - deduzir_iss - v_pis - v_cofins - v_inss - v_ir - v_csll
            
            valores = ET.SubElement(infNFSe, "v_servicos")
            adicionar_campo(valores, "BaseCalculo", "{:.2f}".format(v_servicos))
            adicionar_campo(valores, "Aliquota", fmt_v(row.get("Alíquota", "")))
            adicionar_campo(valores, "ValorIss", fmt_v(row.get("ISS devido", "")))
            adicionar_campo(valores, "ValorLiquidoNfse", "{:.2f}".format(v_liquido))
            
            emit = ET.SubElement(infNFSe, "PrestadorServico")
            tag_doc = "CNPJ" if len(prestador_doc) > 11 else "CPF"
            adicionar_campo(emit, tag_doc, prestador_doc)
            adicionar_campo(emit, "IM", row.get("Inscrição Municipal do Prestador", ""))
            adicionar_campo(emit, "Nome", row.get("Razão Social do Prestador", ""))
            adicionar_campo(emit, "email", row.get("Email do Prestador", ""))
            
            enderEmit = ET.SubElement(emit, "Endereco")
            adicionar_campo(enderEmit, "Endereco", row.get("Endereço do Prestador", ""))
            adicionar_campo(enderEmit, "Numero", row.get("Número do Endereço do Prestador", ""))
            adicionar_campo(enderEmit, "Complemento", row.get("Complemento do Endereço do Prestador", ""))
            adicionar_campo(enderEmit, "Bairro", row.get("Bairro do Prestador", ""))
            adicionar_campo(enderEmit, "CidadePrestador", row.get("Cidade do Prestador", ""))
            adicionar_campo(enderEmit, "UF", row.get("UF do Prestador", ""))
            ET.SubElement(enderEmit, "CodigoMunicipio").text = "3550308"
            adicionar_campo(enderEmit, "CEP", limpar_doc(row.get("CEP do Prestador", "")))
            
            toma = ET.SubElement(infNFSe, "Tomador")
            indicador_tomador = str(row.get("Indicador de CPF/CNPJ do Tomador", "")).strip()

            if indicador_tomador == "3":
                chave_nome = nome_tomador if nome_tomador else "SEM_NOME"
                if chave_nome not in mapa_id_estrangeiros:
                    mapa_id_estrangeiros[chave_nome] = f"EXT{proximo_id:05d}"
                    proximo_id += 1
                
                id_final = mapa_id_estrangeiros[chave_nome]
                ET.SubElement(toma, "idEstrangeiro").text = id_final[:20] 
                adicionar_campo(toma, "Nome", nome_tomador)
                
                endToma = ET.SubElement(toma, "Endereco")
                ET.SubElement(endToma, "logradouro").text = "Não informado" 
                ET.SubElement(endToma, "Numero").text = "S/N"
                ET.SubElement(endToma, "Bairro").text = "Não informado"
                ET.SubElement(endToma, "CodigoMunicipio").text = "9999999"
                ET.SubElement(endToma, "Uf").text = "EX"
                ET.SubElement(endToma, "CodigoPais").text = "69"
                ET.SubElement(endToma, "CEP").text = "00000000"
            else:
                doc_toma = limpar_doc(row.get("CPF/CNPJ do Tomador", ""))
                tag_doc_toma = "CNPJ" if len(doc_toma) > 11 else "CPF"
                adicionar_campo(toma, tag_doc_toma, doc_toma)
                adicionar_campo(toma, "IM", row.get("Inscrição Municipal do Tomador", ""))
                adicionar_campo(toma, "Nome", nome_tomador)
                adicionar_campo(toma, "email", row.get("Email do Tomador", ""))
                
                endToma = ET.SubElement(toma, "Endereco")
                adicionar_campo(endToma, "Endereco", row.get("Endereço do Tomador", ""))
                adicionar_campo(endToma, "Numero", row.get("Número do Endereço do Tomador", ""))
                adicionar_campo(endToma, "Complemento", row.get("Complemento do Endereço do Tomador", ""))
                adicionar_campo(endToma, "Bairro", row.get("Bairro do Tomador", ""))
                adicionar_campo(endToma, "CidadeTomador", row.get("Cidade do Tomador", ""))
                adicionar_campo(endToma, "UF", row.get("UF do Tomador", ""))
                adicionar_campo(endToma, "CEP", limpar_doc(row.get("CEP do Tomador", "")))
            
            serv = ET.SubElement(infNFSe, "Servico")
            vlrDPS = ET.SubElement(serv, "Valores")
            adicionar_campo(vlrDPS, "ValorServicos", fmt_v(v_servicos))
            adicionar_campo(vlrDPS, "ValorDeducoes", fmt_v(row.get("Valor das Deduções", "")))
            adicionar_campo(vlrDPS, "ValorPis", fmt_v(v_pis))
            adicionar_campo(vlrDPS, "ValorCofins", fmt_v(v_cofins))
            adicionar_campo(vlrDPS, "ValorIr", fmt_v(v_ir))
            adicionar_campo(vlrDPS, "ValorCsll", fmt_v(v_csll))
            adicionar_campo(vlrDPS, "ValorInss", fmt_v(v_inss))
            
            iss_ret_elem = ET.SubElement(serv, "IssRetido")
            iss_ret_elem.text = "1" if iss_retido_flag in ["S", "1", "SIM"] else "2"
            
            cod_serv_txt = str(row.get("Código do Serviço Prestado na Nota Fiscal", "")).strip()
            info_planilha = dic_servicos.get(cod_serv_txt)
            
            if info_planilha:
                desc_final, lc116_final = info_planilha[0], info_planilha[1]
            else:
                desc_final, lc116_final = row.get("Discriminação dos Serviços", ""), ""

            adicionar_campo(serv, "codigoTribMunicipio", cod_serv_txt)
            adicionar_campo(serv, "Discriminacao", desc_final)
            ET.SubElement(serv, "ItemListaServico").text = str(lc116_final).strip()
            adicionar_campo(serv, "InformacoesComplementares", row.get("Discriminação dos Serviços", ""))

            if row.get("Valor IBS") or row.get("Valor CBS"):
                reforma_tag = ET.SubElement(infNFSe, "reformaTributaria")
                adicionar_campo(reforma_tag, "ValorIBS", fmt_v(row.get("Valor IBS", "")))
                adicionar_campo(reforma_tag, "ValorCBS", fmt_v(row.get("Valor CBS", "")))
                adicionar_campo(reforma_tag, "AliqEstatualIBS", fmt_v(row.get("Aliquota Estadual IBS", "")))
                adicionar_campo(reforma_tag, "AliqMunicipalIBS", fmt_v(row.get("Aliquota Municipal IBS", "")))

            xml_tree = ET.ElementTree(root)
            ET.indent(xml_tree, space="  ", level=0)
            
            nome_arquivo = f"NFSe_{nf_num}_{prestador_doc}.xml"
            caminho_final = os.path.join(output_dir, nome_arquivo)
            
            if os.path.exists(caminho_final):
                nome_arquivo = f"NFSe_{nf_num}_{prestador_doc}_duplicada.xml"
                caminho_final = os.path.join(output_dir, nome_arquivo)

            xml_tree.write(caminho_final, encoding="utf-8", xml_declaration=True)
            count += 1
            
        return f"Sucesso! {count} arquivos gerados."
    except Exception as e:
        return f"Erro na conversão: {str(e)}"

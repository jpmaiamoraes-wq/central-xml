# logic_resumo.py
import zipfile
from io import BytesIO
import xml.etree.ElementTree as ET
import re
from datetime import datetime
from parsers.router import detect_and_parse_nfse


import pandas as pd

from utils import (
    digits,
    mask_cnpj,
    fmt_period,
    ACCEPTED_MODELS_GLOBAL,
)

# Wrappers para manter compatibilidade com código antigo que usa _digits / _mask_cnpj
def _digits(s: str) -> str:
    return digits(s)

def _mask_cnpj(d: str) -> str:
    return mask_cnpj(d)

NS_RESUMO = {
    "ns": "http://www.portalfiscal.inf.br/nfe",
    "nfe": "http://www.portalfiscal.inf.br/nfe",
    "cte": "http://www.portalfiscal.inf.br/cte",
}


def iter_xml_from_zip_resumo(zf: zipfile.ZipFile, *, max_depth: int = 3):
    """Gera tuplas (nome_arquivo, bytes_xml) para XMLs em zips (Aba 2)"""
    if max_depth < 0:
        return
    for name in zf.namelist():
        lname = name.lower()
        if lname.endswith(".xml"):
            try:
                yield name, zf.read(name)
            except Exception:
                continue
        elif lname.endswith(".zip"):
            try:
                inner_bytes = zf.read(name)
                with zipfile.ZipFile(BytesIO(inner_bytes), "r") as inner_zf:
                    yield from iter_xml_from_zip_resumo(
                        inner_zf, max_depth=max_depth - 1
                    )
            except Exception:
                continue


def _localname_resumo(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _find_first_local_resumo(root, names):
    if root is None:
        return None
    cur = [root]
    for name in names:
        nxt = []
        lname = name.lower()
        for el in cur:
            for ch in el:
                if _localname_resumo(ch.tag).lower() == lname:
                    nxt.append(ch)
        if not nxt:
            return None
        cur = nxt
    return cur[0]


def _findtext_any_resumo(root, xpath_prefixed, fallback_names):
    if root is None:
        return ""
    el = root.find(xpath_prefixed, NS_RESUMO)
    if el is not None and el.text is not None:
        return el.text
    el2 = _find_first_local_resumo(root, fallback_names)
    return el2.text if el2 is not None and el2.text is not None else ""


# --- ATUALIZADO (PATCH 2): Função _parse_fields_resumo (lógica de CTe e Eventos) ---
def _parse_fields_resumo(xml_bytes: bytes):
    """Extrai campos essenciais (Aba 2) para resumo/detalhe/itens."""
    try:
        root = ET.fromstring(xml_bytes)
    except Exception:
        return None, None, None, None, (None, None), ""

    # --- NFSe: tenta detectar antes de procurar infNFe/infCTe ---
    nfse_obj = None
    try:
        xml_text = xml_bytes.decode("utf-8", errors="ignore")
        nfse_obj = detect_and_parse_nfse(xml_text)
    except Exception:
        nfse_obj = None

    if nfse_obj:
        numero = (nfse_obj.numero or "").strip()
        verif = (nfse_obj.codigo_verificacao or "").strip()
        prest = digits(nfse_obj.prestador_cnpjcpf or "")
        chave_nfse = f"NFSE|{prest}|{numero}|{verif}"

        dt_ref = nfse_obj.competencia or nfse_obj.data_emissao
        ano = dt_ref.year if dt_ref else None
        mes = dt_ref.month if dt_ref else None
        data_str = dt_ref.isoformat() if dt_ref else ""

        emit_cnpj = prest
        dest_cnpj = digits(nfse_obj.tomador_cnpjcpf or "")

        return (
            emit_cnpj or None,
            dest_cnpj or None,
            "NFSE",
            chave_nfse or None,
            (ano, mes),
            data_str,
        )
    # --- fim NFSe ---


    # 1) Localiza infNFe ou infCTe
    inf = (
        root.find(".//ns:infNFe", NS_RESUMO)
        or root.find(".//nfe:infNFe", NS_RESUMO)
        or root.find(".//cte:infCTe", NS_RESUMO)
        or _find_first_local_resumo(root, ["NFe", "infNFe"])
        or _find_first_local_resumo(root, ["infNFe"])
        or _find_first_local_resumo(root, ["CTe", "infCTe"])
        or _find_first_local_resumo(root, ["infCTe"])
    )

    # Se não achou infNFe/infCTe, pode ser evento/inutilização
    if inf is None:
        local_root_tag = _localname_resumo(root.tag).lower()
        if "evento" in local_root_tag:
            return None, None, "EVENTO", None, (None, None), ""
        if "inut" in local_root_tag:
            return None, None, "INUT", None, (None, None), ""
        return None, None, None, None, (None, None), ""

    # 2) IDE + modelo
    ide = (
        inf.find(".//ns:ide", NS_RESUMO)
        or inf.find(".//nfe:ide", NS_RESUMO)
        or inf.find(".//cte:ide", NS_RESUMO)
        or _find_first_local_resumo(inf, ["ide"])
    )

    modelo = ""
    if ide is not None:
        mod_el = (
            ide.find("ns:mod", NS_RESUMO)
            or ide.find("nfe:mod", NS_RESUMO)
            or ide.find("cte:mod", NS_RESUMO)
            or _find_first_local_resumo(ide, ["mod"])
        )
        if mod_el is not None and mod_el.text:
            modelo = mod_el.text.strip()

    if modelo and modelo not in ACCEPTED_MODELS_GLOBAL:
        modelo = "OUT"

    # 3) Emitente (CNPJ ou CPF)
    emit_cnpj = ""
    emit_node = (
        inf.find("ns:emit", NS_RESUMO)
        or inf.find("nfe:emit", NS_RESUMO)
        or inf.find("cte:emit", NS_RESUMO)
        or _find_first_local_resumo(inf, ["emit"])
    )
    if emit_node is not None:
        txt = (
            _findtext_any_resumo(emit_node, "ns:CNPJ", ["CNPJ"])
            or _findtext_any_resumo(emit_node, "ns:CPF", ["CPF"])
        )
        emit_cnpj = _digits(txt)

    # 4) Destinatário (CNPJ ou CPF)
    dest_cnpj = ""
    dest_node = (
        inf.find("ns:dest", NS_RESUMO)
        or inf.find("nfe:dest", NS_RESUMO)
        or inf.find("cte:dest", NS_RESUMO)
        or _find_first_local_resumo(inf, ["dest"])
    )
    if dest_node is not None:
        txt = (
            _findtext_any_resumo(dest_node, "ns:CNPJ", ["CNPJ"])
            or _findtext_any_resumo(dest_node, "ns:CPF", ["CPF"])
        )
        dest_cnpj = _digits(txt)

    # 5) Chave (usa protocolo, Id ou regex de 44 dígitos)
    chave = ""
    ch = (
        root.find(".//ns:protNFe/ns:infProt/ns:chNFe", NS_RESUMO)
        or root.find(
            ".//nfe:protNFe/nfe:infProt/nfe:chNFe", NS_RESUMO
        )
        or root.find(".//cte:protCTe/cte:infProt/cte:chCTe", NS_RESUMO)
    )
    if ch is not None and ch.text:
        chave = ch.text.strip()

    if not chave:
        _id = inf.get("Id") or ""
        if _id:
            chave = (
                _id.replace("NFe", "")
                .replace("nfe", "")
                .replace("CTe", "")
                .replace("cte", "")
                .strip()
            )

    if not chave:
        m = re.search(r"\d{44}", ET.tostring(root, encoding="unicode"))
        if m:
            chave = m.group(0)

    # 6) Data / período (ano, mês)
    ano = mes = None
    data_str = ""
    if ide is not None:
        dhEmi = (
            _findtext_any_resumo(ide, "ns:dhEmi", ["dhEmi"])
            or _findtext_any_resumo(ide, "ns:dEmi", ["dEmi"])
        )
        if dhEmi:
            try:
                dt = datetime.fromisoformat(dhEmi.replace("Z", "+00:00"))
                ano, mes = dt.year, dt.month
                data_str = dt.date().isoformat()
            except Exception:
                m = re.search(r"(\d{4})[-/]?(\d{2})[-/]?(\d{2})?", dhEmi)
                if m:
                    ano = int(m.group(1))
                    mes = int(m.group(2))
                    dia = m.group(3)
                    data_str = (
                        f"{ano:04d}-{mes:02d}-{int(dia):02d}"
                        if dia
                        else f"{ano:04d}-{mes:02d}-01"
                    )

    return (
        emit_cnpj or None,
        dest_cnpj or None,
        (modelo or None),
        (chave or None),
        (ano, mes),
        data_str,
    )


# --- ATUALIZADO (PATCH 3): Função summarize_zipfile_resumo (novos contadores) ---
def summarize_zipfile_resumo(zf: zipfile.ZipFile, own_set: set):
    """Gera resumo da tabela (Aba 2) - Atualizado com contadores de Eventos"""
    counters = {
        c: {
            "QTD": 0,
            "QTDETERC": 0,
            "P": {"55": 0, "57": 0, "65": 0,"NFSE":0, "OUT": 0},
            "T": {"55": 0, "57": 0, "65": 0,"NFSE":0, "OUT": 0},
        }
        for c in own_set
    }
    seen_chaves = set()
    warns = set()
    total_docs = 0
    total_xmls = 0
    total_dfe = 0
    seen_dfe = set()
    min_period = None
    max_period = None
    total_eventos_inut = 0  # <- NOVO CONTADOR
    total_duplicados = 0
    total_intercompany = 0

    for name, xml_bytes in iter_xml_from_zip_resumo(zf, max_depth=3):
        total_xmls += 1
        emit_cnpj, dest_cnpj, modelo, chave, (ano, mes), _ = _parse_fields_resumo(
            xml_bytes
        )

        if modelo in ("EVENTO", "INUT"):
            total_eventos_inut += 1
            continue

        if modelo is None:
            continue
        if not chave:
            continue
        if chave in seen_chaves:
            total_duplicados += 1
            continue
        seen_chaves.add(chave)
        total_docs += 1

        if modelo in ACCEPTED_MODELS_GLOBAL and chave not in seen_dfe:
            seen_dfe.add(chave)
            total_dfe += 1
            if ano and mes:
                cur = (ano, mes)
                if (min_period is None) or (cur < min_period):
                    min_period = cur
                if (max_period is None) or (cur > max_period):
                    max_period = cur
        
        if (
            emit_cnpj
            and dest_cnpj
            and emit_cnpj in own_set
            and dest_cnpj in own_set
            and emit_cnpj != dest_cnpj
        ):
            total_intercompany += 1
        # ---------------------------------------------------------
        targets = []

        if emit_cnpj and emit_cnpj in own_set:
            tag = "P"
            cnpj_proprio = emit_cnpj
        elif dest_cnpj and dest_cnpj in own_set:
            tag = "T"
            cnpj_proprio = dest_cnpj
        else:
            continue

        if cnpj_proprio not in counters:
            continue

        mkey = modelo if modelo in ACCEPTED_MODELS_GLOBAL else "OUT"
        if tag == "P":
            counters[cnpj_proprio]["QTD"] += 1
            counters[cnpj_proprio]["P"][mkey] += 1
        else:
            counters[cnpj_proprio]["QTDETERC"] += 1
            counters[cnpj_proprio]["T"][mkey] += 1

    rows = [
        {
            "CNPJ": _mask_cnpj(cnpj),
            "QTD": v["QTD"],
            "QTDETERC": v["QTDETERC"],
            "P(55)": v["P"]["55"],
            "P(57)": v["P"]["57"],
            "P(65)": v["P"]["65"],
            "P(NFSE)": v["P"]["NFSE"],
            "P(OUT)": v["P"]["OUT"],
            "T(55)": v["T"]["55"],
            "T(57)": v["T"]["57"],
            "T(65)": v["T"]["65"],
            "T(NFSE)": v["T"]["NFSE"],
            "T(OUT)": v["T"]["OUT"],
        }
        for cnpj, v in counters.items()
    ]
    breakdown = {}
    for cnpj, v in counters.items():
        breakdown[_mask_cnpj(cnpj)] = {"P": v["P"], "T": v["T"]}

    # --- LÓGICA DE CONTADORES ATUALIZADA ---
    # O 'total_outros' que o log antigo mostrava (total_xmls - total_dfe)
    # agora será dividido em Eventos e Desconhecidos.
    total_outros_geral = max(total_xmls - total_dfe, 0)
    total_outros_desconhecidos = max(
        0, total_outros_geral - total_eventos_inut
    )

    return (
        rows,
        breakdown,
        total_docs,
        warns,
        total_xmls,
        total_outros_desconhecidos,
        total_eventos_inut,
        total_duplicados,
        total_intercompany,
        min_period,
        max_period,
    )


# --- ATUALIZADO (PATCH 4): Função build_detail_from_zip_resumo (lógica CFOP CTe) ---
def build_detail_from_zip_resumo(zf: zipfile.ZipFile, own_set: set):
    """Gera detalhe agregado (Aba 2) - Atualizado para CFOP de CTe"""
    rows = []
    seen = set()
    for name, xml_bytes in iter_xml_from_zip_resumo(zf, max_depth=3):
        emit_cnpj, dest_cnpj, modelo, chave, (ano, mes), _ = _parse_fields_resumo(
            xml_bytes
        )
        if not modelo or modelo not in ACCEPTED_MODELS_GLOBAL:
            continue
        if not chave or chave in seen:
            continue
        seen.add(chave)

        # --- LÓGICA DO CFOP ATUALIZADA ---
        try:
            root = ET.fromstring(xml_bytes)
            cfop = ""

            # 1. Tenta CFOP de NFe (item)
            cfop_el_nfe = (
                root.find(".//ns:det/ns:prod/ns:CFOP", NS_RESUMO)
                or root.find(".//nfe:det/nfe:prod/nfe:CFOP", NS_RESUMO)
            )
            if cfop_el_nfe is not None and cfop_el_nfe.text:
                cfop = cfop_el_nfe.text

            # 2. Se não achou NFe, tenta CFOP de CTe (header)
            if not cfop:
                cfop_el_cte = (
                    root.find(".//cte:infCTe/cte:ide/cte:CFOP", NS_RESUMO)
                    or _find_first_local_resumo(root, ["infCTe", "ide", "CFOP"])
                )
                if cfop_el_cte is not None and cfop_el_cte.text:
                    cfop = cfop_el_cte.text

            # 3. Fallback para NFe (item) sem namespace
            if not cfop:
                inf_nfe = _find_first_local_resumo(root, ["NFe", "infNFe"]) or _find_first_local_resumo(
                    root, ["infNFe"]
                )
                cfop_el_nfe_fallback = (
                    _find_first_local_resumo(inf_nfe, ["det", "prod", "CFOP"])
                    if inf_nfe is not None
                    else None
                )
                if cfop_el_nfe_fallback is not None and cfop_el_nfe_fallback.text:
                    cfop = cfop_el_nfe_fallback.text

        except Exception:
            cfop = ""
        # --- FIM DA LÓGICA DO CFOP ---

        if emit_cnpj and emit_cnpj in own_set:
            emitente = "P"
            cnpj_proprio = emit_cnpj
        elif dest_cnpj and dest_cnpj in own_set:
            emitente = "T"
            cnpj_proprio = dest_cnpj
        else:
            continue

        rows.append(
            {
                "CNPJ": _mask_cnpj(cnpj_proprio) if cnpj_proprio else "",
                "MODELO DE DOCUMENTO": modelo,
                "CFOP": cfop or "",
                "MES": mes or "",
                "ANO": ano or "",
                "EMITENTE (P/T)": emitente,
                "QUANTIDADE": 1,
            }
        )
    if not rows:
        return []
    df = (
        pd.DataFrame(rows)
        .groupby(
            ["CNPJ", "MODELO DE DOCUMENTO", "CFOP", "MES", "ANO", "EMITENTE (P/T)"],
            dropna=False,
        )["QUANTIDADE"]
        .sum()
        .reset_index()
    )
    return df.to_dict("records")


def build_items_from_zip_resumo(zf: zipfile.ZipFile, own_set: set):
    """Gera planilha de itens (Aba 2)"""
    rows = []
    seen_item = set()
    for name, xml_bytes in iter_xml_from_zip_resumo(zf, max_depth=3):
        emit_cnpj, dest_cnpj, modelo, chave, (_ano, _mes), data_str = _parse_fields_resumo(
            xml_bytes
        )
        if modelo not in {"55", "65"}:
            continue
        if not chave:
            continue
        try:
            root = ET.fromstring(xml_bytes)
        except Exception:
            continue

        if emit_cnpj and emit_cnpj in own_set:
            pt = "P"
            cnpj_ref = emit_cnpj
        elif dest_cnpj and dest_cnpj in own_set:
            pt = "T"
            cnpj_ref = dest_cnpj
        else:
            continue

        inf = (
            root.find(".//ns:infNFe", NS_RESUMO)
            or root.find(".//nfe:infNFe", NS_RESUMO)
            or _find_first_local_resumo(root, ["NFe", "infNFe"])
            or _find_first_local_resumo(root, ["infNFe"])
        )

        det_nodes = []
        if inf is not None:
            det_nodes = list(inf.findall(".//ns:det", NS_RESUMO)) or []
            if not det_nodes:
                det_nodes = [
                    ch
                    for ch in inf.iter()
                    if _localname_resumo(ch.tag).lower() == "det"
                ]

        for det in det_nodes:
            prod = det.find("ns:prod", NS_RESUMO)
            if prod is None:
                for ch in det:
                    if _localname_resumo(ch.tag).lower() == "prod":
                        prod = ch
                        break
            if prod is None:
                continue

            nItem = det.get("nItem") or ""
            key = (chave, nItem)
            if key in seen_item:
                continue
            seen_item.add(key)

            def gx(tag_pref, names_list):
                txt = prod.findtext(tag_pref, default="", namespaces=NS_RESUMO)
                if txt:
                    return txt.strip()
                node = _find_first_local_resumo(prod, names_list)
                return (node.text or "").strip() if node is not None and node.text else ""

            xProd = gx("ns:xProd", ["xProd"])
            NCM = gx("ns:NCM", ["NCM"])
            uCom = gx("ns:uCom", ["uCom"])
            CFOP = gx("ns:CFOP", ["CFOP"])

            rows.append(
                {
                    "CNPJ": _mask_cnpj(cnpj_ref),
                    "Modelo": modelo,
                    "Data": data_str,
                    "P/T": pt,
                    "xProd": xProd,
                    "NCM": NCM,
                    "Unidade": uCom,
                    "CFOP_item": CFOP,
                    "Chave": chave,
                    "nItem": nItem,
                    "CNPJ_emit": _mask_cnpj(emit_cnpj or ""),
                    "CNPJ_dest": _mask_cnpj(dest_cnpj or ""),
                }
            )
    return rows

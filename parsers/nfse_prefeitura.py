from datetime import datetime
from schemas.nfse import NFSe

def _txt(node, path):
    if node is None or not path:
        return None
    el = node.find(path)
    if el is None and not path.startswith(".//"):
        el = node.find(".//" + path)
    if el is None or el.text is None:
        return None
    v = el.text.strip()
    return v if v else None

def _first_txt(node, paths):
    for p in paths:
        v = _txt(node, p)
        if v:
            return v
    return None

def _to_date(s: str):
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            cut = s[:19] if "T" in s else s
            return datetime.strptime(cut, fmt).date()
        except Exception:
            pass
    return None

def _to_float(s: str):
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def parse_nfse_prefeitura(root):
    # busca em profundidade (aguenta variações)
    prest = root.find(".//CPFCNPJPrestador")
    tom   = root.find(".//CPFCNPJTomador")

    nfse = NFSe(
        layout="PREFEITURA_NFE",
        numero=_first_txt(root, ["NumeroNFe", "ChaveNFe/NumeroNFe", "nNFSe", "ChaveNFe/nNFSe", "Numero"]),
        serie=_first_txt(root, ["SerieNFe", "ChaveNFe/SerieNFe", "serie"]),
        codigo_verificacao=_first_txt(root, ["CodigoVerificacao", "ChaveNFe/CodigoVerificacao", "cVerif"]),
        data_emissao=_to_date(_first_txt(root, ["DataEmissaoNFe", "ChaveNFe/DataEmissaoNFe", "DataEmissao", "dEmi"])),
        prestador_cnpjcpf=_first_txt(prest, ["CNPJ", "CPF"]) if prest is not None else None,
        prestador_im=_first_txt(root, ["InscricaoMunicipalPrestador"]) or (_txt(prest, "InscricaoMunicipal") if prest is not None else None),
        prestador_razao=_first_txt(root, ["RazaoSocialPrestador"]) or (_txt(prest, "RazaoSocial") if prest is not None else None),
        tomador_cnpjcpf=_first_txt(tom, ["CNPJ", "CPF"]) if tom is not None else None,
        tomador_razao=_first_txt(root, ["RazaoSocialTomador"]) or (_txt(tom, "RazaoSocial") if tom is not None else None),
        valor_servicos=_to_float(_first_txt(root, ["ValorServicos", "Valores/ValorServicos"])),
        base_calculo=_to_float(_first_txt(root, ["ValorBase", "Valores/ValorBase", "BaseCalculo"])),
        aliquota_iss=_to_float(_first_txt(root, ["AliquotaServicos", "Aliquota", "AliquotaISS"])),
        valor_iss=_to_float(_first_txt(root, ["ValorISS", "ValorIss"])),
        discriminacao=_first_txt(root, ["Discriminacao", "DescricaoServico", "Servico/Discriminacao"]),
    )

    iss_ret = _first_txt(root, ["ISSRetido", "IssRetido"])
    if iss_ret is not None:
        nfse.iss_retido = iss_ret.strip() in ("1", "true", "True", "S", "s")

    return nfse

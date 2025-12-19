from datetime import datetime
from schemas.nfse import NFSe

def _txt(node, path):
    el = node.find(path)
    return (el.text or "").strip() if el is not None and el.text else None

def _to_date(s: str):
    if not s:
        return None
    # Ex: 2025-12-16T00:00:00 ou dd/mm/yyyy (varia)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:19], fmt).date()
        except Exception:
            pass
    return None

def _to_float(s: str):
    if s is None:
        return None
    s = s.strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def parse_nfse_prefeitura(root):
    # Pelo seu XML, raiz é NFe e tags são diretas
    prest = root.find("Prestador")
    tom = root.find("Tomador")

    nfse = NFSe(
        layout="PREFEITURA_NFE",
        numero=_txt(root, "NumeroNFe"),
        serie=_txt(root, "SerieNFe"),
        codigo_verificacao=_txt(root, "CodigoVerificacao"),
        data_emissao=_to_date(_txt(root, "DataEmissaoNFe")),
        prestador_cnpjcpf=_txt(prest, "CNPJ") if prest is not None else None,
        prestador_im=_txt(prest, "InscricaoMunicipal") if prest is not None else None,
        prestador_razao=_txt(prest, "RazaoSocial") if prest is not None else None,
        tomador_cnpjcpf=_txt(tom, "CNPJ") or _txt(tom, "CPF") if tom is not None else None,
        tomador_razao=_txt(tom, "RazaoSocial") if tom is not None else None,
        valor_servicos=_to_float(_txt(root, "ValorServicos")),
        base_calculo=_to_float(_txt(root, "ValorBase")),
        aliquota_iss=_to_float(_txt(root, "AliquotaServicos")),
        valor_iss=_to_float(_txt(root, "ValorISS")),
        discriminacao=_txt(root, "Discriminacao"),
    )

    iss_ret = _txt(root, "ISSRetido")
    if iss_ret is not None:
        nfse.iss_retido = iss_ret.strip() in ("1", "true", "True", "S", "s")

    return nfse

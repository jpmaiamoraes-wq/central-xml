from datetime import datetime, date
from schemas.nfse import NFSe

def _txt(node, path, ns=None):
    el = node.find(path, ns or {})
    return (el.text or "").strip() if el is not None and el.text else None

def _to_date(s: str):
    if not s:
        return None
    # ABRASF costuma vir ISO
    # ex: 2025-06-01T10:20:30
    try:
        return datetime.fromisoformat(s.replace("Z","")).date()
    except Exception:
        return None

def _to_float(s: str):
    if s is None:
        return None
    s = s.strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def parse_nfse_abrasf(root):
    ns = {"nfse": "http://www.abrasf.org.br/nfse.xsd"}

    inf = root.find(".//nfse:InfNfse", ns)
    if inf is None:
        return None

    prest = inf.find(".//nfse:PrestadorServico", ns)
    tom = inf.find(".//nfse:TomadorServico", ns)

    nfse = NFSe(
        layout="ABRASF_2.01",
        numero=_txt(inf, "nfse:Numero", ns),
        codigo_verificacao=_txt(inf, "nfse:CodigoVerificacao", ns),
        data_emissao=_to_date(_txt(inf, "nfse:DataEmissao", ns)),
        competencia=_to_date(_txt(inf, "nfse:Competencia", ns)),
        prestador_cnpjcpf=_txt(prest, ".//nfse:Cnpj", ns) if prest is not None else None,
        prestador_im=_txt(prest, ".//nfse:InscricaoMunicipal", ns) if prest is not None else None,
        tomador_cnpjcpf=_txt(tom, ".//nfse:Cnpj", ns) or _txt(tom, ".//nfse:Cpf", ns) if tom is not None else None,
        valor_servicos=_to_float(_txt(inf, ".//nfse:Servico/nfse:Valores/nfse:ValorServicos", ns)),
        base_calculo=_to_float(_txt(inf, ".//nfse:ValoresNfse/nfse:BaseCalculo", ns)),
        aliquota_iss=_to_float(_txt(inf, ".//nfse:ValoresNfse/nfse:Aliquota", ns)),
        valor_iss=_to_float(_txt(inf, ".//nfse:ValoresNfse/nfse:ValorIss", ns)),
        discriminacao=_txt(inf, ".//nfse:Servico/nfse:Discriminacao", ns),
    )
    iss_ret = _txt(inf, ".//nfse:Servico/nfse:Valores/nfse:IssRetido", ns)
    if iss_ret is not None:
        nfse.iss_retido = iss_ret.strip() in ("1", "true", "True", "S", "s")

    return nfse

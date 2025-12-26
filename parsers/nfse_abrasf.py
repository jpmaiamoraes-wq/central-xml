import xml.etree.ElementTree as ET

from schemas.nfse import NFSe

from datetime import datetime

def _txt(node, path: str, ns: dict):
    """
    Pega o texto de um elemento pelo XPath. Retorna None se não achar.
    Aceita path com prefixo (nfse:...) quando ns estiver preenchido.
    """
    if node is None or not path:
        return None
    try:
        el = node.find(path, ns) if ns else node.find(path)
        if el is None:
            return None
        if el.text is None:
            return None
        v = el.text.strip()
        return v if v else None
    except Exception:
        return None

def _to_date(s: str):
    if not s:
        return None
    s = str(s).strip()
    if not s:
        return None

    # formatos comuns NFSe/ABRASF
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass

    # fallback: tenta cortar timezone tipo 2025-12-01T10:20:30-03:00
    try:
        if len(s) >= 19 and s[10] == "T":
            return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
    except Exception:
        pass

    return None

def _to_float(s: str):
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None

    # trata "1.234,56" e "1234,56" e "1234.56"
    if "," in s and "." in s:
        # assume ponto milhar e vírgula decimal
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")

    try:
        return float(s)
    except Exception:
        return None

def _local(tag: str) -> str:
    return tag.split("}")[-1] if tag else tag

def _ns_uri(tag: str):
    if tag and tag.startswith("{") and "}" in tag:
        return tag[1:tag.index("}")]
    return None

def _find_first_by_localname(root, localname: str):
    for e in root.iter():
        if _local(e.tag) == localname:
            return e
    return None

def _first_txt(node, paths, ns):
    if node is None:
        return None
    for xp in paths:
        v = _txt(node, xp, ns)
        if v:
            v = v.strip()
            if v:
                return v
    return None

def parse_nfse_abrasf(root):
    # 1) acha InfNfse em qualquer lugar (pega SOAP também)
    inf = _find_first_by_localname(root, "InfNfse")
    if inf is None:
        return None

    # 2) descobre namespace real do XML (varia entre provedores)
    uri = _ns_uri(inf.tag)
    if not uri:
        # fallback: procura algum elemento que tenha "abrasf" no namespace
        for e in root.iter():
            u = _ns_uri(e.tag)
            if u and "abrasf" in u.lower():
                uri = u
                break

    ns = {"nfse": uri} if uri else {}

    # 3) nós principais (com fallbacks)
    prest = _find_first_by_localname(inf, "PrestadorServico")
    # Em alguns vem Prestador dentro de Servico/Prestador
    prest_alt = _find_first_by_localname(inf, "Prestador")

    # Tomador pode ser TomadorServico OU Tomador
    tom = _find_first_by_localname(inf, "TomadorServico") or _find_first_by_localname(inf, "Tomador")

    # 4) campos com múltiplos XPaths (englobando variações)
    prest_cnpjcpf = (
        _first_txt(prest, [".//nfse:Cnpj", ".//nfse:Cpf"], ns)
        or _first_txt(prest_alt, [".//nfse:Cnpj", ".//nfse:Cpf"], ns)
        or _first_txt(inf, [
            ".//nfse:PrestadorServico//nfse:Cnpj",
            ".//nfse:PrestadorServico//nfse:Cpf",
            ".//nfse:Servico//nfse:Prestador//nfse:Cnpj",
            ".//nfse:Servico//nfse:Prestador//nfse:Cpf",
            ".//nfse:Servico//nfse:Prestador//nfse:CpfCnpj//nfse:Cnpj",
            ".//nfse:Servico//nfse:Prestador//nfse:CpfCnpj//nfse:Cpf",
        ], ns)
    )

    prest_im = (
        _first_txt(prest, [".//nfse:InscricaoMunicipal"], ns)
        or _first_txt(prest_alt, [".//nfse:InscricaoMunicipal"], ns)
        or _first_txt(inf, [
            ".//nfse:PrestadorServico//nfse:InscricaoMunicipal",
            ".//nfse:Servico//nfse:Prestador//nfse:InscricaoMunicipal",
        ], ns)
    )

    tomador_cnpjcpf = (
        _first_txt(tom, [
            ".//nfse:IdentificacaoTomador/nfse:CpfCnpj/nfse:Cnpj",
            ".//nfse:IdentificacaoTomador/nfse:CpfCnpj/nfse:Cpf",
            ".//nfse:CpfCnpj/nfse:Cnpj",
            ".//nfse:CpfCnpj/nfse:Cpf",
        ], ns)
        or _first_txt(inf, [
            ".//nfse:TomadorServico//nfse:IdentificacaoTomador//nfse:Cnpj",
            ".//nfse:TomadorServico//nfse:IdentificacaoTomador//nfse:Cpf",
            ".//nfse:Tomador//nfse:IdentificacaoTomador//nfse:Cnpj",
            ".//nfse:Tomador//nfse:IdentificacaoTomador//nfse:Cpf",
        ], ns)
    )

    # valores: alguns provedores usam ValoresNfse, outros só Servico/Valores
    valor_servicos = _to_float(_first_txt(inf, [
        ".//nfse:Servico/nfse:Valores/nfse:ValorServicos",
        ".//nfse:ValoresNfse/nfse:ValorServicos",
    ], ns))

    base_calculo = _to_float(_first_txt(inf, [
        ".//nfse:ValoresNfse/nfse:BaseCalculo",
        ".//nfse:Servico/nfse:Valores/nfse:BaseCalculo",
    ], ns))

    aliquota_iss = _to_float(_first_txt(inf, [
        ".//nfse:ValoresNfse/nfse:Aliquota",
        ".//nfse:Servico/nfse:Valores/nfse:Aliquota",
    ], ns))

    valor_iss = _to_float(_first_txt(inf, [
        ".//nfse:ValoresNfse/nfse:ValorIss",
        ".//nfse:Servico/nfse:Valores/nfse:ValorIss",
    ], ns))

    discriminacao = _first_txt(inf, [
        ".//nfse:Servico/nfse:Discriminacao",
    ], ns)

    nfse = NFSe(
        layout="ABRASF_2.01",
        numero=_first_txt(inf, ["nfse:Numero", ".//nfse:Numero"], ns),
        codigo_verificacao=_first_txt(inf, ["nfse:CodigoVerificacao", ".//nfse:CodigoVerificacao"], ns),
        data_emissao=_to_date(_first_txt(inf, ["nfse:DataEmissao", ".//nfse:DataEmissao"], ns)),
        competencia=_to_date(_first_txt(inf, ["nfse:Competencia", ".//nfse:Competencia"], ns)),
        prestador_cnpjcpf=prest_cnpjcpf,
        prestador_im=prest_im,
        tomador_cnpjcpf=tomador_cnpjcpf,
        valor_servicos=valor_servicos,
        base_calculo=base_calculo,
        aliquota_iss=aliquota_iss,
        valor_iss=valor_iss,
        discriminacao=discriminacao,
    )

    iss_ret = _first_txt(inf, [
        ".//nfse:Servico/nfse:Valores/nfse:IssRetido",
        ".//nfse:ValoresNfse/nfse:IssRetido",
    ], ns)
    if iss_ret is not None:
        nfse.iss_retido = iss_ret.strip() in ("1", "true", "True", "S", "s")

    return nfse

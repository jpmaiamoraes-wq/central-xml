import xml.etree.ElementTree as ET

from parsers.nfse_abrasf import parse_nfse_abrasf
from parsers.nfse_prefeitura import parse_nfse_prefeitura

def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag

def detect_and_parse_nfse(xml_text: str):
    """
    Retorna NFSe (schema) ou None se não for NFSe suportada.
    """
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return None

    root_name = _strip_ns(root.tag)

    # ABRASF: geralmente <CompNfse>...
    if root_name.lower() == "compnfse":
        return parse_nfse_abrasf(root)

    # Modelo prefeitura que veio como <NFe>...
    if root_name.lower() == "nfe":
        return parse_nfse_prefeitura(root)

    return None

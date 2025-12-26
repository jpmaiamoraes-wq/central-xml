import xml.etree.ElementTree as ET

from parsers.nfse_abrasf import parse_nfse_abrasf # type: ignore
from parsers.nfse_prefeitura import parse_nfse_prefeitura

def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag

def _ns_uri(tag: str):
    if tag and tag.startswith("{") and "}" in tag:
        return tag[1:tag.index("}")]
    return None

def _has_local(root, localname: str) -> bool:
    for e in root.iter():
        if _strip_ns(e.tag).lower() == localname.lower():
            return True
    return False

def _has_abrasf_namespace(root) -> bool:
    # tenta achar qualquer namespace contendo "abrasf"
    for e in root.iter():
        ns = _ns_uri(e.tag)
        if ns and "abrasf" in ns.lower():
            return True
    return False

def detect_and_parse_nfse(xml_text: str):
    """
    Retorna NFSe (schema) ou None se não for NFSe suportada.
    """
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return None

    root_name = _strip_ns(root.tag).lower()

    # 1) Modelo prefeitura específico
    if root_name == "nfe":
        return parse_nfse_prefeitura(root)

    # 2) ABRASF "clássico"
    if root_name == "compnfse":
        return parse_nfse_abrasf(root)

    # 3) ABRASF em outras raízes (inclui SOAP)
    # Critério principal: existe InfNfse em qualquer lugar
    if _has_local(root, "InfNfse"):
        # opcional: reforço pelo namespace abrasf (evita falso positivo)
        if _has_abrasf_namespace(root) or root_name in {
            "nfse", "gerarnfseresposta", "consultarnfseresposta", "envelope"
        }:
            return parse_nfse_abrasf(root)

    return None

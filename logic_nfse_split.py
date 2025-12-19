# logic_nfse_split.py
import io
import zipfile
import xml.etree.ElementTree as ET

def split_nfse_abrasf(xml_bytes: bytes, prefix="nfse_"):
    root = ET.fromstring(xml_bytes)

    ns_url = "http://www.abrasf.org.br/nfse.xsd"
    ns = {"nf": ns_url}

    try:
        ET.register_namespace("", ns_url)
    except Exception:
        pass

    notas = root.findall(".//nf:CompNfse", ns)
    if not notas:
        notas = root.findall(".//CompNfse")

    if not notas:
        return []  # não é lote nesse padrão

    saida = []
    for idx, nota in enumerate(notas, start=1):
        numero = None

        n = nota.find(".//nf:InfNfse/nf:Numero", ns)
        if n is not None and (n.text or "").strip():
            numero = n.text.strip()

        if not numero:
            n = nota.find(".//InfNfse/Numero")
            if n is not None and (n.text or "").strip():
                numero = n.text.strip()

        if not numero:
            numero = f"desconhecida_{idx}"

        filename = f"{prefix}{numero}.xml"
        xml_out = ET.tostring(nota, encoding="utf-8", xml_declaration=True)
        saida.append((filename, xml_out))

    return saida


def make_zip_bytes(files: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, content in files:
            z.writestr(name, content)
    return buf.getvalue()

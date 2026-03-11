import io
import zipfile
import xml.etree.ElementTree as ET

def split_nfse_abrasf(xml_bytes: bytes, filename_original="nota.xml", prefix="sep_"):
    xml_text = None
    try:
        xml_text = xml_bytes.decode('utf-8')
    except UnicodeDecodeError:
        try:
            xml_text = xml_bytes.decode('iso-8859-1')
        except Exception:
            return [(filename_original, xml_bytes)]

    try:
        if xml_text:
            xml_text = xml_text.replace('encoding="iso-8859-1"', 'encoding="utf-8"')
            xml_text = xml_text.replace('encoding="ISO-8859-1"', 'encoding="utf-8"')
        root = ET.fromstring(xml_text)
    except Exception:
        return [(filename_original, xml_bytes)]

    saida = []
    numeros_processados = set()

    def get_local_tag(tag):
        return tag.split('}')[-1]

    def find_blind_text(element, tags_alvo: list):
        """Busca o texto de qualquer uma das tags na lista fornecida dentro do elemento."""
        for child in element.iter():
            if get_local_tag(child.tag) in tags_alvo:
                return child.text.strip() if child.text else None
        return None

    # Mantendo todos os padrões solicitados
    tags_bloco_nota = ['CompNfse', 'Nfse', 'nfdok', 'Reg20Item']
    
    # Busca todos os candidatos
    candidatos_brutos = [elem for elem in root.iter() if get_local_tag(elem.tag) in tags_bloco_nota]
    
    # Lógica para evitar duplicidade entre tags pai e filhas (ex: CompNfse vs Nfse)
    blocos_finais = []
    for i, cand in enumerate(candidatos_brutos):
        is_child = False
        for j, outro in enumerate(candidatos_brutos):
            if i != j:
                # Verifica se o candidato atual 'cand' está dentro do 'outro'
                if any(cand is child for child in outro.iter()):
                    is_child = True
                    break
        if not is_child:
            blocos_finais.append(cand)

    # Tags de busca para nome de arquivo
    tags_numero = ['Numero', 'NumeroNota', 'NumNf']
    tags_cnpj = ['Cnpj', 'CpfCnpj', 'ClienteCNPJCPF', 'CpfCnpjPre']

    blocos_validos = []
    for bloco in blocos_finais:
        num_nota = find_blind_text(bloco, tags_numero)
        if num_nota and num_nota not in numeros_processados:
            blocos_validos.append(bloco)
            numeros_processados.add(num_nota)

    if len(blocos_validos) <= 1:
        return [(filename_original, xml_bytes)]

    for nota in blocos_validos:
        numero = find_blind_text(nota, tags_numero)
        cnpj = find_blind_text(nota, tags_cnpj) or "sem_cnpj"
        
        cnpj_clean = "".join(filter(str.isalnum, cnpj))
        filename = f"{prefix}{cnpj_clean}_{numero}.xml"
        
        try:
            # tstring gera o XML individual preservando o bloco completo
            xml_out = ET.tostring(nota, encoding="utf-8", xml_declaration=True)
            saida.append((filename, xml_out))
        except Exception:
            continue

    return saida

def make_zip_bytes(files: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, content in files:
            z.writestr(name, content)
    return buf.getvalue()
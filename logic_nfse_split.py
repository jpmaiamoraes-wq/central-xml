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

    # --- NOVA FUNÇÃO DE BUSCA RECURSIVA ---
    def find_deep_text(element, tags_alvo: list):
        """Busca exaustivamente por qualquer tag da lista em toda a subárvore do elemento."""
        for child in element.iter():
            local = get_local_tag(child.tag)
            if local in tags_alvo and child.text and child.text.strip():
                return child.text.strip()
        return None

    # Padrões de blocos solicitados
    tags_bloco_nota = ['CompNfse', 'Nfse', 'nfdok', 'Reg20Item']
    
    candidatos_brutos = [elem for elem in root.iter() if get_local_tag(elem.tag) in tags_bloco_nota]
    
    # Filtro pai-filho para evitar duplicidade
    blocos_finais = []
    for i, cand in enumerate(candidatos_brutos):
        is_child = False
        for j, outro in enumerate(candidatos_brutos):
            if i != j:
                if any(cand is child for child in outro.iter()):
                    is_child = True
                    break
        if not is_child:
            blocos_finais.append(cand)

    # Tags de busca
    tags_numero = ['Numero', 'NumeroNota', 'NumNf']
    # Adicionamos 'Cnpj' explicitamente para capturar mesmo em níveis profundos
    tags_cnpj = ['Cnpj', 'CpfCnpj', 'ClienteCNPJCPF', 'CpfCnpjPre']

    blocos_validos = []
    for bloco in blocos_finais:
        num_nota = find_deep_text(bloco, tags_numero)
        if num_nota and num_nota not in numeros_processados:
            blocos_validos.append(bloco)
            numeros_processados.add(num_nota)

    if len(blocos_validos) <= 1:
        return [(filename_original, xml_bytes)]

    for nota in blocos_validos:
        numero = find_deep_text(nota, tags_numero)
        # O find_deep_text agora varrerá até encontrar o <Cnpj> dentro de <CpfCnpj>
        cnpj = find_deep_text(nota, tags_cnpj) or "sem_cnpj"
        
        cnpj_clean = "".join(filter(str.isalnum, cnpj))
        filename = f"{prefix}{cnpj_clean}_{numero}.xml"
        
        try:
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
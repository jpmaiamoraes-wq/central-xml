import io
import zipfile
import xml.etree.ElementTree as ET

def split_nfse_abrasf(xml_bytes: bytes, prefix="nfse_"):
    try:
        root = ET.fromstring(xml_bytes)
    except Exception as e:
        print(f"Erro ao ler XML: {e}")
        return []

    saida = []
    numeros_processados = set() # Controle para evitar duplicados no mesmo arquivo

    def get_local_tag(tag):
        return tag.split('}')[-1]

    def find_blind(element, tag_target):
        for child in element.iter():
            if get_local_tag(child.tag) == tag_target:
                return child
        return None

    # --- LÓGICA DE IDENTIFICAÇÃO DE BLOCOS ---
    # Buscamos Nfse ou CompNfse
    candidatos = [elem for elem in root.iter() if get_local_tag(elem.tag) in ['CompNfse', 'Nfse']]
    
    # Filtramos para pegar apenas os blocos que possuem Numero e que não são "filhos" de outro bloco já aceito
    blocos_validos = []
    for cand in candidatos:
        num_elem = find_blind(cand, 'Numero')
        if num_elem is not None and num_elem.text:
            num_nota = num_elem.text.strip()
            
            # Se já processamos esse número de nota NESTE arquivo, ignoramos os blocos internos
            if num_nota not in numeros_processados:
                blocos_validos.append(cand)
                numeros_processados.add(num_nota)

    # Se só houver 1 nota no arquivo inteiro, retornamos vazio para não desmembrar (mantém original)
    if len(blocos_validos) <= 1:
        return []

    for idx, nota in enumerate(blocos_validos):
        num_elem = find_blind(nota, 'Numero')
        numero = num_elem.text.strip()
        
        cnpj_elem = find_blind(nota, 'Cnpj')
        cnpj = cnpj_elem.text.strip() if cnpj_elem is not None and cnpj_elem.text else "sem_cnpj"

        filename = f"{prefix}{cnpj}_{numero}.xml"
        
        try:
            xml_out = ET.tostring(nota, encoding="utf-8", xml_declaration=True)
            saida.append((filename, xml_out))
        except Exception as e:
            print(f"Erro ao gerar string para a nota {numero}: {e}")

    return saida

def make_zip_bytes(files: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, content in files:
            z.writestr(name, content)
    return buf.getvalue()
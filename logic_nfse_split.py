import io
import zipfile
import xml.etree.ElementTree as ET

def split_nfse_universal(xml_bytes: bytes, prefix="nfse_"):
    try:
        # Tenta decodificar ignorando erros de encoding comuns em XMLs zumbi
        xml_text = xml_bytes.decode('utf-8', errors='ignore')
        root = ET.fromstring(xml_text)
    except Exception as e:
        print(f"Erro ao ler XML: {e}")
        return []

    saida = []
    numeros_processados = set()

    def get_local_tag(tag):
        return tag.split('}')[-1]

    def find_blind_text(element, tags_alvo: list):
        """Busca o texto de qualquer uma das tags na lista fornecida"""
        for child in element.iter():
            if get_local_tag(child.tag) in tags_alvo:
                return child.text.strip() if child.text else None
        return None

    # --- LÓGICA DE IDENTIFICAÇÃO DE BLOCOS ---
    # Adicionamos 'nfdok' (Exemplo 1) e 'Reg20Item' (Exemplo 2)
    tags_bloco_nota = ['CompNfse', 'Nfse', 'nfdok', 'Reg20Item']
    
    candidatos = [elem for elem in root.iter() if get_local_tag(elem.tag) in tags_bloco_nota]
    
    # Possíveis nomes para a tag de Número e CNPJ dependendo do layout
    tags_numero = ['Numero', 'NumeroNota', 'NumNf']
    tags_cnpj = ['Cnpj', 'ClienteCNPJCPF', 'CpfCnpjPre']

    blocos_validos = []
    for cand in candidatos:
        num_nota = find_blind_text(cand, tags_numero)
        
        if num_nota:
            # Se já processamos esse número, evitamos duplicar (caso de tags aninhadas)
            if num_nota not in numeros_processados:
                blocos_validos.append(cand)
                numeros_processados.add(num_nota)

    # Se só houver 1 nota no arquivo inteiro, retornamos vazio (mantém original)
    if len(blocos_validos) <= 1:
        return []

    for nota in blocos_validos:
        numero = find_blind_text(nota, tags_numero)
        cnpj = find_blind_text(nota, tags_cnpj) or "sem_cnpj"
        
        # Limpar caracteres especiais do CNPJ para o nome do arquivo
        cnpj_clean = "".join(filter(str.isalnum, cnpj))

        filename = f"{prefix}{cnpj_clean}_{numero}.xml"
        
        try:
            # Geramos o XML individual para cada bloco identificado
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
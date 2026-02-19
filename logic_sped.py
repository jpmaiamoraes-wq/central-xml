import io
import zipfile
import pandas as pd
import docx  # Importação necessária para ler .docx

def _decode_sped_bytes(data: bytes) -> str:
    """
    Tenta decodificar os bytes de um arquivo SPED usando
    latin-1, cp1252 e utf-8 (nessa ordem).
    """
    for enc in ("latin-1", "cp1252", "utf-8"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("latin-1", errors="ignore")

def _extract_text_from_docx(data: bytes) -> str:
    """
    Extrai todo o texto de um arquivo .docx e retorna como string,
    preservando as quebras de linha.
    """
    doc_file = io.BytesIO(data)
    doc = docx.Document(doc_file)
    # Une os parágrafos com quebra de linha para simular o formato do TXT
    return "\n".join([para.text for para in doc.paragraphs])

def _parse_efd_icms_ipi_txt(txt_bytes: bytes, source_name: str | None = None, is_text: bool = False):
    """
    Lê um conteúdo de EFD ICMS/IPI. 
    'is_text' indica se o dado já vem como string (útil para docx).
    """
    if is_text:
        texto = txt_bytes # Aqui txt_bytes já é a string extraída
    else:
        texto = _decode_sped_bytes(txt_bytes)
        
    linhas = texto.splitlines()

    # --- (O RESTANTE DA SUA LÓGICA DE PARSE PERMANECE IGUAL) ---
    # Acúmulos
    rows_0190: list[list[str]] = []
    rows_0200: list[list[str]] = []
    c100_atual: list[str] | None = None
    rows_c100_only: list[list[str]] = []
    rows_c100_c170_pairs: list[tuple[list[str], list[str]]] = []
    rows_c100_c190_pairs: list[tuple[list[str], list[str]]] = []

    cols_0190_layout = ["REG", "UNID", "DESCR"]
    cols_0200_layout = ["REG", "COD_ITEM", "DESCR_ITEM", "COD_BARRA", "COD_ANT_ITEM", "UNID_INV", "TIPO_ITEM", "COD_NCM", "EX_IPI", "COD_GEN", "COD_LST", "ALIQ_ICMS"]
    c100_cols_layout = ["REG", "IND_OPER", "IND_EMIT", "COD_PART", "COD_MOD", "COD_SIT", "SER", "NUM_DOC", "CHV_NFE", "DT_DOC", "DT_E_S", "VL_DOC"]
    c170_cols_layout = ["REG", "NUM_ITEM", "COD_ITEM", "DESCR_COMPL", "QTD", "UNID", "VL_ITEM", "VL_DESC", "IND_MOV", "CST_ICMS", "CFOP", "COD_NAT"]
    c190_cols_layout = ["REG", "CST_ICMS", "CFOP", "ALIQ_ICMS", "VL_OPR", "VL_BC_ICMS", "VL_ICMS", "VL_BC_ICMS_ST", "VL_ICMS_ST", "VL_RED_BC", "VL_IPI", "COD_OBS"]

    for linha in linhas:
        linha = linha.strip()
        if not linha or "|" not in linha: continue
        if not linha.startswith("|"): continue
        partes = linha.split("|")
        if len(partes) < 3: continue
        campos = partes[1:-1]
        if not campos: continue
        reg = campos[0].upper()

        if reg == "0190": rows_0190.append(campos)
        elif reg == "0200": rows_0200.append(campos)
        elif reg == "C100":
            c100_atual = campos
            rows_c100_only.append(campos)
        elif reg == "C170" and c100_atual is not None:
            rows_c100_c170_pairs.append((c100_atual, campos))
        elif reg == "C190" and c100_atual is not None:
            rows_c100_c190_pairs.append((c100_atual, campos))

    def build_df_fixed(rows, layout_cols, prefix_extra):
        if not rows: return pd.DataFrame()
        max_len = max(len(r) for r in rows)
        padded = [r + [""] * (max_len - len(r)) for r in rows]
        if max_len <= len(layout_cols):
            cols = layout_cols[:max_len]
        else:
            extras = [f"{prefix_extra}_EXTRA_{i}" for i in range(len(layout_cols) + 1, max_len + 1)]
            cols = layout_cols + extras
        return pd.DataFrame(padded, columns=cols)

    df_0190 = build_df_fixed(rows_0190, cols_0190_layout, "B0190")
    df_0200 = build_df_fixed(rows_0200, cols_0200_layout, "B0200")
    rows_c100_c170_c190: list[list[str]] = []

    if rows_c100_c170_pairs or rows_c100_c190_pairs:
        for c100_row, c170_row in rows_c100_c170_pairs:
            c100_cols = (c100_row + [""] * 12)[:12]
            c170_cols = (c170_row + [""] * 12)[:12]
            rows_c100_c170_c190.append(c100_cols + c170_cols + ([""] * 12))
        for c100_row, c190_row in rows_c100_c190_pairs:
            c100_cols = (c100_row + [""] * 12)[:12]
            c190_cols = (c190_row + [""] * 12)[:12]
            rows_c100_c170_c190.append(c100_cols + ([""] * 12) + c190_cols)
    elif rows_c100_only:
        for c100_row in rows_c100_only:
            c100_cols = (c100_row + [""] * 12)[:12]
            rows_c100_c170_c190.append(c100_cols + ([""] * 12) + ([""] * 12))

    if rows_c100_c170_c190:
        max_len = max(len(r) for r in rows_c100_c170_c190)
        padded = [r + [""] * (max_len - len(r)) for r in rows_c100_c170_c190]
        cols_c100 = [f"C100_{c}" for c in c100_cols_layout]
        cols_c170 = [f"C170_{c}" for c in c170_cols_layout]
        cols_c190 = [f"C190_{c}" for c in c190_cols_layout]
        base_cols = cols_c100 + cols_c170 + cols_c190
        cols = base_cols + [f"C_EXTRAS_{i}" for i in range(len(base_cols) + 1, max_len + 1)] if max_len > len(base_cols) else base_cols[:max_len]
        df_c100_c170 = pd.DataFrame(padded, columns=cols)
    else:
        df_c100_c170 = pd.DataFrame()

    if source_name:
        for df in (df_0190, df_0200, df_c100_c170):
            if df is not None and not df.empty:
                df.insert(0, "ARQUIVO_ORIGEM", source_name)

    if not df_c100_c170.empty:
        for col in ["C100_DT_DOC", "C100_DT_E_S"]:
            if col in df_c100_c170.columns:
                s = df_c100_c170[col].astype(str).str.strip().str.extract(r"(\d{8})", expand=False)
                df_c100_c170[col] = pd.to_datetime(s, format="%d%m%Y", errors="coerce")

    return df_0190, df_0200, df_c100_c170


def parse_sped_from_any(data: bytes, filename: str):
    """
    Suporta TXT, ZIP e agora DOCX.
    """
    filename_lower = (filename or "").lower()
    dfs_0190, dfs_0200, dfs_c100_c170 = [], [], []

    # --- Lógica para TXT ---
    if filename_lower.endswith(".txt"):
        res = _parse_efd_icms_ipi_txt(data, source_name=filename)
        dfs_0190.append(res[0]); dfs_0200.append(res[1]); dfs_c100_c170.append(res[2])

    # --- Lógica para DOCX ---
    elif filename_lower.endswith(".docx"):
        texto_docx = _extract_text_from_docx(data)
        # Passamos o texto extraído diretamente
        res = _parse_efd_icms_ipi_txt(texto_docx, source_name=filename, is_text=True)
        dfs_0190.append(res[0]); dfs_0200.append(res[1]); dfs_c100_c170.append(res[2])

    # --- Lógica para ZIP ---
    elif filename_lower.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                fname = info.filename.lower()
                if fname.endswith(".txt"):
                    with zf.open(info) as f:
                        res = _parse_efd_icms_ipi_txt(f.read(), source_name=info.filename)
                elif fname.endswith(".docx"):
                    with zf.open(info) as f:
                        texto = _extract_text_from_docx(f.read())
                        res = _parse_efd_icms_ipi_txt(texto, source_name=info.filename, is_text=True)
                else:
                    continue
                dfs_0190.append(res[0]); dfs_0200.append(res[1]); dfs_c100_c170.append(res[2])

    def _concat(dfs):
        dfs = [d for d in dfs if d is not None and not d.empty]
        return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

    return _concat(dfs_0190), _concat(dfs_0200), _concat(dfs_c100_c170)
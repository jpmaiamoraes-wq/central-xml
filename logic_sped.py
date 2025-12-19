# logic_sped.py
import io
import zipfile
import pandas as pd


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


def _parse_efd_icms_ipi_txt(txt_bytes: bytes, source_name: str | None = None):
    """
    Lê um TXT de EFD ICMS/IPI e retorna:
      - df_0190  (REG, UNID, DESCR, ...)
      - df_0200  (REG, COD_ITEM, DESCR_ITEM, ...)
      - df_c100_c170  (C100 + C170 + C190)
        * Se não houver C170, as colunas C170_* vêm vazias.
        * Se não houver C190, as colunas C190_* vêm vazias.
        * Se houver apenas C190 (sem C170), C170_* fica vazio.
    """

    texto = _decode_sped_bytes(txt_bytes)
    linhas = texto.splitlines()

    # Acúmulos
    rows_0190: list[list[str]] = []
    rows_0200: list[list[str]] = []

    # C100 / C170 / C190
    c100_atual: list[str] | None = None
    rows_c100_only: list[list[str]] = []              # somente C100 (caso sem C170/C190)
    rows_c100_c170_pairs: list[tuple[list[str], list[str]]] = []
    rows_c100_c190_pairs: list[tuple[list[str], list[str]]] = []

    # Layouts oficiais (primeiras 12 colunas)
    cols_0190_layout = ["REG", "UNID", "DESCR"]

    cols_0200_layout = [
        "REG", "COD_ITEM", "DESCR_ITEM", "COD_BARRA", "COD_ANT_ITEM",
        "UNID_INV", "TIPO_ITEM", "COD_NCM", "EX_IPI", "COD_GEN",
        "COD_LST", "ALIQ_ICMS",
    ]

    c100_cols_layout = [
        "REG", "IND_OPER", "IND_EMIT", "COD_PART", "COD_MOD", "COD_SIT",
        "SER", "NUM_DOC", "CHV_NFE", "DT_DOC", "DT_E_S", "VL_DOC",
    ]

    c170_cols_layout = [
        "REG", "NUM_ITEM", "COD_ITEM", "DESCR_COMPL", "QTD", "UNID",
        "VL_ITEM", "VL_DESC", "IND_MOV", "CST_ICMS", "CFOP", "COD_NAT",
    ]

    # layout C190 (primeiras 12 colunas do registro C190)
    # Campos mais comuns: REG, CST_ICMS, CFOP, ALIQ_ICMS, VL_OPR, VL_BC_ICMS,
    # VL_ICMS, VL_BC_ICMS_ST, VL_ICMS_ST, VL_RED_BC, VL_IPI, COD_OBS
    c190_cols_layout = [
        "REG", "CST_ICMS", "CFOP", "ALIQ_ICMS", "VL_OPR", "VL_BC_ICMS",
        "VL_ICMS", "VL_BC_ICMS_ST", "VL_ICMS_ST", "VL_RED_BC", "VL_IPI",
        "COD_OBS",
    ]

    for linha in linhas:
        linha = linha.strip()
        if not linha or "|" not in linha:
            continue
        if not linha.startswith("|"):
            continue

        partes = linha.split("|")
        if len(partes) < 3:
            continue

        # remove apenas o primeiro e o último "", preservando vazios internos
        campos = partes[1:-1]
        if not campos:
            continue

        reg = campos[0].upper()

        # -------- 0190 --------
        if reg == "0190":
            rows_0190.append(campos)

        # -------- 0200 --------
        elif reg == "0200":
            rows_0200.append(campos)

        # -------- C100 (cabeçalho) --------
        elif reg == "C100":
            c100_atual = campos
            rows_c100_only.append(campos)

        # -------- C170 (itens) --------
        elif reg == "C170" and c100_atual is not None:
            rows_c100_c170_pairs.append((c100_atual, campos))

        # -------- C190 (resumo por CFOP) --------
        elif reg == "C190" and c100_atual is not None:
            rows_c100_c190_pairs.append((c100_atual, campos))

    # ---------- helper para montar DataFrames com layout fixo ----------
    def build_df_fixed(rows, layout_cols, prefix_extra):
        """
        rows: lista de listas de campos
        layout_cols: nomes oficiais (REG, UNID, ...)
        prefix_extra: prefixo para extras (ex: 'B0190')
        """
        if not rows:
            return pd.DataFrame()

        max_len = max(len(r) for r in rows)
        padded = [r + [""] * (max_len - len(r)) for r in rows]

        if max_len <= len(layout_cols):
            cols = layout_cols[:max_len]
        else:
            extras = [
                f"{prefix_extra}_EXTRA_{i}"
                for i in range(len(layout_cols) + 1, max_len + 1)
            ]
            cols = layout_cols + extras

        return pd.DataFrame(padded, columns=cols)

    # 0190 e 0200 com nomes oficiais
    df_0190 = build_df_fixed(rows_0190, cols_0190_layout, "B0190")
    df_0200 = build_df_fixed(rows_0200, cols_0200_layout, "B0200")

    # ---------- monta C100 + C170 + C190 ----------

    rows_c100_c170_c190: list[list[str]] = []

    # Caso haja C170 e/ou C190 para algum C100
    if rows_c100_c170_pairs or rows_c100_c190_pairs:
        # 1) Linhas originadas de C170 (C100 + C170 + C190 em branco)
        for c100_row, c170_row in rows_c100_c170_pairs:
            c100_cols = (c100_row + [""] * 12)[:12]
            c170_cols = (c170_row + [""] * 12)[:12]
            c190_blank = [""] * 12
            rows_c100_c170_c190.append(c100_cols + c170_cols + c190_blank)

        # 2) Linhas originadas de C190 (C100 + C170 em branco + C190)
        for c100_row, c190_row in rows_c100_c190_pairs:
            c100_cols = (c100_row + [""] * 12)[:12]
            c170_blank = [""] * 12
            c190_cols = (c190_row + [""] * 12)[:12]
            rows_c100_c170_c190.append(c100_cols + c170_blank + c190_cols)

    # Caso não haja C170/C190, mas exista C100 isolado
    elif rows_c100_only:
        for c100_row in rows_c100_only:
            c100_cols = (c100_row + [""] * 12)[:12]
            c170_blank = [""] * 12
            c190_blank = [""] * 12
            rows_c100_c170_c190.append(c100_cols + c170_blank + c190_blank)

    # Monta DataFrame final de C100 + C170 + C190
    if rows_c100_c170_c190:
        max_len = max(len(r) for r in rows_c100_c170_c190)
        padded = [r + [""] * (max_len - len(r)) for r in rows_c100_c170_c190]

        cols_c100 = [f"C100_{c}" for c in c100_cols_layout]
        cols_c170 = [f"C170_{c}" for c in c170_cols_layout]
        cols_c190 = [f"C190_{c}" for c in c190_cols_layout]

        base_cols = cols_c100 + cols_c170 + cols_c190
        if max_len <= len(base_cols):
            cols = base_cols[:max_len]
        else:
            extras = [
                f"C_EXTRAS_{i}"
                for i in range(len(base_cols) + 1, max_len + 1)
            ]
            cols = base_cols + extras

        df_c100_c170 = pd.DataFrame(padded, columns=cols)
    else:
        df_c100_c170 = pd.DataFrame()

    # ---------- adicionar coluna ARQUIVO_ORIGEM ----------
    if source_name:
        for df in (df_0190, df_0200, df_c100_c170):
            if df is not None and not df.empty:
                df.insert(0, "ARQUIVO_ORIGEM", source_name)

    # ---------- converter datas do C100 (DT_DOC, DT_E_S) se existirem ----------
    if not df_c100_c170.empty:
        for col in ["C100_DT_DOC", "C100_DT_E_S"]:
            if col in df_c100_c170.columns:
                s = (
                    df_c100_c170[col]
                    .astype(str)
                    .str.strip()
                    .str.extract(r"(\d{8})", expand=False)
                )
                dt = pd.to_datetime(s, format="%d%m%Y", errors="coerce")
                df_c100_c170[col] = dt

    return df_0190, df_0200, df_c100_c170


def parse_sped_from_any(data: bytes, filename: str):
    """
    Se for TXT: processa direto.
    Se for ZIP: abre todos os .txt dentro e concatena.
    Retorna: df_0190, df_0200, df_c100_c170
    """
    filename_lower = (filename or "").lower()

    dfs_0190 = []
    dfs_0200 = []
    dfs_c100_c170 = []

    if filename_lower.endswith(".txt"):
        df_0190, df_0200, df_c100_c170 = _parse_efd_icms_ipi_txt(
            data,
            source_name=filename,
        )
        dfs_0190.append(df_0190)
        dfs_0200.append(df_0200)
        dfs_c100_c170.append(df_c100_c170)

    elif filename_lower.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                if not info.filename.lower().endswith(".txt"):
                    continue
                with zf.open(info) as f:
                    txt_bytes = f.read()
                df_0190, df_0200, df_c100_c170 = _parse_efd_icms_ipi_txt(
                    txt_bytes,
                    source_name=info.filename,
                )
                dfs_0190.append(df_0190)
                dfs_0200.append(df_0200)
                dfs_c100_c170.append(df_c100_c170)
    else:
        # tipo não suportado
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    def _concat(dfs):
        dfs = [d for d in dfs if d is not None and not d.empty]
        if not dfs:
            return pd.DataFrame()
        return pd.concat(dfs, ignore_index=True)

    return _concat(dfs_0190), _concat(dfs_0200), _concat(dfs_c100_c170)

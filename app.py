import streamlit as st
import pandas as pd
import io
import os
import zipfile
import tempfile

# Importando suas lógicas existentes e adaptadas
from utils import digits, mask_cnpj, fmt_period
from logic_extrator import processar_extracao_cloud
from logic_resumo import summarize_zipfile_resumo, build_detail_from_zip_resumo, build_items_from_zip_resumo
from logic_sped import parse_sped_from_any
from logic_nfse_split import split_nfse_abrasf, make_zip_bytes
from logic_converter import converter_txt_para_xml_lote

# Configuração da Página
st.set_page_config(page_title="Central de Ferramentas XML", layout="wide", page_icon="📂")

# --- CSS Customizado ---
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { width: 100%; border-radius: 8px; height: 3em; background-color: #007bff; color: white; }
    .stDownloadButton>button { width: 100%; border-radius: 8px; background-color: #28a745; color: white; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE VERIFICAÇÃO DE SENHA ---
def password_entered():
    """Verifica se a senha digitada coincide com a do segredo."""
    if st.session_state["password"] == st.secrets["password"]:
        st.session_state["password_correct"] = True
        del st.session_state["password"]
    else:
        st.session_state["password_correct"] = False

def check_password():
    """Retorna True se o usuário inseriu a senha correta."""
    if "password_correct" not in st.session_state:
        st.text_input("Digite a senha para acessar a Central XML", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Senha incorreta. Tente novamente:", type="password", on_change=password_entered, key="password")
        st.error("😕 Senha inválida")
        return False
    else:
        return True

# --- INÍCIO DO APP PROTEGIDO ---
if check_password():
    st.title("📂 Central de Ferramentas XML")

    # Inicializa o estado dos CNPJs dentro do bloco protegido
    if 'cnpjs' not in st.session_state:
        st.session_state.cnpjs = []

    with st.expander("🏢 Configuração de CNPJs Próprios", expanded=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            novo_cnpj = st.text_input("Adicionar CNPJ ou CPF próprio", placeholder="00.000.000/0000-00")
        with col2:
            st.write("##") 
            if st.button("Adicionar"):
                d = digits(novo_cnpj)
                if d and d not in st.session_state.cnpjs:
                    st.session_state.cnpjs.append(d)
                    st.rerun()
        
        if st.session_state.cnpjs:
            st.write("**Entidades Cadastradas:**")
            chips = [f"`{mask_cnpj(c)}`" for c in st.session_state.cnpjs]
            st.markdown(" ".join(chips))
            if st.button("Limpar Lista", type="secondary"):
                st.session_state.cnpjs = []
                st.rerun()

    # --- ABAS ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Extrator de XML", 
        "Resumo/Análise", 
        "SPED Fiscal", 
        "Separar NFSe",
        "Conversor para XML"
    ])

    # --- ABA 1: EXTRATOR ---
    with tab1:
        st.header("Extrator e Classificador de XML")
        st.info("Extrai arquivos (.zip, .7z) e separa em pastas: Próprios, Terceiros e Outros.")
        
        uploaded_zip = st.file_uploader("Suba o arquivo compactado de origem", type=["zip", "7z"])
        modo_ext = st.radio("Modo de Processamento", ["Juntar Tudo", "Separar pelo Emitente (Classificação)"])
        
        if st.button("🚀 Iniciar Extração"):
            if not uploaded_zip:
                st.error("Selecione um arquivo primeiro.")
            elif modo_ext == "Separar pelo Emitente (Classificação)" and not st.session_state.cnpjs:
                st.error("Para classificar, adicione pelo menos um CNPJ no topo.")
            else:
                with st.spinner("Processando arquivos..."):
                    zip_bytes, logs = processar_extracao_cloud(uploaded_zip, modo_ext, st.session_state.cnpjs)
                    st.success(f"Processamento concluído!")
                    with st.expander("Ver Logs do Processamento"):
                        for log in logs:
                            st.text(log)
                    st.download_button(
                        label="📥 Baixar XMLs Organizados (ZIP)",
                        data=zip_bytes,
                        file_name="XMLs_Organizados.zip",
                        mime="application/zip"
                    )

    # --- ABA 2: RESUMO ---
    with tab2:
        st.header("Resumo e Análise de Itens")
        zip_resumo = st.file_uploader("Selecione o arquivo .zip para análise", type=["zip"], key="resumo_uploader")
        
        if zip_resumo:
            if not st.session_state.cnpjs:
                st.warning("⚠️ Adicione CNPJs próprios no topo para identificar emissões Próprias vs Terceiros.")
            
            own_set = set(st.session_state.cnpjs)
            with zipfile.ZipFile(zip_resumo, 'r') as zf:
                res = summarize_zipfile_resumo(zf, own_set)
                rows, breakdown, total_docs, warns, total_xmls = res[0], res[1], res[2], res[3], res[4]
                st.success(f"Análise concluída: {total_docs} documentos DF-e identificados.")
                st.dataframe(pd.DataFrame(rows), use_container_width=True)
                col_res1, col_res2 = st.columns(2)
                with col_res1:
                    detalhe = build_detail_from_zip_resumo(zf, own_set)
                    df_det = pd.DataFrame(detalhe)
                    st.download_button("📊 Baixar Detalhe (Excel)", df_det.to_csv(index=False).encode('utf-8'), "detalhe_analise.csv")
                with col_res2:
                    itens = build_items_from_zip_resumo(zf, own_set)
                    st.download_button("📦 Baixar Itens (CSV)", pd.DataFrame(itens).to_csv(index=False).encode('utf-8'), "itens_extracao.csv")

    # --- ABA 3: SPED ---
    with tab3:
        st.header("Análise de SPED Fiscal")
        sped_file = st.file_uploader("Selecione o arquivo SPED (.txt, .zip, .docx)", type=["txt", "zip", "docx"])
        if sped_file:
            with st.spinner("Lendo SPED..."):
                df_0190, df_0200, df_c100 = parse_sped_from_any(sped_file.read(), sped_file.name)
                st.write(f"**Registros C100/C170 encontrados:** {len(df_c100)}")
                st.dataframe(df_c100.head(50), use_container_width=True)
                output_sped = io.BytesIO()
                with pd.ExcelWriter(output_sped, engine='xlsxwriter') as writer:
                    if not df_0190.empty: df_0190.to_excel(writer, sheet_name='Unidades_0190', index=False)
                    if not df_0200.empty: df_0200.to_excel(writer, sheet_name='Produtos_0200', index=False)
                    if not df_c100.empty: df_c100.to_excel(writer, sheet_name='Itens_C100_C170', index=False)
                st.download_button("📥 Baixar SPED Convertido (Excel)", output_sped.getvalue(), "sped_analise.xlsx")

    # --- ABA 4: SEPARAR NFSE ---
    with tab4:
        st.header("Desmembrar Lote NFSe (ABRASF)")
        nfse_file = st.file_uploader("Suba o XML ou ZIP com notas em lote", type=["xml", "zip"])
        if st.button("✂️ Desmembrar Notas"):
            if nfse_file:
                partes = split_nfse_abrasf(nfse_file.read())
                if partes:
                    st.success(f"{len(partes)} notas individuais geradas.")
                    st.download_button("📥 Baixar ZIP de Notas", make_zip_bytes(partes), "nfse_desmembradas.zip")
                else:
                    st.error("Não foi possível encontrar múltiplas notas para desmembrar neste arquivo.")

    # --- ABA 5: CONVERSOR ---
    with tab5:
        st.header("Conversor NFSe (TXT/CSV → XML)")
        col_ref1, col_ref2 = st.columns(2)
        with col_ref1:
            ref_file = st.file_uploader("1. Planilha de Referência (De-Para)", type=["xlsx", "xls"])
        with col_ref2:
            txt_to_convert = st.file_uploader("2. Arquivo para converter", type=["txt", "csv", "zip"])

        if st.button("🛠️ Converter para XML"):
            if ref_file and txt_to_convert:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    in_path = os.path.join(tmp_dir, txt_to_convert.name)
                    ref_path = os.path.join(tmp_dir, ref_file.name)
                    out_dir = os.path.join(tmp_dir, "output_xmls")
                    os.makedirs(out_dir)
                    with open(in_path, "wb") as f: f.write(txt_to_convert.getbuffer())
                    with open(ref_path, "wb") as f: f.write(ref_file.getbuffer())
                    with st.spinner("Convertendo..."):
                        res_msg = converter_txt_para_xml_lote(in_path, out_dir, path_ref_custom=ref_path)
                        st.success(res_msg)
                        zip_conv = io.BytesIO()
                        with zipfile.ZipFile(zip_conv, "w") as zf:
                            for root, _, files in os.walk(out_dir):
                                for f in files: zf.write(os.path.join(root, f), arcname=f)
                        st.download_button("📥 Baixar XMLs Gerados", zip_conv.getvalue(), "conversao_nfse.zip")
            else:
                st.error("É necessário subir ambos os arquivos (Referência e Dados).")
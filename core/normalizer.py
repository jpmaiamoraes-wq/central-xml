from schemas.documento_fiscal import DocumentoFiscal
from schemas.nfse import NFSe

def somente_digitos(s: str | None) -> str | None:
    if not s:
        return None
    return "".join(ch for ch in s if ch.isdigit())

def classificar_pt(nfse: NFSe, cnpjs_proprios: set[str]) -> tuple[str|None, str|None]:
    prest = somente_digitos(nfse.prestador_cnpjcpf)
    tom = somente_digitos(nfse.tomador_cnpjcpf)

    if prest and prest in cnpjs_proprios:
        return "P", prest
    if tom and tom in cnpjs_proprios:
        return "T", tom
    # fallback: se quiser, pode resumir por prestador mesmo assim
    return None, prest or tom

def nfse_to_documento(nfse: NFSe, cnpjs_proprios: set[str]) -> DocumentoFiscal:
    papel, cnpj_ref = classificar_pt(nfse, cnpjs_proprios)

    # para resumo mensal: usa competência se tiver, senão data de emissão
    competencia = nfse.competencia or nfse.data_emissao

    return DocumentoFiscal(
        doc_type="NFSE",
        modelo="NFSE",
        numero=nfse.numero,
        serie=nfse.serie,
        chave=None,
        data_emissao=nfse.data_emissao,
        competencia=competencia,
        cnpj_referencia=cnpj_ref,
        papel=papel,
        uf=nfse.prestador_uf or nfse.tomador_uf,
        municipio_ibge=nfse.prestador_mun_ibge or nfse.tomador_mun_ibge,
        valor_total=nfse.valor_servicos,
        valor_iss=nfse.valor_iss,
        origem_layout=nfse.layout,
    )

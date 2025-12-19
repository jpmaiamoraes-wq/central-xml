from dataclasses import dataclass
from typing import Optional
from datetime import date

@dataclass
class DocumentoFiscal:
    doc_type: str                 # NFE | NFCE | CTE | NFSE
    modelo: Optional[str]         # 55 | 65 | 57 | NFSE

    numero: Optional[str]
    serie: Optional[str]
    chave: Optional[str]          # NFSe normalmente não tem

    data_emissao: Optional[date]
    competencia: Optional[date]

    cnpj_referencia: Optional[str]  # quem entra no resumo
    papel: Optional[str]            # P = Próprio | T = Terceiros

    uf: Optional[str]
    municipio_ibge: Optional[str]

    valor_total: Optional[float]
    valor_iss: Optional[float]

    origem_layout: Optional[str]    # ABRASF, PREFEITURA, SEFAZ, etc.

from dataclasses import dataclass
from typing import Optional
from datetime import date

@dataclass
class NFSe:
    # Identificação do documento
    doc_type: str = "NFSE"          # fixo
    layout: Optional[str] = None    # ABRASF_2.01 | PREFEITURA_NFE | OUTRO

    numero: Optional[str] = None
    serie: Optional[str] = None
    codigo_verificacao: Optional[str] = None

    # Datas
    data_emissao: Optional[date] = None
    competencia: Optional[date] = None

    # Prestador
    prestador_cnpjcpf: Optional[str] = None
    prestador_im: Optional[str] = None
    prestador_razao: Optional[str] = None
    prestador_mun_ibge: Optional[str] = None
    prestador_uf: Optional[str] = None

    # Tomador
    tomador_cnpjcpf: Optional[str] = None
    tomador_razao: Optional[str] = None
    tomador_mun_ibge: Optional[str] = None
    tomador_uf: Optional[str] = None

    # Valores
    valor_servicos: Optional[float] = None
    base_calculo: Optional[float] = None
    aliquota_iss: Optional[float] = None
    valor_iss: Optional[float] = None
    iss_retido: Optional[bool] = None

    # Complementos
    discriminacao: Optional[str] = None

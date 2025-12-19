from dataclasses import dataclass
from typing import Optional

@dataclass
class ResultadoProcessamento:
    arquivo: str
    doc_type: Optional[str]

    sucesso: bool
    erro: Optional[str] = None

    duplicado: bool = False
    chave_unica: Optional[str] = None

# utils.py
import os
import re
import sys
import zipfile
import shutil
from datetime import datetime

# ============== PATCH DE SEGURANÇA DO ZIP ==============

import os as _os_chatgpt
import zipfile as _zipfile_chatgpt
import shutil as _shutil_chatgpt

def _safe_extractall_monkey(self, dest, *args, **kwargs):
    base = _os_chatgpt.path.abspath(dest)
    for m in self.infolist():
        target = _os_chatgpt.path.abspath(
            _os_chatgpt.path.normpath(_os_chatgpt.path.join(dest, m.filename))
        )
        if not (target == base or target.startswith(base + _os_chatgpt.sep)):
            # evita Zip Slip
            continue
        if getattr(m, "is_dir", None) and m.is_dir():
            _os_chatgpt.makedirs(target, exist_ok=True)
        else:
            _os_chatgpt.makedirs(_os_chatgpt.path.dirname(target), exist_ok=True)
            with self.open(m) as src, open(target, "wb") as out:
                _shutil_chatgpt.copyfileobj(src, out)

# Aplica o patch uma vez
if not getattr(_zipfile_chatgpt.ZipFile, "_chatgpt_patched_extractall", False):
    try:
        _zipfile_chatgpt.ZipFile._unsafe_extractall = _zipfile_chatgpt.ZipFile.extractall
    except Exception:
        pass
    _zipfile_chatgpt.ZipFile.extractall = _safe_extractall_monkey
    _zipfile_chatgpt.ZipFile._chatgpt_patched_extractall = True


def clean_dir(path: str):
    """Apaga tudo dentro de um diretório (sem apagar o diretório em si)."""
    try:
        if not path or not _os_chatgpt.path.isdir(path):
            return
        for _f in _os_chatgpt.listdir(path):
            _fp = _os_chatgpt.path.join(path, _f)
            if _os_chatgpt.path.isfile(_fp):
                try:
                    _os_chatgpt.remove(_fp)
                except Exception:
                    pass
            elif _os_chatgpt.path.isdir(_fp):
                try:
                    _shutil_chatgpt.rmtree(_fp, ignore_errors=True)
                except Exception:
                    pass
    except Exception:
        pass


# ============== CONFIG / HELPERS GLOBAIS ==============

def base_path() -> str:
    """
    Retorna o caminho base para assets (funciona com PyInstaller).
    """
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


NFE_NS_GLOBAL = "http://www.portalfiscal.inf.br/nfe"
CTE_NS_GLOBAL = "http://www.portalfiscal.inf.br/cte"

NS_MAP_GLOBAL = {"nfe": NFE_NS_GLOBAL}
ACCEPTED_MODELS_GLOBAL = {"55", "65", "57", "NFSE"}  # NF-e, NFC-e, CT-e


def digits(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"\D", "", str(s))


def mask_cnpj(d: str) -> str:
    """
    Formata CNPJ ou CPF:
      - CNPJ: 00.000.000/0000-00
      - CPF : 000.000.000-00
    Outros tamanhos: retorna só os dígitos.
    """
    d = digits(d or "")
    if len(d) == 14:
        return f"{d[0:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}"
    if len(d) == 11:
        return f"{d[0:3]}.{d[3:6]}.{d[6:9]}-{d[9:11]}"
    return d


def fmt_period(p):
    if not p:
        return "—"
    a, m = p
    return f"{m:02d}/{a}"


def log_message(message_list, message: str):
    """
    Adiciona mensagem à lista de log (com timestamp) e imprime no stdout.
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    print(log_entry, file=sys.stdout)
    message_list.append(log_entry)
    return message_list

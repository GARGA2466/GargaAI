# =====================================================================
#   utils.py - Utilidades de texto usadas por vários arquivos
# =====================================================================
import re
import unicodedata


def normalizar(texto):
    """Deixa o texto 'padronizado' para comparar: minúsculo, sem acentos
    e sem pontuação. Ex: 'Fechar ABA!' vira 'fechar aba'."""
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return texto.strip()


def limpar_resposta(texto):
    """Tira da resposta da IA o que não deve ser falado: blocos de
    'raciocínio' (<think>...</think>) e asteriscos de markdown."""
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL)
    return texto.replace("*", "").strip()

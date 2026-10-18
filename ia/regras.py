# =====================================================================
#   regras.py - Lê o regras.txt (comandos instantâneos, sem IA)
# =====================================================================
import os
import re
import time
import subprocess

import pyautogui

from . import modos
from .config import CAMINHO_REGRAS, rotulo
from .utils import normalizar
from .voz import falar
from .ferramentas import (focar_ou_abrir, focar_janela, confirmar, abrir_app,
                          definir_volume, atalho, minimizar_app, maximizar_app,
                          executar_clique_video, focar_navegador,
                          minimizar_navegador, maximizar_navegador,
                          abrir_navegador)

LIMITE_NUMERO = 100   # o {n} do regras.txt só aceita números de 0 a 100


def _montar_padrao(gatilho):
    """Transforma um gatilho do regras.txt num padrão de busca.
    O pedaço {n} vira "qualquer número" (ex: 'volume em {n}' casa com
    'volume em 35'). Tudo é comparado por PALAVRAS INTEIRAS."""
    partes = gatilho.split("{n}", 1)
    palavras = normalizar(partes[0]).split()
    if len(partes) == 2:
        palavras.append(r"(\d+)")
        palavras += normalizar(partes[1]).split()
    # re.escape protege símbolos; o grupo (\d+) é o único trecho "livre"
    corpo = " ".join(p if p == r"(\d+)" else re.escape(p) for p in palavras)
    padrao = rf"(?<!\w){corpo}(?!\w)"
    texto = normalizar(partes[0])
    if len(partes) == 2:
        texto += " {n} " + normalizar(partes[1])
    return re.compile(padrao), texto


def _interpretar_linhas(linhas):
    """Transforma linhas no formato 'gatilho1, gatilho2 = ação' em regras.
    Linhas vazias ou começando com # são ignoradas.

    Gatilhos especiais:
      !gatilho   -> "exato": só vale se a frase inteira for exatamente aquilo
      {n}        -> qualquer número (ex: 'volume em {n}'), que também pode
                    ser usado na ação (ex: definir_volume({n}))
    Cada gatilho vira uma tupla (texto, exato, padrão)."""
    regras = []
    for linha in linhas:
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        gatilhos, acao = linha.split("=", 1)   # divide só no 1º "="
        lista = []
        for g in gatilhos.split(","):
            g = g.strip()
            if not g:
                continue
            exato = g.startswith("!")
            padrao, texto = _montar_padrao(g.lstrip("!"))
            if texto.strip():
                lista.append((texto.strip(), exato, padrao))
        regras.append((lista, acao.strip()))
    return regras


# ---------------------------------------------------------------------
# REGRAS EMBUTIDAS: já vêm prontas, sem precisar mexer no regras.txt.
# "clica no primeiro/segundo/terceiro... vídeo" e "clica no vídeo 3".
# ---------------------------------------------------------------------
_ORDINAIS_REGRA = [("primeiro", 1), ("segundo", 2), ("terceiro", 3), ("quarto", 4),
                   ("quinto", 5), ("sexto", 6), ("setimo", 7), ("oitavo", 8),
                   ("nono", 9), ("decimo", 10)]
_VERBOS_VIDEO = ["clica no", "clique no", "clicar no", "abre o", "abrir o", "abra o",
                 "toca o", "tocar o", "coloca o", "colocar o", "da play no",
                 "dar play no", "seleciona o", "selecionar o"]


def _linhas_embutidas():
    linhas = []
    for palavra, numero in _ORDINAIS_REGRA:
        gatilhos = [f"{verbo} {palavra} video" for verbo in _VERBOS_VIDEO]
        linhas.append(", ".join(gatilhos) + f" = clicar_video({numero})")
    numericos = ([f"{verbo} video {{n}}" for verbo in _VERBOS_VIDEO] +
                 [f"{verbo} {{n}} video" for verbo in _VERBOS_VIDEO])
    linhas.append(", ".join(numericos) + " = clicar_video({n})")
    return linhas


_REGRAS_EMBUTIDAS = _interpretar_linhas(_linhas_embutidas())


def carregar_regras():
    """Lê o regras.txt (a cada comando, então você pode editá-lo com o programa
    aberto) e junta com as regras embutidas acima."""
    regras = []
    if os.path.exists(CAMINHO_REGRAS):
        with open(CAMINHO_REGRAS, "r", encoding="utf-8") as arquivo:
            regras = _interpretar_linhas(arquivo)
    return regras + _REGRAS_EMBUTIDAS


def buscar_regra(comando):
    """Procura no regras.txt uma regra que combine com o que foi dito.
    Devolve o código da ação (com o {n} já trocado pelo número falado).
    Proteções contra disparos errados:
      - compara PALAVRAS INTEIRAS ('play' não dispara dentro de 'display')
      - gatilho com ! só vale se a frase for EXATAMENTE ele
      - {n} só aceita números de 0 a 100
      - se várias regras combinarem, vence o gatilho mais longo
        ('minimizar discord' ganha de 'minimizar')"""
    melhor_acao, melhor_tamanho = None, 0
    for gatilhos, acao in carregar_regras():
        for texto, exato, padrao in gatilhos:
            if len(texto) <= melhor_tamanho:
                continue
            achou = padrao.fullmatch(comando) if exato else padrao.search(comando)
            if not achou:
                continue
            acao_final = acao
            if padrao.groups:                      # o gatilho tem {n}
                numero = int(achou.group(1))
                if numero > LIMITE_NUMERO:
                    continue                       # número fora do limite
                acao_final = acao.replace("{n}", str(numero))
            melhor_acao, melhor_tamanho = acao_final, len(texto)
    return melhor_acao


def _com_aviso(funcao):
    """Faz uma ferramenta mostrar no terminal o texto que ela devolve
    (a IA lê esse texto, mas nas regras ninguém leria)."""
    def envelope(*args, **kwargs):
        resultado = funcao(*args, **kwargs)
        if isinstance(resultado, str):
            print(f"{rotulo()}: {resultado}")
        return resultado
    return envelope


def _clicar_video_regra(posicao):
    """'Clica no segundo vídeo': mostra o resultado no chat e, se der problema
    (navegador sem a porta de depuração, por exemplo), avisa em voz alta numa frase
    curta, sem derrubar o programa."""
    deu_certo, mensagem, fala = executar_clique_video(posicao)
    print(f"{rotulo()}: {mensagem}")
    if not deu_certo and fala and modos.falar_permitido():
        falar(fala)


def _no_navegador(teclas, navegador=None):
    """Traz o navegador (o do config.json, ou o que você nomear) para a frente
    e, SÓ se ele realmente ficou na frente, manda o atalho.
    Ex: no_navegador('ctrl+w')  ou  no_navegador('ctrl+w', 'chrome')."""
    if focar_navegador(navegador):
        print(f"{rotulo()}: {atalho(teclas)}")


def _confirmar_regra(pergunta, codigo):
    """Versão do 'confirmar' para usar dentro do regras.txt: o código só é
    executado depois que você responder "sim"."""
    confirmar(pergunta, lambda: executar_regra(codigo))


def executar_regra(acao):
    """Executa o código de uma regra do regras.txt.
    Aqui o exec() é aceitável porque o texto vem do SEU arquivo, escrito por
    você. Nunca vem da IA. As variáveis abaixo ficam disponíveis para o
    código das regras usar."""
    escopo = {
        "pyautogui": pyautogui,
        "subprocess": subprocess,
        "os": os,
        "time": time,
        # Ações nomeadas (as mesmas que a IA também usa)
        "abrir_app": _com_aviso(abrir_app),            # abre ou foca app/site
        "definir_volume": _com_aviso(definir_volume),  # volume exato de 0 a 100
        "clicar_video": _clicar_video_regra,           # clica no Nº vídeo do YouTube
        # Ações exclusivas das regras
        "no_navegador": _no_navegador,      # foca o navegador e manda um atalho
        "no_opera": _no_navegador,          # nome antigo (vale para o navegador configurado)
        "focar_navegador": focar_navegador,
        "minimizar_navegador": minimizar_navegador,
        "maximizar_navegador": maximizar_navegador,
        "abrir_navegador": abrir_navegador,
        "minimizar_app": minimizar_app,     # minimiza janelas pelo nome
        "maximizar_app": maximizar_app,     # maximiza janelas pelo nome
        "focar_janela": focar_janela,       # foca e confere (não abre nada)
        "focar_ou_abrir": focar_ou_abrir,   # foca o app ou abre se não existir
        "confirmar": _confirmar_regra,      # pergunta e só executa com "sim"
    }
    try:
        print(f"[Ação Direta]: {acao}")
        exec(acao, escopo)
    except Exception as erro:
        print(f"{rotulo()}: erro na regra: {erro}")

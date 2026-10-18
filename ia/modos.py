# =====================================================================
#   modos.py - Modo Trabalho x Modo Conversa
# =====================================================================
#   MODO TRABALHO: foco total em comandos rápidos. A IA responde com uma
#     palavrinha ("Feito!", "Pronto!") ou fica em silêncio, sem puxar assunto.
#     Ideal para gameplay.
#   MODO CONVERSA: a IA é mais amigável e conversa de forma natural, além de
#     executar os comandos normalmente.
#
# Troca por voz: "modo trabalho" / "modo conversa". O modo escolhido fica
# salvo no config.json (chave "modo_padrao"), então vale na próxima vez.
import re
import random
import threading

from . import config

TRABALHO = "trabalho"
CONVERSA = "conversa"
EMOJIS = {TRABALHO: "💼", CONVERSA: "💬"}

# Instruções que são somadas ao prompt da IA conforme o modo
PROMPTS = {
    TRABALHO: (
        "MODO TRABALHO: o usuário está ocupado (por exemplo, jogando). Execute "
        "o pedido com as ferramentas e responda com NO MÁXIMO 3 palavras, como "
        "'Feito!' ou 'Pronto!'. Não puxe assunto, não faça perguntas e não "
        "explique nada. Se for só uma pergunta simples, responda numa frase de "
        "até 6 palavras."),
    CONVERSA: (
        "MODO CONVERSA: seja amigável e natural, como numa conversa entre "
        "amigos. Você pode responder com até 4 frases curtas, comentar, "
        "perguntar algo de volta e manter o diálogo. Quando o usuário pedir uma "
        "ação, continue usando as ferramentas."),
}

MAX_PALAVRAS_TRABALHO = 8      # resposta a uma pergunta no modo trabalho
LIMITE_TOKENS_TRABALHO = 80    # a IA nem "pensa" muito no modo trabalho (mais rápido)

_modo = config.MODO_PADRAO
_trava = threading.Lock()


def modo_atual():
    with _trava:
        return _modo


def rotulo_do_modo(modo=None):
    """O texto do indicador, ex: 'Trabalho 💼' ou 'Conversa 💬'."""
    modo = modo or modo_atual()
    return f"{config.T['modo_' + modo]} {EMOJIS[modo]}"


def prompt_do_modo(modo=None):
    return PROMPTS[modo or modo_atual()]


def opcoes_do_modo(modo=None):
    """Opções extras para o Ollama. No modo trabalho limita o tamanho da resposta."""
    if (modo or modo_atual()) == TRABALHO:
        return {"options": {"num_predict": LIMITE_TOKENS_TRABALHO}}
    return {}


def falar_permitido():
    """False no modo trabalho silencioso (nada é falado, só mostrado no chat)."""
    return not (modo_atual() == TRABALHO and config.TRABALHO_SILENCIOSO)


def aviso_do_modo(modo):
    """O que falar ao trocar de modo (None = não falar nada)."""
    if modo == TRABALHO and config.TRABALHO_SILENCIOSO:
        return None
    return config.T["modo_" + modo + "_ativado"]


def definir_modo(novo, salvar=True):
    """Troca de modo. Se 'lembrar_modo' estiver ligado no config.json, o modo
    escolhido também é salvo como padrão. Devolve True se o modo mudou."""
    global _modo
    with _trava:
        mudou = novo != _modo
        _modo = novo
    if salvar and config.LEMBRAR_MODO:
        config.salvar_no_config("modo_padrao", novo)
    print(f"{config.rotulo()}: Modo {rotulo_do_modo(novo)} ativado.")
    return mudou


def resposta_de_trabalho(texto, usou_ferramenta):
    """O que falar no modo trabalho: nada (se silencioso), uma palavrinha depois
    de uma ação ('Feito!'), ou só o começo curto da resposta a uma pergunta."""
    if config.TRABALHO_SILENCIOSO:
        return ""
    if usou_ferramenta:
        return random.choice((config.T["feito"], config.T["feito2"]))
    if not texto:
        return ""
    primeira = re.split(r"(?<=[.!?])\s+", texto.strip(), maxsplit=1)[0]
    palavras = primeira.split()
    if len(palavras) > MAX_PALAVRAS_TRABALHO:
        primeira = " ".join(palavras[:MAX_PALAVRAS_TRABALHO]).rstrip(",;:.") + "."
    return primeira


# ---------------------------------------------------------------------
# COMANDO DE VOZ: só vale se a frase for EXATAMENTE o pedido de troca
# ("modo trabalho", "ativar modo conversa"...), pra não disparar no meio de
# uma conversa normal.
# ---------------------------------------------------------------------
_PADRAO_PT = re.compile(
    r"^(?:(?:ativar|ativa|entrar no|entra no|muda para|mudar para|passa para|"
    r"passar para|coloca no|colocar no|volta para|voltar para|vai para|ir para) )?"
    r"modo (?:de )?(trabalho|conversa)$")
_PADRAO_EN = re.compile(
    r"^(?:(?:switch to|enter|turn on|activate) )?(work|conversation|chat) mode$")


def reconhecer_comando_modo(comando):
    """Devolve 'trabalho' ou 'conversa' se a frase (já normalizada) for um
    pedido de troca de modo; senão devolve None."""
    achou = _PADRAO_PT.match(comando)
    if achou:
        return achou.group(1)
    achou = _PADRAO_EN.match(comando)
    if achou:
        return TRABALHO if achou.group(1) == "work" else CONVERSA
    return None

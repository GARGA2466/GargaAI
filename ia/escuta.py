# =====================================================================
#   escuta.py - Modos de escuta: palavra de ativação e "não perturbe"
# =====================================================================
#   1) PALAVRA DE ATIVAÇÃO: só reage ao que vem depois do nome (ou de uma
#      variação do nome que o Google costuma entender errado).
#   2) JANELA DE ESCUTA: se você disser SÓ o nome ("Fuyumi"), ela abre uma
#      janelinha de alguns segundos e o seu próximo pedido vale sem o nome.
#   3) TECLA LIGA/DESLIGA: um toque liga, outro desliga o modo "não perturbe"
#      (ideal para call e gravação). Desligada, ela ignora TUDO.
import time

from . import config
from .voz import pausada, fila_audio
from .cerebro import cancelar_tudo

PREFIXOS = ("ei", "oi", "ola", "hey", "hi")    # "ei Fuyumi", "oi Fuyumi"...


# ---------------------------------------------------------------------
# 1) PALAVRA DE ATIVAÇÃO
# ---------------------------------------------------------------------
def _nomes_aceitos():
    """O nome principal + as variações, cada um como lista de palavras.
    Os mais longos vêm primeiro (assim 'fu yumi' ganha de 'fu')."""
    nomes = [config.PALAVRA_ATIVACAO] + list(config.VARIACOES_PALAVRA)
    listas = [n.split() for n in nomes if n.strip()]
    return sorted(listas, key=len, reverse=True)


def tirar_palavra_ativacao(comando):
    """Se o comando COMEÇA com o nome (ou uma variação), devolve o resto, que
    é o pedido de verdade. Devolve "" se a pessoa disse só o nome, e None se
    o comando não começa com o nome (ou seja: não era pra ela).
    Se nenhum nome estiver configurado, devolve o comando sem mexer."""
    if not config.PALAVRA_ATIVACAO:
        return comando

    palavras = comando.split()
    if palavras and palavras[0] in PREFIXOS:
        palavras = palavras[1:]

    for nome in _nomes_aceitos():
        if palavras[:len(nome)] == nome:
            return " ".join(palavras[len(nome):]).strip()
    return None


# ---------------------------------------------------------------------
# 2) JANELA DE ESCUTA (depois de dizer só o nome)
# ---------------------------------------------------------------------
_janela_ate = 0.0


def abrir_janela():
    """Abre a janelinha: o próximo pedido vale mesmo sem dizer o nome."""
    global _janela_ate
    _janela_ate = time.time() + config.JANELA_ESCUTA


def fechar_janela():
    global _janela_ate
    _janela_ate = 0.0


def janela_esta_aberta():
    """True se a janelinha de escuta está aberta (sem fechar ela)."""
    return time.time() <= _janela_ate


def consumir_janela():
    """True se a janelinha estava aberta (e a fecha: ela vale uma vez só)."""
    aberta = time.time() <= _janela_ate
    fechar_janela()
    return aberta


# ---------------------------------------------------------------------
# 3) TECLA LIGA/DESLIGA ("NÃO PERTURBE")
# ---------------------------------------------------------------------
_ultimo_toque = 0.0


def _bipe(agudo):
    """Um bipe curto avisa o estado sem precisar falar (falar atrapalharia
    uma call). Agudo = ligou, grave = desligou. Só funciona no Windows."""
    try:
        import winsound
        winsound.Beep(1000 if agudo else 400, 150 if agudo else 250)
    except Exception:
        pass


def desligar_escuta():
    pausada.set()
    fechar_janela()
    while not fila_audio.empty():          # joga fora o que estava na fila
        try:
            fila_audio.get_nowait()
        except Exception:
            break
    cancelar_tudo()                        # para de falar e de pensar
    print(f"{config.rotulo()}: 🔇 {config.T['escuta_desligada']}")
    _bipe(agudo=False)


def ligar_escuta():
    pausada.clear()
    print(f"{config.rotulo()}: 🎙️ {config.T['escuta_ligada']}")
    _bipe(agudo=True)


def alternar_escuta():
    """Chamada quando você aperta a tecla. O intervalo mínimo entre dois
    toques evita liga-desliga duplo sem querer."""
    global _ultimo_toque
    agora = time.time()
    if agora - _ultimo_toque < 0.4:
        return
    _ultimo_toque = agora
    if pausada.is_set():
        ligar_escuta()
    else:
        desligar_escuta()


def iniciar_tecla():
    """Registra a tecla do config.json. Devolve True se ficou ativa.
    Nunca derruba o programa: se não der certo, avisa e segue sem a tecla."""
    tecla = config.TECLA_ESCUTA
    if not tecla:
        print(f"{config.rotulo()}: tecla liga/desliga desativada (tecla_escuta vazia).")
        return False
    try:
        import keyboard
        # trigger_on_release: age ao SOLTAR a tecla, assim segurar não repete
        keyboard.add_hotkey(tecla, alternar_escuta, trigger_on_release=True)
        return True
    except Exception as erro:
        print(f"{config.rotulo()}: não consegui ativar a tecla '{tecla}' ({erro}). "
              "Sigo sem a tecla liga/desliga.")
        return False


# ---------------------------------------------------------------------
# 4) TECLA DE FORMATAR (apaga o nome e as configurações)
# ---------------------------------------------------------------------
# Para ninguém formatar sem querer: o 1º toque só AVISA, e o 2º toque (até
# 5 segundos depois) é que confirma.
TEMPO_PARA_CONFIRMAR = 5      # segundos entre os dois toques
INTERVALO_MINIMO = 0.6        # toques colados demais não contam como confirmação
_armado_em = 0.0


def apertou_formatar(ao_confirmar):
    """Chamada a cada vez que a tecla de formatar é apertada."""
    global _armado_em
    agora = time.time()
    if _armado_em and agora - _armado_em > TEMPO_PARA_CONFIRMAR:
        _armado_em = 0.0                       # passou do tempo: recomeça
    if _armado_em == 0.0:
        _armado_em = agora
        print(f"{config.rotulo()}: ⚠️ Aperte {config.TECLA_FORMATAR.upper()} de NOVO em "
              f"{TEMPO_PARA_CONFIRMAR} segundos para FORMATAR o assistente.")
        _bipe(agudo=False)
        return
    if agora - _armado_em < INTERVALO_MINIMO:
        return                                 # toque colado: ignora
    _armado_em = 0.0
    ao_confirmar()


def iniciar_tecla_formatar(ao_confirmar):
    """Registra a tecla de formatar. 'ao_confirmar' é o que acontece depois do
    segundo toque. Devolve True se a tecla ficou ativa."""
    tecla = config.TECLA_FORMATAR
    if not tecla:
        return False
    try:
        import keyboard
        keyboard.add_hotkey(tecla, lambda: apertou_formatar(ao_confirmar),
                            trigger_on_release=True)
        return True
    except Exception as erro:
        print(f"{config.rotulo()}: não consegui ativar a tecla de formatar '{tecla}' "
              f"({erro}).")
        return False

# =====================================================================
#   voz.py - Ouvir (microfone) e falar (voz do robô)
# =====================================================================
import math
import time
import array
import queue
import threading

import pyttsx3                       # voz sintetizada do Windows (o robô falando)
import speech_recognition as sr      # transforma sua voz em texto

from .config import T, rotulo

# Estado compartilhado da voz
reconhecedor = sr.Recognizer()       # o "ouvido" do programa
fila_audio = queue.Queue()           # áudios captados esperando tradução
fila_fala = queue.Queue()            # frases esperando para serem faladas
falando = threading.Event()          # "ligado" enquanto o robô fala
parar_fala = threading.Event()       # "ligado" = corte a frase que está sendo dita
pausada = threading.Event()          # "ligado" = modo não perturbe: ignora tudo

# Enquanto o robô fala, só guardamos áudios CURTOS (candidatos a "calma",
# "para tudo"). Áudios longos nessa hora são, quase sempre, a própria voz
# dele voltando pelo microfone, então são descartados.
DURACAO_MAX_CANCELAR = 2.0           # segundos


# ---------------------------------------------------------------------
# MEDIDOR DE VOLUME DO MICROFONE (para as ondas verdes da janela)
# ---------------------------------------------------------------------
# A biblioteca de reconhecimento só avisa quando você TERMINA de falar
# (função ao_ouvir). Para a janela saber que o microfone está captando som
# AGORA, medimos o volume de cada pedacinho de áudio que passa por ele.
# "Captando" = volume acima do limite que o próprio reconhecedor usa para
# decidir que alguém começou a falar.
TEMPO_SEGURA_SOM = 0.35      # a onda continua mexendo um instante depois do último som
nivel_mic = 0.0              # intensidade do último som (0.3 a 1.0)
_ultimo_som = 0.0            # hora do último pedacinho de áudio acima do limite


def _medir_nivel(dados):
    """Recebe um pedaço de áudio cru (16 bits) e anota se tem som."""
    global nivel_mic, _ultimo_som
    tamanho = len(dados) // 2 * 2
    if tamanho == 0:
        return
    amostras = array.array("h")
    amostras.frombytes(dados[:tamanho])
    volume = math.sqrt(sum(a * a for a in amostras) / len(amostras))
    limite = max(float(reconhecedor.energy_threshold), 1.0)
    if volume > limite:
        _ultimo_som = time.time()
        nivel_mic = min(1.0, 0.3 + (volume - limite) / (limite * 3))


def mic_captando():
    """True se o microfone captou som agora há pouco."""
    return time.time() - _ultimo_som < TEMPO_SEGURA_SOM


def nivel_atual():
    """Intensidade do som neste momento (0 se estiver em silêncio)."""
    return nivel_mic if mic_captando() else 0.0


class _FluxoMedidor:
    """Embrulha o fluxo de áudio do microfone: tudo passa normalmente para o
    reconhecimento, mas antes mede o volume. Se a medição falhar, ignora."""

    def __init__(self, fluxo):
        self._fluxo = fluxo

    def read(self, tamanho):
        dados = self._fluxo.read(tamanho)
        try:
            _medir_nivel(dados)
        except Exception:
            pass
        return dados

    def __getattr__(self, nome):          # close() e o resto passam direto
        return getattr(self._fluxo, nome)


class MicrofoneComNivel(sr.Microphone):
    """O mesmo microfone de sempre, só que medindo o volume do que ele capta."""

    def __enter__(self):
        super().__enter__()
        fluxo = getattr(self, "stream", None)
        if fluxo is not None:
            self.stream = _FluxoMedidor(fluxo)
        return self


def falar(texto):
    """Coloca uma frase na fila de fala. Retorna na hora, sem travar nada.
    Quem realmente fala é a função trabalhador_fala, logo abaixo."""
    print(f"{rotulo()}: {texto}")
    fila_fala.put(texto)


def trabalhador_fala():
    """Roda em uma thread própria, pegando frases da fila e falando uma
    por uma. Usar UMA thread só evita os travamentos do pyttsx3, que não
    gosta de ser chamado de vários lugares ao mesmo tempo."""
    motor = pyttsx3.init()
    motor.setProperty("rate", 190)

    # Tenta escolher uma voz do Windows que combine com o idioma
    for voz in motor.getProperty("voices"):
        descricao = f"{voz.id} {voz.name}".lower()
        if any(p in descricao for p in T["voz_busca"]):
            motor.setProperty("voice", voz.id)
            break

    def ao_comecar_palavra(name, location, length):
        """O motor de voz chama esta função a cada palavra que vai falar.
        Se alguém pediu para parar, cortamos a frase aqui. É o jeito mais
        seguro de interromper o pyttsx3 (de dentro da própria thread dele)."""
        if parar_fala.is_set():
            try:
                motor.stop()
            except Exception as erro:
                print(f"{rotulo()}: não consegui interromper a voz: {erro}")

    motor.connect("started-word", ao_comecar_palavra)

    while True:
        texto = fila_fala.get()      # espera chegar uma frase
        parar_fala.clear()           # frase nova: começa sem ordem de parar
        falando.set()                # avisa: "estou falando"
        try:
            motor.say(texto)
            motor.runAndWait()
        except Exception as erro:
            print(f"{rotulo()}: erro na voz: {erro}")
        finally:
            fila_fala.task_done()
            if fila_fala.empty():
                time.sleep(0.4)      # espera o eco da voz sumir da sala
                falando.clear()


def duracao_audio(audio):
    """Quantos segundos tem um áudio captado pelo microfone."""
    return len(audio.frame_data) / (audio.sample_rate * audio.sample_width)


def ao_ouvir(_reconhecedor, audio):
    """Chamada automaticamente toda vez que o microfone capta uma frase.
    Ela só guarda o áudio na fila e sai na hora, assim a escuta continua
    livre mesmo enquanto o programa traduz ou executa outra coisa.

    Se o robô estiver falando, só guardamos áudios curtos e os marcamos como
    'durante_fala'. Quem lê a fila só aceita desses áudios um pedido de
    cancelamento. Todo o resto é ignorado (o robô não obedece à própria voz)."""
    if pausada.is_set():
        return      # modo não perturbe: o áudio nem é guardado (nem vai pro Google)
    durante_fala = falando.is_set()
    if durante_fala and duracao_audio(audio) > DURACAO_MAX_CANCELAR:
        return
    fila_audio.put((audio, durante_fala))
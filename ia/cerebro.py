# =====================================================================
#   cerebro.py - Conversa com a IA (Ollama) e uso das ferramentas
# =====================================================================
import time
import queue
import atexit
import threading
import subprocess
from collections import deque

import ollama                        # conversa com a IA local

from .config import (MODELO, PROMPT_SISTEMA, T, MAX_PASSOS_IA,
                     MEMORIA_MENSAGENS, PALAVRAS_CANCELAR, FRASES_CANCELAR,
                     PALAVRAS_AUXILIARES_CANCELAR, MANTER_MODELO, rotulo)
from . import memoria, modos
from .utils import limpar_resposta
from .voz import falar, fila_fala, falando, parar_fala
from .ferramentas import FERRAMENTAS, executar_ferramenta

memoria = deque(maxlen=MEMORIA_MENSAGENS)      # conversa recente com a IA
cancelar_atual = threading.Event()             # sinal de cancelamento da tarefa atual

# Lista das tarefas da IA que estão rodando agora (cada uma representada pelo
# seu sinal de cancelamento). Serve para saber se "tem algo pra cancelar".
_tarefas_ativas = set()
_trava = threading.Lock()


def processar_com_ia(pedido, cancelar):
    """Envia o pedido para a IA. Roda em uma thread separada para o
    microfone continuar escutando enquanto a IA pensa.

    O fluxo é um pequeno vaivém:
      1. mandamos o pedido + a lista de ferramentas
      2. a IA responde com texto OU pede para usar uma ferramenta
      3. se pediu ferramenta, executamos e devolvemos o resultado
      4. repete até a IA dar a resposta final (máx. MAX_PASSOS_IA vezes)

    'cancelar' é um sinal exclusivo DESTA tarefa. Não dá para interromper o
    Ollama no meio do cálculo, mas quando ele termina, se o sinal estiver
    ligado, jogamos o resultado fora e não executamos nada."""
    modo = modos.modo_atual()              # o modo vale para esta tarefa inteira
    mensagens = [{"role": "system",
                  "content": (f"{PROMPT_SISTEMA} {modos.prompt_do_modo(modo)} "
                              f"{memoria.bloco_para_prompt()} "
                              f"{T['instrucao_idioma']}")}]
    mensagens += list(memoria)                               # conversa recente
    mensagens.append({"role": "user", "content": pedido})    # pedido atual

    usou_ferramenta = False
    try:
        for _ in range(MAX_PASSOS_IA):
            resposta = ollama.chat(model=MODELO, messages=mensagens,
                                   tools=list(FERRAMENTAS.values()),
                                   keep_alive=MANTER_MODELO,
                                   **modos.opcoes_do_modo(modo))
            if cancelar.is_set():
                print(f"{rotulo()}: {T['cancelado']} 🛑")
                return

            msg = resposta.message

            # A IA não pediu ferramenta: é a resposta final. Fala e termina.
            if not msg.tool_calls:
                texto = limpar_resposta(msg.content or "")
                if modo == modos.TRABALHO:
                    # Modo trabalho: só uma palavrinha ("Feito!") ou silêncio
                    texto = modos.resposta_de_trabalho(texto, usou_ferramenta)
                    if not texto and usou_ferramenta:
                        print(f"{rotulo()}: {T['feito']} (modo trabalho, sem fala)")
                elif not texto and usou_ferramenta:
                    texto = T["feito"]
                memoria.append({"role": "user", "content": pedido})
                memoria.append({"role": "assistant",
                                "content": texto or T["feito"]})
                if texto:
                    falar(texto)
                return

            # A IA pediu ferramentas: executa cada uma e devolve o resultado
            mensagens.append(msg)
            for chamada in msg.tool_calls:
                if cancelar.is_set():
                    print(f"{rotulo()}: {T['cancelado']} 🛑")
                    return
                resultado = executar_ferramenta(chamada.function.name,
                                                chamada.function.arguments)
                usou_ferramenta = True
                mensagens.append({"role": "tool",
                                  "tool_name": chamada.function.name,
                                  "content": resultado})

        print(f"{rotulo()}: A IA usou ferramentas demais sem concluir. Parei.")

    except ConnectionError:
        print(f"{rotulo()}: {T['sem_ollama']}")
    except ollama.ResponseError as erro:
        # Ex: modelo não instalado, ou modelo sem suporte a ferramentas
        print(f"{rotulo()}: erro do Ollama: {erro.error}")
    except Exception as erro:
        print(f"{rotulo()}: erro inesperado na IA: {erro}")


_processo_ollama = None      # só existe se FOMOS NÓS que ligamos o Ollama


def garantir_ollama():
    """Se o Ollama ainda não estiver rodando, liga ele ESCONDIDO (sem janela
    preta). Se já estiver rodando (por exemplo, aberto por você), não mexe."""
    global _processo_ollama
    try:
        ollama.list()
        return True                          # já está rodando
    except Exception:
        pass
    try:
        _processo_ollama = subprocess.Popen(
            ["ollama", "serve"], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        atexit.register(desligar_ollama)
        print(f"{rotulo()}: Ligando o Ollama (em segundo plano)...")
        return True
    except Exception as erro:
        print(f"{rotulo()}: não consegui ligar o Ollama sozinho ({erro}). "
              "Abra o Ollama e tente de novo.")
        return False


def desligar_ollama():
    """Ao fechar o GargaAI, desliga o Ollama SÓ se foi ele que ligou
    (assim a memória volta pra você, por exemplo, para jogar)."""
    global _processo_ollama
    if _processo_ollama is not None and _processo_ollama.poll() is None:
        try:
            _processo_ollama.terminate()
        except Exception:
            pass
    _processo_ollama = None


def esperar_ollama(tempo_max=90):
    """Espera o Ollama (o programa que roda a IA) ficar pronto para
    responder. Devolve True se ficou pronto e False se passou do tempo."""
    limite = time.time() + tempo_max
    avisou = False
    while time.time() < limite:
        try:
            ollama.list()           # só pergunta quais modelos existem
            return True
        except Exception:
            if not avisou:
                print(f"{rotulo()}: Esperando o Ollama ficar pronto...")
                avisou = True
            time.sleep(1)
    return False


def preparar_ia():
    """Roda em segundo plano assim que o programa liga: espera o Ollama e
    já carrega o modelo na memória. Assim o primeiro pedido pra IA não
    demora quase 30 segundos. Enquanto isso, os comandos do regras.txt já
    funcionam normalmente."""
    garantir_ollama()
    if not esperar_ollama():
        print(f"{rotulo()}: {T['sem_ollama']}")
        return
    print(f"{rotulo()}: Ollama pronto. Carregando o modelo {MODELO}...")
    try:
        # Um pedido com texto vazio só carrega o modelo, sem gerar resposta
        ollama.generate(model=MODELO, prompt="", keep_alive=MANTER_MODELO)
        print(f"{rotulo()}: Modelo carregado. A IA está pronta!")
    except ollama.ResponseError as erro:
        # Ex: modelo não instalado (rode: ollama pull qwen2.5:7b)
        print(f"{rotulo()}: não consegui carregar o modelo: {erro.error}")
    except Exception as erro:
        print(f"{rotulo()}: não consegui carregar o modelo: {erro}")


def _rodar_tarefa(pedido, cancelar):
    """Roda uma tarefa da IA e, quando ela termina (de qualquer jeito),
    tira ela da lista de tarefas ativas."""
    try:
        processar_com_ia(pedido, cancelar)
    finally:
        with _trava:
            _tarefas_ativas.discard(cancelar)


def iniciar_tarefa_ia(pedido):
    """Dispara a IA em segundo plano. Se já havia uma tarefa em andamento,
    ela é cancelada e esta nova ganha seu próprio sinal de cancelamento
    (assim uma ordem nova nunca 'desfaz' o cancelamento da anterior)."""
    global cancelar_atual
    cancelar_atual.set()                  # cancela a tarefa antiga
    cancelar_atual = threading.Event()    # cria um sinal novo para a nova
    with _trava:
        _tarefas_ativas.add(cancelar_atual)
    threading.Thread(target=_rodar_tarefa,
                     args=(pedido, cancelar_atual), daemon=True).start()


def eh_cancelar(comando):
    """Diz se a frase é um pedido de cancelamento. Agora é bem mais rígido:
    a frase precisa ser praticamente SÓ o pedido (até 3 palavras), formada
    por palavras de cancelar e, no máximo, palavrinhas de apoio.
      'calma', 'calma aí', 'cancela tudo', 'para tudo'  -> cancela
      'fica calma aí', 'abre o youtube para mim'        -> NÃO cancela"""
    palavras = comando.split()
    if not palavras or len(palavras) > 3:
        return False
    if comando in FRASES_CANCELAR:
        return True
    if not any(p in PALAVRAS_CANCELAR for p in palavras):
        return False
    return all(p in PALAVRAS_CANCELAR or p in PALAVRAS_AUXILIARES_CANCELAR
               for p in palavras)


def ia_pensando():
    """True se a IA está processando um pedido agora (usado pela janela
    para mostrar o status 'Pensando...')."""
    with _trava:
        return any(not tarefa.is_set() for tarefa in _tarefas_ativas)


def ha_algo_pra_cancelar():
    """True se existe algo em andamento: o robô falando (ou com frases na
    fila para falar) ou a IA ainda pensando. Se não houver nada, uma
    palavra como 'calma' é simplesmente ignorada."""
    if falando.is_set() or not fila_fala.empty():
        return True
    with _trava:
        return any(not tarefa.is_set() for tarefa in _tarefas_ativas)


def cancelar_tudo():
    """Botão de emergência: cancela a IA, esvazia a fila de fala e corta a
    frase que está sendo dita agora."""
    with _trava:
        for tarefa in _tarefas_ativas:
            tarefa.set()
    cancelar_atual.set()
    while not fila_fala.empty():
        try:
            fila_fala.get_nowait()
            fila_fala.task_done()
        except queue.Empty:
            break
    if falando.is_set():
        parar_fala.set()    # a thread da voz corta a frase na próxima palavra

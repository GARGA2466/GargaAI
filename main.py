# =====================================================================
#   GargaAI - Assistente virtual de voz para Windows
#   Criado e desenvolvido por: Garga
# =====================================================================
#
# ESTE É O ARQUIVO QUE VOCÊ EXECUTA (o iniciar.bat abre ele).
# Ele só liga as peças que ficam na pasta "ia":
#
#   ia/config.py      -> configurações, textos e idioma
#   ia/utils.py       -> utilidades de texto
#   ia/voz.py         -> microfone e voz do robô
#   ia/escuta.py      -> palavra de ativação e tecla "não perturbe"
#   ia/interface.py   -> a janela bonita (avatar, status, mensagens)
#   ia/ferramentas.py -> ações que a IA pode executar
#   ia/regras.py      -> lê o regras.txt (comandos instantâneos)
#   ia/cerebro.py     -> conversa com a IA (Ollama)
#
# COMO O PROGRAMA FUNCIONA (visão geral):
#
#   1. O microfone escuta em segundo plano e guarda o que você fala numa fila.
#      (Se o modo "não perturbe" estiver ligado, nada é guardado.)
#   2. O programa principal pega cada frase da fila e transforma em texto.
#   3. Com o texto em mãos, ele decide o que fazer, nesta ordem:
#        a) é a resposta de uma confirmação ("sim")?
#        b) é "cancela"/"calma"?      -> cancela a tarefa da IA
#        c) é "sair"?                 -> encerra o programa
#           (ou o comando secreto de formatar, que pede confirmação)
#        d) está no regras.txt?       -> executa na hora (rápido)
#        e) nenhuma das anteriores    -> pergunta pra IA (Ollama), mas só
#                                        se você disse o nome dela
#                                        (exceto no modo Conversa)
#   4. A IA nunca escreve código para executar. Ela só ESCOLHE uma função
#      da lista FERRAMENTAS (tool calling). Isso é o que a deixa segura.
# =====================================================================
import os
import sys
import queue
import threading

# Rodando com pythonw (sem janela preta)? Então não existe terminal: tudo o que
# seria impresso vai para o arquivo gargaai.log (ajuda se algo der errado).
# Isso precisa acontecer ANTES dos outros imports, que também imprimem avisos.
SEM_CONSOLE = sys.stdout is None or sys.stderr is None
if SEM_CONSOLE:
    try:
        _log = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "gargaai.log"),
                    "w", encoding="utf-8", buffering=1)
        sys.stdout = _log
        sys.stderr = _log
    except OSError:
        pass

import speech_recognition as sr      # transforma sua voz em texto

import ia.config as config
from ia.config import (IDIOMA, MODELO, T, TEMPO_MAX_FRASE,
                       LIMITE_PALAVRAS_REGRA, FRASES_SAIR, FRASES_FORMATAR,
                       MODO_ESCUTA, INTERFACE, formatar_assistente, rotulo,
                       precisa_configurar, configurar_palavra_ativacao)
from ia.utils import normalizar
from ia.voz import (reconhecedor, fila_audio, fila_fala, falar,
                    trabalhador_fala, ao_ouvir, pausada, MicrofoneComNivel)
from ia.escuta import (tirar_palavra_ativacao, abrir_janela, consumir_janela,
                       iniciar_tecla, iniciar_tecla_formatar)
from ia.regras import buscar_regra, executar_regra
from ia.ferramentas import resolver_confirmacao, confirmar
from ia.modos import (reconhecer_comando_modo, definir_modo, aviso_do_modo,
                      rotulo_do_modo, modo_atual, CONVERSA)
from ia.memoria import (reconhecer_comando_memoria, mostrar_memoria,
                        limpar_com_aviso, itens as itens_da_memoria)
from ia.cerebro import (eh_cancelar, ha_algo_pra_cancelar, cancelar_tudo,
                        iniciar_tarefa_ia, preparar_ia)


parar_programa = threading.Event()   # ligado quando a janela é fechada


def mostrar_erro(titulo, mensagem):
    """Caixinha de aviso do Windows. Serve para avisar de um problema quando
    não existe terminal para mostrar a mensagem."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, mensagem, titulo, 0x10)
    except Exception:
        pass


def definir_titulo_do_terminal():
    """Troca o título da janela preta do terminal pelo nome que você escolheu."""
    try:
        import ctypes
        nome = config.nome_assistente() or "GargaAI"
        ctypes.windll.kernel32.SetConsoleTitleW(f"{nome} - Assistente por Voz")
    except Exception:
        pass                         # fora do Windows (ou sem terminal): ignora


def formatar_e_sair():
    """Formata o assistente (volta o config.json ao padrão de fábrica) e
    fecha o programa. É chamada depois do "sim" (voz) ou do 2º toque na tecla."""
    if formatar_assistente():
        falar(T["formatado"])
        fila_fala.join()                 # espera terminar de falar
        parar_programa.set()             # encerra o laço (e fecha a janela)
    else:
        print(f"{rotulo()}: não consegui formatar. Nada foi apagado.")


def rodar_assistente():
    """Liga a voz, o microfone e o laço que atende os pedidos. Roda até você
    dizer 'sair' ou fechar a janela."""
    # Liga a thread da voz do robô
    threading.Thread(target=trabalhador_fala, daemon=True).start()

    # Em segundo plano: espera o Ollama e já carrega o modelo na memória.
    threading.Thread(target=preparar_ia, daemon=True).start()

    # Calibra o microfone para o barulho do ambiente (1 segundo de silêncio)
    microfone = MicrofoneComNivel()      # microfone que também mede o volume
    print(f"{rotulo()}: Calibrando o microfone, fique em silêncio um instante...")
    with microfone as fonte:
        reconhecedor.adjust_for_ambient_noise(fonte, duration=1)

    falar(T["pronto"].format(nome=config.nome_assistente() or "GargaAI"))

    # Liga a escuta em segundo plano.
    parar_escuta = reconhecedor.listen_in_background(
        microfone, ao_ouvir, phrase_time_limit=TEMPO_MAX_FRASE)
    print("\n🎙️ [Microfone Aberto]: Pode falar!")

    # Tecla de formatar (2 toques seguidos apagam o nome e as configurações)
    iniciar_tecla_formatar(formatar_e_sair)

    # Tecla liga/desliga (modo "não perturbe")
    if iniciar_tecla():
        print(f"{rotulo()}: Tecla liga/desliga: {config.TECLA_ESCUTA.upper()} "
              "(aperte para ligar/desligar a escuta)")

    try:
        while not parar_programa.is_set():
            try:
                audio, durante_fala = fila_audio.get(timeout=0.5)
            except queue.Empty:
                continue

            # Comando DIGITADO na janela chega como texto; o falado, como áudio.
            digitado = isinstance(audio, str)
            if digitado:
                pedido = audio
            else:
                # Transforma o áudio em texto (usa a internet, via Google)
                try:
                    pedido = reconhecedor.recognize_google(
                        audio, language=T["reconhecimento"])
                except sr.UnknownValueError:
                    continue  # não entendeu nada, ignora
                except sr.RequestError as erro:
                    print(f"{rotulo()}: erro no reconhecimento de voz: {erro}")
                    continue

            # Se você apertou a tecla "não perturbe" enquanto o Google traduzia,
            # essa frase é descartada (o que você DIGITOU continua valendo).
            if pausada.is_set() and not digitado:
                continue

            comando = normalizar(pedido)
            if not comando:
                continue
            print(f"{T['voce_disse']}: '{pedido}'")

            # Separa o nome da pessoa do pedido: "Fuyumi, abaixa o volume"
            # vira "abaixa o volume". None = ela não disse o nome.
            sem_nome = tirar_palavra_ativacao(comando)
            if digitado and sem_nome is None:
                sem_nome = comando       # digitar vale como se tivesse dito o nome

            # Se o robô estava falando, só o cancelamento é aceito
            # (com ou sem o nome na frente: "calma" ou "Fuyumi, calma").
            if durante_fala:
                candidato = sem_nome if sem_nome is not None else comando
                if (candidato and eh_cancelar(candidato)
                        and ha_algo_pra_cancelar()):
                    cancelar_tudo()
                    print(f"{rotulo()}: {T['cancelado']} 🛑")
                continue

            tem_palavra = sem_nome is not None

            # Só o nome, sem pedido ("Fuyumi"): abre uma janelinha de alguns
            # segundos, e o próximo pedido vale mesmo sem dizer o nome.
            if tem_palavra and sem_nome == "":
                abrir_janela()
                falar(T["pode_falar"])
                continue

            # Se a janelinha estava aberta, este pedido vale como se tivesse
            # o nome. Então mandamos o nome pra IA junto (é assim que ela sabe
            # quem ela é).
            pedido_ia = pedido
            if tem_palavra:
                comando_efetivo = sem_nome
            elif consumir_janela():
                tem_palavra = True
                comando_efetivo = comando
                pedido_ia = f"{config.nome_assistente()}, {pedido}"
            else:
                comando_efetivo = comando

            # a) Resposta de uma confirmação pendente ("sim" / "não")
            if resolver_confirmacao(comando_efetivo):
                continue

            # b) Cancelamento: SEMPRE funciona, mesmo sem o nome
            if eh_cancelar(comando_efetivo):
                if ha_algo_pra_cancelar():
                    cancelar_tudo()
                    print(f"{rotulo()}: {T['cancelado']} 🛑")
                else:
                    print(f"{rotulo()}: Não tem nada para cancelar, ignorei.")
                continue

            # b2) Trocar de modo: "modo trabalho" / "modo conversa"
            novo_modo = reconhecer_comando_modo(comando_efetivo)
            if novo_modo:
                definir_modo(novo_modo)
                aviso = aviso_do_modo(novo_modo)
                if aviso:
                    falar(aviso)
                continue

            # b3) Memória: "ver a memória" / "limpar a memória" (esta pede confirmação)
            acao_memoria = reconhecer_comando_memoria(comando_efetivo)
            if acao_memoria == "ver":
                mostrar_memoria()
                continue
            if acao_memoria == "limpar":
                confirmar(T["pergunta_limpar_memoria"], limpar_com_aviso)
                continue

            # c) Encerrar o programa: também SEMPRE funciona
            if comando_efetivo in FRASES_SAIR:
                falar(T["tchau"])
                fila_fala.join()
                break

            # c2) Formatar o assistente (comando secreto): pede confirmação
            if comando_efetivo in FRASES_FORMATAR:
                confirmar(T["pergunta_formatar"], formatar_e_sair)
                continue

            # d) Regras diretas do regras.txt: funcionam sem o nome
            if len(comando_efetivo.split()) <= LIMITE_PALAVRAS_REGRA:
                acao = buscar_regra(comando_efetivo)
                if acao:
                    executar_regra(acao)
                    continue

            # e) Só chega aqui o que for IA ou conversa longa.
            # No modo Conversa NÃO exige a palavra de ativação.
            # No modo Trabalho continua exigindo.
            if (MODO_ESCUTA == "palavra_ativacao"
                    and not tem_palavra
                    and modo_atual() != CONVERSA):
                print(f"{rotulo()}: (ignorado, falei sem a palavra de ativação)")
                continue

            # Nada combinou: a IA assume, em segundo plano
            print(f"{rotulo()}: {T['pensando']}")
            iniciar_tarefa_ia(pedido_ia)

    except KeyboardInterrupt:
        print(f"\n{rotulo()}: Encerrado pelo teclado (Ctrl+C).")
    finally:
        parar_escuta(wait_for_stop=False)   # desliga a escuta do microfone


def main():
    print("=" * 60)
    print("  GargaAI Oficial Ativo! (Controle de Voz do Windows)")
    print("  Desenvolvido por: Garga")

    # --- PRIMEIRO ACESSO: pergunta o nome se ainda não tiver sido salvo ---
    if precisa_configurar():
        pedir = None
        if INTERFACE == "janela" or SEM_CONSOLE:
            try:
                from ia import interface
                pedir = interface.pedir_nome      # janelinha bonita no centro da tela
            except Exception:
                pedir = None
        configurar_palavra_ativacao(pedir)
    definir_titulo_do_terminal()

    print(f"  Idioma detectado: {IDIOMA} | Modelo: {MODELO}")
    print(f"  Modo: {rotulo_do_modo()}  (diga 'modo trabalho' ou 'modo conversa')")
    print(f"  Memória: {len(itens_da_memoria())} anotação(ões) carregada(s)")
    if MODO_ESCUTA == "palavra_ativacao":
        print(f"  Palavra de ativação: '{config.nome_assistente()}' "
              "(no modo Trabalho precisa falar o nome; no modo Conversa não)")
    else:
        print(f"  Modo de escuta: {MODO_ESCUTA}")
    print("=" * 60)

    # Janela bonita (plano B: se não der, roda no terminal como antes).
    # Sem console (pythonw) a janela é obrigatória: não existe terminal pra cair.
    if INTERFACE == "janela" or SEM_CONSOLE:
        try:
            from ia import interface
            interface.iniciar(rodar_assistente, parar_programa)
            return
        except Exception as erro:
            print(f"{rotulo()}: não consegui abrir a janela ({erro}).")
            if SEM_CONSOLE:
                mostrar_erro("GargaAI",
                             f"Não consegui abrir a janela.\n\n{erro}\n\n"
                             "Abra o iniciar_com_console.bat para ver a mensagem "
                             "completa (ou leia o arquivo gargaai.log).")
                return
            print(f"{rotulo()}: Vou rodar no terminal. (Para a janela, rode: "
                  "pip install customtkinter pillow)")

    rodar_assistente()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        if SEM_CONSOLE:
            mostrar_erro("GargaAI",
                         "O programa fechou por causa de um erro.\n\n"
                         "Veja os detalhes no arquivo gargaai.log "
                         "(na pasta do GargaAI).")
        else:
            raise
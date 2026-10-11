# =====================================================================
#   PROJETO: GargaAI - ASSISTENTE VIRTUAL DE VOZ PARA WINDOWS
#   CRIADO E DESENVOLVIDO POR: Garga
#   LICENÇA: Open Source / Todos os direitos ao autor original
# =====================================================================

CRIADOR_OFICIAL = "Garga"

if CRIADOR_OFICIAL != "Garga":
    print("ERRO CRÍTICO: Violação de direitos autorais. O projeto pertence a Garga.")
    exit()

import os, subprocess, pyautogui, keyboard, time
import ollama
import speech_recognition as sr
import pyttsx3
import threading
from collections import deque
import pygetwindow as gw

MODELO = "deepseek-coder-v2:16b"

print("="*60)
print("  GargaAI Oficial Ativo! (Controle de Voz do Windows)")
print(f"  Desenvolvido por: {CRIADOR_OFICIAL}")
print("="*60)

# ESCOLHA DO IDIOMA
print("\n[Language / Idioma]")
print("1 - Português (Brasil)")
print("2 - English (US)")
escolha_lang = input("Escolha / Choose (1/2) [Padrão: 1]: ").strip()

if escolha_lang == "2":
    IDIOMA = "en-US"
    MSG_PRONTO = "GargaAI online and listening!"
    MSG_OUVINDO = "You said:"
    MSG_CANCELADO = "Task cancelled!"
    PROMPT_LANG = "Answer in English briefly (max 2 sentences)."
    print("[GargaAI]: English language activated!")
else:
    IDIOMA = "pt-BR"
    MSG_PRONTO = "GargaAI online e ouvindo!"
    MSG_OUVINDO = "Você disse:"
    MSG_CANCELADO = "Ação cancelada!"
    PROMPT_LANG = "Responda em português de forma curta (máximo 2 frases)."
    print("[GargaAI]: Idioma Português ativado!")

robo = pyttsx3.init()
robo.setProperty('rate', 190)

def falar(texto):
    try:
        print(f"[GargaAI]: {texto}")
        robo.say(texto)
        robo.runAndWait()
    except:
        pass

reconhecedor = sr.Recognizer()
pasta = os.path.dirname(os.path.abspath(__file__))
caminho_regras = os.path.join(pasta, "regras.txt")
caminho_extensao = os.path.join(pasta, "extensao.txt")

cancelar_tarefa = False
memoria = deque(maxlen=6)

def focar_ou_abrir(titulo_procurado, url_ou_comando):
    try:
        todas = gw.getAllWindows()
        janela_encontrada = None

        for janela in todas:
            titulo = janela.title.lower()
            if titulo_procurado.lower() in titulo:
                janela_encontrada = janela
                break

        if janela_encontrada:
            if janela_encontrada.isMinimized:
                janela_encontrada.restore()
            janela_encontrada.activate()
            print(f"[GargaAI]: Foquei em → {janela_encontrada.title}")
            return True

        operas = [w for w in gw.getAllWindows() if "opera" in w.title.lower()]
        if operas:
            operas[0].activate()
            time.sleep(0.3)

        print(f"[GargaAI]: Abrindo novo '{titulo_procurado}'...")
        if url_ou_comando.startswith("http"):
            subprocess.Popen(['start', url_ou_comando], shell=True)
        else:
            os.system(url_ou_comando)
        return False

    except Exception:
        if url_ou_comando.startswith("http"):
            subprocess.Popen(['start', url_ou_comando], shell=True)
        else:
            os.system(url_ou_comando)
        return False

def processar_ia_completa(pedido, comando, eh_comando):
    global cancelar_tarefa
    cancelar_tarefa = False

    if eh_comando:
        palavra_chave = comando.replace("abre", "").replace("abrir", "").strip()
        prompt = f"""
        Gere APENAS uma linha no formato: gatilho = codigo_python para Windows.
        Use focar_ou_abrir('Nome', 'url_ou_comando') se for app ou site.
        Pedido: '{pedido}'
        Responda apenas a linha pura sem markdown.
        """
        try:
            resp = ollama.chat(model=MODELO, messages=[{'role': 'user', 'content': prompt}])
            if cancelar_tarefa:
                print(f"[GargaAI]: {MSG_CANCELADO} 🛑")
                return

            nova_regra = resp['message']['content'].replace("```python", "").replace("```", "").strip()
            if "=" in nova_regra and not cancelar_tarefa:
                acao = nova_regra.split("=", 1)[1].strip()
                while acao.count(')') > acao.count('(') and acao.endswith(')'):
                    acao = acao[:-1].strip()
                exec(acao)
                with open(caminho_extensao, "a", encoding="utf-8") as f:
                    f.write("\n" + nova_regra)
                print("[GargaAI]: Aprendido com sucesso!")
        except Exception as e:
            if not cancelar_tarefa:
                print(f"Erro IA: {e}")
    else:
        historico = "\n".join(memoria)
        prompt_conversa = f"""
        Você é o GargaAI, um assistente prestativo.
        {PROMPT_LANG}
        Histórico: {historico if historico else 'Nenhum'}
        Pergunta: {pedido}
        """
        try:
            resp = ollama.chat(model=MODELO, messages=[{'role': 'user', 'content': prompt_conversa}])
            if cancelar_tarefa:
                print(f"[GargaAI]: {MSG_CANCELADO} 🛑")
                return
            resposta = resp['message']['content'].strip()
            memoria.append(f"User: {pedido}")
            memoria.append(f"GargaAI: {resposta}")
            falar(resposta)
        except Exception as e:
            if not cancelar_tarefa:
                print("Erro conversa:", e)

falar(MSG_PRONTO)

while True:
    try:
        with sr.Microphone() as source:
            print("\n🎙️ [Microfone Aberto]: Pode falar!")
            audio = reconhecedor.listen(source, phrase_time_limit=8)

        pedido = reconhecedor.recognize_google(audio, language=IDIOMA)
        comando = pedido.lower().strip()
        print(f"{MSG_OUVINDO} '{pedido}'")

        palavras_cancelar = ["cancela", "cancelar", "para tudo", "esquece", "cancel", "stop", "abort", "calma", "calma aí", "calma ai", "espera", "para", "para aí"]
        if any(p in comando for p in palavras_cancelar):
            cancelar_tarefa = True
            print(f"[GargaAI]: {MSG_CANCELADO} 🛑")
            continue

        if comando in ['encerrar programa', 'sair', 'exit', 'quit']:
            falar("Goodbye!" if IDIOMA == "en-US" else "Até logo, chefe!")
            break

        executou = False
        for caminho in [caminho_regras, caminho_extensao]:
            if os.path.exists(caminho):
                with open(caminho, "r", encoding="utf-8") as f:
                    for linha in f:
                        linha = linha.strip()
                        if "=" in linha and not linha.startswith("#"):
                            gatilhos, acao = linha.split("=", 1)
                            palavras = [p.strip().lower() for p in gatilhos.split(",")]
                            if any(p in comando for p in palavras):
                                print(f"[Ação Direta]: {acao.strip()}")
                                exec(acao.strip())
                                executou = True
                                break
            if executou:
                break

        if executou:
            continue

        palavras_comando = ["abre", "abrir", "fecha", "fechar", "open", "close", "start", "pausa", "pausar", "play", "volume", "muta", "minimiza", "maximiza"]
        eh_comando = any(p in comando for p in palavras_comando)

        print("[GargaAI]: Pensando em segundo plano... (diga 'cancela' ou 'calma' para parar!)")
        t = threading.Thread(target=processar_ia_completa, args=(pedido, comando, eh_comando))
        t.start()

    except sr.UnknownValueError:
        pass
    except Exception as e:
        print("Erro:", e)

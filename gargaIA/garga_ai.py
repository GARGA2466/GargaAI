# =====================================================================
#   PROJETO: GargaAI - ASSISTENTE VIRTUAL DE VOZ PARA WINDOWS
#   CRIADO E DESENVOLVIDO POR: Garga
#   LICENÇA: Open Source / Todos os direitos ao autor original
# =====================================================================

CRIADOR_OFICIAL = "Garga"

# TRAVA ESSENCIAL DE SEGURANÇA: Só roda com a assinatura original do Garga!
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

# ESCOLHA DO IDIOMA (BILINGUAL SUPPORT)
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

# VERIFICAÇÃO AUTOMÁTICA DE MODELO
try:
    print("\n[GargaAI]: Verificando inteligência artificial...")
    modelos_disponiveis = ollama.list()
    lista_nomes = []
    if 'models' in modelos_disponiveis:
        lista_nomes = [m['name'] for m in modelos_disponiveis['models']]
    
    if not any(MODELO in m for m in lista_nomes):
        print(f"[GargaAI]: Modelo '{MODELO}' não encontrado neste PC!")
        print("[GargaAI]: Baixando modelo automaticamente dos servidores (aguarde)...")
        ollama.pull(MODELO)
        print("[GargaAI]: Modelo baixado e configurado com sucesso!")
    else:
        print(f"[GargaAI]: Cérebro '{MODELO}' pronto!")
except Exception as e:
    print(f"[Aviso]: Verifique se o servidor do Ollama está rodando ({e})")

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

def limpar_resposta(texto):
    return texto.replace("```python", "").replace("```", "").strip()

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

def executar_ia_em_segundo_plano(pedido, comando):
    global cancelar_tarefa
    cancelar_tarefa = False

    prompt = f"""
    Gere APENAS uma linha no formato: gatilho = codigo_python para Windows.
    Use focar_ou_abrir('Nome', 'comando_ou_url') se for app ou site.
    Pedido: '{pedido}'
    Responda apenas a linha pura sem markdown.
    """

    try:
        resp = ollama.chat(model=MODELO, messages=[{'role': 'user', 'content': prompt}])
        if cancelar_tarefa:
            print(f"[GargaAI]: {MSG_CANCELADO}")
            return

        nova_regra = limpar_resposta(resp['message']['content'])
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

falar(MSG_PRONTO)

while True:
    try:
        with sr.Microphone() as source:
            reconhecedor.adjust_for_ambient_noise(source, duration=0.5)
            audio = reconhecedor.listen(source)

        pedido = reconhecedor.recognize_google(audio, language=IDIOMA)
        comando = pedido.lower().strip()
        print(f"\n{MSG_OUVINDO} '{pedido}'")

        # Comandos de cancelar universais (PT e EN)
        palavras_cancelar = ["cancela", "cancelar", "para tudo", "esquece", "cancel", "stop", "abort"]
        if any(p in comando for p in palavras_cancelar):
            cancelar_tarefa = True
            print(f"[GargaAI]: {MSG_CANCELADO} 🛑")
            continue

        if comando in ['encerrar programa', 'sair', 'exit', 'quit', 'close gargaai']:
            falar("Goodbye!" if IDIOMA == "en-US" else "Até logo, chefe!")
            break

        # 1. Regras diretas
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
                                try:
                                    exec(acao.strip())
                                except Exception as e:
                                    print("Erro:", e)
                                executou = True
                                break
            if executou:
                break

        if executou:
            continue

        # 2. Comandos de ação (PT e EN)
        palavras_comando = [
            "abre", "abrir", "fecha", "fechar", "open", "close", "start",
            "pausa", "pausar", "despause", "play", "pause", "tocar",
            "volume", "muta", "mute", "unmute", "minimiza", "maximiza",
            "minimize", "maximize", "aba", "tab", "rola", "scroll"
        ]

        if any(p in comando for p in palavras_comando):
            print("[GargaAI]: Processando comando...")
            thread = threading.Thread(target=executar_ia_em_segundo_plano, args=(pedido, comando))
            thread.start()
        else:
            # 3. Conversa livre
            historico = "\n".join(memoria)
            prompt_conversa = f"""
            You are GargaAI, a helpful virtual assistant created by Garga.
            {PROMPT_LANG}
            History: {historico if historico else 'None'}
            User: {pedido}
            """
            resp = ollama.chat(model=MODELO, messages=[{'role': 'user', 'content': prompt_conversa}])
            resposta = resp['message']['content'].strip()
            memoria.append(f"User: {pedido}")
            memoria.append(f"GargaAI: {resposta}")
            falar(resposta)

    except sr.UnknownValueError:
        pass
    except Exception as e:
        print("Erro:", e)
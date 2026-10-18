# =====================================================================
#   interface.py - A janela do GargaAI (CustomTkinter, tema escuro)
# =====================================================================
# O desenho da janela (de cima para baixo):
#
#   +-----------------------------+
#   |   CHAT (80% da altura)      |  tudo o que antes aparecia na tela preta
#   |   o texto sobe sozinho      |  (o que você disse, o que ela fez)
#   +-----------------------------+
#   | (||)  | | || | ||| | | ||   |  CÁPSULA (20%): botão pause/play + ondas
#   +-----------------------------+
#
# O botão redondo mostra || quando a escuta está ligada e ▶ quando está
# pausada (é o mesmo liga/desliga da tecla F8).
# As barras verdes ficam PARADAS (desenhadas como no esboço). Elas só se mexem
# enquanto o microfone está captando som de verdade, e quanto mais alto o
# som, maior o movimento. Voltou o silêncio, elas voltam a ficar paradas.
# Quando a escuta é pausada, as barras ficam cinzas.
#
# Também tem a janelinha de PRIMEIRO ACESSO (pedir_nome), que pergunta como você
# quer chamar o assistente.
#
# CORES: mude as constantes logo abaixo (é só trocar o código da cor).
import sys
import math
import time
import queue
import random
import threading
import os
import subprocess

from . import config
from . import voz, cerebro, escuta, modos

try:
    import customtkinter as ctk
except Exception:          # não instalado: o main.py cai para o terminal
    ctk = None

# ---------------------------------------------------------------------
# CORES E MEDIDAS (mexa aqui para mudar o visual)
# ---------------------------------------------------------------------
COR_FUNDO = "#141518"            # fundo da janela (cinza-grafite bem escuro)
COR_CHAT = "#1a1b1f"             # fundo da área de chat
COR_CAPSULA = "#2a2b32"          # fundo da cápsula (um pouco mais claro)
COR_BORDA = "#3a3b44"
COR_TEXTO = "#e6e6ea"
COR_BOTAO = "#3a3b44"
COR_BOTAO_HOVER = "#4a4b55"
COR_ONDA = "#22c55e"             # barras verdes
COR_ONDA_PAUSADA = "#4b4c55"     # barras cinzas quando pausado

PROPORCAO_CHAT = 4               # chat : cápsula = 4 : 1  (80% / 20%)
PROPORCAO_CAPSULA = 1
LARGURA, ALTURA = 520, 720       # tamanho inicial (formato "celular", como no desenho)

# estado -> texto mostrado no título da janela
ESTADOS = {
    "ouvindo":    "Ouvindo...",
    "aguardando": "Pode falar...",
    "pensando":   "Pensando...",
    "executando": "Executando...",
    "falando":    "Falando...",
    "pausada":    "Pausada",
}

# tipo de linha -> cor no chat
CORES_LOG = {
    "voce":   "#7dd3fc",   # o que você disse
    "acao":   "#c084fc",   # ações executadas
    "erro":   "#f87171",   # problemas
    "cancel": "#fbbf24",   # cancelamentos
    "normal": "#cfcfdc",   # o resto
}

MAX_LINHAS_LOG = 600
ESPACO_BARRAS = 12               # distância entre as barras verdes (pixels)


# ---------------------------------------------------------------------
# LÓGICA (não depende da janela, por isso dá pra testar)
# ---------------------------------------------------------------------
_ultima_acao = 0.0      # hora da última ação executada (para o "Executando...")


def _marcar_acao(linha):
    """Se a linha de texto indica que algo foi executado, anota a hora."""
    global _ultima_acao
    if linha.startswith("[Ação Direta]") or linha.startswith("[Ferramenta]"):
        _ultima_acao = time.time()


def calcular_estado(agora=None):
    """Descobre o que o assistente está fazendo agora, olhando o estado real
    do programa. A ordem importa: o mais 'forte' vem primeiro."""
    agora = agora if agora is not None else time.time()
    if voz.pausada.is_set():
        return "pausada"
    if voz.falando.is_set():
        return "falando"
    if cerebro.ia_pensando():
        return "pensando"
    if agora - _ultima_acao < 1.2:
        return "executando"
    if escuta.janela_esta_aberta():
        return "aguardando"
    return "ouvindo"


def tipo_da_linha(linha):
    """Escolhe a cor de uma linha do chat."""
    baixa = linha.lower()
    if linha.startswith(config.T["voce_disse"]):
        return "voce"
    if linha.startswith("[Ação Direta]") or linha.startswith("[Ferramenta]"):
        return "acao"
    if "🛑" in linha or "cancelad" in baixa:
        return "cancel"
    if "erro" in baixa or "não consegui" in baixa or "nao consegui" in baixa:
        return "erro"
    return "normal"


class _Tee:
    """Copia tudo o que o programa 'imprime' (print) para a janela, sem
    deixar de mostrar no terminal. Assim nenhum outro arquivo precisou mudar."""

    def __init__(self, original, fila):
        self._original = original
        self._fila = fila
        self._parcial = ""
        self._trava = threading.Lock()

    def write(self, texto):
        try:
            if self._original is not None:
                self._original.write(texto)
        except Exception:
            pass
        with self._trava:
            self._parcial += texto
            while "\n" in self._parcial:
                linha, self._parcial = self._parcial.split("\n", 1)
                self._fila.put(linha)
                _marcar_acao(linha)
        return len(texto)

    def flush(self):
        try:
            if self._original is not None:
                self._original.flush()
        except Exception:
            pass

    def __getattr__(self, nome):
        return getattr(self._original, nome)


class Onda:
    """As barras verdes. Em repouso, cada barra fica numa altura fixa (um
    desenho variado, como no esboço). Quando há som, elas se movem
    suavemente em direção a valores sorteados, parecendo um áudio de
    verdade. Passou o som, elas voltam sozinhas ao desenho de repouso."""
    MINIMO = 0.06

    def __init__(self, quantidade=40, semente=None):
        self._sorteio = random.Random(semente)
        self._iniciar(quantidade)

    @staticmethod
    def _repouso(i, n):
        """Altura fixa (0 a 1) da barra i em repouso, mais alta no meio."""
        envelope = 0.55 + 0.45 * math.sin(math.pi * (i + 0.5) / n)
        variacao = abs(math.sin(i * 1.9) * math.cos(i * 0.6))
        return min(0.7, 0.10 + 0.5 * variacao * envelope)

    def _iniciar(self, quantidade):
        quantidade = max(1, quantidade)
        self.alturas = [self._repouso(i, quantidade) for i in range(quantidade)]
        self._alvos = list(self.alturas)

    def redimensionar(self, quantidade):
        """Ajusta o número de barras quando a janela muda de tamanho."""
        if max(1, quantidade) != len(self.alturas):
            self._iniciar(quantidade)

    def passo(self, ativa, intensidade=1.0):
        """Avança a animação um quadro e devolve as alturas atuais.
        ativa=False: as barras voltam ao desenho de repouso e ficam paradas.
        intensidade (0 a 1): quão alto o som está; muda o tamanho do movimento."""
        n = len(self.alturas)
        for i in range(n):
            base = self._repouso(i, n)
            if not ativa:
                self._alvos[i] = base
            elif self._sorteio.random() < 0.3:
                limite = 0.55 + 0.45 * math.sin(math.pi * (i + 0.5) / n)
                pico = max(base, self.MINIMO + (limite - self.MINIMO) * intensidade)
                self._alvos[i] = base + self._sorteio.random() * (pico - base)
            self.alturas[i] += (self._alvos[i] - self.alturas[i]) * 0.35
        return self.alturas


# ---------------------------------------------------------------------
# A JANELA
# ---------------------------------------------------------------------
class Painel:
    def __init__(self, parar_programa):
        self.parar_programa = parar_programa      # ligado quando a janela fecha
        self.terminou = threading.Event()         # ligado quando o assistente acaba
        self.fila_log = queue.Queue()
        self.onda = Onda()
        self._ultimo_desenho = None
        self._estado_mostrado = None
        self._modo_mostrado = None
        self._fechada = False

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.app = ctk.CTk()
        self.nome = config.nome_assistente() or "GargaAI"
        self.app.title(self.nome)
        self.app.geometry(f"{LARGURA}x{ALTURA}")
        self.app.minsize(380, 520)
        self.app.configure(fg_color=COR_FUNDO)
        self.app.protocol("WM_DELETE_WINDOW", self.fechar)
        self._montar()

        # Só no fim (se algo acima falhar, o terminal continua normal)
        self._stdout_original = sys.stdout
        sys.stdout = _Tee(sys.stdout, self.fila_log)
        self.app.after(150, self._atualizar)
        self.app.after(40, self._animar)

    # ---------- montagem dos elementos ----------
    def _montar(self):
        import tkinter as tk
        app = self.app

        # Duas linhas: chat (80%) e cápsula (20%). O "uniform" faz as linhas
        # seguirem exatamente a proporção, mesmo se a janela for redimensionada.
        app.grid_columnconfigure(0, weight=1)
        app.grid_rowconfigure(0, weight=PROPORCAO_CHAT, uniform="altura")
        app.grid_rowconfigure(1, weight=PROPORCAO_CAPSULA, uniform="altura")

        # ----- CHAT (parte de cima) -----
        self.caixa = ctk.CTkTextbox(
            app, corner_radius=22, fg_color=COR_CHAT, text_color=COR_TEXTO,
            border_width=2, border_color=COR_BORDA, wrap="word",
            font=ctk.CTkFont(size=14))
        self.caixa.grid(row=0, column=0, sticky="nsew", padx=18, pady=(18, 10))
        for tipo, cor in CORES_LOG.items():
            self.caixa.tag_config(tipo, foreground=cor)
        self.caixa.configure(state="disabled")

        # ----- CÁPSULA (parte de baixo) -----
        capsula = ctk.CTkFrame(
            app, corner_radius=40, fg_color=COR_CAPSULA,
            border_width=2, border_color=COR_BORDA)
        capsula.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        capsula.grid_columnconfigure(1, weight=1)
        capsula.grid_rowconfigure(0, weight=1)

        # Botão redondo: || quando ouvindo, ▶ quando pausado
        self.btn_pausa = ctk.CTkButton(
            capsula, text="||", width=54, height=54, corner_radius=27,
            font=ctk.CTkFont(size=22, weight="bold"), text_color=COR_TEXTO,
            fg_color=COR_BOTAO, hover_color=COR_BOTAO_HOVER,
            border_width=2, border_color=COR_TEXTO, command=self._alternar)
        self.btn_pausa.grid(row=0, column=0, padx=(20, 8), pady=12)

        # Ondas verdes (desenhadas num canvas)
        self.canvas_onda = tk.Canvas(
            capsula, bg=COR_CAPSULA, highlightthickness=0, bd=0, height=60)
        self.canvas_onda.grid(row=0, column=1, sticky="nsew", padx=(8, 26), pady=12)

    # ---------- ações ----------
    def _alternar(self):
        escuta.alternar_escuta()

    def fechar(self):
        if self._fechada:
            return
        self._fechada = True
        self.parar_programa.set()

        # Cancela tudo da IA
        try:
            cerebro.cancelar_tudo()
        except Exception:
            pass

        # Mata o Ollama se for o processo que a gente ligou
        try:
            cerebro.desligar_ollama()
        except Exception:
            pass

        # Mata qualquer llama-server.exe que ainda esteja rodando (segurança)
        try:
            subprocess.run(["taskkill", "/F", "/IM", "llama-server.exe"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

        sys.stdout = self._stdout_original

        try:
            self.app.destroy()
        except Exception:
            pass

        # Força o fechamento completo do programa
        os._exit(0)

    # ---------- chat ----------
    def _escrever(self, linha):
        if not linha.strip() or set(linha.strip()) == {"="}:
            return                               # pula linhas vazias e enfeites
        self.caixa.configure(state="normal")
        self.caixa.insert("end", linha + "\n", tipo_da_linha(linha))
        if int(self.caixa.index("end-1c").split(".")[0]) > MAX_LINHAS_LOG:
            self.caixa.delete("1.0", "100.0")    # apaga as mais antigas
        self.caixa.see("end")                    # o texto "sobe" sozinho
        self.caixa.configure(state="disabled")

    # ---------- estado (botão e título) ----------
    def _definir_titulo(self, texto):
        """Troca o título da janela. Se o Windows não aceitar o emoji, tira ele."""
        try:
            self.app.title(texto)
        except Exception:
            try:
                simples = texto.encode("ascii", "ignore").decode("ascii")
                self.app.title(simples.replace(" ]", "]"))
            except Exception:
                pass

    def _mostrar_estado(self, estado):
        modo = modos.modo_atual()
        if estado == self._estado_mostrado and modo == self._modo_mostrado:
            return
        self._estado_mostrado = estado
        self._modo_mostrado = modo
        # Ex: "Fuyumi [Trabalho 💼] - Ouvindo..."
        self._definir_titulo(
            f"{self.nome} [{modos.rotulo_do_modo(modo)}] - {ESTADOS[estado]}")
        # || quando o microfone está ativo, ▶ quando está pausado
        if estado == "pausada":
            self.btn_pausa.configure(text="▶")
        else:
            self.btn_pausa.configure(text="||")

    def _atualizar(self):
        """A cada 150 ms: traz as linhas novas para o chat e atualiza o estado."""
        if self._fechada:
            return
        if self.terminou.is_set():               # o assistente acabou ("sair")
            self.fechar()
            return
        try:
            for _ in range(60):                  # no máximo 60 linhas por vez
                self._escrever(self.fila_log.get_nowait())
        except queue.Empty:
            pass
        except Exception as erro:
            print(f"{config.rotulo()}: erro ao atualizar a janela: {erro}")
        try:
            self._mostrar_estado(calcular_estado())
        except Exception as erro:
            print(f"{config.rotulo()}: erro ao atualizar o status: {erro}")
        self.app.after(150, self._atualizar)

    # ---------- ondas verdes (a cada 40 ms) ----------
    def _animar(self):
        if self._fechada:
            return
        try:
            c = self.canvas_onda
            largura = max(int(c.winfo_width()), 60)
            altura = max(int(c.winfo_height()), 20)
            quantidade = max(8, largura // ESPACO_BARRAS)
            self.onda.redimensionar(quantidade)

            escuta_ligada = not voz.pausada.is_set()
            # As barras só se mexem se a escuta está ligada E o microfone
            # está captando som neste momento.
            com_som = escuta_ligada and voz.mic_captando()
            alturas = self.onda.passo(com_som, voz.nivel_atual() if com_som else 0.0)
            cor = COR_ONDA if escuta_ligada else COR_ONDA_PAUSADA

            # Parado = nada mudou desde o último quadro: não redesenha.
            desenho = (largura, altura, cor, tuple(round(a, 2) for a in alturas))
            if desenho != self._ultimo_desenho:
                self._ultimo_desenho = desenho
                c.delete("all")
                meio = altura / 2
                inicio = (largura - (quantidade - 1) * ESPACO_BARRAS) / 2
                for i, h in enumerate(alturas):
                    metade = max(2.0, h * (altura / 2 - 3))
                    x = inicio + i * ESPACO_BARRAS
                    c.create_line(x, meio - metade, x, meio + metade,
                                  fill=cor, width=4, capstyle="round")
        except Exception as erro:
            print(f"{config.rotulo()}: erro na animação: {erro}")
        self.app.after(40, self._animar)


def pedir_nome():
    """Janelinha de PRIMEIRO ACESSO, no centro da tela: pergunta como você quer
    chamar o assistente. Devolve o nome digitado, ou None se a janelinha for
    fechada sem salvar. Se não conseguir abrir, levanta um erro (e o
    config.py pergunta no terminal)."""
    if ctk is None:
        raise RuntimeError("o customtkinter não está instalado "
                           "(rode: pip install customtkinter)")
    T = config.T
    resultado = {"nome": None}

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = ctk.CTk()
    app.title(T["setup_titulo"])
    app.resizable(False, False)
    app.configure(fg_color=COR_FUNDO)

    # Centraliza na tela (considerando a escala do Windows, ex: 125%)
    largura, altura = 440, 290
    try:
        escala = app._get_window_scaling()
    except Exception:
        escala = 1.0
    x = max(int((app.winfo_screenwidth() - largura * escala) / 2), 0)
    y = max(int((app.winfo_screenheight() - altura * escala) / 2), 0)
    app.geometry(f"{largura}x{altura}+{x}+{y}")

    ctk.CTkLabel(app, text=T["setup_pergunta"], text_color=COR_TEXTO,
                 font=ctk.CTkFont(size=21, weight="bold")).pack(pady=(36, 6))
    ctk.CTkLabel(app, text=T["setup_dica"], text_color="#8b8ba0",
                 font=ctk.CTkFont(size=12)).pack()

    entrada = ctk.CTkEntry(
        app, width=320, height=46, corner_radius=23, fg_color=COR_CHAT,
        border_color=COR_BORDA, border_width=2, font=ctk.CTkFont(size=15),
        placeholder_text=T["setup_placeholder"])
    entrada.pack(pady=(22, 4))
    aviso = ctk.CTkLabel(app, text="", text_color="#f87171",
                         font=ctk.CTkFont(size=12))
    aviso.pack()

    def salvar(_evento=None):
        nome = entrada.get().strip()
        if not nome:
            aviso.configure(text=T["setup_vazio"])
            return
        resultado["nome"] = nome[:30]
        app.quit()                               # encerra o mainloop desta janelinha

    ctk.CTkButton(
        app, text=T["setup_salvar"], width=320, height=46, corner_radius=23,
        font=ctk.CTkFont(size=15, weight="bold"), fg_color=COR_ONDA,
        hover_color="#16a34a", text_color="#06210f", command=salvar).pack(pady=(6, 0))
    entrada.bind("<Return>", salvar)             # Enter também salva
    app.protocol("WM_DELETE_WINDOW", app.quit)   # fechar no X = sem nome

    # Sem terminal por trás, a janelinha precisa vir pra frente sozinha
    app.lift()
    app.attributes("-topmost", True)
    app.after(400, lambda: app.attributes("-topmost", False))
    app.after(150, entrada.focus_force)

    try:
        app.mainloop()
    finally:
        try:
            app.destroy()
        except Exception:
            pass
    return resultado["nome"]


def iniciar(alvo, parar_programa):
    """Abre a janela (na thread principal) e roda o assistente ('alvo') numa
    thread à parte, então o microfone, o reconhecimento de voz e a IA nunca
    travam a janela. Se a janela não puder ser criada, levanta um erro ANTES
    de iniciar o assistente, e o main.py cai para o terminal."""
    if ctk is None:
        raise RuntimeError("o customtkinter não está instalado "
                           "(rode: pip install customtkinter)")
    painel = Painel(parar_programa)

    def rodar():
        try:
            alvo()
        finally:
            painel.terminou.set()

    threading.Thread(target=rodar, daemon=True).start()
    try:
        painel.app.mainloop()
    except Exception as erro:
        print(f"{config.rotulo()}: erro na janela: {erro}")
    finally:
        parar_programa.set()
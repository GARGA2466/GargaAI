# =====================================================================
#   ferramentas.py - As únicas ações que a IA pode executar
# =====================================================================
# A IA lê o NOME, os PARÂMETROS e a DESCRIÇÃO (docstring) de cada função
# para decidir qual usar. Por isso as descrições são importantes!
import os
import re
import time
import socket
import threading
import contextlib
import subprocess
import webbrowser
from urllib.parse import urlparse

import pyautogui                     # simula teclado (atalhos, volume, etc.)
import pygetwindow as gw             # enxerga e foca janelas abertas
try:
    import psutil                    # descobre de qual programa é cada janela
except ImportError:
    psutil = None                    # sem ele, o programa usa o título da janela

from .config import (APPS_E_SITES, NAVEGADOR_PADRAO, PORTA_DEPURACAO, PASTA,
                     rotulo)
from .utils import normalizar
from .voz import falar
from . import memoria

pyautogui.PAUSE = 0.02  # pausa curta entre teclas (o padrão, 0.1s, é lento demais)


# ---------------------------------------------------------------------
# NAVEGADORES SUPORTADOS (todos baseados em Chromium)
# ---------------------------------------------------------------------
# "processos" = nome do programa no Windows (é o jeito mais seguro de saber de
# qual navegador é uma janela). "sufixos" = como o título da janela termina
# (plano B, se não der para ler o processo). "progid" = pedaço do nome que o
# Windows usa para registrar o navegador padrão.
NAVEGADORES = {
    "brave":  {"nome": "Brave", "processos": ("brave.exe",),
               "sufixos": ("- brave",), "progid": "brave",
               "comando": "start brave"},
    "chrome": {"nome": "Google Chrome", "processos": ("chrome.exe",),
               "sufixos": ("- google chrome",), "progid": "chrome",
               "comando": "start chrome"},
    "edge":   {"nome": "Microsoft Edge", "processos": ("msedge.exe",),
               "sufixos": ("- microsoft edge",), "progid": "msedge",
               "comando": "start msedge"},
    "opera":  {"nome": "Opera", "processos": ("opera.exe",),
               "sufixos": ("- opera", "- opera gx"), "progid": "opera",
               "comando": "start opera"},
}
_APELIDOS_NAVEGADOR = {"google chrome": "chrome", "microsoft edge": "edge",
                       "opera gx": "opera", "brave browser": "brave"}
_NOMES_GENERICOS_NAVEGADOR = {"", "auto", "navegador", "o navegador", "browser"}


def _nome_do_processo(hwnd, cache):
    """Nome do programa dono da janela (ex: 'brave.exe'), ou None se não der."""
    if hwnd in cache:
        return cache[hwnd]
    nome = None
    try:
        import ctypes
        import ctypes.wintypes
        pid = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value:
            nome = psutil.Process(pid.value).name().lower()
    except Exception:
        nome = None
    cache[hwnd] = nome
    return nome


def _chave_da_janela(janela, cache):
    """Diz de qual navegador é a janela ('brave', 'chrome'...) ou None."""
    hwnd = getattr(janela, "_hWnd", None)
    processo = _nome_do_processo(hwnd, cache) if hwnd is not None else None
    if processo:
        for chave, dados in NAVEGADORES.items():
            if processo in dados["processos"]:
                return chave
        return None                      # é outro programa
    # Plano B: pelo final do título (o Edge usa um espaço invisível no nome)
    titulo = janela.title.lower().replace("\u200b", "")
    titulo = titulo.replace("\u2013", "-").replace("\u2014", "-").strip()
    for chave, dados in NAVEGADORES.items():
        if titulo.endswith(dados["sufixos"]):
            return chave
    return None


def _janelas_de_navegadores(so=None):
    """Janelas de navegadores abertas, de cima para baixo (a primeira é a que
    você usou por último). Devolve uma lista de (chave, janela). Com 'so'
    ('brave', por exemplo), devolve só as desse navegador."""
    try:
        todas = [j for j in gw.getAllWindows() if j.title.strip()]
    except Exception as erro:
        print(f"{rotulo()}: não consegui listar as janelas ({erro})")
        return []
    cache = {}
    achadas = []
    for janela in todas:
        chave = _chave_da_janela(janela, cache)
        if chave and (so is None or chave == so):
            achadas.append((chave, janela))
    return achadas


def _navegador_padrao_do_windows():
    """O navegador padrão do Windows, se for um dos suportados (senão None)."""
    try:
        import winreg
        caminho = (r"Software\Microsoft\Windows\Shell\Associations"
                   r"\UrlAssociations\https\UserChoice")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, caminho) as chave_reg:
            progid = winreg.QueryValueEx(chave_reg, "ProgId")[0].lower()
    except Exception:
        return None
    for chave, dados in NAVEGADORES.items():
        if dados["progid"] in progid:
            return chave
    return None


def navegador_ativo():
    """Qual navegador controlar agora ('brave', 'chrome', 'edge' ou 'opera').
      - config.json com um navegador fixo: é ele, sempre;
      - "auto": o que estiver aberto (se houver vários, o usado por último);
        se nenhum estiver aberto, o navegador padrão do Windows.
    Devolve None se não conseguir descobrir."""
    if NAVEGADOR_PADRAO in NAVEGADORES:
        return NAVEGADOR_PADRAO
    abertos = _janelas_de_navegadores()
    if abertos:
        return abertos[0][0]
    return _navegador_padrao_do_windows()


def _resolver_navegador(nome=None):
    """Transforma o que foi pedido em uma chave. Vazio ou 'navegador' = o
    navegador configurado (navegador_ativo). Aceita também 'chrome', 'Opera'..."""
    texto = normalizar(nome or "")
    if texto in _NOMES_GENERICOS_NAVEGADOR:
        return navegador_ativo()
    texto = _APELIDOS_NAVEGADOR.get(texto, texto)
    return texto if texto in NAVEGADORES else None


def nome_do_navegador(chave=None):
    """Nome bonito para mensagens (ex: 'Brave'). 'navegador' se não souber."""
    chave = chave or navegador_ativo()
    return NAVEGADORES[chave]["nome"] if chave in NAVEGADORES else "navegador"


def _caminho_do_navegador(chave):
    """Acha o .exe do navegador (registro do Windows, depois pastas comuns)."""
    exe = NAVEGADORES[chave]["processos"][0]
    try:
        import winreg
        for raiz in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(
                        raiz, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as reg:
                    caminho = str(winreg.QueryValueEx(reg, None)[0]).strip('"')
                if caminho and os.path.exists(caminho):
                    return caminho
            except OSError:
                continue
    except Exception:
        pass
    if chave == "opera":
        base = os.environ.get("LOCALAPPDATA", "")
        for pasta in ("Opera GX", "Opera"):
            caminho = os.path.join(base, "Programs", pasta, "opera.exe")
            if os.path.exists(caminho):
                return caminho
    return None


def _abrir_url(url):
    """Abre um site no navegador escolhido (config.json) em vez de sempre usar
    o padrão do Windows. Se não achar o programa, usa o padrão do Windows."""
    chave = navegador_ativo()
    caminho = _caminho_do_navegador(chave) if chave else None
    if caminho:
        try:
            subprocess.Popen([caminho, url],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return
        except OSError:
            pass
    webbrowser.open(url)


# ---------------------------------------------------------------------
# JANELAS (qualquer programa, e o navegador configurado)
# ---------------------------------------------------------------------
def focar_ou_abrir(titulo, alvo):
    """Se já existe uma janela com 'titulo' no nome, traz ela para frente.
    Se não existe, abre 'alvo' (um site ou um comando do Windows).
    Esta função também é usada pelo seu regras.txt."""
    janela_achada = None
    try:
        for janela in gw.getAllWindows():
            if titulo.lower() in janela.title.lower():
                janela_achada = janela
                break
    except Exception as erro:
        print(f"{rotulo()}: não consegui listar as janelas ({erro})")

    if janela_achada:
        try:
            if janela_achada.isMinimized:
                janela_achada.restore()
            janela_achada.activate()
        except Exception:
            pass  # o pygetwindow às vezes reclama mesmo funcionando
        print(f"{rotulo()}: Foquei em -> {janela_achada.title}")
        return True

    print(f"{rotulo()}: Abrindo '{titulo}'...")
    if alvo.startswith("http"):
        _abrir_url(alvo)                    # abre no navegador configurado
    else:
        subprocess.Popen(alvo, shell=True)  # comando do Windows
    return False


def _janela_esta_na_frente(janela):
    """Confere se 'janela' é mesmo a janela ativa (a que recebe o teclado)."""
    try:
        ativa = gw.getActiveWindow()
    except Exception:
        return False
    if ativa is None:
        return False
    h_ativa = getattr(ativa, "_hWnd", None)
    h_janela = getattr(janela, "_hWnd", None)
    if h_ativa is not None and h_janela is not None:
        return h_ativa == h_janela
    return ativa.title == janela.title


def _trazer_para_frente(janela, nome, esperar=0.6):
    """Ativa a janela e CONFIRMA que ela ficou na frente (True/False)."""
    try:
        if janela.isMinimized:
            janela.restore()
        janela.activate()
    except Exception:
        pass  # o pygetwindow às vezes reclama mesmo funcionando; conferimos abaixo

    limite = time.time() + esperar
    while time.time() < limite:
        if _janela_esta_na_frente(janela):
            return True
        time.sleep(0.05)

    print(f"{rotulo()}: não consegui trazer '{nome}' para a frente. "
          "Não mandei o atalho.")
    return False


def focar_janela(titulo, esperar=0.6):
    """Traz para a frente a janela cujo título contém 'titulo' e CONFIRMA que
    ela realmente ficou na frente. Devolve True se deu certo e False se não
    achou a janela ou não conseguiu focar. Para o NAVEGADOR, prefira
    focar_navegador(). O regras.txt usa isso antes de mandar um atalho, assim o
    atalho NUNCA vai parar na janela errada (por exemplo, no seu jogo)."""
    try:
        candidatas = [j for j in gw.getAllWindows()
                      if j.title.strip() and titulo.lower() in j.title.lower()]
    except Exception as erro:
        print(f"{rotulo()}: não consegui listar as janelas ({erro})")
        return False

    if not candidatas:
        print(f"{rotulo()}: não achei nenhuma janela '{titulo}'. Não mandei o atalho.")
        return False

    # Prefere a janela cujo título TERMINA com o nome (ex: "Página - Opera"),
    # para não confundir com uma aba que só cita o nome.
    nome = titulo.lower()
    preferidas = [j for j in candidatas
                  if j.title.lower().rstrip().endswith((nome, nome + " gx"))]
    janela = (preferidas or candidatas)[0]
    return _trazer_para_frente(janela, titulo, esperar)


def _janelas_com(titulo):
    """Todas as janelas abertas cujo título contém 'titulo'."""
    try:
        return [j for j in gw.getAllWindows()
                if j.title.strip() and titulo.lower() in j.title.lower()]
    except Exception as erro:
        print(f"{rotulo()}: não consegui listar as janelas ({erro})")
        return []


def minimizar_app(titulo):
    """Minimiza todas as janelas que tenham 'titulo' no nome (usada pelo regras.txt)."""
    janelas = _janelas_com(titulo)
    if not janelas:
        print(f"{rotulo()}: não achei nenhuma janela '{titulo}'.")
    for janela in janelas:
        try:
            janela.minimize()
        except Exception:
            pass


def maximizar_app(titulo):
    """Maximiza todas as janelas que tenham 'titulo' no nome (usada pelo regras.txt)."""
    janelas = _janelas_com(titulo)
    if not janelas:
        print(f"{rotulo()}: não achei nenhuma janela '{titulo}'.")
    for janela in janelas:
        try:
            janela.maximize()
        except Exception:
            pass


# ---------------------------------------------------------------------
# NAVEGADOR CONFIGURADO (Brave, Chrome, Edge ou Opera)
# ---------------------------------------------------------------------
# Todas aceitam um nome opcional: focar_navegador() usa o navegador do
# config.json; focar_navegador('chrome') usa o Chrome, aconteça o que acontecer.
def focar_navegador(navegador=None, esperar=0.6):
    """Traz o navegador para a frente e CONFIRMA que ele ficou na frente.
    Devolve True/False. Se o navegador não estiver aberto ou não vier para a
    frente, devolve False (e o regras.txt NÃO manda o atalho)."""
    chave = _resolver_navegador(navegador)
    if not chave:
        print(f"{rotulo()}: não descobri qual navegador usar. Não mandei o atalho. "
              "(Defina 'navegador_padrao' no config.json.)")
        return False
    nome = NAVEGADORES[chave]["nome"]
    janelas = _janelas_de_navegadores(chave)
    if not janelas:
        print(f"{rotulo()}: não achei nenhuma janela do {nome}. Não mandei o atalho.")
        return False
    return _trazer_para_frente(janelas[0][1], nome, esperar)


def minimizar_navegador(navegador=None):
    """Minimiza todas as janelas do navegador."""
    chave = _resolver_navegador(navegador)
    janelas = _janelas_de_navegadores(chave) if chave else []
    if not janelas:
        print(f"{rotulo()}: não achei nenhuma janela do {nome_do_navegador(chave)}.")
    for _, janela in janelas:
        try:
            janela.minimize()
        except Exception:
            pass


def maximizar_navegador(navegador=None):
    """Maximiza todas as janelas do navegador."""
    chave = _resolver_navegador(navegador)
    janelas = _janelas_de_navegadores(chave) if chave else []
    if not janelas:
        print(f"{rotulo()}: não achei nenhuma janela do {nome_do_navegador(chave)}.")
    for _, janela in janelas:
        try:
            janela.maximize()
        except Exception:
            pass


def abrir_navegador(navegador=None):
    """Foca o navegador se já estiver aberto; se não, abre ele.
    Devolve True se ele já estava aberto."""
    chave = _resolver_navegador(navegador)
    if not chave:
        print(f"{rotulo()}: não descobri qual navegador abrir. "
              "(Defina 'navegador_padrao' no config.json.)")
        return False
    nome = NAVEGADORES[chave]["nome"]
    janelas = _janelas_de_navegadores(chave)
    if janelas:
        janela = janelas[0][1]
        try:
            if janela.isMinimized:
                janela.restore()
            janela.activate()
        except Exception:
            pass
        print(f"{rotulo()}: Foquei em -> {janela.title}")
        return True
    print(f"{rotulo()}: Abrindo o {nome}...")
    subprocess.Popen(NAVEGADORES[chave]["comando"], shell=True)
    return False


# ---------------------------------------------------------------------
# CONFIRMAÇÃO POR VOZ (para ações perigosas, como fechar a janela)
# ---------------------------------------------------------------------
# A ação perigosa NÃO é executada na hora: o robô pergunta, e só executa se
# a PRÓXIMA frase for um "sim". Qualquer outra coisa (ou 10 segundos de
# silêncio) cancela o pedido.
TEMPO_CONFIRMACAO = 10  # segundos para você responder
PALAVRAS_SIM = {"sim", "pode", "pode sim", "confirma", "confirmo",
                "pode fechar", "isso mesmo", "claro"}
PALAVRAS_NAO = {"nao", "nao quero", "deixa", "deixa pra la", "cancela",
                "cancelar", "calma", "para"}

_pendente = None                 # (função a executar, hora em que expira)
_trava_confirmacao = threading.Lock()


def confirmar(pergunta, funcao):
    """Pergunta em voz alta e guarda 'funcao' para executar só se você disser sim."""
    global _pendente
    with _trava_confirmacao:
        _pendente = (funcao, time.time() + TEMPO_CONFIRMACAO)
    falar(pergunta)


def resolver_confirmacao(comando):
    """Chamada pelo main.py a cada frase ouvida. Devolve True se a frase foi
    a resposta de uma confirmação pendente (então o main não faz mais nada
    com ela) e False se não tem nada pendente ou se a frase era outro assunto
    (nesse caso o pedido pendente é descartado e a frase segue o caminho normal)."""
    global _pendente
    with _trava_confirmacao:
        pendente, _pendente = _pendente, None
    if pendente is None:
        return False

    funcao, expira_em = pendente
    if time.time() > expira_em:
        return False                      # demorou demais: pedido esquecido

    if comando in PALAVRAS_SIM:
        print(f"{rotulo()}: Confirmado.")
        try:
            funcao()
        except Exception as erro:
            print(f"{rotulo()}: erro ao executar a ação confirmada: {erro}")
        return True
    if comando in PALAVRAS_NAO:
        print(f"{rotulo()}: Ok, não vou fazer.")
        return True
    return False


# ---------------------------------------------------------------------
# CONTROLE INTERNO DO NAVEGADOR (Playwright + porta de depuração)
# ---------------------------------------------------------------------
# Em vez de adivinhar onde clicar na imagem da tela, conversamos com o
# navegador "por dentro": o Playwright lê a página do YouTube e clica no vídeo
# certo, sem mexer no mouse de verdade (então não atrapalha o jogo).
# Funciona igual no Brave, Chrome, Edge e Opera (todos usam Chromium).
#
# REQUISITOS:
#   1) pip install playwright   (não precisa baixar navegadores)
#   2) o navegador aberto com a porta de depuração, por exemplo com este
#      parâmetro no atalho dele:   --remote-debugging-port=9222
#      (a porta é a "navegador_porta_debug" do config.json).
#      Se a porta não abrir (navegadores novos, como o Chrome, ignoram a porta
#      no perfil normal), acrescente também:
#          --user-data-dir="D:\ia\<navegador>_debug"
#      (é um perfil separado: faça login no YouTube nele uma vez).
ENDERECO_DEPURACAO = f"http://127.0.0.1:{PORTA_DEPURACAO}"   # 127.0.0.1 evita um bug de IPv6 do Windows
_trava_navegador = threading.Lock()      # uma ação no navegador por vez


class ErroNavegador(Exception):
    """Problema ao controlar o navegador. A 'mensagem' (completa) vai pro chat e
    a 'fala' (curta) é o que ela pode dizer em voz alta."""

    def __init__(self, mensagem, fala=None):
        super().__init__(mensagem)
        self.fala = fala or mensagem


def _porta_de_depuracao_aberta():
    """Teste rápido: tem alguém ouvindo na porta de depuração?"""
    try:
        with socket.create_connection(("127.0.0.1", PORTA_DEPURACAO), timeout=0.6):
            return True
    except OSError:
        return False


@contextlib.contextmanager
def conectar_navegador():
    """Conecta ao navegador que JÁ está aberto, pela porta de depuração.
    Uso:   with conectar_navegador() as navegador: ...
    Se não for possível (Playwright faltando, navegador sem a porta, etc.)
    levanta ErroNavegador com uma mensagem amigável. Quem usa deve tratar o
    erro, e nada disso derruba o programa."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ErroNavegador(
            "O Playwright não está instalado. Rode no terminal: pip install playwright",
            "Falta instalar o Playwright.") from None

    chave = navegador_ativo()
    nome = nome_do_navegador(chave)

    if not _porta_de_depuracao_aberta():
        perfil = os.path.join(os.path.dirname(PASTA), f"{chave or 'navegador'}_debug")
        raise ErroNavegador(
            f"O {nome} não está aberto com a porta de depuração ({PORTA_DEPURACAO}). "
            f"Feche o {nome} e abra de novo com o parâmetro --remote-debugging-port="
            f"{PORTA_DEPURACAO}. Se a porta continuar fechada, acrescente também "
            f"--user-data-dir=\"{perfil}\" (perfil separado).",
            f"O {nome} não está com a depuração ligada.")

    with _trava_navegador:
        with sync_playwright() as playwright:
            try:
                navegador = playwright.chromium.connect_over_cdp(
                    ENDERECO_DEPURACAO, timeout=5000)
            except Exception as erro:
                raise ErroNavegador(
                    f"Não consegui conectar ao {nome} na porta {PORTA_DEPURACAO} ({erro}).",
                    f"Não consegui conectar ao {nome}.") from None
            # Ao sair, o Playwright só desliga a conexão: o navegador continua aberto.
            yield navegador


# Palavras que significam a posição de um vídeo
_ORDINAIS = {"primeiro": 1, "primeira": 1, "um": 1, "segundo": 2, "dois": 2,
             "terceiro": 3, "tres": 3, "quarto": 4, "quatro": 4, "quinto": 5,
             "cinco": 5, "sexto": 6, "seis": 6, "setimo": 7, "sete": 7,
             "oitavo": 8, "oito": 8, "nono": 9, "nove": 9, "decimo": 10, "dez": 10}
MAX_POSICAO_VIDEO = 20


def _interpretar_posicao(valor):
    """Aceita 2, '2', '2º', 'segundo'... e devolve o número (ou None)."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        numero = int(valor)
    else:
        texto = normalizar(str(valor))
        digitos = re.search(r"\d+", texto)
        if digitos:
            numero = int(digitos.group())
        else:
            numero = next((n for p, n in _ORDINAIS.items() if p in texto.split()), None)
    if numero is None or not (1 <= numero <= MAX_POSICAO_VIDEO):
        return None
    return numero


def _ordenar_leitura(candidatos):
    """Ordena como se lê: linha de cima primeiro, e dentro da linha, da esquerda
    pra direita. Assim o 'primeiro vídeo' é o do canto superior esquerdo."""
    # Lateral do vídeo (uma coluna só): simplesmente de cima para baixo.
    if candidatos and all(c.get("lateral") for c in candidatos):
        return sorted(candidatos, key=lambda c: (c["top"], c["left"]))
    linhas = []
    for c in sorted(candidatos, key=lambda c: c["top"]):
        if linhas and abs(c["top"] - linhas[-1][0]["top"]) <= 40:
            linhas[-1].append(c)
        else:
            linhas.append([c])
    return [c for linha in linhas for c in sorted(linha, key=lambda c: c["left"])]


# Roda DENTRO da página do YouTube e devolve as miniaturas de vídeo que estão
# visíveis na tela (sem Shorts, sem os links pequenos de título).
#  - Na página inicial / busca: todas as miniaturas visíveis.
#  - ASSISTINDO a um vídeo (/watch): só os recomendados da LATERAL direita
#    (#related, ytd-compact-video-renderer, ytd-rich-item-renderer e os cards
#    novos yt-lockup-view-model), sem o vídeo que já está tocando, sem a lista
#    de reprodução, sem comentários e sem chat.
#  - NÃO usa elementFromPoint: uma janela por cima da página (como a do
#    assistente) não faz o vídeo ser descartado.
#  - Por vídeo, prefere o link da MINIATURA (a#thumbnail); se não houver, o
#    maior link do card. A ordenação final (de cima para baixo) é feita em
#    _ordenar_leitura.
_JS_VIDEOS_NA_TELA = """
() => {
  const largura = document.documentElement.clientWidth || window.innerWidth;
  const altura = document.documentElement.clientHeight || window.innerHeight;
  const assistindo = location.pathname.startsWith('/watch');
  const atual = new URLSearchParams(location.search).get('v');      // vídeo que está tocando
  const EXCLUIR = 'ytd-playlist-panel-renderer, ytd-miniplayer, ytd-live-chat-frame, #chat, ytd-comments';
  const LATERAIS = [
    '#related a#thumbnail',
    'ytd-watch-next-secondary-results-renderer a#thumbnail',
    'ytd-compact-video-renderer a#thumbnail',
    'ytd-rich-item-renderer a#thumbnail',
    'yt-lockup-view-model a[href*="/watch?v="]',
    '#related a[href*="/watch?v="]',
    '#secondary a[href*="/watch?v="]'
  ].join(', ');
  const CARTAO = 'ytd-video-renderer, ytd-rich-item-renderer, ytd-compact-video-renderer, ytd-grid-video-renderer, yt-lockup-view-model';

  const coletar = (ancoras, lateral, minL, minA) => {
    const achados = new Map();
    for (const a of ancoras) {
      if (a.closest(EXCLUIR)) continue;
      let id = null;
      try { id = new URL(a.href, location.href).searchParams.get('v'); } catch (e) {}
      if (!id || id === atual) continue;                             // ignora o que já está tocando
      const r = a.getBoundingClientRect();
      if (r.width < minL || r.height < minA) continue;               // só miniaturas
      const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      if (cx < 0 || cx > largura || cy < 0 || cy > altura) continue; // só o que está na tela
      const estilo = getComputedStyle(a);
      if (estilo.visibility === 'hidden' || estilo.display === 'none') continue;
      const miniatura = a.id === 'thumbnail' || /thumbnail|content-image/i.test(String(a.className || ''));
      const area = r.width * r.height;
      const anterior = achados.get(id);
      if (anterior) {
        if (anterior.miniatura && !miniatura) continue;              // já temos o link da miniatura
        if (anterior.miniatura === miniatura && anterior.area >= area) continue;
      }
      const cartao = a.closest(CARTAO);
      const alvoTitulo = cartao ? cartao.querySelector('#video-title, h3, [title]') : null;
      const titulo = (a.getAttribute('title') || a.getAttribute('aria-label') ||
                      (alvoTitulo && (alvoTitulo.getAttribute('title') || alvoTitulo.textContent)) || '').trim();
      achados.set(id, {id: id, x: cx, y: cy, top: r.top, left: r.left, area: area,
                       livre: true, miniatura: miniatura, titulo: titulo, lateral: lateral});
    }
    return Array.from(achados.values());
  };

  if (assistindo) {
    // Assistindo: os vídeos clicáveis são os recomendados da barra lateral direita
    const ancoras = Array.from(document.querySelectorAll(LATERAIS));
    let achados = coletar(ancoras, true, 100, 50);
    if (!achados.length) achados = coletar(ancoras, true, 50, 28);   // lateral estreita: aceita miniaturas menores
    if (achados.length) return achados;
  }
  return coletar(document.querySelectorAll('a[href*="/watch?v="]'), false, 100, 50);
}
"""

HOSTS_YOUTUBE = ("www.youtube.com", "youtube.com", "m.youtube.com")
_TIPOS_IGNORADOS = ("canal", "shorts")                 # nunca escolhidas
_ORDEM_DOS_TIPOS = {"inicio": 0, "video": 1, "busca": 2, "outra": 3}


def _tipo_de_aba_youtube(url):
    """Classifica a aba pelo endereço:
    'inicio' (youtube.com/), 'video' (/watch), 'busca' (/results), 'outra',
    e as que são IGNORADAS: 'canal' (@canal, /channel/, /c/, /user/) e 'shorts'."""
    try:
        caminho = urlparse(url).path or "/"
    except Exception:
        return "outra"
    if caminho.startswith(("/@", "/channel/", "/c/", "/user/")):
        return "canal"
    if caminho.startswith("/shorts"):
        return "shorts"
    if caminho == "/":
        return "inicio"
    if caminho.startswith("/watch"):
        return "video"
    if caminho.startswith("/results"):
        return "busca"
    return "outra"


def _aba_visivel(pagina):
    """True se é a aba que está aparecendo agora no navegador."""
    try:
        return pagina.evaluate("document.visibilityState") == "visible"
    except Exception:
        return False


def _video_tocando(pagina):
    """True se a aba tem um vídeo tocando neste momento."""
    try:
        return bool(pagina.evaluate(
            "(() => { const v = document.querySelector('video'); "
            "return !!v && !v.paused && !v.ended; })()"))
    except Exception:
        return False


def _escolher_pagina_youtube(navegador):
    """Acha a aba do YouTube que vai receber o clique e devolve
    (pagina, esta_visivel).

    PRIORIDADE ABSOLUTA: a aba que está na sua tela agora
    (visibilityState == 'visible'). Se ela for do YouTube, é ela e pronto: nenhuma
    aba em segundo plano concorre com ela, nem a que está tocando vídeo.
    (Se houver mais de uma janela com aba visível do YouTube, desempata: a que
    tem vídeo tocando, depois início, /watch, busca e o resto.)

    Só se a aba da tela NÃO for do YouTube é que olhamos as de segundo plano.
    Aí abas de canais de criadores (@canal, /channel/...) e Shorts são IGNORADAS,
    pra não pular para as abas secundárias das suas ilhas de abas, e a ordem é:
    a que tem vídeo tocando, depois a página inicial, depois /watch, busca e o resto."""
    todas = []                      # (pagina, tipo, visivel)
    for contexto in navegador.contexts:
        for pagina in contexto.pages:
            try:
                host = urlparse(pagina.url).hostname or ""
            except Exception:
                continue
            if host not in HOSTS_YOUTUBE:
                continue
            todas.append((pagina, _tipo_de_aba_youtube(pagina.url),
                          _aba_visivel(pagina)))

    # 1) A aba que está na tela e é do YouTube (qualquer tipo) vence sempre.
    na_tela = [(pagina, tipo) for pagina, tipo, visivel in todas if visivel]
    if na_tela:
        pontuadas = []
        for ordem, (pagina, tipo) in enumerate(na_tela):
            tocando = tipo == "video" and _video_tocando(pagina)
            pontuadas.append(((0 if tocando else 1, _ORDEM_DOS_TIPOS.get(tipo, 3),
                               ordem), pagina))
        pontuadas.sort(key=lambda item: item[0])
        return pontuadas[0][1], True

    # 2) Nenhuma aba do YouTube na tela: olha as de segundo plano.
    candidatas = [(pagina, tipo) for pagina, tipo, _ in todas
                  if tipo not in _TIPOS_IGNORADOS]
    ignoradas = len(todas) - len(candidatas)

    if not candidatas:
        if ignoradas:
            raise ErroNavegador(
                "Só achei abas de canais ou Shorts do YouTube, e elas são ignoradas. "
                "Abra a página inicial do YouTube ou um vídeo.",
                "Só achei abas de canais do YouTube.")
        nome = nome_do_navegador()
        raise ErroNavegador(f"Não achei nenhuma aba do YouTube aberta no {nome}.",
                            f"Não achei o YouTube aberto no {nome}.")

    pontuadas = []
    for ordem, (pagina, tipo) in enumerate(candidatas):
        tocando = tipo == "video" and _video_tocando(pagina)
        pontuadas.append(((0 if tocando else 1, _ORDEM_DOS_TIPOS[tipo], ordem),
                          pagina))
    pontuadas.sort(key=lambda item: item[0])
    return pontuadas[0][1], False


def executar_clique_video(posicao):
    """Clica no N-ésimo vídeo que aparece na tela do YouTube.
    Devolve (deu_certo, mensagem_completa, frase_curta_para_falar).
    Nunca levanta erro: se algo falhar, só devolve o aviso."""
    numero = _interpretar_posicao(posicao)
    if numero is None:
        return (False, f"Não entendi qual vídeo ('{posicao}'). Diga primeiro, "
                       "segundo, terceiro...", "Não entendi qual vídeo.")
    try:
        with conectar_navegador() as navegador:
            pagina, visivel = _escolher_pagina_youtube(navegador)
            if not visivel:
                try:
                    pagina.bring_to_front()      # a aba precisa estar à frente pra clicar
                except Exception:
                    pass
            candidatos = pagina.evaluate(_JS_VIDEOS_NA_TELA) or []
            livres = [c for c in candidatos if c.get("livre")] or candidatos
            ordenados = _ordenar_leitura(livres)
            if not ordenados:
                raise ErroNavegador("Não encontrei vídeos na tela do YouTube.",
                                    "Não vejo vídeos na tela.")
            if numero > len(ordenados):
                raise ErroNavegador(
                    f"Só vejo {len(ordenados)} vídeo(s) na tela, não dá pra clicar no {numero}º.",
                    f"Só vejo {len(ordenados)} vídeos na tela.")
            alvo = ordenados[numero - 1]
            pagina.mouse.click(alvo["x"], alvo["y"])    # clique dentro da página, sem mexer no mouse do PC
            titulo = (alvo.get("titulo") or "").strip()
            origem = " da lateral" if alvo.get("lateral") else ""
            texto = (f"Cliquei no {numero}º vídeo{origem}"
                     + (f": {titulo[:80]}" if titulo else "."))
            return True, texto, ""
    except ErroNavegador as erro:
        return False, str(erro), erro.fala
    except Exception as erro:
        return (False, f"Não consegui controlar o navegador ({erro}).",
                "Não consegui controlar o navegador.")


def clicar_video(posicao: int) -> str:
    """Clica no vídeo da posição indicada na tela do YouTube que está aberto
    no navegador (Brave, Chrome, Edge ou Opera; 1 = primeiro vídeo, 2 = segundo,
    3 = terceiro...). Use quando o usuário pedir para clicar ou abrir o primeiro,
    segundo, terceiro vídeo. Se o usuário já estiver assistindo a um vídeo, a
    posição vale para os vídeos recomendados da lateral direita. Abas de canais
    são ignoradas. Só funciona se o navegador estiver aberto com a porta de
    depuração."""
    return executar_clique_video(posicao)[1]


def abrir_app(nome: str) -> str:
    """Abre (ou traz para a frente) um aplicativo ou site pelo nome.
    Exemplos de nome: youtube, netflix, discord, tiktok, navegador, brave,
    chrome, edge, opera, calculadora, bloco de notas, ou um endereço de site
    como github.com."""
    nome_limpo = normalizar(nome)

    # 0) Navegadores: "navegador" (o configurado), "brave", "chrome", "edge", "opera"
    if (nome_limpo in _NOMES_GENERICOS_NAVEGADOR or nome_limpo in NAVEGADORES
            or nome_limpo in _APELIDOS_NAVEGADOR):
        chave = _resolver_navegador(nome_limpo)
        if not chave:
            return ("Não consegui descobrir qual navegador abrir. "
                    "Defina 'navegador_padrao' no config.json.")
        abrir_navegador(chave)
        return f"{NAVEGADORES[chave]['nome']} aberto"

    # 1) Procura no dicionário APPS_E_SITES (nome exato, depois por trecho)
    chave = nome_limpo if nome_limpo in APPS_E_SITES else next(
        (k for k in APPS_E_SITES if k in nome_limpo), None)
    if chave:
        titulo, alvo = APPS_E_SITES[chave]
        focar_ou_abrir(titulo, alvo)
        return f"{chave} aberto"

    # 2) Se parece um endereço de site (tem ponto e não tem espaço), abre ele
    if "." in nome.strip() and " " not in nome.strip():
        endereco = nome.strip()
        if not endereco.startswith("http"):
            endereco = "https://" + endereco
        _abrir_url(endereco)
        return f"site {endereco} aberto"

    return f"Não conheço '{nome}'. Adicione no dicionário APPS_E_SITES."


def atalho(teclas: str) -> str:
    """Pressiona um atalho de teclado. Separe as teclas com +.
    Exemplos: 'ctrl+w' (fecha aba), 'ctrl+tab' (próxima aba), 'alt+f4'
    (fecha janela, mas antes o assistente pede confirmação ao usuário),
    'win+d' (área de trabalho), 'playpause' (play/pause)."""
    lista = [t.strip().lower() for t in teclas.split("+") if t.strip()]

    if not lista or len(lista) > 4:
        return "Atalho inválido: use de 1 a 4 teclas separadas por +."

    # Só aceita teclas que o pyautogui realmente conhece
    invalidas = [t for t in lista if t not in pyautogui.KEYBOARD_KEYS]
    if invalidas:
        return f"Teclas desconhecidas: {', '.join(invalidas)}"

    # Fechar janela é perigoso (pode perder um jogo sem salvar): pede confirmação
    if set(lista) == {"alt", "f4"}:
        confirmar("Tem certeza que quer fechar a janela?",
                  lambda: pyautogui.hotkey("alt", "f4"))
        return "Pedi confirmação ao usuário. Não diga mais nada e aguarde."

    pyautogui.hotkey(*lista)
    return f"atalho {'+'.join(lista)} executado"


def definir_volume(nivel: int) -> str:
    """Define o volume do computador para um valor exato de 0 a 100."""
    try:
        nivel = max(0, min(100, int(nivel)))
    except (TypeError, ValueError):
        return "Nível de volume inválido."

    # Cada toque de tecla muda 2% do volume. Então: zera tudo (50 toques
    # para baixo) e sobe até o nível pedido (nivel / 2 toques para cima).
    pyautogui.press("volumedown", presses=50)
    pyautogui.press("volumeup", presses=nivel // 2)
    return f"volume em {nivel}"


def mudar_volume(acao: str) -> str:
    """Muda o volume aos poucos. O parâmetro 'acao' deve ser exatamente um
    destes: 'aumentar', 'diminuir' ou 'mutar' (liga/desliga o mudo)."""
    acao = normalizar(acao)
    if acao.startswith("aument"):
        pyautogui.press("volumeup", presses=5)       # +10%
    elif acao.startswith("diminu"):
        pyautogui.press("volumedown", presses=5)     # -10%
    elif acao.startswith("mut"):
        pyautogui.press("volumemute")
    else:
        return "Ação inválida: use aumentar, diminuir ou mutar."
    return f"volume: {acao}"


# Lista oficial de ferramentas. A IA SÓ consegue executar o que estiver aqui.
FERRAMENTAS = {f.__name__: f for f in
               [abrir_app, atalho, definir_volume, mudar_volume,
                memoria.salvar_memoria, clicar_video]}


def executar_ferramenta(nome, argumentos):
    """Executa a ferramenta que a IA escolheu e devolve o resultado em texto.
    Se a IA pedir algo que não existe ou errar os parâmetros, apenas
    devolvemos uma mensagem de erro (ela pode tentar de novo)."""
    funcao = FERRAMENTAS.get(nome)
    if funcao is None:
        return f"A ferramenta '{nome}' não existe."
    try:
        print(f"[Ferramenta]: {nome}({dict(argumentos)})")
        return str(funcao(**argumentos))
    except TypeError:
        return "Parâmetros errados para essa ferramenta."
    except Exception as erro:
        return f"Erro ao executar: {erro}"


def tem_confirmacao_pendente():
    """True se existe uma pergunta esperando resposta ('sim'/'não').
    Usado pelo main.py pra deixar 'sim'/'não' passarem pelo filtro
    da palavra de ativação."""
    with _trava_confirmacao:
        return _pendente is not None

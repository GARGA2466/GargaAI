# =====================================================================
#   config.py - Configurações do GargaAI
# =====================================================================
# A maioria dos ajustes agora fica no arquivo config.json (na pasta
# principal). Este arquivo lê o config.json e entrega os valores para o
# resto do programa. Se o config.json estiver vazio, faltando ou com erro,
# o programa avisa e usa os valores PADRÃO que estão logo abaixo.
import os
import re
import copy
import json
import shutil

from .utils import normalizar

# Pasta PRINCIPAL do GargaAI (onde ficam o main.py, o regras.txt e o
# config.json). Este arquivo está dentro da pasta "ia", então subimos um nível.
PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMINHO_REGRAS = os.path.join(PASTA, "regras.txt")
CAMINHO_CONFIG = os.path.join(PASTA, "config.json")
CAMINHO_MEMORIA = os.path.join(PASTA, "memoria.json")   # o "diário" do assistente

# PERSONALIDADE: este texto diz à IA quem ela é e como deve se comportar.
# Por enquanto é neutro e fica aqui no código. Mais pra frente ele também
# vai para o config.json.
PROMPT_SISTEMA = (
    "Você é o GargaAI, um assistente de voz que controla o computador do "
    "usuário no Windows. "
    "Quando o usuário pedir uma ação (abrir app ou site, atalho de teclado, "
    "volume), use as ferramentas disponíveis. "
    "Se não existir ferramenta para o pedido, diga isso com honestidade. "
    # (O tamanho das respostas vem do MODO: trabalho ou conversa, em modos.py)
    "Sua resposta será falada em voz alta: não use markdown, listas nem emojis."
)

# ---------------------------------------------------------------------
# VALORES PADRÃO (usados quando o config.json não diz nada ou tem erro)
# ---------------------------------------------------------------------
PADRAO = {
    # Modelo da IA. Precisa SUPORTAR ferramentas (tool calling).
    # Instale uma vez no terminal com:  ollama pull qwen2.5:7b
    # Outras boas opções: qwen3:8b, llama3.1:8b
    "modelo": "qwen2.5:7b",
    "idioma": "auto",              # "auto" (segue o Windows), "pt" ou "en"
    "palavra_ativacao": "",        # vazio = primeira vez, precisa perguntar
    # Jeitos que o Google pode entender o nome errado (ex: ["fiume", "fu yumi"]).
    "variacoes_palavra": [],
    "modo_escuta": "palavra_ativacao",  # "sempre" | "palavra_ativacao"
    # "janela" = interface gráfica bonita | "terminal" = só a tela preta (plano B)
    "interface": "janela",
    # Modo do assistente: "conversa" (amigável, dialoga) ou "trabalho" (respostas
    # mínimas, ideal para jogar). Troca por voz: "modo trabalho" / "modo conversa".
    "modo_padrao": "conversa",
    "lembrar_modo": True,          # True = o modo escolhido por voz fica salvo como padrão
    "trabalho_silencioso": False,  # True = no modo trabalho ela não fala nada
    "tecla_escuta": "f8",
    # Tecla de FORMATAR (apaga o nome e as configurações). Aperte DUAS vezes,
    # com até 5 segundos entre elas. "" = desativada.
    "tecla_formatar": "ctrl+f12",          # tecla liga/desliga (não perturbe). "" = desativada
    "janela_escuta": 10,           # segundos pra falar o pedido depois de dizer só o nome
    "tempo_max_frase": 8,          # segundos máximos de cada frase captada
    "max_passos_ia": 4,            # ferramentas seguidas que a IA pode usar por pedido
    "limite_palavras_regra": 8,    # frases mais longas vão direto pra IA
    "memoria_mensagens": 8,        # mensagens recentes que a IA lembra
    "diario_max_itens": 30,        # anotações da memória de longo prazo (memoria.json)
    # Quanto tempo o modelo fica carregado na memória depois do último uso.
    # Exemplos: "30m" (30 minutos), "2h" (2 horas), "-1m" (para sempre),
    # "0" (descarrega na hora, libera memória mas a próxima resposta demora).
    "manter_modelo": "30m",
    # Navegador que o assistente controla (focar, atalhos, fechar, clique em
    # vídeo do YouTube): "auto" (usa o que estiver aberto no momento; se nenhum
    # estiver, o padrão do Windows), "brave", "chrome", "edge" ou "opera".
    "navegador_padrao": "auto",
    # Porta de depuração do navegador. Só o clique em vídeos usa. O navegador
    # precisa ser aberto com --remote-debugging-port=<esta porta>.
    "navegador_porta_debug": 9222,
    # "nome falado": ["texto do título da janela", "o que executar"]
    #   - se o 2º valor começa com "http", abre no navegador padrão
    #   - senão, é um comando do Windows (ex: "start discord:", "calc")
    "apps_e_sites": {
        "youtube":        ["youtube", "https://www.youtube.com"],
        "netflix":        ["netflix", "https://www.netflix.com"],
        "tiktok":         ["tiktok", "https://www.tiktok.com"],
        "google":         ["google", "https://www.google.com"],
        "discord":        ["discord", "start discord:"],
        "opera":          ["opera", "start opera"],
        "calculadora":    ["calculadora", "calc"],
        "bloco de notas": ["bloco de notas", "notepad"],
    },
    "palavras_cancelar": ["cancela", "cancelar", "cancel", "stop", "abort",
                          "abortar", "calma", "espera"],
    "frases_cancelar": ["para", "pare", "para ai", "para tudo", "pare tudo"],
    "frases_sair": ["encerrar programa", "sair", "exit", "quit"],
}


# ---------------------------------------------------------------------
# LEITURA DO config.json (com proteção contra erros)
# ---------------------------------------------------------------------
def _eh_numero_inteiro_positivo(valor):
    # "bool" também é int no Python (True == 1), então excluímos de propósito
    return isinstance(valor, int) and not isinstance(valor, bool) and valor >= 1


def _eh_lista_de_textos(valor):
    return isinstance(valor, list) and all(isinstance(v, str) for v in valor)


def _eh_dicionario_de_apps(valor):
    """Cada app precisa ter o formato: "nome": ["titulo da janela", "alvo"]."""
    if not isinstance(valor, dict) or not valor:
        return False
    return all(isinstance(v, (list, tuple)) and len(v) == 2
               and all(isinstance(x, str) for x in v)
               for v in valor.values())


NAVEGADORES_VALIDOS = ("auto", "brave", "chrome", "edge", "opera")


def _valor_valido(chave, valor):
    """Confere se o valor do config.json tem o tipo certo para aquela chave."""
    if chave == "modelo":
        return isinstance(valor, str) and valor.strip() != ""
    if chave == "idioma":
        return valor in ("auto", "pt", "en")
    if chave == "palavra_ativacao":
        # Aceita string vazia (primeira vez) ou com nome dentro
        return isinstance(valor, str)
    if chave == "modo_escuta":
        return valor in ("sempre", "palavra_ativacao")
    if chave == "interface":
        return valor in ("janela", "terminal")
    if chave in ("tecla_escuta", "tecla_formatar"):
        return isinstance(valor, str)      # vazio desativa a tecla
    if chave == "variacoes_palavra":
        return _eh_lista_de_textos(valor)
    if chave == "modo_padrao":
        return valor in ("conversa", "trabalho")
    if chave in ("lembrar_modo", "trabalho_silencioso"):
        return isinstance(valor, bool)
    if chave == "manter_modelo":
        return (isinstance(valor, str)
                and re.fullmatch(r"0|-?\d+(\.\d+)?[smh]", valor.strip()) is not None)
    if chave in ("tempo_max_frase", "max_passos_ia", "limite_palavras_regra",
                 "memoria_mensagens", "janela_escuta", "diario_max_itens"):
        return _eh_numero_inteiro_positivo(valor)
    if chave == "navegador_padrao":
        return isinstance(valor, str) and valor.strip().lower() in NAVEGADORES_VALIDOS
    if chave == "navegador_porta_debug":
        return (isinstance(valor, int) and not isinstance(valor, bool)
                and 1024 <= valor <= 65535)
    if chave == "apps_e_sites":
        return _eh_dicionario_de_apps(valor)
    if chave in ("palavras_cancelar", "frases_cancelar", "frases_sair"):
        return _eh_lista_de_textos(valor)
    return False


def carregar_config():
    """Lê o config.json e devolve os ajustes. Qualquer problema vira um
    aviso claro no terminal e o valor padrão é usado no lugar."""
    cfg = dict(PADRAO)

    if not os.path.exists(CAMINHO_CONFIG):
        print("[Config]: config.json não encontrado. Usando valores padrão.")
        return cfg

    try:
        # utf-8-sig aceita o arquivo mesmo se o Bloco de Notas salvar com BOM
        with open(CAMINHO_CONFIG, "r", encoding="utf-8-sig") as arquivo:
            texto = arquivo.read()
    except OSError as erro:
        print(f"[Config]: não consegui abrir o config.json ({erro}). "
              "Usando valores padrão.")
        return cfg

    if not texto.strip():
        return cfg  # arquivo vazio: usa os padrões, sem drama

    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as erro:
        print(f"[Config]: erro no config.json, linha {erro.lineno}, coluna "
              f"{erro.colno}: {erro.msg}. Usando valores padrão.")
        print("[Config]: dica: confira aspas, vírgulas e chaves perto dessa linha.")
        return cfg

    if not isinstance(dados, dict):
        print("[Config]: o config.json precisa começar com { e terminar com }. "
              "Usando valores padrão.")
        return cfg

    for chave, valor in dados.items():
        if chave.startswith("_"):
            continue  # chaves começando com _ são só comentários
        if chave not in PADRAO:
            print(f"[Config]: '{chave}' não é uma configuração conhecida. Ignorei.")
        elif _valor_valido(chave, valor):
            cfg[chave] = valor
        else:
            print(f"[Config]: valor inválido em '{chave}'. "
                  f"Usando o padrão: {PADRAO[chave]}")
    return cfg


def salvar_no_config(chave, valor):
    """Grava um valor no config.json sem estragar o resto do arquivo.
    Proteções:
      - se o config.json tiver algum erro, NÃO sobrescreve (pra você não
        perder suas configurações) e avisa;
      - guarda uma cópia do arquivo antigo em config.json.bak;
      - grava num arquivo temporário e só depois troca, então uma queda de
        energia no meio não deixa o config.json pela metade."""
    dados = {}
    if os.path.exists(CAMINHO_CONFIG):
        try:
            with open(CAMINHO_CONFIG, "r", encoding="utf-8-sig") as arquivo:
                texto = arquivo.read()
            if texto.strip():
                dados = json.loads(texto)
        except (OSError, json.JSONDecodeError) as erro:
            print(f"[Config]: o config.json tem um erro ({erro}). Pra não perder "
                  "suas configurações, NÃO vou sobrescrever o arquivo.")
            print("[Config]: corrija o erro no config.json e tente de novo.")
            return False
        if not isinstance(dados, dict):
            print("[Config]: o config.json não está no formato esperado. "
                  "Não vou sobrescrever.")
            return False

    dados[chave] = valor

    try:
        if os.path.exists(CAMINHO_CONFIG):
            shutil.copy2(CAMINHO_CONFIG, CAMINHO_CONFIG + ".bak")
        temporario = CAMINHO_CONFIG + ".tmp"
        with open(temporario, "w", encoding="utf-8") as arquivo:
            json.dump(dados, arquivo, ensure_ascii=False, indent=2)
        os.replace(temporario, CAMINHO_CONFIG)
        return True
    except OSError as erro:
        print(f"[Config]: não consegui salvar no config.json ({erro}).")
        return False


# ---------------------------------------------------------------------
# IDIOMA AUTOMÁTICO (português ou inglês, conforme o seu Windows)
# ---------------------------------------------------------------------
def detectar_idioma():
    """Pergunta ao Windows qual é o idioma da interface.
    Retorna "pt" se for português e "en" para qualquer outro idioma."""
    try:
        import ctypes
        # O Windows devolve um número; os 8 bits finais identificam o idioma
        # principal. O número 0x16 significa Português.
        codigo = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return "pt" if (codigo & 0xFF) == 0x16 else "en"
    except Exception:
        return "pt"  # se não conseguir descobrir, assume português


# Todos os textos que o programa fala/mostra, nos dois idiomas
TEXTOS = {
    "pt": {
        "reconhecimento": "pt-BR",
        "voz_busca": ["portuguese", "brazil", "pt-br"],
        "pronto": "{nome} online e ouvindo!",
        "voce_disse": "Você disse",
        "cancelado": "Ação cancelada!",
        "tchau": "Até logo, chefe!",
        "pensando": "Pensando... (diga 'cancela' ou 'calma' para parar)",
        "feito": "Pronto!",
        "sem_ollama": "Não consegui falar com o Ollama. Ele está rodando?",
        "instrucao_idioma": "Responda sempre em português do Brasil.",
        "primeiro_nome": "Primeiro acesso detectado! Qual será o meu nome?",
        "nome_salvo": "Perfeito! Agora eu me chamo",
        "pode_falar": "Oi! Pode falar.",
        "memoria_vazia": "Ainda não tenho nada anotado sobre você.",
        "memoria_intro": "Eu lembro disto sobre você:",
        "memoria_e_mais": "E mais {n} anotações.",
        "pergunta_limpar_memoria": "Tem certeza que quer apagar tudo o que eu lembro sobre você?",
        "memoria_apagada": "Pronto, apaguei a minha memória sobre você.",
        "memoria_ja_vazia": "Minha memória já estava vazia.",
        "modo_trabalho": "Trabalho",
        "modo_conversa": "Conversa",
        "modo_trabalho_ativado": "Modo trabalho.",
        "modo_conversa_ativado": "Modo conversa ativado!",
        "feito2": "Feito!",
        "setup_titulo": "Primeiro acesso",
        "setup_pergunta": "Como você deseja me chamar?",
        "setup_dica": "Esse é o nome que você vai falar para me chamar.",
        "setup_placeholder": "Digite um nome (ex: Fuyumi)",
        "setup_salvar": "Salvar",
        "setup_vazio": "Escreva um nome para continuar.",
        "pergunta_formatar": "Tem certeza que quer formatar? Vou apagar o meu nome e todas as configurações.",
        "formatado": "Pronto, formatei tudo. Vou fechar.",
        "escuta_ligada": "Escuta LIGADA",
        "escuta_desligada": "Escuta DESLIGADA (modo não perturbe)",
    },
    "en": {
        "reconhecimento": "en-US",
        "voz_busca": ["english", "en-us"],
        "pronto": "{nome} online and listening!",
        "voce_disse": "You said",
        "cancelado": "Task cancelled!",
        "tchau": "Goodbye!",
        "pensando": "Thinking... (say 'cancel' or 'stop' to abort)",
        "feito": "Done!",
        "sem_ollama": "I couldn't reach Ollama. Is it running?",
        "instrucao_idioma": "Always answer in English.",
        "primeiro_nome": "First launch detected! What should my name be?",
        "nome_salvo": "Perfect! From now on my name is",
        "pode_falar": "Hi! Go ahead.",
        "memoria_vazia": "I have nothing written down about you yet.",
        "memoria_intro": "I remember this about you:",
        "memoria_e_mais": "And {n} more notes.",
        "pergunta_limpar_memoria": "Are you sure you want to erase everything I remember about you?",
        "memoria_apagada": "Done, I erased my memory of you.",
        "memoria_ja_vazia": "My memory was already empty.",
        "modo_trabalho": "Work",
        "modo_conversa": "Chat",
        "modo_trabalho_ativado": "Work mode.",
        "modo_conversa_ativado": "Chat mode on!",
        "feito2": "Got it!",
        "setup_titulo": "First launch",
        "setup_pergunta": "What would you like to call me?",
        "setup_dica": "This is the name you will say to call me.",
        "setup_placeholder": "Type a name (e.g. Fuyumi)",
        "setup_salvar": "Save",
        "setup_vazio": "Please type a name to continue.",
        "pergunta_formatar": "Are you sure you want to reset? I will erase my name and all settings.",
        "formatado": "Done, everything was reset. Closing now.",
        "escuta_ligada": "Listening ON",
        "escuta_desligada": "Listening OFF (do not disturb)",
    },
}

# ---------------------------------------------------------------------
# VALORES FINAIS (é daqui que o resto do programa lê)
# ---------------------------------------------------------------------
_cfg = carregar_config()

MODELO = _cfg["modelo"].strip()
MANTER_MODELO = _cfg["manter_modelo"].strip()
TEMPO_MAX_FRASE = _cfg["tempo_max_frase"]
MAX_PASSOS_IA = _cfg["max_passos_ia"]
LIMITE_PALAVRAS_REGRA = _cfg["limite_palavras_regra"]
MEMORIA_MENSAGENS = _cfg["memoria_mensagens"]
DIARIO_MAX_ITENS = _cfg["diario_max_itens"]
NAVEGADOR_PADRAO = _cfg["navegador_padrao"].strip().lower()   # auto/brave/chrome/edge/opera
PORTA_DEPURACAO = _cfg["navegador_porta_debug"]

# Palavra de ativação (o nome que você deu pro assistente).
# Fica vazia na primeira vez — o main.py chama 'configurar_palavra_ativacao'.
_palavra_ativacao_bruta = _cfg["palavra_ativacao"].strip()
PALAVRA_ATIVACAO = normalizar(_palavra_ativacao_bruta)
MODO_ESCUTA = _cfg["modo_escuta"]
INTERFACE = _cfg["interface"]
MODO_PADRAO = _cfg["modo_padrao"]
LEMBRAR_MODO = _cfg["lembrar_modo"]
TRABALHO_SILENCIOSO = _cfg["trabalho_silencioso"]
VARIACOES_PALAVRA = [v for v in (normalizar(x) for x in _cfg["variacoes_palavra"]) if v]
TECLA_ESCUTA = _cfg["tecla_escuta"].strip().lower()
TECLA_FORMATAR = _cfg["tecla_formatar"].strip().lower()
JANELA_ESCUTA = _cfg["janela_escuta"]

# Os nomes dos apps e as palavras de cancelar/sair passam por "normalizar"
# (minúsculo, sem acento), porque é assim que o que você fala é comparado.
APPS_E_SITES = {normalizar(nome): (dados[0], dados[1])
                for nome, dados in _cfg["apps_e_sites"].items()}
PALAVRAS_CANCELAR = {normalizar(p) for p in _cfg["palavras_cancelar"]}
FRASES_CANCELAR = {normalizar(p) for p in _cfg["frases_cancelar"]}
FRASES_SAIR = {normalizar(p) for p in _cfg["frases_sair"]}

# Palavrinhas que podem acompanhar uma palavra de cancelar sem estragar o
# comando. Ex: "calma aí", "cancela tudo", "para isso" cancelam, mas
# "fica calma aí" NÃO cancela (o "fica" não está na lista).
PALAVRAS_AUXILIARES_CANCELAR = {"tudo", "isso", "ai", "agora", "ja",
                                "por", "favor"}

# Comando de voz SECRETO para formatar (sempre pede confirmação com "sim")
FRASES_FORMATAR = {"formatar assistente", "formatar o assistente",
                   "formatar a assistente", "resetar assistente",
                   "resetar o assistente"}

IDIOMA = detectar_idioma() if _cfg["idioma"] == "auto" else _cfg["idioma"]
T = TEXTOS[IDIOMA]  # "T" guarda os textos do idioma escolhido


# ---------------------------------------------------------------------
# PRIMEIRO ACESSO: pergunta o nome e salva no config.json
# ---------------------------------------------------------------------
def nome_assistente():
    """O nome do assistente como você escreveu (ex: 'Fuyumi'), pra usar em
    textos. A versão sem acento e minúscula (PALAVRA_ATIVACAO) é só pra comparar."""
    return _palavra_ativacao_bruta.title()


def rotulo():
    """O começo das mensagens do terminal e do chat, ex: [Fuyumi].
    Usa o nome que você escolheu (ou GargaAI, se ainda não escolheu nenhum)."""
    return f"[{nome_assistente() or 'GargaAI'}]"


def precisa_configurar():
    """True se a palavra de ativação ainda não foi definida.
    Ou seja: é a primeira vez que o programa roda."""
    return PALAVRA_ATIVACAO == ""


def configurar_palavra_ativacao(pedir_nome=None):
    """Pergunta qual é o nome do assistente e salva no config.json. Depois de
    salvar, atualiza as variáveis globais pra que o resto do programa (main.py)
    já enxergue o nome novo sem reiniciar.

    'pedir_nome' é uma função que abre a janelinha bonita de primeiro acesso e
    devolve o nome digitado (ou None se a janelinha foi fechada). Se ela não for
    dada, ou se não conseguir abrir, a pergunta é feita no terminal."""
    global PALAVRA_ATIVACAO, _palavra_ativacao_bruta

    nome = None
    if pedir_nome is not None:
        try:
            nome = pedir_nome()
            if not nome:                        # fechou a janelinha sem salvar
                nome = "Fuyumi"
                print(f"[Config]: nenhum nome escolhido. Usando o padrão: {nome}")
        except Exception as erro:
            print(f"[Config]: não consegui abrir a janelinha do nome ({erro}).")
            nome = None

    if nome is None:                            # pergunta no terminal
        print()
        print("=" * 60)
        print(f"  {T['primeiro_nome']}")
        print("  (digite o nome e aperte ENTER. Ex: Fuyumi)")
        print("=" * 60)

        while True:
            try:
                nome = input("  > ").strip()
            except (EOFError, KeyboardInterrupt, RuntimeError):
                # Sem resposta (ou sem terminal): usa um padrão seguro
                nome = "Fuyumi"
                print(f"\n  [Sem resposta — usando o padrão: {nome}]")
                break

            if nome:
                break
            print("  [O nome não pode ficar vazio. Tente de novo.]")

    if salvar_no_config("palavra_ativacao", nome):
        _palavra_ativacao_bruta = nome
        PALAVRA_ATIVACAO = normalizar(nome)
        print(f"  {T['nome_salvo']} '{nome}'. Salvo no config.json!")
    else:
        print("  [Não consegui salvar no config.json. Usando só nesta sessão.]")
        _palavra_ativacao_bruta = nome
        PALAVRA_ATIVACAO = normalizar(nome)


# ---------------------------------------------------------------------
# FORMATAR O ASSISTENTE (volta ao estado de fábrica)
# ---------------------------------------------------------------------
TEXTO_AJUDA = ("Edite so o que vem depois dos dois pontos. Texto fica entre aspas, "
               "numeros ficam sem aspas, e toda linha termina com virgula, menos a "
               "ultima de cada bloco. Se errar, o programa avisa e usa os valores padrao.")
TEXTO_AJUDA_ESCUTA = ("palavra_ativacao = nome pra chamar a IA (vazio = ela pergunta na "
                      "primeira vez). variacoes_palavra = jeitos que o Google pode entender "
                      "o nome errado: olhe o 'Voce disse' no terminal e acrescente aqui. "
                      "modo_escuta = palavra_ativacao ou sempre. tecla_escuta = tecla "
                      "liga/desliga do modo nao perturbe (vazio desativa). tecla_formatar = "
                      "aperte 2 vezes pra apagar o nome e as configuracoes (vazio desativa). "
                      "janela_escuta = segundos pra falar o pedido depois de dizer so o nome. "
                      "interface = janela ou terminal. modo_padrao = conversa ou trabalho "
                      "(troque por voz: 'modo trabalho' / 'modo conversa'). lembrar_modo = "
                      "true salva o modo escolhido por voz. trabalho_silencioso = true "
                      "faz o modo trabalho nao falar nada. diario_max_itens = limite de "
                      "anotacoes da memoria de longo prazo (memoria.json). navegador_padrao = "
                      "auto, brave, chrome, edge ou opera (auto usa o que estiver aberto, ou o "
                      "padrao do Windows). navegador_porta_debug = porta de depuracao do "
                      "navegador (so o clique em videos usa).")


_ao_formatar = []        # funções que outros módulos pedem pra rodar ao formatar


def registrar_ao_formatar(funcao):
    """Um módulo (como a memória) usa isto para ser avisado quando o
    assistente for formatado, e assim esquecer tudo o que guarda na memória."""
    _ao_formatar.append(funcao)


def formatar_assistente():
    """FORMATAR: apaga as configurações personalizadas (o nome da IA, as
    variações do nome, a tecla, o modelo...) e grava de novo o config.json
    com os valores de fábrica. Na próxima vez que o programa abrir, ele
    pergunta o nome outra vez, como no primeiro acesso.

    Também apaga as cópias de segurança (config.json.bak e .tmp), porque elas
    guardam o nome antigo, e APAGA A MEMÓRIA (memoria.json), deixando o projeto
    limpo, como de fábrica. Não mexe no regras.txt. Devolve True se deu certo."""
    global PALAVRA_ATIVACAO, _palavra_ativacao_bruta

    # Avisa os outros módulos (a memória esvazia e para de gravar)
    for funcao in _ao_formatar:
        try:
            funcao()
        except Exception as erro:
            print(f"[Config]: aviso ao formatar: {erro}")

    fabrica = {"_ajuda": TEXTO_AJUDA, "_ajuda_escuta": TEXTO_AJUDA_ESCUTA}
    fabrica.update(copy.deepcopy(PADRAO))

    try:
        temporario = CAMINHO_CONFIG + ".tmp"
        with open(temporario, "w", encoding="utf-8") as arquivo:
            json.dump(fabrica, arquivo, ensure_ascii=False, indent=2)
        os.replace(temporario, CAMINHO_CONFIG)
        for sufixo in (".bak", ".tmp"):
            if os.path.exists(CAMINHO_CONFIG + sufixo):
                os.remove(CAMINHO_CONFIG + sufixo)
    except OSError as erro:
        print(f"[Config]: não consegui formatar o config.json ({erro}).")
        return False

    # Apaga o arquivo da memória (e as sobras dele)
    try:
        for sufixo in ("", ".tmp", ".quebrado"):
            if os.path.exists(CAMINHO_MEMORIA + sufixo):
                os.remove(CAMINHO_MEMORIA + sufixo)
    except OSError as erro:
        print(f"[Config]: não consegui apagar a memória ({erro}).")
        return False

    PALAVRA_ATIVACAO = ""
    _palavra_ativacao_bruta = ""
    print(f"{rotulo()}: Assistente formatado! O config.json voltou ao padrão de "
          "fábrica e a memória foi apagada. Na próxima vez, ele vai perguntar "
          "o nome de novo.")
    return True

@echo off
title GargaAI - Instalador e Inicializador
echo ==============================================
echo   GargaAI - Preparando tudo...
echo ==============================================
echo.

REM Verifica se o Ollama existe
where ollama >nul 2>&1
if %errorlevel% neq 0 (
    echo [1/3] Ollama nao encontrado.
    echo Baixando o instalador do Ollama...
    echo.
    powershell -Command "Invoke-WebRequest -Uri https://ollama.com/download/OllamaSetup.exe -OutFile OllamaSetup.exe"
    
    if exist OllamaSetup.exe (
        echo Instalador baixado! Abrindo...
        echo Por favor, clique em Install e termine a instalacao.
        start /wait OllamaSetup.exe
        del OllamaSetup.exe
    ) else (
        echo Erro ao baixar o Ollama. Baixe manualmente em: https://ollama.com
        pause
        exit
    )
) else (
    echo [1/3] Ollama ja esta instalado!
)

echo.
echo [2/3] Iniciando o Ollama...
start "" ollama serve >nul 2>&1
timeout /t 4 >nul

echo.
echo [3/3] Verificando modelo deepseek-coder-v2:16b...
ollama list | findstr "deepseek-coder-v2:16b" >nul
if %errorlevel% neq 0 (
    echo Modelo nao encontrado. Baixando... (pode demorar varios minutos)
    ollama pull deepseek-coder-v2:16b
) else (
    echo Modelo ja esta baixado!
)

echo.
echo Instalando bibliotecas Python...
python -m pip install -r requirements.txt

echo.
echo ==============================================
echo   Tudo pronto! Abrindo o GargaAI...
echo ==============================================
python garga_ai.py

pause

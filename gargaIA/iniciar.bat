@echo off
title GargaAI - Assistente por Voz
echo ==============================================
echo   Iniciando Servidor Ollama...
echo ==============================================

set OLLAMA_MODELS=%~dp0models
start "" "%~dp0Ollama_Programa\ollama.exe" serve

timeout /t 3

echo.
echo Verificando dependencias...
cd /d "%~dp0jarvis"

python -m pip install -r requirements.txt >nul 2>&1

echo.
echo Abrindo o GargaAI...
python garga_ai.py

pause
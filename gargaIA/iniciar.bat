@echo off
title GargaAI - Assistente por Voz
echo ==============================================
echo   Iniciando GargaAI...
echo ==============================================

REM Inicia o Ollama se estiver instalado no PC da pessoa
start "" ollama serve >nul 2>&1

echo.
echo Verificando e instalando dependencias...
python -m pip install -r requirements.txt

echo.
echo Abrindo o GargaAI...
python garga_ai.py

if %errorlevel% neq 0 (
    echo.
    echo ========================================================
    echo   ERRO: Verifique se o Python esta instalado no seu PC!
    echo   Baixe o Python em: https://www.python.org/downloads/
    echo ========================================================
    pause
)
pause

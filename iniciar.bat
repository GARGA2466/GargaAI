@echo off
title GargaAI - Assistente por Voz
cd /d "%~dp0"

echo ==============================================
echo   Iniciando GargaAI...
echo ==============================================
echo.

rem --- 1) Confere se o Python esta instalado ---
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRO: o Python nao foi encontrado.
    echo Instale o Python e marque a opcao "Add Python to PATH".
    pause
    exit /b 1
)

rem --- 2) Pasta dos modelos do Ollama: a pasta "models" ao lado desta pasta ---
rem     (D:\ia\gargaIA  ->  D:\ia\models). Se ela nao existir, o Ollama usa o padrao dele.
rem     O proprio GargaAI liga o Ollama (escondido) e herda esta configuracao.
if exist "%~dp0..\models" for %%i in ("%~dp0..\models") do set "OLLAMA_MODELS=%%~fi"

rem --- 3) Instala as dependencias SO quando o requirements.txt mudou ---
if not exist ".requisitos_ok" goto instalar
fc /b requirements.txt .requisitos_ok >nul 2>&1
if errorlevel 1 goto instalar
goto abrir

:instalar
echo.
echo Instalando dependencias (so acontece quando o requirements.txt muda)...
python -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERRO ao instalar as dependencias. Leia a mensagem acima.
    pause
    exit /b 1
)
copy /y requirements.txt .requisitos_ok >nul

:abrir
rem --- 4) Abre o GargaAI SEM janela preta (pythonw) e fecha esta janela ---
rem     Para ver o terminal (ex: para investigar um erro), use iniciar_com_console.bat
if /i "%~1"=="console" goto comconsole
where pythonw >nul 2>&1
if errorlevel 1 goto comconsole
start "" pythonw main.py
exit /b 0

:comconsole
echo.
echo Abrindo o GargaAI com console...
python main.py
pause

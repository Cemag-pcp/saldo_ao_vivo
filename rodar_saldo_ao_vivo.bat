@echo off
setlocal

cd /d "%~dp0"
set "PYTHONUNBUFFERED=1"

echo ==========================================
echo Iniciando Saldo ao Vivo
echo Pasta: %CD%
echo ==========================================
echo.

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=python"
    ) else (
        py -3.11 --version >nul 2>nul
        if not errorlevel 1 (
            set "PYTHON_EXE=py -3.11"
        ) else (
            py -3 --version >nul 2>nul
            if not errorlevel 1 (
                set "PYTHON_EXE=py -3"
            ) else (
                echo ERRO: nao encontrei Python instalado nesta maquina.
                exit /b 1
            )
        )
    )
)

echo Usando Python: %PYTHON_EXE%
echo.

set "DEPENDENCIAS=playwright python-dotenv pandas requests gspread google-auth psycopg2-binary"

echo Verificando e instalando dependencias do Python...
%PYTHON_EXE% -m pip install %DEPENDENCIAS%
if errorlevel 1 (
    echo.
    echo ERRO: falha ao instalar dependencias do Python.
    exit /b 1
)

echo.
echo Verificando navegador Chromium do Playwright...
%PYTHON_EXE% -m playwright install chromium
if errorlevel 1 (
    echo.
    echo ERRO: falha ao instalar o Chromium do Playwright.
    exit /b 1
)

echo.
%PYTHON_EXE% main.py
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo Aplicacao finalizada com sucesso.
) else (
    echo Aplicacao finalizada com erro. Codigo: %EXIT_CODE%
)

echo.
exit /b %EXIT_CODE%

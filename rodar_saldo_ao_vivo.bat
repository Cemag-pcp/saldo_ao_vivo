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
    python -c "import playwright" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=python"
    ) else (
        py -3.11 -c "import playwright" >nul 2>nul
        if not errorlevel 1 (
            set "PYTHON_EXE=py -3.11"
        ) else (
            py -3 -c "import playwright" >nul 2>nul
            if not errorlevel 1 (
                set "PYTHON_EXE=py -3"
            ) else (
                echo ERRO: nao encontrei um Python com o pacote playwright instalado.
                echo.
                echo Instale as dependencias com:
                echo python -m pip install playwright python-dotenv pandas requests gspread google-auth psycopg2-binary
                echo python -m playwright install chromium
                echo.
                pause
                exit /b 1
            )
        )
    )
)

echo Usando Python: %PYTHON_EXE%
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
pause
exit /b %EXIT_CODE%

@echo off
setlocal

cd /d "%~dp0"
set "PYTHONUNBUFFERED=1"
set "LOG_FILE=%~dp0rodar_saldo_ao_vivo.log"

echo ==========================================
echo Iniciando Saldo ao Vivo
echo Pasta: %CD%
echo Log: %LOG_FILE%
echo ==========================================
echo.

> "%LOG_FILE%" echo ==========================================
>> "%LOG_FILE%" echo Iniciando Saldo ao Vivo
>> "%LOG_FILE%" echo Data/hora: %DATE% %TIME%
>> "%LOG_FILE%" echo Pasta: %CD%
>> "%LOG_FILE%" echo ==========================================
>> "%LOG_FILE%" echo.

if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    py -3.11 --version >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=py -3.11"
    ) else (
        where python >nul 2>nul
        if not errorlevel 1 (
            set "PYTHON_EXE=python"
        ) else (
            py -3 --version >nul 2>nul
            if not errorlevel 1 (
                set "PYTHON_EXE=py -3"
            ) else (
                echo ERRO: nao encontrei Python instalado nesta maquina.
                echo Veja o log em: %LOG_FILE%
                >> "%LOG_FILE%" echo ERRO: nao encontrei Python instalado nesta maquina.
                exit /b 1
            )
        )
    )
)

echo Usando Python: %PYTHON_EXE%
echo.
>> "%LOG_FILE%" echo Usando Python: %PYTHON_EXE%
%PYTHON_EXE% --version >> "%LOG_FILE%" 2>&1

if not exist "requirements.txt" (
    echo ERRO: arquivo requirements.txt nao encontrado.
    echo Veja o log em: %LOG_FILE%
    >> "%LOG_FILE%" echo ERRO: arquivo requirements.txt nao encontrado.
    exit /b 1
)

echo Verificando pip...
%PYTHON_EXE% -m pip --version >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo Pip nao encontrado. Tentando instalar/ativar pip...
    >> "%LOG_FILE%" echo Pip nao encontrado. Tentando instalar/ativar pip...
    %PYTHON_EXE% -m ensurepip --upgrade >> "%LOG_FILE%" 2>&1
    if errorlevel 1 (
        echo.
        echo ERRO: pip nao esta disponivel neste Python.
        echo Veja o log em: %LOG_FILE%
        >> "%LOG_FILE%" echo ERRO: pip nao esta disponivel neste Python.
        exit /b 1
    )
)

echo Verificando e instalando dependencias do Python...
>> "%LOG_FILE%" echo Instalando dependencias do requirements.txt...
%PYTHON_EXE% -m pip install --disable-pip-version-check -r requirements.txt >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo.
    echo ERRO: falha ao instalar dependencias do requirements.txt.
    echo Veja o log em: %LOG_FILE%
    >> "%LOG_FILE%" echo ERRO: falha ao instalar dependencias do requirements.txt.
    exit /b 1
)

echo.
echo Validando Playwright e greenlet...
>> "%LOG_FILE%" echo Validando imports do Playwright e greenlet...
%PYTHON_EXE% -c "import greenlet; from playwright.sync_api import sync_playwright; print('playwright_ok')" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo Playwright/greenlet falhou ao importar. Reinstalando pacotes nativos...
    >> "%LOG_FILE%" echo Playwright/greenlet falhou ao importar. Reinstalando pacotes nativos...
    %PYTHON_EXE% -m pip install --disable-pip-version-check --force-reinstall --no-cache-dir greenlet playwright >> "%LOG_FILE%" 2>&1
    if errorlevel 1 (
        echo.
        echo ERRO: falha ao reinstalar greenlet/playwright.
        echo Veja o log em: %LOG_FILE%
        >> "%LOG_FILE%" echo ERRO: falha ao reinstalar greenlet/playwright.
        exit /b 1
    )

    %PYTHON_EXE% -c "import greenlet; from playwright.sync_api import sync_playwright; print('playwright_ok')" >> "%LOG_FILE%" 2>&1
    if errorlevel 1 (
        echo.
        echo ERRO: greenlet/playwright ainda nao carregou.
        echo Instale o Microsoft Visual C++ Redistributable x64 no servidor e rode novamente.
        echo Link: https://aka.ms/vs/17/release/vc_redist.x64.exe
        echo Veja o log em: %LOG_FILE%
        >> "%LOG_FILE%" echo ERRO: greenlet/playwright ainda nao carregou.
        >> "%LOG_FILE%" echo Instale o Microsoft Visual C++ Redistributable x64: https://aka.ms/vs/17/release/vc_redist.x64.exe
        exit /b 1
    )
)

echo.
echo Verificando navegador Chromium do Playwright...
>> "%LOG_FILE%" echo Instalando/verificando Chromium do Playwright...
%PYTHON_EXE% -m playwright install chromium >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo.
    echo ERRO: falha ao instalar o Chromium do Playwright.
    echo Veja o log em: %LOG_FILE%
    >> "%LOG_FILE%" echo ERRO: falha ao instalar o Chromium do Playwright.
    exit /b 1
)

echo.
>> "%LOG_FILE%" echo Executando main.py...
%PYTHON_EXE% main.py >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo Aplicacao finalizada com sucesso.
    >> "%LOG_FILE%" echo Aplicacao finalizada com sucesso.
) else (
    echo Aplicacao finalizada com erro. Codigo: %EXIT_CODE%
    echo Veja o log em: %LOG_FILE%
    >> "%LOG_FILE%" echo Aplicacao finalizada com erro. Codigo: %EXIT_CODE%
)

echo.
exit /b %EXIT_CODE%

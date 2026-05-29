import datetime
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

try:
    from .flow import SaldoAoVivo
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from flow import SaldoAoVivo

try:
    from core.db import get_erp_credentials_for_bot, get_headless_mode_for_bot
except ImportError:
    get_erp_credentials_for_bot = None
    get_headless_mode_for_bot = None


BOT_NAME = "saldo_ao_vivo"
DEFAULT_ERP_URL = "http://192.168.3.141/sistema"
BASE_DIR = Path(__file__).resolve().parent


load_dotenv(BASE_DIR / ".env", override=False)


def _dentro_da_janela_de_execucao():
    agora = datetime.datetime.now().time()
    inicio = datetime.time(7, 0, 0)
    fim = datetime.time(19, 0, 0)
    return inicio <= agora <= fim


def _headless_habilitado():
    if get_headless_mode_for_bot is not None:
        return bool(get_headless_mode_for_bot(BOT_NAME))
    return os.getenv("BOT_HEADLESS", "").strip().lower() in {"1", "true", "yes", "sim"}


def _carregar_credenciais():
    if get_erp_credentials_for_bot is not None:
        creds = get_erp_credentials_for_bot(BOT_NAME) or {}
        url = creds.get("erp_url") or os.getenv("ERP_URL", DEFAULT_ERP_URL)
        if url and "://" not in url:
            url = f"http://{url}"
        return {
            "url": url,
            "username": creds.get("erp_username") or os.getenv("ERP_USERNAME", ""),
            "password": creds.get("erp_password") or os.getenv("ERP_PASSWORD", ""),
        }

    url = os.getenv("ERP_URL", DEFAULT_ERP_URL)
    if url and "://" not in url:
        url = f"http://{url}"
    return {
        "url": url,
        "username": os.getenv("ERP_USERNAME", ""),
        "password": os.getenv("ERP_PASSWORD", ""),
    }


def main():
    if not _dentro_da_janela_de_execucao():
        return

    creds = _carregar_credenciais()
    if not creds["url"]:
        raise RuntimeError(
            "Nao foi possivel localizar a URL do ERP. Defina ERP_URL ou ajuste a origem das credenciais."
        )

    download_dir = Path.home() / "Downloads"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=_headless_habilitado(),
            slow_mo=250,
            downloads_path=str(download_dir),
        )
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1440, "height": 900},
        )
        page = context.new_page()

        fluxo = SaldoAoVivo(page=page, download_dir=download_dir)

        try:
            fluxo.abrir_erp(creds["url"])
            fluxo.login(creds["username"], creds["password"])
            fluxo.executar()
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()

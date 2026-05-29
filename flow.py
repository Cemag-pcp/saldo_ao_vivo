from pathlib import Path
import sys
import time
from urllib.parse import urljoin

import requests
from playwright.sync_api import Error, Page, TimeoutError

try:
    from .saldo_ao_vivo import (
        apagar_ultimo_download,
        inserir_gspread_saldo_central_mp,
        inserir_gspread_saldo_levantamento,
        inserir_gspread_saldo_levantamento_incluindo_em_processo,
        inserir_postgres_saldo_central_mp,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from saldo_ao_vivo import (
        apagar_ultimo_download,
        inserir_gspread_saldo_central_mp,
        inserir_gspread_saldo_levantamento,
        inserir_gspread_saldo_levantamento_incluindo_em_processo,
        inserir_postgres_saldo_central_mp,
    )


class SaldoAoVivo:
    def __init__(self, page: Page, download_dir: Path):
        self.page = page
        self.download_dir = download_dir

    def _log(self, message: str):
        print(f"[saldo_ao_vivo] {message}", flush=True)

    def abrir_erp(self, url: str):
        self._log(f"Abrindo ERP em {url}")
        self.page.goto(url, wait_until="domcontentloaded")
        self.page.wait_for_timeout(1500)

    def login(self, username: str, password: str):
        if not username or not password:
            self._log("Credenciais ausentes. Pulando login.")
            return

        self._log("Preenchendo login")
        usuario = self._primeiro_locator_disponivel(
            [
                self.page.get_by_label("Usuário", exact=True),
                self.page.get_by_label("Usuario", exact=True),
                self.page.locator("input[name='username']"),
                self.page.locator("input[type='text']").first,
            ],
            "campo de usuario",
        )
        senha = self._primeiro_locator_disponivel(
            [
                self.page.get_by_label("Senha", exact=True),
                self.page.locator("input[type='password']"),
            ],
            "campo de senha",
        )
        entrar = self._primeiro_locator_disponivel(
            [
                self.page.get_by_role("button", name="Entrar", exact=True),
                self.page.locator("button[type='submit']"),
                self.page.get_by_text("Entrar", exact=True),
            ],
            "botao Entrar",
        )

        usuario.click(timeout=10000)
        usuario.fill(username, timeout=10000)
        senha.click(timeout=10000)
        senha.fill(password, timeout=10000)
        entrar.click(timeout=30000, no_wait_after=True)
        self._esperar_pos_login()

    def executar(self):
        self._log("Abrindo relatorio")
        self._abrir_relatorio()
        self._log("Executando fluxo central")
        self._executar_fluxo_central()
        self._log("Executando fluxo levantamento")
        self._executar_fluxo_levantamento()

    def _executar_fluxo_central(self):
        self._preencher_data_base_hoje()
        self._executar_relatorio()
        self._exportar_csv()

        inserir_gspread_saldo_central_mp()
        inserir_postgres_saldo_central_mp()
        apagar_ultimo_download()

    def _executar_fluxo_levantamento(self):
        self._reabrir_relatorio()
        self._preencher_data_base_hoje()
        self._executar_relatorio()
        self._exportar_csv()

        inserir_gspread_saldo_levantamento()
        inserir_gspread_saldo_levantamento_incluindo_em_processo()
        apagar_ultimo_download()

    def _abrir_relatorio(self):
        self._abrir_menu_principal()
        self.page.get_by_text("Estoque", exact=True).click(timeout=10000)
        self.page.wait_for_timeout(500)
        self.page.get_by_text("Consultas", exact=True).click(timeout=10000)
        self.page.wait_for_timeout(500)
        self.page.get_by_text("Saldos de Recursos - CEMAG", exact=True).click(timeout=10000)
        self.page.wait_for_timeout(2500)

    def _reabrir_relatorio(self):
        abas = self.page.get_by_role("tab", name="Saldos de Recursos - CEMAG Fechar")
        if abas.count():
            try:
                abas.click(timeout=5000)
                self.page.wait_for_timeout(1200)
                return
            except Error:
                pass
        self._abrir_relatorio()

    def _abrir_menu_principal(self):
        self._log("Abrindo menu principal")
        candidatos = [
            self.page.get_by_role("button", name="Menu", exact=True),
            self.page.locator("button[aria-label='Menu']"),
            self.page.locator("[aria-label*='menu' i]"),
            self.page.locator("header button").first,
        ]

        ultimo_erro = None
        for botao in candidatos:
            try:
                alvo = botao.first if hasattr(botao, "first") else botao
                if botao.count():
                    alvo.click(timeout=10000)
                    self.page.wait_for_timeout(500)
                    return
            except Exception as exc:
                ultimo_erro = exc

        raise RuntimeError(
            f"Nao foi possivel localizar o botao Menu. Titulo atual: {self.page.title()}"
        ) from ultimo_erro

    def _frame_relatorio(self):
        return self.page.frame_locator("iframe")

    def _preencher_data_base_hoje(self):
        self._log("Preenchendo Data Base com 'h'")
        frame = self._frame_relatorio()
        candidatos = [
            frame.locator("xpath=//*[contains(normalize-space(), 'Data Base')]/following::input[1]"),
            frame.locator("input").first,
        ]

        try:
            campo = self._primeiro_locator_disponivel(candidatos, "campo Data Base")
            campo.click(timeout=5000)
            campo.fill("", timeout=5000)
            campo.type("h", delay=50, timeout=5000)
            campo.press("Tab", timeout=3000)
            self.page.wait_for_timeout(1200)
            return
        except RuntimeError:
            self._log("Campo Data Base nao localizado por seletor. Tentando fallback por coordenada.")

        self.page.mouse.click(295, 166)
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Backspace")
        self.page.keyboard.type("h", delay=50)
        self.page.keyboard.press("Tab")
        self.page.wait_for_timeout(1200)

    def _executar_relatorio(self):
        self._log("Clicando em Executar")
        self.page.get_by_text("Executar", exact=True).click(timeout=10000)
        self._aguardar_processamento()

    def _aguardar_processamento(self):
        self._log("Aguardando processamento do relatorio")
        exportar = self.page.get_by_text("Exportar", exact=True)
        overlays = [
            self.page.locator("section.mdc-dialog__surface[role='dialog']"),
            self.page.locator(".wf-progress-dialog__content"),
            self.page.locator(".wf-progress-indicator__label").filter(
                has_text="Montando saldo da movimentação de recursos..."
            ),
            self.page.locator(".wf-progress-indicator__label").filter(
                has_text="Montando saldo da movimentaÃ§Ã£o de recursos..."
            ),
        ]

        overlay_detectado = None
        for overlay in overlays:
            try:
                overlay.wait_for(state="visible", timeout=5000)
                overlay_detectado = overlay
                self._log("Tela de carregamento detectada. Aguardando desaparecer.")
                break
            except TimeoutError:
                continue
            except Exception:
                continue

        if overlay_detectado is not None:
            try:
                overlay_detectado.wait_for(state="hidden", timeout=180000)
            except Exception:
                self._aguardar_overlay_sumir()
            self._log("Tela de carregamento finalizada.")
            self.page.wait_for_timeout(1500)
        else:
            self._log("Overlay de carregamento nao foi detectado por seletor dedicado.")
            self._aguardar_overlay_sumir()

        for tentativa in range(1, 37):
            try:
                if exportar.count():
                    try:
                        if exportar.first.is_enabled():
                            self._log("Relatorio pronto para exportacao.")
                            self.page.wait_for_timeout(1500)
                            return
                    except Exception:
                        self._log("Botao Exportar apareceu novamente. Prosseguindo.")
                        self.page.wait_for_timeout(1500)
                        return
            except Exception:
                pass

            if tentativa % 5 == 0:
                self._log(f"Relatorio ainda processando... tentativa {tentativa}/36")
            self.page.wait_for_timeout(5000)

        self._log("Tempo de espera esgotado. Tentando prosseguir mesmo assim.")
        self.page.wait_for_timeout(1500)

    def _aguardar_overlay_sumir(self):
        self._log("Validando se o overlay de carregamento ainda esta visivel")
        seletores = [
            self.page.locator("section.mdc-dialog__surface[role='dialog']"),
            self.page.locator(".wf-progress-dialog__content"),
            self.page.locator(".wf-progress-indicator__label").filter(
                has_text="Montando saldo da movimentação de recursos..."
            ),
            self.page.locator(".wf-progress-indicator__label").filter(
                has_text="Montando saldo da movimentaÃ§Ã£o de recursos..."
            ),
        ]

        for tentativa in range(1, 49):
            overlay_visivel = False
            for locator in seletores:
                try:
                    if locator.count() and locator.first.is_visible():
                        overlay_visivel = True
                        break
                except Exception:
                    continue

            if not overlay_visivel:
                self._log("Overlay de carregamento nao esta mais visivel.")
                return

            if tentativa % 6 == 0:
                self._log(f"Overlay ainda visivel... tentativa {tentativa}/48")
            self.page.wait_for_timeout(2500)

    def _exportar_csv(self):
        self._log("Abrindo exportacao CSV")
        self._clicar_botao_exportar_principal()
        self.page.wait_for_timeout(1500)

        self._selecionar_opcao_csv()
        self._clicar_botao_continuar_exportacao()
        self.page.wait_for_timeout(3000)

        try:
            utf8 = self.page.frame_locator("iframe").locator("select").first
            if utf8.count():
                utf8.select_option(label="UTF-8", timeout=5000)
                self.page.wait_for_timeout(500)
        except Exception:
            self._log("Nao foi possivel ajustar UTF-8 por seletor. Seguindo com o valor atual.")

        referencia = self._mais_recente_em_downloads()
        self._clicar_botao_exportar_final()

        arquivo = self._aguardar_arquivo_novo(referencia, timeout=30)
        if arquivo is None:
            self._log("Download automatico nao disparou. Tentando link manual 'clique aqui'.")
            self._clicar_link_download_manual()
            arquivo = self._aguardar_arquivo_novo(referencia, timeout=60)

        if arquivo is None:
            self._log("Tentando baixar o arquivo pela URL do link manual.")
            arquivo = self._baixar_via_link_manual()

        if arquivo is None:
            raise RuntimeError(
                "O ERP nao gerou um download detectavel na pasta Downloads apos a exportacao."
            )

        self._log(f"Download detectado em {arquivo}")
        self.page.wait_for_timeout(1500)

    def _clicar_botao_exportar_principal(self):
        candidatos = [
            self.page.get_by_role("button", name="Exportar", exact=True),
            self.page.get_by_text("Exportar", exact=True),
            self.page.locator("button").filter(has_text="Exportar"),
        ]

        for locator in candidatos:
            try:
                if locator.count():
                    locator.first.click(timeout=10000)
                    return
            except Exception:
                continue

        self._log("Botao Exportar principal nao localizado por seletor. Tentando atalho Alt+X.")
        try:
            self.page.keyboard.press("Alt+X")
            self.page.wait_for_timeout(1000)
            if self.page.get_by_text("Exportar para CSV", exact=True).count():
                return
        except Exception:
            pass

        self._log("Atalho Alt+X nao abriu a exportacao. Tentando fallback por coordenada.")
        self.page.mouse.click(190, 64)
        self.page.wait_for_timeout(800)

    def _clicar_botao_exportar_final(self):
        candidatos = [
            self.page.get_by_role("button", name="Exportar", exact=True),
            self.page.get_by_text("Exportar", exact=True),
            self.page.frame_locator("iframe").get_by_text("Exportar", exact=True),
        ]

        for locator in candidatos:
            try:
                if locator.count():
                    locator.first.click(timeout=10000)
                    return
            except Exception:
                continue

        self._log("Botao Exportar final nao localizado por seletor. Tentando fallback por coordenada.")
        self.page.mouse.click(131, 64)
        self.page.wait_for_timeout(800)

    def _clicar_botao_continuar_exportacao(self):
        candidatos = [
            self.page.get_by_role("button", name="Continuar", exact=True),
            self.page.get_by_text("Continuar", exact=True),
            self.page.locator("button").filter(has_text="Continuar"),
        ]

        for locator in candidatos:
            try:
                if locator.count():
                    locator.first.click(timeout=10000)
                    return
            except Exception:
                continue

        self._log("Botao Continuar nao localizado por seletor. Tentando fallback por coordenada.")
        self.page.mouse.click(686, 543)
        self.page.wait_for_timeout(800)

    def _selecionar_opcao_csv(self):
        self._log("Selecionando opcao CSV")
        candidatos = [
            self.page.get_by_role("button", name="Exportar para CSV", exact=True),
            self.page.get_by_text("Exportar para CSV", exact=True),
            self.page.locator("button").filter(has_text="Exportar para CSV"),
        ]

        for locator in candidatos:
            try:
                if locator.count():
                    locator.first.click(timeout=10000)
                    self.page.wait_for_timeout(500)
                    return
            except Exception:
                continue

        self._log("Opcao CSV nao localizada por seletor. Tentando fallback por coordenada.")
        self.page.mouse.click(538, 401)
        self.page.wait_for_timeout(500)

    def _clicar_link_download_manual(self):
        candidatos = [
            self.page.get_by_text("clique aqui", exact=False),
            self.page.get_by_text("iniciar manualmente", exact=False),
            self.page.frame_locator("iframe").get_by_text("clique aqui", exact=False),
        ]

        for locator in candidatos:
            try:
                if locator.count():
                    locator.first.click(timeout=10000)
                    self.page.wait_for_timeout(1000)
                    return
            except Exception:
                continue

        self._log("Link manual nao localizado por seletor. Tentando fallback por coordenada.")
        self.page.mouse.click(393, 116)
        self.page.wait_for_timeout(1000)

    def _mais_recente_em_downloads(self):
        arquivos = [p for p in self.download_dir.glob("*") if p.is_file()]
        if not arquivos:
            return None
        return max(arquivos, key=lambda p: p.stat().st_mtime)

    def _aguardar_arquivo_novo(self, referencia, timeout=30):
        limite = time.time() + timeout
        ref_mtime = referencia.stat().st_mtime if referencia and referencia.exists() else 0

        while time.time() < limite:
            arquivos = [p for p in self.download_dir.glob("*") if p.is_file()]
            if arquivos:
                mais_recente = max(arquivos, key=lambda p: p.stat().st_mtime)
                if mais_recente.stat().st_mtime > ref_mtime:
                    return mais_recente
            self.page.wait_for_timeout(1000)

        return None

    def _baixar_via_link_manual(self):
        href = None
        for locator in [
            self.page.locator("a").first,
            self.page.frame_locator("iframe").locator("a").first,
        ]:
            try:
                if locator.count():
                    href = locator.get_attribute("href", timeout=3000)
                    if href:
                        break
            except Exception:
                continue

        if not href:
            self._log("Nao foi possivel localizar href do link manual.")
            return None

        url_download = urljoin(self.page.url, href)
        self._log(f"Baixando arquivo pela URL manual: {url_download}")

        session = requests.Session()
        try:
            for cookie in self.page.context.cookies():
                session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"))
        except Exception:
            pass

        try:
            response = session.get(url_download, timeout=120, stream=True)
            response.raise_for_status()
        except Exception as exc:
            self._log(f"Falha ao baixar pela URL manual: {exc}")
            return None

        nome = self._nome_arquivo_da_resposta(response)
        destino = self.download_dir / nome

        try:
            with open(destino, "wb") as arquivo:
                for bloco in response.iter_content(chunk_size=65536):
                    if bloco:
                        arquivo.write(bloco)
        except Exception as exc:
            self._log(f"Falha ao salvar arquivo baixado manualmente: {exc}")
            return None

        return destino

    def _nome_arquivo_da_resposta(self, response):
        content_disposition = response.headers.get("content-disposition", "")
        partes = [p.strip() for p in content_disposition.split(";")]
        for parte in partes:
            if parte.lower().startswith("filename="):
                return parte.split("=", 1)[1].strip('"')
        return f"saldo_ao_vivo_{int(time.time())}.csv"

    def _esperar_pos_login(self):
        self._log("Aguardando tela principal apos login")
        self.page.wait_for_timeout(1500)

        for _ in range(12):
            if self.page.get_by_role("button", name="Menu", exact=True).count():
                self._log("Tela principal carregada")
                return
            if self.page.locator("button[aria-label='Menu']").count():
                self._log("Tela principal carregada")
                return
            self.page.wait_for_timeout(1000)

        raise RuntimeError(
            f"Login nao chegou na tela principal. Titulo atual: {self.page.title()} | URL atual: {self.page.url}"
        )

    def _primeiro_locator_disponivel(self, candidatos, descricao: str):
        ultimo_erro = None
        for locator in candidatos:
            try:
                if locator.count():
                    return locator.first
            except Exception as exc:
                ultimo_erro = exc
        raise RuntimeError(f"Nao foi possivel localizar {descricao}.") from ultimo_erro

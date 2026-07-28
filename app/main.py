from __future__ import annotations

import ctypes
import json
import os
import shutil
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import BOTH, END, LEFT, X, filedialog, messagebox, ttk
import tkinter as tk

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.license import LicenseClient
from app.updater import download_verified, latest
from core.capture import GIB, PktmonCapture
from core.store import CaptureStore

VERSION = "0.1.2-pilot"
STATE_DIR = Path(os.getenv("LOCALAPPDATA", Path.home())) / "Karvalho" / "RFNextInfo"
CAPTURE_DIR = Path.home() / "Documents" / "Capturas"
ASSETS = ROOT / "assets"
DB_PATH = STATE_DIR / "capture.sqlite3"


def _format_bytes(value: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{value} B"
        value /= 1024


def _capture_summary(envelope: dict) -> tuple[dict, dict[str, list[int]]]:
    summary = {"character": "", "level": None, "exp": None, "market_events": 0}
    marks: dict[str, list[int]] = {}
    for event in envelope.get("events", []):
        data = event.get("data") or {}
        fields = data.get("fields") if isinstance(data.get("fields"), dict) else data
        summary["character"] = str(
            fields.get("character_name") or fields.get("character") or summary["character"]
        )
        summary["level"] = fields.get("level", summary["level"])
        summary["exp"] = fields.get("exp", fields.get("gain_exp", summary["exp"]))
        if "exchange" in event.get("type", "").lower() or "market" in event.get("type", "").lower():
            summary["market_events"] += 1
        for record in data.get("records", []) if isinstance(data.get("records"), list) else []:
            collection_id = record.get("collection_index")
            slots = record.get("completed_slots")
            if collection_id is not None and isinstance(slots, list):
                marks[str(collection_id)] = sorted({
                    int(slot) + 1 for slot in slots if isinstance(slot, int) and 0 <= slot < 10
                })
    return summary, marks


def _recycle(paths: list[Path]) -> bool:
    existing = [str(path.resolve()) for path in paths if path.exists()]
    if not existing:
        return True

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p), ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", ctypes.c_bool),
            ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    operation = SHFILEOPSTRUCTW(
        None, 3, "\0".join(existing) + "\0\0", None,
        0x0040 | 0x0010 | 0x0400, False, None, None,
    )
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation)) == 0 and not operation.fAnyOperationsAborted


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"RF NEXT INFO · Karvalho · {VERSION}")
        self.geometry("980x680")
        self.minsize(820, 610)
        self.configure(bg="#070909")
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        self.license = LicenseClient(STATE_DIR, version=VERSION)
        self.capture = PktmonCapture(CAPTURE_DIR)
        self.store = CaptureStore(DB_PATH)
        self.last_files: list[Path] = []
        self.capture_allowed = False
        self.tray = None
        self._style()
        self._build()
        self._load_preferences()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Control-F8>", lambda _: self.start_capture())
        self.bind("<Control-F9>", lambda _: self.stop_capture())
        self.after(600, self._poll)

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background="#070909", foreground="#F4F2EB", font=("Segoe UI", 10))
        style.configure("TFrame", background="#070909")
        style.configure("Panel.TFrame", background="#0d1110", bordercolor="#6d5428", relief="solid")
        style.configure("TLabel", background="#070909", foreground="#F4F2EB")
        style.configure("Muted.TLabel", foreground="#b9b5aa")
        style.configure("Gold.TLabel", foreground="#D4A64D", font=("Segoe UI Semibold", 12))
        style.configure("Title.TLabel", foreground="#F4F2EB", font=("Segoe UI Semibold", 23))
        style.configure("TButton", background="#D4A64D", foreground="#070909", padding=(13, 9))
        style.map("TButton", background=[("active", "#e1b75f"), ("disabled", "#6d5428")])
        style.configure("Quiet.TButton", background="#111614", foreground="#F4F2EB")
        style.configure("TNotebook", background="#070909", borderwidth=0)
        style.configure("TNotebook.Tab", background="#111614", foreground="#b9b5aa", padding=(14, 9))
        style.map("TNotebook.Tab", background=[("selected", "#D4A64D")], foreground=[("selected", "#070909")])
        style.configure("TEntry", fieldbackground="#050707", foreground="#F4F2EB", insertcolor="#F4F2EB")

    def _build(self) -> None:
        header = ttk.Frame(self, padding=(22, 18))
        header.pack(fill=X)
        try:
            self.logo = tk.PhotoImage(file=str(ASSETS / "karvalho-primary-gold.png"))
            ratio = max(1, self.logo.width() // 190)
            if ratio > 1:
                self.logo = self.logo.subsample(ratio, ratio)
            ttk.Label(header, image=self.logo).pack(side=LEFT, padx=(0, 22))
        except tk.TclError:
            ttk.Label(header, text="KARVALHO", style="Gold.TLabel").pack(side=LEFT, padx=(0, 22))
        title = ttk.Frame(header)
        title.pack(side=LEFT)
        ttk.Label(title, text="RF NEXT INFO", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title, text="Captura passiva, leitura local e exportação controlada.", style="Muted.TLabel").pack(anchor="w")

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill=BOTH, expand=True, padx=22, pady=(0, 12))
        self.capture_tab = ttk.Frame(self.tabs, padding=18)
        self.license_tab = ttk.Frame(self.tabs, padding=18)
        self.tutorial_tab = ttk.Frame(self.tabs, padding=18)
        self.tabs.add(self.capture_tab, text="Captura")
        self.tabs.add(self.license_tab, text="Licença")
        self.tabs.add(self.tutorial_tab, text="Tutorial")
        self._capture_ui()
        self._license_ui()
        self._tutorial_ui()
        ttk.Label(
            self, text=f"Discord: Carvalho  ·  carvalho@tuta.com  ·  {VERSION}",
            style="Muted.TLabel",
        ).pack(pady=(0, 15))

    def _capture_ui(self) -> None:
        status = ttk.Frame(self.capture_tab, style="Panel.TFrame", padding=18)
        status.pack(fill=X)
        self.capture_state = ttk.Label(status, text="Pronto", style="Gold.TLabel")
        self.capture_state.grid(row=0, column=0, sticky="w")
        self.license_state = ttk.Label(status, text="Licença: verificando", style="Muted.TLabel")
        self.license_state.grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.storage_state = ttk.Label(status, text="Armazenamento: calculando", style="Muted.TLabel")
        self.storage_state.grid(row=2, column=0, sticky="w", pady=(5, 0))
        buttons = ttk.Frame(self.capture_tab, padding=(0, 18))
        buttons.pack(fill=X)
        self.start_button = ttk.Button(buttons, text="Iniciar captura  Ctrl+F8", command=self.start_capture)
        self.start_button.pack(side=LEFT)
        self.stop_button = ttk.Button(buttons, text="Parar  Ctrl+F9", style="Quiet.TButton", command=self.stop_capture)
        self.stop_button.pack(side=LEFT, padx=10)
        ttk.Button(buttons, text="Exportar JSON + CSV", style="Quiet.TButton", command=self.export).pack(side=LEFT)
        profile = ttk.Frame(self.capture_tab, style="Panel.TFrame", padding=18)
        profile.pack(fill=X)
        ttk.Label(profile, text="Personagem para o site", style="Gold.TLabel").pack(anchor="w")
        self.character = ttk.Entry(profile)
        self.character.pack(fill=X, pady=(8, 0))
        ttk.Label(profile, text="Use o nome exatamente como está cadastrado no site.", style="Muted.TLabel").pack(anchor="w", pady=(5, 0))
        self.metrics = tk.Text(
            self.capture_tab, height=12, bg="#050707", fg="#F4F2EB", insertbackground="#F4F2EB",
            relief="solid", borderwidth=1, highlightthickness=1, highlightbackground="#6d5428",
            font=("Consolas", 10), state="disabled",
        )
        self.metrics.pack(fill=BOTH, expand=True, pady=(18, 0))

    def _license_ui(self) -> None:
        ttk.Label(self.license_tab, text="Ativar instalação", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self.license_tab,
            text="A chave é enviada uma vez e não fica salva neste computador. A instalação valida a cada 24 horas e possui até 72 horas offline.",
            style="Muted.TLabel", wraplength=760,
        ).pack(anchor="w", pady=(6, 16))
        self.key_entry = ttk.Entry(self.license_tab, show="•")
        self.key_entry.pack(fill=X)
        ttk.Button(self.license_tab, text="Ativar licença", command=self.activate).pack(anchor="w", pady=12)
        self.activation_status = ttk.Label(self.license_tab, text="", style="Muted.TLabel", wraplength=760)
        self.activation_status.pack(anchor="w")
        ttk.Separator(self.license_tab).pack(fill=X, pady=24)
        ttk.Label(self.license_tab, text="Atualizações", style="Gold.TLabel").pack(anchor="w")
        self.channel = tk.StringVar(value="stable")
        ttk.Radiobutton(self.license_tab, text="Estável", value="stable", variable=self.channel).pack(anchor="w")
        ttk.Radiobutton(self.license_tab, text="Beta", value="beta", variable=self.channel).pack(anchor="w")
        ttk.Button(self.license_tab, text="Verificar atualização", style="Quiet.TButton", command=self.check_update).pack(anchor="w", pady=12)
        ttk.Button(self.license_tab, text="Abrir versão anterior", style="Quiet.TButton", command=self.rollback).pack(anchor="w")

    def _tutorial_ui(self) -> None:
        text = (
            "1. Abra a aba Licença e ative esta instalação.\n\n"
            "2. Em Captura, informe o personagem e clique em Iniciar. O Windows pode pedir permissão de administrador porque o Pktmon é uma ferramenta nativa de rede.\n\n"
            "3. Deixe o jogo rodar normalmente. A tela mostra volume capturado, espaço livre e eventos reconhecidos. Amarelo: 5 GB. Vermelho: 10 GB ou menos de 10% livre. A captura para com segurança abaixo de 2 GB livres.\n\n"
            "4. Clique em Parar e aguarde a leitura dos segmentos. Kills são estimadas por eventos de recompensa; dados não confirmados não são exibidos como fatos.\n\n"
            "5. Clique em Exportar JSON + CSV. O tamanho será mostrado e você poderá enviar os segmentos brutos para a Lixeira somente depois da validação dos arquivos.\n\n"
            "Privacidade: captura passiva local, sem injeção no jogo, sem token de sessão, sem atualização silenciosa e sem telemetria."
        )
        ttk.Label(self.tutorial_tab, text="Comece em cinco passos", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self.tutorial_tab, text=text, wraplength=820, justify=LEFT, style="Muted.TLabel").pack(anchor="w", pady=15)

    def _load_preferences(self) -> None:
        path = STATE_DIR / "preferences.json"
        try:
            prefs = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prefs = {}
        if "minimize_to_tray" not in prefs:
            prefs["minimize_to_tray"] = messagebox.askyesno(
                "Comportamento ao fechar",
                "Ao fechar a janela, manter a captura visível na área de notificação?\n\nVocê poderá encerrar pelo ícone Karvalho.",
            )
            path.write_text(json.dumps(prefs), encoding="utf-8")
        self.minimize_to_tray = bool(prefs["minimize_to_tray"])

    def _run(self, job, done) -> None:
        def worker():
            try:
                result = job()
                self.after(0, lambda: done(result, None))
            except Exception as error:
                self.after(0, lambda error=error: done(None, error))
        threading.Thread(target=worker, daemon=True).start()

    def activate(self) -> None:
        key = self.key_entry.get().strip()
        if not key:
            return messagebox.showwarning("Licença", "Informe a chave recebida.")
        self.activation_status.configure(text="Validando…")
        self._run(
            lambda: self.license.activate(key, VERSION),
            lambda result, error: self._activation_done(result, error),
        )

    def _activation_done(self, claims, error) -> None:
        self.key_entry.delete(0, END)
        if error:
            self.activation_status.configure(text=f"Não foi possível ativar: {error}")
            return
        self.activation_status.configure(text=f"Instalação ativa até {claims['valid_until']}.")
        self._refresh_license()

    def _refresh_license(self) -> tuple[bool, str]:
        allowed, message = self.license.refresh_if_due(VERSION)
        self.capture_allowed = allowed
        self.license_state.configure(text=f"Licença: {message}")
        self.start_button.configure(state="normal" if allowed and not self.capture.status().active else "disabled")
        return allowed, message

    def start_capture(self) -> None:
        allowed, message = self._refresh_license()
        if not allowed:
            return messagebox.showwarning("Captura bloqueada", message)
        try:
            self.capture.start(datetime.now().strftime("rfnext-%Y%m%d-%H%M%S"))
            self.capture_state.configure(text="Capturando TCP/12000 e TCP/12020")
        except Exception as error:
            messagebox.showerror("Não foi possível iniciar", str(error))

    def stop_capture(self) -> None:
        try:
            status = self.capture.stop()
            self.last_files = list(status.files)
            self.capture_state.configure(text="Lendo segmentos capturados…")
        except Exception as error:
            return messagebox.showerror("Falha ao parar", str(error))

        def ingest():
            store = CaptureStore(DB_PATH)
            try:
                return sum(store.ingest(path) for path in self.last_files)
            finally:
                store.close()

        self._run(ingest, lambda result, error: self.capture_state.configure(
            text=f"Captura encerrada · {result or 0} eventos novos" if not error else f"Captura encerrada · leitura falhou: {error}"
        ))

    def export(self) -> None:
        if not self.license.lease:
            return messagebox.showwarning("Exportação", "Ative a licença antes de exportar.")
        target = filedialog.askdirectory(title="Escolha a pasta de exportação", initialdir=str(CAPTURE_DIR))
        if not target:
            return
        capture_id = datetime.now().strftime("rfnext-info-%Y%m%d-%H%M%S")
        try:
            result = self.store.export(Path(target), capture_id)
            envelope = json.loads(result.json_path.read_text(encoding="utf-8"))
            detected, marks = _capture_summary(envelope)
            name = self.character.get().strip() or detected["character"]
            envelope["metadata"].update(
                installation_id=self.license.installation_id,
                license_lease=self.license.lease,
                app_version=VERSION,
            )
            envelope["capture"] = detected
            envelope["profiles"] = [{"name": name, "marks": marks}] if name else []
            temporary = result.json_path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
            json.loads(temporary.read_text(encoding="utf-8"))
            os.replace(temporary, result.json_path)
            total = result.json_path.stat().st_size + result.csv_path.stat().st_size
        except Exception as error:
            return messagebox.showerror("Exportação falhou", str(error))
        erase = messagebox.askyesno(
            "Exportação concluída",
            f"Arquivos validados: {_format_bytes(total)}.\n\nEnviar {_format_bytes(result.raw_bytes)} de segmentos brutos para a Lixeira?",
        )
        if erase and not _recycle(self.last_files):
            messagebox.showwarning("Lixeira", "Alguns segmentos não puderam ser movidos. Nenhum apagamento permanente foi usado.")

    def check_update(self) -> None:
        self.activation_status.configure(text="Consultando GitHub…")
        self._run(lambda: latest(self.channel.get()), self._update_found)

    def _update_found(self, release, error) -> None:
        if error:
            return self.activation_status.configure(text=f"Atualização indisponível: {error}")
        tag = str(release.get("tag_name", ""))
        notes = str(release.get("body", "")).strip()[:800]
        if tag.lstrip("v") == VERSION:
            return self.activation_status.configure(text="Você já usa a versão mais recente.")
        if not messagebox.askyesno("Atualização encontrada", f"{tag}\n\n{notes}\n\nBaixar e verificar agora?"):
            return
        public_key = self.license.state.get("public_key")
        if not public_key:
            return messagebox.showwarning("Atualização", "Ative a licença para obter a chave pública de verificação.")
        self._run(lambda: download_verified(release, public_key), self._update_downloaded)

    def _update_downloaded(self, installer, error) -> None:
        if error:
            return messagebox.showerror("Atualização rejeitada", str(error))
        if messagebox.askyesno("Atualização verificada", "Assinatura e SHA-256 conferem. Abrir o instalador visível agora?"):
            if getattr(sys, "frozen", False):
                rollback = STATE_DIR / "rollback" / "RFNextInfo.exe"
                rollback.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sys.executable, rollback)
            os.startfile(installer)

    def rollback(self) -> None:
        previous = STATE_DIR / "rollback" / "RFNextInfo.exe"
        if not previous.is_file():
            return messagebox.showinfo("Versão anterior", "Ainda não existe uma versão anterior preservada.")
        if messagebox.askyesno(
            "Abrir versão anterior",
            "A versão anterior será aberta como executável preservado. Feche a versão atual antes de capturar.",
        ):
            os.startfile(previous)

    def _poll(self) -> None:
        try:
            status = self.capture.status()
            total = sum(path.stat().st_size for path in CAPTURE_DIR.glob("*.etl"))
            usage = shutil.disk_usage(CAPTURE_DIR)
            percent_free = usage.free / usage.total if usage.total else 0
            level = "VERMELHO" if total >= 10 * GIB or percent_free < .10 else "AMARELO" if total >= 5 * GIB else "OK"
            self.storage_state.configure(
                text=f"Armazenamento: {_format_bytes(total)} capturados · {_format_bytes(usage.free)} livres · {level}"
            )
            self.start_button.configure(state="disabled" if status.active or not self.capture_allowed else "normal")
            count = self.store.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            kills = self.store.conn.execute("SELECT COUNT(*) FROM events WHERE type='drop_item_field'").fetchone()[0]
            lines = [
                f"Captura ativa       {'SIM' if status.active else 'NÃO'}",
                f"Segmentos atuais    {len(status.files)}",
                f"Tamanho da sessão   {_format_bytes(status.bytes_written)}",
                f"Eventos reconhecidos {count}",
                f"Kills estimadas      {kills}  (proxy por recompensa)",
                "",
                "Dados não confirmados permanecem ocultos.",
            ]
            self.metrics.configure(state="normal")
            self.metrics.delete("1.0", END)
            self.metrics.insert("1.0", "\n".join(lines))
            self.metrics.configure(state="disabled")
        except Exception:
            pass
        self.after(1000, self._poll)

    def _close(self) -> None:
        if self.capture.status().active and self.minimize_to_tray:
            try:
                import pystray
                from PIL import Image
                if not self.tray:
                    image = Image.open(ASSETS / "karvalho-primary-gold.png")
                    self.tray = pystray.Icon(
                        "RF NEXT INFO", image, "RF NEXT INFO · captura visível",
                        pystray.Menu(
                            pystray.MenuItem("Abrir", lambda: self.after(0, self.deiconify)),
                            pystray.MenuItem("Encerrar", lambda: self.after(0, self._exit)),
                        ),
                    )
                    threading.Thread(target=self.tray.run, daemon=True).start()
                self.withdraw()
                return
            except Exception:
                pass
        self._exit()

    def _exit(self) -> None:
        if self.capture.status().active:
            if not messagebox.askyesno("Encerrar", "A captura está ativa. Parar com segurança e encerrar?"):
                return
            self.capture.stop()
        if self.tray:
            self.tray.stop()
        self.store.close()
        self.destroy()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sample, marks = _capture_summary({"events": [{
            "type": "collection_snapshot_chunk",
            "data": {"fields": {"character_name": "Carvalho"}, "records": [
                {"collection_index": 1001, "completed_slots": [0, 2]}
            ]},
        }]})
        assert sample["character"] == "Carvalho" and marks == {"1001": [1, 3]}
        raise SystemExit(0)
    App().mainloop()

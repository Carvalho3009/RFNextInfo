from __future__ import annotations

import ctypes
import json
import os
import re
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
from app.support_log import configure as configure_log, recent_lines
from app.updater import download_verified, latest
from core.capture import GIB, PktmonCapture
from core.store import CaptureStore

VERSION = "1.0.3"
STATE_DIR = Path(os.getenv("LOCALAPPDATA", Path.home())) / "Karvalho" / "RFNextInfo"
MACHINE_STATE_DIR = (
    Path(os.environ["PROGRAMDATA"]) / "Karvalho" / "RFNextInfo"
    if os.getenv("PROGRAMDATA")
    else STATE_DIR / "machine"
)
CAPTURE_DIR = Path.home() / "Documents" / "Capturas"
EXPORT_DIR = CAPTURE_DIR / "Exportados"
ASSETS = ROOT / "assets"
DB_PATH = STATE_DIR / "capture.sqlite3"
PREFERENCES_PATH = STATE_DIR / "preferences.json"
LOG_PATH = MACHINE_STATE_DIR / "logs" / "rfnext-info.log"


def _item_names() -> dict[str, str]:
    try:
        return json.loads(
            (ROOT / "core" / "item_names.json").read_text(encoding="utf-8-sig")
        )
    except (OSError, ValueError):
        return {}


ITEM_NAMES = _item_names()


def _format_bytes(value: int) -> str:
    number = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if number < 1024 or unit == "TB":
            return f"{number:.1f} {unit}" if unit != "B" else f"{int(number)} B"
        number /= 1024
    return f"{number:.1f} TB"


def _safe_name(value: str, fallback: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value.strip())
    value = re.sub(r"\s+", "-", value).strip(".- ")
    return (value or fallback)[:50]


def _capture_prefix(session_id: str) -> str | None:
    match = re.search(r"-(\d{8}-\d{6})-(\d+)$", session_id)
    return f"rfnext-{match.group(1)}-{int(match.group(2)):03d}" if match else None


def _capture_summary(envelope: dict) -> tuple[dict, dict[str, list[int]]]:
    summary = {
        "character": "",
        "level": None,
        "exp": None,
        "exp_percent": None,
        "exp_gained": 0,
        "credits": 0,
        "contribution": None,
        "market_events": 0,
        "kills": 0,
        "loot": [],
    }
    marks: dict[str, list[int]] = {}
    for event in envelope.get("events", []):
        data = event.get("data") or {}
        fields = data.get("fields") if isinstance(data.get("fields"), dict) else data
        summary["character"] = str(
            fields.get("character_name")
            or fields.get("character")
            or summary["character"]
        )
        summary["level"] = fields.get("level", summary["level"])
        summary["exp"] = fields.get("exp", summary["exp"])
        summary["exp_percent"] = fields.get(
            "exp_percent", summary["exp_percent"]
        )
        if isinstance(fields.get("gain_exp"), (int, float)):
            summary["exp_gained"] += fields["gain_exp"]
        for credit_key in ("gain_credit", "credit_gain", "credits"):
            if isinstance(fields.get(credit_key), (int, float)):
                summary["credits"] += fields[credit_key]
                break
        if isinstance(fields.get("contribution_total"), (int, float)):
            summary["contribution"] = fields["contribution_total"]
        kind = str(event.get("type", "")).lower()
        if "exchange" in kind or "market" in kind:
            summary["market_events"] += 1
        if event.get("type") == "drop_item_field":
            summary["kills"] += 1
            for item in data.get("results", []):
                summary["loot"].append(
                    {
                        "item": (
                            item.get("item_name")
                            or ITEM_NAMES.get(str(item.get("item_index")))
                            or item.get("item_index")
                        ),
                        "count": item.get("count"),
                        "gain_total": item.get("gain_total"),
                    }
                )
        for record in (
            data.get("records", []) if isinstance(data.get("records"), list) else []
        ):
            collection_id = record.get("collection_index")
            slots = record.get("completed_slots")
            if collection_id is not None and isinstance(slots, list):
                marks[str(collection_id)] = sorted(
                    {
                        int(slot) + 1
                        for slot in slots
                        if isinstance(slot, int) and 0 <= slot < 10
                    }
                )
    return summary, marks


def _recycle(paths: list[Path]) -> bool:
    existing = [str(path.resolve()) for path in paths if path.exists()]
    if not existing:
        return True

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", ctypes.c_bool),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    operation = SHFILEOPSTRUCTW(
        None,
        3,
        "\0".join(existing) + "\0\0",
        None,
        0x0040 | 0x0010 | 0x0400,
        False,
        None,
        None,
    )
    return (
        ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation)) == 0
        and not operation.fAnyOperationsAborted
    )


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"RF NEXT INFO · Karvalho · {VERSION}")
        self.geometry("1020x740")
        self.minsize(860, 650)
        self.configure(bg="#070909")
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        MACHINE_STATE_DIR.mkdir(parents=True, exist_ok=True)
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        self.log = configure_log(LOG_PATH, VERSION)
        self.license = LicenseClient(
            MACHINE_STATE_DIR,
            version=VERSION,
            legacy_paths=(STATE_DIR / "license.json",),
        )
        self.capture = PktmonCapture(CAPTURE_DIR)
        self.store = CaptureStore(DB_PATH)
        self.last_files: list[Path] = []
        self.capture_allowed = False
        self.current_session = self.store.latest_session()
        self.tray = None
        self._last_poll_error = ""
        self.prefs: dict = {}
        self._style()
        self._build()
        self._load_preferences()
        self._refresh_info()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Control-F8>", lambda _: self.start_capture())
        self.bind("<Control-F9>", lambda _: self.stop_capture())
        self.after(600, self._poll)

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            ".", background="#070909", foreground="#F4F2EB", font=("Segoe UI", 10)
        )
        style.configure("TFrame", background="#070909")
        style.configure(
            "Panel.TFrame",
            background="#0d1110",
            bordercolor="#6d5428",
            relief="solid",
        )
        style.configure("TLabel", background="#070909", foreground="#F4F2EB")
        style.configure("Muted.TLabel", foreground="#b9b5aa")
        style.configure(
            "Gold.TLabel", foreground="#D4A64D", font=("Segoe UI Semibold", 12)
        )
        style.configure(
            "Title.TLabel", foreground="#F4F2EB", font=("Segoe UI Semibold", 23)
        )
        style.configure(
            "TButton", background="#D4A64D", foreground="#070909", padding=(13, 9)
        )
        style.map(
            "TButton",
            background=[("active", "#e1b75f"), ("disabled", "#6d5428")],
        )
        style.configure("Quiet.TButton", background="#111614", foreground="#F4F2EB")
        style.configure("TNotebook", background="#070909", borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background="#111614",
            foreground="#b9b5aa",
            padding=(14, 9),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#D4A64D")],
            foreground=[("selected", "#070909")],
        )
        style.configure(
            "TEntry",
            fieldbackground="#050707",
            foreground="#F4F2EB",
            insertcolor="#F4F2EB",
        )
        style.configure(
            "Horizontal.TProgressbar",
            background="#D4A64D",
            troughcolor="#111614",
            bordercolor="#6d5428",
        )

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
            ttk.Label(header, text="KARVALHO", style="Gold.TLabel").pack(
                side=LEFT, padx=(0, 22)
            )
        title = ttk.Frame(header)
        title.pack(side=LEFT)
        ttk.Label(title, text="RF NEXT INFO", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title,
            text="Captura passiva, leitura local e exportação controlada.",
            style="Muted.TLabel",
        ).pack(anchor="w")

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill=BOTH, expand=True, padx=22, pady=(0, 12))
        self.capture_tab = ttk.Frame(self.tabs, padding=18)
        self.info_tab = ttk.Frame(self.tabs, padding=18)
        self.license_tab = ttk.Frame(self.tabs, padding=18)
        self.tutorial_tab = ttk.Frame(self.tabs, padding=18)
        self.tabs.add(self.capture_tab, text="Captura")
        self.tabs.add(self.info_tab, text="Informações")
        self.tabs.add(self.license_tab, text="Licença")
        self.tabs.add(self.tutorial_tab, text="Tutorial")
        self._capture_ui()
        self._info_ui()
        self._license_ui()
        self._tutorial_ui()
        ttk.Label(
            self,
            text=f"Discord: Carvalho  ·  carvalho@tuta.com  ·  {VERSION}",
            style="Muted.TLabel",
        ).pack(pady=(0, 15))

    def _capture_ui(self) -> None:
        status = ttk.Frame(self.capture_tab, style="Panel.TFrame", padding=18)
        status.pack(fill=X)
        self.capture_state = ttk.Label(status, text="Pronto", style="Gold.TLabel")
        self.capture_state.grid(row=0, column=0, sticky="w")
        self.license_state = ttk.Label(
            status, text="Licença: verificando", style="Muted.TLabel"
        )
        self.license_state.grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.storage_state = ttk.Label(
            status, text="Armazenamento: calculando", style="Muted.TLabel"
        )
        self.storage_state.grid(row=2, column=0, sticky="w", pady=(5, 0))
        buttons = ttk.Frame(self.capture_tab, padding=(0, 18))
        buttons.pack(fill=X)
        self.start_button = ttk.Button(
            buttons, text="Iniciar captura  Ctrl+F8", command=self.start_capture
        )
        self.start_button.pack(side=LEFT)
        self.stop_button = ttk.Button(
            buttons,
            text="Parar  Ctrl+F9",
            style="Quiet.TButton",
            command=self.stop_capture,
        )
        self.stop_button.pack(side=LEFT, padx=10)
        ttk.Button(
            buttons,
            text="Exportar JSON + CSV",
            style="Quiet.TButton",
            command=self.export,
        ).pack(side=LEFT)

        profile = ttk.Frame(self.capture_tab, style="Panel.TFrame", padding=18)
        profile.pack(fill=X)
        ttk.Label(profile, text="Profile do site", style="Gold.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(profile, text="Personagem 1", style="Gold.TLabel").grid(
            row=0, column=1, sticky="w", padx=(14, 0)
        )
        ttk.Label(profile, text="Personagem 2 (opcional)", style="Gold.TLabel").grid(
            row=0, column=2, sticky="w", padx=(14, 0)
        )
        self.profile = ttk.Entry(profile)
        self.character1 = ttk.Entry(profile)
        self.character2 = ttk.Entry(profile)
        self.profile.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.character1.grid(
            row=1, column=1, sticky="ew", padx=(14, 0), pady=(8, 0)
        )
        self.character2.grid(
            row=1, column=2, sticky="ew", padx=(14, 0), pady=(8, 0)
        )
        for column in range(3):
            profile.columnconfigure(column, weight=1)
        ttk.Label(
            profile,
            text=(
                "A identidade automática usa o UID confirmado do fluxo. "
                "Os nomes acima são o fallback para o site."
            ),
            style="Muted.TLabel",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(7, 0))
        self.auto_export = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            profile,
            text="Exportar automaticamente ao parar para Documentos\\Capturas\\Exportados",
            variable=self.auto_export,
            command=self._save_preferences,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(9, 0))

        self.metrics = tk.Text(
            self.capture_tab,
            height=10,
            bg="#050707",
            fg="#F4F2EB",
            insertbackground="#F4F2EB",
            relief="solid",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground="#6d5428",
            font=("Consolas", 10),
            state="disabled",
        )
        self.metrics.pack(fill=BOTH, expand=True, pady=(18, 0))

    def _info_ui(self) -> None:
        ttk.Label(
            self.info_tab, text="Informações da sessão", style="Title.TLabel"
        ).pack(anchor="w")
        ttk.Label(
            self.info_tab,
            text=(
                "Valores são separados pela identidade confirmada do personagem. "
                "Campos ainda não decodificados permanecem como —."
            ),
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(5, 12))
        self.info_text = tk.Text(
            self.info_tab,
            bg="#050707",
            fg="#F4F2EB",
            relief="solid",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground="#6d5428",
            font=("Consolas", 10),
            state="disabled",
        )
        self.info_text.pack(fill=BOTH, expand=True)

    def _license_ui(self) -> None:
        ttk.Label(
            self.license_tab, text="Ativar instalação", style="Title.TLabel"
        ).pack(anchor="w")
        ttk.Label(
            self.license_tab,
            text=(
                "A ativação fica lembrada neste computador e é preservada nas "
                "atualizações. A chave é enviada uma vez e não fica salva; "
                "a licença valida a cada 24 horas e possui até 72 horas offline."
            ),
            style="Muted.TLabel",
            wraplength=820,
        ).pack(anchor="w", pady=(6, 16))
        self.key_entry = ttk.Entry(self.license_tab, show="•")
        self.key_entry.pack(fill=X)
        ttk.Button(
            self.license_tab, text="Ativar licença", command=self.activate
        ).pack(anchor="w", pady=12)
        self.activation_status = ttk.Label(
            self.license_tab, text="", style="Muted.TLabel", wraplength=820
        )
        self.activation_status.pack(anchor="w")
        ttk.Label(
            self.license_tab,
            text=f"Versão instalada: {VERSION} · log técnico ativo",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(8, 4))
        support_buttons = ttk.Frame(self.license_tab)
        support_buttons.pack(anchor="w")
        ttk.Button(
            support_buttons,
            text="Enviar log técnico",
            style="Quiet.TButton",
            command=self.send_diagnostic,
        ).pack(side=LEFT)
        ttk.Button(
            support_buttons,
            text="Abrir pasta do log",
            style="Quiet.TButton",
            command=self.open_log_folder,
        ).pack(side=LEFT, padx=10)
        ttk.Button(
            support_buttons,
            text="Salvar cópia do log",
            style="Quiet.TButton",
            command=self.save_log_copy,
        ).pack(side=LEFT)
        ttk.Separator(self.license_tab).pack(fill=X, pady=24)
        ttk.Label(
            self.license_tab, text="Atualizações", style="Gold.TLabel"
        ).pack(anchor="w")
        self.channel = tk.StringVar(value="stable")
        ttk.Radiobutton(
            self.license_tab,
            text="Estável",
            value="stable",
            variable=self.channel,
            command=self._save_preferences,
        ).pack(anchor="w")
        ttk.Radiobutton(
            self.license_tab,
            text="Beta",
            value="beta",
            variable=self.channel,
            command=self._save_preferences,
        ).pack(anchor="w")
        self.update_button = ttk.Button(
            self.license_tab,
            text="Verificar atualização",
            style="Quiet.TButton",
            command=self.check_update,
        )
        self.update_button.pack(anchor="w", pady=(12, 8))
        self.update_progress = ttk.Progressbar(
            self.license_tab,
            mode="determinate",
            maximum=100,
        )
        self.update_progress.pack(fill=X)
        self.update_status = ttk.Label(
            self.license_tab,
            text="",
            style="Muted.TLabel",
        )
        self.update_status.pack(anchor="w", pady=(4, 10))
        ttk.Button(
            self.license_tab,
            text="Abrir versão anterior",
            style="Quiet.TButton",
            command=self.rollback,
        ).pack(anchor="w")

    def _tutorial_ui(self) -> None:
        text = (
            "1. Ative esta instalação na aba Licença. A ativação será lembrada nas próximas aberturas.\n\n"
            "2. Em Captura, informe o Profile do site e um ou dois personagens. Clique em Iniciar; o Windows pede permissão administrativa para o Pktmon nativo.\n\n"
            "3. Abra até dois clientes do RF NEXT. A identificação usa o UID confirmado de cada fluxo e a aba Informações mostra os dados separados.\n\n"
            "4. Pare a captura e aguarde a leitura. Cada parada cria uma sessão independente; capturas diferentes não são misturadas.\n\n"
            "5. Exporte. Cada personagem recebe JSON e CSV com nome Profile-Personagem-datahora-contador. Eventos não decodificados geram um diagnóstico separado e só são enviados com sua autorização. Para relatar um problema do programa, use Enviar log técnico na aba Licença.\n\n"
            "6. Confira o tamanho informado. Somente depois da exportação validada o programa oferece enviar os segmentos brutos à Lixeira.\n\n"
            "Privacidade: captura passiva local, sem injeção no jogo, token de sessão, atualização silenciosa ou telemetria."
        )
        ttk.Label(
            self.tutorial_tab, text="Comece em seis passos", style="Title.TLabel"
        ).pack(anchor="w")
        ttk.Label(
            self.tutorial_tab,
            text=text,
            wraplength=850,
            justify=LEFT,
            style="Muted.TLabel",
        ).pack(anchor="w", pady=15)

    def _load_preferences(self) -> None:
        try:
            self.prefs = json.loads(PREFERENCES_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.prefs = {}
        if "minimize_to_tray" not in self.prefs:
            self.prefs["minimize_to_tray"] = messagebox.askyesno(
                "Comportamento ao fechar",
                "Ao fechar a janela, manter a captura visível na área de notificação?\n\n"
                "Você poderá encerrar pelo ícone Karvalho.",
            )
        self.minimize_to_tray = bool(self.prefs["minimize_to_tray"])
        self.profile.insert(0, str(self.prefs.get("profile", "")))
        self.character1.insert(0, str(self.prefs.get("character1", "")))
        self.character2.insert(0, str(self.prefs.get("character2", "")))
        self.auto_export.set(bool(self.prefs.get("auto_export", False)))
        self.channel.set(
            self.prefs.get("channel")
            if self.prefs.get("channel") in {"stable", "beta"}
            else "stable"
        )
        last_session = str(self.prefs.get("last_session") or "")
        if _capture_prefix(last_session):
            self.current_session = last_session
        try:
            running = self.capture.system_running()
            prefix = str(self.prefs.get("capture_prefix") or "")
            files = tuple(CAPTURE_DIR.glob(f"{prefix}*.etl")) if prefix else ()
            if running and not files:
                candidates = sorted(
                    CAPTURE_DIR.glob("rfnext-*.etl"),
                    key=lambda path: path.stat().st_mtime_ns,
                    reverse=True,
                )
                if candidates:
                    match = re.match(
                        r"^(rfnext-\d{8}-\d{6}-\d{3})\d*\.etl$",
                        candidates[0].name,
                    )
                    if not match:
                        match = re.match(
                            r"^(rfnext-\d{8}-\d{6})\d+\.etl$",
                            candidates[0].name,
                        )
                    prefix = match.group(1) if match else ""
                    files = (
                        tuple(CAPTURE_DIR.glob(f"{prefix}*.etl"))
                        if prefix
                        else ()
                    )
            if prefix and files and (
                running or bool(self.prefs.get("capture_pending"))
            ):
                match = re.match(
                    r"^rfnext-(\d{8}-\d{6})-(\d{3})$", prefix
                )
                if match and _capture_prefix(self.current_session or "") != prefix:
                    profile = _safe_name(
                        self.profile.get().strip(), "Profile"
                    )
                    self.current_session = (
                        f"{profile}-{match.group(1)}-{int(match.group(2)):03d}"
                    )
                else:
                    legacy = re.match(r"^rfnext-(\d{8}-\d{6})$", prefix)
                    if legacy and legacy.group(1) not in (
                        self.current_session or ""
                    ):
                        profile = _safe_name(
                            self.profile.get().strip(), "Profile"
                        )
                        counter = int(self.prefs.get("session_counter", 0))
                        self.current_session = (
                            f"{profile}-{legacy.group(1)}-{counter:03d}"
                        )
                status = self.capture.attach(prefix)
                self.last_files = list(status.files)
                self.prefs.update(
                    capture_prefix=prefix,
                    capture_pending=True,
                )
                self.capture_state.configure(
                    text=(
                        f"Captura pendente recuperada · {len(status.files)} "
                        "segmento(s) · clique Parar para analisar"
                    )
                )
                self.log.info(
                    "capture_recovered active=%s segments=%d",
                    status.active,
                    len(status.files),
                )
        except Exception:
            self.log.exception("capture_recovery_failed")
        self._save_preferences()

    def _save_preferences(self) -> None:
        self.prefs.update(
            {
                "profile": self.profile.get().strip(),
                "character1": self.character1.get().strip(),
                "character2": self.character2.get().strip(),
                "auto_export": self.auto_export.get(),
                "channel": self.channel.get(),
                "last_session": self.current_session,
            }
        )
        PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = PREFERENCES_PATH.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.prefs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, PREFERENCES_PATH)

    def _run(self, job, done) -> None:
        def worker():
            try:
                result = job()
                self.after(0, lambda: done(result, None))
            except Exception as error:
                if hasattr(self, "log"):
                    self.log.exception(
                        "background_job_failed job=%s",
                        getattr(job, "__name__", type(job).__name__),
                    )
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
            self.activation_status.configure(
                text=f"Não foi possível ativar: {error}"
            )
            return
        self.activation_status.configure(
            text=f"Instalação ativa até {claims['valid_until']}."
        )
        self._refresh_license()

    def _refresh_license(self) -> tuple[bool, str]:
        allowed, message = self.license.refresh_if_due(VERSION)
        self.capture_allowed = allowed
        self.license_state.configure(text=f"Licença: {message}")
        self.start_button.configure(
            state="normal"
            if allowed and not self.capture.status().active
            else "disabled"
        )
        return allowed, message

    def start_capture(self) -> None:
        allowed, message = self._refresh_license()
        if not allowed:
            return messagebox.showwarning("Captura bloqueada", message)
        if self.capture.status().active:
            return messagebox.showwarning(
                "Captura já ativa",
                "O PktMon já está capturando. Clique em Parar para recuperar "
                "e analisar os arquivos existentes.",
            )
        profile = self.profile.get().strip()
        characters = [
            name
            for name in (
                self.character1.get().strip(),
                self.character2.get().strip(),
            )
            if name
        ]
        if not profile or not characters:
            return messagebox.showwarning(
                "Identificação",
                "Informe o Profile do site e pelo menos um personagem.",
            )
        counter = int(self.prefs.get("session_counter", 0)) + 1
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        session_id = (
            f"{_safe_name(profile, 'Profile')}-{stamp}-{counter:03d}"
        )
        capture_prefix = f"rfnext-{stamp}-{counter:03d}"
        try:
            self.capture.start(capture_prefix)
        except Exception as error:
            self.log.exception("capture_start_failed")
            return messagebox.showerror("Não foi possível iniciar", str(error))
        self.current_session = session_id
        self.prefs.update(
            session_counter=counter,
            capture_prefix=capture_prefix,
            capture_pending=True,
        )
        try:
            self._save_preferences()
        except OSError:
            self.log.exception("capture_state_save_failed")
        self.log.info("capture_started ports=12000,12020,12040")
        self.capture_state.configure(
            text="Capturando até dois clientes em TCP/12000, 12020 e 12040"
        )

    def stop_capture(self) -> None:
        if not self.current_session:
            try:
                running = self.capture.status().active
            except Exception as error:
                return messagebox.showerror("Falha ao consultar PktMon", str(error))
            if not running:
                return messagebox.showwarning(
                    "Sessão", "Não existe sessão atual para encerrar."
                )
            if not messagebox.askyesno(
                "PktMon externo ativo",
                "O PktMon está ativo sem uma sessão reconhecida pelo programa. "
                "Deseja encerrá-lo? Nenhum arquivo será apagado.",
            ):
                return
            try:
                self.capture.stop()
                self.capture_state.configure(
                    text="PktMon externo encerrado · nenhum arquivo foi apagado"
                )
            except Exception as error:
                messagebox.showerror("Falha ao parar", str(error))
            return
        if not self.capture.attached:
            prefix = str(
                self.prefs.get("capture_prefix")
                or _capture_prefix(self.current_session)
                or ""
            )
            if prefix and tuple(CAPTURE_DIR.glob(f"{prefix}*.etl")):
                self.capture.attach(prefix)
        try:
            status = self.capture.stop()
            self.last_files = list(status.files)
            self.log.info("capture_stopped segments=%d", len(self.last_files))
            self.capture_state.configure(text="Lendo segmentos capturados…")
        except Exception as error:
            self.log.exception("capture_stop_failed")
            return messagebox.showerror("Falha ao parar", str(error))
        session_id = self.current_session

        def ingest():
            store = CaptureStore(DB_PATH)
            try:
                added = 0
                failures = []
                for path in self.last_files:
                    try:
                        added += store.ingest(path, session_id=session_id)
                    except Exception as error:
                        self.log.exception("capture_segment_ingest_failed")
                        failures.append(f"{path.name}: {error}")
                return added, failures
            finally:
                store.close()

        def ingest_done(result, error):
            if error:
                text = f"Captura encerrada · leitura falhou: {error}"
            else:
                added, failures = result
                self.log.info(
                    "capture_ingested events=%d failures=%d",
                    added,
                    len(failures),
                )
                text = f"Captura encerrada · {added} eventos novos"
                if failures:
                    text += (
                        f" · {len(failures)} segmento(s) ignorado(s): "
                        + "; ".join(failures)
                    )
                else:
                    self.prefs["capture_pending"] = False
                    self._save_preferences()
            self.capture_state.configure(text=text)
            self._refresh_info()
            if not error and self.auto_export.get():
                self._export_to(EXPORT_DIR)

        self._run(ingest, ingest_done)

    def _session_parts(self) -> tuple[str, int]:
        match = re.search(r"-(\d{8}-\d{6})-(\d+)$", self.current_session or "")
        if match:
            return match.group(1), int(match.group(2))
        return datetime.now().strftime("%Y%m%d-%H%M%S"), int(
            self.prefs.get("session_counter", 0)
        )

    def _character_exports(self) -> list[dict[str, str | bool | None]]:
        if not self.current_session:
            return []
        detected = self.store.session_profiles(self.current_session)
        manual = [
            name
            for name in (
                self.character1.get().strip(),
                self.character2.get().strip(),
            )
            if name
        ]
        if len(detected) > 2:
            raise ValueError(
                "Mais de dois personagens foram identificados nesta sessão."
            )
        stats = self.store.session_stats(self.current_session)
        if len(detected) > 1 and int(stats["unassigned"] or 0):
            raise ValueError(
                "Há eventos reconhecidos sem UID nesta sessão; a exportação foi "
                "bloqueada para não misturar os dois personagens."
            )
        if not detected:
            if len(manual) > 1:
                raise ValueError(
                    "Dois personagens foram informados, mas a captura não trouxe "
                    "UID suficiente para separar os eventos com segurança."
                )
            return [
                {
                    "uid": None,
                    "name": manual[0] if manual else "Nao-identificado",
                    "include_unassigned": True,
                }
            ]
        unused = manual.copy()
        result = []
        for index, item in enumerate(detected):
            name = item["name"]
            match = next(
                (
                    candidate
                    for candidate in unused
                    if candidate.casefold() == name.casefold()
                ),
                None,
            )
            if match:
                unused.remove(match)
                name = match
            elif not name and unused:
                name = unused.pop(0)
            result.append(
                {
                    "uid": item["uid"],
                    "name": name or f"Personagem-{index + 1}",
                    "include_unassigned": len(detected) == 1,
                }
            )
        return result

    def export(self) -> None:
        if not self.current_session:
            self.current_session = self.store.latest_session()
        if not self.current_session:
            return messagebox.showwarning(
                "Exportação", "Nenhuma sessão capturada está disponível."
            )
        pending_files = self.capture.segment_files()
        if pending_files and not self.store.session_sources(self.current_session):
            return messagebox.showwarning(
                "Captura pendente",
                "Os arquivos capturados ainda não foram analisados. Clique em "
                "Parar, aguarde a leitura e tente exportar novamente.",
            )
        target = filedialog.askdirectory(
            title="Escolha a pasta de exportação", initialdir=str(EXPORT_DIR)
        )
        if target:
            self._export_to(Path(target))

    def _diagnostic_file(
        self,
        target: Path,
        capture_id: str,
        session_id: str,
        *,
        include_logs: bool = False,
    ) -> Path | None:
        return self.store.export_diagnostics(
            target,
            capture_id,
            session_id,
            logs=recent_lines(LOG_PATH) if include_logs else None,
        )

    def open_log_folder(self) -> None:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        os.startfile(LOG_PATH.parent)

    def save_log_copy(self) -> None:
        lines = recent_lines(LOG_PATH)
        if not lines:
            return messagebox.showinfo(
                "Log técnico", "Ainda não há registros para salvar."
            )
        target = filedialog.asksaveasfilename(
            title="Salvar cópia sanitizada do log",
            defaultextension=".txt",
            initialfile=(
                f"RFNextInfo-log-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
            ),
            filetypes=(("Arquivo de texto", "*.txt"),),
        )
        if not target:
            return
        path = Path(target)
        temporary = path.with_name(f"{path.name}.tmp")
        try:
            temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
            os.replace(temporary, path)
            self.log.info("log_copy_saved")
            messagebox.showinfo("Log técnico", "Cópia sanitizada salva.")
        except OSError as error:
            temporary.unlink(missing_ok=True)
            messagebox.showerror("Log técnico", str(error))

    def send_diagnostic(self) -> None:
        if not self.license.lease:
            return messagebox.showwarning(
                "Diagnóstico", "Ative a licença antes de enviar."
            )
        if not messagebox.askyesno(
            "Enviar log técnico",
            "Autoriza enviar o log técnico sanitizado?\n\n"
            "Não são incluídos payload, IP, UID, personagem, licença, chave ou token.",
        ):
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        session_id = f"suporte-{stamp}"
        try:
            diagnostic = self._diagnostic_file(
                EXPORT_DIR,
                f"diagnostico-tecnico-{stamp}",
                session_id,
                include_logs=True,
            )
        except Exception as error:
            self.log.exception("diagnostic_export_failed")
            return messagebox.showerror("Diagnóstico", str(error))
        if not diagnostic:
            return messagebox.showinfo(
                "Diagnóstico", "Ainda não há informações técnicas para enviar."
            )
        self._run(
            lambda: self.license.upload_diagnostic(diagnostic, VERSION),
            self._diagnostic_done,
        )

    def _diagnostic_done(self, result, error) -> None:
        if error:
            self.log.error(
                "diagnostic_upload_failed error=%s", type(error).__name__
            )
            return messagebox.showinfo(
                "Diagnóstico",
                f"Não foi possível enviar. O arquivo foi preservado:\n{error}",
            )
        self.log.info("diagnostic_uploaded")
        messagebox.showinfo(
            "Diagnóstico", f"Enviado com protocolo {result.get('receipt')}."
        )

    def _export_to(self, target: Path) -> None:
        if not self.current_session:
            return
        profile = self.profile.get().strip() or "Profile"
        stamp, counter = self._session_parts()
        try:
            characters = self._character_exports()
            results = []
            for character in characters:
                name = str(character["name"])
                capture_id = (
                    f"{_safe_name(profile, 'Profile')}-"
                    f"{_safe_name(name, 'Personagem')}-{stamp}-{counter:03d}"
                )
                result = self.store.export(
                    target,
                    capture_id,
                    session_id=self.current_session,
                    character_uid=character["uid"],
                    include_unassigned=bool(character["include_unassigned"]),
                    context={
                        "profile": profile,
                        "character_name": name,
                        "installation_id": self.license.installation_id,
                        "license_lease": self.license.lease,
                        "app_version": VERSION,
                        "session_counter": counter,
                    },
                )
                envelope = json.loads(
                    result.json_path.read_text(encoding="utf-8")
                )
                detected, marks = _capture_summary(envelope)
                envelope["capture"] = detected
                envelope["profiles"] = [
                    {
                        "profile": profile,
                        "name": name,
                        "character_uid": character["uid"],
                        "marks": marks,
                    }
                ]
                temporary = result.json_path.with_suffix(".json.tmp")
                temporary.write_text(
                    json.dumps(envelope, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                json.loads(temporary.read_text(encoding="utf-8"))
                os.replace(temporary, result.json_path)
                results.append(result)
            diagnostic = self._diagnostic_file(
                target,
                (
                    f"{_safe_name(profile, 'Profile')}-diagnostico-"
                    f"{stamp}-{counter:03d}"
                ),
                self.current_session,
            )
            total = sum(
                result.json_path.stat().st_size
                + result.csv_path.stat().st_size
                for result in results
            ) + (diagnostic.stat().st_size if diagnostic else 0)
            raw_files = self.store.session_sources(self.current_session)
            raw_bytes = int(
                self.store.session_stats(self.current_session)["raw_bytes"] or 0
            )
        except Exception as error:
            self.log.exception("export_failed")
            return messagebox.showerror("Exportação falhou", str(error))

        if diagnostic and messagebox.askyesno(
            "Diagnóstico sanitizado",
            "Existem eventos ainda não decodificados. O arquivo separado não "
            "contém payload, IP, UID, personagem ou licença.\n\n"
            "Autoriza enviar ao desenvolvedor?",
        ):
            self._run(
                lambda: self.license.upload_diagnostic(diagnostic, VERSION),
                self._diagnostic_done,
            )
        self.log.info("export_completed characters=%d bytes=%d", len(results), total)

        erase = messagebox.askyesno(
            "Exportação concluída",
            f"{len(results)} personagem(ns), JSON + CSV validados: "
            f"{_format_bytes(total)}.\n\n"
            f"Enviar {_format_bytes(raw_bytes)} de segmentos desta sessão para "
            "a Lixeira e remover somente esta sessão do histórico local?",
        )
        if erase:
            if not _recycle(raw_files):
                return messagebox.showwarning(
                    "Lixeira",
                    "Alguns segmentos não puderam ser movidos. "
                    "O histórico local foi preservado.",
                )
            try:
                self.store.clear_exported(self.current_session)
                self.last_files = []
                self.capture_state.configure(
                    text="Exportação concluída · sessão enviada à Lixeira"
                )
                self.current_session = self.store.latest_session()
                self._save_preferences()
                self._refresh_info()
            except Exception as error:
                messagebox.showerror(
                    "Limpeza incompleta",
                    "Os arquivos exportados permanecem válidos, mas a sessão "
                    f"local não foi limpa: {error}",
                )

    def _refresh_info(self) -> None:
        lines = []
        if not self.current_session:
            lines = ["Nenhuma sessão disponível."]
        else:
            stats = self.store.session_stats(self.current_session)
            started, ended = stats["started_ns"], stats["ended_ns"]
            duration = (
                max(0, int((ended - started) / 1_000_000_000))
                if isinstance(started, int) and isinstance(ended, int)
                else 0
            )
            lines.extend(
                [
                    f"Sessão              {self.current_session}",
                    f"Tempo               {duration // 60}m {duration % 60}s",
                    f"Eventos reconhecidos {stats['recognized']}",
                    f"Sem personagem       {stats['unassigned']}",
                    f"Não decodificados   {stats['unknown']}",
                    f"Dados brutos         {_format_bytes(int(stats['raw_bytes'] or 0))}",
                    "",
                ]
            )
            try:
                characters = self._character_exports()
            except ValueError as error:
                lines.extend([f"Separação pendente  {error}", ""])
                characters = []
            for character in characters:
                envelope = self.store.session_envelope(
                    self.current_session,
                    character["uid"],
                    bool(character["include_unassigned"]),
                )
                summary, _ = _capture_summary(envelope)
                exp_percent = summary["exp_percent"]
                exp_percent_text = (
                    f"{exp_percent:.2f}%"
                    if isinstance(exp_percent, (int, float))
                    else "—"
                )
                lines.extend(
                    [
                        f"[{character['name']}]",
                        f"UID                 {character['uid'] or 'aguardando identificação'}",
                        f"Level               {summary['level'] if summary['level'] is not None else '—'}",
                        f"EXP                 {summary['exp'] if summary['exp'] is not None else '—'}",
                        f"EXP no level        {exp_percent_text}",
                        f"EXP obtida          {summary['exp_gained']}",
                        f"Créditos            {summary['credits'] if summary['credits'] else '—'}",
                        f"Contribuição        {summary['contribution'] if summary['contribution'] is not None else '—'}",
                        f"Mercado             {summary['market_events']} evento(s)",
                        f"Kills estimadas     {summary['kills']} (proxy por recompensa)",
                        "Loot                "
                        + (
                            ", ".join(
                                f"{item['item']} x{item['count']}"
                                for item in summary["loot"][:10]
                            )
                            if summary["loot"]
                            else "—"
                        ),
                        "",
                    ]
                )
        self.info_text.configure(state="normal")
        self.info_text.delete("1.0", END)
        self.info_text.insert("1.0", "\n".join(lines))
        self.info_text.configure(state="disabled")

    def check_update(self) -> None:
        self.update_button.configure(state="disabled")
        self.update_progress.configure(value=0)
        self.update_status.configure(text="Consultando atualizações…")
        self._run(lambda: latest(self.channel.get()), self._update_found)

    def _update_found(self, release, error) -> None:
        if error:
            self.update_button.configure(state="normal")
            return self.update_status.configure(
                text=f"Atualização indisponível: {error}"
            )
        tag = str(release.get("tag_name", ""))
        notes = str(release.get("body", "")).strip()[:800]
        if tag.lstrip("v") == VERSION:
            self.update_button.configure(state="normal")
            self.update_progress.configure(value=100)
            return self.update_status.configure(
                text="Você já usa a versão mais recente."
            )
        if not messagebox.askyesno(
            "Atualização encontrada",
            f"{tag}\n\n{notes}\n\nBaixar e verificar agora?",
        ):
            self.update_button.configure(state="normal")
            self.update_status.configure(text="Atualização cancelada.")
            return
        public_key = self.license.state.get("public_key")
        if not public_key:
            self.update_button.configure(state="normal")
            self.update_status.configure(text="Ative a licença antes de atualizar.")
            return messagebox.showwarning(
                "Atualização",
                "Ative a licença para obter a chave pública de verificação.",
            )
        def progress(phase: str, downloaded: int, total: int | None) -> None:
            self.after(
                0,
                lambda: self._update_progress_changed(
                    phase, downloaded, total
                ),
            )

        self._run(
            lambda: download_verified(release, public_key, progress),
            self._update_downloaded,
        )

    def _update_progress_changed(
        self, phase: str, downloaded: int, total: int | None
    ) -> None:
        if phase == "manifest":
            self.update_status.configure(text="Verificando manifesto assinado…")
            return
        if phase == "verify":
            self.update_progress.configure(value=99)
            self.update_status.configure(text="Verificando integridade do instalador…")
            return
        percent = min(100, downloaded * 100 / total) if total else 0
        self.update_progress.configure(value=percent)
        size = _format_bytes(downloaded)
        suffix = f" de {_format_bytes(total)}" if total else ""
        self.update_status.configure(
            text=f"Baixando atualização: {percent:.0f}% · {size}{suffix}"
        )

    def _update_downloaded(self, installer, error) -> None:
        self.update_button.configure(state="normal")
        if error:
            self.update_progress.configure(value=0)
            self.update_status.configure(text=f"Falha na atualização: {error}")
            return messagebox.showerror("Atualização rejeitada", str(error))
        self.update_progress.configure(value=100)
        self.update_status.configure(text="Download concluído e verificado.")
        if self.capture.attached and self.capture.status().active:
            return messagebox.showwarning(
                "Captura ativa",
                "Pare a captura e aguarde a leitura terminar antes de atualizar.",
            )
        if messagebox.askyesno(
            "Atualização verificada",
            "Assinatura e SHA-256 conferem.\n\n"
            "O RF NEXT INFO será fechado e o instalador será aberto. Continuar?",
        ):
            if getattr(sys, "frozen", False):
                rollback = STATE_DIR / "rollback" / "RFNextInfo.exe"
                rollback.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sys.executable, rollback)
            self._save_preferences()
            try:
                os.startfile(installer)
            except OSError as launch_error:
                self.log.exception("update_installer_launch_failed")
                return messagebox.showerror(
                    "Não foi possível abrir o instalador", str(launch_error)
                )
            if self.tray:
                self.tray.stop()
            self.store.close()
            self.log.info("app_closed_for_update")
            self.destroy()

    def rollback(self) -> None:
        previous = STATE_DIR / "rollback" / "RFNextInfo.exe"
        if not previous.is_file():
            return messagebox.showinfo(
                "Versão anterior",
                "Ainda não existe uma versão anterior preservada.",
            )
        if messagebox.askyesno(
            "Abrir versão anterior",
            "A versão anterior será aberta como executável preservado. "
            "Feche a versão atual antes de capturar.",
        ):
            os.startfile(previous)

    def _poll(self) -> None:
        try:
            status = self.capture.status()
            total = sum(path.stat().st_size for path in CAPTURE_DIR.glob("*.etl"))
            usage = shutil.disk_usage(CAPTURE_DIR)
            percent_free = usage.free / usage.total if usage.total else 0
            level = (
                "VERMELHO"
                if total >= 10 * GIB or percent_free < 0.10
                else "AMARELO"
                if total >= 5 * GIB
                else "OK"
            )
            self.storage_state.configure(
                text=(
                    f"Armazenamento: {_format_bytes(total)} capturados · "
                    f"{_format_bytes(usage.free)} livres · {level}"
                )
            )
            self.start_button.configure(
                state="disabled"
                if status.active or not self.capture_allowed
                else "normal"
            )
            stats = (
                self.store.session_stats(self.current_session)
                if self.current_session
                else {"recognized": 0, "unknown": 0, "unassigned": 0}
            )
            kills = (
                self.store.conn.execute(
                    """SELECT COUNT(*) FROM events
                       WHERE session_id=? AND type='drop_item_field'""",
                    (self.current_session,),
                ).fetchone()[0]
                if self.current_session
                else 0
            )
            lines = [
                f"Captura ativa        {'SIM' if status.active else 'NÃO'}",
                f"Sessão atual         {self.current_session or '—'}",
                f"Segmentos atuais     {len(status.files)}",
                f"Tamanho da sessão    {_format_bytes(status.bytes_written)}",
                f"Eventos reconhecidos {stats['recognized']}",
                f"Sem personagem       {stats['unassigned']}",
                f"Não decodificados    {stats['unknown']}",
                f"Kills estimadas      {kills}  (proxy por recompensa)",
                "",
                "Dados não confirmados permanecem ocultos.",
            ]
            self.metrics.configure(state="normal")
            self.metrics.delete("1.0", END)
            self.metrics.insert("1.0", "\n".join(lines))
            self.metrics.configure(state="disabled")
            self._last_poll_error = ""
        except Exception as error:
            if str(error) != self._last_poll_error:
                self._last_poll_error = str(error)
                self.log.exception("status_poll_failed")
        self.after(1000, self._poll)

    def report_callback_exception(self, exc, value, tb) -> None:
        self.log.error("tk_callback_failed", exc_info=(exc, value, tb))
        messagebox.showerror(
            "Falha inesperada",
            "O problema foi registrado. Use “Enviar log técnico” "
            "na aba Licença para ajudar na correção.",
        )

    def _close(self) -> None:
        self._save_preferences()
        if (
            self.capture.attached
            and self.capture.status().active
            and self.minimize_to_tray
        ):
            try:
                import pystray
                from PIL import Image

                if not self.tray:
                    image = Image.open(ASSETS / "karvalho-primary-gold.png")
                    self.tray = pystray.Icon(
                        "RF NEXT INFO",
                        image,
                        "RF NEXT INFO · captura visível",
                        pystray.Menu(
                            pystray.MenuItem(
                                "Abrir", lambda: self.after(0, self.deiconify)
                            ),
                            pystray.MenuItem(
                                "Encerrar", lambda: self.after(0, self._exit)
                            ),
                        ),
                    )
                    threading.Thread(target=self.tray.run, daemon=True).start()
                self.withdraw()
                return
            except Exception:
                pass
        self._exit()

    def _exit(self) -> None:
        if self.capture.attached and self.capture.status().active:
            if not messagebox.askyesno(
                "Encerrar",
                "A captura está ativa. Parar com segurança e encerrar?",
            ):
                return
            self.capture.stop()
        self._save_preferences()
        if self.tray:
            self.tray.stop()
        self.store.close()
        self.log.info("app_closed")
        self.destroy()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sample, marks = _capture_summary(
            {
                "events": [
                    {
                        "type": "collection_snapshot_chunk",
                        "data": {
                            "fields": {"character_name": "Carvalho"},
                            "records": [
                                {
                                    "collection_index": 1001,
                                    "completed_slots": [0, 2],
                                }
                            ],
                        },
                    }
                ]
            }
        )
        assert sample["character"] == "Carvalho"
        assert marks == {"1001": [1, 3]}
        assert _safe_name("Profile/Teste", "Profile") == "Profile-Teste"
        raise SystemExit(0)
    App().mainloop()

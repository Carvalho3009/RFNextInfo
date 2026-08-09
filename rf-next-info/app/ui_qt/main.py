from __future__ import annotations

import os
import sys
import ctypes
import json
import math
import subprocess
import threading
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtNetwork, QtWidgets

from app.ui_qt.data import (
    CLASS_ICON_FILES,
    DB_PATH,
    PREFERENCES_PATH,
    RARITY_COLORS,
    ReadOnlySnapshotReader,
    load_farm_catalog,
    load_license_status,
    load_preferences,
    save_preferences,
)
from app.license import LicenseClient
from app.main import (
    BIOSUITS,
    CAPTURE_DIR,
    DEFAULT_PORTS,
    LOG_PATH,
    MACHINE_STATE_DIR,
    ROVERS,
    RELEASE_SEQUENCE,
    STATE_DIR,
    VERSION,
    _recycle,
)
from app.paths import (
    KNOWLEDGE_DB_PATH,
    UPDATES_DIR,
    ensure_runtime_layout,
)
from app.site_profile import SiteProfileClient
from app.support_log import (
    configure as configure_log,
    install_exception_hooks,
    recent_lines,
    set_detailed,
)
from app.updater import (
    download_verified,
    latest,
    verify_downloaded,
    verify_manifest,
)
from app.ui_qt.operations import (
    CaptureEngine,
    DEFAULT_GLOBAL_SHORTCUTS,
    ExportEngine,
    GlobalHotkeys,
    MonitorEngine,
    SiteUploadEngine,
)
from core.store import CaptureStore
from core.knowledge import KnowledgeStore


PAGES = (
    ("Visão geral", "Resumo dos clientes e da sessão atual."),
    ("Envios", "Envios dos dados já lidos pela captura contínua."),
    ("Monitor PvE", "Vida do último monstro atacado confirmado."),
    ("Monitor PvP", "Vida e DPS HP do último jogador em combate confirmado."),
    ("Boss", "Bosses próximos, vida, DPS estimado e tempo restante."),
    ("Alertas", "Avisos visuais e sonoros configuráveis."),
    ("Subsessões", "Histórico e criação de subsessões."),
    ("Configurações", "Preferências do programa e do Profile."),
    ("Tutorial", "Primeiros passos e atalhos."),
)
MONITOR_PAGES = {2: "pve", 3: "pvp", 4: "boss"}
MONITOR_SHORTCUT_OPTIONS = tuple(
    f"{modifier}+F{number}"
    for modifier in ("Ctrl", "Alt", "Shift")
    for number in range(1, 13)
    if not (modifier == "Ctrl" and number in {8, 9})
)

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
ASSETS = ROOT / "assets"
MOB_ICONS = ASSETS / "mob-icons"
INSTANCE_SERVER_NAME = "RFQOL.App"
DISCORD_URL = "https://discord.gg/D3hhdMgkj"

SUBSESSION_COLUMNS = (
    ("select", "", 28, True),
    ("name", "Subsessão", 210, True),
    ("character", "Personagem", 120, True),
    ("client", "Cliente", 72, False),
    ("status", "Status", 90, False),
    ("time", "Tempo", 82, True),
    ("map", "Mapa", 130, False),
    ("spot", "Spot", 150, False),
    ("mobs", "Mobs", 220, False),
    ("levels", "Níveis", 160, False),
    ("kills", "Kills", 58, True),
    ("finalizations", "Finaliz.", 72, False),
    ("exp_total", "XP total", 90, True),
    ("exp_percent", "XP %", 66, True),
    ("exp_hour", "XP/h", 90, True),
    ("exp_hour_percent", "XP/h %", 72, True),
    ("credits", "Créditos", 96, False),
    ("credits_hour", "Créditos/h", 100, False),
    ("contribution", "Contrib.", 96, True),
    ("contribution_hour", "Contrib./h", 100, False),
    ("loot_total", "Loot", 64, False),
    ("loot_common", "Comum", 64, False),
    ("loot_uncommon", "Incomum", 72, False),
    ("loot_rare", "Raro", 64, False),
    ("loot_epic", "Épico", 64, False),
    ("upload", "Envio", 88, False),
)
SUBSESSION_COLUMN_INDEX = {
    key: index for index, (key, _label, _width, _visible) in enumerate(SUBSESSION_COLUMNS)
}


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = (
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    )


def _process_memory_bytes() -> int | None:
    if os.name != "nt":
        return None
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(_ProcessMemoryCounters),
        wintypes.DWORD,
    )
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    success = psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(),
        ctypes.byref(counters),
        counters.cb,
    )
    return int(counters.WorkingSetSize) if success else None


def _load_fonts() -> None:
    for name in ("Saira.ttf", "SairaSemiCondensed-Bold.ttf"):
        QtGui.QFontDatabase.addApplicationFont(str(ASSETS / name))


def _label(text: str, role: str = "") -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    if role:
        label.setProperty("role", role)
    return label


class _MovableOverlay(QtWidgets.QDialog):
    position_changed = QtCore.Signal(QtCore.QPoint)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_offset: QtCore.QPoint | None = None

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_offset = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            self._drag_offset is not None
            and event.buttons() & QtCore.Qt.MouseButton.LeftButton
        ):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            event.button() == QtCore.Qt.MouseButton.LeftButton
            and self._drag_offset is not None
        ):
            self._drag_offset = None
            self.position_changed.emit(self.pos())
            event.accept()
            return
        super().mouseReleaseEvent(event)


class MainWindow(QtWidgets.QMainWindow):
    data_loaded = QtCore.Signal(object)
    data_failed = QtCore.Signal(str)
    combat_loaded = QtCore.Signal(object)
    combat_failed = QtCore.Signal(str)
    capture_operation_done = QtCore.Signal(str, object, object)
    site_operation_done = QtCore.Signal(str, object, object)
    global_hotkey_triggered = QtCore.Signal(str)
    update_progress_changed = QtCore.Signal(str, int, object)

    def __init__(
        self,
        *,
        load_data: bool = True,
        database_path: Path = DB_PATH,
        preferences_path: Path = PREFERENCES_PATH,
    ) -> None:
        super().__init__()
        ensure_runtime_layout()
        self.database_path = Path(database_path)
        database = CaptureStore(self.database_path)
        database.close()
        self.knowledge_path = (
            KNOWLEDGE_DB_PATH
            if self.database_path == DB_PATH
            else self.database_path.with_name("knowledge.sqlite3")
        )
        self.preferences_path = Path(preferences_path)
        self.active_client = 0
        self.snapshot: dict[str, object] = {}
        self.preferences: dict[str, object] = {}
        self.selected_subsessions: set[str] = set()
        self.subsession_page = 1
        self.editing_subsession_id: str | None = None
        self.capture_engine: CaptureEngine | None = None
        self.monitor_engine: MonitorEngine | None = None
        self.monitor_enabled = {"pve": False, "pvp": False, "boss": False}
        self.monitor_client_enabled = {
            "pve": [False, False],
            "pvp": [False, False],
        }
        self.monitor_next_due = {"pve": 0.0, "pvp": 0.0, "boss": 0.0}
        self.monitor_controls: dict[str, dict[str, Any]] = {}
        self.boss_overlay: QtWidgets.QDialog | None = None
        self.pvp_overlay: QtWidgets.QDialog | None = None
        self.alert_last_fired: dict[str, float] = {}
        self.capture_busy = False
        self.site_busy = False
        self.pending_capture_action: str | None = None
        self.license_active = False
        self.capture_recovery_attempted = False
        self.license_refresh_running = False
        self.last_license_refresh_at = 0.0
        self.exit_requested = False
        self.next_read_at = 0.0
        self.last_heartbeat_at = 0.0
        self.last_storage_scan_at = 0.0
        self.storage_bytes = 0
        self.last_capture_session = ""
        self.live_preview_error = ""
        self.live_combat_events: list[dict[str, Any]] = []
        self.live_combat_ports: tuple[tuple[int, ...], ...] = ()
        self.pending_export_cleanup = False
        self.pending_observation_session = ""
        self.pending_auto_market: tuple[str, str] | None = None
        try:
            self.log_path = LOG_PATH
            self.log = configure_log(self.log_path, VERSION)
        except OSError as error:
            raise OSError(f"Não foi possível gravar o log em {LOG_PATH}") from error
        install_exception_hooks(self.log)
        self.license_client = LicenseClient(
            MACHINE_STATE_DIR, version=VERSION
        )
        self.license_client.record_release_sequence(RELEASE_SEQUENCE)
        self.snapshot_reader = ReadOnlySnapshotReader(
            self.database_path, self.license_client
        )
        self.site_profile = SiteProfileClient(
            STATE_DIR, version=VERSION
        )
        self.site_uploader = SiteUploadEngine(
            self.database_path, self.site_profile, self.license_client
        )
        self.export_engine = ExportEngine(self.database_path, self.license_client)
        self.data_load_running = False
        self.data_load_pending = False
        self.combat_load_running = False
        self.combat_load_pending = False
        self.controls_initialized = False
        self.setObjectName("mainWindow")
        self.setWindowTitle(f"RF QOL — {VERSION}")
        self.setMinimumSize(1180, 664)
        self.resize(1440, 810)

        icon = QtGui.QIcon(str(ASSETS / "karvalho-symbol-gold.png"))
        self.setWindowIcon(icon)
        self._tray = self._build_tray(icon)

        root = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_topbar())
        layout.addWidget(self._build_body(), 1)
        layout.addWidget(self._build_footer())
        self.setCentralWidget(root)
        self.data_loaded.connect(self._apply_readonly_data)
        self.data_failed.connect(self._show_read_error)
        self.combat_loaded.connect(self._apply_combat_data)
        self.combat_failed.connect(self._show_combat_error)
        self.capture_operation_done.connect(self._capture_operation_finished)
        self.site_operation_done.connect(self._site_operation_finished)
        self.global_hotkey_triggered.connect(self._global_hotkey_action)
        self.update_progress_changed.connect(self._update_progress)
        self.page_stack.currentChanged.connect(self._page_changed)
        self.global_hotkeys = GlobalHotkeys(self.global_hotkey_triggered.emit)
        if load_data:
            self.global_hotkeys.start()
        self.capture_timer = QtCore.QTimer(self)
        self.capture_timer.timeout.connect(self._capture_tick)
        self.capture_timer.start(1000)
        if load_data:
            QtCore.QTimer.singleShot(0, self._load_readonly_data)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        if sys.platform == "win32" and QtWidgets.QApplication.platformName() == "windows":
            enabled = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(self.winId()), 20, ctypes.byref(enabled), ctypes.sizeof(enabled)
            )
        self._sync_responsive_layouts()

    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.WindowStateChange:
            QtCore.QTimer.singleShot(0, self._sync_responsive_layouts)

    def _sync_responsive_layouts(self) -> None:
        self._sync_overview_layout()
        self._sync_combat_layout()

    def _sync_overview_layout(self) -> None:
        if hasattr(self, "overview_secondary"):
            expanded = self.isMaximized() or self.isFullScreen()
            self.overview_secondary.setVisible(expanded)
            if hasattr(self, "primary_metric_groups"):
                for index, group in enumerate(self.primary_metric_groups):
                    self.primary_metric_grid.addWidget(group, index, 0, 1, 2)
                if expanded:
                    heights = []
                    for primary, secondary in zip(
                        self.primary_metric_groups, self.secondary_metric_groups
                    ):
                        height = max(primary.sizeHint().height(), secondary.sizeHint().height())
                        primary.setMinimumHeight(height)
                        secondary.setMinimumHeight(height)
                        heights.append(height)
                else:
                    heights = [group.sizeHint().height() for group in self.primary_metric_groups]
                    for group, height in zip(self.primary_metric_groups, heights):
                        group.setMinimumHeight(height)
                    for group in self.secondary_metric_groups:
                        group.setMinimumHeight(0)
                self.primary_metrics.setMinimumHeight(
                    sum(heights)
                    + self.primary_metric_grid.verticalSpacing() * (len(heights) - 1)
                )

    def _sync_combat_layout(self) -> None:
        expanded = self.isMaximized() or self.isFullScreen()
        for page in getattr(self, "combat_page_layouts", {}).values():
            layout = page["layout"]
            cards = page["cards"]
            for card in cards:
                layout.removeWidget(card)
            for row in range(3):
                layout.setRowStretch(row, 0)
            visible_cards = [card for card in cards if not card.isHidden()]
            if len(visible_cards) == 1:
                layout.addWidget(visible_cards[0], 0, 0, 1, 2)
                layout.setRowStretch(1, 1)
                layout.setColumnStretch(0, 1)
                layout.setColumnStretch(1, 0)
            elif expanded:
                for index, card in enumerate(visible_cards):
                    layout.addWidget(card, 0, index)
                layout.setRowStretch(1, 1)
                layout.setColumnStretch(0, 1)
                layout.setColumnStretch(1, 1)
            else:
                for index, card in enumerate(visible_cards):
                    layout.addWidget(card, index, 0, 1, 2)
                layout.setRowStretch(2, 1)
                layout.setColumnStretch(0, 1)
                layout.setColumnStretch(1, 0)

    def _build_tray(self, icon: QtGui.QIcon) -> QtWidgets.QSystemTrayIcon | None:
        if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QtWidgets.QSystemTrayIcon(icon, self)
        tray.setToolTip(f"RF QOL — {VERSION}")
        menu = QtWidgets.QMenu(self)
        self.tray_menu = menu
        show_action = menu.addAction("Abrir RF QOL")
        show_action.triggered.connect(self._show_from_tray)
        menu.addSeparator()
        self.tray_start_action = menu.addAction("Iniciar / continuar")
        self.tray_start_action.triggered.connect(self._start_capture)
        self.tray_pause_action = menu.addAction("Pausar")
        self.tray_pause_action.triggered.connect(self._pause_capture)
        self.tray_stop_action = menu.addAction("Encerrar")
        self.tray_stop_action.triggered.connect(self._stop_capture)
        menu.addSeparator()
        exit_action = menu.addAction("Sair")
        exit_action.triggered.connect(self._exit_application)
        tray.setContextMenu(menu)
        tray.activated.connect(self._tray_activated)
        tray.show()
        return tray

    def _tray_activated(self, reason: QtWidgets.QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QtWidgets.QSystemTrayIcon.ActivationReason.Trigger,
            QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _exit_application(self) -> None:
        self.exit_requested = True
        self.close()

    def _build_topbar(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QWidget(objectName="topbar")
        bar.setFixedHeight(60)
        row = QtWidgets.QHBoxLayout(bar)
        row.setContentsMargins(18, 0, 18, 0)
        row.setSpacing(18)
        for text, tone in (
            ("Licença — carregando", "muted"),
            ("Captura — não conectada", "info"),
            ("Última leitura: —", "muted"),
            ("Próx. atualização: —", "muted"),
            ("Armazenado: —", "muted"),
            ("RAM: —", "muted"),
        ):
            label = _label(text, tone)
            if text.startswith("Licença"):
                self.top_license = label
            elif text.startswith("Captura"):
                self.top_capture = label
            elif text.startswith("Última"):
                self.top_last_read = label
            elif text.startswith("Próx"):
                self.top_next_read = label
            elif text.startswith("Armazenado"):
                self.top_storage = label
            elif text.startswith("RAM"):
                self.top_memory = label
            row.addWidget(label)
        row.addStretch(1)
        for index, text in enumerate(
            ("Iniciar  Ctrl+F8", "Pausar", "Encerrar  Ctrl+F9", "Encerrar sem ler")
        ):
            button = QtWidgets.QPushButton(text)
            button.setEnabled(False)
            if index == 0:
                self.start_button = button
                button.clicked.connect(self._start_capture)
            elif index == 1:
                self.pause_button = button
                button.clicked.connect(self._pause_capture)
            elif index == 2:
                self.stop_button = button
                button.clicked.connect(self._stop_capture)
            else:
                self.stop_without_reading_button = button
                button.setToolTip(
                    "Interrompe a captura agora e preserva os arquivos brutos para leitura posterior."
                )
                button.clicked.connect(self._stop_capture_without_reading)
            row.addWidget(button)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+F8"), self, activated=self._start_capture)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+F9"), self, activated=self._stop_capture)
        return bar

    def _build_body(self) -> QtWidgets.QWidget:
        body = QtWidgets.QWidget(objectName="body")
        row = QtWidgets.QHBoxLayout(body)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._build_sidebar())

        workspace = QtWidgets.QWidget(objectName="workspace")
        column = QtWidgets.QVBoxLayout(workspace)
        column.setContentsMargins(24, 14, 24, 18)
        column.setSpacing(14)
        column.addWidget(self._build_clients())
        self.page_stack = QtWidgets.QStackedWidget(objectName="pageStack")
        for index, (title, description) in enumerate(PAGES):
            if title == "Visão geral":
                page = self._build_overview_page()
            elif title == "Envios":
                page = self._build_sends_page()
            elif title == "Monitor PvE":
                page = self._build_combat_page("pve")
            elif title == "Monitor PvP":
                page = self._build_combat_page("pvp")
            elif title == "Boss":
                page = self._build_combat_page("boss")
            elif title == "Alertas":
                page = self._build_alerts_page()
            elif title == "Subsessões":
                page = self._build_subsessions_page()
            elif title == "Configurações":
                page = self._build_settings_page()
            elif title == "Tutorial":
                page = self._build_tutorial_page()
            else:
                page = self._build_page(title, description)
            self.page_stack.addWidget(page)
        column.addWidget(self.page_stack, 1)
        row.addWidget(workspace, 1)
        return body

    def _build_sidebar(self) -> QtWidgets.QWidget:
        sidebar = QtWidgets.QWidget(objectName="sidebar")
        sidebar.setFixedWidth(210)
        column = QtWidgets.QVBoxLayout(sidebar)
        column.setContentsMargins(14, 22, 14, 18)
        column.setSpacing(8)

        logo = QtWidgets.QLabel(objectName="brandLogo")
        pixmap = QtGui.QPixmap(str(ASSETS / "karvalho-symbol-gold.png"))
        logo.setPixmap(pixmap.scaled(72, 72, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                     QtCore.Qt.TransformationMode.SmoothTransformation))
        logo.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        column.addWidget(logo)
        brand = _label("KARVALHO", "brand")
        brand.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        column.addWidget(brand)
        column.addSpacing(20)

        self.nav_group = QtWidgets.QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QtWidgets.QPushButton] = []
        for index, (title, _) in enumerate(PAGES):
            button = QtWidgets.QPushButton(title)
            button.setObjectName(f"nav{index}")
            button.setCheckable(True)
            button.setMinimumHeight(46)
            button.clicked.connect(lambda checked=False, page=index: self.page_stack.setCurrentIndex(page))
            self.nav_group.addButton(button, index)
            self.nav_buttons.append(button)
            column.addWidget(button)
        self.nav_buttons[0].setChecked(True)
        column.addStretch(1)
        return sidebar

    def _build_clients(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QWidget(objectName="clientBar")
        row = QtWidgets.QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        self.client_group = QtWidgets.QButtonGroup(bar)
        self.client_group.setExclusive(True)
        self.client_buttons: list[QtWidgets.QPushButton] = []
        self.client_uid_buttons: list[QtWidgets.QToolButton] = []
        for index, name in enumerate(("Cliente A · Definir nome", "Cliente B · Definir nome")):
            button = QtWidgets.QPushButton(name)
            button.setProperty("client", True)
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.clicked.connect(lambda checked=False, client=index: self._select_client(client))
            self.client_group.addButton(button, index)
            self.client_buttons.append(button)
            row.addWidget(button)
            rename = QtWidgets.QToolButton()
            rename.setText("✎")
            rename.setToolTip(f"Definir nome manual do Cliente {chr(65 + index)}")
            rename.clicked.connect(
                lambda checked=False, client=index: self._rename_client(client)
            )
            row.addWidget(rename)
            uid = QtWidgets.QToolButton()
            uid.setText("UID: Auto")
            uid.setToolTip(
                f"Escolher um personagem confirmado para o Cliente {chr(65 + index)}"
            )
            uid.clicked.connect(
                lambda checked=False, client=index: self._choose_client_uid(client)
            )
            self.client_uid_buttons.append(uid)
            row.addWidget(uid)
        row.addStretch(1)
        return bar

    def _build_page(self, title: str, description: str) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        page.setObjectName("page" + title.replace(" ", ""))
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(12)
        column.addWidget(_label(title, "title"))

        card = QtWidgets.QFrame(objectName="emptyCard")
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.addWidget(_label(description, "subtitle"))
        card_layout.addWidget(_label("Estrutura F1 — dados e ações reais ainda não conectados.", "muted"))
        card_layout.addStretch(1)
        column.addWidget(card, 1)
        return page

    def _build_combat_page(self, mode: str) -> QtWidgets.QWidget:
        if not hasattr(self, "combat_widgets"):
            self.combat_widgets: dict[str, list[dict[str, Any]]] = {}
            self.combat_page_layouts: dict[str, dict[str, Any]] = {}
        title = {"pve": "Monitor PvE", "pvp": "Monitor PvP", "boss": "Boss"}[mode]
        page = QtWidgets.QWidget(objectName=f"pageCombat{mode.upper()}")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(12)
        column.addWidget(_label(title, "title"))
        client_tabs = None
        if mode in {"pve", "pvp"}:
            client_tabs = QtWidgets.QTabBar()
            client_tabs.setExpanding(False)
            client_tabs.addTab("Cliente A")
            client_tabs.addTab("Cliente B")
            column.addWidget(client_tabs)
        controls = QtWidgets.QHBoxLayout()
        monitor_shortcut = DEFAULT_GLOBAL_SHORTCUTS[f"monitor_{mode}"]
        client_suffix = " Cliente A" if client_tabs is not None else ""
        enabled = QtWidgets.QPushButton(
            f"Ligar monitor{client_suffix}  {monitor_shortcut}"
        )
        enabled.setCheckable(True)
        enabled.toggled.connect(
            lambda checked, selected=mode: self._toggle_monitor(selected, checked)
        )
        interval = QtWidgets.QSpinBox()
        interval.setRange(1, 60)
        interval.setValue(2 if mode in {"pvp", "boss"} else 3)
        interval.setSuffix(" s")
        interval.valueChanged.connect(
            lambda _value, selected=mode: self._monitor_interval_changed(selected)
        )
        controls.addWidget(enabled)
        controls.addWidget(_label("Atualizar a cada", "muted"))
        controls.addWidget(interval)
        overlay = None
        if mode in {"pvp", "boss"}:
            shortcut = "Ctrl+Shift+F6" if mode == "pvp" else "Ctrl+Shift+F7"
            overlay = QtWidgets.QPushButton(f"Abrir overlay  {shortcut}")
            overlay.setCheckable(True)
            if mode == "pvp":
                overlay.setToolTip(
                    "Arraste o overlay com o botão esquerdo para mudar sua posição."
                )
            overlay.toggled.connect(
                self._toggle_pvp_overlay if mode == "pvp" else self._toggle_boss_overlay
            )
            controls.addWidget(overlay)
        controls.addStretch(1)
        column.addLayout(controls)
        self.monitor_controls[mode] = {
            "enabled": enabled,
            "interval": interval,
            "overlay": overlay,
            "shortcut": monitor_shortcut,
            "tabs": client_tabs,
        }
        if client_tabs is not None:
            client_tabs.currentChanged.connect(
                lambda index, selected=mode: self._monitor_client_changed(
                    selected, index
                )
            )
        description = _label(
            (
                "Stream efêmero em memória. Nenhum arquivo bruto é criado quando "
                "somente os monitores estão ligados."
            ),
            "muted",
        )
        description.setWordWrap(True)
        column.addWidget(description)
        scroll = QtWidgets.QScrollArea(objectName="pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        content = QtWidgets.QWidget(objectName="scrollContent")
        content_layout = QtWidgets.QGridLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(12)
        content_layout.setSizeConstraint(
            QtWidgets.QLayout.SizeConstraint.SetMinimumSize
        )
        widgets = []
        cards = []
        for index in range(2):
            card = QtWidgets.QFrame(objectName="panel")
            layout = QtWidgets.QVBoxLayout(card)
            layout.setContentsMargins(20, 16, 20, 16)
            layout.setSpacing(10)
            heading = _label(f"Cliente {chr(65 + index)} · aguardando personagem", "subtitle")
            target = _label("Último alvo confirmado: —", "subtitle")
            status = _label("Aguardando eventos confirmados de combate.", "muted")
            progress = QtWidgets.QProgressBar()
            progress.setRange(0, 1000)
            progress.setValue(0)
            progress.setTextVisible(False)
            stats = QtWidgets.QHBoxLayout()
            values: dict[str, QtWidgets.QLabel] = {}
            labels = [("current_hp", "Vida atual"), ("max_hp", "Vida máxima"), ("hp_percent", "Vida")]
            if mode == "pvp":
                labels.append(("dps_hp", "DPS HP · 10 s"))
            for key, label in labels:
                block = QtWidgets.QVBoxLayout()
                caption = _label(label, "muted")
                caption.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                value = _label("—", "data")
                value.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                values[key] = value
                block.addWidget(caption)
                block.addWidget(value)
                stats.addLayout(block, 1)
            layout.addWidget(heading)
            boss_layout = None
            boss_empty = None
            if mode == "boss":
                boss_panel = QtWidgets.QFrame(objectName="secondaryMetricGroup")
                boss_column = QtWidgets.QVBoxLayout(boss_panel)
                boss_column.setContentsMargins(14, 12, 14, 12)
                boss_column.setSpacing(8)
                boss_column.addWidget(_label("Boss próximo", "subtitle"))
                boss_empty = _label("Nenhum boss confirmado próximo.", "muted")
                boss_column.addWidget(boss_empty)
                boss_layout = QtWidgets.QVBoxLayout()
                boss_layout.setSpacing(8)
                boss_column.addLayout(boss_layout)
                layout.addWidget(boss_panel)
            nearby_layout = None
            nearby_empty = None
            if mode in {"pve", "pvp"}:
                nearby_panel = QtWidgets.QFrame(objectName="secondaryMetricGroup")
                nearby_column = QtWidgets.QVBoxLayout(nearby_panel)
                nearby_column.setContentsMargins(14, 12, 14, 12)
                nearby_column.setSpacing(12)
                nearby_column.addWidget(
                    _label(
                        "Mobs próximos" if mode == "pve" else "Jogadores próximos",
                        "subtitle",
                    )
                )
                nearby_empty = _label("Nenhum registro recente.", "muted")
                nearby_column.addWidget(nearby_empty)
                nearby_layout = QtWidgets.QVBoxLayout()
                nearby_layout.setSpacing(12)
                nearby_column.addLayout(nearby_layout)
                layout.addWidget(nearby_panel)
            if mode != "boss":
                layout.addWidget(target)
                layout.addWidget(progress)
                layout.addLayout(stats)
            layout.addWidget(status)
            content_layout.addWidget(card, index, 0, 1, 2)
            if client_tabs is not None and index:
                card.hide()
            cards.append(card)
            widgets.append(
                {
                    "heading": heading,
                    "target": target,
                    "status": status,
                    "progress": progress,
                    "boss_layout": boss_layout,
                    "boss_empty": boss_empty,
                    "nearby_layout": nearby_layout,
                    "nearby_empty": nearby_empty,
                    **values,
                }
            )
        page_empty = None
        if mode == "boss":
            page_empty = _label(
                "Nenhum Boss detectado pelos clientes ativos.", "muted"
            )
            page_empty.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            content_layout.addWidget(page_empty, 2, 0, 1, 2)
        self.combat_widgets[mode] = widgets
        content_layout.setRowStretch(2, 1)
        self.combat_page_layouts[mode] = {
            "mode": mode,
            "layout": content_layout,
            "cards": cards,
            "empty": page_empty,
        }
        scroll.setWidget(content)
        column.addWidget(scroll, 1)
        return page

    def _build_alerts_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageAlerts")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(12)
        column.addWidget(_label("Alertas", "title"))
        panel = QtWidgets.QFrame(objectName="panel")
        form = QtWidgets.QFormLayout(panel)
        form.setContentsMargins(20, 18, 20, 18)
        self.alert_character_enabled = QtWidgets.QCheckBox("Avisar aproximação")
        self.alert_character_names = QtWidgets.QLineEdit()
        self.alert_character_names.setPlaceholderText("Nomes separados por vírgula")
        character_row = QtWidgets.QHBoxLayout()
        character_row.addWidget(self.alert_character_enabled)
        character_row.addWidget(self.alert_character_names, 1)
        form.addRow("Personagens", character_row)
        self.alert_guild_enabled = QtWidgets.QCheckBox("Avisar aproximação")
        self.alert_guild_names = QtWidgets.QLineEdit()
        self.alert_guild_names.setPlaceholderText(
            "Disponível quando o ID/nome da guilda for confirmado"
        )
        guild_row = QtWidgets.QHBoxLayout()
        guild_row.addWidget(self.alert_guild_enabled)
        guild_row.addWidget(self.alert_guild_names, 1)
        form.addRow("Guildas", guild_row)
        self.alert_pvp_hit = QtWidgets.QCheckBox("Avisar ao sofrer ataque PvP")
        form.addRow("Combate", self.alert_pvp_hit)
        self.alert_boss = QtWidgets.QCheckBox("Avisar ao detectar boss próximo")
        form.addRow("Boss", self.alert_boss)
        self.alert_low_hp = QtWidgets.QCheckBox("Avisar abaixo de")
        self.alert_low_hp_percent = QtWidgets.QSpinBox()
        self.alert_low_hp_percent.setRange(1, 99)
        self.alert_low_hp_percent.setValue(30)
        self.alert_low_hp_percent.setSuffix(" %")
        hp_row = QtWidgets.QHBoxLayout()
        hp_row.addWidget(self.alert_low_hp)
        hp_row.addWidget(self.alert_low_hp_percent)
        hp_row.addStretch(1)
        form.addRow("Vida", hp_row)
        self.alert_sound = QtWidgets.QCheckBox("Som do sistema")
        self.alert_sound.setChecked(True)
        form.addRow("Aviso sonoro", self.alert_sound)
        save = QtWidgets.QPushButton("Salvar alertas")
        save.clicked.connect(self._save_alert_settings)
        form.addRow("", save)
        self.alert_status = _label(
            "Nenhum alerta recente. A verificação usa somente dados confirmados.",
            "muted",
        )
        self.alert_status.setWordWrap(True)
        form.addRow("Estado", self.alert_status)
        column.addWidget(panel)
        column.addStretch(1)
        return page

    def _build_overview_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageVisãogeral")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        column.addWidget(_label("Visão geral", "title"))
        self.overview_status = _label("Lendo a sessão mais recente…", "muted")
        column.addWidget(self.overview_status)

        scroll = QtWidgets.QScrollArea(objectName="pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        content = QtWidgets.QWidget(objectName="scrollContent")
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(10)
        self.overview_split = QtWidgets.QWidget()
        split_layout = QtWidgets.QHBoxLayout(self.overview_split)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(10)
        primary = QtWidgets.QWidget()
        primary_layout = QtWidgets.QVBoxLayout(primary)
        primary_layout.setContentsMargins(0, 0, 0, 0)
        primary_layout.setSpacing(10)

        hero = QtWidgets.QFrame(objectName="panel")
        hero_row = QtWidgets.QHBoxLayout(hero)
        hero_row.setContentsMargins(18, 16, 18, 16)
        self.rover_icon = QtWidgets.QLabel("—", objectName="roverIcon")
        self.rover_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.rover_icon.setFixedSize(96, 96)
        hero_row.addWidget(self.rover_icon)
        self.character_icon = QtWidgets.QLabel("—", objectName="characterIcon")
        self.character_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.character_icon.setFixedSize(72, 72)
        hero_row.addWidget(self.character_icon)
        identity = QtWidgets.QVBoxLayout()
        self.character_name = _label("Aguardando personagem", "hero")
        self.character_details = _label("Nível — · Classe — · Biosuit —", "muted")
        self.rover_name = _label("Rover —", "muted")
        identity.addWidget(self.character_name)
        identity.addWidget(self.character_details)
        identity.addWidget(self.rover_name)
        hero_row.addLayout(identity, 1)
        primary_layout.addWidget(hero)

        metrics = QtWidgets.QWidget()
        self.primary_metrics = metrics
        grid = QtWidgets.QGridLayout(metrics)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)
        self.metric_labels: dict[str, QtWidgets.QLabel] = {}

        def metric_group(
            title: str,
            definitions: tuple[tuple[str, str], ...],
            *,
            show_progress: bool = False,
        ) -> QtWidgets.QFrame:
            group = QtWidgets.QFrame(objectName="metricGroup")
            group_layout = QtWidgets.QVBoxLayout(group)
            group_layout.setContentsMargins(14, 11, 14, 11)
            group_layout.setSpacing(8)
            group_layout.addWidget(_label(title, "subtitle"))
            values = QtWidgets.QHBoxLayout()
            values.setSpacing(10)
            for index, (key, label_text) in enumerate(definitions):
                if index:
                    divider = QtWidgets.QWidget(objectName="metricDivider")
                    divider.setFixedWidth(1)
                    values.addWidget(divider)
                cell = QtWidgets.QVBoxLayout()
                caption = _label(label_text, "muted")
                caption.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                value = _label("—", "data")
                value.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                cell.addWidget(caption)
                cell.addWidget(value)
                values.addLayout(cell, 1)
                self.metric_labels[key] = value
            group_layout.addLayout(values)
            if show_progress:
                self.exp_progress = QtWidgets.QProgressBar()
                self.exp_progress.setRange(0, 10000)
                self.exp_progress.setTextVisible(False)
                group_layout.addWidget(self.exp_progress)
            return group

        character_exp = metric_group(
            "Experiência do personagem",
            (("exp", "Atual"), ("exp_missing", "Restante"), ("exp_percent", "Nível")),
            show_progress=True,
        )
        session_exp = metric_group(
            "Experiência da sessão",
            (("exp_gained", "Total"), ("exp_hour", "Por hora"), ("exp_hour_percent", "Por hora (%)")),
        )
        resources = metric_group(
            "Recursos da sessão",
            (("credits", "Créditos total"), ("credits_hour", "Créditos/h"),
             ("contribution", "Contribuição total"),
             ("contribution_hour", "Contribuição/h"), ("diamonds", "Diamantes")),
        )
        combat = metric_group(
            "Combate",
            (("kills", "Abates estimados"), ("finalizations", "Finalizações")),
        )
        loot = metric_group(
            "Loot da sessão",
            (("loot", "Total"), ("common", "Comum"), ("uncommon", "Incomum"),
             ("rare", "Raro"), ("epic", "Épico")),
        )
        self.primary_metric_grid = grid
        self.primary_metric_groups = (
            character_exp, session_exp, resources, combat, loot,
        )
        for group, position in zip(
            self.primary_metric_groups,
            ((0, 0, 1, 1), (0, 1, 1, 1), (1, 0, 1, 2),
             (2, 0, 1, 1), (2, 1, 1, 1)),
        ):
            grid.addWidget(group, *position)
        self.exp_percent = self.metric_labels["exp_percent"]
        primary_layout.addWidget(metrics)

        subsession = QtWidgets.QFrame(objectName="accentPanel")
        subsession_layout = QtWidgets.QVBoxLayout(subsession)
        subsession_layout.setContentsMargins(16, 12, 16, 12)
        subsession_layout.addWidget(_label("Subsessão ativa", "subtitle"))
        self.active_subsession = _label("Nenhuma subsessão em andamento.", "muted")
        subsession_layout.addWidget(self.active_subsession)
        primary_layout.addWidget(subsession)
        primary_layout.addStretch(1)
        split_layout.addWidget(primary, 1)
        self.overview_secondary = self._build_secondary_overview()
        self.overview_secondary.setVisible(False)
        split_layout.addWidget(self.overview_secondary, 1)
        content_layout.addWidget(self.overview_split)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        column.addWidget(scroll, 1)
        return page

    def _build_secondary_overview(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        hero_card = QtWidgets.QFrame(objectName="panel")
        hero = QtWidgets.QHBoxLayout(hero_card)
        hero.setContentsMargins(18, 16, 18, 16)
        self.secondary_rover_icon = QtWidgets.QLabel("—", objectName="roverIcon")
        self.secondary_character_icon = QtWidgets.QLabel("—", objectName="characterIcon")
        self.secondary_rover_icon.setFixedSize(96, 96)
        self.secondary_character_icon.setFixedSize(72, 72)
        for icon in (self.secondary_rover_icon, self.secondary_character_icon):
            icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            hero.addWidget(icon)
        identity = QtWidgets.QVBoxLayout()
        self.secondary_character_name = _label("Aguardando personagem", "hero")
        self.secondary_character_details = _label("Nível — · Classe — · Biosuit —", "muted")
        self.secondary_rover_name = _label("Rover —", "muted")
        identity.addWidget(self.secondary_character_name)
        identity.addWidget(self.secondary_character_details)
        identity.addWidget(self.secondary_rover_name)
        hero.addLayout(identity, 1)
        layout.addWidget(hero_card)
        self.secondary_metric_labels: dict[str, QtWidgets.QLabel] = {}
        groups = (
            ("Experiência do personagem", (("exp", "Atual"), ("exp_missing", "Restante"), ("exp_percent", "Nível"))),
            ("Experiência da sessão", (("exp_gained", "Total"), ("exp_hour", "Por hora"), ("exp_hour_percent", "Por hora (%)"))),
            ("Recursos da sessão", (("credits", "Créditos total"), ("credits_hour", "Créditos/h"), ("contribution", "Contribuição total"), ("contribution_hour", "Contribuição/h"), ("diamonds", "Diamantes"))),
            ("Combate", (("kills", "Abates estimados"), ("finalizations", "Finalizações"))),
            ("Loot da sessão", (("loot", "Total"), ("common", "Comum"), ("uncommon", "Incomum"), ("rare", "Raro"), ("epic", "Épico"))),
        )
        self.secondary_metric_groups = []
        for title, definitions in groups:
            group = QtWidgets.QFrame(objectName="secondaryMetricGroup")
            group_layout = QtWidgets.QVBoxLayout(group)
            group_layout.setContentsMargins(14, 11, 14, 11)
            group_layout.setSpacing(8)
            group_layout.addWidget(_label(title, "subtitle"))
            values = QtWidgets.QHBoxLayout()
            values.setSpacing(10)
            for index, (key, caption) in enumerate(definitions):
                if index:
                    divider = QtWidgets.QWidget(objectName="metricDivider")
                    divider.setFixedWidth(1)
                    values.addWidget(divider)
                cell = QtWidgets.QVBoxLayout()
                label = _label(caption, "muted"); label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                value = _label("—", "data"); value.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                cell.addWidget(label); cell.addWidget(value)
                values.addLayout(cell, 1)
                self.secondary_metric_labels[key] = value
            group_layout.addLayout(values)
            if title == "Experiência do personagem":
                self.secondary_exp_progress = QtWidgets.QProgressBar()
                self.secondary_exp_progress.setRange(0, 10000)
                self.secondary_exp_progress.setTextVisible(False)
                group_layout.addWidget(self.secondary_exp_progress)
            layout.addWidget(group)
            self.secondary_metric_groups.append(group)
        active = QtWidgets.QFrame(objectName="accentPanel")
        active_layout = QtWidgets.QVBoxLayout(active)
        active_layout.addWidget(_label("Subsessão ativa", "subtitle"))
        self.secondary_active_subsession = _label("Nenhuma subsessão em andamento.", "muted")
        active_layout.addWidget(self.secondary_active_subsession)
        layout.addWidget(active)
        layout.addStretch(1)
        return panel

    def _build_sends_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageEnvios")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        column.addWidget(_label("Envios", "title"))
        column.addWidget(_label("Dados já lidos pela captura contínua.", "muted"))

        scroll = QtWidgets.QScrollArea(objectName="pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        content = QtWidgets.QWidget(objectName="scrollContent")
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(8)

        continuous = QtWidgets.QFrame(objectName="panel")
        continuous_layout = QtWidgets.QHBoxLayout(continuous)
        continuous_layout.setContentsMargins(16, 12, 16, 12)
        continuous_text = QtWidgets.QVBoxLayout()
        continuous_text.addWidget(_label("EXP e Loot · Contínuo", "subtitle"))
        self.send_continuous_status = _label("Lendo sessão…", "info")
        continuous_text.addWidget(self.send_continuous_status)
        continuous_layout.addLayout(continuous_text, 1)
        self.send_session_details = _label("Sessão —", "muted")
        continuous_layout.addWidget(self.send_session_details)
        content_layout.addWidget(continuous)
        self.discard_previous = QtWidgets.QCheckBox(
            "Descartar a sessão anterior ao iniciar"
        )
        self.discard_previous.setToolTip(
            "Move os segmentos anteriores para a Lixeira e remove somente aquela sessão."
        )
        content_layout.addWidget(self.discard_previous)

        grid = QtWidgets.QGridLayout()
        grid.setSpacing(8)
        self.send_status_labels: dict[str, QtWidgets.QLabel] = {}
        self.send_buttons: dict[tuple[str, int], QtWidgets.QPushButton] = {}
        domains = (
            ("character", "Personagem + equipamentos", "F1", False),
            ("market", "Mercado", "F2", True),
            ("codex", "Codex", "F3", False),
            ("memory_chips", "Memory Chips", "F4", False),
        )
        for index, (mode, title, shortcut, general) in enumerate(domains):
            card = QtWidgets.QFrame(objectName="panel")
            card_layout = QtWidgets.QVBoxLayout(card)
            card_layout.setContentsMargins(16, 12, 16, 12)
            heading = QtWidgets.QHBoxLayout()
            heading.addWidget(_label(title, "subtitle"))
            heading.addStretch(1)
            heading.addWidget(_label(shortcut, "shortcut"))
            card_layout.addLayout(heading)
            status = _label("Aguardando leitura", "info")
            self.send_status_labels[mode] = status
            card_layout.addWidget(status)
            actions = QtWidgets.QHBoxLayout()
            labels = ("Enviar Mercado · geral",) if general else ("Enviar Cliente A", "Enviar Cliente B")
            for client_index, text in enumerate(labels):
                button = QtWidgets.QPushButton(text)
                target_index = -1 if general else client_index
                button.clicked.connect(
                    lambda checked=False, selected=mode, target=target_index: self._send_mode(
                        selected, target
                    )
                )
                self.send_buttons[(mode, target_index)] = button
                actions.addWidget(button)
            card_layout.addLayout(actions)
            grid.addWidget(card, index // 2, index % 2)
        content_layout.addLayout(grid)

        selected = QtWidgets.QFrame(objectName="accentPanel")
        selected_layout = QtWidgets.QHBoxLayout(selected)
        selected_layout.setContentsMargins(16, 12, 16, 12)
        self.send_selected_status = _label("Nenhuma subsessão selecionada", "muted")
        selected_layout.addWidget(self.send_selected_status, 1)
        self.send_selected_button = QtWidgets.QPushButton("Enviar subsessões selecionadas")
        self.send_selected_button.clicked.connect(self._send_selected_subsessions)
        selected_layout.addWidget(self.send_selected_button)
        content_layout.addWidget(selected)
        privacy = QtWidgets.QFrame(objectName="panel")
        privacy_layout = QtWidgets.QVBoxLayout(privacy)
        privacy_layout.setContentsMargins(16, 12, 16, 12)
        privacy_layout.addWidget(_label("Privacidade e segurança", "subtitle"))
        privacy_layout.addWidget(_label(
            "Payloads sensíveis não são salvos nem enviados. Somente dados decodificados e autorizados saem deste computador.",
            "muted",
        ))
        content_layout.addWidget(privacy)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        column.addWidget(scroll, 1)
        return page

    def _build_subsessions_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageSubsessões")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        column.addWidget(_label("Subsessões", "title"))

        selector = QtWidgets.QWidget()
        selector_layout = QtWidgets.QHBoxLayout(selector)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.setSpacing(0)
        self.subsession_mode_group = QtWidgets.QButtonGroup(selector)
        self.subsession_mode_group.setExclusive(True)
        for index, title in enumerate(("Histórico", "Nova subsessão")):
            button = QtWidgets.QPushButton(title)
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.clicked.connect(lambda checked=False, mode=index: self.subsession_stack.setCurrentIndex(mode))
            self.subsession_mode_group.addButton(button, index)
            selector_layout.addWidget(button)
        column.addWidget(selector)

        self.subsession_stack = QtWidgets.QStackedWidget()
        self.subsession_stack.addWidget(self._build_subsession_history())
        self.subsession_stack.addWidget(self._build_subsession_form())
        column.addWidget(self.subsession_stack, 1)
        return page

    def _build_subsession_history(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        filters = QtWidgets.QHBoxLayout()
        self.subsession_search = QtWidgets.QLineEdit()
        self.subsession_search.setPlaceholderText("Buscar por nome, localização ou mob")
        self.subsession_search.textChanged.connect(self._reset_subsession_page)
        filters.addWidget(self.subsession_search, 1)
        self.subsession_filter = QtWidgets.QComboBox()
        self.subsession_filter.addItems(("Todas", "Cliente A", "Cliente B", "Em andamento", "Encerradas", "Enviadas", "Não enviadas"))
        self.subsession_filter.currentTextChanged.connect(self._reset_subsession_page)
        filters.addWidget(self.subsession_filter)
        self.subsession_page_size = QtWidgets.QComboBox()
        self.subsession_page_size.addItems(("5", "10", "20", "50"))
        self.subsession_page_size.setCurrentText("10")
        self.subsession_page_size.currentTextChanged.connect(self._reset_subsession_page)
        filters.addWidget(self.subsession_page_size)
        layout.addLayout(filters)

        actions = QtWidgets.QHBoxLayout()
        for text, callback in (
            ("Selecionar visíveis", self._toggle_visible_subsessions),
            ("Editar", self._edit_subsession),
            ("Renomear", self._rename_subsession),
            ("Encerrar", self._end_subsession),
            ("Excluir", self._delete_subsessions),
        ):
            button = QtWidgets.QPushButton(text)
            button.clicked.connect(callback)
            if text == "Excluir":
                button.setProperty("danger", True)
            actions.addWidget(button)
        self.subsession_columns_button = QtWidgets.QToolButton()
        self.subsession_columns_button.setText("Colunas")
        self.subsession_columns_button.setToolTip(
            "Escolha as colunas e arraste os cabeçalhos para mudar a ordem."
        )
        self.subsession_columns_button.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup
        )
        columns_menu = QtWidgets.QMenu(self.subsession_columns_button)
        self.subsession_column_actions: dict[str, QtGui.QAction] = {}
        for key, label_text, _width, visible in SUBSESSION_COLUMNS[1:]:
            action = columns_menu.addAction(label_text)
            action.setCheckable(True)
            action.setChecked(visible)
            action.toggled.connect(
                lambda checked, selected=key: self._set_subsession_column_visible(
                    selected, checked
                )
            )
            self.subsession_column_actions[key] = action
        columns_menu.addSeparator()
        columns_menu.addAction("Restaurar padrão", self._reset_subsession_columns)
        self.subsession_columns_button.setMenu(columns_menu)
        actions.addWidget(self.subsession_columns_button)
        actions.addStretch(1)
        self.subsession_upload_button = QtWidgets.QPushButton("Enviar selecionadas")
        self.subsession_upload_button.clicked.connect(self._send_selected_subsessions)
        actions.addWidget(self.subsession_upload_button)
        layout.addLayout(actions)

        self.subsession_table = QtWidgets.QTableWidget(0, len(SUBSESSION_COLUMNS))
        self.subsession_table.setHorizontalHeaderLabels(
            tuple(label for _key, label, _width, _visible in SUBSESSION_COLUMNS)
        )
        self.subsession_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.subsession_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.subsession_table.verticalHeader().setVisible(False)
        self.subsession_table.itemChanged.connect(self._subsession_selection_changed)
        header = self.subsession_table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setSectionsMovable(True)
        header.sectionDoubleClicked.connect(self._autofit_subsession_column)
        self._restoring_subsession_columns = True
        for column, (_key, _label_text, width, visible) in enumerate(SUBSESSION_COLUMNS):
            header.resizeSection(column, width)
            self.subsession_table.setColumnHidden(column, not visible)
        self._restoring_subsession_columns = False
        self.subsession_columns_timer = QtCore.QTimer(self)
        self.subsession_columns_timer.setSingleShot(True)
        self.subsession_columns_timer.setInterval(250)
        self.subsession_columns_timer.timeout.connect(
            self._save_subsession_columns
        )
        header.sectionMoved.connect(self._subsession_columns_changed)
        header.sectionResized.connect(self._subsession_columns_changed)
        layout.addWidget(self.subsession_table, 1)

        pagination = QtWidgets.QHBoxLayout()
        self.subsession_page_status = _label("Nenhum registro", "muted")
        pagination.addWidget(self.subsession_page_status)
        pagination.addStretch(1)
        previous = QtWidgets.QPushButton("Anterior")
        previous.clicked.connect(lambda: self._change_subsession_page(-1))
        next_page = QtWidgets.QPushButton("Próxima")
        next_page.clicked.connect(lambda: self._change_subsession_page(1))
        pagination.addWidget(previous)
        pagination.addWidget(next_page)
        layout.addLayout(pagination)
        return page

    def _build_subsession_form(self) -> QtWidgets.QWidget:
        scroll = QtWidgets.QScrollArea(objectName="pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        content = QtWidgets.QWidget(objectName="scrollContent")
        layout = QtWidgets.QFormLayout(content)
        layout.setContentsMargins(4, 4, 12, 4)
        layout.setSpacing(10)
        self.subsession_client = QtWidgets.QComboBox()
        self.subsession_client.addItems(("Cliente A", "Cliente B"))
        self.subsession_favorite = QtWidgets.QComboBox()
        load_favorite = QtWidgets.QPushButton("Carregar")
        load_favorite.clicked.connect(self._load_subsession_favorite)
        save_favorite = QtWidgets.QPushButton("Salvar favorito")
        save_favorite.clicked.connect(self._save_subsession_favorite)
        delete_favorite = QtWidgets.QPushButton("Excluir")
        delete_favorite.clicked.connect(self._delete_subsession_favorite)
        favorites = QtWidgets.QWidget()
        favorites_layout = QtWidgets.QHBoxLayout(favorites)
        favorites_layout.setContentsMargins(0, 0, 0, 0)
        favorites_layout.addWidget(self.subsession_favorite, 1)
        favorites_layout.addWidget(load_favorite)
        favorites_layout.addWidget(save_favorite)
        favorites_layout.addWidget(delete_favorite)
        self.subsession_map = QtWidgets.QComboBox()
        self.subsession_map.currentTextChanged.connect(self._subsession_map_changed)
        self.subsession_spot = QtWidgets.QComboBox()
        self.subsession_spot.currentTextChanged.connect(self._subsession_spot_changed)
        filter_levels = QtWidgets.QWidget()
        filter_levels_layout = QtWidgets.QHBoxLayout(filter_levels)
        filter_levels_layout.setContentsMargins(0, 0, 0, 0)
        filter_levels_layout.setSpacing(8)
        self.subsession_filter_level_from = QtWidgets.QSpinBox()
        self.subsession_filter_level_from.setRange(0, 999)
        self.subsession_filter_level_to = QtWidgets.QSpinBox()
        self.subsession_filter_level_to.setRange(0, 999)
        self.subsession_filter_level_from.setFixedWidth(110)
        self.subsession_filter_level_to.setFixedWidth(110)
        self.subsession_filter_level_from.valueChanged.connect(
            self._refilter_subsession_mobs
        )
        self.subsession_filter_level_to.valueChanged.connect(
            self._refilter_subsession_mobs
        )
        filter_levels_layout.addWidget(self.subsession_filter_level_from)
        filter_levels_layout.addWidget(_label("até", "muted"))
        filter_levels_layout.addWidget(self.subsession_filter_level_to)
        filter_levels_layout.addStretch(1)
        self.subsession_mobs = QtWidgets.QListWidget()
        self.subsession_mobs.setMinimumHeight(300)
        self.subsession_select_all = QtWidgets.QCheckBox("Selecionar todos os mobs")
        self.subsession_select_all.toggled.connect(self._toggle_all_mobs)
        self.subsession_other_mob = QtWidgets.QLineEdit()
        self.subsession_other_mob.setPlaceholderText("Nome de mob adicional")
        # Mantidos ocultos apenas para ler favoritos antigos sem perder dados.
        self.subsession_level_from = QtWidgets.QSpinBox(content)
        self.subsession_level_from.setRange(0, 999)
        self.subsession_level_from.hide()
        self.subsession_level_to = QtWidgets.QSpinBox(content)
        self.subsession_level_to.setRange(0, 999)
        self.subsession_level_to.hide()
        self.subsession_duration = QtWidgets.QSpinBox(); self.subsession_duration.setRange(0, 1440); self.subsession_duration.setSuffix(" min")
        self.subsession_name = QtWidgets.QLineEdit(); self.subsession_name.setPlaceholderText("Observação ou nome")
        self.auto_subsession = QtWidgets.QCheckBox("Criar a próxima automaticamente")
        self.auto_subsession_minutes = QtWidgets.QSpinBox(); self.auto_subsession_minutes.setRange(5, 240); self.auto_subsession_minutes.setSuffix(" min")
        automatic = QtWidgets.QWidget(); automatic_layout = QtWidgets.QHBoxLayout(automatic); automatic_layout.setContentsMargins(0,0,0,0); automatic_layout.addWidget(self.auto_subsession); automatic_layout.addWidget(self.auto_subsession_minutes); automatic_layout.addStretch(1)
        for label_text, widget in (
            ("Favorito", favorites), ("Cliente", self.subsession_client),
            ("Observação", self.subsession_name),
            ("Mapa", self.subsession_map),
            ("Spot", self.subsession_spot),
            ("Filtrar mobs por level", filter_levels),
            ("Mobs", self.subsession_mobs),
            ("", self.subsession_select_all),
            ("Mob extra", self.subsession_other_mob),
            ("Duração (0 = manual)", self.subsession_duration),
            ("Automática", automatic),
        ):
            layout.addRow(label_text, widget)
        self.subsession_form_layout = layout
        buttons = QtWidgets.QWidget(); buttons_layout = QtWidgets.QHBoxLayout(buttons); buttons_layout.setContentsMargins(0,0,0,0); buttons_layout.addStretch(1)
        cancel = QtWidgets.QPushButton("Cancelar"); cancel.clicked.connect(self._cancel_subsession_form)
        self.subsession_save = QtWidgets.QPushButton("Criar subsessão"); self.subsession_save.clicked.connect(self._save_subsession)
        buttons_layout.addWidget(cancel); buttons_layout.addWidget(self.subsession_save)
        layout.addRow("", buttons)
        scroll.setWidget(content)
        return scroll

    def _build_settings_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageConfigurações")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        column.addWidget(_label("Configurações", "title"))
        scroll = QtWidgets.QScrollArea(objectName="pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        content = QtWidgets.QWidget(objectName="scrollContent")
        grid = QtWidgets.QGridLayout(content)
        self.settings_grid = grid
        grid.setContentsMargins(0, 0, 8, 0)
        grid.setSpacing(8)

        capture = QtWidgets.QFrame(objectName="panel")
        self.settings_capture_panel = capture
        capture_form = QtWidgets.QFormLayout(capture)
        capture_form.addRow(_label("Capturas", "subtitle"))
        directory = QtWidgets.QWidget(); directory_layout = QtWidgets.QHBoxLayout(directory); directory_layout.setContentsMargins(0,0,0,0)
        self.setting_capture_directory = QtWidgets.QLineEdit(); browse = QtWidgets.QPushButton("Escolher…"); browse.clicked.connect(self._choose_capture_directory)
        directory_layout.addWidget(self.setting_capture_directory, 1); directory_layout.addWidget(browse)
        capture_form.addRow("Pasta", directory)
        self.setting_decode_interval = QtWidgets.QSpinBox(); self.setting_decode_interval.setRange(15, 300); self.setting_decode_interval.setSingleStep(5); self.setting_decode_interval.setSuffix(" s")
        capture_form.addRow("Intervalo de leitura", self.setting_decode_interval)
        self.setting_language = QtWidgets.QComboBox(); self.setting_language.addItem("Português", "pt"); self.setting_language.addItem("English", "en")
        capture_form.addRow("Idioma dos nomes", self.setting_language)
        grid.addWidget(capture, 1, 0)

        profile = QtWidgets.QFrame(objectName="panel")
        profile_form = QtWidgets.QFormLayout(profile)
        profile_form.addRow(_label("Integração com o Profile", "subtitle"))
        self.setting_profile = QtWidgets.QLineEdit(); profile_form.addRow("Nome do Profile", self.setting_profile)
        self.setting_site_token = QtWidgets.QLineEdit(); self.setting_site_token.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password); self.setting_site_token.setPlaceholderText("Token gerado no site"); profile_form.addRow("Token", self.setting_site_token)
        profile_actions = QtWidgets.QWidget(); profile_actions_layout = QtWidgets.QHBoxLayout(profile_actions); profile_actions_layout.setContentsMargins(0,0,0,0)
        connect_token = QtWidgets.QPushButton("Validar token"); connect_token.clicked.connect(self._connect_site_profile)
        disconnect_token = QtWidgets.QPushButton("Revogar localmente"); disconnect_token.clicked.connect(self._disconnect_site_profile)
        self.export_upload_button = QtWidgets.QPushButton("Exportar e enviar agora"); self.export_upload_button.clicked.connect(self._export_and_upload)
        profile_actions_layout.addWidget(connect_token); profile_actions_layout.addWidget(disconnect_token); profile_actions_layout.addWidget(self.export_upload_button)
        profile_form.addRow(profile_actions)
        self.site_profile_status = _label("Verificando token salvo…", "muted"); self.site_profile_status.setWordWrap(True); profile_form.addRow(self.site_profile_status)
        grid.addWidget(profile, 1, 1)

        shortcuts = QtWidgets.QFrame(objectName="panel")
        shortcuts_form = QtWidgets.QFormLayout(shortcuts)
        shortcuts_form.addRow(_label("Atalhos", "subtitle"))
        self.setting_shortcuts: dict[str, QtWidgets.QComboBox] = {}
        for mode, title, default in (("character", "Personagem", "F1"), ("market", "Mercado", "F2"), ("codex", "Codex", "F3"), ("memory_chips", "Memory Chips", "F4")):
            combo = QtWidgets.QComboBox(); combo.addItems(tuple(f"F{number}" for number in range(1, 13))); combo.setCurrentText(default)
            shortcuts_form.addRow(title, combo); self.setting_shortcuts[mode] = combo
        shortcuts_form.addRow(_label("Monitores", "subtitle"))
        for mode, title in (
            ("monitor_pve", "Monitor PvE"),
            ("monitor_pvp", "Monitor PvP"),
            ("monitor_boss", "Boss"),
        ):
            combo = QtWidgets.QComboBox()
            combo.addItems(MONITOR_SHORTCUT_OPTIONS)
            combo.setCurrentText(DEFAULT_GLOBAL_SHORTCUTS[mode])
            shortcuts_form.addRow(title, combo)
            self.setting_shortcuts[mode] = combo
        grid.addWidget(shortcuts, 2, 0)

        behavior = QtWidgets.QFrame(objectName="panel")
        behavior_layout = QtWidgets.QVBoxLayout(behavior)
        behavior_layout.addWidget(_label("Comportamento", "subtitle"))
        self.setting_minimize = QtWidgets.QCheckBox("Minimizar para a bandeja")
        self.setting_auto_export = QtWidgets.QCheckBox("Exportar automaticamente ao parar")
        self.setting_auto_market = QtWidgets.QCheckBox(
            "Enviar Leilão/Mercado automaticamente ao concluir a lista"
        )
        self.setting_delete_export = QtWidgets.QCheckBox("Excluir após exportar")
        self.setting_detailed_log = QtWidgets.QCheckBox("Ativar log completo (detalhado)")
        self.setting_detailed_log.setToolTip(
            "Registra ações e etapas internas. Pode aumentar o tamanho do arquivo; "
            "chaves, tokens e conteúdo bruto de pacotes continuam removidos."
        )
        behavior_layout.addWidget(self.setting_minimize); behavior_layout.addWidget(self.setting_auto_export); behavior_layout.addWidget(self.setting_auto_market); behavior_layout.addWidget(self.setting_delete_export); behavior_layout.addWidget(self.setting_detailed_log); behavior_layout.addStretch(1)
        grid.addWidget(behavior, 2, 1)

        license_panel = QtWidgets.QFrame(objectName="accentPanel")
        self.settings_license_panel = license_panel
        license_layout = QtWidgets.QVBoxLayout(license_panel)
        license_layout.addWidget(_label("Licença", "subtitle"))
        self.license_title = _label("Lendo licença local…", "subtitle")
        self.license_details = _label("A chave e o comprovante não são exibidos.", "muted")
        self.license_details.setWordWrap(True)
        license_layout.addWidget(self.license_title)
        license_layout.addWidget(self.license_details)
        self.license_key = QtWidgets.QLineEdit()
        self.license_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.license_key.setPlaceholderText("RFQ-…")
        license_layout.addWidget(self.license_key)
        self.activate_license_button = QtWidgets.QPushButton("Ativar licença")
        self.activate_license_button.clicked.connect(self._activate_license)
        license_layout.addWidget(self.activate_license_button)
        license_layout.addStretch(1)
        grid.addWidget(license_panel, 0, 0)

        support = QtWidgets.QFrame(objectName="panel")
        support_layout = QtWidgets.QVBoxLayout(support)
        support_layout.addWidget(_label("Suporte e atualização", "subtitle"))
        support_layout.addWidget(_label("Discord oficial · carvalho@tuta.com", "muted"))
        support_layout.addWidget(_label(f"Versão instalada: {VERSION}", "muted"))
        update_row = QtWidgets.QHBoxLayout()
        self.update_channel = QtWidgets.QComboBox(); self.update_channel.addItem("Estável", "stable"); self.update_channel.addItem("Beta", "beta")
        self.update_button = QtWidgets.QPushButton("Verificar atualização"); self.update_button.clicked.connect(self._check_update)
        self.rollback_button = QtWidgets.QPushButton("Abrir versão anterior"); self.rollback_button.clicked.connect(self._rollback)
        update_row.addWidget(self.update_channel); update_row.addWidget(self.update_button); update_row.addWidget(self.rollback_button)
        support_layout.addLayout(update_row)
        self.update_progress = QtWidgets.QProgressBar(); self.update_progress.setRange(0,100); self.update_progress.setValue(0)
        self.update_status = _label("Atualização não verificada.", "muted")
        support_layout.addWidget(self.update_progress); support_layout.addWidget(self.update_status)
        support_actions = QtWidgets.QGridLayout()
        for index, (text, callback) in enumerate((
            ("Abrir Discord", self._open_discord),
            ("Enviar log técnico", self._send_diagnostic),
            ("Salvar cópia do log", self._save_log_copy),
            ("Abrir pasta do log", self._open_log_folder),
        )):
            button = QtWidgets.QPushButton(text)
            button.clicked.connect(callback)
            support_actions.addWidget(button, index // 2, index % 2)
        support_layout.addLayout(support_actions)
        grid.addWidget(support, 0, 1)

        storage = QtWidgets.QFrame(objectName="panel")
        storage_layout = QtWidgets.QVBoxLayout(storage)
        storage_layout.addWidget(_label("Armazenamento", "subtitle"))
        self.setting_storage = _label("A pasta é lida das preferências atuais.", "muted"); self.setting_storage.setWordWrap(True); storage_layout.addWidget(self.setting_storage)
        export_row = QtWidgets.QHBoxLayout()
        export_button = QtWidgets.QPushButton("Exportar sessão"); export_button.clicked.connect(self._export_session)
        export_row.addWidget(export_button); export_row.addStretch(1); storage_layout.addLayout(export_row); storage_layout.addStretch(1)
        grid.addWidget(storage, 3, 0, 1, 2)

        actions = QtWidgets.QHBoxLayout(); actions.addStretch(1)
        cancel_settings = QtWidgets.QPushButton("Cancelar"); cancel_settings.clicked.connect(self._load_settings_fields)
        save_settings = QtWidgets.QPushButton("Salvar configurações"); save_settings.clicked.connect(self._save_settings)
        actions.addWidget(cancel_settings); actions.addWidget(save_settings)
        grid.addLayout(actions, 4, 0, 1, 2)
        scroll.setWidget(content)
        column.addWidget(scroll, 1)
        return page

    def _load_settings_fields(self) -> None:
        preferences = self.preferences
        column_settings = preferences.get("subsession_columns")
        self._apply_subsession_columns(
            dict(column_settings) if isinstance(column_settings, dict) else {}
        )
        self.setting_capture_directory.setText(str(
            preferences.get("capture_directory") or CAPTURE_DIR
        ))
        self.setting_decode_interval.setValue(self._bounded(preferences.get("decode_interval_seconds"), 15, 300, 30))
        language = "en" if preferences.get("item_name_language") == "en" else "pt"
        self.setting_language.setCurrentIndex(self.setting_language.findData(language))
        self.setting_profile.setText(
            self.site_profile.profile or str(preferences.get("profile") or "")
        )
        self.site_profile_status.setText(
            f"Conectado ao Profile {self.site_profile.profile}"
            if self.site_profile.connected
            else "Token do Profile ainda não validado."
        )
        shortcuts = dict(preferences.get("shortcuts") or {})
        for mode, combo in self.setting_shortcuts.items():
            combo.setCurrentText(str(shortcuts.get(mode) or DEFAULT_GLOBAL_SHORTCUTS[mode]))
        self._apply_monitor_shortcut_labels(shortcuts)
        self.setting_minimize.setChecked(bool(preferences.get("minimize_to_tray", False)))
        self.setting_auto_export.setChecked(bool(preferences.get("auto_export", False)))
        self.setting_auto_market.setChecked(bool(preferences.get("auto_market_upload", True)))
        self.setting_delete_export.setChecked(bool(preferences.get("delete_after_export", False)))
        self.setting_detailed_log.setChecked(bool(preferences.get("detailed_logging", False)))
        monitor_intervals = dict(preferences.get("monitor_intervals") or {})
        for mode, controls in self.monitor_controls.items():
            default = 2 if mode in {"pvp", "boss"} else 3
            controls["interval"].setValue(
                self._bounded(monitor_intervals.get(mode), 1, 60, default)
            )
        alerts = dict(preferences.get("alerts") or {})
        self.alert_character_enabled.setChecked(bool(alerts.get("characters_enabled")))
        self.alert_character_names.setText(str(alerts.get("characters") or ""))
        self.alert_guild_enabled.setChecked(bool(alerts.get("guilds_enabled")))
        self.alert_guild_names.setText(str(alerts.get("guilds") or ""))
        self.alert_pvp_hit.setChecked(bool(alerts.get("pvp_hit")))
        self.alert_boss.setChecked(bool(alerts.get("boss_detected")))
        self.alert_low_hp.setChecked(bool(alerts.get("low_hp")))
        self.alert_low_hp_percent.setValue(
            self._bounded(alerts.get("low_hp_percent"), 1, 99, 30)
        )
        self.alert_sound.setChecked(bool(alerts.get("sound", True)))
        self.subsession_duration.setValue(self._bounded(preferences.get("subsession_duration_minutes"), 0, 1440, 30))
        self.auto_subsession.setChecked(bool(preferences.get("auto_subsession", False)))
        self.auto_subsession_minutes.setValue(self._bounded(preferences.get("auto_subsession_minutes"), 5, 240, 30))
        self._refresh_subsession_favorites()
        channel = str(preferences.get("channel") or "stable")
        index = self.update_channel.findData(channel)
        self.update_channel.setCurrentIndex(max(0, index))
        self.setting_storage.setText(f"Capturas: {self.setting_capture_directory.text()}\nRetenção: até exclusão manual após exportação validada.")

    def _save_settings(self) -> None:
        capture_directory = Path(self.setting_capture_directory.text().strip())
        shortcuts = {mode: combo.currentText() for mode, combo in self.setting_shortcuts.items()}
        if not capture_directory.is_absolute():
            QtWidgets.QMessageBox.warning(self, "Configurações", "Escolha uma pasta absoluta para as capturas.")
            return
        if len(set(shortcuts.values())) != len(shortcuts):
            QtWidgets.QMessageBox.warning(self, "Configurações", "Cada ação precisa usar uma tecla de atalho diferente.")
            return
        self.preferences = save_preferences({
            "capture_directory": str(capture_directory),
            "decode_interval_seconds": self.setting_decode_interval.value(),
            "item_name_language": self.setting_language.currentData(),
            "profile": self.setting_profile.text().strip(),
            "shortcuts": shortcuts,
            "minimize_to_tray": self.setting_minimize.isChecked(),
            "auto_export": self.setting_auto_export.isChecked(),
            "auto_market_upload": self.setting_auto_market.isChecked(),
            "delete_after_export": self.setting_delete_export.isChecked(),
            "detailed_logging": self.setting_detailed_log.isChecked(),
            "channel": self.update_channel.currentData(),
            "monitor_intervals": {
                mode: controls["interval"].value()
                for mode, controls in self.monitor_controls.items()
            },
            "alerts": self._alert_preferences(),
        }, self.preferences_path)
        set_detailed(self.log, self.setting_detailed_log.isChecked())
        self.log.debug(
            "settings_saved decode_interval=%s language=%s minimize=%s auto_export=%s "
            "delete_after_export=%s",
            self.setting_decode_interval.value(),
            self.setting_language.currentData(),
            self.setting_minimize.isChecked(),
            self.setting_auto_export.isChecked(),
            self.setting_delete_export.isChecked(),
        )
        if not self.capture_engine or not self.capture_engine.current_session:
            self.capture_engine = None
            self._ensure_capture_engine()
        self._refresh_farm_catalog()
        self._render_overview()
        self._apply_monitor_shortcut_labels(shortcuts)
        self._sync_global_hotkeys(shortcuts)
        self.setting_storage.setText(f"Capturas: {capture_directory}\nPreferências salvas para a interface estável e para o preview.")
        if self.site_profile.connected:
            alert_payload = self._site_alert_preferences()
            self._run_site_operation(
                "alerts:save",
                lambda: self.site_profile.save_monitor_alerts(alert_payload),
            )
        QtWidgets.QMessageBox.information(self, "Configurações", "Configurações salvas.")

    def _alert_preferences(self) -> dict[str, object]:
        return {
            "characters_enabled": self.alert_character_enabled.isChecked(),
            "characters": self.alert_character_names.text().strip(),
            "guilds_enabled": self.alert_guild_enabled.isChecked(),
            "guilds": self.alert_guild_names.text().strip(),
            "pvp_hit": self.alert_pvp_hit.isChecked(),
            "boss_detected": self.alert_boss.isChecked(),
            "low_hp": self.alert_low_hp.isChecked(),
            "low_hp_percent": self.alert_low_hp_percent.value(),
            "sound": self.alert_sound.isChecked(),
        }

    def _site_alert_preferences(self) -> dict[str, object]:
        local = self._alert_preferences()
        return {
            "characters_enabled": local["characters_enabled"],
            "characters": [
                value.strip()
                for value in str(local["characters"]).split(",")
                if value.strip()
            ],
            "guilds_enabled": local["guilds_enabled"],
            "guilds": [
                value.strip()
                for value in str(local["guilds"]).split(",")
                if value.strip()
            ],
            "pvp_hit": local["pvp_hit"],
            "boss_detected": local["boss_detected"],
            "low_hp": local["low_hp"],
            "low_hp_percent": local["low_hp_percent"],
            "sound": local["sound"],
        }

    def _save_alert_settings(self) -> None:
        self.preferences = save_preferences(
            {"alerts": self._alert_preferences()}, self.preferences_path
        )
        self.alert_status.setText("Configurações de alerta salvas.")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        engine = self.capture_engine
        if (
            not self.exit_requested
            and bool(self.preferences.get("minimize_to_tray"))
            and engine and engine.active and self._tray
        ):
            self.hide()
            event.ignore()
            return
        self.global_hotkeys.stop()
        if self.monitor_engine:
            try:
                self.monitor_engine.stop()
            except Exception:
                self.log.exception("monitor_stop_on_close_failed")
        if engine and engine.current_session and not self.capture_busy:
            try:
                engine.stop()
            except Exception:
                self.log.exception("capture_stop_on_close_failed")
        if self._tray and hasattr(self._tray, "hide"):
            self._tray.hide()
            if hasattr(self._tray, "setContextMenu"):
                self._tray.setContextMenu(None)
        self.log.info("app_closed")
        super().closeEvent(event)

    @QtCore.Slot(str)
    def _global_hotkey_action(self, action: str) -> None:
        self.log.debug("global_hotkey_triggered action=%s", action)
        if action == "start":
            self._start_capture()
        elif action == "stop":
            self._stop_capture()
        elif action in {"character", "market", "codex", "memory_chips"}:
            self._send_mode(action, -1 if action == "market" else self.active_client)
        elif action.startswith("monitor_"):
            mode = action.removeprefix("monitor_")
            controls = self.monitor_controls.get(mode)
            if controls:
                controls["enabled"].toggle()
        elif action.startswith("overlay_"):
            mode = action.removeprefix("overlay_")
            controls = self.monitor_controls.get(mode)
            if controls and controls.get("overlay"):
                controls["overlay"].toggle()

    def _sync_global_hotkeys(self, shortcuts: dict[str, str] | None = None) -> None:
        shortcuts = shortcuts or {
            mode: combo.currentText()
            for mode, combo in self.setting_shortcuts.items()
        }
        if getattr(self.global_hotkeys, "shortcuts", None) == shortcuts:
            return
        self.global_hotkeys.stop()
        self.global_hotkeys.start(shortcuts)

    def _apply_monitor_shortcut_labels(
        self, shortcuts: dict[str, str] | None = None
    ) -> None:
        shortcuts = shortcuts or {}
        for mode, controls in self.monitor_controls.items():
            shortcut = str(
                shortcuts.get(f"monitor_{mode}")
                or DEFAULT_GLOBAL_SHORTCUTS[f"monitor_{mode}"]
            )
            controls["shortcut"] = shortcut
            self._update_monitor_button(mode)

    def _rename_client(self, index: int) -> None:
        current = str(self.preferences.get(f"character{index + 1}") or "")
        name, accepted = QtWidgets.QInputDialog.getText(
            self,
            f"Cliente {chr(65 + index)}",
            "Nome manual (somente para visualização):",
            text=current,
        )
        if not accepted:
            return
        self.preferences = save_preferences(
            {f"character{index + 1}": name.strip()}, self.preferences_path
        )
        self._render_overview()

    def _disconnect_site_profile(self) -> None:
        self.site_profile.disconnect()
        self.setting_site_token.clear()
        self.site_profile_status.setText("Token removido deste computador")
        self._set_send_controls()

    def _choose_capture_directory(self) -> None:
        selected = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Escolha a pasta das capturas", self.setting_capture_directory.text()
        )
        if selected:
            self.setting_capture_directory.setText(selected)

    @staticmethod
    def _bounded(value: object, minimum: int, maximum: int, default: int) -> int:
        try:
            return max(minimum, min(maximum, int(value)))
        except (TypeError, ValueError):
            return default

    def _refresh_farm_catalog(self) -> None:
        current_map = self.subsession_map.currentText()
        self.farm_catalog = load_farm_catalog(
            "en" if self.preferences.get("item_name_language") == "en" else "pt"
        )
        self.subsession_map.blockSignals(True)
        self.subsession_map.clear()
        self.subsession_map.addItems(tuple(self.farm_catalog))
        preferred = str(self.preferences.get("subsession_map") or current_map)
        if preferred in self.farm_catalog:
            self.subsession_map.setCurrentText(preferred)
        self.subsession_map.blockSignals(False)
        self._subsession_map_changed(self.subsession_map.currentText())

    def _subsession_map_changed(self, map_name: str) -> None:
        current = self.subsession_spot.currentText()
        self.subsession_spot.blockSignals(True)
        self.subsession_spot.clear()
        self.subsession_spot.addItems(tuple(self.farm_catalog.get(map_name, {})))
        preferred = str(self.preferences.get("subsession_spot") or current)
        if preferred in self.farm_catalog.get(map_name, {}):
            self.subsession_spot.setCurrentText(preferred)
        self.subsession_spot.blockSignals(False)
        self._subsession_spot_changed(self.subsession_spot.currentText())

    def _subsession_spot_changed(self, spot_name: str) -> None:
        self._populate_subsession_mobs(spot_name)

    def _refilter_subsession_mobs(self, _value: int = 0) -> None:
        self._populate_subsession_mobs(
            self.subsession_spot.currentText(), set(self._selected_mobs())
        )

    def _populate_subsession_mobs(
        self, spot_name: str, selected: set[str] | None = None
    ) -> None:
        selected = selected or set()
        mobs = self.farm_catalog.get(self.subsession_map.currentText(), {}).get(spot_name, {})
        self.subsession_mobs.clear()
        for mob, levels in mobs.items():
            minimum = self.subsession_filter_level_from.value()
            maximum = self.subsession_filter_level_to.value()
            matches = any(
                (not minimum or level >= minimum)
                and (not maximum or level <= maximum)
                for level in levels
            )
            if not matches and mob not in selected:
                continue
            level_text = (
                str(levels[0]) if len(levels) == 1
                else f"{levels[0]}–{levels[-1]}"
            )
            item = QtWidgets.QListWidgetItem(f"{mob} · Nv. {level_text}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, mob)
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                QtCore.Qt.CheckState.Checked
                if mob in selected
                else QtCore.Qt.CheckState.Unchecked
            )
            self.subsession_mobs.addItem(item)
        self.subsession_select_all.blockSignals(True)
        self.subsession_select_all.setChecked(False)
        self.subsession_select_all.blockSignals(False)

    def _toggle_all_mobs(self, checked: bool) -> None:
        state = QtCore.Qt.CheckState.Checked if checked else QtCore.Qt.CheckState.Unchecked
        for row in range(self.subsession_mobs.count()):
            self.subsession_mobs.item(row).setCheckState(state)

    def _selected_mobs(self) -> list[str]:
        return [
            str(
                self.subsession_mobs.item(row).data(
                    QtCore.Qt.ItemDataRole.UserRole
                )
                or self.subsession_mobs.item(row).text()
            )
            for row in range(self.subsession_mobs.count())
            if self.subsession_mobs.item(row).checkState() == QtCore.Qt.CheckState.Checked
        ]

    def _subsession_favorites(self) -> dict[str, dict[str, object]]:
        value = self.preferences.get("subsession_favorites")
        if not isinstance(value, dict):
            return {}
        return {
            str(name): dict(options)
            for name, options in value.items()
            if isinstance(options, dict)
        }

    def _refresh_subsession_favorites(self, selected: str = "") -> None:
        selected = selected or str(self.subsession_favorite.currentData() or "")
        self.subsession_favorite.blockSignals(True)
        self.subsession_favorite.clear()
        self.subsession_favorite.addItem("Selecione um favorito", "")
        for name in sorted(self._subsession_favorites(), key=str.casefold):
            self.subsession_favorite.addItem(name, name)
        index = self.subsession_favorite.findData(selected)
        self.subsession_favorite.setCurrentIndex(max(0, index))
        self.subsession_favorite.blockSignals(False)

    def _subsession_favorite_values(self) -> dict[str, object]:
        return {
            "client": self.subsession_client.currentIndex(),
            "map": self.subsession_map.currentText(),
            "spot": self.subsession_spot.currentText(),
            "mobs": self._selected_mobs(),
            "other_mob": self.subsession_other_mob.text(),
            "filter_level_from": self.subsession_filter_level_from.value(),
            "filter_level_to": self.subsession_filter_level_to.value(),
            "level_from": self.subsession_level_from.value(),
            "level_to": self.subsession_level_to.value(),
            "duration": self.subsession_duration.value(),
            "name": self.subsession_name.text(),
            "automatic": self.auto_subsession.isChecked(),
            "automatic_minutes": self.auto_subsession_minutes.value(),
        }

    def _save_subsession_favorite(self) -> None:
        default = self.subsession_name.text().strip() or " · ".join(
            value
            for value in (
                self.subsession_map.currentText(),
                self.subsession_spot.currentText(),
            )
            if value
        )
        name, accepted = QtWidgets.QInputDialog.getText(
            self, "Salvar favorito", "Nome do favorito:", text=default
        )
        name = name.strip()
        if not accepted or not name:
            return
        favorites = self._subsession_favorites()
        if name in favorites and QtWidgets.QMessageBox.question(
            self,
            "Salvar favorito",
            f"Substituir o favorito {name}?",
        ) != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        favorites[name] = self._subsession_favorite_values()
        self.preferences = save_preferences(
            {"subsession_favorites": favorites}, self.preferences_path
        )
        self._refresh_subsession_favorites(name)

    def _load_subsession_favorite(self) -> None:
        name = str(self.subsession_favorite.currentData() or "")
        values = self._subsession_favorites().get(name)
        if not values:
            return
        for control, key in (
            (self.subsession_filter_level_from, "filter_level_from"),
            (self.subsession_filter_level_to, "filter_level_to"),
        ):
            control.blockSignals(True)
            control.setValue(self._bounded(values.get(key), 0, 999, 0))
            control.blockSignals(False)
        self.subsession_client.setCurrentIndex(
            self._bounded(values.get("client"), 0, 1, 0)
        )
        self.subsession_map.setCurrentText(str(values.get("map") or ""))
        self.subsession_spot.setCurrentText(str(values.get("spot") or ""))
        chosen = {str(value) for value in values.get("mobs", [])}
        self._populate_subsession_mobs(self.subsession_spot.currentText(), chosen)
        self.subsession_other_mob.setText(str(values.get("other_mob") or ""))
        self.subsession_level_from.setValue(
            self._bounded(values.get("level_from"), 0, 999, 0)
        )
        self.subsession_level_to.setValue(
            self._bounded(values.get("level_to"), 0, 999, 0)
        )
        self.subsession_duration.setValue(
            self._bounded(values.get("duration"), 0, 1440, 0)
        )
        self.subsession_name.setText(str(values.get("name") or ""))
        self.auto_subsession.setChecked(bool(values.get("automatic")))
        self.auto_subsession_minutes.setValue(
            self._bounded(values.get("automatic_minutes"), 5, 240, 30)
        )

    def _delete_subsession_favorite(self) -> None:
        name = str(self.subsession_favorite.currentData() or "")
        if not name or QtWidgets.QMessageBox.question(
            self, "Excluir favorito", f"Excluir o favorito {name}?"
        ) != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        favorites = self._subsession_favorites()
        favorites.pop(name, None)
        self.preferences = save_preferences(
            {"subsession_favorites": favorites}, self.preferences_path
        )
        self._refresh_subsession_favorites()

    def _client_uid_for(self, index: int) -> str | None:
        key = f"client:{chr(97 + index)}"
        profiles = list(self.snapshot.get("profiles") or [])
        profile = next((item for item in profiles if item.get("client_key") == key), None)
        if profile is None and not any(item.get("client_key") for item in profiles):
            profile = profiles[index] if index < len(profiles) else None
        return str(profile.get("uid")) if profile and profile.get("uid") else None

    def _overview_character(
        self, index: int
    ) -> tuple[dict[str, Any] | None, dict[str, Any], bool]:
        """Retorna o personagem atual com fallback seguro do histórico."""
        key = f"client:{chr(97 + index)}"
        characters = list(self.snapshot.get("characters") or [])
        routed = any(item.get("client_key") for item in characters)
        character = next(
            (item for item in characters if item.get("client_key") == key), None
        )
        if character is None and not routed and index < len(characters):
            character = characters[index]
        summary = dict(character.get("summary") or {}) if character else {}

        binding = next(
            (
                item
                for item in self.snapshot.get("client_bindings") or []
                if item.get("client_key") == key
            ),
            None,
        )
        selected_uid = self._uid_selections().get(key)
        historical = next(
            (
                item
                for item in self.snapshot.get("character_history") or []
                if str(item.get("uid") or "") == str(selected_uid or "")
            ),
            None,
        )
        use_history = bool(
            historical
            and (
                character is None
                or not binding
                or binding.get("source") == "manual"
            )
        )
        if not use_history:
            return character, summary, False

        if character is None:
            character = {
                "uid": str(historical.get("uid") or ""),
                "name": str(historical.get("name") or ""),
                "client_key": key,
            }
        used = False
        biosuit_index = historical.get("biosuit_item_index")
        if not summary.get("biosuit_item_index") and isinstance(biosuit_index, int):
            biosuit = BIOSUITS.get(str(biosuit_index), {})
            summary.update(
                biosuit_item_index=biosuit_index,
                biosuit_name=str(biosuit.get("name") or ""),
                biosuit_type=biosuit.get("biosuit_type"),
                biosuit_grade=biosuit.get("grade"),
                character_class=str(biosuit.get("class_name") or ""),
            )
            used = True
        rover_index = historical.get("rover_item_index")
        if not summary.get("rover_item_index") and isinstance(rover_index, int):
            rover = ROVERS.get(str(rover_index), {})
            summary.update(
                rover_item_index=rover_index,
                rover_name=str(rover.get("name") or ""),
                rover_grade=rover.get("grade"),
            )
            used = True
        return character, summary, used

    def _uid_selections(self) -> dict[str, str]:
        value = self.preferences.get("client_uid_selections")
        return {
            str(key): str(uid)
            for key, uid in (value.items() if isinstance(value, dict) else ())
            if key in {"client:a", "client:b"} and uid
        }

    def _refresh_client_uid_buttons(self) -> None:
        history = {
            str(item.get("uid")): str(item.get("name") or "")
            for item in self.snapshot.get("character_history") or []
            if item.get("uid")
        }
        selections = self._uid_selections()
        for index, button in enumerate(self.client_uid_buttons):
            uid = selections.get(f"client:{chr(97 + index)}")
            button.setText(
                f"UID: {history.get(uid) or uid}" if uid else "UID: Auto"
            )
            button.setToolTip(
                f"Vínculo do Cliente {chr(65 + index)}: "
                + (f"{history.get(uid) or 'personagem conhecido'} · UID {uid}" if uid else "detecção automática")
            )

    def _choose_client_uid(self, index: int) -> None:
        history = list(self.snapshot.get("character_history") or [])
        choices = [("Automático · detectar pelo jogo", None)]
        choices.extend(
            (
                " · ".join(
                    value for value in (
                        str(item.get("name") or "Sem nome"),
                        f"UID {item['uid']}",
                        str(item.get("last_seen_at") or "").replace("T", " ")[:16],
                    ) if value
                ),
                str(item["uid"]),
            )
            for item in history if item.get("uid")
        )
        labels = [label for label, _uid in choices]
        current_uid = self._uid_selections().get(f"client:{chr(97 + index)}")
        current = next(
            (position for position, (_label, uid) in enumerate(choices) if uid == current_uid),
            0,
        )
        selected, accepted = QtWidgets.QInputDialog.getItem(
            self,
            f"UID do Cliente {chr(65 + index)}",
            "Escolha um personagem confirmado anteriormente:",
            labels,
            current,
            False,
        )
        if not accepted:
            return
        uid = choices[labels.index(selected)][1]
        try:
            self._set_client_uid_selection(index, uid)
        except ValueError as error:
            QtWidgets.QMessageBox.warning(self, "Vínculo de UID", str(error))

    def _set_client_uid_selection(self, index: int, uid: str | None) -> None:
        key = f"client:{chr(97 + index)}"
        other = "client:b" if key == "client:a" else "client:a"
        selections = self._uid_selections()
        if uid and selections.get(other) == uid:
            raise ValueError("O UID já está selecionado no outro cliente")
        session_id = str(
            (self.capture_engine.current_session if self.capture_engine else None)
            or self.snapshot.get("session_id")
            or ""
        )
        if session_id:
            store = CaptureStore(self.database_path)
            try:
                store.select_client_uid(session_id, key, uid)
            finally:
                store.close()
        if uid:
            selections[key] = uid
        else:
            selections.pop(key, None)
        self.preferences = save_preferences(
            {"client_uid_selections": selections}, self.preferences_path
        )
        self._refresh_client_uid_buttons()
        if session_id:
            self._load_readonly_data()

    def _apply_uid_selections(self, session_id: str) -> None:
        store = CaptureStore(self.database_path)
        try:
            for key, uid in self._uid_selections().items():
                try:
                    store.select_client_uid(session_id, key, uid)
                except ValueError as error:
                    self.log.warning(
                        "uid_history_binding_rejected client=%s error=%s", key, error
                    )
        finally:
            store.close()

    def _reconcile_uid_selections(self) -> None:
        selections = self._uid_selections()
        corrected = []
        for binding in self.snapshot.get("client_bindings") or []:
            key = str(binding.get("client_key") or "")
            confirmed = str(binding.get("uid") or "")
            selected = selections.get(key)
            if binding.get("source") == "canonical" and selected and selected != confirmed:
                selections.pop(key, None)
                corrected.append(key)
        if corrected:
            self.preferences = save_preferences(
                {"client_uid_selections": selections}, self.preferences_path
            )
            self.top_last_read.setText(
                "Vínculo histórico ajustado pela identificação confirmada do jogo"
            )
            self.log.warning("uid_history_selection_reconciled clients=%s", corrected)

    def _save_subsession(self) -> None:
        session_id = str(self.snapshot.get("session_id") or "")
        if not session_id:
            QtWidgets.QMessageBox.warning(self, "Subsessão", "Nenhuma sessão está disponível.")
            return
        map_name, spot_name = self.subsession_map.currentText(), self.subsession_spot.currentText()
        mobs = self._selected_mobs()
        extra = self.subsession_other_mob.text().strip()
        if extra:
            mobs.extend(value.strip() for value in extra.split(",") if value.strip())
        if not map_name or not spot_name or not mobs:
            QtWidgets.QMessageBox.warning(self, "Subsessão", "Escolha mapa, spot e ao menos um mob.")
            return
        first, last = self.subsession_level_from.value(), self.subsession_level_to.value()
        if first and last and first > last:
            QtWidgets.QMessageBox.warning(self, "Subsessão", "O nível inicial não pode ser maior que o final.")
            return
        catalog_mobs = self.farm_catalog.get(map_name, {}).get(spot_name, {})
        levels: dict[str, int | str] = {}
        for mob in mobs:
            known = catalog_mobs.get(mob, ())
            if known:
                levels[mob] = known[0] if len(known) == 1 else f"{known[0]}-{known[-1]}"
            elif first and last:
                levels[mob] = first if first == last else f"{first}-{last}"
        index = self.subsession_client.currentIndex()
        values = dict(
            name=self.subsession_name.text().strip() or spot_name,
            character_uid=self._client_uid_for(index),
            client_key=f"client:{chr(97 + index)}",
            location=" > ".join(value for value in (map_name, spot_name) if value),
            map_name=map_name,
            spot_name=spot_name,
            mobs=list(dict.fromkeys(mobs)),
            mob_levels=levels,
            duration_minutes=self.subsession_duration.value(),
        )
        store = CaptureStore(self.database_path)
        try:
            if self.editing_subsession_id:
                store.update_subsession(self.editing_subsession_id, **values)
            else:
                store.start_subsession(
                    f"{session_id}-sub-{time.time_ns()}", session_id,
                    started_ns=time.time_ns(), **values,
                )
        except ValueError as error:
            QtWidgets.QMessageBox.warning(self, "Subsessão", str(error))
            return
        finally:
            store.close()
        self.preferences = save_preferences({
            "subsession_duration_minutes": self.subsession_duration.value(),
            "subsession_map": map_name,
            "subsession_spot": spot_name,
            "auto_subsession": self.auto_subsession.isChecked(),
            "auto_subsession_minutes": self.auto_subsession_minutes.value(),
        }, self.preferences_path)
        self._cancel_subsession_form()
        self._reload_snapshot()

    def _cancel_subsession_form(self) -> None:
        self.editing_subsession_id = None
        self.subsession_save.setText("Criar subsessão")
        self.subsession_name.clear()
        self.subsession_other_mob.clear()
        self.subsession_mode_group.button(0).setChecked(True)
        self.subsession_stack.setCurrentIndex(0)

    def _selected_subsession_ids(self) -> list[str]:
        selected = []
        for row in range(self.subsession_table.rowCount()):
            item = self.subsession_table.item(row, 0)
            if item and item.checkState() == QtCore.Qt.CheckState.Checked:
                selected.append(str(item.data(QtCore.Qt.ItemDataRole.UserRole)))
        self.selected_subsessions.update(selected)
        return selected

    def _toggle_visible_subsessions(self) -> None:
        visible = [self.subsession_table.item(row, 0) for row in range(self.subsession_table.rowCount())]
        checked = visible and all(item.checkState() == QtCore.Qt.CheckState.Checked for item in visible if item)
        for item in visible:
            if item:
                item.setCheckState(QtCore.Qt.CheckState.Unchecked if checked else QtCore.Qt.CheckState.Checked)
        self._subsession_selection_changed()

    def _one_selected_subsession(self, action: str) -> dict[str, object] | None:
        selected = self._selected_subsession_ids()
        if len(selected) != 1:
            QtWidgets.QMessageBox.information(self, "Subsessão", f"Selecione uma única subsessão para {action}.")
            return None
        return next((item for item in self.snapshot.get("subsessions", []) if item.get("id") == selected[0]), None)

    def _edit_subsession(self) -> None:
        item = self._one_selected_subsession("editar")
        if not item:
            return
        self.editing_subsession_id = str(item["id"])
        self.subsession_client.setCurrentIndex(1 if item.get("client_key") == "client:b" else 0)
        self.subsession_map.setCurrentText(str(item.get("map_name") or ""))
        self.subsession_spot.setCurrentText(str(item.get("spot_name") or ""))
        chosen = set(item.get("mobs") or [])
        self._populate_subsession_mobs(self.subsession_spot.currentText(), chosen)
        extras = chosen - {
            str(
                self.subsession_mobs.item(row).data(
                    QtCore.Qt.ItemDataRole.UserRole
                )
                or self.subsession_mobs.item(row).text()
            )
            for row in range(self.subsession_mobs.count())
        }
        self.subsession_other_mob.setText(", ".join(sorted(extras)))
        self.subsession_name.setText(str(item.get("name") or ""))
        self.subsession_duration.setValue(int(item.get("duration_minutes") or 0))
        self.subsession_save.setText("Salvar alterações")
        self.subsession_mode_group.button(1).setChecked(True)
        self.subsession_stack.setCurrentIndex(1)

    def _rename_subsession(self) -> None:
        item = self._one_selected_subsession("renomear")
        if not item:
            return
        name, accepted = QtWidgets.QInputDialog.getText(self, "Renomear subsessão", "Nome:", text=str(item.get("name") or ""))
        if not accepted:
            return
        store = CaptureStore(self.database_path)
        try:
            store.rename_subsession(str(item["id"]), name)
        except ValueError as error:
            QtWidgets.QMessageBox.warning(self, "Subsessão", str(error))
        finally:
            store.close()
        self._reload_snapshot()

    def _end_subsession(self) -> None:
        item = self._one_selected_subsession("encerrar")
        if not item:
            return
        if item.get("ended_ns") is not None:
            QtWidgets.QMessageBox.information(self, "Subsessão", "A subsessão já está encerrada.")
            return
        store = CaptureStore(self.database_path)
        try:
            store.end_subsession(str(item["id"]), time.time_ns())
        finally:
            store.close()
        self._reload_snapshot()

    def _rotate_auto_subsessions(self) -> None:
        engine = self.capture_engine
        session_id = str(engine.current_session if engine else "")
        if not session_id:
            return
        now = time.time_ns()
        automatic = self.auto_subsession.isChecked()
        automatic_minutes = self.auto_subsession_minutes.value() if automatic else 0
        store = CaptureStore(self.database_path)
        changed = False
        try:
            for active in store.subsessions(session_id):
                if active.get("ended_ns") is not None:
                    continue
                duration = int(active.get("duration_minutes") or 0)
                if duration == 0:
                    continue
                limit = min(duration, automatic_minutes or duration)
                boundary_ns = (
                    int(active["started_ns"])
                    + limit * 60 * 1_000_000_000
                )
                if now < boundary_ns:
                    continue
                while now >= boundary_ns:
                    store.end_subsession(str(active["id"]), boundary_ns)
                    self.log.info(
                        "subsession_auto_ended id=%s boundary_ns=%s delay_ms=%s",
                        active["id"],
                        boundary_ns,
                        max(0, (now - boundary_ns) // 1_000_000),
                    )
                    changed = True
                    if not automatic:
                        break
                    owner = str(
                        active.get("client_key")
                        or active.get("character_uid")
                        or "geral"
                    ).replace(":", "-")
                    next_id = f"{session_id}-sub-{boundary_ns}-{owner}"
                    store.start_subsession(
                        next_id,
                        session_id,
                        str(active.get("name") or active.get("spot_name") or "Subsessão"),
                        character_uid=active.get("character_uid"),
                        client_key=str(active.get("client_key") or ""),
                        location=str(active.get("location") or ""),
                        map_name=str(active.get("map_name") or ""),
                        spot_name=str(active.get("spot_name") or ""),
                        mobs=list(active.get("mobs") or []),
                        mob_levels=dict(active.get("mob_levels") or {}),
                        duration_minutes=automatic_minutes,
                        started_ns=boundary_ns,
                    )
                    active = {
                        **active,
                        "id": next_id,
                        "duration_minutes": automatic_minutes,
                        "started_ns": boundary_ns,
                        "ended_ns": None,
                    }
                    boundary_ns += automatic_minutes * 60 * 1_000_000_000
        finally:
            store.close()
        if changed:
            self._load_readonly_data()

    def _delete_subsessions(self) -> None:
        selected = self._selected_subsession_ids()
        if not selected:
            QtWidgets.QMessageBox.information(self, "Subsessão", "Selecione ao menos uma subsessão para excluir.")
            return
        if QtWidgets.QMessageBox.question(
            self, "Excluir subsessões",
            f"Excluir {len(selected)} subsessão(ões) localmente? Os eventos capturados não serão apagados.",
        ) != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        store = CaptureStore(self.database_path)
        try:
            store.delete_subsessions(selected)
        finally:
            store.close()
        self.selected_subsessions.difference_update(selected)
        self._reload_snapshot()

    def _reset_subsession_page(self, _value: object = None) -> None:
        self.subsession_page = 1
        self._render_subsessions()

    def _change_subsession_page(self, delta: int) -> None:
        self.subsession_page = max(1, self.subsession_page + delta)
        self._render_subsessions()

    def _set_subsession_column_visible(self, key: str, visible: bool) -> None:
        column = SUBSESSION_COLUMN_INDEX[key]
        self.subsession_table.setColumnHidden(column, not visible)
        if not self._restoring_subsession_columns:
            self.subsession_columns_timer.start()

    def _subsession_columns_changed(self, *_args: object) -> None:
        if self._restoring_subsession_columns:
            return
        header = self.subsession_table.horizontalHeader()
        selection_position = header.visualIndex(SUBSESSION_COLUMN_INDEX["select"])
        if selection_position != 0:
            self._restoring_subsession_columns = True
            header.moveSection(selection_position, 0)
            self._restoring_subsession_columns = False
        self.subsession_columns_timer.start()

    def _save_subsession_columns(self) -> None:
        header = self.subsession_table.horizontalHeader()
        order = [
            SUBSESSION_COLUMNS[header.logicalIndex(visual)][0]
            for visual in range(header.count())
        ]
        visible = [
            key
            for key, _label, _width, _default in SUBSESSION_COLUMNS[1:]
            if not self.subsession_table.isColumnHidden(
                SUBSESSION_COLUMN_INDEX[key]
            )
        ]
        widths = {
            key: self.subsession_table.columnWidth(index)
            for index, (key, _label, _width, _default) in enumerate(
                SUBSESSION_COLUMNS
            )
        }
        self.preferences = save_preferences(
            {
                "subsession_columns": {
                    "order": order,
                    "visible": visible,
                    "widths": widths,
                }
            },
            self.preferences_path,
        )

    def _apply_subsession_columns(self, settings: dict[str, object]) -> None:
        if not hasattr(self, "subsession_table"):
            return
        known = set(SUBSESSION_COLUMN_INDEX)
        configured_order = settings.get("order")
        requested = [
            str(key) for key in (
                configured_order if isinstance(configured_order, list) else []
            )
            if str(key) in known and str(key) != "select"
        ]
        order = ["select", *dict.fromkeys(requested)]
        order.extend(key for key in SUBSESSION_COLUMN_INDEX if key not in order)
        configured_visible = settings.get("visible")
        visible = (
            {str(key) for key in configured_visible if str(key) in known}
            if isinstance(configured_visible, list)
            else {
                key for key, _label, _width, default in SUBSESSION_COLUMNS
                if default
            }
        )
        configured_widths = settings.get("widths")
        widths = dict(configured_widths) if isinstance(configured_widths, dict) else {}
        header = self.subsession_table.horizontalHeader()
        self._restoring_subsession_columns = True
        try:
            for visual, key in enumerate(order):
                current = header.visualIndex(SUBSESSION_COLUMN_INDEX[key])
                if current != visual:
                    header.moveSection(current, visual)
            for key, _label, default_width, _default in SUBSESSION_COLUMNS:
                column = SUBSESSION_COLUMN_INDEX[key]
                try:
                    width = max(28, min(800, int(widths.get(key, default_width))))
                except (TypeError, ValueError):
                    width = default_width
                header.resizeSection(column, width)
                if key != "select":
                    shown = key in visible
                    self.subsession_table.setColumnHidden(column, not shown)
                    action = self.subsession_column_actions[key]
                    action.blockSignals(True)
                    action.setChecked(shown)
                    action.blockSignals(False)
            self.subsession_table.setColumnHidden(
                SUBSESSION_COLUMN_INDEX["select"], False
            )
        finally:
            self._restoring_subsession_columns = False

    def _reset_subsession_columns(self) -> None:
        self._apply_subsession_columns({})
        self._save_subsession_columns()

    def _filtered_subsessions(self) -> list[dict[str, object]]:
        items = list(self.snapshot.get("subsessions") or [])
        view = self.subsession_filter.currentText()
        if view == "Cliente A": items = [item for item in items if item.get("client_key") != "client:b"]
        elif view == "Cliente B": items = [item for item in items if item.get("client_key") == "client:b"]
        elif view == "Em andamento": items = [item for item in items if item.get("ended_ns") is None]
        elif view == "Encerradas": items = [item for item in items if item.get("ended_ns") is not None]
        elif view == "Enviadas": items = [item for item in items if item.get("upload_state") == "sent"]
        elif view == "Não enviadas": items = [item for item in items if item.get("upload_state") != "sent"]
        query = self.subsession_search.text().strip().casefold()
        if query:
            items = [item for item in items if query in " ".join((str(item.get("name") or ""), str(item.get("location") or ""), " ".join(item.get("mobs") or []))).casefold()]
        return items

    def _render_subsessions(self) -> None:
        if not hasattr(self, "subsession_table"):
            return
        items = self._filtered_subsessions()
        size = int(self.subsession_page_size.currentText())
        pages = max(1, (len(items) + size - 1) // size)
        self.subsession_page = min(self.subsession_page, pages)
        visible = items[(self.subsession_page - 1) * size:self.subsession_page * size]
        summaries = dict(self.snapshot.get("subsession_summaries") or {})
        profiles = list(self.snapshot.get("profiles") or [])
        profiles_by_client = {
            item.get("client_key"): str(item.get("name") or "")
            for item in profiles if item.get("client_key")
        }
        profiles_by_uid = {
            item.get("uid"): str(item.get("name") or "")
            for item in profiles if item.get("uid")
        }
        self.subsession_table.blockSignals(True)
        self.subsession_table.setRowCount(len(visible))
        for row, item in enumerate(visible):
            summary = dict(summaries.get(item["id"]) or {})
            ended = item.get("ended_ns") or time.time_ns()
            duration = max(0, int((ended - item["started_ns"]) / 1_000_000_000))
            exp_total = int(summary.get("exp_gained") or 0)
            hours = duration / 3600 if duration else 0
            exp_percent = summary.get("exp_gained_percent")
            exp_hour = round(exp_total / hours) if hours else 0
            exp_hour_percent = (
                exp_percent / hours
                if hours and isinstance(exp_percent, (int, float)) else None
            )
            credits = int(summary.get("credits") or 0)
            contribution = summary.get("contribution")
            rarity = dict(summary.get("loot_by_rarity") or {})
            contribution_hour = (
                round(contribution / hours)
                if hours and isinstance(contribution, (int, float)) else None
            )
            character = (
                profiles_by_client.get(item.get("client_key"))
                or profiles_by_uid.get(item.get("character_uid"))
                or str(summary.get("character") or "")
                or "Aguardando UID"
            )
            location = str(item.get("location") or "").strip()
            levels = " · ".join(
                f"{mob}: {level}"
                for mob, level in dict(item.get("mob_levels") or {}).items()
            )
            values = {
                "select": "",
                "name": str(item.get("name") or "—")
                + (f"\n{location}" if location else ""),
                "character": character,
                "client": "Cliente B" if item.get("client_key") == "client:b" else "Cliente A",
                "status": "Em andamento" if item.get("ended_ns") is None else "Encerrada",
                "time": f"{duration // 3600:02d}:{duration // 60 % 60:02d}:{duration % 60:02d}",
                "map": str(item.get("map_name") or "—"),
                "spot": str(item.get("spot_name") or "—"),
                "mobs": ", ".join(item.get("mobs") or []) or "—",
                "levels": levels or "—",
                "kills": self._format_value(int(summary.get("kills") or 0)),
                "finalizations": self._format_value(
                    int(summary.get("finalizations") or 0)
                ),
                "exp_total": self._format_value(exp_total),
                "exp_percent": self._format_value(exp_percent, "%"),
                "exp_hour": self._format_value(exp_hour),
                "exp_hour_percent": self._format_value(exp_hour_percent, "%"),
                "credits": self._format_value(credits),
                "credits_hour": self._format_value(
                    round(credits / hours) if hours else 0
                ),
                "contribution": self._format_value(contribution),
                "contribution_hour": self._format_value(contribution_hour),
                "loot_total": self._format_value(sum(
                    int(rarity.get(key) or 0)
                    for key in ("common", "uncommon", "rare", "epic")
                )),
                "loot_common": self._format_value(int(rarity.get("common") or 0)),
                "loot_uncommon": self._format_value(int(rarity.get("uncommon") or 0)),
                "loot_rare": self._format_value(int(rarity.get("rare") or 0)),
                "loot_epic": self._format_value(int(rarity.get("epic") or 0)),
                "upload": {
                    "sent": "Enviada",
                    "pending": "Pendente",
                    "failed": "Falhou",
                }.get(str(item.get("upload_state") or ""), "Não enviada"),
            }
            for column, (key, _label, _width, _visible) in enumerate(
                SUBSESSION_COLUMNS
            ):
                text = values[key]
                cell = QtWidgets.QTableWidgetItem(text)
                if key == "select":
                    cell.setFlags(cell.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                    cell.setCheckState(QtCore.Qt.CheckState.Checked if item["id"] in self.selected_subsessions else QtCore.Qt.CheckState.Unchecked)
                    cell.setData(QtCore.Qt.ItemDataRole.UserRole, item["id"])
                elif key in {"name", "mobs", "levels"}:
                    cell.setToolTip(text)
                cell.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                self.subsession_table.setItem(row, column, cell)
            self.subsession_table.setRowHeight(row, 46 if location else 32)
        self.subsession_table.blockSignals(False)
        self.subsession_page_status.setText(f"Página {self.subsession_page} de {pages} · {len(items)} registro(s)")
        self._subsession_selection_changed()

    def _autofit_subsession_column(self, column: int) -> None:
        self.subsession_table.resizeColumnToContents(column)

    def _subsession_selection_changed(self, _item: QtWidgets.QTableWidgetItem | None = None) -> None:
        self.selected_subsessions.intersection_update(
            str(item.get("id"))
            for item in self.snapshot.get("subsessions") or []
            if item.get("id")
        )
        visible_ids = {
            str(self.subsession_table.item(row, 0).data(QtCore.Qt.ItemDataRole.UserRole))
            for row in range(self.subsession_table.rowCount())
            if self.subsession_table.item(row, 0)
        }
        self.selected_subsessions.difference_update(visible_ids)
        self.selected_subsessions.update(self._selected_subsession_ids())
        self.send_selected_status.setText(
            f"{len(self.selected_subsessions)} subsessão(ões) selecionada(s)"
            if self.selected_subsessions else "Nenhuma subsessão selecionada"
        )
        self._set_send_controls()

    def _render_sends(self) -> None:
        snapshot = self.snapshot
        stats = dict(snapshot.get("stats") or {})
        session = snapshot.get("session_id")
        self.send_continuous_status.setText("Dados locais disponíveis" if session else "Nenhuma sessão disponível")
        self.send_session_details.setText(
            f"{session} · {stats.get('recognized', 0)} eventos" if session else "Sessão —"
        )
        characters = [
            item for item in snapshot.get("characters") or [] if item.get("uid")
        ]
        market_events = sum(int((item.get("summary") or {}).get("market_events") or 0) for item in characters)
        self.send_status_labels["character"].setText(f"{len(characters)} personagem(ns) lido(s)" if characters else "Nenhum personagem lido")
        self.send_status_labels["market"].setText(f"{market_events} evento(s) de mercado")
        collections = dict(snapshot.get("collection_type_counts") or {})
        self.send_status_labels["codex"].setText(
            f"{int(collections.get(1) or 0)} pacote(s) lido(s)"
            if collections.get(1) else "Nenhum registro identificado"
        )
        self.send_status_labels["memory_chips"].setText(
            f"{int(collections.get(2) or 0)} pacote(s) lido(s)"
            if collections.get(2) else "Nenhum registro identificado"
        )
        self._set_send_controls()

    def _set_send_controls(self) -> None:
        enabled = bool(
            self.site_profile.connected
            and self.snapshot.get("session_id")
            and not self.site_busy
        )
        characters = [
            item for item in self.snapshot.get("characters") or [] if item.get("uid")
        ]
        collections = dict(self.snapshot.get("collection_type_counts") or {})
        availability = {
            "character": bool(characters),
            "market": any(
                int((item.get("summary") or {}).get("market_events") or 0)
                for item in characters
            ),
            "codex": bool(collections.get(1)),
            "memory_chips": bool(collections.get(2)),
        }
        capturing = bool(self.capture_engine and self.capture_engine.active)
        for (mode, _client), button in self.send_buttons.items():
            available = enabled and (capturing or availability[mode])
            button.setEnabled(available)
            button.setToolTip(
                ""
                if available
                else "Ainda não existem dados deste tipo disponíveis para envio."
            )
        selected_enabled = enabled and bool(self.selected_subsessions)
        for button in (self.send_selected_button, self.subsession_upload_button):
            button.setEnabled(selected_enabled)
            button.setToolTip(
                ""
                if selected_enabled
                else "Selecione uma subsessão encerrada e valide o token do Profile."
            )

    def _run_site_operation(self, name: str, callback) -> None:
        if self.site_busy:
            self.log.debug("site_operation_skipped name=%s reason=busy", name)
            return
        self.site_busy = True
        self._set_send_controls()
        self.log.debug("site_operation_started name=%s", name)

        def worker() -> None:
            started = time.perf_counter()
            try:
                self.site_operation_done.emit(name, callback(), None)
            except Exception as error:
                self.log.exception("background_operation_failed name=%s", name)
                self.site_operation_done.emit(name, None, error)
            finally:
                self.log.debug(
                    "site_operation_finished name=%s duration_ms=%s",
                    name,
                    round((time.perf_counter() - started) * 1000),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _activate_license(self) -> None:
        key = self.license_key.text().strip()
        if not key:
            QtWidgets.QMessageBox.warning(self, "Licença", "Informe a chave recebida.")
            return
        self.license_title.setText("Validando…")
        self._run_site_operation(
            "license:activate", lambda: self.license_client.activate(key, VERSION)
        )

    def _refresh_license_online(self) -> None:
        now = time.monotonic()
        if (
            self.site_busy
            or self.license_refresh_running
            or now - self.last_license_refresh_at < 60
        ):
            return
        self.license_refresh_running = True
        self.last_license_refresh_at = now
        self._run_site_operation(
            "license:refresh", lambda: self.license_client.refresh_if_due(VERSION)
        )

    def _current_session_id(self) -> str:
        return str(
            self.last_capture_session
            or self.snapshot.get("session_id")
            or self.preferences.get("last_session")
            or ""
        )

    def _export_session(self) -> None:
        engine = self.capture_engine
        if engine and engine.active:
            QtWidgets.QMessageBox.warning(
                self, "Exportação", "Encerre a captura antes de exportar."
            )
            return
        session_id = self._current_session_id()
        if not session_id:
            QtWidgets.QMessageBox.warning(
                self, "Exportação", "Nenhuma sessão capturada está disponível."
            )
            return
        target = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Escolha a pasta de exportação",
            str(Path(self.setting_capture_directory.text()) / "Exportados"),
        )
        if not target:
            return
        self._prepare_export_identity(session_id)
        self._run_export("export", session_id, Path(target))

    def _prepare_export_identity(self, session_id: str) -> None:
        store = CaptureStore(self.database_path)
        try:
            profiles = store.session_profiles(session_id)
            if len(profiles) != 1 or not store.unidentified_exp_flows(session_id):
                return
            name = str(profiles[0].get("name") or "personagem detectado")
            value, accepted = QtWidgets.QInputDialog.getDouble(
                self,
                "Identificar eventos pela EXP",
                f"Informe a EXP atual (%) de {name}:",
                0.0, 0.0, 100.0, 4,
            )
            if accepted:
                store.assign_unidentified_to_uid_by_exp(
                    session_id, str(profiles[0]["uid"]), value
                )
        finally:
            store.close()

    def _run_export(self, name: str, session_id: str, target: Path) -> None:
        profile = self.setting_profile.text().strip() or "Profile"
        language = str(self.preferences.get("item_name_language") or "pt")
        self.update_status.setText("Exportando e validando JSON/CSV…")
        self._run_site_operation(
            name,
            lambda: self.export_engine.export(
                session_id, target, profile, language
            ),
        )

    def _export_and_upload(self) -> None:
        if not self.site_profile.connected:
            QtWidgets.QMessageBox.warning(
                self, "Envio", "Valide o token do Profile antes de enviar."
            )
            return
        engine = self.capture_engine
        if engine and engine.active:
            QtWidgets.QMessageBox.warning(
                self, "Envio", "Encerre a captura antes de exportar e enviar."
            )
            return
        session_id = self._current_session_id()
        if not session_id:
            QtWidgets.QMessageBox.warning(self, "Envio", "Nenhuma sessão disponível.")
            return
        self._prepare_export_identity(session_id)
        target = Path(self.setting_capture_directory.text()) / "Exportados"
        profile = self.setting_profile.text().strip() or "Profile"
        language = str(self.preferences.get("item_name_language") or "pt")

        def export_and_upload() -> dict[str, object]:
            exported = self.export_engine.export(
                session_id, target, profile, language
            )
            receipts = [
                self.site_profile.upload(result.json_path, result.sha256)
                for result in exported["results"]
            ]
            exported["receipts"] = receipts
            return exported

        self._run_site_operation("export_upload", export_and_upload)

    def _finish_export(self, payload: dict[str, object], *, uploaded: bool) -> None:
        warnings = list(payload.get("warnings") or [])
        if warnings:
            QtWidgets.QMessageBox.warning(
                self,
                "Exportação com identificação incompleta",
                "\n\n".join(warnings) + "\n\nA exportação foi concluída.",
            )
        count = len(payload.get("results") or [])
        total = int(payload.get("total_bytes") or 0)
        raw = int(payload.get("raw_bytes") or 0)
        message = (
            f"{count} personagem(ns), JSON + CSV validados: "
            f"{self._format_bytes(total)}."
        )
        if uploaded:
            message += "\nEnvio ao site concluído."
        erase = self.setting_delete_export.isChecked()
        if not erase:
            erase = QtWidgets.QMessageBox.question(
                self,
                "Exportação concluída",
                message + f"\n\nMover {self._format_bytes(raw)} de segmentos para a Lixeira?",
            ) == QtWidgets.QMessageBox.StandardButton.Yes
        else:
            QtWidgets.QMessageBox.information(self, "Exportação concluída", message)
        if erase:
            files = [Path(path) for path in payload.get("raw_files") or []]
            if files and not _recycle(files):
                QtWidgets.QMessageBox.warning(
                    self, "Lixeira", "Alguns segmentos não puderam ser movidos."
                )
                return
            store = CaptureStore(self.database_path)
            try:
                store.clear_exported(str(payload.get("session_id") or ""))
            finally:
                store.close()
            self.preferences = save_preferences({
                "capture_pending": False,
                "last_session": "",
                "capture_prefix": "",
            }, self.preferences_path)
            self.last_capture_session = ""
            self.snapshot = {}
        diagnostic = payload.get("diagnostic")
        if diagnostic and QtWidgets.QMessageBox.question(
            self,
            "Diagnóstico sanitizado",
            "Existem eventos não decodificados. Autoriza enviar o arquivo "
            "sanitizado ao desenvolvedor?",
        ) == QtWidgets.QMessageBox.StandardButton.Yes:
            self._run_site_operation(
                "diagnostic:file",
                lambda: self.license_client.upload_diagnostic(Path(diagnostic), VERSION),
            )
        self.update_status.setText(message.replace("\n", " · "))
        self._load_readonly_data()

    def _open_log_folder(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        os.startfile(self.log_path.parent)

    def _open_discord(self) -> None:
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(DISCORD_URL))

    def _save_log_copy(self) -> None:
        lines = recent_lines(self.log_path)
        if not lines:
            QtWidgets.QMessageBox.information(
                self, "Log técnico", "Ainda não há registros para salvar."
            )
            return
        target, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Salvar cópia sanitizada do log",
            str(Path.home() / "Downloads" / f"RFQOL-log-{datetime.now():%Y%m%d-%H%M%S}.txt"),
            "Arquivo de texto (*.txt)",
        )
        if not target:
            return
        path = Path(target)
        temporary = path.with_name(f"{path.name}.tmp")
        try:
            temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
            os.replace(temporary, path)
            QtWidgets.QMessageBox.information(self, "Log técnico", "Cópia salva.")
        except OSError as error:
            temporary.unlink(missing_ok=True)
            QtWidgets.QMessageBox.warning(self, "Log técnico", str(error))

    def _send_diagnostic(self) -> None:
        if not self.license_client.lease:
            QtWidgets.QMessageBox.warning(
                self, "Diagnóstico", "Ative a licença antes de enviar."
            )
            return
        if QtWidgets.QMessageBox.question(
            self,
            "Enviar log técnico",
            "Autoriza enviar o log técnico sanitizado? Nenhuma senha, token, "
            "payload, IP, UID ou nome de personagem será incluído.",
        ) != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        store = CaptureStore(self.database_path)
        try:
            diagnostic = store.export_diagnostics(
                Path(self.setting_capture_directory.text()) / "Exportados",
                f"diagnostico-tecnico-{stamp}",
                f"suporte-{stamp}",
                logs=recent_lines(self.log_path),
            )
        finally:
            store.close()
        if not diagnostic:
            QtWidgets.QMessageBox.information(
                self, "Diagnóstico", "Ainda não há informações técnicas para enviar."
            )
            return
        self._run_site_operation(
            "diagnostic:file",
            lambda: self.license_client.upload_diagnostic(diagnostic, VERSION),
        )

    def _check_update(self) -> None:
        self.update_button.setEnabled(False)
        self.update_progress.setValue(0)
        self.update_status.setText("Consultando atualizações…")
        channel = str(self.update_channel.currentData() or "stable")
        self._run_site_operation("update:check", lambda: latest(channel))

    @QtCore.Slot(str, int, object)
    def _update_progress(self, phase: str, downloaded: int, total: object) -> None:
        if phase == "manifest":
            self.update_status.setText("Verificando manifesto assinado…")
            return
        if phase == "verify":
            self.update_progress.setValue(99)
            self.update_status.setText("Verificando integridade do instalador…")
            return
        size = int(total) if isinstance(total, int) else 0
        percent = min(100, round(downloaded * 100 / size)) if size else 0
        self.update_progress.setValue(percent)
        self.update_status.setText(
            f"Baixando: {percent}% · {self._format_bytes(downloaded)}"
        )

    def _download_update(self, release: dict[str, object]) -> None:
        self._run_site_operation(
            "update:download",
            lambda: download_verified(
                release,
                lambda phase, downloaded, total: self.update_progress_changed.emit(
                    phase, downloaded, total
                ),
                UPDATES_DIR,
                current_sequence=self.license_client.highest_release_sequence,
            ),
        )
    def _launch_update(self, installer: Path) -> None:
        try:
            manifest = verify_manifest(
                json.loads((UPDATES_DIR / "update-manifest.json").read_text(encoding="utf-8")),
                current_sequence=self.license_client.highest_release_sequence,
            )
            verify_downloaded(installer, manifest)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self.log.exception("update_reverification_failed")
            QtWidgets.QMessageBox.critical(
                self, "Atualização rejeitada", f"O instalador não é confiável:\n{error}"
            )
            return
        engine = self.capture_engine
        if self.capture_busy or (engine and engine.current_session):
            QtWidgets.QMessageBox.warning(
                self,
                "Captura pendente",
                "Encerre a captura e aguarde a leitura terminar antes de atualizar.",
            )
            return
        if QtWidgets.QMessageBox.question(
            self,
            "Atualização verificada",
            "Manifesto Ed25519 e SHA-256 conferem.\n\n"
            "O instalador não usa assinatura de código do Windows e pode "
            "aparecer como Publicador desconhecido.\n\n"
            "O RF QOL será fechado e o instalador será aberto. Continuar?",
        ) != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        script = (
            "Wait-Process -Id $args[0] -ErrorAction SilentlyContinue; "
            "Start-Process -FilePath $args[1]"
        )
        subprocess.Popen(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive",
                "-WindowStyle", "Hidden", "-Command", script,
                str(os.getpid()), str(installer.resolve()),
            ],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.exit_requested = True
        self.close()

    def _rollback(self) -> None:
        QtWidgets.QMessageBox.information(
            self,
            "Versão anterior",
            "O rollback só será oferecido quando existir um instalador anterior "
            "com manifesto e assinaturas válidas.",
        )

    def _connect_site_profile(self) -> None:
        profile = self.setting_profile.text().strip()
        token = self.setting_site_token.text().strip()
        if not profile or not token:
            QtWidgets.QMessageBox.warning(
                self, "Profile", "Informe o nome do Profile e o token gerado no site."
            )
            return
        self.site_profile_status.setText("Validando token…")
        self._run_site_operation(
            "connect", lambda: self.site_profile.connect(profile, token)
        )

    def _send_mode(self, mode: str, client_index: int) -> None:
        if not self.site_profile.connected:
            QtWidgets.QMessageBox.warning(
                self, "Envio", "Valide o token do Profile antes de enviar."
            )
            return
        target = 0 if client_index < 0 else client_index
        self.send_status_labels[mode].setText(
            "Lendo e enviando Mercado geral…"
            if mode == "market"
            else f"Lendo e enviando Cliente {chr(65 + target)}…"
        )
        language = str(self.preferences.get("item_name_language") or "pt")

        def read_and_send():
            engine = self.capture_engine
            if engine and engine.active:
                engine.read_live()
                store = CaptureStore(self.database_path)
                try:
                    for path in store.session_sources(engine.current_session):
                        if path.exists():
                            store.ingest(
                                path,
                                session_id=engine.current_session,
                                ports=DEFAULT_PORTS,
                                client_ports=engine.client_ports,
                                append_only=True,
                            )
                finally:
                    store.close()
            snapshot = ReadOnlySnapshotReader(
                self.database_path, self.license_client
            ).load(language)
            return self.site_uploader.send_mode(mode, target, snapshot, language)

        self._run_site_operation(
            f"send:{mode}:{target}",
            read_and_send,
        )

    def _send_selected_subsessions(self) -> None:
        self._subsession_selection_changed()
        identifiers = sorted(self.selected_subsessions)
        if not identifiers:
            return
        self.send_selected_status.setText("Enviando subsessões selecionadas…")
        self.subsession_upload_button.setText("Enviando…")
        language = str(self.preferences.get("item_name_language") or "pt")
        self._run_site_operation(
            "subsessions",
            lambda: self.site_uploader.send_subsessions(
                identifiers, dict(self.snapshot), language
            ),
        )

    @QtCore.Slot(str, object, object)
    def _site_operation_finished(
        self, name: str, result: object, error: object
    ) -> None:
        self.log.debug(
            "site_operation_applied name=%s success=%s error_type=%s",
            name,
            error is None,
            type(error).__name__ if error is not None else "none",
        )
        self.site_busy = False
        if name.startswith("license:"):
            self.license_refresh_running = False
        if name == "connect":
            self.setting_site_token.clear()
            if error is None:
                data = dict(result or {})
                self.preferences = save_preferences(
                    {"profile": data.get("profile")}, self.preferences_path
                )
                self.site_profile_status.setText(
                    f"Conectado ao Profile {data.get('profile')}"
                )
            else:
                self.site_profile_status.setText(
                    f"Não foi possível conectar: {error}"
                )
        elif name == "license:activate":
            self.license_key.clear()
            if error is not None:
                self.license_title.setText(f"Não foi possível ativar: {error}")
            else:
                self._apply_license(load_license_status())
                self.license_title.setText("Licença ativada e salva")
        elif name == "license:refresh":
            if error is not None:
                self.log.warning("license_refresh_failed error=%s", type(error).__name__)
            self._apply_license(load_license_status())
        elif name.startswith("send:"):
            mode = name.split(":", 2)[1]
            if error is None:
                target = dict(result or {}).get("target") or "Dados"
                self.send_status_labels[mode].setText(f"{target} enviado")
            else:
                message = str(error) or "Envio recusado pelo site"
                self.send_status_labels[mode].setText(message)
                QtWidgets.QMessageBox.warning(self, "Envio", str(error))
            self._load_readonly_data()
        elif name == "subsessions":
            self.subsession_upload_button.setText("Enviar selecionadas")
            if error is not None:
                self.send_selected_status.setText("Falha no envio")
                QtWidgets.QMessageBox.warning(self, "Subsessões", str(error))
            else:
                data = dict(result or {})
                failures = list(data.get("failures") or [])
                if failures:
                    self.log.error(
                        "subsession_upload_result failures=%s sent=%s",
                        len(failures), data.get("sent", 0),
                    )
                self.send_selected_status.setText(
                    f"{data.get('sent', 0)} enviada(s)"
                    + (f" · {len(failures)} falha(s)" if failures else "")
                )
                self._load_readonly_data()
                if failures:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Envio de subsessões",
                        f"{data.get('sent', 0)} enviada(s); "
                        f"{len(failures)} falharam.\n\n" + "\n".join(failures),
                    )
        elif name in {"export", "auto_export", "export_upload"}:
            if error is not None:
                self.update_status.setText(f"Exportação falhou: {error}")
                QtWidgets.QMessageBox.warning(self, "Exportação", str(error))
            else:
                self._finish_export(
                    dict(result or {}), uploaded=name == "export_upload"
                )
            QtCore.QTimer.singleShot(0, self._flush_observation_upload)
        elif name == "observations":
            if error is not None:
                self.log.error(
                    "observation_upload_failed error_type=%s",
                    type(error).__name__,
                )
            else:
                data = dict(result or {})
                self.log.info(
                    "observation_upload_completed characters=%s mobs=%s skipped=%s",
                    data.get("characters", 0),
                    data.get("mobs", 0),
                    bool(data.get("skipped")),
                )
        elif name == "alerts:save":
            if error is not None:
                self.log.error(
                    "monitor_alert_sync_failed error_type=%s",
                    type(error).__name__,
                )
            else:
                self.log.info("monitor_alert_sync_completed")
        elif name == "auto_market":
            pending, self.pending_auto_market = self.pending_auto_market, None
            if error is not None:
                self.log.error(
                    "auto_market_upload_failed error_type=%s",
                    type(error).__name__,
                )
            elif pending:
                session, signature = pending
                signatures = dict(
                    self.preferences.get("auto_market_signatures") or {}
                )
                signatures[session] = signature
                signatures = dict(list(signatures.items())[-20:])
                self.preferences = save_preferences(
                    {"auto_market_signatures": signatures},
                    self.preferences_path,
                )
                self.send_status_labels["market"].setText(
                    "Mercado enviado automaticamente"
                )
                self.log.info("auto_market_upload_completed")
        elif name == "diagnostic:file":
            if error is not None:
                QtWidgets.QMessageBox.information(
                    self, "Diagnóstico", f"Não foi possível enviar: {error}"
                )
            else:
                receipt = dict(result or {}).get("receipt")
                QtWidgets.QMessageBox.information(
                    self, "Diagnóstico", f"Enviado com protocolo {receipt}."
                )
        elif name == "update:check":
            self.update_button.setEnabled(True)
            if error is not None:
                self.update_status.setText(f"Atualização indisponível: {error}")
            else:
                release = dict(result or {})
                tag = str(release.get("tag_name") or "")
                if tag.lstrip("v") == VERSION:
                    self.update_progress.setValue(100)
                    self.update_status.setText("Você já usa a versão mais recente.")
                elif QtWidgets.QMessageBox.question(
                    self,
                    "Atualização encontrada",
                    f"{tag}\n\n{str(release.get('body') or '')[:800]}\n\n"
                    "Baixar e verificar agora?",
                ) == QtWidgets.QMessageBox.StandardButton.Yes:
                    self.update_button.setEnabled(False)
                    self._download_update(release)
                else:
                    self.update_status.setText("Atualização cancelada.")
        elif name == "update:download":
            self.update_button.setEnabled(True)
            if error is not None:
                self.update_progress.setValue(0)
                self.update_status.setText(f"Falha na atualização: {error}")
                QtWidgets.QMessageBox.warning(self, "Atualização rejeitada", str(error))
            else:
                self.update_progress.setValue(100)
                self.update_status.setText("Download concluído e verificado.")
                self._launch_update(Path(result))
        self._set_send_controls()

    def _reload_snapshot(self) -> None:
        self.overview_status.setText("Atualizando dados locais…")
        session_id = str(self.snapshot.get("session_id") or "")
        if session_id and self.database_path.exists():
            store = CaptureStore(self.database_path, readonly=True)
            try:
                self.snapshot["subsessions"] = store.subsessions(session_id)
                self._render_subsessions()
            finally:
                store.close()
        self._load_readonly_data()

    def _build_tutorial_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageTutorial")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        column.addWidget(_label("Tutorial", "title"))
        column.addWidget(_label("Comece em seis passos", "subtitle"))
        scroll = QtWidgets.QScrollArea(objectName="pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        content = QtWidgets.QWidget(objectName="scrollContent")
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        steps = (
            "Ative esta instalação em Configurações, na área Licença. A ativação será lembrada nas próximas aberturas.",
            "Abra o RF NEXT. O programa detecta automaticamente até dois clientes e separa as conexões de cada um.",
            "Use Cliente A e Cliente B para alternar a visão. Se necessário, renomeie apenas a identificação visual do cliente.",
            "Em Envios, Personagem, Mercado, Codex e Memory Chips enviam dados já lidos; eles não iniciam outra captura.",
            "Em Configurações, informe o Profile e o token do site. Subsessões encerradas podem ser selecionadas e enviadas sem duplicidade.",
            "Cada parada encerra uma sessão independente. Confira o tamanho antes de exportar e mova os segmentos à Lixeira somente após validar a exportação.",
        )
        for number, text in enumerate(steps, 1):
            card = QtWidgets.QFrame(objectName="panel")
            row = QtWidgets.QHBoxLayout(card)
            row.setContentsMargins(16, 12, 16, 12)
            badge = _label(str(number), "step")
            badge.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            badge.setFixedSize(34, 34)
            body = _label(text, "muted")
            body.setWordWrap(True)
            row.addWidget(badge)
            row.addWidget(body, 1)
            content_layout.addWidget(card)
        privacy = QtWidgets.QFrame(objectName="accentPanel")
        privacy_layout = QtWidgets.QVBoxLayout(privacy)
        privacy_layout.setContentsMargins(16, 12, 16, 12)
        privacy_layout.addWidget(_label("Privacidade", "subtitle"))
        privacy_text = _label(
            "Captura passiva limitada às conexões detectadas do RF NEXT, sem captura geral da rede, injeção, token de sessão, atualização silenciosa ou telemetria.",
            "muted",
        )
        privacy_text.setWordWrap(True)
        privacy_layout.addWidget(privacy_text)
        content_layout.addWidget(privacy)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        column.addWidget(scroll, 1)
        return page

    def _load_readonly_data(self) -> None:
        if self.data_load_running:
            self.data_load_pending = True
            self.log.debug("data_load_queued")
            return
        self.data_load_running = True
        self.log.debug("data_load_started")

        def worker() -> None:
            started = time.perf_counter()
            try:
                preferences = load_preferences(self.preferences_path)
                language = str(preferences.get("item_name_language") or "pt")
                capture_directory = Path(
                    preferences.get("capture_directory")
                    or CAPTURE_DIR
                )
                self.data_loaded.emit({
                    "preferences": preferences,
                    "license": load_license_status(),
                    "snapshot": self.snapshot_reader.load(language),
                    "storage_bytes": self._stored_capture_bytes(capture_directory),
                })
            except Exception as error:
                self.log.exception("data_load_failed")
                self.data_failed.emit(f"{type(error).__name__}: {error}")
            finally:
                self.log.debug(
                    "data_load_worker_finished duration_ms=%s",
                    round((time.perf_counter() - started) * 1000),
                )

        threading.Thread(target=worker, daemon=True).start()

    @QtCore.Slot(object)
    def _apply_readonly_data(self, payload: dict[str, object]) -> None:
        self.preferences = dict(payload.get("preferences") or {})
        set_detailed(self.log, bool(self.preferences.get("detailed_logging", False)))
        self.snapshot = dict(payload.get("snapshot") or {})
        self._reconcile_uid_selections()
        stats = dict(self.snapshot.get("stats") or {})
        self.log.debug(
            "data_load_applied session_available=%s characters=%s profiles=%s "
            "subsessions=%s recognized=%s unknown=%s storage_bytes=%s",
            bool(self.snapshot.get("session_id")),
            len(self.snapshot.get("characters") or []),
            len(self.snapshot.get("profiles") or []),
            len(self.snapshot.get("subsessions") or []),
            stats.get("recognized", 0),
            stats.get("unknown", 0),
            int(payload.get("storage_bytes") or 0),
        )
        self._apply_license(dict(payload.get("license") or {}))
        if not self.controls_initialized:
            self._load_settings_fields()
            self._sync_global_hotkeys()
            self._refresh_farm_catalog()
            self.controls_initialized = True
        self._render_overview()
        self._render_combat()
        self._render_subsessions()
        self._render_sends()
        engine = self._ensure_capture_engine()
        if engine.current_session:
            self.top_capture.setText(
                "Captura — ativa" if engine.active else "Captura — pendente recuperada"
            )
        storage_bytes = int(payload.get("storage_bytes") or 0)
        self.storage_bytes = storage_bytes
        self.top_storage.setText(f"Armazenado: {self._format_bytes(storage_bytes)}")
        self.setting_storage.setText(
            f"Capturas: {self.setting_capture_directory.text()}\n"
            f"Tamanho atual: {self._format_bytes(storage_bytes)}"
        )
        if self.license_active:
            self._refresh_license_online()
        self._finish_data_load()

    @QtCore.Slot(str)
    def _show_read_error(self, message: str) -> None:
        self.log.error("data_load_failed error_type=%s", message.split(":", 1)[0])
        self.overview_status.setText(f"Não foi possível ler a sessão: {message}")
        self.license_title.setText("Não foi possível ler a licença local")
        self._finish_data_load()

    def _finish_data_load(self) -> None:
        self.data_load_running = False
        if self.data_load_pending:
            self.data_load_pending = False
            QtCore.QTimer.singleShot(0, self._load_readonly_data)

    def _load_combat_data(self) -> None:
        if self.combat_load_running:
            self.combat_load_pending = True
            return
        self.combat_load_running = True
        active_locations: dict[str, str] = {}
        for subsession in list(self.snapshot.get("subsessions") or []):
            if subsession.get("ended_ns") is not None:
                continue
            client_key = str(subsession.get("client_key") or "")
            location = " · ".join(
                value
                for value in (
                    str(subsession.get("map_name") or "").strip(),
                    str(subsession.get("spot_name") or "").strip(),
                )
                if value
            ) or str(subsession.get("location") or "").strip()
            if client_key and location:
                active_locations[client_key] = location

        def worker() -> None:
            try:
                language = str(self.preferences.get("item_name_language") or "pt")
                reader = ReadOnlySnapshotReader(
                    self.database_path, self.license_client
                )
                payload = (
                    reader.load_live_combat(
                        list(self.live_combat_events),
                        self.live_combat_ports,
                        language,
                    )
                    if self.live_combat_events
                    else reader.load_combat(language)
                )
                knowledge = KnowledgeStore(self.knowledge_path)
                try:
                    for monitor in payload.get("combat_monitors") or []:
                        knowledge.observe_combat(
                            [monitor],
                            location=active_locations.get(
                                str(monitor.get("client_key") or ""), ""
                            ),
                        )
                finally:
                    knowledge.close()
                self.combat_loaded.emit(payload)
            except Exception as error:
                self.log.exception("combat_load_failed")
                self.combat_failed.emit(f"{type(error).__name__}: {error}")

        threading.Thread(target=worker, daemon=True).start()

    def _flush_observation_upload(self) -> None:
        session = self.pending_observation_session
        if not session or not self.site_profile.connected:
            return
        if self.site_busy:
            QtCore.QTimer.singleShot(500, self._flush_observation_upload)
            return
        self.pending_observation_session = ""
        self._run_site_operation(
            "observations",
            lambda: self.site_uploader.send_observations(
                session, self.knowledge_path
            ),
        )

    def _maybe_auto_market_upload(self) -> None:
        enabled = (
            self.setting_auto_market.isChecked()
            if self.controls_initialized
            else bool(self.preferences.get("auto_market_upload", True))
        )
        engine = self.capture_engine
        session = str((engine and engine.current_session) or "")
        if not enabled or not session or not self.site_profile.connected or self.site_busy:
            return
        store = CaptureStore(self.database_path, readonly=True)
        try:
            signature = store.completed_market_signature(session)
        finally:
            store.close()
        sent = dict(self.preferences.get("auto_market_signatures") or {})
        if not signature or sent.get(session) == signature:
            return
        self.pending_auto_market = (session, signature)
        language = str(self.preferences.get("item_name_language") or "pt")
        self._run_site_operation(
            "auto_market",
            lambda: self.site_uploader.send_mode(
                "market",
                0,
                ReadOnlySnapshotReader(
                    self.database_path, self.license_client
                ).load(language),
                language,
            ),
        )

    @QtCore.Slot(object)
    def _apply_combat_data(self, payload: dict[str, object]) -> None:
        if payload.get("session_id") == self.snapshot.get("session_id"):
            self.snapshot["combat_monitors"] = list(
                payload.get("combat_monitors") or []
            )
            self._render_combat()
            self._evaluate_alerts(self.snapshot["combat_monitors"])
        self._finish_combat_load()

    def _evaluate_alerts(self, monitors: list[dict[str, Any]]) -> None:
        alerts = self._alert_preferences()
        wanted_characters = {
            value.strip().casefold()
            for value in str(alerts.get("characters") or "").split(",")
            if value.strip()
        }
        wanted_guilds = {
            value.strip().casefold()
            for value in str(alerts.get("guilds") or "").split(",")
            if value.strip()
        }
        for monitor in monitors:
            for player in list(monitor.get("nearby_players") or []):
                name = str(player.get("name") or "").casefold()
                guild = str(player.get("guild_name") or "").casefold()
                if alerts.get("characters_enabled") and name in wanted_characters:
                    self._fire_alert(f"character:{name}", f"Personagem próximo: {player.get('name')}")
                if alerts.get("guilds_enabled") and guild in wanted_guilds:
                    self._fire_alert(f"guild:{guild}", f"Guilda próxima: {player.get('guild_name')}")
            pvp = dict(monitor.get("pvp") or {})
            if alerts.get("pvp_hit") and pvp.get("direction") == "entrada":
                self._fire_alert("pvp_hit", f"Ataque PvP recebido de {pvp.get('name') or 'jogador'}")
            if alerts.get("boss_detected"):
                for boss in list(monitor.get("bosses") or []):
                    boss_key = boss.get("npc_index") or boss.get("uid") or boss.get("name")
                    self._fire_alert(
                        f"boss:{boss_key}",
                        f"Boss próximo: {boss.get('name') or 'boss confirmado'}",
                    )
            local = dict(monitor.get("local") or {})
            percent = local.get("hp_percent")
            if (
                alerts.get("low_hp")
                and isinstance(percent, (int, float))
                and percent <= int(alerts.get("low_hp_percent") or 30)
            ):
                self._fire_alert("low_hp", f"Vida baixa: {float(percent):.1f}%".replace(".", ","))

    def _fire_alert(self, key: str, message: str) -> None:
        now = time.monotonic()
        if now - self.alert_last_fired.get(key, 0.0) < 10:
            return
        self.alert_last_fired[key] = now
        self.alert_status.setText(message)
        self.log.info("monitor_alert key=%s", key.split(":", 1)[0])
        if self.alert_sound.isChecked():
            QtWidgets.QApplication.beep()
        QtWidgets.QApplication.alert(self, 3000)

    @QtCore.Slot(str)
    def _show_combat_error(self, message: str) -> None:
        self.top_last_read.setText(
            f"Última leitura rápida: falhou ({message.split(':', 1)[0]})"
        )
        self.top_last_read.setToolTip(message)
        self._finish_combat_load()

    def _finish_combat_load(self) -> None:
        self.combat_load_running = False
        if self.combat_load_pending:
            self.combat_load_pending = False
            QtCore.QTimer.singleShot(0, self._load_combat_data)

    def _apply_license(self, status: dict[str, object]) -> None:
        active = bool(status.get("active"))
        self.license_active = active
        message = str(status.get("message") or "Licença indisponível")
        self.top_license.setText(f"Licença — {message.lower()}")
        self.top_license.setProperty("role", "ok" if active else "muted")
        self.top_license.style().unpolish(self.top_license)
        self.top_license.style().polish(self.top_license)
        self.license_title.setText(message)
        self.license_title.setProperty("role", "ok" if active else "warning")
        details = [f"Fonte local: {status.get('source') or 'nenhuma'}"]
        if status.get("valid_until"):
            details.append(f"Prazo offline: {status['valid_until']}")
        if status.get("next_check_at"):
            details.append(f"Próxima validação: {status['next_check_at']}")
        details.append("Comprovante local protegido; renovação online feita quando devida.")
        self.license_details.setText("\n".join(details))
        self._set_capture_controls()

    @staticmethod
    def _stored_capture_bytes(directory: Path) -> int:
        try:
            return sum(
                path.stat().st_size
                for path in Path(directory).rglob("*")
                if path.is_file() and path.suffix.casefold() in {".etl", ".pcap", ".pcapng"}
            )
        except OSError:
            return 0

    def _ensure_capture_engine(self) -> CaptureEngine:
        if self.capture_engine is None:
            directory = Path(
                self.preferences.get("capture_directory")
                or CAPTURE_DIR
            )
            self.capture_engine = CaptureEngine(
                directory,
                self.database_path,
                self.license_client,
                profile=str(self.preferences.get("profile") or "Profile"),
                session_counter=self._bounded(
                    self.preferences.get("session_counter"), 0, 999999, 0
                ),
            )
            if not self.capture_recovery_attempted:
                self.capture_recovery_attempted = True
                try:
                    recovered = self.capture_engine.restore(self.preferences)
                    if recovered:
                        self.last_capture_session = str(recovered["session_id"])
                        self.log.info(
                            "capture_recovered active=%s files=%s",
                            recovered["active"], recovered["files"],
                        )
                except Exception:
                    self.log.exception("capture_recovery_failed")
        return self.capture_engine

    def _ensure_monitor_engine(self) -> MonitorEngine:
        if self.monitor_engine is None:
            self.monitor_engine = MonitorEngine(self.license_client)
        return self.monitor_engine

    def _monitor_interval_changed(self, mode: str) -> None:
        self.monitor_next_due[mode] = 0.0

    def _update_monitor_button(self, mode: str) -> None:
        controls = self.monitor_controls[mode]
        enabled = controls["enabled"].isChecked()
        action = "Desligar monitor" if enabled else "Ligar monitor"
        tabs = controls.get("tabs")
        client = f" Cliente {chr(65 + tabs.currentIndex())}" if tabs else ""
        controls["enabled"].setText(
            f"{action}{client}  {controls['shortcut']}"
        )

    def _monitor_client_changed(self, mode: str, index: int) -> None:
        controls = self.monitor_controls[mode]
        enabled = controls["enabled"]
        enabled.blockSignals(True)
        enabled.setChecked(self.monitor_client_enabled[mode][index])
        enabled.blockSignals(False)
        for card_index, card in enumerate(self.combat_page_layouts[mode]["cards"]):
            card.setVisible(card_index == index)
        self._update_monitor_button(mode)
        self._sync_combat_layout()
        self._render_combat()

    def _disable_monitor_mode(self, mode: str) -> None:
        if mode in self.monitor_client_enabled:
            self.monitor_client_enabled[mode] = [False, False]
        self.monitor_enabled[mode] = False
        controls = self.monitor_controls[mode]
        controls["enabled"].blockSignals(True)
        controls["enabled"].setChecked(False)
        controls["enabled"].blockSignals(False)
        self._update_monitor_button(mode)

    def _resume_active_monitors(self) -> None:
        if not any(self.monitor_enabled.values()) or self.capture_busy:
            return
        monitor = self._ensure_monitor_engine()
        if not monitor.active:
            self.top_last_read.setText("Monitores — iniciando stream em memória…")
            self._run_capture_operation("monitor:start", monitor.start)

    def _toggle_monitor(self, mode: str, enabled: bool) -> None:
        controls = self.monitor_controls[mode]
        tabs = controls.get("tabs")
        if tabs is not None:
            self.monitor_client_enabled[mode][tabs.currentIndex()] = enabled
            self.monitor_enabled[mode] = any(self.monitor_client_enabled[mode])
        else:
            self.monitor_enabled[mode] = enabled
        self._update_monitor_button(mode)
        self.monitor_next_due[mode] = 0.0
        self._render_combat()
        if not any(self.monitor_enabled.values()):
            if self.monitor_engine and self.monitor_engine.active:
                try:
                    self.monitor_engine.stop()
                except Exception:
                    self.log.exception("monitor_stop_failed")
            self.top_last_read.setText("Monitores — desligados")
            return
        capture = self.capture_engine
        if capture and capture.active:
            self._capture_tick()
            return
        self._resume_active_monitors()

    def _toggle_boss_overlay(self, enabled: bool) -> None:
        if not enabled:
            if self.boss_overlay:
                self.boss_overlay.close()
                self.boss_overlay = None
            return
        overlay = _MovableOverlay(self)
        overlay.setWindowTitle("RF QOL · Boss")
        overlay.setWindowFlags(
            QtCore.Qt.WindowType.Tool
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.FramelessWindowHint
        )
        overlay.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)
        overlay.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        overlay.setObjectName("monitorOverlay")
        overlay.setStyleSheet("QDialog#monitorOverlay { background: transparent; }")
        overlay.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
        overlay.setToolTip("Arraste com o botão esquerdo para mover.")
        overlay.position_changed.connect(self._save_boss_overlay_position)
        layout = QtWidgets.QVBoxLayout(overlay)
        layout.setContentsMargins(12, 10, 12, 10)
        self.boss_overlay_name = _label("Aguardando boss próximo", "subtitle")
        self.boss_overlay_hp = _label("HP —", "data")
        self.boss_overlay_progress = QtWidgets.QProgressBar()
        self.boss_overlay_progress.setRange(0, 1000)
        self.boss_overlay_progress.setTextVisible(False)
        self.boss_overlay_rate = _label("DPS — · Tempo restante —", "muted")
        layout.addWidget(self.boss_overlay_name)
        layout.addWidget(self.boss_overlay_hp)
        layout.addWidget(self.boss_overlay_progress)
        layout.addWidget(self.boss_overlay_rate)
        overlay.resize(430, 150)
        self._restore_overlay_position(overlay, "boss_overlay_position")
        self.boss_overlay = overlay
        overlay.show()
        self._update_boss_overlay(
            list(self.snapshot.get("combat_monitors") or [])
        )

    def _toggle_pvp_overlay(self, enabled: bool) -> None:
        if not enabled:
            if self.pvp_overlay:
                self.pvp_overlay.close()
                self.pvp_overlay = None
            return
        overlay = _MovableOverlay(self)
        overlay.setWindowTitle("RF QOL · PvP próximo")
        overlay.setWindowFlags(
            QtCore.Qt.WindowType.Tool
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.FramelessWindowHint
        )
        overlay.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)
        overlay.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        overlay.setObjectName("monitorOverlay")
        overlay.setStyleSheet("QDialog#monitorOverlay { background: transparent; }")
        overlay.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
        overlay.setToolTip("Arraste com o botão esquerdo para mover.")
        overlay.position_changed.connect(self._save_pvp_overlay_position)
        layout = QtWidgets.QVBoxLayout(overlay)
        layout.setContentsMargins(12, 10, 12, 10)
        self.pvp_overlay_summary = _label("Nenhum jogador hostil confirmado", "subtitle")
        self.pvp_overlay_rows = QtWidgets.QVBoxLayout()
        layout.addWidget(self.pvp_overlay_summary)
        layout.addLayout(self.pvp_overlay_rows)
        overlay.resize(410, 180)
        self._restore_overlay_position(overlay, "pvp_overlay_position")
        self.pvp_overlay = overlay
        overlay.show()
        self._update_pvp_overlay(
            list(self.snapshot.get("combat_monitors") or [])
        )

    def _restore_overlay_position(
        self, overlay: QtWidgets.QDialog, preference_key: str
    ) -> None:
        position = self.preferences.get(preference_key)
        if isinstance(position, (list, tuple)) and len(position) == 2:
            try:
                point = QtCore.QPoint(int(position[0]), int(position[1]))
                screen = QtGui.QGuiApplication.screenAt(point)
                if screen is None:
                    screen = QtGui.QGuiApplication.primaryScreen()
                if screen is not None:
                    area = screen.availableGeometry()
                    point.setX(
                        max(area.left(), min(point.x(), area.right() - overlay.width() + 1))
                    )
                    point.setY(
                        max(area.top(), min(point.y(), area.bottom() - overlay.height() + 1))
                    )
                overlay.move(point)
            except (TypeError, ValueError):
                pass

    def _save_overlay_position(
        self, preference_key: str, position: QtCore.QPoint
    ) -> None:
        self.preferences = save_preferences(
            {preference_key: [position.x(), position.y()]},
            self.preferences_path,
        )

    @QtCore.Slot(QtCore.QPoint)
    def _save_pvp_overlay_position(self, position: QtCore.QPoint) -> None:
        self._save_overlay_position("pvp_overlay_position", position)

    @QtCore.Slot(QtCore.QPoint)
    def _save_boss_overlay_position(self, position: QtCore.QPoint) -> None:
        self._save_overlay_position("boss_overlay_position", position)

    def _set_capture_controls(self) -> None:
        engine = self.capture_engine
        active = bool(engine and engine.active)
        paused = bool(engine and engine.paused)
        self.start_button.setText(
            "Continuar  Ctrl+F8" if paused else "Iniciar  Ctrl+F8"
        )
        self.start_button.setEnabled(
            self.license_active and not self.capture_busy and not active
        )
        self.pause_button.setEnabled(active and not self.capture_busy)
        self.stop_button.setEnabled(
            bool(engine and engine.current_session) and not self.capture_busy
        )
        self.stop_without_reading_button.setEnabled(
            bool(engine and engine.current_session) and not self.capture_busy
        )
        if self._tray:
            self.tray_start_action.setEnabled(self.start_button.isEnabled())
            self.tray_pause_action.setEnabled(self.pause_button.isEnabled())
            self.tray_stop_action.setEnabled(self.stop_button.isEnabled())

    def _run_capture_operation(self, name: str, callback) -> None:
        if self.capture_busy:
            self.log.debug("capture_operation_skipped name=%s reason=busy", name)
            return
        self.capture_busy = True
        self._set_capture_controls()
        self.log.debug("capture_operation_started name=%s", name)

        def worker() -> None:
            started = time.perf_counter()
            try:
                self.capture_operation_done.emit(name, callback(), None)
            except Exception as error:
                self.log.exception(
                    "capture_operation_failed name=%s error_type=%s detail=%s",
                    name,
                    type(error).__name__,
                    error,
                )
                self.capture_operation_done.emit(name, None, error)
            finally:
                self.log.debug(
                    "capture_operation_finished name=%s duration_ms=%s",
                    name,
                    round((time.perf_counter() - started) * 1000),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _discard_previous_capture(self) -> bool:
        engine = self._ensure_capture_engine()
        session_id = str(
            engine.current_session
            or self.preferences.get("last_session")
            or self.snapshot.get("session_id")
            or ""
        )
        store = CaptureStore(self.database_path)
        try:
            files = list(store.session_sources(session_id)) if session_id else []
        finally:
            store.close()
        prefix = str(self.preferences.get("capture_prefix") or "")
        capture_directory = Path(
            self.preferences.get("capture_directory")
            or CAPTURE_DIR
        )
        if prefix:
            files.extend(capture_directory.glob(f"{prefix}*.etl"))
        files = list(dict.fromkeys(path for path in files if path.exists()))
        if not session_id and not files:
            self.discard_previous.setChecked(False)
            return True
        total = sum(path.stat().st_size for path in files)
        if not QtWidgets.QMessageBox.question(
            self,
            "Descartar sessão anterior",
            f"Mover {self._format_bytes(total)} para a Lixeira e remover somente "
            "a sessão anterior?",
        ) == QtWidgets.QMessageBox.StandardButton.Yes:
            return False
        try:
            files.extend(engine.abandon())
            files = list(dict.fromkeys(path for path in files if path.exists()))
            if files and not _recycle(files):
                raise OSError("Alguns segmentos não puderam ser movidos para a Lixeira")
            store = CaptureStore(self.database_path)
            try:
                if session_id:
                    store.clear_exported(session_id)
            finally:
                store.close()
            self.preferences = save_preferences({
                "capture_pending": False,
                "last_session": "",
                "capture_prefix": "",
                "capture_ports": [],
                "capture_client_ports": [],
                "capture_client_pids": [],
            }, self.preferences_path)
            self.capture_engine = None
            self.capture_recovery_attempted = True
            self.discard_previous.setChecked(False)
            self.snapshot = {}
            self.log.info("previous_session_discarded")
            return True
        except Exception as error:
            self.log.exception("previous_session_discard_failed")
            QtWidgets.QMessageBox.warning(self, "Descartar sessão", str(error))
            return False

    def _start_capture(self) -> None:
        if not self.license_active:
            self.top_capture.setText("Captura — licença necessária")
            return
        if self.discard_previous.isChecked() and not self._discard_previous_capture():
            return
        if self.monitor_engine and self.monitor_engine.active:
            try:
                self.monitor_engine.stop()
            except Exception as error:
                self.log.exception("monitor_handover_stop_failed")
                self.top_capture.setText(f"Captura — monitor não encerrou: {error}")
                return
        engine = self._ensure_capture_engine()
        self.top_capture.setText(
            "Captura — continuando…" if engine.paused else "Captura — iniciando…"
        )
        self._run_capture_operation("start", engine.start)

    def _pause_capture(self) -> None:
        engine = self._ensure_capture_engine()
        if self.capture_busy:
            self.pending_capture_action = "pause"
            self.top_capture.setText("Captura — pausará após a leitura atual…")
            return
        if not engine.active:
            return
        self.top_capture.setText("Captura — pausando e lendo segmentos…")
        self._run_capture_operation("pause", lambda: engine.stop(pause=True))

    def _stop_capture(self) -> None:
        engine = self._ensure_capture_engine()
        if self.capture_busy:
            self.pending_capture_action = "stop"
            self.top_capture.setText("Captura — encerrará após a leitura atual…")
            return
        if not engine.current_session:
            self.top_capture.setText("Captura — nenhuma sessão para encerrar")
            return
        self.top_capture.setText("Captura — encerrando e lendo segmentos…")
        self._run_capture_operation("stop", engine.stop)

    def _stop_capture_without_reading(self) -> None:
        engine = self._ensure_capture_engine()
        if self.capture_busy:
            return
        if not engine.current_session:
            self.top_capture.setText("Captura — nenhuma sessão para encerrar")
            return
        self.top_capture.setText("Captura — interrompendo sem ler os arquivos…")
        self._run_capture_operation("stop_without_reading", engine.stop_without_reading)

    @QtCore.Slot(str, object, object)
    def _capture_operation_finished(
        self, name: str, result: object, error: object
    ) -> None:
        self.capture_busy = False
        self.log.debug(
            "capture_operation_applied name=%s success=%s error_type=%s",
            name,
            error is None,
            type(error).__name__ if error is not None else "none",
        )
        if error is not None:
            if name.startswith("monitor:"):
                self.top_last_read.setText(f"Monitor — falha: {error}")
                self.top_last_read.setToolTip(str(error))
                for mode, enabled in self.monitor_enabled.items():
                    if enabled:
                        self._disable_monitor_mode(mode)
                return
            detail = str(error)
            if name == "start" and "Outra captura PktMon" in detail:
                self.top_capture.setText("Captura — outra sessão já está ativa")
                self.top_capture.setToolTip(detail)
                QtWidgets.QMessageBox.warning(
                    self,
                    "Captura já ativa",
                    "Já existe outra instância do RF QOL capturando. "
                    "Encerre essa sessão pelo programa que já está aberto e tente novamente.",
                )
            else:
                self.top_capture.setText(f"Captura — falha: {error}")
                self.top_capture.setToolTip(detail)
            if name in {"read", "preview"}:
                if name == "preview":
                    now_mono = time.monotonic()
                    for mode, enabled in self.monitor_enabled.items():
                        if enabled:
                            self.monitor_next_due[mode] = (
                                now_mono
                                + self.monitor_controls[mode]["interval"].value()
                            )
                else:
                    self.next_read_at = (
                        time.monotonic() + self.setting_decode_interval.value()
                    )
                self.top_last_read.setText(
                    f"Última leitura: falhou ({type(error).__name__}); captura continua"
                )
                self.top_last_read.setToolTip(str(error))
            self._set_capture_controls()
            pending, self.pending_capture_action = self.pending_capture_action, None
            if pending == "pause":
                QtCore.QTimer.singleShot(0, self._pause_capture)
            elif pending == "stop":
                QtCore.QTimer.singleShot(0, self._stop_capture)
            return
        data = dict(result or {})
        files = data.get("files") or 0
        file_count = files if isinstance(files, int) else len(files)
        self.log.debug(
            "capture_result name=%s live=%s clients=%s connections=%s available=%s "
            "added=%s bytes=%s fallback=%s failures=%s files=%s paused=%s",
            name,
            data.get("live"),
            data.get("clients"),
            data.get("connections"),
            data.get("available"),
            data.get("added"),
            data.get("bytes"),
            data.get("fallback"),
            len(data.get("failures") or []),
            file_count,
            data.get("paused"),
        )
        for failure in data.get("failures") or []:
            self.log.error("capture_result_failure name=%s detail=%s", name, failure)
        if name in {"monitor:start", "monitor:preview"}:
            now_mono = time.monotonic()
            if name == "monitor:start":
                self.top_last_read.setText(
                    f"Monitores — ativos · {data.get('clients', 0)} cliente(s)"
                )
            else:
                self.live_combat_events = list(data.get("events") or [])
                self.live_combat_ports = tuple(
                    tuple(int(port) for port in group)
                    for group in data.get("client_ports") or []
                )
                metrics = dict(data.get("monitor_metrics") or {})
                self.top_last_read.setText(
                    f"Monitores: {len(self.live_combat_events)} evento(s) prioritários"
                    f" · fila {metrics.get('queue_depth', 0)}"
                    f" · atraso {float(metrics.get('lag_seconds') or 0):.1f} s"
                )
                self.log.debug("monitor_metrics %s", metrics)
                self._load_combat_data()
            for mode, enabled in self.monitor_enabled.items():
                if enabled and self.monitor_next_due[mode] <= now_mono:
                    self.monitor_next_due[mode] = (
                        now_mono + self.monitor_controls[mode]["interval"].value()
                    )
            self._set_capture_controls()
            return
        engine = self._ensure_capture_engine()
        if name == "start":
            self.last_capture_session = str(data.get("session_id") or "")
            self._apply_uid_selections(self.last_capture_session)
            self.preferences = save_preferences({
                "session_counter": data.get("session_counter"),
                "last_session": data.get("session_id"),
                "capture_pending": True,
                "capture_prefix": data.get("capture_prefix"),
                "capture_ports": data.get("capture_ports"),
                "capture_client_ports": data.get("capture_client_ports"),
                "capture_client_pids": data.get("capture_client_pids"),
            }, self.preferences_path)
            self.next_read_at = time.monotonic() + 3
            self.top_capture.setText(
                f"Captura — ativa · {data.get('clients', 0)} cliente(s)"
            )
            if not data.get("live"):
                live_error = str(data.get("live_error") or "leitura ao encerrar")
                self.live_preview_error = live_error
                self.log.warning("live_preview_start_failed error=%s", live_error)
                self.top_last_read.setText(
                    f"Última leitura: prévia indisponível ({live_error.split(':', 1)[0]})"
                )
                self.top_last_read.setToolTip(live_error)
            else:
                self.live_preview_error = ""
                self.top_last_read.setText("Última leitura: primeira em 3 s")
                self.top_last_read.setToolTip("")
            self._capture_tick()
        elif name == "read":
            now = datetime.now().strftime("%H:%M:%S")
            if data.get("available"):
                suffix = " · modo compatível" if data.get("fallback") else ""
                self.top_last_read.setText(
                    f"Última leitura: {now} · {data.get('added', 0)} evento(s){suffix}"
                )
                self.top_last_read.setToolTip(self.live_preview_error)
            else:
                error_type = self.live_preview_error.split(":", 1)[0]
                self.top_last_read.setText(
                    f"Última leitura: prévia indisponível ({error_type})"
                    if error_type else "Última leitura: prévia indisponível"
                )
                self.top_last_read.setToolTip(self.live_preview_error)
            if data.get("capture_prefix"):
                self.preferences = save_preferences({
                    "capture_prefix": data.get("capture_prefix"),
                    "capture_ports": data.get("capture_ports"),
                }, self.preferences_path)
            self.next_read_at = time.monotonic() + self.setting_decode_interval.value()
            self._load_readonly_data()
            QtCore.QTimer.singleShot(0, self._maybe_auto_market_upload)
        elif name == "preview":
            now = datetime.now().strftime("%H:%M:%S")
            now_mono = time.monotonic()
            metrics = dict(data.get("monitor_metrics") or {})
            for mode, enabled in self.monitor_enabled.items():
                if enabled and self.monitor_next_due[mode] <= now_mono:
                    self.monitor_next_due[mode] = (
                        now_mono + self.monitor_controls[mode]["interval"].value()
                    )
            self.top_last_read.setText(
                f"Última leitura rápida: {now} · {data.get('added', 0)} evento(s)"
                f" · fila {metrics.get('queue_depth', 0)}"
                f" · atraso {float(metrics.get('lag_seconds') or 0):.1f} s"
                if data.get("available")
                else "Última leitura rápida: indisponível neste modo de captura"
            )
            self.live_combat_events = list(data.get("events") or [])
            self.live_combat_ports = tuple(
                tuple(int(port) for port in group)
                for group in data.get("client_ports") or []
            )
            self.log.debug("monitor_metrics %s", metrics)
            self._load_combat_data()
        elif name == "pause":
            self.top_capture.setText("Captura — pausada")
            self._load_readonly_data()
            if any(self.monitor_enabled.values()):
                QtCore.QTimer.singleShot(0, self._resume_active_monitors)
        elif name == "stop":
            self.last_capture_session = str(data.get("session_id") or self.last_capture_session)
            failures = list(data.get("failures") or [])
            self.top_capture.setText(
                "Captura — encerrada"
                + (f" · {len(failures)} falha(s)" if failures else "")
            )
            if not failures:
                self.preferences = save_preferences(
                    {"capture_pending": False}, self.preferences_path
                )
                if self.site_profile.connected and self.last_capture_session:
                    self.pending_observation_session = self.last_capture_session
            self._load_readonly_data()
            if any(self.monitor_enabled.values()):
                QtCore.QTimer.singleShot(0, self._resume_active_monitors)
            self.top_next_read.setText("Próx. leitura: —")
            if not failures and self.setting_auto_export.isChecked():
                target = Path(self.setting_capture_directory.text()) / "Exportados"
                self._prepare_export_identity(self.last_capture_session)
                QtCore.QTimer.singleShot(
                    0,
                    lambda session=self.last_capture_session, destination=target:
                    self._run_export("auto_export", session, destination),
                )
            elif not failures:
                QtCore.QTimer.singleShot(0, self._flush_observation_upload)
        elif name == "stop_without_reading":
            self.last_capture_session = str(
                data.get("session_id") or self.last_capture_session
            )
            self.preferences = save_preferences(
                {
                    "capture_pending": True,
                    "last_session": self.last_capture_session,
                },
                self.preferences_path,
            )
            self.top_capture.setText(
                f"Captura — encerrada sem leitura · {file_count} arquivo(s) preservado(s)"
            )
            self.top_next_read.setText("Próx. leitura: adiada")
            self.capture_engine = None
            self.capture_recovery_attempted = False
            if any(self.monitor_enabled.values()):
                QtCore.QTimer.singleShot(0, self._resume_active_monitors)
        self._set_capture_controls()
        pending, self.pending_capture_action = self.pending_capture_action, None
        if pending == "pause":
            QtCore.QTimer.singleShot(0, self._pause_capture)
        elif pending == "stop":
            QtCore.QTimer.singleShot(0, self._stop_capture)

    def _capture_tick(self) -> None:
        memory = _process_memory_bytes()
        self.top_memory.setText(
            f"RAM: {self._format_bytes(memory)}" if memory is not None else "RAM: —"
        )
        engine = self.capture_engine
        monitor = self.monitor_engine
        if not engine and not monitor:
            return
        now = time.monotonic()
        if self.license_active and now - self.last_license_refresh_at >= 60:
            self._refresh_license_online()
        if engine and engine.active and now - self.last_heartbeat_at >= 15:
            try:
                engine.heartbeat()
                self.last_heartbeat_at = now
                self.log.debug("capture_heartbeat_ok")
            except OSError as error:
                self.log.warning("capture_heartbeat_failed error_type=%s", type(error).__name__)
                self.top_capture.setText(f"Captura — heartbeat falhou: {error}")
        if engine and engine.active:
            if now - self.last_storage_scan_at >= 5:
                self.last_storage_scan_at = now
                directory = Path(
                    self.preferences.get("capture_directory")
                    or CAPTURE_DIR
                )
                self.storage_bytes = self._stored_capture_bytes(directory)
                self.top_storage.setText(
                    f"Armazenado: {self._format_bytes(self.storage_bytes)}"
                )
            self._rotate_auto_subsessions()
            remaining = max(0, math.ceil(self.next_read_at - now))
            monitor_active = any(self.monitor_enabled.values())
            next_due = min(
                (
                    self.monitor_next_due[mode]
                    for mode, enabled in self.monitor_enabled.items()
                    if enabled
                ),
                default=0.0,
            )
            monitor_remaining = max(0, math.ceil(next_due - now))
            self.top_next_read.setText(
                f"Próx. leitura: {remaining} s"
                + (f" · monitor: {monitor_remaining} s" if monitor_active else "")
            )
            if not self.capture_busy and now >= self.next_read_at:
                self.top_last_read.setText("Última leitura: atualizando…")
                self._run_capture_operation("read", engine.read_live)
            elif (
                monitor_active
                and not self.capture_busy
                and now >= next_due
            ):
                self.top_last_read.setText("Última leitura rápida: atualizando…")
                self._run_capture_operation("preview", engine.preview_live)
        elif monitor and monitor.active and any(self.monitor_enabled.values()):
            next_due = min(
                self.monitor_next_due[mode]
                for mode, enabled in self.monitor_enabled.items()
                if enabled
            )
            self.top_next_read.setText(
                f"Próx. monitor: {max(0, math.ceil(next_due - now))} s"
            )
            if not self.capture_busy and now >= next_due:
                self._run_capture_operation("monitor:preview", monitor.snapshot)
        elif engine and engine.paused:
            self.top_next_read.setText("Próx. leitura: pausada")
        elif engine and engine.current_session and not self.capture_busy:
            self.top_capture.setText("Captura — interrompida; encerre para analisar")

    def _page_changed(self, index: int) -> None:
        self.log.debug("ui_page_changed index=%s", index)
        if index in MONITOR_PAGES:
            mode = MONITOR_PAGES[index]
            self.monitor_next_due[mode] = 0.0
            self._capture_tick()

    @staticmethod
    def _format_bytes(value: int) -> str:
        amount = float(max(0, value))
        for unit in ("B", "KiB", "MiB", "GiB"):
            if amount < 1024 or unit == "GiB":
                return f"{amount:.1f} {unit}".replace(".", ",")
            amount /= 1024
        return "0 B"

    def _select_client(self, index: int) -> None:
        self.active_client = index
        self.log.debug("ui_client_selected index=%s", index)
        self._render_overview()

    def _render_combat(self) -> None:
        monitors = list(self.snapshot.get("combat_monitors") or [])
        routed = any(item.get("client_key") for item in monitors)
        for mode, groups in self.combat_widgets.items():
            for index, widgets in enumerate(groups):
                key = f"client:{chr(97 + index)}"
                monitor = next(
                    (item for item in monitors if item.get("client_key") == key),
                    None,
                )
                if monitor is None and not routed and index < len(monitors):
                    monitor = monitors[index]
                character = str((monitor or {}).get("character_name") or "").strip()
                widgets["heading"].setText(
                    f"Cliente {chr(65 + index)} · {character or 'aguardando personagem'}"
                )
                if (
                    mode in self.monitor_client_enabled
                    and not self.monitor_client_enabled[mode][index]
                ):
                    self._render_nearby(widgets, [], mode, {})
                    widgets["target"].setText("Último alvo confirmado: —")
                    widgets["status"].setText(
                        f"Monitor desligado para o Cliente {chr(65 + index)}."
                    )
                    widgets["progress"].setValue(0)
                    for name in ("current_hp", "max_hp", "hp_percent", "dps_hp"):
                        if name in widgets:
                            widgets[name].setText("—")
                    continue
                if mode == "boss":
                    bosses = list((monitor or {}).get("bosses") or [])
                    self._render_bosses(widgets, bosses)
                    self.combat_page_layouts[mode]["cards"][index].setVisible(
                        bool(bosses)
                    )
                    widgets["status"].setText(
                        "Bosses próximos confirmados pelo stream em memória."
                        if bosses
                        else "Nenhum boss confirmado próximo."
                    )
                    continue
                nearby_key = "nearby_monsters" if mode == "pve" else "nearby_players"
                self._render_nearby(
                    widgets,
                    list((monitor or {}).get(nearby_key) or []),
                    mode,
                    dict((monitor or {}).get("player_counts") or {}),
                )
                target = dict((monitor or {}).get(mode) or {})
                if not target:
                    widgets["target"].setText("Último alvo confirmado: —")
                    widgets["status"].setText(
                        "Aguardando eventos confirmados de combate."
                        if monitor and monitor.get("local_combat_uid") is not None
                        else "Entre novamente no personagem uma vez para vincular o combate."
                    )
                    widgets["progress"].setValue(0)
                    for name in ("current_hp", "max_hp", "hp_percent", "dps_hp"):
                        if name in widgets:
                            widgets[name].setText("—")
                    continue
                label = "Último monstro confirmado" if mode == "pve" else "Último oponente confirmado"
                widgets["target"].setText(f"{label}: {target.get('name') or '—'}")
                current = target.get("current_hp")
                maximum = target.get("max_hp")
                percent = target.get("hp_percent")
                widgets["current_hp"].setText(self._format_count(current))
                widgets["max_hp"].setText(self._format_count(maximum))
                widgets["hp_percent"].setText(
                    f"{float(percent):.2f}%".replace(".", ",")
                    if isinstance(percent, (int, float)) else "—"
                )
                widgets["progress"].setValue(
                    max(0, min(1000, round(float(percent) * 10)))
                    if isinstance(percent, (int, float)) else 0
                )
                if "dps_hp" in widgets:
                    widgets["dps_hp"].setText(self._format_count(target.get("dps_hp")))
                age = float(target.get("age_seconds") or 0)
                direction = f" · {target.get('direction')}" if target.get("direction") else ""
                widgets["status"].setText(
                    f"Estado antigo · última confirmação há {age:.1f} s{direction}".replace(".", ",")
                    if target.get("stale")
                    else f"Atualizado há {age:.1f} s{direction}".replace(".", ",")
                )
        boss_page = self.combat_page_layouts.get("boss")
        if boss_page:
            has_boss = any(not card.isHidden() for card in boss_page["cards"])
            boss_page["empty"].setVisible(not has_boss)
        self._sync_combat_layout()
        self._update_boss_overlay(monitors)
        self._update_pvp_overlay(monitors)

    def _render_nearby(
        self,
        widgets: dict[str, Any],
        entities: list[dict[str, Any]],
        mode: str,
        counts: dict[str, Any],
    ) -> None:
        layout = widgets.get("nearby_layout")
        empty = widgets.get("nearby_empty")
        if layout is None or empty is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        empty.setVisible(not entities)
        if mode == "pvp" and entities:
            empty.setVisible(True)
            empty.setText(
                f"Aliados {counts.get('allies', 0)} · Inimigos {counts.get('enemies', 0)} "
                f"· Não classificados {counts.get('unknown', 0)}"
            )
        for entity in entities[:20]:
            row = QtWidgets.QFrame(objectName="secondaryMetricGroup")
            row.setMinimumHeight(64)
            horizontal = QtWidgets.QHBoxLayout(row)
            horizontal.setContentsMargins(14, 10, 14, 10)
            horizontal.setSpacing(10)
            if mode == "pvp":
                icon = QtWidgets.QLabel()
                biosuit = BIOSUITS.get(str(entity.get("biosuit_item_index") or ""), {})
                class_name = str(biosuit.get("class_name") or "")
                icon_path = ASSETS / "class-icons" / CLASS_ICON_FILES.get(class_name, "")
                if icon_path.is_file():
                    icon.setPixmap(
                        QtGui.QPixmap(str(icon_path)).scaled(
                            32,
                            32,
                            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                            QtCore.Qt.TransformationMode.SmoothTransformation,
                        )
                    )
                icon.setFixedSize(36, 36)
                horizontal.addWidget(icon)
            else:
                icon = QtWidgets.QLabel()
                icon.setFixedSize(42, 42)
                icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                icon_path = self._mob_icon_path(entity.get("npc_index"))
                if icon_path:
                    icon.setPixmap(
                        QtGui.QPixmap(str(icon_path)).scaled(
                            40,
                            40,
                            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                            QtCore.Qt.TransformationMode.SmoothTransformation,
                        )
                    )
                else:
                    icon.setText("NPC")
                    icon.setProperty("role", "muted")
                horizontal.addWidget(icon)
            name = str(entity.get("name") or "") or (
                f"NPC {entity.get('npc_index')}" if mode == "pve" else "Jogador confirmado"
            )
            level = f" · Nv. {entity['level']}" if entity.get("level") else ""
            horizontal.addWidget(_label(f"{name}{level}", "subtitle"), 1)
            percent = entity.get("hp_percent")
            value = (
                f"{self._format_count(entity.get('current_hp'))} HP"
                if mode == "pve" and entity.get("current_hp") is not None
                else f"{float(percent):.2f}%".replace(".", ",")
                if isinstance(percent, (int, float))
                else "HP —"
            )
            horizontal.addWidget(
                _label(value, "data")
            )
            layout.addWidget(row)

    @staticmethod
    def _mob_icon_path(npc_index: object) -> Path | None:
        if not isinstance(npc_index, (int, float)):
            return None
        stem = str(int(npc_index))
        return next(
            (
                path
                for suffix in (".webp", ".png", ".jpg", ".jpeg")
                if (path := MOB_ICONS / f"{stem}{suffix}").is_file()
            ),
            None,
        )

    def _update_pvp_overlay(self, monitors: list[dict[str, Any]]) -> None:
        if not self.pvp_overlay:
            return
        while self.pvp_overlay_rows.count():
            item = self.pvp_overlay_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        players: dict[str, dict[str, Any]] = {}
        hostile_ids: set[str] = set()
        for monitor in monitors:
            target = dict(monitor.get("pvp") or {})
            if target and not target.get("stale"):
                identity = str(
                    target.get("character_uid")
                    or target.get("uid")
                    or target.get("name")
                    or ""
                )
                if identity:
                    players[identity] = target
                    hostile_ids.add(identity)
            local_realm = (monitor.get("local") or {}).get("realm")
            for player in list(monitor.get("nearby_players") or []):
                identity = str(
                    player.get("character_uid")
                    or player.get("uid")
                    or player.get("name")
                    or ""
                )
                if identity:
                    players.setdefault(identity, player)
                    if (
                        local_realm is not None
                        and player.get("realm") is not None
                        and player.get("realm") != local_realm
                    ):
                        hostile_ids.add(identity)
        player_rows = list(players.items())
        self.pvp_overlay_summary.setText(
            f"Jogadores próximos: {len(player_rows)} · Hostis confirmados: {len(hostile_ids)}"
            if player_rows
            else "Nenhum jogador próximo confirmado"
        )
        for identity, player in player_rows[:8]:
            row = QtWidgets.QFrame(objectName="secondaryMetricGroup")
            layout = QtWidgets.QHBoxLayout(row)
            layout.setContentsMargins(8, 5, 8, 5)
            name = str(player.get("name") or "Jogador confirmado")
            level = f" · Nv. {player['level']}" if player.get("level") else ""
            status = " · Hostil" if identity in hostile_ids else " · Próximo"
            layout.addWidget(_label(f"{name}{level}{status}", "subtitle"), 1)
            percent = player.get("hp_percent")
            layout.addWidget(
                _label(
                    f"{float(percent):.1f}%".replace(".", ",")
                    if isinstance(percent, (int, float))
                    else "HP —",
                    "data",
                )
            )
            self.pvp_overlay_rows.addWidget(row)

    def _update_boss_overlay(self, monitors: list[dict[str, Any]]) -> None:
        if not self.boss_overlay:
            return
        boss = next(
            (
                item
                for monitor in monitors
                for item in list(monitor.get("bosses") or [])
            ),
            None,
        )
        if not boss:
            self.boss_overlay_name.setText("Aguardando boss próximo")
            self.boss_overlay_hp.setText("HP —")
            self.boss_overlay_progress.setValue(0)
            self.boss_overlay_rate.setText("DPS — · Tempo restante —")
            return
        current, maximum, percent = (
            boss.get("current_hp"),
            boss.get("max_hp"),
            boss.get("hp_percent"),
        )
        self.boss_overlay_name.setText(str(boss.get("name") or "Boss confirmado"))
        self.boss_overlay_hp.setText(
            f"HP {self._format_count(current)} / {self._format_count(maximum)}"
        )
        self.boss_overlay_progress.setValue(
            max(0, min(1000, round(float(percent) * 10)))
            if isinstance(percent, (int, float))
            else 0
        )
        eta = boss.get("eta_seconds")
        eta_text = (
            f"{int(eta) // 60:02d}:{int(eta) % 60:02d}"
            if isinstance(eta, (int, float))
            else "—"
        )
        self.boss_overlay_rate.setText(
            f"DPS {self._format_count(boss.get('dps_hp'))} · Tempo restante {eta_text}"
        )

    def _render_bosses(self, widgets: dict[str, Any], bosses: list[dict[str, Any]]) -> None:
        layout = widgets["boss_layout"]
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        widgets["boss_empty"].setVisible(not bosses)
        for boss in bosses:
            row = QtWidgets.QFrame(objectName="secondaryMetricGroup")
            column = QtWidgets.QVBoxLayout(row)
            column.setContentsMargins(12, 10, 12, 10)
            column.setSpacing(5)
            level = f" · Nv. {boss['level']}" if boss.get("level") else ""
            heading = QtWidgets.QHBoxLayout()
            icon_path = self._mob_icon_path(boss.get("npc_index"))
            if icon_path:
                icon = QtWidgets.QLabel()
                icon.setFixedSize(56, 56)
                icon.setPixmap(
                    QtGui.QPixmap(str(icon_path)).scaled(
                        54,
                        54,
                        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                        QtCore.Qt.TransformationMode.SmoothTransformation,
                    )
                )
                heading.addWidget(icon)
            heading.addWidget(
                _label(f"{boss.get('name') or 'Boss confirmado'}{level}", "subtitle"),
                1,
            )
            column.addLayout(heading)
            current, maximum, percent = boss.get("current_hp"), boss.get("max_hp"), boss.get("hp_percent")
            age = float(boss.get("age_seconds") or 0)
            hp = f"HP {self._format_count(current)} / {self._format_count(maximum)}"
            if isinstance(percent, (int, float)):
                hp += f" · {float(percent):.2f}%".replace(".", ",")
            state = "Estado antigo" if boss.get("stale") else "Atualizado"
            column.addWidget(_label(f"{hp} · {state} há {age:.1f} s".replace(".", ","), "muted"))
            eta = boss.get("eta_seconds")
            eta_text = (
                f"{int(eta) // 60:02d}:{int(eta) % 60:02d}"
                if isinstance(eta, (int, float))
                else "—"
            )
            column.addWidget(
                _label(
                    f"DPS estimado {self._format_count(boss.get('dps_hp'))} "
                    f"· Tempo restante {eta_text}",
                    "muted",
                )
            )
            for title, key in (
                ("DPS por jogador · 10 s", "top_damage_players"),
                ("DPS por guilda · 10 s", "top_damage_guilds"),
                ("DPS por grupo · 10 s", "top_damage_groups"),
            ):
                ranking = list(boss.get(key) or [])
                if ranking:
                    column.addWidget(_label(title, "subtitle"))
                    for position, item in enumerate(ranking[:10], 1):
                        ranking_row = QtWidgets.QHBoxLayout()
                        name = str(item.get("name") or "Não identificado")
                        guild = str(item.get("guild_name") or "").strip()
                        if guild:
                            name += f" · {guild}"
                        ranking_row.addWidget(_label(f"{position}. {name}", "muted"), 1)
                        ranking_row.addWidget(
                            _label(
                                f"{self._format_count(item.get('dps_hp'))}/s "
                                f"· dano {self._format_count(item.get('damage'))}",
                                "data",
                            )
                        )
                        column.addLayout(ranking_row)
            progress = QtWidgets.QProgressBar()
            progress.setRange(0, 1000)
            progress.setValue(max(0, min(1000, round(float(percent) * 10))) if isinstance(percent, (int, float)) else 0)
            progress.setTextVisible(False)
            column.addWidget(progress)
            layout.addWidget(row)

    @staticmethod
    def _format_count(value: object) -> str:
        if not isinstance(value, (int, float)):
            return "—"
        return f"{value:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".") \
            if isinstance(value, float) and not value.is_integer() else f"{int(value):,}".replace(",", ".")

    def _render_overview(self) -> None:
        snapshot = self.snapshot
        profiles = list(snapshot.get("profiles") or [])
        characters = list(snapshot.get("characters") or [])
        for index, button in enumerate(self.client_buttons):
            key = f"client:{chr(97 + index)}"
            profile = next((item for item in profiles if item.get("client_key") == key), None)
            if profile is None and not any(item.get("client_key") for item in profiles):
                profile = profiles[index] if index < len(profiles) else None
            manual = str(self.preferences.get(f"character{index + 1}") or "").strip()
            captured = str(profile.get("name") or "").strip() if profile else ""
            names = [value for value in (manual, captured) if value]
            names = list(dict.fromkeys(value.casefold() for value in names))
            display = " · ".join(
                next(value for value in (manual, captured) if value.casefold() == folded)
                for folded in names
            )
            button.setText(f"Cliente {chr(65 + index)} · {display or 'Definir nome'}")
        self._refresh_client_uid_buttons()

        key = f"client:{chr(97 + self.active_client)}"
        character, summary, historical_identity = self._overview_character(
            self.active_client
        )
        captured_name = str(character.get("name") or "").strip() if character else ""
        manual_name = str(self.preferences.get(f"character{self.active_client + 1}") or "").strip()
        name = (
            manual_name
            if manual_name and (not captured_name or captured_name.startswith("Personagem-"))
            else captured_name or manual_name or "Aguardando personagem"
        )
        stats = dict(snapshot.get("stats") or {})
        started, ended = stats.get("started_ns"), stats.get("ended_ns")
        if (
            isinstance(started, int)
            and self.capture_engine
            and self.capture_engine.active
        ):
            ended = max(int(ended or 0), time.time_ns())
        duration = max(0, int((ended - started) / 1_000_000_000)) if isinstance(started, int) and isinstance(ended, int) else 0
        hours = duration / 3600 if duration else 0
        gained = float(summary.get("exp_gained") or 0)
        credits = float(summary.get("credits") or 0)
        contribution = summary.get("contribution")
        rarity = dict(summary.get("loot_by_rarity") or {})

        self.overview_status.setText(
            f"Sessão {snapshot.get('session_id')} · {duration // 60} min · {stats.get('recognized', 0)} eventos reconhecidos"
            if snapshot.get("session_id") else "Nenhuma sessão disponível."
        )
        self.character_name.setText(name)
        details = [
            f"Nível {summary['level']}" if summary.get("level") is not None else "Nível —",
            str(summary.get("character_class") or "Classe —"),
            str(summary.get("biosuit_name") or "Biosuit —"),
        ]
        if historical_identity:
            details.append("Último estado conhecido")
        self.character_details.setText(" · ".join(details))
        self.rover_name.setText(str(summary.get("rover_name") or "Rover —"))
        percent = summary.get("exp_percent")
        self.exp_percent.setText(f"{percent:.2f}%".replace(".", ",") if isinstance(percent, (int, float)) else "—")
        self.exp_progress.setValue(round(float(percent) * 100) if isinstance(percent, (int, float)) else 0)
        self._set_character_icon(str(summary.get("character_class") or ""), int(summary.get("biosuit_grade") or 0))
        self._set_rover_icon(
            int(summary.get("rover_item_index") or 0),
            int(summary.get("rover_grade") or 0),
            str(summary.get("rover_name") or ""),
        )

        values = {
            "exp": summary.get("exp"), "exp_missing": summary.get("exp_missing"),
            "exp_percent": percent,
            "credits": credits, "contribution": contribution,
            "diamonds": summary.get("diamonds"), "exp_gained": gained,
            "exp_hour": gained / hours if hours else None,
            "exp_hour_percent": (float(summary.get("exp_gained_percent") or 0) / hours if hours else None),
            "credits_hour": credits / hours if hours else None,
            "contribution_hour": (float(contribution) / hours if hours and isinstance(contribution, (int, float)) else None),
            "kills": summary.get("kills"), "finalizations": summary.get("finalizations"),
            "loot": sum(int(rarity.get(item, 0)) for item in ("common", "uncommon", "rare", "epic")),
            "common": rarity.get("common"), "uncommon": rarity.get("uncommon"),
            "rare": rarity.get("rare"), "epic": rarity.get("epic"),
        }
        for metric, label in self.metric_labels.items():
            suffix = "%" if metric in {"exp_percent", "exp_hour_percent"} else ""
            label.setText(self._format_value(values.get(metric), suffix))

        subsessions = list(snapshot.get("subsessions") or [])
        active = next((item for item in subsessions if item.get("ended_ns") is None and item.get("client_key") == key), None)
        self.active_subsession.setText(
            f"{active.get('name')} · {active.get('map_name') or active.get('location') or 'local não informado'}"
            if active else "Nenhuma subsessão em andamento."
        )
        self._render_secondary_overview(1 - self.active_client, duration)

    def _render_secondary_overview(self, index: int, duration: int) -> None:
        if not hasattr(self, "overview_secondary"):
            return
        key = f"client:{chr(97 + index)}"
        character, summary, historical_identity = self._overview_character(index)
        captured = str(character.get("name") or "").strip() if character else ""
        manual = str(self.preferences.get(f"character{index + 1}") or "").strip()
        name = (
            manual
            if manual and (not captured or captured.startswith("Personagem-"))
            else captured or manual or "Aguardando personagem"
        )
        self.secondary_character_name.setText(
            f"Cliente {chr(65 + index)} · {name}"
        )
        details = [
            f"Nível {summary['level']}" if summary.get("level") is not None else "Nível —",
            str(summary.get("character_class") or "Classe —"),
            str(summary.get("biosuit_name") or "Biosuit —"),
        ]
        if historical_identity:
            details.append("Último estado conhecido")
        self.secondary_character_details.setText(" · ".join(details))
        self.secondary_rover_name.setText(str(summary.get("rover_name") or "Rover —"))
        percent = summary.get("exp_percent")
        self.secondary_exp_progress.setValue(
            round(float(percent) * 100)
            if isinstance(percent, (int, float)) else 0
        )
        self._set_character_icon(
            str(summary.get("character_class") or ""),
            int(summary.get("biosuit_grade") or 0),
            self.secondary_character_icon,
        )
        self._set_rover_icon(
            int(summary.get("rover_item_index") or 0),
            int(summary.get("rover_grade") or 0),
            str(summary.get("rover_name") or ""),
            self.secondary_rover_icon,
        )
        hours = duration / 3600 if duration else 0
        gained = float(summary.get("exp_gained") or 0)
        credits = float(summary.get("credits") or 0)
        contribution = summary.get("contribution")
        rarity = dict(summary.get("loot_by_rarity") or {})
        values = {
            "exp": summary.get("exp"),
            "exp_missing": summary.get("exp_missing"),
            "exp_percent": summary.get("exp_percent"),
            "exp_gained": gained,
            "exp_hour": gained / hours if hours else None,
            "exp_hour_percent": float(summary.get("exp_gained_percent") or 0) / hours if hours else None,
            "credits": credits,
            "credits_hour": credits / hours if hours else None,
            "contribution": contribution,
            "contribution_hour": float(contribution) / hours if hours and isinstance(contribution, (int, float)) else None,
            "diamonds": summary.get("diamonds"),
            "kills": summary.get("kills"),
            "finalizations": summary.get("finalizations"),
            "loot": sum(int(rarity.get(item, 0)) for item in ("common", "uncommon", "rare", "epic")),
            "common": rarity.get("common"),
            "uncommon": rarity.get("uncommon"),
            "rare": rarity.get("rare"),
            "epic": rarity.get("epic"),
        }
        for metric, label in self.secondary_metric_labels.items():
            label.setText(self._format_value(
                values.get(metric), "%" if metric in {"exp_percent", "exp_hour_percent"} else ""
            ))
        active = next((
            item for item in self.snapshot.get("subsessions") or []
            if item.get("ended_ns") is None and item.get("client_key") == key
        ), None)
        self.secondary_active_subsession.setText(
            f"{active.get('name')} · {active.get('map_name') or active.get('location') or 'local não informado'}"
            if active else "Nenhuma subsessão em andamento."
        )

    def _set_character_icon(
        self, class_name: str, grade: int, widget: QtWidgets.QLabel | None = None
    ) -> None:
        widget = widget or self.character_icon
        filename = CLASS_ICON_FILES.get(class_name)
        if not filename:
            widget.setPixmap(QtGui.QPixmap())
            widget.setText(class_name or "—")
            return
        image = QtGui.QImage(str(ASSETS / "class-icons" / filename)).convertToFormat(QtGui.QImage.Format.Format_ARGB32)
        color = RARITY_COLORS.get(grade)
        if color:
            painter = QtGui.QPainter(image)
            painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(image.rect(), QtGui.QColor(color))
            painter.end()
        pixmap = QtGui.QPixmap.fromImage(image).scaled(62, 62, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
        widget.setText("")
        widget.setPixmap(pixmap)

    def _set_rover_icon(
        self,
        item_index: int,
        grade: int,
        name: str,
        widget: QtWidgets.QLabel | None = None,
    ) -> None:
        widget = widget or self.rover_icon
        pixmap = QtGui.QPixmap(
            str(ASSETS / "rover-icons" / f"loadout-{item_index}.webp")
        )
        if not pixmap.isNull():
            widget.setText("")
            widget.setPixmap(pixmap.scaled(
                widget.width() - 4,
                widget.height() - 4,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            ))
            widget.setToolTip(name or f"Rover {item_index}")
            return
        color = QtGui.QColor(RARITY_COLORS.get(grade, "#6b7470"))
        image = QtGui.QImage(64, 64, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtGui.QPen(color, 4))
        painter.drawRoundedRect(QtCore.QRectF(8, 14, 48, 30), 8, 8)
        painter.setBrush(color)
        painter.drawEllipse(QtCore.QRectF(13, 41, 12, 12))
        painter.drawEllipse(QtCore.QRectF(39, 41, 12, 12))
        painter.end()
        widget.setText("")
        widget.setPixmap(QtGui.QPixmap.fromImage(image))
        widget.setToolTip(name or "Rover não identificado")

    @staticmethod
    def _format_value(value: object, suffix: str = "") -> str:
        if not isinstance(value, (int, float)):
            return "—"
        number = f"{value:,.2f}" if suffix else f"{value:,.0f}"
        return number.replace(",", "_").replace(".", ",").replace("_", ".") + suffix

    def _build_footer(self) -> QtWidgets.QWidget:
        footer = QtWidgets.QWidget(objectName="statusbar")
        footer.setFixedHeight(42)
        row = QtWidgets.QHBoxLayout(footer)
        row.setContentsMargins(18, 0, 18, 0)
        row.addStretch(1)
        row.addWidget(_label(f"v{VERSION}", "muted"))
        return footer


STYLE = """
QWidget { color: #F4F2EB; font-family: 'Saira'; font-size: 14px; }
QMainWindow { background: #070909; }
#topbar, #statusbar { background: #0A1115; border-bottom: 1px solid #26333A; }
#statusbar { border-top: 1px solid #26333A; border-bottom: none; }
#sidebar { background: #08151C; border-right: 1px solid #26333A; }
#workspace { background: #07131A; }
QLabel[role='title'] { font-family: 'Saira SemiCondensed'; font-size: 30px; font-weight: 700; }
QLabel[role='subtitle'] { font-size: 18px; font-weight: 600; }
QLabel[role='hero'] { font-family: 'Saira SemiCondensed'; font-size: 24px; font-weight: 700; }
QLabel[role='muted'] { color: #A9B0B2; }
QLabel[role='info'] { color: #38BDF8; }
QLabel[role='data'] { color: #38BDF8; font-size: 20px; font-weight: 600; }
QLabel[role='ok'] { color: #58C96B; }
QLabel[role='warning'] { color: #F0B84A; }
QLabel[role='step'] { background: #3A301B; color: #F6BE3B; border: 1px solid #D4A64D; border-radius: 5px; font-weight: 700; }
QLabel[role='brand'] { color: #D4A64D; font-weight: 700; letter-spacing: 4px; }
QPushButton { background: #0A1115; border: 1px solid #314149; border-radius: 5px; padding: 8px 14px; }
QPushButton:hover { border-color: #D4A64D; color: #FFFFFF; }
QPushButton:focus { border: 2px solid #38BDF8; }
QPushButton:checked { background: #3A301B; border-color: #D4A64D; color: #F6BE3B; }
QPushButton:disabled { color: #6D7578; border-color: #26333A; background: #0A0E10; }
QTabBar { background: transparent; }
QTabBar::tab {
    background: #0A1115;
    color: #F4F2EB;
    border: 1px solid #314149;
    border-bottom-color: #D4A64D;
    padding: 9px 22px;
    min-width: 96px;
}
QTabBar::tab:selected {
    background: #3A301B;
    color: #F6BE3B;
    border-color: #D4A64D;
}
QTabBar::tab:hover { color: #FFFFFF; border-color: #D4A64D; }
QMessageBox { background: #081820; }
QMessageBox QLabel { color: #F4F2EB; background: transparent; }
QMessageBox QPushButton { color: #F4F2EB; min-width: 90px; }
QMenu { background: #081820; color: #F4F2EB; border: 1px solid #314149; padding: 4px; }
QMenu::item { background: transparent; padding: 7px 24px 7px 28px; }
QMenu::item:selected { background: #3A301B; color: #F6BE3B; }
QMenu::item:disabled { color: #6D7578; }
QMenu::separator { background: #26333A; height: 1px; margin: 4px 8px; }
#sidebar QPushButton { text-align: left; border-color: transparent; padding-left: 18px; }
#sidebar QPushButton:checked { border-left: 3px solid #F6BE3B; }
QPushButton[client='true'] { min-width: 210px; }
QLineEdit, QComboBox, QSpinBox, QListWidget, QTableWidget {
    background: #0A1115;
    color: #F4F2EB;
    border: 1px solid #314149;
    border-radius: 5px;
    padding: 6px;
    selection-background-color: #3A301B;
    selection-color: #F6BE3B;
}
QLineEdit:disabled { background: #0A0E10; color: #6D7578; }
QComboBox QAbstractItemView { background: #0A1115; color: #F4F2EB; selection-background-color: #3A301B; }
QComboBox::drop-down, QSpinBox::up-button, QSpinBox::down-button { border: none; }
QTableWidget { gridline-color: #26333A; border-radius: 0; padding: 0; }
QHeaderView { background: #0D1A20; }
QHeaderView::section { background: #0D1A20; color: #A9B0B2; border: none; border-right: 1px solid #26333A; border-bottom: 1px solid #26333A; padding: 7px; }
QTableCornerButton::section { background: #0D1A20; border: none; border-bottom: 1px solid #26333A; }
QCheckBox { spacing: 7px; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #52626A; border-radius: 3px; background: #0A1115; }
QCheckBox::indicator:checked { background: #D4A64D; border-color: #F6BE3B; }
#emptyCard { background: #081820; border: 1px solid #26333A; border-radius: 8px; }
#panel, #metricGroup, #secondaryMetricGroup { background: #081820; border: 1px solid #26333A; border-radius: 8px; }
#metricDivider { background: #26333A; }
#accentPanel { background: #081820; border: 1px solid #D4A64D; border-radius: 8px; }
#characterIcon, #roverIcon { background: #0A1115; border: 1px solid #314149; border-radius: 8px; }
QProgressBar { background: #0A1115; border: 1px solid #26333A; border-radius: 5px; height: 10px; }
QProgressBar::chunk { background: #38BDF8; border-radius: 4px; }
QScrollArea, QScrollArea QWidget#qt_scrollarea_viewport, #scrollContent { background: #07131A; border: none; }
QScrollBar:vertical { background: #07131A; width: 10px; }
QScrollBar::handle:vertical { background: #314149; border-radius: 5px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def create_application(argv: list[str] | None = None) -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(argv or ["rf-qol-qt-preview"])
    if not hasattr(app, "_rfnext_translator"):
        translator = QtCore.QTranslator(app)
        translator.load(
            "qtbase_pt_BR",
            QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.LibraryPath.TranslationsPath),
        )
        app.installTranslator(translator)
        app._rfnext_translator = translator
    _load_fonts()
    app.setStyleSheet(STYLE)
    return app


def _notify_running_instance(name: str = INSTANCE_SERVER_NAME) -> bool:
    socket = QtNetwork.QLocalSocket()
    socket.connectToServer(name, QtCore.QIODevice.OpenModeFlag.WriteOnly)
    if not socket.waitForConnected(350):
        return False
    socket.write(b"show\n")
    socket.waitForBytesWritten(350)
    socket.disconnectFromServer()
    return True


def _claim_instance_server(
    app: QtWidgets.QApplication,
    name: str = INSTANCE_SERVER_NAME,
) -> QtNetwork.QLocalServer | None:
    lock_root = QtCore.QStandardPaths.writableLocation(
        QtCore.QStandardPaths.StandardLocation.TempLocation
    )
    lock = QtCore.QLockFile(str(Path(lock_root) / f"{name}.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        _notify_running_instance(name)
        return None
    server = QtNetwork.QLocalServer(app)
    QtNetwork.QLocalServer.removeServer(name)
    if not server.listen(name):
        lock.unlock()
        raise RuntimeError("Não foi possível reservar a instância única do RF QOL.")
    app._rfnext_instance_lock = lock
    return server


def _activate_from_instance_request(
    server: QtNetwork.QLocalServer,
    window: MainWindow,
) -> None:
    requested = False
    while server.hasPendingConnections():
        connection = server.nextPendingConnection()
        if connection:
            connection.waitForReadyRead(50)
            requested = requested or bytes(connection.readAll()).strip() == b"show"
            connection.disconnectFromServer()
            connection.deleteLater()
    if requested:
        window._show_from_tray()


def main() -> int:
    self_test = "--self-test" in sys.argv
    if self_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application(sys.argv)
    instance_server = None if self_test else _claim_instance_server(app)
    if not self_test and instance_server is None:
        return 0
    window = MainWindow(load_data=not self_test)
    if instance_server is not None:
        instance_server.newConnection.connect(
            lambda: _activate_from_instance_request(instance_server, window)
        )
        app._rfnext_instance_server = instance_server
    window.show()
    app.processEvents()
    if self_test:
        passed = (
            window.minimumSize() == QtCore.QSize(1180, 664)
            and window.page_stack.count() == len(PAGES)
            and (ROOT / "core" / "rfnext_frame_decode.py").is_file()
            and (ROOT / "core" / "collection_requirements.csv").is_file()
            and (ROOT / "core" / "job1_pending_layouts.json").is_file()
            and (ROOT / "core" / "job1_all_opcodes.csv").is_file()
            and MACHINE_STATE_DIR != STATE_DIR
            and UPDATES_DIR.parent == MACHINE_STATE_DIR
        )
        window.capture_timer.stop()
        window.exit_requested = True
        window.close()
        app.quit()
        if passed:
            LOG_PATH.with_name("self-test.ok").write_text("passed\n", encoding="ascii")
        return 0 if passed else 1
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

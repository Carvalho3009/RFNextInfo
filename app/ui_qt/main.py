from __future__ import annotations

import os
import sys
import ctypes
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

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
    DEFAULT_PORTS,
    LOG_PATH,
    MACHINE_STATE_DIR,
    STATE_DIR,
    VERSION,
    _recycle,
)
from app.site_profile import SiteProfileClient
from app.support_log import configure as configure_log, recent_lines
from app.updater import download_verified, latest
from app.ui_qt.operations import (
    CaptureEngine,
    ExportEngine,
    GlobalHotkeys,
    SiteUploadEngine,
)
from core.store import CaptureStore


PAGES = (
    ("Visão geral", "Resumo dos clientes e da sessão atual."),
    ("Envios", "Envios dos dados já lidos pela captura contínua."),
    ("Subsessões", "Histórico e criação de subsessões."),
    ("Configurações", "Preferências do programa e do Profile."),
    ("Tutorial", "Primeiros passos e atalhos."),
)

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
ASSETS = ROOT / "assets"

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


def _load_fonts() -> None:
    for name in ("Saira.ttf", "SairaSemiCondensed-Bold.ttf"):
        QtGui.QFontDatabase.addApplicationFont(str(ASSETS / name))


def _label(text: str, role: str = "") -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    if role:
        label.setProperty("role", role)
    return label


class MainWindow(QtWidgets.QMainWindow):
    data_loaded = QtCore.Signal(object)
    data_failed = QtCore.Signal(str)
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
        self.database_path = Path(database_path)
        self.preferences_path = Path(preferences_path)
        self.active_client = 0
        self.snapshot: dict[str, object] = {}
        self.preferences: dict[str, object] = {}
        self.selected_subsessions: set[str] = set()
        self.subsession_page = 1
        self.editing_subsession_id: str | None = None
        self.capture_engine: CaptureEngine | None = None
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
        self.pending_export_cleanup = False
        self.snapshot_reader = ReadOnlySnapshotReader(self.database_path)
        try:
            self.log_path = LOG_PATH
            self.log = configure_log(self.log_path, VERSION)
        except OSError:
            self.log_path = STATE_DIR / "logs" / "rfnext-info.log"
            self.log = configure_log(self.log_path, VERSION)
        self.license_client = LicenseClient(
            STATE_DIR,
            version=VERSION,
            legacy_paths=(
                MACHINE_STATE_DIR / "license.dat",
                MACHINE_STATE_DIR / "license.json",
            ),
        )
        self.site_profile = SiteProfileClient(STATE_DIR, version=VERSION)
        self.site_uploader = SiteUploadEngine(
            self.database_path, self.site_profile, self.license_client
        )
        self.export_engine = ExportEngine(self.database_path, self.license_client)
        self.data_load_running = False
        self.data_load_pending = False
        self.setObjectName("mainWindow")
        self.setWindowTitle(f"RF NEXT QOL — {VERSION}")
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
        self.capture_operation_done.connect(self._capture_operation_finished)
        self.site_operation_done.connect(self._site_operation_finished)
        self.global_hotkey_triggered.connect(self._global_hotkey_action)
        self.update_progress_changed.connect(self._update_progress)
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
        self._sync_overview_layout()

    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.WindowStateChange:
            QtCore.QTimer.singleShot(0, self._sync_overview_layout)

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

    def _build_tray(self, icon: QtGui.QIcon) -> QtWidgets.QSystemTrayIcon | None:
        if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QtWidgets.QSystemTrayIcon(icon, self)
        tray.setToolTip(f"RF NEXT QOL — {VERSION}")
        menu = QtWidgets.QMenu()
        show_action = menu.addAction("Abrir RF NEXT QOL")
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
        tray.activated.connect(
            lambda reason: self._show_from_tray()
            if reason == QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick
            else None
        )
        tray.show()
        return tray

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _exit_application(self) -> None:
        self.exit_requested = True
        self.close()

    def _build_topbar(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QWidget(objectName="topbar")
        bar.setFixedHeight(56)
        row = QtWidgets.QHBoxLayout(bar)
        row.setContentsMargins(18, 0, 18, 0)
        row.setSpacing(18)
        for text, tone in (
            ("Licença — carregando", "muted"),
            ("Captura — não conectada", "info"),
            ("Última leitura: —", "muted"),
            ("Próx. atualização: —", "muted"),
            ("Armazenado: —", "muted"),
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
            row.addWidget(label)
        row.addStretch(1)
        for index, text in enumerate(("Iniciar  Ctrl+F8", "Pausar", "Encerrar  Ctrl+F9")):
            button = QtWidgets.QPushButton(text)
            button.setEnabled(False)
            if index == 0:
                self.start_button = button
                button.clicked.connect(self._start_capture)
            elif index == 1:
                self.pause_button = button
                button.clicked.connect(self._pause_capture)
            else:
                self.stop_button = button
                button.clicked.connect(self._stop_capture)
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
            if index == 0:
                page = self._build_overview_page()
            elif index == 1:
                page = self._build_sends_page()
            elif index == 2:
                page = self._build_subsessions_page()
            elif index == 3:
                page = self._build_settings_page()
            elif index == 4:
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
        self.subsession_map = QtWidgets.QComboBox()
        self.subsession_map.currentTextChanged.connect(self._subsession_map_changed)
        self.subsession_spot = QtWidgets.QComboBox()
        self.subsession_spot.currentTextChanged.connect(self._subsession_spot_changed)
        self.subsession_mobs = QtWidgets.QListWidget()
        self.subsession_mobs.setMinimumHeight(300)
        self.subsession_select_all = QtWidgets.QCheckBox("Selecionar todos os mobs")
        self.subsession_select_all.toggled.connect(self._toggle_all_mobs)
        self.subsession_other_mob = QtWidgets.QLineEdit()
        self.subsession_other_mob.setPlaceholderText("Nome de mob adicional")
        levels = QtWidgets.QWidget()
        levels_layout = QtWidgets.QHBoxLayout(levels)
        levels_layout.setContentsMargins(0, 0, 0, 0)
        self.subsession_level_from = QtWidgets.QSpinBox(); self.subsession_level_from.setRange(0, 999)
        self.subsession_level_to = QtWidgets.QSpinBox(); self.subsession_level_to.setRange(0, 999)
        levels_layout.addWidget(self.subsession_level_from); levels_layout.addWidget(_label("até", "muted")); levels_layout.addWidget(self.subsession_level_to)
        self.subsession_duration = QtWidgets.QSpinBox(); self.subsession_duration.setRange(0, 1440); self.subsession_duration.setSuffix(" min")
        self.subsession_name = QtWidgets.QLineEdit(); self.subsession_name.setPlaceholderText("Observação ou nome")
        self.auto_subsession = QtWidgets.QCheckBox("Criar a próxima automaticamente")
        self.auto_subsession_minutes = QtWidgets.QSpinBox(); self.auto_subsession_minutes.setRange(5, 240); self.auto_subsession_minutes.setSuffix(" min")
        automatic = QtWidgets.QWidget(); automatic_layout = QtWidgets.QHBoxLayout(automatic); automatic_layout.setContentsMargins(0,0,0,0); automatic_layout.addWidget(self.auto_subsession); automatic_layout.addWidget(self.auto_subsession_minutes); automatic_layout.addStretch(1)
        for label_text, widget in (
            ("Cliente", self.subsession_client), ("Mapa", self.subsession_map),
            ("Spot", self.subsession_spot), ("Mobs", self.subsession_mobs),
            ("", self.subsession_select_all),
            ("Mob extra", self.subsession_other_mob), ("Nível dos mobs", levels),
            ("Duração (0 = manual)", self.subsession_duration),
            ("Observação", self.subsession_name), ("Automática", automatic),
        ):
            layout.addRow(label_text, widget)
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
        grid.addWidget(shortcuts, 2, 0)

        behavior = QtWidgets.QFrame(objectName="panel")
        behavior_layout = QtWidgets.QVBoxLayout(behavior)
        behavior_layout.addWidget(_label("Comportamento", "subtitle"))
        self.setting_minimize = QtWidgets.QCheckBox("Minimizar para a bandeja")
        self.setting_auto_export = QtWidgets.QCheckBox("Exportar automaticamente ao parar")
        self.setting_delete_export = QtWidgets.QCheckBox("Excluir após exportar")
        behavior_layout.addWidget(self.setting_minimize); behavior_layout.addWidget(self.setting_auto_export); behavior_layout.addWidget(self.setting_delete_export); behavior_layout.addStretch(1)
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
        self.license_key.setPlaceholderText("KRV-…")
        license_layout.addWidget(self.license_key)
        self.activate_license_button = QtWidgets.QPushButton("Ativar licença")
        self.activate_license_button.clicked.connect(self._activate_license)
        license_layout.addWidget(self.activate_license_button)
        license_layout.addStretch(1)
        grid.addWidget(license_panel, 0, 0)

        support = QtWidgets.QFrame(objectName="panel")
        support_layout = QtWidgets.QVBoxLayout(support)
        support_layout.addWidget(_label("Suporte e atualização", "subtitle"))
        support_layout.addWidget(_label("Discord Carvalho · carvalho@tuta.com", "muted"))
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
            preferences.get("capture_directory") or Path.home() / "Documents" / "Capturas"
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
            combo.setCurrentText(str(shortcuts.get(mode) or {"character": "F1", "market": "F2", "codex": "F3", "memory_chips": "F4"}[mode]))
        self.setting_minimize.setChecked(bool(preferences.get("minimize_to_tray", False)))
        self.setting_auto_export.setChecked(bool(preferences.get("auto_export", False)))
        self.setting_delete_export.setChecked(bool(preferences.get("delete_after_export", False)))
        self.subsession_duration.setValue(self._bounded(preferences.get("subsession_duration_minutes"), 0, 1440, 30))
        self.auto_subsession.setChecked(bool(preferences.get("auto_subsession", False)))
        self.auto_subsession_minutes.setValue(self._bounded(preferences.get("auto_subsession_minutes"), 5, 240, 30))
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
            QtWidgets.QMessageBox.warning(self, "Configurações", "Cada envio precisa usar uma tecla de atalho diferente.")
            return
        self.preferences = save_preferences({
            "capture_directory": str(capture_directory),
            "decode_interval_seconds": self.setting_decode_interval.value(),
            "item_name_language": self.setting_language.currentData(),
            "profile": self.setting_profile.text().strip(),
            "shortcuts": shortcuts,
            "minimize_to_tray": self.setting_minimize.isChecked(),
            "auto_export": self.setting_auto_export.isChecked(),
            "delete_after_export": self.setting_delete_export.isChecked(),
            "channel": self.update_channel.currentData(),
        }, self.preferences_path)
        if not self.capture_engine or not self.capture_engine.current_session:
            self.capture_engine = None
            self._ensure_capture_engine()
        self._refresh_farm_catalog()
        self._render_overview()
        self._sync_global_hotkeys(shortcuts)
        self.setting_storage.setText(f"Capturas: {capture_directory}\nPreferências salvas para a interface estável e para o preview.")
        QtWidgets.QMessageBox.information(self, "Configurações", "Configurações salvas.")

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
        if engine and engine.current_session and not self.capture_busy:
            try:
                engine.stop()
            except Exception:
                self.log.exception("capture_stop_on_close_failed")
        self.log.info("app_closed")
        super().closeEvent(event)

    @QtCore.Slot(str)
    def _global_hotkey_action(self, action: str) -> None:
        if action == "start":
            self._start_capture()
        elif action == "stop":
            self._stop_capture()
        elif action in {"character", "market", "codex", "memory_chips"}:
            self._send_mode(action, -1 if action == "market" else self.active_client)

    def _sync_global_hotkeys(self, shortcuts: dict[str, str] | None = None) -> None:
        shortcuts = shortcuts or {
            mode: combo.currentText()
            for mode, combo in self.setting_shortcuts.items()
        }
        if getattr(self.global_hotkeys, "shortcuts", None) == shortcuts:
            return
        self.global_hotkeys.stop()
        self.global_hotkeys.start(shortcuts)

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
        mobs = self.farm_catalog.get(self.subsession_map.currentText(), {}).get(spot_name, {})
        self.subsession_mobs.clear()
        for mob, levels in mobs.items():
            level_text = (
                str(levels[0]) if len(levels) == 1
                else f"{levels[0]}–{levels[-1]}"
            )
            item = QtWidgets.QListWidgetItem(f"{mob} · Nv. {level_text}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, mob)
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Unchecked)
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

    def _client_uid_for(self, index: int) -> str | None:
        key = f"client:{chr(97 + index)}"
        profiles = list(self.snapshot.get("profiles") or [])
        profile = next((item for item in profiles if item.get("client_key") == key), None)
        if profile is None and not any(item.get("client_key") for item in profiles):
            profile = profiles[index] if index < len(profiles) else None
        return str(profile.get("uid")) if profile and profile.get("uid") else None

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
        for row in range(self.subsession_mobs.count()):
            mob = self.subsession_mobs.item(row)
            mob_name = str(mob.data(QtCore.Qt.ItemDataRole.UserRole) or mob.text())
            mob.setCheckState(QtCore.Qt.CheckState.Checked if mob_name in chosen else QtCore.Qt.CheckState.Unchecked)
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
                if now - int(active["started_ns"]) < limit * 60 * 1_000_000_000:
                    continue
                store.end_subsession(str(active["id"]), now)
                changed = True
                if automatic:
                    store.start_subsession(
                        f"{session_id}-sub-{now}-{active.get('character_uid') or 'geral'}",
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
                        started_ns=now,
                    )
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
            return
        self.site_busy = True
        self._set_send_controls()

        def worker() -> None:
            try:
                self.site_operation_done.emit(name, callback(), None)
            except Exception as error:
                self.log.exception("background_operation_failed name=%s", name)
                self.site_operation_done.emit(name, None, error)

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
            str(Path.home() / "Downloads" / f"RFNextInfo-log-{datetime.now():%Y%m%d-%H%M%S}.txt"),
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
        public_key = self.license_client.state.get("public_key")
        if not public_key:
            self.update_button.setEnabled(True)
            QtWidgets.QMessageBox.warning(
                self, "Atualização", "Ative a licença antes de atualizar."
            )
            return
        self._run_site_operation(
            "update:download",
            lambda: download_verified(
                release,
                public_key,
                lambda phase, downloaded, total: self.update_progress_changed.emit(
                    phase, downloaded, total
                ),
            ),
        )

    def _launch_update(self, installer: Path) -> None:
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
            "O RF NEXT QOL será fechado e o instalador será aberto. Continuar?",
        ) != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        if getattr(sys, "frozen", False):
            rollback = STATE_DIR / "rollback" / "RFNextInfo"
            shutil.rmtree(rollback, ignore_errors=True)
            shutil.copytree(
                Path(sys.executable).parent,
                rollback,
                ignore=shutil.ignore_patterns("Uninstall.exe"),
            )
        escaped = str(installer).replace("'", "''")
        script = (
            f"Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue; "
            f"Start-Process -FilePath '{escaped}'"
        )
        subprocess.Popen(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive",
                "-WindowStyle", "Hidden", "-Command", script,
            ],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.exit_requested = True
        self.close()

    def _rollback(self) -> None:
        previous = STATE_DIR / "rollback" / "RFNextInfo" / "RFNextInfo.exe"
        if not previous.is_file():
            QtWidgets.QMessageBox.information(
                self, "Versão anterior", "Ainda não existe uma versão anterior preservada."
            )
            return
        os.startfile(previous)

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
            snapshot = ReadOnlySnapshotReader(self.database_path).load(language)
            return self.site_uploader.send_mode(mode, target, snapshot, language)

        self._run_site_operation(
            f"send:{mode}:{target}",
            read_and_send,
        )

    def _send_selected_subsessions(self) -> None:
        identifiers = sorted(self.selected_subsessions)
        if not identifiers:
            return
        self.send_selected_status.setText("Enviando subsessões selecionadas…")
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
            if error is not None:
                self.send_selected_status.setText("Falha no envio")
                QtWidgets.QMessageBox.warning(self, "Subsessões", str(error))
            else:
                data = dict(result or {})
                failures = list(data.get("failures") or [])
                self.send_selected_status.setText(
                    f"{data.get('sent', 0)} enviada(s)"
                    + (f" · {len(failures)} falha(s)" if failures else "")
                )
                self._load_readonly_data()
        elif name in {"export", "auto_export", "export_upload"}:
            if error is not None:
                self.update_status.setText(f"Exportação falhou: {error}")
                QtWidgets.QMessageBox.warning(self, "Exportação", str(error))
            else:
                self._finish_export(
                    dict(result or {}), uploaded=name == "export_upload"
                )
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
            return
        self.data_load_running = True

        def worker() -> None:
            try:
                preferences = load_preferences(self.preferences_path)
                language = str(preferences.get("item_name_language") or "pt")
                capture_directory = Path(
                    preferences.get("capture_directory")
                    or Path.home() / "Documents" / "Capturas"
                )
                self.data_loaded.emit({
                    "preferences": preferences,
                    "license": load_license_status(),
                    "snapshot": self.snapshot_reader.load(language),
                    "storage_bytes": self._stored_capture_bytes(capture_directory),
                })
            except Exception as error:
                self.data_failed.emit(f"{type(error).__name__}: {error}")

        threading.Thread(target=worker, daemon=True).start()

    @QtCore.Slot(object)
    def _apply_readonly_data(self, payload: dict[str, object]) -> None:
        self.preferences = dict(payload.get("preferences") or {})
        self.snapshot = dict(payload.get("snapshot") or {})
        self._apply_license(dict(payload.get("license") or {}))
        self._load_settings_fields()
        self._sync_global_hotkeys()
        self._refresh_farm_catalog()
        self._render_overview()
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
        self.overview_status.setText(f"Não foi possível ler a sessão: {message}")
        self.license_title.setText("Não foi possível ler a licença local")
        self._finish_data_load()

    def _finish_data_load(self) -> None:
        self.data_load_running = False
        if self.data_load_pending:
            self.data_load_pending = False
            QtCore.QTimer.singleShot(0, self._load_readonly_data)

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
                or Path.home() / "Documents" / "Capturas"
            )
            self.capture_engine = CaptureEngine(
                directory,
                self.database_path,
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
        if self._tray:
            self.tray_start_action.setEnabled(self.start_button.isEnabled())
            self.tray_pause_action.setEnabled(self.pause_button.isEnabled())
            self.tray_stop_action.setEnabled(self.stop_button.isEnabled())

    def _run_capture_operation(self, name: str, callback) -> None:
        if self.capture_busy:
            return
        self.capture_busy = True
        self._set_capture_controls()

        def worker() -> None:
            try:
                self.capture_operation_done.emit(name, callback(), None)
            except Exception as error:
                self.log.exception("capture_operation_failed name=%s", name)
                self.capture_operation_done.emit(name, None, error)

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
            or Path.home() / "Documents" / "Capturas"
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

    @QtCore.Slot(str, object, object)
    def _capture_operation_finished(
        self, name: str, result: object, error: object
    ) -> None:
        self.capture_busy = False
        if error is not None:
            self.top_capture.setText(f"Captura — falha: {error}")
            if name == "read":
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
        engine = self._ensure_capture_engine()
        if name == "start":
            self.last_capture_session = str(data.get("session_id") or "")
            self.preferences = save_preferences({
                "session_counter": data.get("session_counter"),
                "last_session": data.get("session_id"),
                "capture_pending": True,
                "capture_prefix": data.get("capture_prefix"),
                "capture_ports": data.get("capture_ports"),
                "capture_client_ports": data.get("capture_client_ports"),
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
        elif name == "pause":
            self.top_capture.setText("Captura — pausada")
            self._load_readonly_data()
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
            self._load_readonly_data()
            self.top_next_read.setText("Próx. leitura: —")
            if not failures and self.setting_auto_export.isChecked():
                target = Path(self.setting_capture_directory.text()) / "Exportados"
                self._prepare_export_identity(self.last_capture_session)
                QtCore.QTimer.singleShot(
                    0,
                    lambda session=self.last_capture_session, destination=target:
                    self._run_export("auto_export", session, destination),
                )
        self._set_capture_controls()
        pending, self.pending_capture_action = self.pending_capture_action, None
        if pending == "pause":
            QtCore.QTimer.singleShot(0, self._pause_capture)
        elif pending == "stop":
            QtCore.QTimer.singleShot(0, self._stop_capture)

    def _capture_tick(self) -> None:
        engine = self.capture_engine
        if not engine:
            return
        now = time.monotonic()
        if self.license_active and now - self.last_license_refresh_at >= 60:
            self._refresh_license_online()
        if engine.active and now - self.last_heartbeat_at >= 15:
            try:
                engine.heartbeat()
                self.last_heartbeat_at = now
            except OSError as error:
                self.top_capture.setText(f"Captura — heartbeat falhou: {error}")
        if engine.active:
            if now - self.last_storage_scan_at >= 5:
                self.last_storage_scan_at = now
                directory = Path(
                    self.preferences.get("capture_directory")
                    or Path.home() / "Documents" / "Capturas"
                )
                self.storage_bytes = self._stored_capture_bytes(directory)
                self.top_storage.setText(
                    f"Armazenado: {self._format_bytes(self.storage_bytes)}"
                )
            self._rotate_auto_subsessions()
            remaining = max(0, int(self.next_read_at - now))
            self.top_next_read.setText(f"Próx. leitura: {remaining} s")
            if not self.capture_busy and now >= self.next_read_at:
                self.top_last_read.setText("Última leitura: atualizando…")
                self._run_capture_operation("read", engine.read_live)
        elif engine.paused:
            self.top_next_read.setText("Próx. leitura: pausada")
        elif engine.current_session and not self.capture_busy:
            self.top_capture.setText("Captura — interrompida; encerre para analisar")

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
        self._render_overview()

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

        key = f"client:{chr(97 + self.active_client)}"
        routed = any(item.get("client_key") for item in characters)
        character = next((item for item in characters if item.get("client_key") == key), None)
        if character is None and not routed and self.active_client < len(characters):
            character = characters[self.active_client]
        summary = dict(character.get("summary") or {}) if character else {}
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
        characters = list(self.snapshot.get("characters") or [])
        key = f"client:{chr(97 + index)}"
        routed = any(item.get("client_key") for item in characters)
        character = next(
            (item for item in characters if item.get("client_key") == key), None
        )
        if character is None and not routed and index < len(characters):
            character = characters[index]
        summary = dict(character.get("summary") or {}) if character else {}
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
        self.secondary_character_details.setText(" · ".join((
            f"Nível {summary['level']}" if summary.get("level") is not None else "Nível —",
            str(summary.get("character_class") or "Classe —"),
            str(summary.get("biosuit_name") or "Biosuit —"),
        )))
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
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(argv or ["rf-next-qol-qt-preview"])
    _load_fonts()
    app.setStyleSheet(STYLE)
    return app


def main() -> int:
    self_test = "--self-test" in sys.argv
    if self_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application(sys.argv)
    window = MainWindow(load_data=not self_test)
    window.show()
    app.processEvents()
    if self_test:
        passed = (
            window.minimumSize() == QtCore.QSize(1180, 664)
            and window.page_stack.count() == 5
            and (ROOT / "core" / "rfnext_frame_decode.py").is_file()
            and (ROOT / "core" / "collection_requirements.csv").is_file()
        )
        window.capture_timer.stop()
        window.exit_requested = True
        window.close()
        app.quit()
        return 0 if passed else 1
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

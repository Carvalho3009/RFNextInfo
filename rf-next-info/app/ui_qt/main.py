from __future__ import annotations

import csv
import os
import sys
import ctypes
import gc
import json
import math
import subprocess
import threading
import time
import zipfile
from collections import OrderedDict, deque
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtNetwork, QtWidgets

from app.build_profile import (
    INSTANCE_SERVER_NAME,
    LICENSE_SERVER,
    PROFILE_LABEL,
    SITE_FEATURES,
    SITE_SERVER,
)
from app.ui_qt.data import (
    CLASS_ICON_FILES,
    DB_PATH,
    INVENTORY_CATEGORIES,
    ITEM_GRADES,
    PREFERENCES_PATH,
    RARITY_COLORS,
    ReadOnlySnapshotReader,
    load_farm_catalog,
    load_license_status,
    load_preferences,
    route_live_drop_events,
    route_live_loot_announcements,
    save_preferences,
)
from app.license import LicenseClient
from app.main import (
    BIOSUITS,
    CAPTURE_DIR,
    DEFAULT_PORTS,
    FARM_LABELS_EN_PT,
    FARM_LABELS_PT_EN,
    LOG_PATH,
    MACHINE_STATE_DIR,
    ROVERS,
    RELEASE_SEQUENCE,
    STATE_DIR,
    VERSION,
    _recycle,
    DROP_ALERT_CATEGORY_LABELS,
    drop_alert_category,
    game_catalog_name,
    game_data_language,
    item_names_for_language,
)
from app.paths import (
    KNOWLEDGE_DB_PATH,
    LOCAL_API_STATE_PATH,
    UPDATES_DIR,
    ensure_runtime_layout,
)
from app.local_api import (
    LOCAL_API_DEFAULT_PORT,
    LocalApiTokenStore,
    LocalOutputApi,
)
from app.alert_sound import (
    install_alert_sound,
    play_alert_sound,
    resolve_alert_sound,
)
from app.site_profile import SiteProfileClient
from app.support_log import (
    configure as configure_log,
    install_exception_hooks,
    recent_lines,
    set_detailed,
)
from app.updater import (
    UPDATE_MODE,
    backup_database,
    cached_rollback,
    download_release_with_rollback,
    latest,
    verify_downloaded,
    verify_manifest,
)
from app.ui_qt.operations import (
    CaptureEngine,
    DEFAULT_MEMORY_BUDGET_MB,
    DEFAULT_GLOBAL_SHORTCUTS,
    ExportEngine,
    GlobalHotkeys,
    MAX_MEMORY_BUDGET_MB,
    MEMORY_BUDGET_STEP_MB,
    MIN_MEMORY_BUDGET_MB,
    MonitorEngine,
    SiteUploadEngine,
    memory_limits_for_budget,
)
from core.store import CaptureStore, exp_rank_level_progress
from core.combat_monitor import NEARBY_PLAYER_STALE_SECONDS
from core.auction_sales import auction_sales_snapshot, auction_transaction_history
from core.drop_alerts import (
    aggregate_item_drops_by_client,
    confirmed_item_drop_alerts,
)
from core.knowledge import KnowledgeStore
from core.map_state import (
    MAP_CATALOG,
    MAP_PREVIEW_CATALOG,
    apply_manual_map_fallbacks,
    map_name,
    map_region,
)
from core.program_status import build_program_status
from core.subsession_context import (
    SubsessionContextStabilizer,
    automatic_subsession_end,
    infer_subsession_context,
)


PAGES = (
    ("Visão geral", "Resumo dos clientes e da sessão atual."),
    ("Resumo Geral", "Um card consolidado para cada cliente adicionado."),
    ("Sessões", "Sessão atual e envios de dados já lidos."),
    ("Subsessões", "Histórico, criação e gerenciamento de subsessões."),
    ("Monitoramento", "PvE, PvP e Boss em uma única área."),
    ("Bancos", "PvP, PvE e vendas próprias capturadas do leilão."),
    ("Ranking de EXP", "Top 100 oficial de EXP do servidor."),
    ("Mapa", "Posição local e jogadores próximos de até dois clientes."),
    ("Drops", "Itens recebidos durante a sessão atual."),
    ("Drops de jogadores", "Itens anunciados de outros jogadores, sem duplicidade entre clientes."),
    ("Alertas", "Avisos visuais e sonoros configuráveis."),
    ("Configurações", "Preferências, Profile, API local e saúde do programa."),
    ("Inventário", "Itens e quantidades recebidos do personagem selecionado."),
)
PC_SLOT_COUNT = 2
EMULATOR_SLOT_COUNT = 5
CLIENT_SLOT_COUNT = PC_SLOT_COUNT + EMULATOR_SLOT_COUNT
PAGE_INDEX_BY_TITLE = {title: index for index, (title, _description) in enumerate(PAGES)}
SESSIONS_PAGE_INDEX = PAGE_INDEX_BY_TITLE["Sessões"]
SUBSESSIONS_PAGE_INDEX = PAGE_INDEX_BY_TITLE["Subsessões"]
MONITOR_PAGE_INDEX = PAGE_INDEX_BY_TITLE["Monitoramento"]
BANKS_PAGE_INDEX = PAGE_INDEX_BY_TITLE["Bancos"]
EXP_RANK_PAGE_INDEX = PAGE_INDEX_BY_TITLE["Ranking de EXP"]
MAP_PAGE_INDEX = PAGE_INDEX_BY_TITLE["Mapa"]
DROPS_PAGE_INDEX = PAGE_INDEX_BY_TITLE["Drops"]
LOOT_ANNOUNCEMENTS_PAGE_INDEX = PAGE_INDEX_BY_TITLE["Drops de jogadores"]
SETTINGS_PAGE_INDEX = PAGE_INDEX_BY_TITLE["Configurações"]
MONITOR_TAB_INDEX = {"pve": 0, "pvp": 1, "boss": 2}
MONITOR_FEATURES = {
    "pve": "monitor-pve",
    "pvp": "monitor-pvp",
    "boss": "monitor-boss",
}
FOCUS_READ_INTERVAL_SECONDS = 300
PVP_NEARBY_REFRESH_SECONDS = 10.0
DROP_ALERT_REFRESH_SECONDS = 1.0
PROGRAM_STATUS_PREVIEW_SECONDS = 2.0
MAP_PREVIEW_SECONDS = 1.0
DEFAULT_MEMORY_LIMITS = memory_limits_for_budget(DEFAULT_MEMORY_BUDGET_MB)
MAX_INVENTORY_ICON_CACHE = DEFAULT_MEMORY_LIMITS["inventory_icons"]
INVENTORY_ICON_SIZE = 46
PVP_DATABASE_ROW_LIMIT = DEFAULT_MEMORY_LIMITS["pvp_rows"]
MEMORY_SAMPLE_SECONDS = 5.0
MEMORY_PRESSURE_COOLDOWN_SECONDS = 60.0
MONITOR_SHORTCUT_OPTIONS = tuple(
    f"{modifier}+F{number}"
    for modifier in ("Ctrl", "Alt", "Shift")
    for number in range(1, 13)
    if not (modifier == "Ctrl" and number in {8, 9})
)

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
ASSETS = ROOT / "assets"
MOB_ICONS = ASSETS / "mob-icons"
ITEM_ICON_ARCHIVE = ASSETS / "item-icons.zip"
MAP_PREVIEW_ASSETS = {
    map_index: {
        **dict(item.get("world_bounds") or {}),
        "path": ASSETS / "maps" / str(item.get("asset") or f"{map_index}.webp"),
        "regions": list(item.get("regions") or []),
        "live_position_transform": item.get("live_position_transform"),
    }
    for map_index, item in MAP_PREVIEW_CATALOG.items()
    if isinstance(item, dict) and isinstance(item.get("world_bounds"), dict)
}
DROP_RARITY_LABELS = {
    1: "Comum",
    2: "Incomum",
    3: "Raro",
    4: "Épico",
    5: "Lendário",
}
DROP_DEFAULT_COLOR = "#AEB7C2"
DISCORD_URL = "https://discord.gg/D3hhdMgkj"
_FONTS_LOADED = False

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
    ("context", "Contexto", 110, False),
    ("mau", "MAU", 120, False),
    ("launcher", "Launcher", 120, False),
    ("exp_potion", "Poção de EXP", 130, False),
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
SUBSESSION_CARD_DEFAULT_FIELDS = (
    "name",
    "time",
    "map",
    "mobs",
    "levels",
    "kills",
    "exp_percent",
    "exp_hour",
)


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
    global _FONTS_LOADED
    if _FONTS_LOADED:
        return
    for name in ("Saira.ttf", "SairaSemiCondensed-Bold.ttf"):
        QtGui.QFontDatabase.addApplicationFont(str(ASSETS / name))
    _FONTS_LOADED = True


def _label(text: str, role: str = "") -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    if role:
        label.setProperty("role", role)
    return label


def _display_text(value: object) -> str:
    text = str(value or "")
    if any(marker in text for marker in ("Ã", "Â", "â€")):
        try:
            repaired = text.encode("latin-1").decode("utf-8")
            if repaired:
                return repaired
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
    return text


def _client_key(index: int) -> str:
    return f"client:{chr(97 + index)}"


def _client_label(index: int) -> str:
    return f"Cliente {index + 1}"


class _MovableOverlay(QtWidgets.QDialog):
    position_changed = QtCore.Signal(QtCore.QPoint)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_offset: QtCore.QPoint | None = None
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_QuitOnClose, False)

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


class _ClientButton(QtWidgets.QPushButton):
    double_clicked = QtCore.Signal()

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class _MapSelectionDialog(QtWidgets.QDialog):
    def __init__(
        self,
        options: list[tuple[str, str]],
        current: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Selecionar mapa atual")
        self.setMinimumSize(540, 500)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        heading = _label("Mapa não reconhecido automaticamente", "sectionTitle")
        layout.addWidget(heading)
        help_text = _label(
            "Selecione o mapa na lista. A identificação automática continuará ativa.",
            "muted",
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Procurar mapa…")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.map_list = QtWidgets.QListWidget()
        self.map_list.setAlternatingRowColors(False)
        self.map_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        selected_item = None
        for label, map_name_value in options:
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, map_name_value)
            self.map_list.addItem(item)
            if map_name_value.casefold() == current.casefold():
                selected_item = item
        layout.addWidget(self.map_list, 1)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText("Usar mapa")
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.search.textChanged.connect(self._filter_maps)
        self.map_list.itemDoubleClicked.connect(lambda _item: self.accept())
        if selected_item is None and self.map_list.count():
            selected_item = self.map_list.item(0)
        if selected_item is not None:
            self.map_list.setCurrentItem(selected_item)
            self.map_list.scrollToItem(selected_item)
        self.search.setFocus()

    def _filter_maps(self, text: str) -> None:
        query = text.strip().casefold()
        first_visible = None
        for index in range(self.map_list.count()):
            item = self.map_list.item(index)
            visible = not query or query in item.text().casefold()
            item.setHidden(not visible)
            if visible and first_visible is None:
                first_visible = item
        current = self.map_list.currentItem()
        if current is None or current.isHidden():
            self.map_list.setCurrentItem(first_visible)

    def selected_map_name(self) -> str:
        item = self.map_list.currentItem()
        if item is None or item.isHidden():
            return ""
        return str(item.data(QtCore.Qt.ItemDataRole.UserRole) or "").strip()


def _navigation_icon(kind: str, size: int = 20) -> QtGui.QIcon:
    """Ícones vetoriais leves para manter o shell independente de icon fonts."""
    icon = QtGui.QIcon()
    for mode, color in (
        (QtGui.QIcon.Mode.Normal, "#AEB7C2"),
        (QtGui.QIcon.Mode.Active, "#F4F2EB"),
        (QtGui.QIcon.Mode.Selected, "#D4A64D"),
        (QtGui.QIcon.Mode.Disabled, "#596269"),
    ):
        canvas = QtGui.QPixmap(size, size)
        canvas.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(canvas)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pen = QtGui.QPen(QtGui.QColor(color), 1.6)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        if kind == "home":
            painter.drawPolyline((QtCore.QPointF(3, 10), QtCore.QPointF(10, 4), QtCore.QPointF(17, 10)))
            painter.drawRect(QtCore.QRectF(5.5, 9, 9, 8))
        elif kind == "clock":
            painter.drawEllipse(QtCore.QRectF(3, 3, 14, 14))
            painter.drawLine(QtCore.QPointF(10, 6), QtCore.QPointF(10, 10))
            painter.drawLine(QtCore.QPointF(10, 10), QtCore.QPointF(13, 12))
        elif kind == "pulse":
            painter.drawPolyline((QtCore.QPointF(2, 11), QtCore.QPointF(6, 11), QtCore.QPointF(8, 5), QtCore.QPointF(11, 16), QtCore.QPointF(13, 9), QtCore.QPointF(18, 9)))
        elif kind == "bank":
            painter.drawPolyline((QtCore.QPointF(3, 7), QtCore.QPointF(10, 3), QtCore.QPointF(17, 7), QtCore.QPointF(3, 7)))
            for x in (5, 8.5, 12, 15):
                painter.drawLine(QtCore.QPointF(x, 8), QtCore.QPointF(x, 15))
            painter.drawLine(QtCore.QPointF(3, 16), QtCore.QPointF(17, 16))
        elif kind == "trophy":
            painter.drawRect(QtCore.QRectF(6, 3, 8, 8))
            painter.drawArc(QtCore.QRectF(2, 4, 6, 6), 90 * 16, 180 * 16)
            painter.drawArc(QtCore.QRectF(12, 4, 6, 6), -90 * 16, 180 * 16)
            painter.drawLine(QtCore.QPointF(10, 11), QtCore.QPointF(10, 15))
            painter.drawLine(QtCore.QPointF(6, 17), QtCore.QPointF(14, 17))
        elif kind == "map":
            painter.drawPolyline((QtCore.QPointF(3, 5), QtCore.QPointF(8, 3), QtCore.QPointF(13, 5), QtCore.QPointF(17, 3), QtCore.QPointF(17, 15), QtCore.QPointF(13, 17), QtCore.QPointF(8, 15), QtCore.QPointF(3, 17), QtCore.QPointF(3, 5)))
            painter.drawLine(QtCore.QPointF(8, 3), QtCore.QPointF(8, 15))
            painter.drawLine(QtCore.QPointF(13, 5), QtCore.QPointF(13, 17))
        elif kind == "bell":
            painter.drawArc(QtCore.QRectF(5, 3, 10, 12), 0, 180 * 16)
            painter.drawLine(QtCore.QPointF(5, 8), QtCore.QPointF(4, 14))
            painter.drawLine(QtCore.QPointF(15, 8), QtCore.QPointF(16, 14))
            painter.drawLine(QtCore.QPointF(4, 14), QtCore.QPointF(16, 14))
            painter.drawArc(QtCore.QRectF(8, 13, 4, 4), 180 * 16, 180 * 16)
        elif kind == "link":
            painter.drawArc(QtCore.QRectF(2, 5, 9, 10), 70 * 16, 220 * 16)
            painter.drawArc(QtCore.QRectF(9, 5, 9, 10), -110 * 16, 220 * 16)
            painter.drawLine(QtCore.QPointF(7, 10), QtCore.QPointF(13, 10))
        elif kind == "settings":
            painter.drawEllipse(QtCore.QRectF(7, 7, 6, 6))
            painter.drawEllipse(QtCore.QRectF(3, 3, 14, 14))
            for angle in range(0, 360, 45):
                radians = math.radians(angle)
                painter.drawLine(
                    QtCore.QPointF(10 + math.cos(radians) * 7, 10 + math.sin(radians) * 7),
                    QtCore.QPointF(10 + math.cos(radians) * 9, 10 + math.sin(radians) * 9),
                )
        elif kind == "book":
            painter.drawRoundedRect(QtCore.QRectF(3, 3, 7, 14), 1, 1)
            painter.drawRoundedRect(QtCore.QRectF(10, 3, 7, 14), 1, 1)
            painter.drawLine(QtCore.QPointF(10, 4), QtCore.QPointF(10, 17))
        else:  # caixa / inventário
            painter.drawRect(QtCore.QRectF(4, 6, 12, 11))
            painter.drawLine(QtCore.QPointF(4, 6), QtCore.QPointF(7, 3))
            painter.drawLine(QtCore.QPointF(16, 6), QtCore.QPointF(13, 3))
            painter.drawLine(QtCore.QPointF(7, 3), QtCore.QPointF(13, 3))
        painter.end()
        icon.addPixmap(canvas, mode)
    return icon


def _status_dot_icon(color: str = "#58C96B", size: int = 10) -> QtGui.QIcon:
    canvas = QtGui.QPixmap(size, size)
    canvas.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(canvas)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(QtGui.QColor(color))
    painter.drawEllipse(QtCore.QRectF(1.5, 1.5, size - 3, size - 3))
    painter.end()
    return QtGui.QIcon(canvas)


def _capture_action_icon(kind: str, color: str, size: int = 20) -> QtGui.QIcon:
    """Ícones de captura próprios, com cor semântica e estado inativo neutro."""
    icon = QtGui.QIcon()
    for mode, current in (
        (QtGui.QIcon.Mode.Normal, color),
        (QtGui.QIcon.Mode.Active, color),
        (QtGui.QIcon.Mode.Selected, color),
        (QtGui.QIcon.Mode.Disabled, "#596269"),
    ):
        canvas = QtGui.QPixmap(size, size)
        canvas.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(canvas)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pen = QtGui.QPen(QtGui.QColor(current), 2.0)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(QtGui.QColor(current))
        if kind == "start":
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.drawPolygon(QtGui.QPolygonF((
                QtCore.QPointF(6, 4),
                QtCore.QPointF(16, 10),
                QtCore.QPointF(6, 16),
            )))
        elif kind == "continue":
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.drawPolygon(QtGui.QPolygonF((
                QtCore.QPointF(7, 4),
                QtCore.QPointF(16, 10),
                QtCore.QPointF(7, 16),
            )))
            painter.drawRoundedRect(QtCore.QRectF(3, 4, 2.5, 12), 1, 1)
        elif kind == "pause":
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QtCore.QRectF(5, 4, 3.5, 12), 1, 1)
            painter.drawRoundedRect(QtCore.QRectF(11.5, 4, 3.5, 12), 1, 1)
        elif kind == "stop":
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QtCore.QRectF(5, 5, 10, 10), 1.5, 1.5)
        else:  # encerrar sem ler
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QtCore.QRectF(4, 4, 12, 12), 2, 2)
            painter.drawLine(QtCore.QPointF(5, 15), QtCore.QPointF(15, 5))
        painter.end()
        icon.addPixmap(canvas, mode)
    return icon


class _MemorySparkline(QtWidgets.QWidget):
    """Histórico curto e estritamente limitado do uso de memória."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.samples: deque[float] = deque(maxlen=60)
        self.limit_mb = 768.0
        self.setMinimumHeight(94)

    def add_sample(self, value_mb: float | None, limit_mb: float) -> None:
        self.limit_mb = max(1.0, float(limit_mb))
        if isinstance(value_mb, (int, float)):
            sample = max(0.0, float(value_mb))
            if not self.samples:
                self.samples.append(sample)
            self.samples.append(sample)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        area = self.rect().adjusted(8, 8, -8, -12)
        painter.fillRect(area, QtGui.QColor("#0A0F13"))
        grid = QtGui.QPen(QtGui.QColor("#26333A"), 1, QtCore.Qt.PenStyle.DashLine)
        painter.setPen(grid)
        for step in (0.0, 0.5, 1.0):
            y = area.bottom() - area.height() * step
            painter.drawLine(QtCore.QPointF(area.left(), y), QtCore.QPointF(area.right(), y))
        if len(self.samples) > 1:
            points = QtGui.QPolygonF()
            count = max(1, len(self.samples) - 1)
            for index, sample in enumerate(self.samples):
                x = area.left() + area.width() * index / count
                y = area.bottom() - area.height() * min(1.0, sample / self.limit_mb)
                points.append(QtCore.QPointF(x, y))
            painter.setPen(QtGui.QPen(QtGui.QColor("#E5B35C"), 2.2))
            painter.drawPolyline(points)
        painter.end()


class _MapPreview(QtWidgets.QWidget):
    """Mapa completo com posição, zoom, arraste e foco no personagem."""

    view_changed = QtCore.Signal(int, bool)
    MIN_ZOOM = 1.0
    MAX_ZOOM = 6.0
    ZOOM_STEP = 1.25

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        lock_character_position: bool = False,
        show_player_labels: bool = True,
        interactive: bool = True,
    ) -> None:
        super().__init__(parent)
        self.lock_character_position = bool(lock_character_position)
        self.show_player_labels = bool(show_player_labels)
        self.interactive = bool(interactive)
        self.map_index: int | None = None
        self.local_position: dict[str, float] = {}
        self.players: list[dict[str, object]] = []
        self.player_count = 0
        self._map_pixmaps: OrderedDict[int, QtGui.QPixmap] = OrderedDict()
        self.zoom = self.MIN_ZOOM
        self.pan_offset = QtCore.QPointF()
        self.follow_character = self.interactive
        self._drag_origin: QtCore.QPointF | None = None
        self._drag_pan_origin = QtCore.QPointF()
        self.setMinimumSize(220, 220)
        self.setCursor(
            QtCore.Qt.CursorShape.OpenHandCursor
            if self.interactive else QtCore.Qt.CursorShape.ArrowCursor
        )
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return max(220, int(width))

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(560, 560)

    def set_player_count(self, count: int) -> None:
        """Compatibilidade com consumidores antigos da miniatura."""
        self.player_count = max(0, int(count))
        self.players = [{} for _index in range(self.player_count)]
        self.update()

    def set_snapshot(
        self,
        map_index: object,
        local_position: object,
        players: object,
    ) -> None:
        next_map_index = None
        if isinstance(map_index, (int, float)) and not isinstance(map_index, bool):
            next_map_index = int(map_index)
        elif isinstance(map_index, str) and map_index.strip().isdigit():
            next_map_index = int(map_index.strip())
        if next_map_index != self.map_index:
            self.zoom = self.MIN_ZOOM
            self.pan_offset = QtCore.QPointF()
            self.follow_character = self.interactive
            self.view_changed.emit(self.zoom_percent(), self.follow_character)
        self.map_index = next_map_index
        self.local_position = (
            {
                axis: float(value)
                for axis in ("x", "y", "z")
                if isinstance((value := local_position.get(axis)), (int, float))
            }
            if isinstance(local_position, dict)
            else {}
        )
        self.players = [
            dict(item) for item in (players if isinstance(players, list) else [])
            if isinstance(item, dict)
        ]
        self.player_count = len(self.players)
        self.update()

    def zoom_percent(self) -> int:
        return int(round(self.zoom * 100))

    def _area(self) -> QtCore.QRectF:
        return QtCore.QRectF(self.rect().adjusted(1, 1, -1, -1))

    def _base_target(self, area: QtCore.QRectF, pixmap: QtGui.QPixmap) -> QtCore.QRectF:
        return self._fit_rect(area, pixmap.width(), pixmap.height())

    @staticmethod
    def _clamp_pan(
        area: QtCore.QRectF,
        base: QtCore.QRectF,
        zoom: float,
        offset: QtCore.QPointF,
    ) -> QtCore.QPointF:
        limit_x = max(0.0, (base.width() * zoom - area.width()) / 2)
        limit_y = max(0.0, (base.height() * zoom - area.height()) / 2)
        return QtCore.QPointF(
            max(-limit_x, min(limit_x, offset.x())),
            max(-limit_y, min(limit_y, offset.y())),
        )

    def _target_rect(
        self,
        area: QtCore.QRectF,
        pixmap: QtGui.QPixmap,
        metadata: dict[str, object],
    ) -> QtCore.QRectF:
        base = self._base_target(area, pixmap)
        size = QtCore.QSizeF(base.width() * self.zoom, base.height() * self.zoom)
        unpanned = QtCore.QRectF(
            area.center().x() - size.width() / 2,
            area.center().y() - size.height() / 2,
            size.width(),
            size.height(),
        )
        if not self.interactive:
            self.pan_offset = QtCore.QPointF()
            self.follow_character = False
            return unpanned
        if self.follow_character:
            character = self._project(self.local_position, unpanned, metadata)
            desired = (
                area.center() - character
                if character is not None else QtCore.QPointF()
            )
            self.pan_offset = (
                desired
                if self.lock_character_position
                else self._clamp_pan(area, base, self.zoom, desired)
            )
        else:
            self.pan_offset = self._clamp_pan(
                area, base, self.zoom, self.pan_offset
            )
        return unpanned.translated(self.pan_offset)

    def set_zoom(
        self, value: float, anchor: QtCore.QPointF | None = None
    ) -> None:
        if not self.interactive:
            return
        next_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, float(value)))
        if abs(next_zoom - self.zoom) < 0.001:
            return
        old_zoom = self.zoom
        if not self.follow_character:
            area = self._area()
            anchor = anchor or area.center()
            ratio = next_zoom / old_zoom
            old_center = area.center() + self.pan_offset
            new_center = anchor + (old_center - anchor) * ratio
            self.pan_offset = new_center - area.center()
        self.zoom = next_zoom
        self.view_changed.emit(self.zoom_percent(), self.follow_character)
        self.update()

    def zoom_in(self) -> None:
        self.set_zoom(self.zoom * self.ZOOM_STEP)

    def zoom_out(self) -> None:
        self.set_zoom(self.zoom / self.ZOOM_STEP)

    def pan_by(self, delta: QtCore.QPointF) -> None:
        if not self.interactive:
            return
        map_asset = self._map_pixmap()
        self.follow_character = False
        self.pan_offset += delta
        if map_asset:
            pixmap, _metadata = map_asset
            area = self._area()
            self.pan_offset = self._clamp_pan(
                area, self._base_target(area, pixmap), self.zoom, self.pan_offset
            )
        self.view_changed.emit(self.zoom_percent(), self.follow_character)
        self.update()

    def focus_on_character(self) -> None:
        if not self.interactive:
            return
        self.follow_character = True
        self.view_changed.emit(self.zoom_percent(), self.follow_character)
        self.update()

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if not self.interactive:
            event.ignore()
            return
        factor = self.ZOOM_STEP if event.angleDelta().y() > 0 else 1 / self.ZOOM_STEP
        self.set_zoom(self.zoom * factor, event.position())
        event.accept()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if not self.interactive:
            super().mousePressEvent(event)
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_origin = event.position()
            self._drag_pan_origin = QtCore.QPointF(self.pan_offset)
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if not self.interactive:
            super().mouseMoveEvent(event)
            return
        if self._drag_origin is not None:
            self.follow_character = False
            self.pan_offset = self._drag_pan_origin + event.position() - self._drag_origin
            map_asset = self._map_pixmap()
            if map_asset:
                pixmap, _metadata = map_asset
                area = self._area()
                self.pan_offset = self._clamp_pan(
                    area, self._base_target(area, pixmap), self.zoom, self.pan_offset
                )
            self.view_changed.emit(self.zoom_percent(), self.follow_character)
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if not self.interactive:
            super().mouseReleaseEvent(event)
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_origin = None
            self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        if not self.interactive:
            super().mouseDoubleClickEvent(event)
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.focus_on_character()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _map_pixmap(self) -> tuple[QtGui.QPixmap, dict[str, object]] | None:
        metadata = MAP_PREVIEW_ASSETS.get(self.map_index or -1)
        if not metadata:
            return None
        index = int(self.map_index or 0)
        if index not in self._map_pixmaps:
            self._map_pixmaps[index] = QtGui.QPixmap(str(metadata["path"]))
            while len(self._map_pixmaps) > 4:
                self._map_pixmaps.popitem(last=False)
        pixmap = self._map_pixmaps.pop(index)
        self._map_pixmaps[index] = pixmap
        return (pixmap, metadata) if not pixmap.isNull() else None

    def _current_region(
        self, metadata: dict[str, object]
    ) -> dict[str, object] | None:
        x, y = self.local_position.get("x"), self.local_position.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            return None
        x, y = self._world_coordinates(float(x), float(y), metadata)
        regions = [
            item for item in metadata.get("regions") or []
            if isinstance(item, dict) and isinstance(item.get("center"), dict)
        ]
        if not regions:
            return None
        return min(
            regions,
            key=lambda item: (
                float(item["center"].get("x") or 0) - float(x)
            ) ** 2 + (
                float(item["center"].get("y") or 0) - float(y)
            ) ** 2,
        )

    def current_region_name(self, language: str = "pt") -> str:
        metadata = MAP_PREVIEW_ASSETS.get(self.map_index or -1)
        region = self._current_region(metadata) if metadata else None
        if not region:
            return ""
        primary, secondary = ("en", "pt") if language == "en" else ("pt", "en")
        return str(region.get(primary) or region.get(secondary) or "")

    @staticmethod
    def _world_coordinates(
        x: float,
        y: float,
        metadata: dict[str, object],
    ) -> tuple[float, float]:
        transform = metadata.get("live_position_transform")
        if not isinstance(transform, dict):
            return x, y
        try:
            return (
                x * float(transform.get("scale_x", 1.0))
                + float(transform.get("offset_x", 0.0)),
                y * float(transform.get("scale_y", 1.0))
                + float(transform.get("offset_y", 0.0)),
            )
        except (TypeError, ValueError):
            return x, y

    @staticmethod
    def _region_projection(
        pixmap: QtGui.QPixmap,
        metadata: dict[str, object],
        region: dict[str, object] | None,
    ) -> tuple[QtCore.QRectF, dict[str, object]]:
        source = QtCore.QRectF(pixmap.rect())
        bounds = region.get("crop_bounds") if region else None
        if not isinstance(bounds, dict):
            return source, metadata
        global_span_x = float(metadata["span_x"])
        global_span_y = float(metadata["span_y"])
        left = (
            (float(bounds["min_x"]) - float(metadata["min_x"]))
            / global_span_x * pixmap.width()
        )
        top = (
            (float(bounds["min_y"]) - float(metadata["min_y"]))
            / global_span_y * pixmap.height()
        )
        width = float(bounds["span_x"]) / global_span_x * pixmap.width()
        height = float(bounds["span_y"]) / global_span_y * pixmap.height()
        return QtCore.QRectF(left, top, width, height), bounds

    @staticmethod
    def _fit_rect(area: QtCore.QRectF, width: int, height: int) -> QtCore.QRectF:
        if width <= 0 or height <= 0:
            return area
        scale = min(area.width() / width, area.height() / height)
        size = QtCore.QSizeF(width * scale, height * scale)
        return QtCore.QRectF(
            area.center().x() - size.width() / 2,
            area.center().y() - size.height() / 2,
            size.width(),
            size.height(),
        )

    @staticmethod
    def _project(
        position: object,
        target: QtCore.QRectF,
        metadata: dict[str, object],
    ) -> QtCore.QPointF | None:
        if not isinstance(position, dict):
            return None
        x, y = position.get("x"), position.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            return None
        x, y = _MapPreview._world_coordinates(float(x), float(y), metadata)
        span_x, span_y = float(metadata["span_x"]), float(metadata["span_y"])
        normalized_x = (x - float(metadata["min_x"])) / span_x
        normalized_y = (y - float(metadata["min_y"])) / span_y
        if not (-0.05 <= normalized_x <= 1.05 and -0.05 <= normalized_y <= 1.05):
            return None
        return QtCore.QPointF(
            target.left() + target.width() * min(1.0, max(0.0, normalized_x)),
            target.top() + target.height() * min(1.0, max(0.0, normalized_y)),
        )

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        area = self._area()
        painter.fillRect(area, QtGui.QColor("#0A0F13"))
        map_asset = self._map_pixmap()
        metadata: dict[str, object] | None = None
        target = area
        if map_asset:
            pixmap, metadata = map_asset
            source = QtCore.QRectF(pixmap.rect())
            target = self._target_rect(area, pixmap, metadata)
            painter.setOpacity(0.82)
            painter.drawPixmap(target, pixmap, source)
            painter.setOpacity(1.0)
        else:
            painter.setPen(QtGui.QPen(QtGui.QColor("#202A30"), 1))
            for division in range(1, 5):
                x = area.left() + area.width() * division / 5
                y = area.top() + area.height() * division / 5
                painter.drawLine(
                    QtCore.QPointF(x, area.top()), QtCore.QPointF(x, area.bottom())
                )
                painter.drawLine(
                    QtCore.QPointF(area.left(), y), QtCore.QPointF(area.right(), y)
                )
        center = (
            self._project(self.local_position, target, metadata)
            if metadata else None
        ) or QtCore.QPointF(area.center())
        projected_players = [
            self._project(player.get("position"), target, metadata)
            for player in self.players
        ] if metadata else []
        projected_players = [point for point in projected_players if point is not None]
        observed_radius = max(
            [44.0, *(
                math.hypot(point.x() - center.x(), point.y() - center.y()) + 14
                for point in projected_players
            )],
        )
        observed_radius = min(observed_radius, min(area.width(), area.height()) * 0.42)
        painter.setPen(QtGui.QPen(
            QtGui.QColor(99, 185, 243, 150),
            1.5,
            QtCore.Qt.PenStyle.DashLine,
        ))
        painter.setBrush(QtGui.QColor(99, 185, 243, 22))
        painter.drawEllipse(center, observed_radius, observed_radius)
        painter.setPen(QtGui.QPen(QtGui.QColor("#D4A64D"), 2))
        painter.setBrush(QtGui.QColor("#132028"))
        painter.drawEllipse(center, 10, 10)
        painter.drawLine(center + QtCore.QPointF(0, -6), center + QtCore.QPointF(-4, 5))
        painter.drawLine(center + QtCore.QPointF(0, -6), center + QtCore.QPointF(4, 5))
        painter.drawLine(center + QtCore.QPointF(-4, 5), center + QtCore.QPointF(4, 5))
        painter.setPen(QtGui.QPen(QtGui.QColor("#63B9F3"), 1.5))
        painter.setBrush(QtGui.QColor("#63B9F3"))
        offsets = ((32, -22), (48, 10), (-34, -34), (-46, 21), (10, 42))
        font = painter.font()
        font.setPointSizeF(max(7.0, min(9.0, area.width() / 48)))
        painter.setFont(font)
        for index, player in enumerate(self.players[:12]):
            point = (
                self._project(player.get("position"), target, metadata)
                if metadata else None
            )
            if point is None:
                dx, dy = offsets[index % len(offsets)]
                ring = 1 + index // len(offsets)
                point = center + QtCore.QPointF(dx * ring, dy * ring)
            painter.setPen(QtGui.QPen(QtGui.QColor("#63B9F3"), 1.5))
            painter.setBrush(QtGui.QColor("#63B9F3"))
            painter.drawEllipse(point, 3.5, 3.5)
            name = str(player.get("name") or "").strip()
            if not name or not self.show_player_labels:
                continue
            label = name if len(name) <= 18 else name[:17] + "…"
            label_rect = QtCore.QRectF(
                min(area.right() - 112, point.x() + 6),
                max(area.top(), point.y() - 10 + (index % 2) * 10),
                108,
                20,
            )
            painter.setPen(QtGui.QColor("#071014"))
            painter.drawText(label_rect.translated(1, 1), label)
            painter.setPen(QtGui.QColor("#DDE9F2"))
            painter.drawText(label_rect, label)
        painter.end()


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
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
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
        self.active_category = "pc"
        self.snapshot: dict[str, object] = {}
        self.preferences: dict[str, object] = load_preferences(self.preferences_path)
        legacy_client_count = self._bounded(
            self.preferences.get("visible_client_count"), 1, CLIENT_SLOT_COUNT, 1
        )
        self.visible_client_slots = self._normalize_visible_client_slots(
            self.preferences.get("visible_client_slots"), legacy_client_count
        )
        self.visible_client_count = len(self.visible_client_slots)
        self.memory_limits = memory_limits_for_budget(
            self.preferences.get("memory_limit_mb")
        )
        self.farm_catalog: dict[str, dict[str, dict[str, tuple[int, ...]]]] = {}
        self.selected_subsessions: set[str] = set()
        self.subsession_page = 1
        self.drops_page = 1
        self.loot_announcements_page = 1
        self.editing_subsession_id: str | None = None
        self.capture_engine: CaptureEngine | None = None
        self.monitor_engine: MonitorEngine | None = None
        self.local_api: LocalOutputApi | None = None
        self.local_api_token = ""
        self.auction_projection_secret = os.urandom(32)
        self.program_status_snapshot: dict[str, object] = {}
        self.previous_program_status: dict[str, dict[str, object]] = {}
        self.program_status_next_refresh = 0.0
        self.program_status_preview_next_due = 0.0
        self.map_preview_next_due = 0.0
        self.latest_monitor_metrics: dict[str, object] = {}
        self.local_api_state_path = (
            LOCAL_API_STATE_PATH
            if self.preferences_path == PREFERENCES_PATH
            else self.preferences_path.with_name("local-api.bin")
        )
        self.monitor_enabled = {"pve": False, "pvp": False, "boss": False}
        self.monitor_client_enabled = {
            "pve": [False] * CLIENT_SLOT_COUNT,
            "pvp": [False] * CLIENT_SLOT_COUNT,
        }
        self.monitor_next_due = {"pve": 0.0, "pvp": 0.0, "boss": 0.0}
        self.pvp_nearby_next_due = 0.0
        self.drop_alert_next_due = 0.0
        self.monitor_controls: dict[str, dict[str, Any]] = {}
        self.boss_overlay: QtWidgets.QDialog | None = None
        self.boss_dps_overlay: QtWidgets.QDialog | None = None
        self.pvp_overlays: dict[str, QtWidgets.QDialog] = {}
        self.alert_last_fired: OrderedDict[str, float] = OrderedDict()
        self.drop_alert_session: str | None = None
        self.loot_announcement_session: str | None = None
        self.seen_drop_alerts: dict[str, None] = {}
        self.capture_busy = False
        self.site_busy = False
        self.pending_capture_action: str | None = None
        self.license_active = False
        self.license_features: set[str] = set()
        self.connection_limits = {"pc": 0, "emulators": 0}
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
        self.observation_sync_next_due = time.monotonic() + 300
        self.pending_auto_market: tuple[str, str] | None = None
        self.auto_market_retry_after = 0.0
        self.pending_auto_exp_rank: tuple[str, str] | None = None
        self.auto_exp_rank_retry_after = 0.0
        self.inventory_icon_cache: OrderedDict[int, QtGui.QIcon] = OrderedDict()
        self.memory_next_sample = 0.0
        self.memory_pressure_last_at = -MEMORY_PRESSURE_COOLDOWN_SECONDS
        self.item_icon_zip: zipfile.ZipFile | None = None
        try:
            self.log_path = LOG_PATH
            self.log = configure_log(self.log_path, VERSION, detailed=True)
        except OSError as error:
            raise OSError(f"Não foi possível gravar o log em {LOG_PATH}") from error
        install_exception_hooks(self.log)
        self.license_client = LicenseClient(
            MACHINE_STATE_DIR, server=LICENSE_SERVER, version=VERSION
        )
        self.license_client.record_release_sequence(RELEASE_SEQUENCE)
        self.snapshot_reader = ReadOnlySnapshotReader(
            self.database_path,
            self.license_client,
            character_history_limit=self.memory_limits["character_history"],
        )
        self.site_profile = SiteProfileClient(
            STATE_DIR,
            server=SITE_SERVER,
            version=VERSION,
            features=SITE_FEATURES,
        )
        self.site_uploader = SiteUploadEngine(
            self.database_path, self.site_profile, self.license_client
        )
        self.export_engine = ExportEngine(self.database_path, self.license_client)
        self.data_load_running = False
        self.data_load_pending = False
        self.combat_load_running = False
        self.combat_load_pending = False
        self.subsession_context_session = ""
        self.subsession_context_stabilizer = SubsessionContextStabilizer()
        self.controls_initialized = False
        self.setObjectName("mainWindow")
        self.setWindowTitle(f"RF QOL — {VERSION} ({PROFILE_LABEL})")
        self.setMinimumSize(1180, 664)
        self.resize(1440, 810)

        icon = QtGui.QIcon(str(ASSETS / "karvalho-symbol-gold.png"))
        self.setWindowIcon(icon)
        self._tray = self._build_tray(icon)

        root = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        main_surface = QtWidgets.QWidget(objectName="mainSurface")
        main_layout = QtWidgets.QVBoxLayout(main_surface)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self._build_topbar())
        main_layout.addWidget(self._build_body(), 1)
        main_layout.addWidget(self._build_footer())
        layout.addWidget(main_surface, 1)
        self.setCentralWidget(root)
        self._sync_client_collection()
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
        self._apply_license(self.license_client.local_status())
        if load_data:
            self.global_hotkeys.start()
        self.capture_timer = QtCore.QTimer(self)
        self.capture_timer.timeout.connect(self._capture_tick)
        self.capture_timer.start(250)
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
            if self.isMinimized():
                QtCore.QTimer.singleShot(0, self._keep_overlays_visible)

    def _keep_overlays_visible(self) -> None:
        for overlay in (
            self.boss_overlay,
            self.boss_dps_overlay,
            *self.pvp_overlays.values(),
        ):
            if overlay is not None:
                overlay.show()

    def _sync_responsive_layouts(self) -> None:
        self._sync_overview_layout()
        self._sync_combat_layout()

    def _sync_overview_layout(self) -> None:
        if not hasattr(self, "overview_grid"):
            return
        for card in (
            *self.overview_cards,
            self.program_status_card,
            self.nearby_mobs_card,
            self.drops_card,
        ):
            self.overview_grid.removeWidget(card)
        self.session_card.show()
        self.subsession_card.show()
        self.overview_grid.addWidget(self.session_card, 0, 0)
        self.overview_grid.addWidget(self.subsession_card, 0, 1)
        self.overview_grid.addWidget(self.map_card, 1, 0, 1, 2)
        self.overview_grid.addWidget(self.health_card, 2, 0, 1, 2)
        for column in range(2):
            self.overview_grid.setColumnStretch(column, 1)
        for row in range(3):
            self.overview_grid.setRowStretch(row, 1 if row < 2 else 0)

    def _open_active_subsession(self) -> None:
        self.page_stack.setCurrentIndex(SUBSESSIONS_PAGE_INDEX)

    def _open_session_details(self) -> None:
        self.page_stack.setCurrentIndex(SESSIONS_PAGE_INDEX)

    def _open_drops_page(self) -> None:
        self.page_stack.setCurrentIndex(DROPS_PAGE_INDEX)

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
        tray.setToolTip(f"RF QOL — {VERSION} ({PROFILE_LABEL})")
        menu = QtWidgets.QMenu(self)
        self.tray_menu = menu
        show_action = menu.addAction("Abrir RF QOL")
        show_action.triggered.connect(self._show_from_tray)
        menu.addSeparator()
        self.tray_start_action = menu.addAction("Começar captura nova")
        self.tray_start_action.triggered.connect(self._start_new_capture)
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
        bar.setFixedHeight(64)
        row = QtWidgets.QHBoxLayout(bar)
        row.setContentsMargins(26, 0, 18, 0)
        row.setSpacing(10)
        row.addStretch(1)
        self.top_program_status = _label("Ocioso", "warning")
        self.top_program_status.setObjectName("statusChip")
        self.top_capture = _label("Captura inativa", "muted")
        self.top_capture.setObjectName("statusChip")
        self.top_location = _label("Mapa —", "muted")
        self.top_location.setObjectName("statusChip")
        self.top_memory = _label("RAM —", "muted")
        self.top_memory.setObjectName("statusChip")
        for label in (
            self.top_program_status,
            self.top_capture,
            self.top_location,
            self.top_memory,
        ):
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            row.addWidget(label)
        row.addStretch(1)

        hidden_statuses = (
            ("top_license", "Licença — carregando"),
            ("top_last_read", "Última leitura: —"),
            ("top_next_read", "Próx. atualização: —"),
            ("top_storage", "Armazenado: —"),
        )
        for attribute, text in hidden_statuses:
            label = _label(text, "muted")
            label.setParent(bar)
            label.hide()
            setattr(self, attribute, label)

        action_specs = (
            ("Start", "start", "Começar captura nova", "#58C96B"),
            ("Continue", "continue", "Continuar captura anterior", "#4EA7D8"),
            ("Pause", "pause", "Pausar captura", "#D4A64D"),
            ("Stop", "stop", "Encerrar captura", "#FF6547"),
            ("StopRaw", "stop_raw", "Encerrar sem ler", "#FF6547"),
        )
        for index, (object_suffix, kind, tooltip, color) in enumerate(action_specs):
            button = QtWidgets.QToolButton(objectName=f"capture{object_suffix}")
            button.setProperty("captureAction", True)
            button.setIcon(_capture_action_icon(kind, color))
            button.setIconSize(QtCore.QSize(20, 20))
            button.setFixedSize(36, 36)
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
            button.setEnabled(False)
            if index == 0:
                self.start_button = button
                button.clicked.connect(self._start_new_capture)
            elif index == 1:
                self.continue_button = button
                button.clicked.connect(self._continue_capture)
            elif index == 2:
                self.pause_button = button
                button.clicked.connect(self._pause_capture)
            elif index == 3:
                self.stop_button = button
                button.clicked.connect(self._stop_capture)
            else:
                self.stop_without_reading_button = button
                button.setToolTip(
                    "Interrompe a captura agora e preserva os arquivos brutos para leitura posterior."
                )
                button.clicked.connect(self._stop_capture_without_reading)
            row.addWidget(button)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+F8"), self, activated=self._start_new_capture)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+F9"), self, activated=self._stop_capture)
        return bar

    def _build_body(self) -> QtWidgets.QWidget:
        workspace = QtWidgets.QWidget(objectName="workspace")
        column = QtWidgets.QVBoxLayout(workspace)
        column.setContentsMargins(32, 22, 32, 18)
        column.setSpacing(12)
        heading = QtWidgets.QHBoxLayout()
        self.page_title = _label(PAGES[0][0], "workspaceTitle")
        heading.addWidget(self.page_title)
        self.version_badge = _label(f"{VERSION} · {PROFILE_LABEL}", "versionBadge")
        heading.addWidget(self.version_badge)
        heading.addStretch(1)
        column.addLayout(heading)
        column.addWidget(self._build_clients())
        self.page_stack = QtWidgets.QStackedWidget(objectName="pageStack")
        for index, (title, description) in enumerate(PAGES):
            if title == "Visão geral":
                page = self._build_overview_page()
            elif title == "Resumo Geral":
                page = self._build_general_summary_page()
            elif title == "Sessões":
                page = self._build_sessions_page()
            elif title == "Subsessões":
                page = self._build_subsessions_page()
            elif title == "Monitoramento":
                page = self._build_monitoring_page()
            elif title == "Bancos":
                page = self._build_banks_page()
            elif title == "Ranking de EXP":
                page = self._build_exp_rank_page()
            elif title == "Mapa":
                page = self._build_map_page()
            elif title == "Drops":
                page = self._build_drops_page()
            elif title == "Drops de jogadores":
                page = self._build_loot_announcements_page()
            elif title == "Alertas":
                page = self._build_alerts_page()
            elif title == "Configurações":
                page = self._build_settings_page()
            elif title == "Inventário":
                page = self._build_inventory_page()
            else:
                page = self._build_page(title, description)
            for label in page.findChildren(QtWidgets.QLabel):
                if label.property("role") == "title":
                    label.hide()
                    break
            self.page_stack.addWidget(page)
        self._apply_table_column_policy(self.page_stack)
        column.addWidget(self.page_stack, 1)
        return workspace

    @staticmethod
    def _apply_table_column_policy(root: QtWidgets.QWidget) -> None:
        """Permite ordenar, redimensionar e autofitar todas as colunas."""
        for table in root.findChildren(QtWidgets.QTableWidget):
            header = table.horizontalHeader()
            header.setSectionsMovable(True)
            if hasattr(header, "setFirstSectionMovable"):
                header.setFirstSectionMovable(True)
            header.setStretchLastSection(False)
            header.setSectionResizeMode(
                QtWidgets.QHeaderView.ResizeMode.Interactive
            )
            if not bool(table.property("standardColumnPolicy")):
                header.sectionDoubleClicked.connect(
                    table.resizeColumnToContents
                )
                table.setProperty("standardColumnPolicy", True)

    def _build_sidebar(self) -> QtWidgets.QWidget:
        sidebar = QtWidgets.QWidget(objectName="sidebar")
        sidebar.setFixedWidth(248)
        column = QtWidgets.QVBoxLayout(sidebar)
        column.setContentsMargins(0, 34, 0, 18)
        column.setSpacing(4)

        logo = QtWidgets.QLabel(objectName="brandLogo")
        pixmap = QtGui.QPixmap(str(ASSETS / "karvalho-primary-gold.png"))
        if pixmap.width() > 1000 and pixmap.height() > 500:
            pixmap = pixmap.copy(QtCore.QRect(
                int(pixmap.width() * 0.035),
                int(pixmap.height() * 0.20),
                int(pixmap.width() * 0.90),
                int(pixmap.height() * 0.44),
            ))
        logo.setPixmap(pixmap.scaled(216, 54, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                     QtCore.Qt.TransformationMode.SmoothTransformation))
        logo.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        logo.setFixedHeight(62)
        column.addWidget(logo)
        product = _label("RF QOL", "product")
        product.setContentsMargins(18, 4, 18, 14)
        column.addWidget(product)

        self.nav_group = QtWidgets.QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QtWidgets.QPushButton] = []
        category_container = QtWidgets.QWidget(sidebar)
        category_container.hide()
        category_row = QtWidgets.QHBoxLayout(category_container)
        self.category_group = QtWidgets.QButtonGroup(self)
        self.category_group.setExclusive(True)
        self.category_buttons: dict[str, QtWidgets.QPushButton] = {}
        for category, title in (("pc", "PC"), ("emulator", "Emuladores")):
            button = QtWidgets.QPushButton(title, category_container)
            button.setCheckable(True)
            button.setChecked(category == "pc")
            button.clicked.connect(
                lambda checked=False, selected=category: self._select_category(selected)
            )
            self.category_group.addButton(button)
            self.category_buttons[category] = button
            category_row.addWidget(button)
            button.hide()

        nav_scroll = QtWidgets.QScrollArea(sidebar)
        nav_scroll.setObjectName("sidebarNavScroll")
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        nav_content = QtWidgets.QWidget(objectName="sidebarNavContent")
        nav_scroll.viewport().setAutoFillBackground(False)
        nav_content.setAutoFillBackground(False)
        self.sidebar_nav_scroll = nav_scroll
        self.sidebar_nav_content = nav_content
        nav_column = QtWidgets.QVBoxLayout(nav_content)
        nav_column.setContentsMargins(0, 0, 0, 0)
        nav_column.setSpacing(4)
        nav_icons = (
            "home", "home", "clock", "clock", "pulse", "bank", "trophy", "map",
            "box", "box", "bell", "settings", "box",
        )

        for index, (title, _) in enumerate(PAGES):
            if title == "Configurações":
                separator = QtWidgets.QFrame(objectName="navSeparator")
                separator.setFixedHeight(1)
                nav_column.addSpacing(8)
                nav_column.addWidget(separator)
                nav_column.addSpacing(8)
            button = QtWidgets.QPushButton(title)
            button.setObjectName(f"nav{index}")
            button.setCheckable(True)
            button.setIcon(_navigation_icon(nav_icons[index]))
            button.setIconSize(QtCore.QSize(20, 20))
            button.setMinimumHeight(46)
            button.clicked.connect(lambda checked=False, page=index: self.page_stack.setCurrentIndex(page))
            self.nav_group.addButton(button, index)
            self.nav_buttons.append(button)
            nav_column.addWidget(button)
        self.nav_buttons[0].setChecked(True)
        nav_column.addStretch(1)
        nav_scroll.setWidget(nav_content)
        column.addWidget(nav_scroll, 1)
        return sidebar

    def _build_clients(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QWidget(objectName="clientBar")
        row = QtWidgets.QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.client_group = QtWidgets.QButtonGroup(bar)
        self.client_group.setExclusive(True)
        self.client_buttons: list[QtWidgets.QPushButton] = []
        for index in range(CLIENT_SLOT_COUNT):
            button = _ClientButton(_client_label(index))
            button.setIcon(_status_dot_icon())
            button.setIconSize(QtCore.QSize(10, 10))
            button.setProperty("client", True)
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.setToolTip("Clique duas vezes para definir o UID deste cliente.")
            button.clicked.connect(lambda checked=False, client=index: self._select_client(client))
            button.double_clicked.connect(
                lambda client=index: self._choose_client_uid(client)
            )
            self.client_group.addButton(button, index)
            self.client_buttons.append(button)
            row.addWidget(button)
            button.setVisible(index in self.visible_client_slots)
        self.add_client_button = QtWidgets.QPushButton("+  Adicionar cliente")
        self.add_client_button.setObjectName("addClient")
        self.add_client_button.clicked.connect(
            lambda checked=False: self._add_client_slot()
        )
        row.addWidget(self.add_client_button)
        self.client_source = _label("PC local", "clientSource")
        row.addWidget(self.client_source)
        self.remove_client_button = QtWidgets.QPushButton("Excluir cliente")
        self.remove_client_button.setObjectName("removeClient")
        self.remove_client_button.setToolTip(
            "Remove o cliente da interface sem apagar sessões ou dados capturados."
        )
        self.remove_client_button.clicked.connect(self._remove_selected_client)
        row.addWidget(self.remove_client_button)
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

    def _build_monitoring_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageMonitoramento")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        column.addWidget(_label("Monitoramento", "title"))
        self.monitor_tabs = QtWidgets.QTabWidget(objectName="monitorTabs")
        for mode, title in (("pve", "PvE"), ("pvp", "PvP"), ("boss", "Boss")):
            self.monitor_tabs.addTab(
                self._build_combat_page(mode, embedded=True), title
            )
        self.monitor_tabs.currentChanged.connect(self._monitoring_tab_changed)
        column.addWidget(self.monitor_tabs, 1)
        return page

    def _build_combat_page(
        self, mode: str, *, embedded: bool = False
    ) -> QtWidgets.QWidget:
        if not hasattr(self, "combat_widgets"):
            self.combat_widgets: dict[str, list[dict[str, Any]]] = {}
            self.combat_page_layouts: dict[str, dict[str, Any]] = {}
        title = {"pve": "Monitor PvE", "pvp": "Monitor PvP", "boss": "Boss"}[mode]
        page = QtWidgets.QWidget(objectName=f"pageCombat{mode.upper()}")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(8 if embedded else 0, 8 if embedded else 0, 8 if embedded else 0, 8 if embedded else 0)
        column.setSpacing(12)
        if not embedded:
            column.addWidget(_label(title, "title"))
        client_tabs = None
        if mode in {"pve", "pvp"}:
            client_tabs = QtWidgets.QTabBar()
            client_tabs.setExpanding(False)
            for index in range(CLIENT_SLOT_COUNT):
                client_tabs.addTab(_client_label(index))
                client_tabs.setTabVisible(index, index < PC_SLOT_COUNT)
            column.addWidget(client_tabs)
        controls = QtWidgets.QHBoxLayout()
        monitor_shortcut = DEFAULT_GLOBAL_SHORTCUTS[f"monitor_{mode}"]
        client_suffix = f" {_client_label(0)}" if client_tabs is not None else ""
        enabled = QtWidgets.QPushButton(
            f"Ligar monitor{client_suffix}  {monitor_shortcut}"
        )
        enabled.setCheckable(True)
        enabled.toggled.connect(
            lambda checked, selected=mode: self._toggle_monitor(selected, checked)
        )
        interval = (
            QtWidgets.QDoubleSpinBox()
            if mode == "pvp"
            else QtWidgets.QSpinBox()
        )
        interval.setRange(0.5 if mode == "pvp" else 1, 60)
        if mode == "pvp":
            interval.setDecimals(1)
            interval.setSingleStep(0.5)
        interval.setValue(1 if mode == "pvp" else 2 if mode == "boss" else 3)
        interval.setSuffix(" s")
        interval.valueChanged.connect(
            lambda _value, selected=mode: self._monitor_interval_changed(selected)
        )
        controls.addWidget(enabled)
        controls.addWidget(_label("Atualizar a cada", "muted"))
        controls.addWidget(interval)
        focus = None
        if mode in {"pvp", "boss"}:
            focus = QtWidgets.QCheckBox("Modo foco")
            focus.setToolTip(
                "Mantém os monitores ligados no intervalo rápido e adia as "
                "demais leituras para 5 minutos."
            )
            focus.toggled.connect(
                lambda _checked, selected=mode: self._monitor_focus_changed(selected)
            )
            controls.addWidget(focus)
        overlay = None
        hostile_overlay = None
        non_hostile_overlay = None
        dps_overlay = None
        if mode in {"pvp", "boss"}:
            shortcut = "Ctrl+Shift+F6" if mode == "pvp" else "Ctrl+Shift+F7"
            overlay_label = "Overlay alvo atual" if mode == "pvp" else "Overlay de vida"
            overlay = QtWidgets.QPushButton(f"{overlay_label}  {shortcut}")
            overlay.setCheckable(True)
            if mode == "pvp":
                overlay.setToolTip(
                    "Arraste o overlay com o botão esquerdo para mudar sua posição."
                )
            overlay.toggled.connect(
                (lambda checked: self._toggle_pvp_overlay(checked, "target"))
                if mode == "pvp" else self._toggle_boss_overlay
            )
            controls.addWidget(overlay)
            if mode == "pvp":
                hostile_overlay = QtWidgets.QPushButton("Overlay hostis")
                hostile_overlay.setCheckable(True)
                hostile_overlay.toggled.connect(
                    lambda checked: self._toggle_pvp_overlay(checked, "hostile")
                )
                non_hostile_overlay = QtWidgets.QPushButton("Overlay não hostis")
                non_hostile_overlay.setCheckable(True)
                non_hostile_overlay.toggled.connect(
                    lambda checked: self._toggle_pvp_overlay(checked, "non_hostile")
                )
                controls.addWidget(hostile_overlay)
                controls.addWidget(non_hostile_overlay)
            if mode == "boss":
                dps_overlay = QtWidgets.QPushButton("Overlay de DPS")
                dps_overlay.setCheckable(True)
                dps_overlay.setToolTip(
                    "Arraste o overlay com o botão esquerdo para mudar sua posição."
                )
                dps_overlay.toggled.connect(self._toggle_boss_dps_overlay)
                controls.addWidget(dps_overlay)
        controls.addStretch(1)
        column.addLayout(controls)
        self.monitor_controls[mode] = {
            "enabled": enabled,
            "interval": interval,
            "focus": focus,
            "overlay": overlay,
            "hostile_overlay": hostile_overlay,
            "non_hostile_overlay": non_hostile_overlay,
            "dps_overlay": dps_overlay,
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
        for index in range(CLIENT_SLOT_COUNT):
            card = QtWidgets.QFrame(objectName="panel")
            layout = QtWidgets.QVBoxLayout(card)
            layout.setContentsMargins(20, 16, 20, 16)
            layout.setSpacing(10)
            heading = _label(f"{_client_label(index)} · aguardando personagem", "subtitle")
            target = _label("Último alvo confirmado: —", "subtitle")
            status = _label("Aguardando eventos confirmados de combate.", "muted")
            progress = QtWidgets.QProgressBar()
            progress.setRange(0, 1000)
            progress.setValue(0)
            progress.setTextVisible(False)
            self_health = None
            self_progress = None
            if mode == "pve":
                self_health = _label("Sua vida: —", "muted")
                self_progress = QtWidgets.QProgressBar(objectName="playerHealthProgress")
                self_progress.setRange(0, 1000)
                self_progress.setValue(0)
                self_progress.setTextVisible(False)
                self_progress.setToolTip(
                    "Última vida do personagem confirmada pelo monitor PvE."
                )
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
            if mode == "pvp":
                layout.addWidget(target)
                layout.addWidget(progress)
                layout.addLayout(stats)
            nearby_layout = None
            nearby_empty = None
            if mode == "pvp":
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
            if mode == "pve":
                layout.addWidget(self_health)
                layout.addWidget(self_progress)
                layout.addWidget(target)
                layout.addWidget(progress)
                layout.addLayout(stats)
            layout.addWidget(status)
            content_layout.addWidget(card, index, 0, 1, 2)
            if index >= PC_SLOT_COUNT or (client_tabs is not None and index):
                card.hide()
            cards.append(card)
            widgets.append(
                {
                    "heading": heading,
                    "target": target,
                    "status": status,
                    "progress": progress,
                    "self_health": self_health,
                    "self_progress": self_progress,
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
        self.alert_item_drop = QtWidgets.QCheckBox(
            "Avisar ao receber drop de item confirmado"
        )
        self.alert_item_drop.setToolTip(
            "Durante uma captura ativa, ignora recompensas de EXP, créditos "
            "e contribuição."
        )
        form.addRow("Drops", self.alert_item_drop)
        drop_categories = QtWidgets.QWidget()
        drop_categories_layout = QtWidgets.QHBoxLayout(drop_categories)
        drop_categories_layout.setContentsMargins(0, 0, 0, 0)
        drop_categories_layout.setSpacing(8)
        self.alert_drop_rarities: dict[int, QtWidgets.QCheckBox] = {}
        for grade, label in ((0, "Sem categoria"), *DROP_RARITY_LABELS.items()):
            option = QtWidgets.QCheckBox(label)
            option.setChecked(True)
            self.alert_drop_rarities[int(grade)] = option
            drop_categories_layout.addWidget(option)
        drop_categories_layout.addStretch(1)
        form.addRow("Raridades", drop_categories)
        drop_types = QtWidgets.QWidget()
        drop_types_layout = QtWidgets.QGridLayout(drop_types)
        drop_types_layout.setContentsMargins(0, 0, 0, 0)
        drop_types_layout.setHorizontalSpacing(12)
        drop_types_layout.setVerticalSpacing(4)
        self.alert_drop_types: dict[str, QtWidgets.QCheckBox] = {}
        for index, (category, label) in enumerate(
            DROP_ALERT_CATEGORY_LABELS.items()
        ):
            option = QtWidgets.QCheckBox(label)
            option.setChecked(True)
            self.alert_drop_types[category] = option
            drop_types_layout.addWidget(option, index // 4, index % 4)
        form.addRow("Tipos de item", drop_types)
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
        self.alert_threat = QtWidgets.QCheckBox(
            "Avisar enquanto houver inimigo confirmado próximo"
        )
        form.addRow("Ameaça", self.alert_threat)
        self.alert_farm_started = QtWidgets.QCheckBox(
            "Avisar ao entrar no estado Farm"
        )
        form.addRow("Farm", self.alert_farm_started)
        self.alert_teleporting = QtWidgets.QCheckBox(
            "Avisar ao iniciar um teleporte confirmado"
        )
        form.addRow("Teleporte", self.alert_teleporting)
        self.alert_cooldown_seconds = QtWidgets.QSpinBox()
        self.alert_cooldown_seconds.setRange(5, 300)
        self.alert_cooldown_seconds.setValue(10)
        self.alert_cooldown_seconds.setSuffix(" s")
        form.addRow("Intervalo mínimo", self.alert_cooldown_seconds)
        self.alert_sound = QtWidgets.QCheckBox("Som do sistema")
        self.alert_sound.setChecked(True)
        form.addRow("Aviso sonoro", self.alert_sound)
        self.alert_sound_file = ""
        self.alert_sound_name = QtWidgets.QLineEdit()
        self.alert_sound_name.setReadOnly(True)
        self.alert_sound_name.setPlaceholderText("Som padrão do sistema")
        choose_sound = QtWidgets.QPushButton("Escolher WAV")
        choose_sound.clicked.connect(self._choose_alert_sound)
        test_sound = QtWidgets.QPushButton("Testar")
        test_sound.clicked.connect(self._test_alert_sound)
        remove_sound = QtWidgets.QPushButton("Usar padrão")
        remove_sound.clicked.connect(self._clear_alert_sound)
        sound_row = QtWidgets.QHBoxLayout()
        sound_row.addWidget(self.alert_sound_name, 1)
        sound_row.addWidget(choose_sound)
        sound_row.addWidget(test_sound)
        sound_row.addWidget(remove_sound)
        form.addRow("Som personalizado", sound_row)
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
        column.setSpacing(8)
        self.overview_status = _label("Lendo a sessão mais recente…", "muted")
        self.overview_status.hide()
        column.addWidget(self.overview_status)

        scroll = QtWidgets.QScrollArea(objectName="pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        content = QtWidgets.QWidget(objectName="scrollContent")
        self.overview_grid = QtWidgets.QGridLayout(content)
        self.overview_grid.setContentsMargins(0, 0, 8, 0)
        self.overview_grid.setHorizontalSpacing(12)
        self.overview_grid.setVerticalSpacing(12)

        def card(title: str, icon: str) -> tuple[QtWidgets.QFrame, QtWidgets.QVBoxLayout]:
            frame = QtWidgets.QFrame(objectName="dashboardCard")
            layout = QtWidgets.QVBoxLayout(frame)
            layout.setContentsMargins(18, 16, 18, 16)
            layout.setSpacing(9)
            header = QtWidgets.QHBoxLayout()
            icon_label = QtWidgets.QLabel()
            icon_label.setPixmap(_navigation_icon(icon, 19).pixmap(19, 19))
            icon_label.setFixedSize(22, 22)
            header.addWidget(icon_label)
            header.addWidget(_label(title, "cardTitle"))
            header.addStretch(1)
            layout.addLayout(header)
            return frame, layout

        self.session_card, session = card("Sessão atual", "clock")
        self.character_name = _label("Aguardando personagem", "cardIdentity")
        self.character_details = _label("Nível —", "muted")
        session.addWidget(self.character_name)
        session.addWidget(self.character_details)
        self.session_duration = _label("00:00:00", "sessionTime")
        session.addWidget(self.session_duration)
        exp_row = QtWidgets.QHBoxLayout()
        exp_row.addWidget(_label("EXP", "muted"))
        exp_row.addStretch(1)
        self.metric_labels: dict[str, QtWidgets.QLabel] = {}
        self.exp_percent = _label("—", "metricCompact")
        self.metric_labels["exp_percent"] = self.exp_percent
        exp_row.addWidget(self.exp_percent)
        session.addLayout(exp_row)
        self.exp_progress = QtWidgets.QProgressBar(objectName="goldProgress")
        self.exp_progress.setRange(0, 10000)
        self.exp_progress.setTextVisible(False)
        session.addWidget(self.exp_progress)
        session_stats = QtWidgets.QHBoxLayout()
        session_stats.setSpacing(0)
        for index, (key, caption) in enumerate((
            ("exp_hour_percent", "EXP/h"),
            ("credits", "Créditos"),
            ("kills", "Mobs"),
        )):
            if index:
                divider = QtWidgets.QFrame(objectName="metricDivider")
                divider.setFixedWidth(1)
                session_stats.addWidget(divider)
            cell = QtWidgets.QVBoxLayout()
            label = _label(caption, "muted")
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            value = _label("—", "metricValue")
            value.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.metric_labels[key] = value
            cell.addWidget(label)
            cell.addWidget(value)
            session_stats.addLayout(cell, 1)
        session.addLayout(session_stats)
        self.session_epic_breakdown = _label("Épicos  —", "metricCompact")
        self.session_epic_breakdown.setWordWrap(True)
        session.addWidget(self.session_epic_breakdown)

        for key in (
            "exp", "exp_missing", "exp_gained", "exp_hour", "credits_hour",
            "contribution", "contribution_hour", "diamonds", "finalizations",
            "loot", "common", "uncommon", "rare", "epic",
        ):
            hidden = _label("—", "data")
            hidden.setParent(page)
            hidden.hide()
            self.metric_labels[key] = hidden
        self.character_icon = QtWidgets.QLabel("—", objectName="characterIcon", parent=page)
        self.rover_icon = QtWidgets.QLabel("—", objectName="roverIcon", parent=page)
        self.rover_name = _label("Rover —", "muted")
        self.character_icon.setFixedSize(72, 72)
        self.rover_icon.setFixedSize(96, 72)
        equipment_row = QtWidgets.QHBoxLayout()
        equipment_row.addWidget(self.character_icon)
        equipment_row.addWidget(self.rover_icon)
        equipment_row.addWidget(self.rover_name, 1)
        session.addLayout(equipment_row)

        self.program_status_card = QtWidgets.QFrame(parent=page)
        self.program_status_card.hide()
        status_heading = QtWidgets.QHBoxLayout()
        status_heading.addWidget(_label("Status", "muted"))
        status_heading.addStretch(1)
        self.dashboard_status = _label("Ocioso  •", "statusHero")
        self.dashboard_status.setObjectName("dashboardStatus")
        status_heading.addWidget(self.dashboard_status)
        session.addLayout(status_heading)
        self.dashboard_activity = _label("Monitor aguardando", "statusLine")
        self.dashboard_threat = _label("Sem ameaça", "statusLine")
        self.dashboard_attack = _label("Não sendo atacado", "statusLine")
        status_details = QtWidgets.QHBoxLayout()
        status_details.addWidget(self.dashboard_activity)
        status_details.addWidget(self.dashboard_threat)
        status_details.addWidget(self.dashboard_attack)
        session.addLayout(status_details)

        self.nearby_mobs_card, nearby_mobs = card("Mobs próximos", "pulse")
        self.overview_mobs_status = _label(
            "Nenhum mob próximo confirmado.", "muted"
        )
        nearby_mobs.addWidget(self.overview_mobs_status)
        self.overview_mobs_table = QtWidgets.QTableWidget(0, 3)
        self.overview_mobs_table.setObjectName("overviewMobsTable")
        self.overview_mobs_table.setHorizontalHeaderLabels(
            ("Mob", "Nível", "Vida máxima")
        )
        self.overview_mobs_table.verticalHeader().hide()
        self.overview_mobs_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.overview_mobs_table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.NoSelection
        )
        self.overview_mobs_table.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.overview_mobs_table.setMinimumHeight(135)
        self.overview_mobs_table.setMaximumHeight(175)
        mobs_header = self.overview_mobs_table.horizontalHeader()
        mobs_header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        mobs_header.setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        mobs_header.setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        nearby_mobs.addWidget(self.overview_mobs_table, 1)
        self.overview_mobs_table.hide()

        self.subsession_card, subsession = card("Subsessão ativa", "clock")
        self.subsession_card.setParent(content)
        self._overview_has_subsession = False
        self.subsession_badge = _label("Inativa", "muted")
        subsession_header = subsession.itemAt(0).layout()
        subsession_header.addWidget(self.subsession_badge)
        self.subsession_card_fields_button = QtWidgets.QToolButton()
        self.subsession_card_fields_button.setText("Informações")
        self.subsession_card_fields_button.setToolTip(
            "Escolha no card as mesmas informações disponíveis nas colunas."
        )
        self.subsession_card_fields_button.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup
        )
        subsession_fields_menu = QtWidgets.QMenu(self.subsession_card_fields_button)
        configured_card_fields = self.preferences.get("subsession_card_fields")
        selected_card_fields = (
            {
                str(key) for key in configured_card_fields
                if str(key) in SUBSESSION_COLUMN_INDEX and str(key) != "select"
            }
            if isinstance(configured_card_fields, list)
            else set(SUBSESSION_CARD_DEFAULT_FIELDS)
        )
        self.subsession_card_field_actions: dict[str, QtGui.QAction] = {}
        for key, label_text, _width, _visible in SUBSESSION_COLUMNS[1:]:
            action = subsession_fields_menu.addAction(label_text)
            action.setCheckable(True)
            action.setChecked(key in selected_card_fields)
            if key == "exp_hour_percent":
                action.setVisible(False)
            action.toggled.connect(
                lambda checked, field=key: self._set_subsession_card_field_visible(
                    field, checked
                )
            )
            self.subsession_card_field_actions[key] = action
        subsession_fields_menu.addSeparator()
        subsession_fields_menu.addAction(
            "Restaurar padrão", self._reset_subsession_card_fields
        )
        self.subsession_card_fields_button.setMenu(subsession_fields_menu)
        subsession_header.addWidget(self.subsession_card_fields_button)
        self.subsession_empty = _label(
            "Inicie uma subsessão para acompanhar este cliente.", "muted"
        )
        self.subsession_empty.setWordWrap(True)
        subsession.addWidget(self.subsession_empty)
        self.subsession_card_fields = QtWidgets.QGridLayout()
        self.subsession_card_fields.setHorizontalSpacing(12)
        self.subsession_card_fields.setVerticalSpacing(8)
        self.subsession_card_field_widgets: dict[str, QtWidgets.QWidget] = {}
        self.subsession_card_values: dict[str, QtWidgets.QLabel] = {}
        for index, (key, label_text, _width, _visible) in enumerate(
            SUBSESSION_COLUMNS[1:]
        ):
            field = QtWidgets.QWidget()
            field_layout = QtWidgets.QVBoxLayout(field)
            field_layout.setContentsMargins(0, 0, 0, 0)
            field_layout.setSpacing(1)
            caption = _label(
                "XP/h (bruto e %)" if key == "exp_hour" else label_text,
                "muted",
            )
            value = _label("—", "metricValue")
            value.setWordWrap(key in {"name", "map", "spot", "mobs", "levels", "context"})
            field_layout.addWidget(caption)
            field_layout.addWidget(value)
            self.subsession_card_fields.addWidget(field, index // 2, index % 2)
            self.subsession_card_field_widgets[key] = field
            self.subsession_card_values[key] = value
        subsession.addLayout(self.subsession_card_fields)
        self.active_subsession = self.subsession_card_values["name"]
        self.active_subsession_duration = self.subsession_card_values["time"]
        self.subsession_map_line = self.subsession_card_values["map"]
        self.subsession_mobs_line = self.subsession_card_values["mobs"]
        self.subsession_levels_line = self.subsession_card_values["levels"]
        self.subsession_metrics = {
            key: self.subsession_card_values[key]
            for key in ("kills", "exp_percent", "exp_hour_percent")
        }
        self._apply_subsession_card_fields(selected_card_fields)
        self.view_subsession_button = QtWidgets.QPushButton(
            "Abrir subsessões  →", objectName="linkButton"
        )
        self.view_subsession_button.clicked.connect(self._open_active_subsession)
        subsession.addWidget(self.view_subsession_button)

        self.map_card, map_layout = card("Mapa e proximidade", "map")
        map_toolbar = QtWidgets.QHBoxLayout()
        map_toolbar.setSpacing(6)
        map_toolbar.addStretch(1)
        self.overview_map_zoom_out = QtWidgets.QPushButton("−")
        self.overview_map_zoom_out.setObjectName("mapToolButton")
        self.overview_map_zoom_out.setToolTip("Diminuir zoom")
        self.overview_map_zoom_out.setAccessibleName("Diminuir zoom do mapa")
        self.overview_map_zoom_out.setFixedWidth(38)
        self.overview_map_zoom = _label("100%", "muted")
        self.overview_map_zoom.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignCenter
        )
        self.overview_map_zoom.setMinimumWidth(48)
        self.overview_map_zoom_in = QtWidgets.QPushButton("+")
        self.overview_map_zoom_in.setObjectName("mapToolButton")
        self.overview_map_zoom_in.setToolTip("Aumentar zoom")
        self.overview_map_zoom_in.setAccessibleName("Aumentar zoom do mapa")
        self.overview_map_zoom_in.setFixedWidth(38)
        self.overview_map_focus = QtWidgets.QPushButton("Focar personagem")
        self.overview_map_focus.setObjectName("mapFocusButton")
        self.overview_map_focus.setToolTip(
            "Centralizar o mapa novamente na posição atual do personagem"
        )
        map_toolbar.addWidget(self.overview_map_zoom_out)
        map_toolbar.addWidget(self.overview_map_zoom)
        map_toolbar.addWidget(self.overview_map_zoom_in)
        map_toolbar.addWidget(self.overview_map_focus)
        map_layout.addLayout(map_toolbar)
        for control in (
            self.overview_map_zoom_out,
            self.overview_map_zoom,
            self.overview_map_zoom_in,
            self.overview_map_focus,
        ):
            control.hide()
        map_identity = QtWidgets.QHBoxLayout()
        map_identity_text = QtWidgets.QVBoxLayout()
        self.overview_map_name = _label("Mapa não identificado", "cardIdentity")
        self.overview_map_region = _label("Região —", "muted")
        map_identity_text.addWidget(self.overview_map_name)
        map_identity_text.addWidget(self.overview_map_region)
        map_identity.addLayout(map_identity_text, 1)
        self.overview_coordinates = _label("—, —", "mapCoordinates")
        map_identity.addWidget(self.overview_coordinates)
        map_layout.addLayout(map_identity)
        self.overview_map_preview = _MapPreview(
            show_player_labels=False,
            interactive=False,
        )
        self.overview_map_preview.setMaximumSize(420, 420)
        self.overview_map_preview.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self.overview_map_zoom_out.clicked.connect(
            self.overview_map_preview.zoom_out
        )
        self.overview_map_zoom_in.clicked.connect(
            self.overview_map_preview.zoom_in
        )
        self.overview_map_focus.clicked.connect(
            self.overview_map_preview.focus_on_character
        )
        self.overview_map_preview.view_changed.connect(
            lambda zoom, focused: self.overview_map_zoom.setText(
                f"{zoom}%" + (" · foco" if focused else "")
            )
        )
        self.overview_map_preview.view_changed.emit(100, False)
        map_layout.addWidget(
            self.overview_map_preview,
            0,
            QtCore.Qt.AlignmentFlag.AlignHCenter,
        )
        map_details = QtWidgets.QVBoxLayout()
        self.overview_map_state = _label("Aguardando coordenadas", "muted")
        self.overview_nearby_players = _label("Outros jogadores  —", "detailLine")
        self.overview_nearby_names = _label("Nomes: —", "muted")
        self.overview_nearby_names.setWordWrap(True)
        map_details.addWidget(self.overview_map_state)
        map_details.addWidget(self.overview_nearby_players)
        map_details.addWidget(self.overview_nearby_names)
        map_layout.addLayout(map_details)

        self.drops_card, drops = card("Drops recentes", "box")
        self.overview_drop_rows: list[tuple[QtWidgets.QLabel, QtWidgets.QLabel, QtWidgets.QLabel]] = []
        for _ in range(3):
            row_widget = QtWidgets.QFrame(objectName="dropRow")
            row = QtWidgets.QHBoxLayout(row_widget)
            row.setContentsMargins(8, 6, 8, 6)
            marker = QtWidgets.QLabel("", objectName="dropIcon")
            marker.setFixedSize(32, 32)
            marker.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            marker.setPixmap(_navigation_icon("box", 22).pixmap(22, 22))
            name = _label("Aguardando drop", "dropName")
            age = _label("—", "muted")
            row.addWidget(marker)
            row.addWidget(name, 1)
            row.addWidget(age)
            drops.addWidget(row_widget)
            self.overview_drop_rows.append((marker, name, age))
        drops.addStretch(1)
        self.view_drops_button = QtWidgets.QPushButton(
            "Ver todos os drops  →", objectName="linkButton"
        )
        self.view_drops_button.clicked.connect(self._open_drops_page)
        drops.addWidget(self.view_drops_button)

        self.health_card, health = card("Saúde e memória", "pulse")
        health_body = QtWidgets.QHBoxLayout()
        health_stats = QtWidgets.QVBoxLayout()
        self.overview_memory_limit = _label("Limite  —", "healthLine")
        self.overview_memory_use = _label("Em uso  —", "healthLineOk")
        self.overview_queue = _label("Fila  —", "healthLineInfo")
        self.overview_checkpoint = _label("Checkpoint  —", "healthLineOk")
        for widget in (
            self.overview_memory_limit,
            self.overview_memory_use,
            self.overview_queue,
            self.overview_checkpoint,
        ):
            health_stats.addWidget(widget)
        health_stats.addStretch(1)
        health_body.addLayout(health_stats, 1)
        self.memory_sparkline = _MemorySparkline()
        health_body.addWidget(self.memory_sparkline, 2)
        health.addLayout(health_body)

        self.overview_cards = (
            self.session_card,
            self.subsession_card,
            self.map_card,
            self.health_card,
        )
        self.nearby_mobs_card.hide()
        self.drops_card.hide()
        self._sync_overview_layout()
        scroll.setWidget(content)
        column.addWidget(scroll, 1)
        return page

    def _build_sessions_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageSessoes")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        column.addWidget(_label("Sessões", "title"))
        column.addWidget(_label(
            "Acompanhe a sessão atual e envie dados já lidos.", "muted"
        ))
        column.addWidget(self._build_sends_page(embedded=True), 1)
        return page

    def _build_general_summary_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageResumoGeral")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        column.addWidget(_label("Resumo Geral", "title"))
        column.addWidget(_label(
            "Visão consolidada de todos os clientes adicionados.", "muted"
        ))
        scroll = QtWidgets.QScrollArea(objectName="pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        content = QtWidgets.QWidget(objectName="scrollContent")
        grid = QtWidgets.QGridLayout(content)
        grid.setContentsMargins(0, 0, 8, 0)
        grid.setSpacing(12)
        grid.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignTop
            | QtCore.Qt.AlignmentFlag.AlignLeft
        )
        self.general_summary_cards: list[dict[str, Any]] = []
        for index in range(CLIENT_SLOT_COUNT):
            frame = QtWidgets.QFrame(objectName="dashboardCard")
            frame.setMinimumWidth(420)
            frame.setMaximumWidth(560)
            frame.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Preferred,
                QtWidgets.QSizePolicy.Policy.Maximum,
            )
            layout = QtWidgets.QVBoxLayout(frame)
            layout.setContentsMargins(14, 12, 14, 12)
            layout.setSpacing(8)
            header = QtWidgets.QHBoxLayout()
            identity = QtWidgets.QVBoxLayout()
            client = _label(self._client_name(index), "muted")
            character = _label("Aguardando personagem", "cardIdentity")
            identity.addWidget(client)
            identity.addWidget(character)
            header.addLayout(identity, 1)
            diamonds_box = QtWidgets.QVBoxLayout()
            diamonds_box.addWidget(_label("Diamantes", "muted"))
            diamonds = _label("—", "metricCompact")
            diamonds.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
            diamonds_box.addWidget(diamonds)
            header.addLayout(diamonds_box)
            layout.addLayout(header)

            equipment = QtWidgets.QHBoxLayout()
            equipment.setSpacing(10)
            class_icon = QtWidgets.QLabel("—", objectName="characterIcon")
            class_icon.setFixedSize(46, 46)
            class_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            equipment.addWidget(class_icon)
            class_text = QtWidgets.QVBoxLayout()
            class_text.setSpacing(0)
            class_name = _label("Classe —", "metricCompact")
            biosuit_name = _label("Biosuit —", "muted")
            class_text.addWidget(class_name)
            class_text.addWidget(biosuit_name)
            equipment.addLayout(class_text, 1)
            rover_icon = QtWidgets.QLabel("—", objectName="roverIcon")
            rover_icon.setFixedSize(52, 46)
            rover_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            equipment.addWidget(rover_icon)
            rover_name = _label("Rover —", "metricCompact")
            rover_name.setMinimumWidth(90)
            equipment.addWidget(rover_name)
            layout.addLayout(equipment)

            exp_row = QtWidgets.QHBoxLayout()
            exp_row.setSpacing(8)
            exp_row.addWidget(_label("EXP atual", "muted"))
            exp_progress = QtWidgets.QProgressBar(objectName="summaryExpBar")
            exp_progress.setRange(0, 10_000)
            exp_progress.setValue(0)
            exp_progress.setTextVisible(False)
            exp_progress.setFixedHeight(9)
            exp_row.addWidget(exp_progress, 1)
            exp_percent = _label("—", "metricCompact")
            exp_percent.setMinimumWidth(54)
            exp_percent.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
            exp_row.addWidget(exp_percent)
            layout.addLayout(exp_row)

            values: dict[str, QtWidgets.QLabel] = {}
            metrics = QtWidgets.QGridLayout()
            metrics.setHorizontalSpacing(12)
            metrics.setVerticalSpacing(6)
            for field_index, (key, caption) in enumerate((
                ("duration", "Tempo de sessão"),
                ("session_exp", "EXP da sessão"),
                ("credits", "Créditos"),
                ("contribution", "Contribuição"),
            )):
                cell = QtWidgets.QWidget()
                cell_layout = QtWidgets.QVBoxLayout(cell)
                cell_layout.setContentsMargins(0, 0, 0, 0)
                cell_layout.setSpacing(1)
                cell_layout.addWidget(_label(caption, "muted"))
                value = _label("—", "metricCompact")
                value.setWordWrap(True)
                cell_layout.addWidget(value)
                metrics.addWidget(cell, field_index // 2, field_index % 2)
                values[key] = value
            layout.addLayout(metrics)
            grid.addWidget(frame, index // 2, index % 2)
            self.general_summary_cards.append({
                "frame": frame,
                "client": client,
                "character": character,
                "class_icon": class_icon,
                "class_name": class_name,
                "biosuit_name": biosuit_name,
                "rover_icon": rover_icon,
                "rover_name": rover_name,
                "diamonds": diamonds,
                "exp_progress": exp_progress,
                "exp_percent": exp_percent,
                "values": values,
            })
        scroll.setWidget(content)
        column.addWidget(scroll, 1)
        return page

    def _render_general_summary(self) -> None:
        if not hasattr(self, "general_summary_cards"):
            return
        now_ns = time.time_ns()
        session_ended_ns = (self.snapshot.get("stats") or {}).get("ended_ns")
        session_live = bool(
            self.capture_engine
            and self.capture_engine.active
            and self.capture_engine.current_session == self.snapshot.get("session_id")
        )
        for index, card in enumerate(self.general_summary_cards):
            card["frame"].setVisible(index in self.visible_client_slots)
            if index not in self.visible_client_slots:
                continue
            character, summary, historical = self._overview_character(index)
            character = character or {}
            name = str(character.get("name") or "").strip()
            card["client"].setText(self._client_name(index))
            card["character"].setText(name or "Aguardando personagem")
            if historical and name:
                card["character"].setToolTip("Último estado conhecido")
            self._set_character_icon(
                str(summary.get("character_class") or ""),
                int(summary.get("biosuit_grade") or 0),
                card["class_icon"],
            )
            self._set_rover_icon(
                int(summary.get("rover_item_index") or 0),
                int(summary.get("rover_grade") or 0),
                str(summary.get("rover_name") or ""),
                card["rover_icon"],
            )
            started_ns = summary.get("recognized_at_ns")
            duration = (
                max(0, int((
                    (now_ns if session_live else int(session_ended_ns or now_ns))
                    - started_ns
                ) / 1_000_000_000))
                if isinstance(started_ns, int) else 0
            )
            percent = summary.get("exp_percent")
            gained = summary.get("exp_gained")
            gained_percent = summary.get("exp_gained_percent")
            credits_total = summary.get("credits_total")
            credits_gained = summary.get("credits")
            contribution = summary.get("contribution")
            hours = duration / 3600 if duration else 0
            contribution_hour = (
                float(contribution) / hours
                if hours and isinstance(contribution, (int, float))
                else None
            )
            values = card["values"]
            card["diamonds"].setText(self._format_value(summary.get("diamonds")))
            card["class_name"].setText(
                str(summary.get("character_class") or "Classe —")
            )
            card["biosuit_name"].setText(
                str(summary.get("biosuit_name") or "Biosuit —")
            )
            card["rover_name"].setText(
                str(summary.get("rover_name") or "Rover —")
            )
            card["exp_percent"].setText(self._format_value(percent, "%"))
            card["exp_progress"].setValue(
                max(0, min(10_000, round(float(percent) * 100)))
                if isinstance(percent, (int, float)) else 0
            )
            values["duration"].setText(
                f"{duration // 3600:02d}:{duration // 60 % 60:02d}:{duration % 60:02d}"
            )
            values["session_exp"].setText(
                f"{self._format_value(gained)} ({self._format_value(gained_percent, '%')})"
            )
            values["credits"].setText(
                f"Total {self._format_value(credits_total)} · "
                f"Sessão +{self._format_value(credits_gained)}"
            )
            values["contribution"].setText(
                f"+{self._format_value(contribution)} · "
                f"{self._format_value(contribution_hour)}/h"
            )

    def _build_sends_page(self, *, embedded: bool = False) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageEnvios")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(
            8 if embedded else 0,
            8 if embedded else 0,
            8 if embedded else 0,
            8 if embedded else 0,
        )
        column.setSpacing(10)
        if not embedded:
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
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(8)
        self.send_status_labels: dict[str, QtWidgets.QLabel] = {}
        self.send_buttons: dict[tuple[str, int], QtWidgets.QPushButton] = {}
        domains = (
            ("character", "Personagem + equipamentos", False),
            ("inventory", "Inventário", False),
            ("market", "Mercado", True),
            ("codex", "Codex", False),
            ("memory_chips", "Memory Chips", False),
            ("all", "Tudo do cliente", False),
        )
        for index, (mode, title, general) in enumerate(domains):
            card = QtWidgets.QFrame(objectName="panel")
            card_layout = QtWidgets.QVBoxLayout(card)
            card_layout.setContentsMargins(16, 12, 16, 12)
            heading = QtWidgets.QHBoxLayout()
            heading.addWidget(_label(title, "subtitle"))
            heading.addStretch(1)
            card_layout.addLayout(heading)
            status = _label("Aguardando leitura", "info")
            self.send_status_labels[mode] = status
            card_layout.addWidget(status)
            actions = QtWidgets.QHBoxLayout()
            labels = (
                ("Enviar Mercado · geral",)
                if general
                else tuple(f"Enviar {_client_label(i)}" for i in range(CLIENT_SLOT_COUNT))
            )
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
                if target_index >= PC_SLOT_COUNT:
                    button.hide()
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

    def _build_subsessions_page(self, *, embedded: bool = False) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageSubsessões")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(
            8 if embedded else 0,
            8 if embedded else 0,
            8 if embedded else 0,
            8 if embedded else 0,
        )
        column.setSpacing(10)
        if not embedded:
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
        self.subsession_filter.addItems((
            "Todas",
            *(_client_label(index) for index in range(CLIENT_SLOT_COUNT)),
            "Em andamento",
            "Encerradas",
            "Enviadas",
            "Não enviadas",
        ))
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
        self.subsession_client.addItems(
            tuple(_client_label(index) for index in range(CLIENT_SLOT_COUNT))
        )
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
        self.subsession_auto_next = QtWidgets.QCheckBox(
            "Criar a próxima automaticamente"
        )
        self.subsession_auto_minutes = QtWidgets.QSpinBox(content)
        self.subsession_auto_minutes.setRange(5, 240)
        self.subsession_auto_minutes.setSingleStep(5)
        self.subsession_auto_minutes.setSuffix(" min")
        automatic_next = QtWidgets.QWidget()
        automatic_next_layout = QtWidgets.QHBoxLayout(automatic_next)
        automatic_next_layout.setContentsMargins(0, 0, 0, 0)
        automatic_next_layout.addWidget(self.subsession_auto_next)
        automatic_next_layout.addWidget(_label("a cada", "muted"))
        automatic_next_layout.addWidget(self.subsession_auto_minutes)
        automatic_next_layout.addStretch(1)
        self.subsession_name = QtWidgets.QLineEdit(); self.subsession_name.setPlaceholderText("Observação ou nome")
        self.subsession_end_on_teleport = QtWidgets.QCheckBox("Teleporte")
        self.subsession_end_on_death = QtWidgets.QCheckBox("Morte")
        self.subsession_end_after_no_kill = QtWidgets.QCheckBox("30 s sem kill")
        auto_end = QtWidgets.QWidget()
        auto_end_layout = QtWidgets.QHBoxLayout(auto_end)
        auto_end_layout.setContentsMargins(0, 0, 0, 0)
        for control in (
            self.subsession_end_on_teleport,
            self.subsession_end_on_death,
            self.subsession_end_after_no_kill,
        ):
            auto_end_layout.addWidget(control)
        auto_end_layout.addStretch(1)
        self.subsession_auto_context = QtWidgets.QCheckBox(
            "Preencher mapa, spot e mobs por proximidade"
        )
        self.subsession_auto_context.setToolTip(
            "Usa dados confirmados, exige três leituras estáveis por pelo menos "
            "cinco segundos e só define o spot quando houver uma correspondência única."
        )
        self.subsession_auto_context.toggled.connect(self._toggle_auto_context)
        context_controls = QtWidgets.QWidget()
        context_layout = QtWidgets.QHBoxLayout(context_controls)
        context_layout.setContentsMargins(0, 0, 0, 0)
        context_layout.setSpacing(8)
        context_layout.addWidget(self.subsession_auto_context)
        self.subsession_fill_context = QtWidgets.QPushButton(
            "Buscar localização e mobs agora"
        )
        self.subsession_fill_context.setObjectName("subsessionFillContext")
        self.subsession_fill_context.setToolTip(
            "Preenche este rascunho com o mapa e os mobs próximos confirmados "
            "do cliente selecionado. Não inicia a subsessão."
        )
        self.subsession_fill_context.clicked.connect(
            self._fill_subsession_from_current_context
        )
        context_layout.addWidget(self.subsession_fill_context)
        context_layout.addStretch(1)
        self.subsession_context_status = _label(
            "Use o botão para consultar o contexto atual sem iniciar a subsessão.",
            "muted",
        )
        self.subsession_context_status.setWordWrap(True)
        for label_text, widget in (
            ("Favorito", favorites), ("Cliente", self.subsession_client),
            ("Contexto", context_controls),
            ("", self.subsession_context_status),
            ("Observação", self.subsession_name),
            ("Mapa", self.subsession_map),
            ("Spot", self.subsession_spot),
            ("Filtrar mobs por level", filter_levels),
            ("Mobs", self.subsession_mobs),
            ("", self.subsession_select_all),
            ("Mob extra", self.subsession_other_mob),
            ("Duração (0 = manual)", self.subsession_duration),
            ("Próxima subsessão", automatic_next),
            ("Encerrar automaticamente", auto_end),
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

    def _build_drops_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageDrops")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)

        heading = QtWidgets.QHBoxLayout()
        title = QtWidgets.QVBoxLayout()
        title.setSpacing(2)
        title.addWidget(_label("Drops", "title"))
        title.addWidget(
            _label("Itens confirmados da sessão atual · até 1.000 eventos", "muted")
        )
        heading.addLayout(title)
        heading.addStretch(1)
        self.drops_search = QtWidgets.QLineEdit()
        self.drops_search.setPlaceholderText("Buscar item ou personagem")
        self.drops_search.setClearButtonEnabled(True)
        self.drops_search.setMaximumWidth(300)
        self.drops_search.textChanged.connect(self._reset_drops_page)
        heading.addWidget(self.drops_search)
        self.drops_client_filter = QtWidgets.QComboBox()
        self.drops_client_filter.addItem("Todos os clientes", "")
        for index in range(CLIENT_SLOT_COUNT):
            self.drops_client_filter.addItem(_client_label(index), _client_key(index))
        self.drops_client_filter.currentIndexChanged.connect(
            self._reset_drops_page
        )
        heading.addWidget(self.drops_client_filter)
        self.drops_rarity_filter = QtWidgets.QComboBox()
        self.drops_rarity_filter.addItem("Todas as raridades", -1)
        self.drops_rarity_filter.addItem("Sem raridade identificada", 0)
        for grade, rarity in DROP_RARITY_LABELS.items():
            self.drops_rarity_filter.addItem(rarity, grade)
        self.drops_rarity_filter.currentIndexChanged.connect(
            self._reset_drops_page
        )
        heading.addWidget(self.drops_rarity_filter)
        column.addLayout(heading)

        summary = QtWidgets.QFrame(objectName="accentPanel")
        summary_layout = QtWidgets.QHBoxLayout(summary)
        summary_layout.setContentsMargins(16, 12, 16, 12)
        self.drops_summary = _label("Nenhum drop confirmado", "info")
        summary_layout.addWidget(self.drops_summary, 1)
        self.drops_last_seen = _label("Último drop  —", "muted")
        summary_layout.addWidget(self.drops_last_seen)
        column.addWidget(summary)

        self.drops_table = QtWidgets.QTableWidget(0, 8)
        self.drops_table.setHorizontalHeaderLabels((
            "Primeiro", "Último", "Cliente", "Personagem", "Item", "Qtd.",
            "Raridade", "Ocorrências",
        ))
        self.drops_table.setIconSize(QtCore.QSize(30, 30))
        self.drops_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.drops_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.drops_table.setAlternatingRowColors(False)
        self.drops_table.verticalHeader().setVisible(False)
        drops_header = self.drops_table.horizontalHeader()
        for index in (0, 1, 2, 5, 6, 7):
            drops_header.setSectionResizeMode(
                index, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
        for index in (3, 4):
            drops_header.setSectionResizeMode(
                index, QtWidgets.QHeaderView.ResizeMode.Stretch
            )
        column.addWidget(self.drops_table, 1)

        pagination = QtWidgets.QHBoxLayout()
        self.drops_page_status = _label("Nenhum registro", "muted")
        pagination.addWidget(self.drops_page_status)
        pagination.addStretch(1)
        self.drops_page_size = QtWidgets.QComboBox()
        self.drops_page_size.addItems(("25", "50", "100"))
        self.drops_page_size.currentTextChanged.connect(self._reset_drops_page)
        pagination.addWidget(_label("Linhas", "muted"))
        pagination.addWidget(self.drops_page_size)
        previous = QtWidgets.QPushButton("Anterior")
        previous.clicked.connect(lambda: self._change_drops_page(-1))
        next_page = QtWidgets.QPushButton("Próxima")
        next_page.clicked.connect(lambda: self._change_drops_page(1))
        pagination.addWidget(previous)
        pagination.addWidget(next_page)
        column.addLayout(pagination)

        return page

    def _build_loot_announcements_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageDropsJogadores")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        heading = QtWidgets.QHBoxLayout()
        title = QtWidgets.QVBoxLayout()
        title.addWidget(_label("Drops de jogadores", "title"))
        title.addWidget(_label(
            "Anúncios do chat consolidados entre todos os clientes.", "muted"
        ))
        heading.addLayout(title)
        heading.addStretch(1)
        self.loot_announcements_search = QtWidgets.QLineEdit()
        self.loot_announcements_search.setPlaceholderText("Buscar item ou jogador")
        self.loot_announcements_search.setClearButtonEnabled(True)
        self.loot_announcements_search.setMaximumWidth(300)
        self.loot_announcements_search.textChanged.connect(
            self._reset_loot_announcements_page
        )
        heading.addWidget(self.loot_announcements_search)
        self.loot_announcements_client_filter = QtWidgets.QComboBox()
        self.loot_announcements_client_filter.addItem("Todos os clientes", "")
        for index in range(CLIENT_SLOT_COUNT):
            self.loot_announcements_client_filter.addItem(
                _client_label(index), _client_key(index)
            )
        self.loot_announcements_client_filter.currentIndexChanged.connect(
            self._reset_loot_announcements_page
        )
        heading.addWidget(self.loot_announcements_client_filter)
        self.loot_announcements_rarity_filter = QtWidgets.QComboBox()
        self.loot_announcements_rarity_filter.addItem("Todas as raridades", -1)
        self.loot_announcements_rarity_filter.addItem(
            "Sem raridade identificada", 0
        )
        for grade, rarity in DROP_RARITY_LABELS.items():
            self.loot_announcements_rarity_filter.addItem(rarity, grade)
        self.loot_announcements_rarity_filter.currentIndexChanged.connect(
            self._reset_loot_announcements_page
        )
        heading.addWidget(self.loot_announcements_rarity_filter)
        column.addLayout(heading)
        summary = QtWidgets.QFrame(objectName="accentPanel")
        summary_layout = QtWidgets.QHBoxLayout(summary)
        summary_layout.setContentsMargins(16, 12, 16, 12)
        self.loot_announcements_summary = _label("Nenhum aviso capturado", "info")
        summary_layout.addWidget(self.loot_announcements_summary)
        column.addWidget(summary)
        self.loot_announcements_table = QtWidgets.QTableWidget(0, 6)
        self.loot_announcements_table.setHorizontalHeaderLabels((
            "Horário", "Cliente", "Jogador", "Item", "Qtd.", "Raridade",
        ))
        self.loot_announcements_table.setIconSize(QtCore.QSize(30, 30))
        self.loot_announcements_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.loot_announcements_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.loot_announcements_table.verticalHeader().setVisible(False)
        announcements_header = self.loot_announcements_table.horizontalHeader()
        for index in (0, 1, 4, 5):
            announcements_header.setSectionResizeMode(
                index, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
        for index in (2, 3):
            announcements_header.setSectionResizeMode(
                index, QtWidgets.QHeaderView.ResizeMode.Stretch
            )
        column.addWidget(self.loot_announcements_table, 1)
        pagination = QtWidgets.QHBoxLayout()
        self.loot_announcements_page_status = _label("Nenhum registro", "muted")
        pagination.addWidget(self.loot_announcements_page_status)
        pagination.addStretch(1)
        self.loot_announcements_page_size = QtWidgets.QComboBox()
        self.loot_announcements_page_size.addItems(("25", "50", "100"))
        self.loot_announcements_page_size.currentTextChanged.connect(
            self._reset_loot_announcements_page
        )
        pagination.addWidget(_label("Linhas", "muted"))
        pagination.addWidget(self.loot_announcements_page_size)
        previous = QtWidgets.QPushButton("Anterior")
        previous.clicked.connect(lambda: self._change_loot_announcements_page(-1))
        following = QtWidgets.QPushButton("Próxima")
        following.clicked.connect(lambda: self._change_loot_announcements_page(1))
        pagination.addWidget(previous)
        pagination.addWidget(following)
        column.addLayout(pagination)
        return page

    def _build_inventory_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageInventario")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        heading = QtWidgets.QHBoxLayout()
        heading.addWidget(_label("Inventário", "title"))
        heading.addStretch(1)
        self.inventory_search = QtWidgets.QLineEdit()
        self.inventory_search.setPlaceholderText("Filtrar por nome ou código")
        self.inventory_search.setClearButtonEnabled(True)
        self.inventory_search.setMaximumWidth(340)
        self.inventory_search.textChanged.connect(self._render_inventory)
        heading.addWidget(self.inventory_search)
        column.addLayout(heading)
        self.inventory_category_tabs = QtWidgets.QTabBar()
        self.inventory_category_tabs.setExpanding(False)
        for key, label in INVENTORY_CATEGORIES:
            index = self.inventory_category_tabs.addTab(label)
            self.inventory_category_tabs.setTabData(index, key)
        self.inventory_category_tabs.currentChanged.connect(
            self._render_inventory
        )
        column.addWidget(self.inventory_category_tabs)
        self.inventory_status = _label(
            "Aguardando um snapshot de inventário.", "muted"
        )
        column.addWidget(self.inventory_status)
        self.inventory_table = QtWidgets.QTableWidget(0, 4)
        self.inventory_table.setHorizontalHeaderLabels(
            ("Item", "Quantidade", "Tipo", "Slot")
        )
        self.inventory_table.setIconSize(QtCore.QSize(46, 46))
        self.inventory_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.inventory_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.inventory_table.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.inventory_table.customContextMenuRequested.connect(
            self._show_inventory_category_menu
        )
        self.inventory_table.verticalHeader().setVisible(False)
        header = self.inventory_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for index in range(1, 4):
            header.setSectionResizeMode(
                index, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
        column.addWidget(self.inventory_table, 1)
        column.addWidget(
            _label(
                "Atualizado passivamente pelos snapshots e deltas recebidos do servidor do jogo.",
                "muted",
            )
        )
        return page

    def _build_exp_rank_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageRankingEXP")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)

        heading = QtWidgets.QHBoxLayout()
        title = QtWidgets.QVBoxLayout()
        title.setSpacing(2)
        title.addWidget(_label("Ranking de EXP", "title"))
        title.addWidget(_label("Top 100 oficial do servidor", "muted"))
        heading.addLayout(title)
        heading.addStretch(1)
        self.exp_rank_search = QtWidgets.QLineEdit()
        self.exp_rank_search.setPlaceholderText("Buscar personagem ou guilda")
        self.exp_rank_search.setClearButtonEnabled(True)
        self.exp_rank_search.setMaximumWidth(340)
        self.exp_rank_search.textChanged.connect(self._render_exp_rank)
        heading.addWidget(self.exp_rank_search)
        self.exp_rank_export = QtWidgets.QPushButton("Exportar CSV")
        self.exp_rank_export.setEnabled(False)
        self.exp_rank_export.clicked.connect(
            lambda _checked=False: self._export_exp_rank_csv()
        )
        heading.addWidget(self.exp_rank_export)
        column.addLayout(heading)

        summary = QtWidgets.QFrame(objectName="accentPanel")
        summary_row = QtWidgets.QHBoxLayout(summary)
        summary_row.setContentsMargins(16, 12, 16, 12)
        summary_row.setSpacing(18)
        self.exp_rank_state = _label("Aguardando captura", "muted")
        self.exp_rank_state.setMinimumWidth(150)
        summary_row.addWidget(self.exp_rank_state)
        self.exp_rank_status = _label(
            "Abra o ranking no jogo para iniciar a leitura passiva.", "muted"
        )
        self.exp_rank_status.setWordWrap(True)
        summary_row.addWidget(self.exp_rank_status, 1)
        column.addWidget(summary)

        self.exp_rank_table = QtWidgets.QTableWidget(0, 7)
        self.exp_rank_table.setHorizontalHeaderLabels(
            (
                "Posição", "Variação", "Personagem", "Guilda",
                "Nível", "EXP %", "EXP total",
            )
        )
        self.exp_rank_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.exp_rank_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.exp_rank_table.setAlternatingRowColors(False)
        self.exp_rank_table.verticalHeader().setVisible(False)
        header = self.exp_rank_table.horizontalHeader()
        for index in (0, 1, 4, 5, 6):
            header.setSectionResizeMode(
                index, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
        for index in (2, 3):
            header.setSectionResizeMode(
                index, QtWidgets.QHeaderView.ResizeMode.Stretch
            )
        self.exp_rank_history_table = QtWidgets.QTableWidget(0, 10)
        self.exp_rank_history_table.setHorizontalHeaderLabels((
            "Captura", "Posição", "Personagem", "Nível", "EXP %",
            "EXP total", "Ganho", "Ganho %", "EXP/h", "%/h",
        ))
        self.exp_rank_history_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.exp_rank_history_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.exp_rank_history_table.setAlternatingRowColors(False)
        self.exp_rank_history_table.verticalHeader().setVisible(False)
        history_header = self.exp_rank_history_table.horizontalHeader()
        for index in (0, 1, 3, 4, 6, 7, 8, 9):
            history_header.setSectionResizeMode(
                index, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
        history_header.setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        history_header.setSectionResizeMode(
            5, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        self.exp_rank_tabs = QtWidgets.QTabWidget()
        self.exp_rank_tabs.addTab(self.exp_rank_table, "Ranking atual")
        self.exp_rank_tabs.addTab(self.exp_rank_history_table, "Histórico")
        self.exp_rank_tabs.currentChanged.connect(
            self._set_exp_rank_export_available
        )
        column.addWidget(self.exp_rank_tabs, 1)
        note = _label(
            "Leitura passiva. Nível e EXP % usam a curva 1.28.5; ganho % representa "
            "pontos de progresso de nível entre capturas.",
            "muted",
        )
        note.setWordWrap(True)
        column.addWidget(note)
        return page

    def _build_map_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageMapa")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)

        heading = QtWidgets.QHBoxLayout()
        title = QtWidgets.QVBoxLayout()
        title.setSpacing(2)
        title.addWidget(_label("Mapa", "title"))
        title.addWidget(_label("Estado espacial passivo · limite de dois clientes", "muted"))
        heading.addLayout(title)
        heading.addStretch(1)
        self.map_manual_button = QtWidgets.QPushButton("Selecionar mapa atual")
        self.map_manual_button.setToolTip(
            "Usa o nome informado somente enquanto o reconhecimento automático "
            "não identificar este mapa."
        )
        self.map_manual_button.clicked.connect(self._set_manual_map_fallback)
        heading.addWidget(self.map_manual_button)
        self.map_manual_clear = QtWidgets.QPushButton("Remover mapa manual")
        self.map_manual_clear.setToolTip(
            "Remove apenas o fallback; o reconhecimento automático permanece ativo."
        )
        self.map_manual_clear.clicked.connect(self._clear_manual_map_fallback)
        heading.addWidget(self.map_manual_clear)
        self.map_capacity = _label("0/2 vagas em uso", "muted")
        heading.addWidget(self.map_capacity)
        column.addLayout(heading)

        summary = QtWidgets.QFrame(objectName="accentPanel")
        summary_row = QtWidgets.QHBoxLayout(summary)
        summary_row.setContentsMargins(16, 12, 16, 12)
        summary_row.setSpacing(18)
        self.map_state = _label("Aguardando rota", "muted")
        self.map_state.setMinimumWidth(170)
        summary_row.addWidget(self.map_state)
        self.map_status = _label(
            "Inicie a captura ou um monitor para receber coordenadas.", "muted"
        )
        self.map_status.setWordWrap(True)
        summary_row.addWidget(self.map_status, 1)
        column.addWidget(summary)

        metrics = QtWidgets.QHBoxLayout()
        self.map_metric_labels: dict[str, QtWidgets.QLabel] = {}
        for key, title_text in (
            ("map", "Mapa"),
            ("x", "Coordenada X"),
            ("y", "Coordenada Y"),
            ("z", "Coordenada Z"),
            ("players", "Jogadores próximos"),
        ):
            card = QtWidgets.QFrame(objectName="mapMetricGroup")
            card_layout = QtWidgets.QVBoxLayout(card)
            card_layout.setContentsMargins(12, 8, 12, 8)
            card_layout.setSpacing(2)
            card_layout.addWidget(_label(title_text, "muted"))
            value = _label("—", "data")
            card_layout.addWidget(value)
            self.map_metric_labels[key] = value
            metrics.addWidget(card, 1)
        column.addLayout(metrics)

        viewer = QtWidgets.QFrame(objectName="mapViewerPanel")
        viewer_layout = QtWidgets.QVBoxLayout(viewer)
        viewer_layout.setContentsMargins(12, 10, 12, 12)
        viewer_layout.setSpacing(8)
        viewer_toolbar = QtWidgets.QHBoxLayout()
        viewer_toolbar.addWidget(_label("Mapa completo", "subtitle"))
        viewer_toolbar.addStretch(1)
        self.map_page_zoom_out = QtWidgets.QPushButton("−")
        self.map_page_zoom_out.setObjectName("mapToolButton")
        self.map_page_zoom_out.setAccessibleName("Diminuir zoom do mapa")
        self.map_page_zoom_out.setToolTip("Diminuir zoom")
        self.map_page_zoom_out.setFixedWidth(38)
        self.map_page_zoom = _label("100% · foco", "muted")
        self.map_page_zoom.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.map_page_zoom.setMinimumWidth(78)
        self.map_page_zoom_in = QtWidgets.QPushButton("+")
        self.map_page_zoom_in.setObjectName("mapToolButton")
        self.map_page_zoom_in.setAccessibleName("Aumentar zoom do mapa")
        self.map_page_zoom_in.setToolTip("Aumentar zoom")
        self.map_page_zoom_in.setFixedWidth(38)
        self.map_page_focus = QtWidgets.QPushButton("Focar personagem")
        self.map_page_focus.setObjectName("mapFocusButton")
        self.map_page_focus.setToolTip(
            "Centralizar o mapa novamente na posição atual do personagem"
        )
        viewer_toolbar.addWidget(self.map_page_zoom_out)
        viewer_toolbar.addWidget(self.map_page_zoom)
        viewer_toolbar.addWidget(self.map_page_zoom_in)
        viewer_toolbar.addWidget(self.map_page_focus)
        viewer_layout.addLayout(viewer_toolbar)
        self.map_page_preview = _MapPreview()
        self.map_page_preview.setMinimumHeight(360)
        self.map_page_zoom_out.clicked.connect(self.map_page_preview.zoom_out)
        self.map_page_zoom_in.clicked.connect(self.map_page_preview.zoom_in)
        self.map_page_focus.clicked.connect(
            self.map_page_preview.focus_on_character
        )
        self.map_page_preview.view_changed.connect(
            lambda zoom, focused: self.map_page_zoom.setText(
                f"{zoom}%" + (" · foco" if focused else "")
            )
        )
        viewer_layout.addWidget(self.map_page_preview, 1)
        hint = _label(
            "Use a roda do mouse ou os botões para zoom. Arraste o mapa para navegar.",
            "muted",
        )
        hint.setWordWrap(True)
        viewer_layout.addWidget(hint)
        column.addWidget(viewer, 2)

        column.addWidget(_label("Jogadores próximos", "subtitle"))
        self.map_players_table = QtWidgets.QTableWidget(0, 6)
        self.map_players_table.setHorizontalHeaderLabels(
            ("Personagem", "Guilda", "X", "Y", "Z", "Distância")
        )
        self.map_players_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.map_players_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.map_players_table.setAlternatingRowColors(False)
        self.map_players_table.verticalHeader().setVisible(False)
        header = self.map_players_table.horizontalHeader()
        for index in (0, 1):
            header.setSectionResizeMode(index, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for index in range(2, 6):
            header.setSectionResizeMode(
                index, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
        column.addWidget(self.map_players_table, 1)
        note = _label(
            "O terceiro cliente continua capturando normalmente, mas não mantém estado de mapa.",
            "muted",
        )
        note.setWordWrap(True)
        column.addWidget(note)
        return page

    def _build_banks_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageBancos")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        column.addWidget(_label("Bancos", "title"))
        description = _label(
            "Consulte as identidades PvP, o conhecimento de monstros e suas vendas "
            "próprias capturadas no leilão.",
            "muted",
        )
        description.setWordWrap(True)
        column.addWidget(description)
        self.banks_tabs = QtWidgets.QTabWidget(objectName="banksTabs")
        self.banks_tabs.addTab(self._build_pvp_database_page(embedded=True), "PvP")
        self.banks_tabs.addTab(self._build_pve_database_page(), "PvE")
        self.banks_tabs.addTab(self._build_auction_database_page(), "Leilão")
        self.banks_tabs.currentChanged.connect(self._render_selected_bank)
        column.addWidget(self.banks_tabs, 1)
        return page

    def _render_selected_bank(self, index: int | None = None) -> None:
        current = self.banks_tabs.currentIndex() if index is None else index
        if current == 0:
            self._render_pvp_database()
        elif current == 1:
            self._render_pve_database()
        elif current == 2:
            self._render_auction_database()

    def _bank_is_visible(self, index: int) -> bool:
        return (
            hasattr(self, "banks_tabs")
            and self.page_stack.currentIndex() == BANKS_PAGE_INDEX
            and self.banks_tabs.currentIndex() == index
        )

    def _build_pve_database_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageBancoPvE")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(8, 10, 8, 8)
        column.setSpacing(10)
        heading = QtWidgets.QHBoxLayout()
        heading.addWidget(_label("Monstros conhecidos", "subtitle"))
        heading.addStretch(1)
        refresh = QtWidgets.QPushButton("Atualizar")
        refresh.clicked.connect(self._render_pve_database)
        heading.addWidget(refresh)
        column.addLayout(heading)
        note = _label(
            "Uma observação idêntica não volta à fila. Novos locais são preservados e "
            "HP divergente fica em revisão, sem substituir o valor confirmado.",
            "muted",
        )
        note.setWordWrap(True)
        column.addWidget(note)
        self.pve_database_filter = QtWidgets.QLineEdit()
        self.pve_database_filter.setPlaceholderText(
            "Filtrar monstro, NPC, mapa ou coordenada"
        )
        self.pve_database_filter.textChanged.connect(self._filter_pve_database)
        column.addWidget(self.pve_database_filter)
        self.pve_database_table = QtWidgets.QTableWidget(0, 7)
        self.pve_database_table.setHorizontalHeaderLabels((
            "Monstro", "NPC", "Nível", "HP máximo", "Localizações",
            "Revisão de HP", "Sincronização",
        ))
        self.pve_database_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.pve_database_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.pve_database_table.verticalHeader().setVisible(False)
        header = self.pve_database_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for index in (1, 2, 3, 5, 6):
            header.setSectionResizeMode(
                index, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
        column.addWidget(self.pve_database_table, 1)
        self.pve_database_status = _label("Nenhum monstro observado.", "muted")
        column.addWidget(self.pve_database_status)
        return page

    def _build_auction_database_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageBancoLeilao")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(8, 10, 8, 8)
        column.setSpacing(10)
        heading = QtWidgets.QHBoxLayout()
        heading.addWidget(_label("Histórico do leilão", "subtitle"))
        heading.addStretch(1)
        self.auction_database_send = QtWidgets.QPushButton("Enviar banco ao site")
        self.auction_database_send.setToolTip(
            "Envia somente registros confirmados e sanitizados, sem IDs de conta ou personagem."
        )
        self.auction_database_send.clicked.connect(self._send_auction_bank)
        heading.addWidget(self.auction_database_send)
        refresh = QtWidgets.QPushButton("Atualizar")
        refresh.clicked.connect(self._render_auction_database)
        heading.addWidget(refresh)
        column.addLayout(heading)
        note = _label(
            "Mostra compras confirmadas, vendas próprias e registros históricos ainda "
            "sem tipo validado, sempre sem IDs de conta ou personagem.",
            "muted",
        )
        note.setWordWrap(True)
        column.addWidget(note)
        filters = QtWidgets.QHBoxLayout()
        self.auction_database_filter = QtWidgets.QLineEdit()
        self.auction_database_filter.setPlaceholderText("Filtrar item ou servidor")
        self.auction_database_filter.textChanged.connect(
            self._filter_auction_database
        )
        filters.addWidget(self.auction_database_filter, 1)
        self.auction_database_status_filter = QtWidgets.QComboBox()
        for label, value in (
            ("Todos os estados", ""),
            ("Ativos", "active"),
            ("Vendidos", "sold"),
            ("Cancelados", "cancelled"),
            ("Liquidados", "settled"),
            ("Comprados", "bought"),
            ("Tipo não validado", "unclassified"),
        ):
            self.auction_database_status_filter.addItem(label, value)
        self.auction_database_status_filter.currentIndexChanged.connect(
            self._filter_auction_database
        )
        filters.addWidget(self.auction_database_status_filter)
        column.addLayout(filters)
        self.auction_database_table = QtWidgets.QTableWidget(0, 7)
        self.auction_database_table.setHorizontalHeaderLabels((
            "Item", "Refino", "Quantidade", "Preço/un.", "Estado",
            "Servidor", "Observado",
        ))
        self.auction_database_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.auction_database_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.auction_database_table.verticalHeader().setVisible(False)
        header = self.auction_database_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for index in range(1, 7):
            header.setSectionResizeMode(
                index, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
        column.addWidget(self.auction_database_table, 1)
        self.auction_database_status = _label(
            "Selecione um personagem para consultar suas vendas.", "muted"
        )
        column.addWidget(self.auction_database_status)
        return page

    def _build_pvp_database_page(self, *, embedded: bool = False) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageBancoPvP")
        column = QtWidgets.QVBoxLayout(page)
        if embedded:
            column.setContentsMargins(8, 10, 8, 8)
        else:
            column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        heading = QtWidgets.QHBoxLayout()
        if not embedded:
            heading.addWidget(_label("Banco PvP", "title"))
        heading.addStretch(1)
        heading.addWidget(_label("Enviar a cada", "muted"))
        self.pvp_sync_interval = QtWidgets.QSpinBox()
        self.pvp_sync_interval.setRange(1, 60)
        self.pvp_sync_interval.setSuffix(" min")
        self.pvp_sync_interval.setValue(5)
        self.pvp_sync_interval.valueChanged.connect(
            self._save_pvp_sync_interval
        )
        heading.addWidget(self.pvp_sync_interval)
        send_now = QtWidgets.QPushButton("Enviar ao site")
        send_now.setToolTip("Envia as alterações pendentes ao Banco Temporário.")
        send_now.clicked.connect(self._send_pvp_database_now)
        heading.addWidget(send_now)
        receive_now = QtWidgets.QPushButton("Receber do site")
        receive_now.setToolTip("Recebe somente o Banco Final aprovado.")
        receive_now.clicked.connect(self._receive_pvp_database_now)
        heading.addWidget(receive_now)
        refresh = QtWidgets.QPushButton("Atualizar")
        refresh.clicked.connect(self._render_pvp_database)
        heading.addWidget(refresh)
        column.addLayout(heading)
        note = _label(
            "UIDs neutros vistos em uma única sessão ficam em quarentena. Uma "
            "segunda sessão ou uma confirmação de guilda/status promove ao Banco "
            "Final; nenhum registro é excluído automaticamente.",
            "muted",
        )
        note.setWordWrap(True)
        column.addWidget(note)

        filters = QtWidgets.QHBoxLayout()
        self.pvp_database_filter = QtWidgets.QLineEdit()
        self.pvp_database_filter.setPlaceholderText(
            "Filtrar UID, personagem ou guilda"
        )
        self.pvp_database_filter.textChanged.connect(self._filter_pvp_database)
        filters.addWidget(self.pvp_database_filter, 1)
        self.pvp_database_status_filter = QtWidgets.QComboBox()
        for label, value in (
            ("Todos os status", ""),
            ("Aliado", "ally"),
            ("Inimigo", "enemy"),
            ("Neutro", "neutral"),
        ):
            self.pvp_database_status_filter.addItem(label, value)
        self.pvp_database_status_filter.currentIndexChanged.connect(
            self._filter_pvp_database
        )
        filters.addWidget(self.pvp_database_status_filter)
        self.pvp_database_curation_filter = QtWidgets.QComboBox()
        for label, value in (
            ("Banco final", "final"),
            ("Quarentena", "quarantine"),
            ("Todos os registros", ""),
        ):
            self.pvp_database_curation_filter.addItem(label, value)
        self.pvp_database_curation_filter.currentIndexChanged.connect(
            self._filter_pvp_database
        )
        filters.addWidget(self.pvp_database_curation_filter)
        column.addLayout(filters)

        batch = QtWidgets.QHBoxLayout()
        select_visible = QtWidgets.QPushButton("Selecionar visíveis")
        select_visible.clicked.connect(self._select_visible_pvp_rows)
        batch.addWidget(select_visible)
        clear_selection = QtWidgets.QPushButton("Desmarcar todos")
        batch.addWidget(clear_selection)
        self.pvp_batch_guild_enabled = QtWidgets.QCheckBox("Alterar guilda")
        batch.addWidget(self.pvp_batch_guild_enabled)
        self.pvp_batch_guild = QtWidgets.QLineEdit()
        self.pvp_batch_guild.setPlaceholderText("Nova guilda; vazio limpa")
        self.pvp_batch_guild.setEnabled(False)
        self.pvp_batch_guild_enabled.toggled.connect(self.pvp_batch_guild.setEnabled)
        batch.addWidget(self.pvp_batch_guild, 1)
        self.pvp_batch_status = QtWidgets.QComboBox()
        self.pvp_batch_status.addItem("Manter status atual", None)
        for label, value in (
            ("Aliado", "ally"),
            ("Inimigo", "enemy"),
            ("Neutro", "neutral"),
            ("Ignorar", "ignored"),
        ):
            self.pvp_batch_status.addItem(label, value)
        batch.addWidget(self.pvp_batch_status)
        apply_batch = QtWidgets.QPushButton("Aplicar aos marcados")
        apply_batch.clicked.connect(self._apply_pvp_batch_edit)
        batch.addWidget(apply_batch)
        column.addLayout(batch)

        self.pvp_database_table = QtWidgets.QTableWidget(0, 8)
        self.pvp_database_table.setHorizontalHeaderLabels(
            (
                "", "UID", "Personagem", "Classe", "Rover",
                "Evidência", "Guilda", "Status",
            )
        )
        self.pvp_database_table.verticalHeader().setVisible(False)
        self.pvp_database_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.pvp_database_table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.NoSelection
        )
        header = self.pvp_database_table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        saved_header = str(
            self.preferences.get("pvp_database_header_state_v2") or ""
        )
        restored = bool(saved_header) and header.restoreState(
                QtCore.QByteArray.fromBase64(saved_header.encode("ascii"))
            )
        if not restored:
            for index, width in enumerate(
                (42, 170, 220, 120, 140, 160, 220, 120)
            ):
                header.resizeSection(index, width)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.pvp_header_save_timer = QtCore.QTimer(self)
        self.pvp_header_save_timer.setSingleShot(True)
        self.pvp_header_save_timer.setInterval(250)
        self.pvp_header_save_timer.timeout.connect(self._save_pvp_header_state)
        header.sectionMoved.connect(
            lambda *_args: self.pvp_header_save_timer.start()
        )
        header.sectionResized.connect(
            lambda *_args: self.pvp_header_save_timer.start()
        )
        clear_selection.clicked.connect(self._clear_pvp_checks)
        column.addWidget(self.pvp_database_table, 1)
        self.pvp_database_status = _label("Nenhum UID observado.", "muted")
        column.addWidget(self.pvp_database_status)
        return page

    def _render_pvp_database(self) -> None:
        if not hasattr(self, "pvp_database_table"):
            return
        checked_uids = self._checked_pvp_uids()
        query = self.pvp_database_filter.text().strip()
        wanted_status = str(
            self.pvp_database_status_filter.currentData() or ""
        )
        wanted_curation = str(
            self.pvp_database_curation_filter.currentData() or ""
        )
        knowledge = KnowledgeStore(self.knowledge_path)
        try:
            rows = knowledge.characters(
                query=query,
                status=wanted_status,
                curation_state=wanted_curation,
                limit=self.memory_limits["pvp_rows"],
            )
            total = knowledge.character_count(
                query=query,
                status=wanted_status,
                curation_state=wanted_curation,
            )
            curation = knowledge.curation_summary()
        finally:
            knowledge.close()
        self.pvp_database_rows = {
            str(row["character_uid"]): row for row in rows
        }
        self.pvp_database_table.setRowCount(0)
        self.pvp_database_table.setRowCount(len(rows))
        labels = {
            "ally": "Aliado",
            "enemy": "Inimigo",
            "neutral": "Neutro",
            "ignored": "Ignorar",
        }
        for row_index, row in enumerate(rows):
            uid = str(row["character_uid"])
            biosuit_index = row.get("biosuit_item_index")
            biosuit = BIOSUITS.get(str(biosuit_index or ""), {})
            class_name = str(biosuit.get("class_name") or "")
            rover_index = row.get("rover_item_index")
            rover = ROVERS.get(str(rover_index or ""), {})
            rover_name = game_catalog_name(
                rover,
                self.preferences.get("item_name_language"),
            )
            check_cell = QtWidgets.QTableWidgetItem()
            check_cell.setFlags(
                QtCore.Qt.ItemFlag.ItemIsEnabled
                | QtCore.Qt.ItemFlag.ItemIsUserCheckable
            )
            check_cell.setCheckState(
                QtCore.Qt.CheckState.Checked
                if uid in checked_uids else QtCore.Qt.CheckState.Unchecked
            )
            uid_cell = QtWidgets.QTableWidgetItem(uid)
            uid_cell.setFlags(uid_cell.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            name_cell = QtWidgets.QTableWidgetItem(str(row.get("name") or "—"))
            name_cell.setFlags(name_cell.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            class_cell = QtWidgets.QTableWidgetItem(class_name or "—")
            class_cell.setFlags(class_cell.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            class_cell.setToolTip(
                f"Biosuit #{biosuit_index}" if biosuit_index else "Biosuit não identificado"
            )
            rover_cell = QtWidgets.QTableWidgetItem(rover_name or "—")
            rover_cell.setFlags(rover_cell.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            rover_cell.setToolTip(
                f"Rover #{rover_index}" if rover_index else "Rover não identificado"
            )
            sightings = int(row.get("observation_count") or 0)
            sessions = int(row.get("session_count") or 0)
            evidence_cell = QtWidgets.QTableWidgetItem(
                f"{sessions} sessão(ões) · {sightings} aparição(ões)"
            )
            evidence_cell.setFlags(
                evidence_cell.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable
            )
            evidence_cell.setToolTip(
                "O Banco Final exige confirmação manual, identidade de guilda/status "
                "ou observação em pelo menos duas sessões."
            )
            guild = QtWidgets.QLineEdit(str(row.get("guild_name") or ""))
            guild.setPlaceholderText("Guilda não identificada")
            guild.editingFinished.connect(
                lambda current_uid=uid, editor=guild: self._save_pvp_identity(
                    current_uid, editor, None
                )
            )
            status = QtWidgets.QComboBox()
            for value in ("ally", "enemy", "neutral", "ignored"):
                status.addItem(labels[value], value)
            selected = status.findData(str(row.get("pvp_status") or "neutral"))
            status.setCurrentIndex(max(0, selected))
            status.currentIndexChanged.connect(
                lambda _index, current_uid=uid, editor=guild, combo=status:
                    self._save_pvp_identity(current_uid, editor, combo)
            )
            self.pvp_database_table.setItem(row_index, 0, check_cell)
            self.pvp_database_table.setItem(row_index, 1, uid_cell)
            self.pvp_database_table.setItem(row_index, 2, name_cell)
            self.pvp_database_table.setItem(row_index, 3, class_cell)
            self.pvp_database_table.setItem(row_index, 4, rover_cell)
            self.pvp_database_table.setItem(row_index, 5, evidence_cell)
            self.pvp_database_table.setCellWidget(row_index, 6, guild)
            self.pvp_database_table.setCellWidget(row_index, 7, status)
        pending = sum(row.get("upload_state") == "pending" for row in rows)
        suffix = (
            f"Banco final: {curation['final']} · "
            f"quarentena: {curation['quarantine']}"
        )
        if not total:
            text = f"Nenhum UID neste filtro · {suffix}"
        elif total > len(rows):
            text = (
                f"Mostrando {len(rows)} de {total} UID(s) · "
                f"{pending} pendente(s) nesta lista · refine a busca · {suffix}"
            )
        else:
            text = f"{total} UID(s) · {pending} aguardando envio · {suffix}"
        self.pvp_database_status.setText(text)

    def _render_pve_database(self) -> None:
        if not hasattr(self, "pve_database_table"):
            return
        if "monitor-pve" not in self.license_features:
            self.pve_database_table.setRowCount(0)
            self.pve_database_status.setText(
                "Banco PvE não incluído nesta licença."
            )
            return
        knowledge = KnowledgeStore(self.knowledge_path)
        try:
            rows = knowledge.mobs()
            locations = knowledge.mob_locations()
            candidates = knowledge.mob_hp_candidates()
        finally:
            knowledge.close()
        locations_by_mob: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for location in locations:
            key = (
                int(location.get("npc_index") or 0),
                str(location.get("protocol_version") or ""),
            )
            locations_by_mob.setdefault(key, []).append(location)
        candidates_by_mob: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for candidate in candidates:
            key = (
                int(candidate.get("npc_index") or 0),
                str(candidate.get("protocol_version") or ""),
            )
            candidates_by_mob.setdefault(key, []).append(candidate)

        self.pve_database_rows = rows
        self.pve_database_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            npc_index = int(row.get("npc_index") or 0)
            protocol = str(row.get("protocol_version") or "")
            key = (npc_index, protocol)
            location_labels = []
            for location in locations_by_mob.get(key, []):
                label = str(location.get("label") or "").strip()
                map_index = location.get("map_index")
                if not label and map_index is not None:
                    label = f"Mapa #{map_index}"
                coordinates = [
                    location.get("position_x"),
                    location.get("position_y"),
                    location.get("position_z"),
                ]
                if all(isinstance(value, (int, float)) for value in coordinates):
                    position = ", ".join(f"{float(value):.1f}" for value in coordinates)
                    label = f"{label or 'Coordenada'} ({position})"
                if label:
                    location_labels.append(label)
            location_text = "; ".join(location_labels)
            visible_locations = "; ".join(location_labels[:2])
            if len(location_labels) > 2:
                visible_locations += f"; +{len(location_labels) - 2}"
            pending_candidates = [
                item for item in candidates_by_mob.get(key, [])
                if item.get("review_state") == "pending"
            ]
            candidate_values = ", ".join(
                self._format_count(item.get("max_hp"))
                for item in pending_candidates
            )
            values = (
                str(row.get("name") or f"Monstro #{npc_index}"),
                str(npc_index),
                self._format_count(row.get("level")),
                self._format_count(row.get("max_hp")),
                visible_locations or "—",
                f"Revisar {len(pending_candidates)}" if pending_candidates else "Sem conflito",
                "Pendente" if row.get("upload_state") == "pending" else "Enviado",
            )
            for column, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(value)
                cell.setData(QtCore.Qt.ItemDataRole.UserRole, value)
                self.pve_database_table.setItem(row_index, column, cell)
            name_cell = self.pve_database_table.item(row_index, 0)
            name_cell.setToolTip(f"Protocolo {protocol or 'não identificado'}")
            location_cell = self.pve_database_table.item(row_index, 4)
            location_cell.setData(
                QtCore.Qt.ItemDataRole.UserRole, location_text or "sem localização"
            )
            location_cell.setToolTip(location_text or "Nenhuma localização confirmada")
            candidate_cell = self.pve_database_table.item(row_index, 5)
            candidate_cell.setToolTip(
                f"Valores divergentes: {candidate_values}"
                if candidate_values else "Nenhuma divergência de HP"
            )
        self._filter_pve_database()

    def _filter_pve_database(self, *_args) -> None:
        if not hasattr(self, "pve_database_table"):
            return
        query = self.pve_database_filter.text().strip().casefold()
        visible = 0
        for row in range(self.pve_database_table.rowCount()):
            values = [
                str(
                    self.pve_database_table.item(row, column).data(
                        QtCore.Qt.ItemDataRole.UserRole
                    ) or self.pve_database_table.item(row, column).text()
                )
                for column in range(self.pve_database_table.columnCount())
            ]
            matches = not query or query in " ".join(values).casefold()
            self.pve_database_table.setRowHidden(row, not matches)
            visible += int(matches)
        rows = list(getattr(self, "pve_database_rows", []))
        known_hp = sum(row.get("max_hp") is not None for row in rows)
        known_locations = sum(int(row.get("location_count") or 0) > 0 for row in rows)
        conflicts = sum(int(row.get("hp_candidate_count") or 0) for row in rows)
        self.pve_database_status.setText(
            f"{visible} de {len(rows)} monstro(s) · {known_hp} com HP · "
            f"{known_locations} com localização · {conflicts} divergência(s) em revisão"
            if rows else "Nenhum monstro observado."
        )

    def _render_auction_database(self) -> None:
        if not hasattr(self, "auction_database_table"):
            return
        session_id = str(self.snapshot.get("session_id") or "")
        character_uid = self._client_uid_for(self.active_client)
        self.auction_database_context = ""
        rows: list[dict[str, Any]] = []
        if not session_id:
            self.auction_database_context = "Nenhuma sessão disponível."
        elif not character_uid:
            self.auction_database_context = (
                f"Aguardando o personagem de {self._client_name(self.active_client)}."
            )
        else:
            store = CaptureStore(self.database_path, readonly=True)
            try:
                events = store.auction_sale_events(session_id, character_uid)
            finally:
                store.close()
            catalog = item_names_for_language(
                self.preferences.get("item_name_language")
            )
            rows = auction_sales_snapshot(
                events,
                secret=self.auction_projection_secret,
            )
            transactions = auction_transaction_history(
                events,
                secret=self.auction_projection_secret,
            )
            transaction_keys = {
                (str(row.get("listing_id") or ""), row.get("transaction_type"))
                for row in transactions
            }
            rows = [
                row for row in rows
                if not (
                    row.get("status") in {"sold", "settled"}
                    and (str(row.get("listing_id") or ""), "sold")
                    in transaction_keys
                )
            ] + [
                {**row, "status": row.get("transaction_type")}
                for row in transactions
            ]
            rows.sort(
                key=lambda item: int(item.get("observed_at_ns") or 0),
                reverse=True,
            )
            self.auction_database_context = (
                f"{self._client_name(self.active_client)} · histórico próprio capturado"
            )
        self.auction_database_rows = rows
        self.auction_database_table.setRowCount(len(rows))
        status_labels = {
            "active": "Ativo",
            "sold": "Vendido",
            "cancelled": "Cancelado",
            "settled": "Liquidado",
            "bought": "Comprado",
            "unclassified": "Tipo não validado",
        }
        for row_index, row in enumerate(rows):
            item_index = int(row.get("item_index") or 0)
            enchant = row.get("enchant_level")
            observed_at = self._format_observed_at(row.get("observed_at_ns"))
            status = str(row.get("status") or "")
            values = (
                str(catalog.get(str(item_index)) or f"Item {item_index}"),
                f"+{int(enchant)}" if isinstance(enchant, int) else "—",
                self._format_count(row.get("quantity")),
                self._format_count(row.get("price_per_unit")),
                status_labels.get(status, status or "—"),
                f"Servidor {row.get('server_type')}",
                observed_at,
            )
            for column, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(value)
                self.auction_database_table.setItem(row_index, column, cell)
            self.auction_database_table.item(row_index, 0).setToolTip(
                f"Item #{item_index}"
            )
            self.auction_database_table.item(row_index, 4).setData(
                QtCore.Qt.ItemDataRole.UserRole, status
            )
            raw_type = row.get("exchange_type_raw")
            if status == "unclassified" and isinstance(raw_type, int):
                self.auction_database_table.item(row_index, 4).setToolTip(
                    f"Tipo bruto confirmado: {raw_type}. Compra/venda ainda não validada."
                )
        self._filter_auction_database()

    @staticmethod
    def _format_observed_at(value: object) -> str:
        try:
            timestamp = int(value) / 1_000_000_000
            if timestamp <= 0:
                return "—"
            return datetime.fromtimestamp(timestamp).strftime("%d/%m %H:%M:%S")
        except (OSError, OverflowError, TypeError, ValueError):
            return "—"

    def _filter_auction_database(self, *_args) -> None:
        if not hasattr(self, "auction_database_table"):
            return
        query = self.auction_database_filter.text().strip().casefold()
        wanted_status = str(
            self.auction_database_status_filter.currentData() or ""
        )
        visible = 0
        for row in range(self.auction_database_table.rowCount()):
            values = [
                self.auction_database_table.item(row, column).text()
                for column in range(self.auction_database_table.columnCount())
            ]
            status = str(
                self.auction_database_table.item(row, 4).data(
                    QtCore.Qt.ItemDataRole.UserRole
                ) or ""
            )
            matches = (
                (not query or query in " ".join(values).casefold())
                and (not wanted_status or status == wanted_status)
            )
            self.auction_database_table.setRowHidden(row, not matches)
            visible += int(matches)
        rows = list(getattr(self, "auction_database_rows", []))
        active = sum(row.get("status") == "active" for row in rows)
        context = str(getattr(self, "auction_database_context", ""))
        self.auction_database_status.setText(
            f"{context} · {visible} de {len(rows)} registro(s) · {active} ativo(s)"
            if rows else context or "Nenhum histórico próprio capturado."
        )

    def _filter_pvp_database(self, *_args) -> None:
        if not hasattr(self, "pvp_database_table"):
            return
        self._render_pvp_database()

    def _checked_pvp_uids(self) -> set[str]:
        if not hasattr(self, "pvp_database_table"):
            return set()
        return {
            self.pvp_database_table.item(row, 1).text()
            for row in range(self.pvp_database_table.rowCount())
            if self.pvp_database_table.item(row, 0).checkState()
            == QtCore.Qt.CheckState.Checked
        }

    def _select_visible_pvp_rows(self) -> None:
        self._clear_pvp_checks()
        for row in range(self.pvp_database_table.rowCount()):
            if not self.pvp_database_table.isRowHidden(row):
                self.pvp_database_table.item(row, 0).setCheckState(
                    QtCore.Qt.CheckState.Checked
                )

    def _clear_pvp_checks(self) -> None:
        for row in range(self.pvp_database_table.rowCount()):
            self.pvp_database_table.item(row, 0).setCheckState(
                QtCore.Qt.CheckState.Unchecked
            )

    def _apply_pvp_batch_edit(self) -> None:
        uids = self._checked_pvp_uids()
        change_guild = self.pvp_batch_guild_enabled.isChecked()
        status = self.pvp_batch_status.currentData()
        if not uids:
            self.pvp_database_status.setText("Marque ao menos um UID.")
            return
        if not change_guild and status is None:
            self.pvp_database_status.setText("Escolha uma alteração para aplicar.")
            return
        knowledge = KnowledgeStore(self.knowledge_path)
        changed = 0
        try:
            for uid in uids:
                row = knowledge.character(uid)
                if row is None:
                    continue
                knowledge.update_pvp_identity(
                    uid,
                    guild_name=(
                        self.pvp_batch_guild.text()
                        if change_guild else row.get("guild_name") or ""
                    ),
                    status=status if status is not None else row.get("pvp_status") or "neutral",
                )
                changed += 1
        except ValueError as error:
            self.pvp_database_status.setText(str(error))
            return
        finally:
            knowledge.close()
        self._render_pvp_database()
        self.pvp_database_status.setText(
            f"{changed} UID(s) alterado(s); envio pendente."
        )

    def _save_pvp_header_state(self) -> None:
        state = bytes(
            self.pvp_database_table.horizontalHeader().saveState().toBase64()
        ).decode("ascii")
        self.preferences = save_preferences(
            {"pvp_database_header_state_v2": state}, self.preferences_path
        )

    def _save_pvp_identity(
        self,
        uid: str,
        guild: QtWidgets.QLineEdit,
        status: QtWidgets.QComboBox | None,
    ) -> None:
        knowledge = KnowledgeStore(self.knowledge_path)
        try:
            current = knowledge.character(uid, include_ignored=False)
            if current is None:
                return
            saved = knowledge.update_pvp_identity(
                uid,
                guild_name=guild.text(),
                status=(
                    status.currentData()
                    if status is not None
                    else current.get("pvp_status") or "neutral"
                ),
            )
        except ValueError as error:
            self.pvp_database_status.setText(str(error))
            return
        finally:
            knowledge.close()
        guild.setText(str(saved.get("guild_name") or ""))
        self.pvp_database_status.setText("Alteração salva; sincronização pendente.")
        if saved.get("pvp_status") == "ignored":
            self._render_pvp_database()

    def _save_pvp_sync_interval(self, minutes: int) -> None:
        self.preferences = save_preferences(
            {"pvp_sync_interval_minutes": int(minutes)}, self.preferences_path
        )
        self.observation_sync_next_due = time.monotonic() + int(minutes) * 60

    def _send_pvp_database_now(self) -> None:
        self.pvp_database_status.setText("Enviando alterações ao site…")
        self._maybe_sync_observations(time.monotonic(), force=True)

    def _receive_pvp_database_now(self) -> None:
        if not self.site_profile.connected:
            self.pvp_database_status.setText(
                "Valide o token do Profile antes de receber."
            )
            return
        if self.site_busy:
            self.pvp_database_status.setText("Aguarde a operação atual terminar.")
            return
        self.pvp_database_status.setText("Recebendo Banco Final do site…")
        self._run_site_operation(
            "observations:receive",
            lambda: self.site_uploader.receive_observations(self.knowledge_path),
        )

    def _build_integrations_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageIntegracoes")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        column.addWidget(_label("Integrações", "title"))
        column.addWidget(_label(
            "Conecte o Profile, controle a API local e acompanhe a saúde das saídas.",
            "muted",
        ))

        scroll = QtWidgets.QScrollArea(objectName="pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        content = QtWidgets.QWidget(objectName="scrollContent")
        grid = QtWidgets.QGridLayout(content)
        self.integrations_grid = grid
        grid.setContentsMargins(0, 0, 8, 0)
        grid.setSpacing(8)
        grid.addWidget(self._build_profile_integration_panel(), 0, 0)
        grid.addWidget(self._build_local_api_panel(), 0, 1)
        grid.addWidget(self._build_integration_health_panel(), 1, 0, 1, 2)

        actions = QtWidgets.QHBoxLayout()
        actions.addStretch(1)
        restore = QtWidgets.QPushButton("Restaurar valores salvos")
        restore.clicked.connect(self._load_settings_fields)
        save = QtWidgets.QPushButton("Salvar integrações")
        save.clicked.connect(self._save_settings)
        actions.addWidget(restore)
        actions.addWidget(save)
        grid.addLayout(actions, 2, 0, 1, 2)
        grid.setRowStretch(3, 1)
        scroll.setWidget(content)
        column.addWidget(scroll, 1)
        return page

    def _build_profile_integration_panel(self) -> QtWidgets.QWidget:
        profile = QtWidgets.QFrame(objectName="panel")
        profile_form = QtWidgets.QFormLayout(profile)
        profile_form.addRow(_label("Integração com o Profile", "subtitle"))
        self.setting_profile = QtWidgets.QLineEdit()
        profile_form.addRow("Nome do Profile", self.setting_profile)
        self.setting_site_token = QtWidgets.QLineEdit()
        self.setting_site_token.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.setting_site_token.setPlaceholderText("Token gerado no site")
        profile_form.addRow("Token", self.setting_site_token)
        profile_actions = QtWidgets.QWidget()
        profile_actions_layout = QtWidgets.QHBoxLayout(profile_actions)
        profile_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.connect_site_button = QtWidgets.QPushButton("Validar token")
        self.connect_site_button.clicked.connect(self._connect_site_profile)
        self.disconnect_site_button = QtWidgets.QPushButton("Revogar localmente")
        self.disconnect_site_button.clicked.connect(self._disconnect_site_profile)
        self.export_upload_button = QtWidgets.QPushButton("Exportar e enviar agora")
        self.export_upload_button.clicked.connect(self._export_and_upload)
        profile_actions_layout.addWidget(self.connect_site_button)
        profile_actions_layout.addWidget(self.disconnect_site_button)
        profile_actions_layout.addWidget(self.export_upload_button)
        profile_form.addRow(profile_actions)
        site_enabled = bool(SITE_SERVER)
        for widget in (
            self.setting_profile,
            self.setting_site_token,
            self.connect_site_button,
            self.disconnect_site_button,
        ):
            widget.setEnabled(site_enabled)
        self.export_upload_button.setEnabled(
            site_enabled and self._site_allows("export")
        )
        if not self._site_allows("export"):
            self.export_upload_button.setToolTip(
                "Nesta versão, a integração está liberada para Mercado e "
                "Ranking de EXP."
            )
        self.site_profile_status = _label(
            "Verificando token salvo para Mercado e Ranking de EXP…"
            if site_enabled
            else "Integração com o site desativada neste perfil de homologação.",
            "muted",
        )
        self.site_profile_status.setWordWrap(True)
        profile_form.addRow(self.site_profile_status)
        return profile

    def _build_local_api_panel(self) -> QtWidgets.QWidget:
        local_api = QtWidgets.QFrame(objectName="panel")
        local_api_layout = QtWidgets.QVBoxLayout(local_api)
        local_api_layout.addWidget(_label("API local", "subtitle"))
        self.setting_local_api = QtWidgets.QCheckBox(
            "Ativar saída somente neste computador"
        )
        local_api_layout.addWidget(self.setting_local_api)
        port_row = QtWidgets.QHBoxLayout()
        port_row.addWidget(_label("Porta", "muted"))
        self.setting_local_api_port = QtWidgets.QSpinBox()
        self.setting_local_api_port.setRange(1024, 65535)
        self.setting_local_api_port.setValue(LOCAL_API_DEFAULT_PORT)
        port_row.addWidget(self.setting_local_api_port)
        self.local_api_copy_token = QtWidgets.QPushButton("Copiar token")
        self.local_api_copy_token.setEnabled(False)
        self.local_api_copy_token.clicked.connect(self._copy_local_api_token)
        port_row.addWidget(self.local_api_copy_token)
        port_row.addStretch(1)
        local_api_layout.addLayout(port_row)
        self.local_api_status = _label(
            "Desativada. O token permanece protegido localmente.", "muted"
        )
        self.local_api_status.setWordWrap(True)
        local_api_layout.addWidget(self.local_api_status)
        local_api_layout.addStretch(1)
        return local_api

    def _build_integration_health_panel(self) -> QtWidgets.QWidget:
        health = QtWidgets.QFrame(objectName="accentPanel")
        layout = QtWidgets.QGridLayout(health)
        layout.addWidget(_label("Saúde do programa", "subtitle"), 0, 0, 1, 4)
        self.integration_health_labels: dict[str, QtWidgets.QLabel] = {}
        for column, (key, title) in enumerate((
            ("capture", "Captura"),
            ("memory", "Memória"),
            ("checkpoint", "Checkpoint"),
            ("stream", "Stream"),
        )):
            layout.addWidget(_label(title, "muted"), 1, column)
            value = _label("—", "info")
            value.setWordWrap(True)
            layout.addWidget(value, 2, column)
            self.integration_health_labels[key] = value
        return health

    def _build_settings_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(objectName="pageConfigurações")
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        self.settings_sections = QtWidgets.QTabWidget(objectName="settingsSections")
        self.settings_sections.addTab(self._build_settings_general_page(), "Geral")
        self.settings_sections.addTab(
            self._build_integrations_page(), "Integrações e API"
        )
        self.settings_sections.currentChanged.connect(
            lambda _index: self._render_integration_health()
        )
        column.addWidget(self.settings_sections, 1)
        return page

    def _build_settings_general_page(self) -> QtWidgets.QWidget:
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
        self.setting_memory_limit = QtWidgets.QSpinBox()
        self.setting_memory_limit.setRange(
            MIN_MEMORY_BUDGET_MB, MAX_MEMORY_BUDGET_MB
        )
        self.setting_memory_limit.setSingleStep(MEMORY_BUDGET_STEP_MB)
        self.setting_memory_limit.setSuffix(" MiB")
        self.setting_memory_limit.setToolTip(
            "Orçamento de memória do RF QOL. Limites menores reduzem filas, "
            "eventos recentes, históricos e caches. Filas em uso mudam na "
            "próxima ativação da captura ou dos monitores."
        )
        self.setting_memory_limit.valueChanged.connect(
            self._update_memory_limit_summary
        )
        capture_form.addRow("Limite de RAM", self.setting_memory_limit)
        self.setting_memory_summary = _label("", "muted")
        self.setting_memory_summary.setWordWrap(True)
        capture_form.addRow("", self.setting_memory_summary)
        self.setting_memory_limit.setValue(self.memory_limits["budget_mb"])
        self._update_memory_limit_summary(self.setting_memory_limit.value())
        self.setting_language = QtWidgets.QComboBox(); self.setting_language.addItem("Português", "pt"); self.setting_language.addItem("English", "en")
        capture_form.addRow("Idioma dos dados do jogo", self.setting_language)
        grid.addWidget(capture, 1, 0)

        shortcuts = QtWidgets.QFrame(objectName="panel")
        shortcuts_form = QtWidgets.QFormLayout(shortcuts)
        shortcuts_form.addRow(_label("Atalhos dos monitores", "subtitle"))
        self.setting_shortcuts: dict[str, QtWidgets.QComboBox] = {}
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
        self.setting_detailed_log = QtWidgets.QCheckBox("Log completo (sempre ativo)")
        self.setting_detailed_log.setChecked(True)
        self.setting_detailed_log.setEnabled(False)
        self.setting_detailed_log.setToolTip(
            "Registra sempre ações e etapas internas. Pode aumentar o tamanho do arquivo; "
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
        self.retry_license_button = QtWidgets.QPushButton("Tentar validar agora")
        self.retry_license_button.clicked.connect(
            lambda: self._refresh_license_online(force=True)
        )
        license_layout.addWidget(self.retry_license_button)
        license_layout.addStretch(1)
        grid.addWidget(license_panel, 0, 0)

        support = QtWidgets.QFrame(objectName="panel")
        support_layout = QtWidgets.QVBoxLayout(support)
        support_layout.addWidget(_label("Suporte e atualização", "subtitle"))
        support_layout.addWidget(_label("Discord oficial · carvalho@tuta.com", "muted"))
        support_layout.addWidget(_label(f"Versão instalada: {VERSION}", "muted"))
        update_row = QtWidgets.QHBoxLayout()
        manual_update = UPDATE_MODE == "manual"
        self.update_channel = QtWidgets.QComboBox(); self.update_channel.addItem("Estável", "stable"); self.update_channel.addItem("Beta", "beta")
        self.update_channel.setEnabled(not manual_update)
        self.update_button = QtWidgets.QPushButton("Abrir Discord para atualizações" if manual_update else "Verificar atualização")
        self.update_button.clicked.connect(self._open_discord if manual_update else self._check_update)
        self.rollback_button = QtWidgets.QPushButton("Rollback somente por instalação manual" if manual_update else "Abrir versão anterior")
        self.rollback_button.clicked.connect(self._rollback)
        self.rollback_button.setEnabled(not manual_update)
        update_row.addWidget(self.update_channel); update_row.addWidget(self.update_button); update_row.addWidget(self.rollback_button)
        support_layout.addLayout(update_row)
        self.update_progress = QtWidgets.QProgressBar(); self.update_progress.setRange(0,100); self.update_progress.setValue(0)
        self.update_status = _label(
            "Atualização automática desativada. Instale novas versões manualmente."
            if manual_update else "Atualização não verificada.",
            "muted",
        )
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
        grid.addWidget(storage, 1, 1)

        actions = QtWidgets.QHBoxLayout(); actions.addStretch(1)
        cancel_settings = QtWidgets.QPushButton("Cancelar"); cancel_settings.clicked.connect(self._load_settings_fields)
        save_settings = QtWidgets.QPushButton("Salvar configurações"); save_settings.clicked.connect(self._save_settings)
        actions.addWidget(cancel_settings); actions.addWidget(save_settings)
        grid.addLayout(actions, 3, 0, 1, 2)
        scroll.setWidget(content)
        column.addWidget(scroll, 1)
        return page

    def _update_memory_limit_summary(self, value: int) -> None:
        limits = memory_limits_for_budget(value)
        summary = (
            f"Até {limits['pending_packets']:,} pacotes e "
            f"{limits['pending_packet_bytes'] // 1024**2} MiB por fila · "
            f"{limits['events']:,} eventos recentes · "
            f"{limits['pvp_rows']} linhas do Banco PvP."
        ).replace(",", ".")
        self.setting_memory_summary.setText(summary)

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
        self.setting_memory_limit.setValue(
            memory_limits_for_budget(preferences.get("memory_limit_mb"))["budget_mb"]
        )
        language = "en" if preferences.get("item_name_language") == "en" else "pt"
        self.setting_language.setCurrentIndex(self.setting_language.findData(language))
        self.setting_profile.setText(
            self.site_profile.profile or str(preferences.get("profile") or "")
        )
        self.site_profile_status.setText(
            "Integração com o site desativada neste perfil de homologação."
            if not SITE_SERVER
            else f"Conectado ao Profile {self.site_profile.profile} para Mercado e Ranking de EXP."
            if self.site_profile.connected
            else "Token do Profile ainda não validado. Integração disponível para Mercado e Ranking de EXP."
        )
        shortcuts = dict(preferences.get("shortcuts") or {})
        for mode, combo in self.setting_shortcuts.items():
            combo.setCurrentText(str(shortcuts.get(mode) or DEFAULT_GLOBAL_SHORTCUTS[mode]))
        self._apply_monitor_shortcut_labels(shortcuts)
        self.setting_minimize.setChecked(bool(preferences.get("minimize_to_tray", False)))
        self.setting_auto_export.setChecked(bool(preferences.get("auto_export", False)))
        self.setting_auto_market.setChecked(bool(preferences.get("auto_market_upload", True)))
        self.setting_delete_export.setChecked(bool(preferences.get("delete_after_export", False)))
        self.setting_detailed_log.setChecked(True)
        self.setting_local_api.setChecked(bool(preferences.get("local_api_enabled", False)))
        self.setting_local_api_port.setValue(
            self._bounded(
                preferences.get("local_api_port"),
                1024,
                65535,
                LOCAL_API_DEFAULT_PORT,
            )
        )
        monitor_intervals = dict(preferences.get("monitor_intervals") or {})
        monitor_focus = dict(preferences.get("monitor_focus") or {})
        for mode, controls in self.monitor_controls.items():
            if mode == "pvp":
                try:
                    interval = float(monitor_intervals.get(mode, 1.0))
                except (TypeError, ValueError):
                    interval = 1.0
                controls["interval"].setValue(max(0.5, min(60.0, interval)))
            else:
                default = 2 if mode == "boss" else 3
                controls["interval"].setValue(
                    self._bounded(monitor_intervals.get(mode), 1, 60, default)
                )
            if controls.get("focus") is not None:
                controls["focus"].setChecked(bool(monitor_focus.get(mode, False)))
        alerts = dict(preferences.get("alerts") or {})
        self.alert_character_enabled.setChecked(bool(alerts.get("characters_enabled")))
        self.alert_character_names.setText(str(alerts.get("characters") or ""))
        self.alert_guild_enabled.setChecked(bool(alerts.get("guilds_enabled")))
        self.alert_guild_names.setText(str(alerts.get("guilds") or ""))
        self.alert_pvp_hit.setChecked(bool(alerts.get("pvp_hit")))
        self.alert_boss.setChecked(bool(alerts.get("boss_detected")))
        self.alert_item_drop.setChecked(bool(alerts.get("item_drop")))
        raw_drop_rarities = alerts.get("drop_rarities")
        selected_drop_rarities = (
            {
                int(value)
                for value in raw_drop_rarities
                if isinstance(value, (int, float, str))
                and str(value).lstrip("-").isdigit()
            }
            if isinstance(raw_drop_rarities, list)
            else set(self.alert_drop_rarities)
        )
        for grade, option in self.alert_drop_rarities.items():
            option.setChecked(grade in selected_drop_rarities)
        raw_drop_types = alerts.get("drop_types")
        selected_drop_types = (
            {str(value) for value in raw_drop_types}
            if isinstance(raw_drop_types, list)
            else set(self.alert_drop_types)
        )
        for category, option in self.alert_drop_types.items():
            option.setChecked(category in selected_drop_types)
        self.alert_low_hp.setChecked(bool(alerts.get("low_hp")))
        self.alert_low_hp_percent.setValue(
            self._bounded(alerts.get("low_hp_percent"), 1, 99, 30)
        )
        self.alert_threat.setChecked(bool(alerts.get("threat")))
        self.alert_farm_started.setChecked(bool(alerts.get("farm_started")))
        self.alert_teleporting.setChecked(bool(alerts.get("teleporting")))
        self.alert_cooldown_seconds.setValue(
            self._bounded(alerts.get("cooldown_seconds"), 5, 300, 10)
        )
        self.alert_sound.setChecked(bool(alerts.get("sound", True)))
        self.alert_sound_file = str(alerts.get("sound_file") or "")
        self.alert_sound_name.setText(
            "Som WAV personalizado" if self._resolved_alert_sound() else ""
        )
        self.subsession_duration.setValue(self._bounded(preferences.get("subsession_duration_minutes"), 0, 1440, 30))
        self.subsession_auto_next.setChecked(
            bool(preferences.get("auto_subsession", False))
        )
        self.subsession_auto_minutes.setValue(
            self._bounded(preferences.get("auto_subsession_minutes"), 5, 240, 30)
        )
        self.subsession_auto_context.setChecked(
            bool(preferences.get("auto_subsession_context", False))
        )
        self.subsession_end_on_teleport.setChecked(
            bool(preferences.get("subsession_end_on_teleport", False))
        )
        self.subsession_end_on_death.setChecked(
            bool(preferences.get("subsession_end_on_death", False))
        )
        self.subsession_end_after_no_kill.setChecked(
            bool(preferences.get("subsession_end_after_no_kill", False))
        )
        self._refresh_subsession_favorites()
        channel = str(preferences.get("channel") or "stable")
        index = self.update_channel.findData(channel)
        self.update_channel.setCurrentIndex(max(0, index))
        self.setting_storage.setText(f"Capturas: {self.setting_capture_directory.text()}\nRetenção: até exclusão manual após exportação validada.")

    def _save_settings(self) -> None:
        capture_directory = Path(self.setting_capture_directory.text().strip())
        shortcuts = {mode: combo.currentText() for mode, combo in self.setting_shortcuts.items()}
        old_language = game_data_language(
            self.preferences.get("item_name_language")
        )
        new_language = game_data_language(self.setting_language.currentData())
        old_memory_budget = self.memory_limits["budget_mb"]
        new_memory_limits = memory_limits_for_budget(
            self.setting_memory_limit.value()
        )
        selected_farm = (
            self.subsession_map.currentText(),
            self.subsession_spot.currentText(),
        )
        if old_language == "pt" and new_language == "en":
            selected_farm = FARM_LABELS_PT_EN.get(selected_farm, selected_farm)
        elif old_language == "en" and new_language == "pt":
            selected_farm = FARM_LABELS_EN_PT.get(selected_farm, selected_farm)
        if not capture_directory.is_absolute():
            QtWidgets.QMessageBox.warning(self, "Configurações", "Escolha uma pasta absoluta para as capturas.")
            return
        if len(set(shortcuts.values())) != len(shortcuts):
            QtWidgets.QMessageBox.warning(self, "Configurações", "Cada ação precisa usar uma tecla de atalho diferente.")
            return
        self.preferences = save_preferences({
            "capture_directory": str(capture_directory),
            "decode_interval_seconds": self.setting_decode_interval.value(),
            "memory_limit_mb": new_memory_limits["budget_mb"],
            "item_name_language": new_language,
            "subsession_map": selected_farm[0],
            "subsession_spot": selected_farm[1],
            "profile": self.setting_profile.text().strip(),
            "shortcuts": shortcuts,
            "minimize_to_tray": self.setting_minimize.isChecked(),
            "auto_export": self.setting_auto_export.isChecked(),
            "auto_market_upload": self.setting_auto_market.isChecked(),
            "delete_after_export": self.setting_delete_export.isChecked(),
            "detailed_logging": True,
            "local_api_enabled": self.setting_local_api.isChecked(),
            "local_api_port": self.setting_local_api_port.value(),
            "channel": self.update_channel.currentData(),
            "monitor_intervals": {
                mode: controls["interval"].value()
                for mode, controls in self.monitor_controls.items()
            },
            "monitor_focus": {
                mode: bool(controls.get("focus") and controls["focus"].isChecked())
                for mode, controls in self.monitor_controls.items()
                if mode in {"pvp", "boss"}
            },
            "alerts": self._alert_preferences(),
        }, self.preferences_path)
        for engine in (self.capture_engine, self.monitor_engine):
            map_module = getattr(engine, "map_module", None)
            if map_module is not None:
                map_module.set_language(new_language)
        self.memory_limits = new_memory_limits
        self.snapshot_reader.character_history_limit = self.memory_limits[
            "character_history"
        ]
        while len(self.inventory_icon_cache) > self.memory_limits["inventory_icons"]:
            self.inventory_icon_cache.popitem(last=False)
        while len(self.alert_last_fired) > self.memory_limits["alert_cooldowns"]:
            self.alert_last_fired.popitem(last=False)
        while len(self.seen_drop_alerts) > self.memory_limits["seen_drop_events"]:
            self.seen_drop_alerts.pop(next(iter(self.seen_drop_alerts)))
        self.memory_next_sample = 0.0
        set_detailed(self.log, True)
        self.log.debug(
            "settings_saved decode_interval=%s language=%s minimize=%s auto_export=%s "
            "delete_after_export=%s",
            self.setting_decode_interval.value(),
            self.setting_language.currentData(),
            self.setting_minimize.isChecked(),
            self.setting_auto_export.isChecked(),
            self.setting_delete_export.isChecked(),
        )
        memory_restart_pending = False
        if not self.capture_engine or not self.capture_engine.current_session:
            self.capture_engine = None
            self._ensure_capture_engine()
        elif old_memory_budget != self.memory_limits["budget_mb"]:
            configure = getattr(
                self.capture_engine, "configure_memory_budget", None
            )
            memory_restart_pending = not bool(
                callable(configure)
                and configure(self.memory_limits["budget_mb"])
            )
        if self.monitor_engine and not self.monitor_engine.active:
            self.monitor_engine = None
        elif (
            self.monitor_engine
            and old_memory_budget != self.memory_limits["budget_mb"]
        ):
            configure = getattr(
                self.monitor_engine, "configure_memory_budget", None
            )
            memory_restart_pending = memory_restart_pending or not bool(
                callable(configure)
                and configure(self.memory_limits["budget_mb"])
            )
        if self._bank_is_visible(0):
            self._render_pvp_database()
        elif self.pvp_database_table.rowCount() > self.memory_limits["pvp_rows"]:
            self.pvp_database_table.setRowCount(0)
            self.pvp_database_rows = {}
        self._refresh_farm_catalog()
        self._render_overview()
        if old_language != new_language:
            self._load_readonly_data()
        self._apply_monitor_shortcut_labels(shortcuts)
        self._sync_global_hotkeys(shortcuts)
        self._sync_local_api()
        self.setting_storage.setText(f"Capturas: {capture_directory}\nPreferências salvas para a interface estável e para o preview.")
        QtWidgets.QMessageBox.information(
            self,
            "Configurações",
            "Configurações salvas."
            + (
                " O novo limite completo será usado na próxima ativação "
                "da captura ou dos monitores."
                if memory_restart_pending else ""
            ),
        )

    def _map_api_snapshot(self) -> dict[str, object]:
        if not self.license_active or "map" not in self.license_features:
            return {
                "available": False,
                "reason": (
                    "feature_required" if self.license_active else "license_required"
                ),
                "capacity": 2,
                "clients": [],
            }
        return dict(self.snapshot.get("map") or {})

    def _status_api_snapshot(self) -> dict[str, object]:
        if not self.license_active:
            return {"schema_version": 1, "enabled_modes": [], "clients": []}
        return dict(self.program_status_snapshot)

    def _health_api_snapshot(self) -> dict[str, object]:
        now_ns = time.time_ns()
        engine = self.capture_engine
        if engine and getattr(engine, "active", False):
            capture_state = "active"
        elif engine and getattr(engine, "paused", False):
            capture_state = "paused"
        elif engine and getattr(engine, "current_session", None):
            capture_state = "pending"
        else:
            capture_state = "idle"

        checkpoints = self.snapshot.get("session_checkpoints")
        latest_checkpoint = (
            dict(checkpoints[0])
            if isinstance(checkpoints, list)
            and checkpoints
            and isinstance(checkpoints[0], dict)
            else {}
        )
        checkpoint_ns = int(latest_checkpoint.get("checkpoint_ns") or 0)
        checkpoint_age = (
            max(0.0, (now_ns - checkpoint_ns) / 1_000_000_000)
            if checkpoint_ns > 0 else None
        )

        stream_available = False
        stream_metrics: dict[str, object] = {}
        stream_candidates = (
            (self.monitor_engine, "events"),
            (engine, "live_events"),
        )
        for stream_engine, attribute in stream_candidates:
            if not stream_engine or not getattr(stream_engine, "active", False):
                continue
            stream_available = True
            reporter = getattr(getattr(stream_engine, attribute, None), "metrics", None)
            if callable(reporter):
                try:
                    stream_metrics = dict(reporter())
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    stream_metrics = {}
            break
        if stream_available and not stream_metrics:
            stream_metrics = dict(self.latest_monitor_metrics)

        memory_bytes = _process_memory_bytes()
        memory_budget_bytes = int(self.memory_limits["pressure_bytes"])
        return {
            "generated_at_ns": now_ns,
            "process": {
                "version": VERSION,
                "memory_bytes": memory_bytes,
                "memory_budget_bytes": memory_budget_bytes,
                "memory_pressure": (
                    memory_bytes >= memory_budget_bytes
                    if memory_bytes is not None else None
                ),
            },
            "capture": {
                "state": capture_state,
                "session_available": bool(
                    (engine and getattr(engine, "current_session", None))
                    or self.snapshot.get("session_id")
                ),
            },
            "checkpoint": {
                "available": bool(latest_checkpoint),
                "reason": latest_checkpoint.get("reason"),
                "age_seconds": checkpoint_age,
            },
            "stream": {
                **stream_metrics,
                "available": stream_available,
            },
        }

    def _render_integration_health(self) -> None:
        if not hasattr(self, "integration_health_labels"):
            return
        health = self._health_api_snapshot()
        process = dict(health.get("process") or {})
        capture = dict(health.get("capture") or {})
        checkpoint = dict(health.get("checkpoint") or {})
        stream = dict(health.get("stream") or {})
        capture_labels = {
            "active": "Ativa",
            "paused": "Pausada",
            "pending": "Aguardando leitura",
            "idle": "Ociosa",
        }
        self.integration_health_labels["capture"].setText(
            capture_labels.get(str(capture.get("state") or ""), "Indisponível")
        )
        memory = process.get("memory_bytes")
        budget = process.get("memory_budget_bytes")
        self.integration_health_labels["memory"].setText(
            f"{self._format_bytes(int(memory))} / {self._format_bytes(int(budget))}"
            if isinstance(memory, int) and isinstance(budget, int)
            else "Indisponível"
        )
        if checkpoint.get("available"):
            age = checkpoint.get("age_seconds")
            reason = {
                "interval": "Salvamento periódico",
                "paused": "Pausa salva",
                "finalized": "Sessão finalizada",
            }.get(str(checkpoint.get("reason") or ""), "Sessão salva")
            self.integration_health_labels["checkpoint"].setText(
                f"{reason} · há {int(age)} s"
                if isinstance(age, (int, float)) else reason
            )
        else:
            self.integration_health_labels["checkpoint"].setText("Ainda não criado")
        if stream.get("available"):
            dropped = int(stream.get("dropped_packets") or 0) + int(
                stream.get("dropped_events") or 0
            )
            self.integration_health_labels["stream"].setText(
                f"Fila {int(stream.get('queue_depth') or 0)} · descartes {dropped}"
            )
        else:
            self.integration_health_labels["stream"].setText("Inativo")
        if hasattr(self, "overview_memory_limit"):
            memory_mb = (
                float(memory) / (1024 * 1024)
                if isinstance(memory, int) else None
            )
            budget_mb = (
                float(budget) / (1024 * 1024)
                if isinstance(budget, int) else float(self.memory_limits["budget_mb"])
            )
            self.overview_memory_limit.setText(f"Limite  {budget_mb:.0f} MiB")
            self.overview_memory_use.setText(
                f"Em uso  {memory_mb:.0f} MiB"
                if memory_mb is not None else "Em uso  —"
            )
            self.overview_queue.setText(
                f"Fila  {int(stream.get('queue_depth') or 0)} / "
                f"{int(stream.get('event_limit') or 0):,}".replace(",", ".")
                if stream.get("available") else "Fila  inativa"
            )
            if checkpoint.get("available"):
                age = checkpoint.get("age_seconds")
                self.overview_checkpoint.setText(
                    f"Checkpoint  {int(age)}s"
                    if isinstance(age, (int, float)) else "Checkpoint  salvo"
                )
            else:
                self.overview_checkpoint.setText("Checkpoint  —")
            self.memory_sparkline.add_sample(memory_mb, budget_mb)

    def _build_program_status_snapshot(self) -> dict[str, object]:
        alerts = self._alert_preferences()
        return build_program_status(
            self.snapshot.get("combat_monitors") or [],
            self.snapshot.get("map") or {}
            if "map" in self.license_features
            else {},
            self._combat_decode_modes(),
            low_hp_percent=int(alerts.get("low_hp_percent") or 30),
            client_keys=(_client_key(index) for index in self.visible_client_slots),
        )

    def _render_program_status(self) -> None:
        if not hasattr(self, "top_program_status"):
            return
        snapshot = self._build_program_status_snapshot()
        self.program_status_snapshot = snapshot
        self._evaluate_status_alerts(snapshot)
        key = _client_key(self.active_client)
        client = next(
            (item for item in snapshot.get("clients") or [] if item.get("client_key") == key),
            None,
        )
        labels = {
            "teleporting": "Teleportando",
            "pvp": "PvP",
            "boss": "Boss",
            "farm": "Farm",
            "idle": "Ocioso",
        }
        status = str((client or {}).get("display_status") or "idle")
        display = labels.get(status, "Ocioso")
        self.top_program_status.setText(display.upper())
        self.top_program_status.setProperty(
            "role",
            "info" if status == "teleporting"
            else "warning" if status in {"pvp", "boss"}
            else "ok" if status == "farm"
            else "muted",
        )
        self.top_program_status.style().unpolish(self.top_program_status)
        self.top_program_status.style().polish(self.top_program_status)
        if hasattr(self, "dashboard_status"):
            signals = dict((client or {}).get("signals") or {})
            activity = str((client or {}).get("activity") or "unknown")
            activity_labels = {
                "farm": "Dano ou abate de mob nos últimos 30 segundos",
                "pvp": "Dano PvP causado ou recebido",
                "boss": "Boss reconhecido próximo",
                "idle": "Nenhuma atividade detectada",
                "unknown": "Monitor aguardando",
            }
            self.dashboard_status.setText(f"{display}  •")
            self.dashboard_status.setProperty(
                "role",
                "info" if status == "teleporting"
                else "warning" if status in {"pvp", "boss"}
                else "ok" if status == "farm"
                else "muted",
            )
            self.dashboard_status.style().unpolish(self.dashboard_status)
            self.dashboard_status.style().polish(self.dashboard_status)
            self.dashboard_activity.setText(
                "Teleporte confirmado em andamento"
                if status == "teleporting"
                else activity_labels.get(activity, "Monitor aguardando")
            )
            threat = signals.get("threat")
            attacked = signals.get("under_attack")
            self.dashboard_threat.setText(
                "Ameaça próxima" if threat is True
                else "Sem ameaça" if threat is False
                else "Ameaça não monitorada"
            )
            self.dashboard_attack.setText(
                "Sendo atacado" if attacked is True
                else "Não sendo atacado" if attacked is False
                else "Ataque não monitorado"
            )
        self._render_general_summary()

    def _sync_local_api(self) -> None:
        if not hasattr(self, "setting_local_api"):
            return
        enabled = self.setting_local_api.isChecked()
        if not enabled or not self.license_active:
            if self.local_api:
                self.local_api.stop()
                self.local_api = None
            self.local_api_token = ""
            self.local_api_copy_token.setEnabled(False)
            self.local_api_status.setText(
                "Desativada. Ative uma licença válida primeiro."
                if enabled
                else "Desativada. O token permanece protegido localmente."
            )
            return
        port = self.setting_local_api_port.value()
        if self.local_api and self.local_api.active and self.local_api.port == port:
            self.local_api_copy_token.setEnabled(bool(self.local_api_token))
            self.local_api_status.setText(
                f"Ativa em http://127.0.0.1:{port} · somente leitura."
            )
            return
        if self.local_api:
            self.local_api.stop()
            self.local_api = None
        try:
            self.local_api_token = LocalApiTokenStore(
                self.local_api_state_path
            ).load_or_create()
            api = LocalOutputApi(
                self._map_api_snapshot,
                self.local_api_token,
                status_provider=self._status_api_snapshot,
                health_provider=self._health_api_snapshot,
                port=port,
            )
            actual_port = api.start()
            self.local_api = api
        except (OSError, ValueError) as error:
            self.local_api_token = ""
            self.local_api_copy_token.setEnabled(False)
            self.local_api_status.setText(
                f"Não foi possível iniciar a API local: {error}"
            )
            self.log.warning(
                "local_api_start_failed error_type=%s", type(error).__name__
            )
            return
        self.local_api_copy_token.setEnabled(True)
        self.local_api_status.setText(
            f"Ativa em http://127.0.0.1:{actual_port} · somente leitura."
        )
        self.log.info("local_api_started port=%s", actual_port)

    def _copy_local_api_token(self) -> None:
        if not self.local_api_token:
            return
        QtWidgets.QApplication.clipboard().setText(self.local_api_token)
        self.local_api_status.setText(
            "Token copiado. Compartilhe somente com integrações locais confiáveis."
        )

    def _alert_preferences(self) -> dict[str, object]:
        return {
            "characters_enabled": self.alert_character_enabled.isChecked(),
            "characters": self.alert_character_names.text().strip(),
            "guilds_enabled": self.alert_guild_enabled.isChecked(),
            "guilds": self.alert_guild_names.text().strip(),
            "pvp_hit": self.alert_pvp_hit.isChecked(),
            "boss_detected": self.alert_boss.isChecked(),
            "item_drop": self.alert_item_drop.isChecked(),
            "drop_rarities": [
                grade
                for grade, option in self.alert_drop_rarities.items()
                if option.isChecked()
            ],
            "drop_types": [
                category
                for category, option in self.alert_drop_types.items()
                if option.isChecked()
            ],
            "low_hp": self.alert_low_hp.isChecked(),
            "low_hp_percent": self.alert_low_hp_percent.value(),
            "threat": self.alert_threat.isChecked(),
            "farm_started": self.alert_farm_started.isChecked(),
            "teleporting": self.alert_teleporting.isChecked(),
            "cooldown_seconds": self.alert_cooldown_seconds.value(),
            "sound": self.alert_sound.isChecked(),
            "sound_file": self.alert_sound_file,
        }

    def _evaluate_status_alerts(self, snapshot: dict[str, object]) -> None:
        clients = {
            str(item.get("client_key") or ""): item
            for item in snapshot.get("clients") or []
            if isinstance(item, dict) and item.get("client_key")
        }
        if not self.previous_program_status:
            self.previous_program_status = clients
            return
        for client_key, current in clients.items():
            previous = self.previous_program_status.get(client_key, {})
            signals = dict(current.get("signals") or {})
            previous_signals = dict(previous.get("signals") or {})
            try:
                client_index = ord(client_key.rsplit(":", 1)[-1]) - ord("a")
            except (TypeError, ValueError):
                client_index = -1
            client_name = (
                self._client_title(client_index)
                if 0 <= client_index < CLIENT_SLOT_COUNT
                else client_key
            )
            if self.alert_threat.isChecked() and signals.get("threat") is True:
                self._fire_alert(
                    f"status-threat:{client_key}",
                    f"Ameaça em {client_name}: inimigo confirmado próximo.",
                )
            if (
                self.alert_farm_started.isChecked()
                and current.get("activity") == "farm"
                and previous.get("activity") != "farm"
            ):
                self._fire_alert(
                    f"status-farm:{client_key}",
                    f"{client_name} entrou no estado Farm.",
                )
            if (
                self.alert_teleporting.isChecked()
                and signals.get("teleporting") is True
                and previous_signals.get("teleporting") is not True
            ):
                self._fire_alert(
                    f"status-teleport:{client_key}",
                    f"Teleporte confirmado em {client_name}.",
                )
        self.previous_program_status = clients

    @property
    def _alert_sounds_directory(self) -> Path:
        return (
            MACHINE_STATE_DIR / "sounds"
            if self.preferences_path == PREFERENCES_PATH
            else self.preferences_path.parent / "sounds"
        )

    def _resolved_alert_sound(self) -> Path | None:
        return resolve_alert_sound(
            self._alert_sounds_directory, self.alert_sound_file
        )

    def _choose_alert_sound(self) -> None:
        selected, _filter = QtWidgets.QFileDialog.getOpenFileName(
            self, "Escolher som do alerta", "", "Áudio WAV (*.wav)"
        )
        if not selected:
            return
        try:
            self.alert_sound_file = install_alert_sound(
                Path(selected), self._alert_sounds_directory
            )
        except (OSError, ValueError) as error:
            QtWidgets.QMessageBox.warning(self, "Som personalizado", str(error))
            return
        self.alert_sound_name.setText("Som WAV personalizado")
        self.alert_status.setText("Som validado. Salve os alertas para manter a escolha.")

    def _clear_alert_sound(self) -> None:
        self.alert_sound_file = ""
        self.alert_sound_name.clear()
        self.alert_status.setText("Som padrão selecionado. Salve os alertas.")

    def _test_alert_sound(self) -> None:
        play_alert_sound(
            self._resolved_alert_sound(), QtWidgets.QApplication.beep
        )

    def _save_alert_settings(self) -> None:
        self.preferences = save_preferences(
            {"alerts": self._alert_preferences()}, self.preferences_path
        )
        self.drop_alert_next_due = 0.0
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
        if self.local_api:
            self.local_api.stop()
            self.local_api = None
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
        for overlay in (
            self.boss_overlay,
            self.boss_dps_overlay,
            *self.pvp_overlays.values(),
        ):
            if overlay is not None:
                overlay.close()
        if self.item_icon_zip is not None:
            self.item_icon_zip.close()
            self.item_icon_zip = None
        self.log.info("app_closed")
        super().closeEvent(event)

    @QtCore.Slot(str)
    def _global_hotkey_action(self, action: str) -> None:
        self.log.debug("global_hotkey_triggered action=%s", action)
        if action == "start":
            self._start_capture()
        elif action == "stop":
            self._stop_capture()
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

    def _captured_client_name(self, index: int) -> str:
        profiles = list(self.snapshot.get("profiles") or [])
        key = _client_key(index)
        profile = next(
            (item for item in profiles if item.get("client_key") == key), None
        )
        if profile is None and not any(item.get("client_key") for item in profiles):
            profile = profiles[index] if index < len(profiles) else None
        return str((profile or {}).get("name") or "").strip()

    @staticmethod
    def _normalize_visible_client_slots(
        value: object, legacy_count: int
    ) -> list[int]:
        slots: list[int] = []
        if isinstance(value, list):
            for raw in value:
                try:
                    index = int(raw)
                except (TypeError, ValueError):
                    continue
                if 0 <= index < CLIENT_SLOT_COUNT and index not in slots:
                    slots.append(index)
        if not slots:
            slots = list(range(max(1, min(CLIENT_SLOT_COUNT, legacy_count))))
        if 0 not in slots:
            slots.insert(0, 0)
        return slots

    def _client_name(self, index: int) -> str:
        try:
            display_index = self.visible_client_slots.index(index)
        except ValueError:
            display_index = index
        return _client_label(display_index)

    @staticmethod
    def _client_source_key(index: int) -> str:
        return "pc" if index < PC_SLOT_COUNT else "emulator"

    def _client_source_label(self, index: int) -> str:
        return "PC local" if self._client_source_key(index) == "pc" else "Emulador local"

    def _client_title(self, index: int, captured: str = "") -> str:
        name = self._client_name(index)
        captured = str(captured or self._captured_client_name(index)).strip()
        if captured and captured.casefold() != name.casefold():
            return f"{name} - {captured}"
        return name

    def _refresh_client_labels(self) -> None:
        for index, button in enumerate(self.client_buttons):
            captured = self._captured_client_name(index)
            suffix = f" · {captured}" if captured else ""
            button.setText(f"{self._client_name(index)}{suffix}")
        for mode, controls in self.monitor_controls.items():
            tabs = controls.get("tabs")
            if tabs is not None:
                for index in range(CLIENT_SLOT_COUNT):
                    tabs.setTabText(index, self._client_name(index))
                self._update_monitor_button(mode)
        if hasattr(self, "subsession_client"):
            for index in range(CLIENT_SLOT_COUNT):
                self.subsession_client.setItemText(index, self._client_name(index))
        if hasattr(self, "subsession_filter"):
            for index in range(CLIENT_SLOT_COUNT):
                self.subsession_filter.setItemText(index + 1, self._client_name(index))
        if hasattr(self, "drops_client_filter"):
            for index in range(CLIENT_SLOT_COUNT):
                self.drops_client_filter.setItemText(
                    index + 1, self._client_name(index)
                )
        for (_mode, index), button in self.send_buttons.items():
            if index >= 0:
                button.setText(f"Enviar {self._client_title(index)}")

    def _persist_client_collection(self) -> None:
        self.visible_client_count = len(self.visible_client_slots)
        self.preferences = save_preferences(
            {
                "visible_client_count": self.visible_client_count,
                "visible_client_slots": list(self.visible_client_slots),
            },
            self.preferences_path,
        )

    def _sync_client_collection(self) -> None:
        visible = set(self.visible_client_slots)
        self.visible_client_count = len(self.visible_client_slots)
        if self.active_client not in visible:
            self.active_client = self.visible_client_slots[0]
        for index, button in enumerate(self.client_buttons):
            button.setVisible(index in visible)
            button.setChecked(index == self.active_client)
        self.add_client_button.setEnabled(len(visible) < CLIENT_SLOT_COUNT)
        self.add_client_button.setToolTip(
            "Escolha entre PC local, Emulador local ou Externo via API."
            if len(visible) < CLIENT_SLOT_COUNT
            else f"Limite técnico atual: {CLIENT_SLOT_COUNT} clientes locais."
        )
        self.remove_client_button.setVisible(len(visible) > 1)
        self.remove_client_button.setEnabled(self.active_client != 0)
        self.client_source.setText(self._client_source_label(self.active_client))
        self._refresh_client_labels()
        for mode, controls in self.monitor_controls.items():
            tabs = controls.get("tabs")
            if tabs is not None:
                for index in range(CLIENT_SLOT_COUNT):
                    tabs.setTabVisible(index, index in visible)
                tabs.setCurrentIndex(self.active_client)
            elif mode == "boss":
                for index, card in enumerate(
                    self.combat_page_layouts[mode]["cards"]
                ):
                    card.setVisible(index in visible)
        for (_mode, index), button in self.send_buttons.items():
            if index >= 0:
                button.setVisible(index in visible)
        self._sync_combat_layout()

    def _add_client_slot(self, source: str | None = None) -> None:
        source_labels = {
            "PC local": "pc",
            "Emulador local": "emulator",
            "Externo via API": "remote_api",
        }
        if source is None:
            selected, accepted = QtWidgets.QInputDialog.getItem(
                self,
                "Adicionar cliente",
                "Qual é a fonte do cliente?",
                tuple(source_labels),
                0,
                False,
            )
            if not accepted:
                return
            source = source_labels.get(str(selected))
        if source == "remote_api":
            QtWidgets.QMessageBox.information(
                self,
                "Externo via API",
                "A origem externa já faz parte do fluxo planejado, mas a consulta "
                "LAN e o pareamento ainda não estão disponíveis neste candidato. "
                "Nenhum cliente foi adicionado.",
            )
            return
        ranges = {
            "pc": range(PC_SLOT_COUNT),
            "emulator": range(PC_SLOT_COUNT, CLIENT_SLOT_COUNT),
        }
        slots = ranges.get(str(source))
        if slots is None:
            return
        index = next(
            (candidate for candidate in slots if candidate not in self.visible_client_slots),
            None,
        )
        if index is None:
            label = "PC local" if source == "pc" else "Emulador local"
            QtWidgets.QMessageBox.warning(
                self,
                "Adicionar cliente",
                f"Todas as vagas de {label} já estão em uso.",
            )
            return
        self.visible_client_slots.append(index)
        self.active_client = index
        self._persist_client_collection()
        self._sync_client_collection()
        if self._client_allowed(index):
            self.client_buttons[index].click()

    def _remove_selected_client(self) -> None:
        index = self.active_client
        if index == 0 or index not in self.visible_client_slots:
            return
        answer = QtWidgets.QMessageBox.question(
            self,
            "Excluir cliente",
            f"Excluir {self._client_name(index)} da interface?\n\n"
            "Sessões, capturas e dados armazenados não serão apagados.",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Cancel,
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.monitor_client_enabled["pve"][index] = False
        self.monitor_client_enabled["pvp"][index] = False
        self.visible_client_slots.remove(index)
        self.active_client = self.visible_client_slots[0]
        self._persist_client_collection()
        self._sync_client_collection()
        if self._client_allowed(self.active_client):
            self.client_buttons[self.active_client].click()

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
        elif self.subsession_auto_context.isChecked():
            self.subsession_map.setCurrentIndex(-1)
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
            "auto_context": self.subsession_auto_context.isChecked(),
            "end_on_teleport": self.subsession_end_on_teleport.isChecked(),
            "end_on_death": self.subsession_end_on_death.isChecked(),
            "end_after_no_kill": self.subsession_end_after_no_kill.isChecked(),
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
            self._bounded(values.get("client"), 0, CLIENT_SLOT_COUNT - 1, 0)
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
        self.subsession_auto_context.blockSignals(True)
        self.subsession_end_on_teleport.setChecked(
            bool(values.get("end_on_teleport"))
        )
        self.subsession_end_on_death.setChecked(bool(values.get("end_on_death")))
        self.subsession_end_after_no_kill.setChecked(
            bool(values.get("end_after_no_kill"))
        )
        self.subsession_auto_context.setChecked(bool(values.get("auto_context")))
        self.subsession_auto_context.blockSignals(False)

    def _toggle_auto_context(self, enabled: bool) -> None:
        if enabled:
            self.subsession_map.setCurrentIndex(-1)
            self.subsession_spot.setCurrentIndex(-1)
            self.subsession_mobs.clear()

    def _fill_subsession_from_current_context(self) -> None:
        index = self.subsession_client.currentIndex()
        client_key = _client_key(index)
        self._apply_manual_map_fallbacks()
        map_snapshot = self.snapshot.get("map")
        map_clients = (
            map_snapshot.get("clients") or []
            if isinstance(map_snapshot, dict)
            else []
        )
        spatial = next(
            (
                dict(item)
                for item in map_clients
                if isinstance(item, dict) and item.get("client_key") == client_key
            ),
            {},
        )
        location = (
            spatial
            if spatial.get("map_enabled") is True
            and (
                not spatial.get("stale")
                or spatial.get("map_source") == "manual_fallback"
            )
            else {}
        )
        monitors = [
            dict(item)
            for item in self.snapshot.get("combat_monitors") or []
            if isinstance(item, dict)
        ]
        monitor = next(
            (
                item for item in monitors
                if item.get("client_key") == client_key
            ),
            {},
        )
        if not monitor and not any(item.get("client_key") for item in monitors):
            monitor = monitors[index] if index < len(monitors) else {}
        context = infer_subsession_context(monitor, location, self.farm_catalog)
        map_name = str(context.get("map_name") or "").strip()
        spot_name = str(context.get("spot_name") or "").strip()
        mobs = list(dict.fromkeys(
            str(value).strip()
            for value in context.get("mobs") or []
            if str(value).strip()
        ))

        if map_name:
            map_index = self.subsession_map.findText(map_name)
            if map_index < 0:
                self.subsession_map.addItem(map_name)
                map_index = self.subsession_map.findText(map_name)
            self.subsession_map.setCurrentIndex(map_index)
            spot_index = self.subsession_spot.findText(spot_name) if spot_name else -1
            if spot_name and spot_index < 0:
                self.subsession_spot.addItem(spot_name)
                spot_index = self.subsession_spot.findText(spot_name)
            self.subsession_spot.setCurrentIndex(spot_index)

        if mobs:
            self._populate_subsession_mobs(spot_name, set(mobs))
            listed = {
                str(
                    self.subsession_mobs.item(row).data(
                        QtCore.Qt.ItemDataRole.UserRole
                    )
                    or self.subsession_mobs.item(row).text()
                )
                for row in range(self.subsession_mobs.count())
            }
            self.subsession_other_mob.setText(
                ", ".join(value for value in mobs if value not in listed)
            )

        found = []
        if map_name:
            found.append("mapa")
        if spot_name:
            found.append("spot")
        if mobs:
            found.append(f"{len(mobs)} mob(s)")
        if not found:
            message = (
                f"Nenhuma localização ou mob próximo recente foi encontrado para "
                f"{self._client_name(index)}."
            )
            role = "warning"
        else:
            message = (
                f"Preenchido com {', '.join(found)} de {self._client_name(index)}."
            )
            if map_name and mobs and not spot_name:
                message += " O spot ficou vazio porque não houve correspondência única."
            role = "ok" if spot_name or not map_name else "warning"
        self.subsession_context_status.setText(message)
        self.subsession_context_status.setProperty("role", role)
        self.subsession_context_status.style().unpolish(
            self.subsession_context_status
        )
        self.subsession_context_status.style().polish(
            self.subsession_context_status
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
        key = _client_key(index)
        profiles = list(self.snapshot.get("profiles") or [])
        profile = next((item for item in profiles if item.get("client_key") == key), None)
        if profile is None and not any(item.get("client_key") for item in profiles):
            profile = profiles[index] if index < len(profiles) else None
        return str(profile.get("uid")) if profile and profile.get("uid") else None

    def _overview_character(
        self, index: int
    ) -> tuple[dict[str, Any] | None, dict[str, Any], bool]:
        """Retorna o personagem atual com fallback seguro do histórico."""
        key = _client_key(index)
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
                biosuit_name=game_catalog_name(
                    biosuit,
                    self.preferences.get("item_name_language"),
                ),
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
                rover_name=game_catalog_name(
                    rover,
                    self.preferences.get("item_name_language"),
                ),
                rover_grade=rover.get("grade"),
            )
            used = True
        return character, summary, used

    def _uid_selections(self) -> dict[str, str]:
        value = self.preferences.get("client_uid_selections")
        return {
            str(key): str(uid)
            for key, uid in (value.items() if isinstance(value, dict) else ())
            if key in {_client_key(index) for index in range(CLIENT_SLOT_COUNT)} and uid
        }

    def _refresh_client_uid_tooltips(self) -> None:
        history = {
            str(item.get("uid")): str(item.get("name") or "")
            for item in self.snapshot.get("character_history") or []
            if item.get("uid")
        }
        selections = self._uid_selections()
        for index, button in enumerate(self.client_buttons):
            uid = selections.get(_client_key(index))
            button.setToolTip(
                "Clique duas vezes para definir o UID. Vínculo atual: "
                + (
                    f"{history.get(uid) or 'personagem conhecido'} · UID {uid}"
                    if uid
                    else "detecção automática"
                )
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
        current_uid = self._uid_selections().get(_client_key(index))
        current = next(
            (position for position, (_label, uid) in enumerate(choices) if uid == current_uid),
            0,
        )
        selected, accepted = QtWidgets.QInputDialog.getItem(
            self,
            f"UID do {_client_label(index)}",
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
        key = _client_key(index)
        selections = self._uid_selections()
        if uid and any(
            selected == uid and selected_key != key
            for selected_key, selected in selections.items()
        ):
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
        self._refresh_client_uid_tooltips()
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
        session_id = str(
            (self.capture_engine.current_session if self.capture_engine else None)
            or self.snapshot.get("session_id")
            or ""
        )
        if not session_id:
            QtWidgets.QMessageBox.warning(self, "Subsessão", "Nenhuma sessão está disponível.")
            return
        map_name, spot_name = self.subsession_map.currentText(), self.subsession_spot.currentText()
        mobs = self._selected_mobs()
        extra = self.subsession_other_mob.text().strip()
        if extra:
            mobs.extend(value.strip() for value in extra.split(",") if value.strip())
        auto_context = self.subsession_auto_context.isChecked()
        if not auto_context and (not map_name or not spot_name or not mobs):
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
            name=self.subsession_name.text().strip() or spot_name or "Subsessão automática",
            character_uid=self._client_uid_for(index),
            client_key=f"client:{chr(97 + index)}",
            location=" > ".join(value for value in (map_name, spot_name) if value),
            map_name=map_name,
            spot_name=spot_name,
            mobs=list(dict.fromkeys(mobs)),
            mob_levels=levels,
            auto_context=auto_context,
            duration_minutes=self.subsession_duration.value(),
            end_on_teleport=self.subsession_end_on_teleport.isChecked(),
            end_on_death=self.subsession_end_on_death.isChecked(),
            end_after_no_kill=self.subsession_end_after_no_kill.isChecked(),
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
            "auto_subsession": self.subsession_auto_next.isChecked(),
            "auto_subsession_minutes": self.subsession_auto_minutes.value(),
            "subsession_map": map_name,
            "subsession_spot": spot_name,
            "auto_subsession_context": auto_context,
            "subsession_end_on_teleport": self.subsession_end_on_teleport.isChecked(),
            "subsession_end_on_death": self.subsession_end_on_death.isChecked(),
            "subsession_end_after_no_kill": self.subsession_end_after_no_kill.isChecked(),
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
        key = str(item.get("client_key") or "client:a")
        self.subsession_client.setCurrentIndex(
            max(0, min(CLIENT_SLOT_COUNT - 1, ord(key[-1]) - 97))
        )
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
        self.subsession_auto_context.blockSignals(True)
        self.subsession_auto_context.setChecked(bool(item.get("auto_context")))
        self.subsession_auto_context.blockSignals(False)
        self.subsession_end_on_teleport.setChecked(bool(item.get("end_on_teleport")))
        self.subsession_end_on_death.setChecked(bool(item.get("end_on_death")))
        self.subsession_end_after_no_kill.setChecked(bool(item.get("end_after_no_kill")))
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
        create_next = self.subsession_auto_next.isChecked()
        next_duration = self.subsession_auto_minutes.value()
        store = CaptureStore(self.database_path)
        changed = False
        monitors = {
            str(item.get("client_key") or ""): item
            for item in self.snapshot.get("combat_monitors") or []
            if isinstance(item, dict)
        }
        spatial_clients = {
            str(item.get("client_key") or ""): item
            for item in (self.snapshot.get("map") or {}).get("clients") or []
            if isinstance(item, dict)
        }
        try:
            for active in store.subsessions(session_id):
                if active.get("ended_ns") is not None:
                    continue
                duration = int(active.get("duration_minutes") or 0)
                timed_boundary = (
                    int(active["started_ns"])
                    + duration * 60 * 1_000_000_000
                    if duration > 0 else None
                )
                signal = automatic_subsession_end(
                    active,
                    monitors.get(str(active.get("client_key") or "")),
                    spatial_clients.get(str(active.get("client_key") or "")),
                    now_ns=now,
                )
                boundaries = [
                    (timed_boundary, "duração") if timed_boundary else None,
                    signal,
                ]
                boundaries = [item for item in boundaries if item is not None]
                if not boundaries:
                    continue
                boundary_ns, end_reason = min(boundaries)
                if now < boundary_ns:
                    continue
                store.end_subsession(str(active["id"]), boundary_ns)
                self.log.info(
                    "subsession_auto_ended id=%s reason=%s boundary_ns=%s delay_ms=%s",
                    active["id"],
                    end_reason,
                    boundary_ns,
                    max(0, (now - boundary_ns) // 1_000_000),
                )
                if create_next and end_reason == "duração":
                    store.start_subsession(
                        f"{session_id}-sub-{boundary_ns}-{active.get('client_key') or 'geral'}",
                        session_id,
                        str(active.get("name") or "Subsessão automática"),
                        character_uid=active.get("character_uid"),
                        client_key=str(active.get("client_key") or ""),
                        location=str(active.get("location") or ""),
                        map_name=str(active.get("map_name") or ""),
                        spot_name=str(active.get("spot_name") or ""),
                        mobs=list(active.get("mobs") or []),
                        mob_levels=dict(active.get("mob_levels") or {}),
                        auto_context=bool(active.get("auto_context")),
                        context_source=active.get("context_source"),
                        context_confidence=active.get("context_confidence"),
                        context_observation_count=int(
                            active.get("context_observation_count") or 0
                        ),
                        context_first_seen_ns=active.get("context_first_seen_ns"),
                        context_updated_ns=active.get("context_updated_ns"),
                        duration_minutes=next_duration,
                        end_on_teleport=bool(active.get("end_on_teleport")),
                        end_on_death=bool(active.get("end_on_death")),
                        end_after_no_kill=bool(active.get("end_after_no_kill")),
                        started_ns=boundary_ns,
                    )
                    self.log.info(
                        "subsession_auto_started previous_id=%s boundary_ns=%s duration_minutes=%s",
                        active["id"],
                        boundary_ns,
                        next_duration,
                    )
                changed = True
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

    def _selected_subsession_card_fields(self) -> list[str]:
        return [
            key for key, _label_text, _width, _visible in SUBSESSION_COLUMNS[1:]
            if key != "exp_hour_percent"
            and self.subsession_card_field_actions[key].isChecked()
        ]

    def _apply_subsession_card_fields(self, fields: object) -> None:
        selected = {
            str(key) for key in (fields if isinstance(fields, (list, tuple, set)) else [])
            if str(key) in self.subsession_card_field_widgets
        }
        active = bool(getattr(self, "_overview_has_subsession", False))
        for key, widget in self.subsession_card_field_widgets.items():
            widget.setVisible(
                active and key in selected and key != "exp_hour_percent"
            )

    def _set_subsession_card_field_visible(self, key: str, visible: bool) -> None:
        if key not in self.subsession_card_field_actions:
            return
        action = self.subsession_card_field_actions[key]
        if action.isChecked() != visible:
            action.blockSignals(True)
            action.setChecked(visible)
            action.blockSignals(False)
        selected = self._selected_subsession_card_fields()
        self._apply_subsession_card_fields(selected)
        self.preferences = save_preferences(
            {"subsession_card_fields": selected}, self.preferences_path
        )

    def _reset_subsession_card_fields(self) -> None:
        selected = set(SUBSESSION_CARD_DEFAULT_FIELDS)
        for key, action in self.subsession_card_field_actions.items():
            action.blockSignals(True)
            action.setChecked(key in selected)
            action.blockSignals(False)
        self._apply_subsession_card_fields(selected)
        self.preferences = save_preferences(
            {"subsession_card_fields": list(SUBSESSION_CARD_DEFAULT_FIELDS)},
            self.preferences_path,
        )

    def _subsession_display_values(
        self,
        item: dict[str, object],
        summary: dict[str, object],
        duration: int,
    ) -> dict[str, str]:
        profiles = list(self.snapshot.get("profiles") or [])
        profiles_by_client = {
            profile.get("client_key"): str(profile.get("name") or "")
            for profile in profiles if isinstance(profile, dict) and profile.get("client_key")
        }
        profiles_by_uid = {
            profile.get("uid"): str(profile.get("name") or "")
            for profile in profiles if isinstance(profile, dict) and profile.get("uid")
        }
        exp_total = int(summary.get("exp_gained") or 0)
        hours = duration / 3600 if duration else 0
        exp_percent = summary.get("exp_gained_percent")
        exp_hour = round(exp_total / hours) if hours else 0
        exp_hour_percent = (
            float(exp_percent) / hours
            if hours and isinstance(exp_percent, (int, float)) else None
        )
        credits = int(summary.get("credits") or 0)
        contribution = summary.get("contribution")
        rarity = dict(summary.get("loot_by_rarity") or {})
        contribution_hour = (
            round(float(contribution) / hours)
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
        client_key = str(item.get("client_key") or "client:a")
        try:
            client_index = max(
                0, min(CLIENT_SLOT_COUNT - 1, ord(client_key[-1]) - 97)
            )
        except (IndexError, TypeError):
            client_index = 0
        return {
            "select": "",
            "name": str(item.get("name") or "—")
            + (f"\n{location}" if location else ""),
            "character": character,
            "client": self._client_name(client_index),
            "status": "Em andamento" if item.get("ended_ns") is None else "Encerrada",
            "time": (
                f"{duration // 3600:02d}:"
                f"{duration // 60 % 60:02d}:{duration % 60:02d}"
            ),
            "map": str(item.get("map_name") or "—"),
            "spot": str(item.get("spot_name") or "—"),
            "mobs": ", ".join(str(value) for value in item.get("mobs") or []) or "—",
            "levels": levels or "—",
            "context": (
                f"Automático · {int(item.get('context_observation_count') or 0)} leituras"
                if item.get("context_confidence") == "stable"
                else "Manual" if item.get("context_source") == "manual"
                else "Automático · aguardando" if item.get("auto_context")
                else "Manual"
            ),
            "mau": self._subsession_usage_state(item.get("mau_state")),
            "launcher": self._subsession_usage_state(item.get("launcher_state")),
            "exp_potion": self._subsession_usage_state(
                item.get("exp_potion_state")
            ),
            "kills": self._format_value(int(summary.get("kills") or 0)),
            "finalizations": self._format_value(int(summary.get("finalizations") or 0)),
            "exp_total": self._format_value(exp_total),
            "exp_percent": self._format_value(exp_percent, "%"),
            "exp_hour": (
                f"{self._format_value(exp_hour)} "
                f"({self._format_value(exp_hour_percent, '%')})"
            ),
            "exp_hour_percent": self._format_value(exp_hour_percent, "%"),
            "credits": self._format_value(credits),
            "credits_hour": self._format_value(round(credits / hours) if hours else 0),
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

    @staticmethod
    def _subsession_usage_state(value: object) -> str:
        return {
            "detected": "Uso detectado",
            "not_detected": "Não detectado",
            "pending_evidence": "Aguardando captura validada",
        }.get(str(value or ""), "Aguardando captura validada")

    def _filtered_subsessions(self) -> list[dict[str, object]]:
        items = list(self.snapshot.get("subsessions") or [])
        view = self.subsession_filter.currentText()
        labels = {
            self._client_name(index): _client_key(index)
            for index in range(CLIENT_SLOT_COUNT)
        }
        if view in labels:
            items = [item for item in items if item.get("client_key") == labels[view]]
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
        self.subsession_table.blockSignals(True)
        self.subsession_table.setRowCount(len(visible))
        for row, item in enumerate(visible):
            summary = dict(summaries.get(item["id"]) or {})
            ended = item.get("ended_ns") or time.time_ns()
            duration = max(0, int((ended - item["started_ns"]) / 1_000_000_000))
            location = str(item.get("location") or "").strip()
            values = self._subsession_display_values(item, summary, duration)
            for column, (key, _label, _width, _visible) in enumerate(
                SUBSESSION_COLUMNS
            ):
                text = values[key]
                cell = QtWidgets.QTableWidgetItem(text)
                if key == "select":
                    cell.setFlags(cell.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                    cell.setCheckState(QtCore.Qt.CheckState.Checked if item["id"] in self.selected_subsessions else QtCore.Qt.CheckState.Unchecked)
                    cell.setData(QtCore.Qt.ItemDataRole.UserRole, item["id"])
                elif key in {"name", "mobs", "levels", "context"}:
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
        inventory_count = sum(
            len(items)
            for items in dict(snapshot.get("inventories") or {}).values()
        )
        self.send_status_labels["inventory"].setText(
            f"{inventory_count} item(ns) lido(s)"
            if inventory_count else "Nenhum item identificado"
        )
        self.send_status_labels["all"].setText("Envio completo separado por cliente")
        self._set_send_controls()

    def _inventory_icon(self, item_index: int) -> QtGui.QIcon:
        cached = self.inventory_icon_cache.get(item_index)
        if cached is not None:
            self.inventory_icon_cache.move_to_end(item_index)
            return cached
        icon = QtGui.QIcon()
        try:
            if self.item_icon_zip is None and ITEM_ICON_ARCHIVE.is_file():
                self.item_icon_zip = zipfile.ZipFile(ITEM_ICON_ARCHIVE)
            if self.item_icon_zip is not None:
                pixmap = QtGui.QPixmap()
                pixmap.loadFromData(
                    self.item_icon_zip.read(f"{item_index}.webp"), "WEBP"
                )
                if not pixmap.isNull():
                    icon = QtGui.QIcon(pixmap.scaled(
                        INVENTORY_ICON_SIZE,
                        INVENTORY_ICON_SIZE,
                        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                        QtCore.Qt.TransformationMode.SmoothTransformation,
                    ))
        except (KeyError, OSError, zipfile.BadZipFile):
            pass
        if icon.isNull():
            icon = self.style().standardIcon(
                QtWidgets.QStyle.StandardPixmap.SP_FileIcon
            )
        self.inventory_icon_cache[item_index] = icon
        while len(self.inventory_icon_cache) > self.memory_limits["inventory_icons"]:
            self.inventory_icon_cache.popitem(last=False)
        return icon

    def _render_inventory(self, _filter: str = "") -> None:
        if not hasattr(self, "inventory_table"):
            return
        uid = self._client_uid_for(self.active_client)
        items = list(
            dict(self.snapshot.get("inventories") or {}).get(str(uid or ""), [])
        )
        category = self.inventory_category_tabs.tabData(
            self.inventory_category_tabs.currentIndex()
        )
        items = [
            item
            for item in items
            if self._inventory_category(item) == category
        ]
        query = self.inventory_search.text().strip().casefold()
        if query:
            items = [
                item
                for item in items
                if query in str(item.get("name") or "").casefold()
                or query in str(item.get("item_index") or "")
            ]
        items.sort(
            key=lambda item: (
                str(item.get("name") or "").casefold(),
                int(item.get("slot") or 0),
            )
        )
        self.inventory_table.setRowCount(len(items))
        for row, item in enumerate(items):
            item_index = int(item.get("item_index") or 0)
            refinement = int(item.get("refinement") or 0)
            name = str(item.get("name") or f"Item {item_index}")
            label = f"{name}  +{refinement}" if refinement else name
            name_cell = QtWidgets.QTableWidgetItem(
                self._inventory_icon(item_index), label
            )
            name_cell.setData(QtCore.Qt.ItemDataRole.UserRole, item_index)
            name_cell.setToolTip(f"Item {item_index}")
            rarity = int(item.get("rarity") or 0)
            color = RARITY_COLORS.get(rarity)
            if color:
                name_cell.setForeground(QtGui.QColor(color))
            quantity = QtWidgets.QTableWidgetItem(
                self._format_count(item.get("quantity"))
            )
            quantity.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            kind = QtWidgets.QTableWidgetItem(
                "Equipamento"
                if item.get("kind") == "equipment"
                else "Empilhável"
            )
            slot = QtWidgets.QTableWidgetItem(str(int(item.get("slot") or 0)))
            slot.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            for column, cell in enumerate((name_cell, quantity, kind, slot)):
                self.inventory_table.setItem(row, column, cell)
            self.inventory_table.setRowHeight(row, 54)
        total = sum(int(item.get("quantity") or 0) for item in items)
        character = self._captured_client_name(self.active_client)
        category_label = self.inventory_category_tabs.tabText(
            self.inventory_category_tabs.currentIndex()
        )
        self.inventory_status.setText(
            f"{character or self._client_name(self.active_client)} · "
            f"{category_label} · "
            f"{len(items)} item(ns) · quantidade total {self._format_count(total)}"
            if uid
            else "Aguardando o personagem deste cliente ser identificado."
        )

    def _render_exp_rank(self, _filter: str = "") -> None:
        if not hasattr(self, "exp_rank_table"):
            return
        if "exp-ranking" not in self.license_features:
            self.exp_rank_table.setRowCount(0)
            self.exp_rank_history_table.setRowCount(0)
            self.exp_rank_state.setText("Módulo não licenciado")
            self.exp_rank_status.setText(
                "Ranking de EXP não incluído nesta licença."
            )
            self._set_exp_rank_export_available()
            return
        ranking = dict(self.snapshot.get("exp_rank") or {})
        records = [
            dict(record)
            for record in (ranking.get("records") or [])
            if isinstance(record, dict)
            and 1 <= int(record.get("rank") or 0) <= 100
        ]
        query = self.exp_rank_search.text().strip().casefold()
        if query:
            records = [
                record
                for record in records
                if query in str(record.get("character_name") or "").casefold()
                or query in str(record.get("guild_name") or "").casefold()
            ]
        records.sort(key=lambda record: int(record.get("rank") or 0))

        self.exp_rank_table.setRowCount(len(records))
        for row, record in enumerate(records):
            rank = int(record.get("rank") or 0)
            previous_rank = int(record.get("previous_rank") or 0)
            change = previous_rank - rank if previous_rank > 0 else None
            change_text = (
                "—"
                if change is None
                else f"+{change}"
                if change > 0
                else str(change)
            )
            level, level_percent = exp_rank_level_progress(record.get("total_exp"))
            cells = (
                QtWidgets.QTableWidgetItem(str(rank)),
                QtWidgets.QTableWidgetItem(change_text),
                QtWidgets.QTableWidgetItem(
                    str(record.get("character_name") or "Não identificado")
                ),
                QtWidgets.QTableWidgetItem(str(record.get("guild_name") or "—")),
                QtWidgets.QTableWidgetItem(str(level) if level is not None else "—"),
                QtWidgets.QTableWidgetItem(
                    f"{level_percent:.2f}%".replace(".", ",")
                    if level_percent is not None else "—"
                ),
                QtWidgets.QTableWidgetItem(
                    self._format_count(record.get("total_exp"))
                ),
            )
            for column, cell in enumerate(cells):
                if column in (0, 1, 4, 5):
                    cell.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                elif column == 6:
                    cell.setTextAlignment(
                        QtCore.Qt.AlignmentFlag.AlignRight
                        | QtCore.Qt.AlignmentFlag.AlignVCenter
                    )
                if column in (4, 5):
                    cell.setToolTip(
                        "Calculado pela EXP total com a curva oficial 1.28.5."
                    )
                self.exp_rank_table.setItem(row, column, cell)

        history_rows = []
        for capture in self.snapshot.get("exp_rank_history") or []:
            if not isinstance(capture, dict):
                continue
            captured_at_ns = int(capture.get("captured_at_ns") or 0)
            for raw in capture.get("records") or []:
                if not isinstance(raw, dict):
                    continue
                if query and query not in " ".join((
                    str(raw.get("character_name") or ""),
                    str(raw.get("guild_name") or ""),
                )).casefold():
                    continue
                history_rows.append((captured_at_ns, raw))
        self.exp_rank_history_table.setRowCount(len(history_rows))
        for row, (captured_at_ns, record) in enumerate(history_rows):
            captured = (
                datetime.fromtimestamp(captured_at_ns / 1_000_000_000)
                .astimezone().strftime("%d/%m/%Y %H:%M:%S")
                if captured_at_ns > 0 else "—"
            )
            values = (
                captured,
                str(record.get("rank") or "—"),
                str(record.get("character_name") or "Não identificado"),
                str(record.get("level") or "—"),
                self._format_percent(record.get("level_percent")),
                self._format_count(record.get("total_exp")),
                self._format_signed_count(record.get("gained_exp")),
                self._format_signed_percent(record.get("gained_percent")),
                self._format_count(record.get("exp_per_hour")),
                self._format_signed_percent(record.get("exp_percent_per_hour")),
            )
            for column, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(value)
                if column != 2:
                    cell.setTextAlignment(
                        QtCore.Qt.AlignmentFlag.AlignRight
                        | QtCore.Qt.AlignmentFlag.AlignVCenter
                    )
                self.exp_rank_history_table.setItem(row, column, cell)

        completeness = str(ranking.get("completeness") or "")
        count = int(ranking.get("record_count") or len(ranking.get("records") or []))
        if not ranking or count <= 0:
            state_text, state_role = "Aguardando captura", "muted"
            status = (
                "Abra e percorra o Top 100 no jogo. O RF QOL observa a consulta "
                "sem controlar a tela."
            )
        else:
            complete = completeness == "complete"
            state_text = "Top 100 completo" if complete else "Captura parcial"
            state_role = "ok" if complete else "warning"
            details = [f"{count}/100 posições capturadas"]
            captured_at_ns = int(ranking.get("captured_at_ns") or 0)
            if captured_at_ns > 0:
                captured_at = datetime.fromtimestamp(
                    captured_at_ns / 1_000_000_000
                ).astimezone()
                details.append(captured_at.strftime("atualizado em %d/%m/%Y às %H:%M:%S"))
            conflicts = int(ranking.get("conflict_count") or 0)
            if conflicts:
                details.append(f"{conflicts} conflito(s) detectado(s)")
            missing = list(ranking.get("missing_positions") or [])
            if missing:
                preview = ", ".join(str(position) for position in missing[:10])
                suffix = f" e mais {len(missing) - 10}" if len(missing) > 10 else ""
                details.append(f"faltam {preview}{suffix}")
            if query:
                details.append(f"{len(records)} resultado(s) no filtro")
            status = " · ".join(details) + "."
        self.exp_rank_state.setText(state_text)
        self.exp_rank_state.setProperty("role", state_role)
        self.exp_rank_state.style().unpolish(self.exp_rank_state)
        self.exp_rank_state.style().polish(self.exp_rank_state)
        self.exp_rank_status.setText(status)
        self._set_exp_rank_export_available()

    def _set_exp_rank_export_available(self, _index: int = -1) -> None:
        if not hasattr(self, "exp_rank_export"):
            return
        table = (
            self.exp_rank_history_table
            if self.exp_rank_tabs.currentIndex() == 1
            else self.exp_rank_table
        )
        self.exp_rank_export.setEnabled(
            "exp-ranking" in self.license_features and table.rowCount() > 0
        )

    def _export_exp_rank_csv(self, path: Path | None = None) -> Path | None:
        explicit_path = path is not None
        table = (
            self.exp_rank_history_table
            if self.exp_rank_tabs.currentIndex() == 1
            else self.exp_rank_table
        )
        if "exp-ranking" not in self.license_features or table.rowCount() <= 0:
            if not explicit_path:
                QtWidgets.QMessageBox.information(
                    self,
                    "Ranking de EXP",
                    "Não existem registros disponíveis para exportar.",
                )
            return None
        if path is None:
            kind = "historico" if table is self.exp_rank_history_table else "atual"
            suggested = (
                Path.home()
                / f"ranking-exp-{kind}-{datetime.now():%Y%m%d-%H%M%S}.csv"
            )
            selected, _selected_filter = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Exportar Ranking de EXP",
                str(suggested),
                "Arquivo CSV (*.csv)",
            )
            if not selected:
                return None
            path = Path(selected)
        if path.suffix.casefold() != ".csv":
            path = path.with_suffix(".csv")
        headers = [
            str(table.horizontalHeaderItem(column).text())
            for column in range(table.columnCount())
        ]
        rows = [
            [
                str(table.item(row, column).text())
                if table.item(row, column) is not None else ""
                for column in range(table.columnCount())
            ]
            for row in range(table.rowCount())
        ]
        try:
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle, delimiter=";", lineterminator="\n")
                writer.writerow(headers)
                writer.writerows(rows)
        except OSError as error:
            if not explicit_path:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Ranking de EXP",
                    f"Não foi possível salvar o CSV: {error}",
                )
            return None
        if not explicit_path:
            self.exp_rank_status.setText(
                f"CSV exportado com {len(rows)} registro(s): {path}"
            )
        return path

    def _manual_map_fallbacks(self) -> dict[str, dict[str, object]]:
        raw = self.preferences.get("manual_map_fallbacks")
        if not isinstance(raw, dict):
            return {}
        result: dict[str, dict[str, object]] = {}
        for client_key, value in raw.items():
            if (
                not str(client_key).startswith("client:")
                or not isinstance(value, dict)
            ):
                continue
            name = str(value.get("map_name") or "").strip()[:160]
            region = str(value.get("region_name") or "").strip()[:160]
            if not name:
                continue
            try:
                index = int(value.get("map_index") or 0)
            except (TypeError, ValueError):
                index = 0
            if index not in MAP_PREVIEW_ASSETS:
                index = next((
                    candidate
                    for candidate in sorted(MAP_PREVIEW_ASSETS)
                    if any(
                        map_name(candidate, language).casefold() == name.casefold()
                        and str(
                            (map_region(candidate, None, language) or {}).get(
                                "region_name"
                            ) or ""
                        ).casefold() == region.casefold()
                        for language in ("pt", "en")
                    )
                ), 0)
            result[str(client_key)] = {
                "map_name": name,
                "region_name": region,
                "map_index": index or None,
            }
        return result

    def _apply_manual_map_fallbacks(self) -> None:
        self.snapshot["map"] = apply_manual_map_fallbacks(
            self.snapshot.get("map") or {}, self._manual_map_fallbacks()
        )

    def _set_manual_map_fallback(self) -> None:
        key = _client_key(self.active_client)
        language = str(self.preferences.get("item_name_language") or "pt")
        grouped_options: dict[str, dict[str, object]] = {}
        for index in sorted(MAP_CATALOG):
            resolved = map_name(index, language)
            fixed = map_region(index, None, language) or {}
            region = str(fixed.get("region_name") or "")
            display_value = f"{resolved} · {region}" if region else resolved
            group = grouped_options.setdefault(
                display_value.casefold(), {
                    "name": resolved,
                    "region": region,
                    "value": display_value,
                    "indices": [],
                }
            )
            group["indices"].append(index)
        options = [
            (
                f"{group['value']} · "
                + "/".join(f"#{index}" for index in group["indices"]),
                str(group["value"]),
            )
            for group in grouped_options.values()
        ]
        configured = self._manual_map_fallbacks().get(key, {})
        current_name = str(configured.get("map_name") or "")
        current_region = str(configured.get("region_name") or "")
        current = (
            f"{current_name} · {current_region}" if current_region else current_name
        )
        selected = self._choose_manual_map_name(options, current)
        if selected is None:
            return
        selected = str(selected).strip()[:320]
        selected_group = grouped_options.get(selected.casefold())
        manual_name = str(
            (selected_group or {}).get("name") or selected
        ).strip()[:160]
        manual_region = str(
            (selected_group or {}).get("region") or ""
        ).strip()[:160]
        selected_indices = list((selected_group or {}).get("indices") or [])
        manual_map_index = next(
            (index for index in selected_indices if index in MAP_PREVIEW_ASSETS),
            selected_indices[0] if selected_indices else 0,
        )
        if not manual_name:
            QtWidgets.QMessageBox.warning(
                self, "Mapa atual", "Informe um nome de mapa válido."
            )
            return
        fallbacks = self._manual_map_fallbacks()
        fallbacks[key] = {
            "map_name": manual_name,
            "region_name": manual_region,
            "map_index": manual_map_index or None,
        }
        self.preferences = save_preferences(
            {"manual_map_fallbacks": fallbacks}, self.preferences_path
        )
        self._apply_manual_map_fallbacks()
        self._render_map()

    def _choose_manual_map_name(
        self,
        options: list[tuple[str, str]],
        current: str,
    ) -> str | None:
        dialog = _MapSelectionDialog(options, current, self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None
        return dialog.selected_map_name()

    def _clear_manual_map_fallback(self) -> None:
        key = _client_key(self.active_client)
        fallbacks = self._manual_map_fallbacks()
        if key not in fallbacks:
            return
        fallbacks.pop(key, None)
        self.preferences = save_preferences(
            {"manual_map_fallbacks": fallbacks}, self.preferences_path
        )
        self._apply_manual_map_fallbacks()
        self._render_map()

    def _render_map(self) -> None:
        if not hasattr(self, "map_players_table"):
            return
        self._apply_manual_map_fallbacks()
        snapshot = dict(self.snapshot.get("map") or {})
        capacity = int(snapshot.get("capacity") or 2)
        active = int(snapshot.get("active_count") or 0)
        limited = int(snapshot.get("limited_count") or 0)
        self.map_capacity.setText(
            f"{active}/{capacity} vagas em uso"
            + (f" · {limited} limitado(s)" if limited else "")
        )
        key = _client_key(self.active_client)
        client = next(
            (
                dict(item)
                for item in (snapshot.get("clients") or [])
                if isinstance(item, dict) and item.get("client_key") == key
            ),
            {},
        )
        enabled = client.get("map_enabled") is True
        manual_fallback = client.get("map_source") == "manual_fallback"
        configured_fallback = key in self._manual_map_fallbacks()
        self.map_manual_clear.setEnabled(configured_fallback)
        self.map_manual_button.setText(
            "Alterar mapa manual" if configured_fallback else "Informar mapa atual"
        )
        position = dict(client.get("position") or {})
        players = [
            dict(item)
            for item in (client.get("nearby_players") or [])
            if isinstance(item, dict)
        ] if enabled else []

        if not client:
            state, role = "Aguardando rota", "muted"
            status = "Este cliente ainda não possui uma rota de rede identificada."
        elif not enabled:
            state, role = "Limite do Mapa", "warning"
            status = (
                "As duas vagas estão ocupadas. Este cliente continua disponível "
                "para captura e monitores independentes."
            )
        elif client.get("reason") == "awaiting_data":
            if manual_fallback:
                state, role = "Mapa informado manualmente", "warning"
                status = (
                    "O nome manual está sendo usado como fallback; o reconhecimento "
                    "automático continua ativo e assumirá assim que identificar o mapa."
                )
            else:
                state, role = "Aguardando coordenadas", "muted"
                status = "A rota está admitida; mova o personagem para confirmar a posição."
        else:
            state = "Posição antiga" if client.get("stale") else "Posição atual"
            role = "warning" if client.get("stale") else "ok"
            details = [str(client.get("character_name") or self._client_name(self.active_client))]
            age = client.get("age_seconds")
            if isinstance(age, (int, float)):
                details.append(f"observada há {float(age):.1f} s".replace(".", ","))
            if client.get("teleporting") is True:
                details.append("warp em andamento")
            if manual_fallback:
                details.append("nome manual temporário; automático ainda ativo")
            status = " · ".join(details) + "."
        self.map_state.setText(state)
        self.map_state.setProperty("role", role)
        self.map_state.style().unpolish(self.map_state)
        self.map_state.style().polish(self.map_state)
        self.map_status.setText(status)

        map_name = str(client.get("map_name") or "").strip()
        map_index = client.get("map_index")
        self.map_metric_labels["map"].setText(
            map_name
            or (
                f"Mapa #{int(map_index)}"
                if isinstance(map_index, (int, float))
                else "—"
            )
        )
        for coordinate in ("x", "y", "z"):
            value = position.get(coordinate)
            self.map_metric_labels[coordinate].setText(
                f"{float(value):.3f}".replace(".", ",")
                if isinstance(value, (int, float))
                else "—"
            )
        self.map_metric_labels["players"].setText(str(len(players)))
        if hasattr(self, "overview_map_name"):
            x_value, y_value = position.get("x"), position.get("y")
            coordinate_text = (
                f"{float(x_value):.0f}, {float(y_value):.0f}"
                if isinstance(x_value, (int, float))
                and isinstance(y_value, (int, float))
                else "—, —"
            )
            shown_map = map_name or (
                f"Mapa #{int(map_index)}"
                if isinstance(map_index, (int, float)) else "Mapa não identificado"
            )
            self.overview_coordinates.setText(coordinate_text)
            self.overview_map_name.setText(shown_map)
            region_name = str(client.get("region_name") or "").strip()
            region_center = dict(client.get("region_center") or {})
            center_x, center_y = region_center.get("x"), region_center.get("y")
            self.overview_map_region.setText(
                (
                    f"Região {region_name} · centro {float(center_x):.0f}, {float(center_y):.0f}"
                    if region_name
                    and isinstance(center_x, (int, float))
                    and isinstance(center_y, (int, float))
                    else f"Região {region_name}" if region_name else "Região —"
                )
            )
            self.overview_map_state.setText(state)
            self.overview_nearby_players.setText(
                f"Outros jogadores  {len(players)}"
            )
            player_names = list(dict.fromkeys(
                str(player.get("name") or "Não identificado").strip()
                or "Não identificado"
                for player in players
            ))
            shown_names = ", ".join(player_names[:6]) or "—"
            if len(player_names) > 6:
                shown_names += f" e mais {len(player_names) - 6}"
            self.overview_nearby_names.setText(f"Nomes: {shown_names}")
            self.overview_nearby_names.setToolTip(", ".join(player_names))
            self.overview_map_preview.set_snapshot(map_index, position, players)
            self.top_location.setText(
                f"{shown_map} · {region_name} · {coordinate_text}"
                if region_name and coordinate_text != "—, —"
                else f"{shown_map} · {coordinate_text}"
                if coordinate_text != "—, —" else shown_map
            )
            self.top_location.setProperty("role", "ok" if enabled else "muted")
            self.top_location.style().unpolish(self.top_location)
            self.top_location.style().polish(self.top_location)
        if hasattr(self, "map_page_preview"):
            self.map_page_preview.set_snapshot(map_index, position, players)

        self.map_players_table.setRowCount(len(players))
        for row, player in enumerate(players):
            player_position = dict(player.get("position") or {})
            distance = player.get("distance")
            values = (
                str(player.get("name") or "Não identificado"),
                str(player.get("guild_name") or "—"),
                *(
                    f"{float(player_position.get(axis)):.3f}".replace(".", ",")
                    if isinstance(player_position.get(axis), (int, float))
                    else "—"
                    for axis in ("x", "y", "z")
                ),
                f"{float(distance):.2f}".replace(".", ",")
                if isinstance(distance, (int, float))
                else "—",
            )
            for column, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(value)
                if column >= 2:
                    cell.setTextAlignment(
                        QtCore.Qt.AlignmentFlag.AlignRight
                        | QtCore.Qt.AlignmentFlag.AlignVCenter
                    )
                self.map_players_table.setItem(row, column, cell)

    def _inventory_category(self, item: dict[str, object]) -> str:
        overrides = dict(self.preferences.get("inventory_category_overrides") or {})
        item_index = str(int(item.get("item_index") or 0))
        category = str(overrides.get(item_index) or item.get("category") or "")
        allowed = {key for key, _label_text in INVENTORY_CATEGORIES}
        if category in allowed:
            return category
        return "equipment" if item.get("kind") == "equipment" else "other"

    def _apply_inventory_category_overrides(self) -> None:
        self._apply_inventory_overrides_to_snapshot(self.snapshot)

    def _apply_inventory_overrides_to_snapshot(self, snapshot: dict) -> None:
        for items in dict(snapshot.get("inventories") or {}).values():
            for item in items:
                if isinstance(item, dict):
                    item["category"] = self._inventory_category(item)
                    if str(item.get("item_index") or "") in dict(
                        self.preferences.get("inventory_category_overrides") or {}
                    ):
                        item["category_source"] = "manual"

    def _show_inventory_category_menu(self, position: QtCore.QPoint) -> None:
        row = self.inventory_table.rowAt(position.y())
        cell = self.inventory_table.item(row, 0) if row >= 0 else None
        if cell is None:
            return
        item_index = int(cell.data(QtCore.Qt.ItemDataRole.UserRole) or 0)
        if item_index <= 0:
            return
        current = next(
            (
                self._inventory_category(item)
                for items in dict(self.snapshot.get("inventories") or {}).values()
                for item in items
                if int(item.get("item_index") or 0) == item_index
            ),
            "other",
        )
        menu = QtWidgets.QMenu(self)
        for key, label in INVENTORY_CATEGORIES:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(key == current)
            action.triggered.connect(
                lambda checked=False, selected=key: self._set_inventory_category(
                    item_index, selected
                )
            )
        menu.exec(self.inventory_table.viewport().mapToGlobal(position))

    def _set_inventory_category(self, item_index: int, category: str) -> None:
        allowed = {key for key, _label_text in INVENTORY_CATEGORIES}
        if category not in allowed:
            return
        overrides = dict(self.preferences.get("inventory_category_overrides") or {})
        overrides[str(int(item_index))] = category
        self.preferences = save_preferences(
            {"inventory_category_overrides": overrides}, self.preferences_path
        )
        self._apply_inventory_category_overrides()
        self._render_inventory()
        self.inventory_status.setText(
            f"Categoria do item {item_index} atualizada manualmente."
        )

    def _site_allows(self, feature: str) -> bool:
        allows = getattr(self.site_profile, "allows", None)
        return bool(allows(feature)) if callable(allows) else True

    def _set_send_controls(self) -> None:
        enabled = bool(
            self.site_profile.connected
            and self.snapshot.get("session_id")
            and not self.site_busy
        )
        characters = [
            item for item in self.snapshot.get("characters") or [] if item.get("uid")
        ]
        collections_by_uid = dict(
            self.snapshot.get("collection_type_counts_by_uid") or {}
        )
        characters_by_client = {
            item.get("client_key"): str(item.get("uid"))
            for item in characters
            if item.get("client_key") and item.get("uid")
        }
        availability = {
            "market": any(
                int((item.get("summary") or {}).get("market_events") or 0)
                for item in characters
            ),
        }
        for (mode, _client), button in self.send_buttons.items():
            if mode == "market":
                mode_available = availability["market"]
            else:
                uid = characters_by_client.get(f"client:{chr(97 + _client)}")
                if uid is None and len(characters) == 1:
                    uid = str(characters[0]["uid"])
                if mode in {"character", "all"}:
                    mode_available = bool(uid)
                elif mode == "inventory":
                    mode_available = bool(
                        uid and dict(self.snapshot.get("inventories") or {}).get(uid)
                    )
                else:
                    kind = 1 if mode == "codex" else 2
                    mode_available = bool(
                        uid and dict(collections_by_uid.get(uid) or {}).get(kind)
                    )
            available = (
                enabled
                and self._site_allows(mode)
                and mode_available
                and (_client < 0 or self._client_allowed(_client))
            )
            button.setEnabled(available)
            button.setToolTip(
                ""
                if available
                else "Integração não liberada para este tipo de dado."
                if not self._site_allows(mode)
                else "Slot não incluído nesta licença."
                if _client >= 0 and not self._client_allowed(_client)
                else "Ainda não existem dados deste tipo disponíveis para envio."
            )
        selected_enabled = (
            enabled
            and self._site_allows("subsession")
            and bool(self.selected_subsessions)
        )
        for button in (self.send_selected_button, self.subsession_upload_button):
            button.setEnabled(selected_enabled)
            button.setToolTip(
                ""
                if selected_enabled
                else "Selecione uma subsessão encerrada e valide o token do Profile."
            )
        if hasattr(self, "auction_database_send"):
            auction_enabled = enabled and self._site_allows("auction-bank")
            self.auction_database_send.setEnabled(auction_enabled)
            self.auction_database_send.setToolTip(
                "Envia somente registros confirmados e sanitizados."
                if auction_enabled
                else "Valide o token do Profile para enviar o Banco de Leilão."
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

    def _refresh_license_online(self, *, force: bool = False) -> None:
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
            "license:refresh",
            lambda: self.license_client.refresh_if_due(VERSION, force=force),
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
        if UPDATE_MODE == "manual":
            self.update_status.setText(
                "Atualização automática desativada. Use o Discord oficial."
            )
            return
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
        if UPDATE_MODE == "manual":
            self.update_status.setText("Download automático desativado.")
            return
        self._run_site_operation(
            "update:download",
            lambda: download_release_with_rollback(
                release,
                lambda phase, downloaded, total: self.update_progress_changed.emit(
                    phase, downloaded, total
                ),
                UPDATES_DIR,
                current_version=VERSION,
                current_sequence=self.license_client.highest_release_sequence,
            ),
        )
    def _launch_update(self, installer: Path) -> None:
        if UPDATE_MODE == "manual":
            self.update_status.setText("Instalação automática desativada.")
            return
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
        if UPDATE_MODE == "manual":
            QtWidgets.QMessageBox.information(
                self,
                "Instalação manual",
                "Para voltar de versão, use somente um instalador compatível "
                "fornecido oficialmente.",
            )
            return
        try:
            installer = cached_rollback(
                UPDATES_DIR / "rollback",
                current_version=VERSION,
                current_sequence=self.license_client.highest_release_sequence,
            )
        except (OSError, ValueError, json.JSONDecodeError):
            QtWidgets.QMessageBox.information(
                self,
                "Versão anterior",
                "Não existe uma versão anterior compatível e assinada no cache.",
            )
            return
        engine = self.capture_engine
        if self.capture_busy or (engine and engine.current_session):
            QtWidgets.QMessageBox.warning(
                self,
                "Captura pendente",
                "Encerre a captura e aguarde a leitura terminar antes do rollback.",
            )
            return
        if QtWidgets.QMessageBox.question(
            self,
            "Restaurar versão anterior",
            "A versão anterior possui manifesto Ed25519, compatibilidade, "
            "tamanho e SHA-256 válidos. Um backup verificado do banco será "
            "criado e o Windows pedirá confirmação administrativa. Continuar?",
        ) != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            installer = cached_rollback(
                UPDATES_DIR / "rollback",
                current_version=VERSION,
                current_sequence=self.license_client.highest_release_sequence,
            )
            backup_database(
                self.database_path,
                UPDATES_DIR / "database-backups",
                VERSION,
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self.log.exception("rollback_installer_launch_failed")
            QtWidgets.QMessageBox.critical(self, "Rollback rejeitado", str(error))
            return
        script = (
            "Wait-Process -Id $args[0] -ErrorAction SilentlyContinue; "
            "Start-Process -FilePath $args[1]"
        )
        try:
            subprocess.Popen(
                [
                    "powershell.exe", "-NoProfile", "-NonInteractive",
                    "-WindowStyle", "Hidden", "-Command", script,
                    str(os.getpid()), str(installer.resolve()),
                ],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as error:
            self.log.exception("rollback_installer_launch_failed")
            QtWidgets.QMessageBox.critical(self, "Rollback rejeitado", str(error))
            return
        self.exit_requested = True
        self.close()

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
        if client_index >= 0 and not self._client_allowed(client_index):
            QtWidgets.QMessageBox.warning(
                self, "Envio", "Este slot não está incluído na licença atual."
            )
            return
        if not self.site_profile.connected:
            QtWidgets.QMessageBox.warning(
                self, "Envio", "Valide o token do Profile antes de enviar."
            )
            return
        target = 0 if client_index < 0 else client_index
        self.send_status_labels[mode].setText(
            "Lendo e enviando Mercado geral…"
            if mode == "market"
            else f"Lendo e enviando {self._client_title(target)}…"
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
                                restrict_to_clients=bool(engine.client_ports),
                            )
                finally:
                    store.close()
            snapshot = ReadOnlySnapshotReader(
                self.database_path, self.license_client
            ).load(language)
            self._apply_inventory_overrides_to_snapshot(snapshot)
            if mode == "all":
                return self.site_uploader.send_all(target, snapshot, language)
            return self.site_uploader.send_mode(mode, target, snapshot, language)

        self._run_site_operation(
            f"send:{mode}:{target}",
            read_and_send,
        )

    def _send_selected_subsessions(self) -> None:
        self._subsession_selection_changed()
        identifiers = sorted(self.selected_subsessions)
        if not identifiers:
            self.send_selected_status.setText(
                "Nenhuma Farm encerrada foi selecionada para envio."
            )
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

    def _send_auction_bank(self) -> None:
        session_id = str(
            (self.capture_engine and self.capture_engine.current_session)
            or self.snapshot.get("session_id")
            or self.last_capture_session
            or ""
        )
        if not session_id:
            self.auction_database_status.setText(
                "Nenhuma sessão disponível para envio."
            )
            return
        self.auction_database_status.setText("Enviando Banco de Leilão…")
        self._run_site_operation(
            "auction_bank",
            lambda: self.site_uploader.send_auction_bank(
                session_id,
                str(self.preferences.get("item_name_language") or "pt"),
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
                    f"Conectado ao Profile {data.get('profile')} para envio do Mercado."
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
                self._apply_license(self.license_client.local_status())
                self.license_title.setText("Licença ativada e salva")
        elif name == "license:refresh":
            if error is not None:
                self.log.warning("license_refresh_failed error=%s", type(error).__name__)
            self._apply_license(self.license_client.local_status())
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
        elif name == "auction_bank":
            if error is not None:
                self.auction_database_status.setText(f"Falha no envio: {error}")
                QtWidgets.QMessageBox.warning(
                    self, "Banco de Leilão", str(error)
                )
            else:
                data = dict(result or {})
                self.auction_database_status.setText(
                    f"Enviado · {data.get('listings', 0)} anúncio(s) · "
                    f"{data.get('transactions', 0)} transação(ões)."
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
        elif name == "observations:send":
            if error is not None:
                self.log.error(
                    "observation_upload_failed error_type=%s",
                    type(error).__name__,
                )
                if self._bank_is_visible(0):
                    self._render_pvp_database()
                elif self._bank_is_visible(1):
                    self._render_pve_database()
                self.pvp_database_status.setText(f"Falha no envio: {error}")
            else:
                data = dict(result or {})
                self.log.info(
                    "observation_upload_completed characters=%s pve_records=%s "
                    "pve_conflicts=%s skipped=%s",
                    data.get("sent_characters", 0),
                    data.get("sent_mobs", 0),
                    data.get("pve_conflicts", 0),
                    bool(data.get("skipped")),
                )
                if self._bank_is_visible(0):
                    self._render_pvp_database()
                elif self._bank_is_visible(1):
                    self._render_pve_database()
                characters = int(data.get("sent_characters") or 0)
                pve_records = int(data.get("sent_mobs") or 0)
                conflicts = int(data.get("pve_conflicts") or 0)
                parts = []
                if characters:
                    parts.append(f"{characters} UID(s) ao Banco Temporário")
                if pve_records:
                    parts.append(f"{pve_records} registro(s) do Banco PvE confirmado(s)")
                if conflicts:
                    parts.append(f"{conflicts} conflito(s) de HP em revisão")
                self.pvp_database_status.setText(
                    " · ".join(parts) + "." if parts else "Nenhuma mudança pendente."
                )
            QtCore.QTimer.singleShot(0, self._maybe_auto_exp_rank_upload)
        elif name == "observations:receive":
            if self._bank_is_visible(0):
                self._render_pvp_database()
            if error is not None:
                self.log.error(
                    "observation_download_failed error_type=%s",
                    type(error).__name__,
                )
                self.pvp_database_status.setText(f"Falha no recebimento: {error}")
            else:
                data = dict(result or {})
                self.pvp_database_status.setText(
                    f"Banco Final recebido · revisão {data.get('revision', 0)} · "
                    f"{data.get('synced_characters', 0)} UID(s)."
                )
        elif name == "auto_market":
            pending, self.pending_auto_market = self.pending_auto_market, None
            if error is not None:
                self.auto_market_retry_after = time.monotonic() + 60
                self.send_status_labels["market"].setText(
                    f"Falha no envio automático: {error}"
                )
                self.log.error(
                    "auto_market_upload_failed error_type=%s",
                    type(error).__name__,
                )
            elif pending:
                self.auto_market_retry_after = 0.0
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
            QtCore.QTimer.singleShot(0, self._maybe_auto_exp_rank_upload)
        elif name == "auto_exp_rank":
            pending, self.pending_auto_exp_rank = self.pending_auto_exp_rank, None
            if error is not None:
                self.auto_exp_rank_retry_after = time.monotonic() + 60
                self.log.error(
                    "auto_exp_rank_upload_failed error_type=%s",
                    type(error).__name__,
                )
            elif pending:
                self.auto_exp_rank_retry_after = 0.0
                snapshot_key, signature = pending
                signatures = dict(
                    self.preferences.get("auto_exp_rank_signatures") or {}
                )
                signatures[snapshot_key] = signature
                signatures = dict(list(signatures.items())[-50:])
                self.preferences = save_preferences(
                    {"auto_exp_rank_signatures": signatures},
                    self.preferences_path,
                )
                self.log.info(
                    "auto_exp_rank_upload_completed records=%s",
                    dict(result or {}).get("records", 0),
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
        self.memory_limits = memory_limits_for_budget(
            self.preferences.get("memory_limit_mb")
        )
        self.snapshot_reader.character_history_limit = self.memory_limits[
            "character_history"
        ]
        set_detailed(self.log, True)
        live_map = dict(self.snapshot.get("map") or {})
        self.snapshot = dict(payload.get("snapshot") or {})
        if live_map.get("clients") and not dict(self.snapshot.get("map") or {}).get("clients"):
            self.snapshot["map"] = live_map
        self._apply_manual_map_fallbacks()
        self._apply_inventory_category_overrides()
        if hasattr(self, "pvp_sync_interval"):
            self.pvp_sync_interval.blockSignals(True)
            self.pvp_sync_interval.setValue(
                self._bounded(
                    self.preferences.get("pvp_sync_interval_minutes"), 1, 60, 5
                )
            )
            self.pvp_sync_interval.blockSignals(False)
        if self.observation_sync_next_due <= 0:
            self.observation_sync_next_due = (
                time.monotonic() + self._pvp_sync_interval_seconds()
            )
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
            self._sync_local_api()
        self._render_overview()
        self._render_combat()
        self._render_subsessions()
        self._render_sends()
        self._render_inventory()
        self._render_exp_rank()
        self._render_map()
        self._render_drops()
        self._render_loot_announcements()
        self._render_program_status()
        self._render_general_summary()
        self._render_integration_health()
        if self.page_stack.currentIndex() == BANKS_PAGE_INDEX:
            self._render_selected_bank()
        self._evaluate_drop_alerts(
            str(self.snapshot.get("session_id") or ""),
            list(self.snapshot.get("drop_events") or []),
        )
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
        self.overview_status.show()
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
        active_modes = self._combat_decode_modes()
        active_locations: dict[str, object] = {}
        for client in (self.snapshot.get("map") or {}).get("clients") or []:
            if not client.get("map_enabled") or client.get("stale"):
                continue
            client_key = str(client.get("client_key") or "")
            map_index = client.get("map_index")
            map_name = str(client.get("map_name") or "").strip()
            if not map_name and isinstance(map_index, int):
                map_name = f"Mapa #{map_index}"
            if client_key and (map_name or isinstance(map_index, int)):
                region_name = str(client.get("region_name") or "").strip()
                active_locations[client_key] = {
                    "map_index": map_index,
                    "map_name": map_name,
                    "label": map_name,
                    "region_name": region_name,
                    "spot_name": region_name,
                }
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
            if client_key and location and client_key not in active_locations:
                active_locations[client_key] = location
        session_id = str(self.snapshot.get("session_id") or "")
        exp_rank_records = list(
            (self.snapshot.get("exp_rank") or {}).get("records") or []
        )
        active_auto_clients = {
            str(subsession.get("client_key") or "")
            for subsession in (self.snapshot.get("subsessions") or [])
            if subsession.get("ended_ns") is None
            and subsession.get("auto_context")
        }
        if self.subsession_context_session != session_id:
            self.subsession_context_stabilizer.clear()
            self.subsession_context_session = session_id
        farm_catalog = self.farm_catalog

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
                        active_modes,
                    )
                    if self.live_combat_events
                    else reader.load_combat(language, active_modes)
                )
                knowledge = KnowledgeStore(self.knowledge_path)
                try:
                    knowledge.observe_exp_rank_records(
                        exp_rank_records, session_id=session_id
                    )
                    knowledge.enrich_combat_monitors(
                        payload.get("combat_monitors") or []
                    )
                    for monitor in payload.get("combat_monitors") or []:
                        knowledge.observe_combat(
                            [monitor],
                            location=active_locations.get(
                                str(monitor.get("client_key") or ""), ""
                            ),
                            session_id=session_id or "",
                        )
                finally:
                    knowledge.close()
                if session_id:
                    store = CaptureStore(self.database_path)
                    context_changed = False
                    try:
                        for monitor in payload.get("combat_monitors") or []:
                            client_key = str(monitor.get("client_key") or "")
                            if client_key not in active_auto_clients:
                                self.subsession_context_stabilizer.discard(client_key)
                                continue
                            context = infer_subsession_context(
                                monitor,
                                active_locations.get(client_key, ""),
                                farm_catalog,
                            )
                            context = self.subsession_context_stabilizer.observe(
                                client_key, context, now_ns=time.time_ns()
                            )
                            if context is None:
                                continue
                            context_changed = store.update_auto_subsession_context(
                                session_id, client_key, **context
                            ) or context_changed
                    finally:
                        store.close()
                    payload["subsession_context_changed"] = context_changed
                self.combat_loaded.emit(payload)
            except Exception as error:
                self.log.exception("combat_load_failed")
                self.combat_failed.emit(f"{type(error).__name__}: {error}")

        threading.Thread(target=worker, daemon=True).start()

    def _flush_observation_upload(self) -> None:
        session = self.pending_observation_session
        if not self._site_allows("observations"):
            self.pending_observation_session = ""
            return
        if not session or not self.site_profile.connected:
            return
        if self.site_busy:
            QtCore.QTimer.singleShot(500, self._flush_observation_upload)
            return
        self.pending_observation_session = ""
        self._run_site_operation(
            "observations:send",
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
        if (
            not enabled
            or not session
            or not self.site_profile.connected
            or self.site_busy
            or time.monotonic() < self.auto_market_retry_after
        ):
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
        self.send_status_labels["market"].setText(
            "Enviando Mercado automaticamente…"
        )
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

    def _maybe_auto_exp_rank_upload(self) -> None:
        engine = self.capture_engine
        session = str(
            (engine and engine.current_session)
            or self.snapshot.get("session_id")
            or self.last_capture_session
            or ""
        )
        if (
            not self._site_allows("exp-ranking")
            or "exp-ranking" not in self.license_features
            or not session
            or not self.site_profile.connected
            or self.site_busy
            or time.monotonic() < self.auto_exp_rank_retry_after
        ):
            return
        store = CaptureStore(self.database_path, readonly=True)
        try:
            ranking = store.exp_rank_snapshot(session)
        finally:
            store.close()
        if ranking.get("completeness") != "complete":
            return
        signature = str(ranking.get("signature") or "")
        snapshot_key = str(ranking.get("snapshot_key") or "")
        sent = dict(self.preferences.get("auto_exp_rank_signatures") or {})
        if not signature or not snapshot_key or sent.get(snapshot_key) == signature:
            return
        self.pending_auto_exp_rank = (snapshot_key, signature)
        self._run_site_operation(
            "auto_exp_rank",
            lambda: self.site_uploader.send_exp_rank(session),
        )

    def _pvp_sync_interval_seconds(self) -> int:
        minutes = (
            self.pvp_sync_interval.value()
            if hasattr(self, "pvp_sync_interval")
            else self._bounded(
                self.preferences.get("pvp_sync_interval_minutes"), 1, 60, 5
            )
        )
        return int(minutes) * 60

    def _maybe_sync_observations(self, now: float, *, force: bool = False) -> None:
        session = str(
            self.snapshot.get("session_id") or self.last_capture_session or ""
        )
        if (
            not self._site_allows("observations")
            or not session
            or not self.site_profile.connected
        ):
            if force and hasattr(self, "pvp_database_status"):
                self.pvp_database_status.setText(
                    "Valide o token do Profile e carregue uma sessão antes de sincronizar."
                )
            return
        if not force and now < self.observation_sync_next_due:
            return
        if self.site_busy:
            return
        self.observation_sync_next_due = now + self._pvp_sync_interval_seconds()
        self.pending_observation_session = session
        self._flush_observation_upload()

    @QtCore.Slot(object)
    def _apply_combat_data(self, payload: dict[str, object]) -> None:
        routing = payload.get("routing_metrics")
        if isinstance(routing, dict):
            self.log.debug(
                "combat_routing total=%s associated=%s identity_associated=%s "
                "identity_flows=%s single_client_fallback=%s unmatched=%s",
                routing.get("total_events", 0),
                routing.get("associated_events", 0),
                routing.get("identity_associated_events", 0),
                routing.get("identity_bound_flows", 0),
                routing.get("single_client_fallback_events", 0),
                routing.get("unmatched_events", 0),
            )
        if payload.get("session_id") == self.snapshot.get("session_id"):
            self.snapshot["combat_monitors"] = list(
                payload.get("combat_monitors") or []
            )
            self._render_combat()
            self._render_overview_nearby_mobs()
            if (
                self.page_stack.currentIndex() == BANKS_PAGE_INDEX
                and self.banks_tabs.currentIndex() == 1
            ):
                self._render_pve_database()
            self._evaluate_alerts(self.snapshot["combat_monitors"])
            if payload.get("subsession_context_changed"):
                QtCore.QTimer.singleShot(0, self._load_readonly_data)
        self._finish_combat_load()

    def _combat_decode_modes(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                (
                    *self._licensed_status_modes(),
                    *(
                        mode
                        for mode, enabled in self.monitor_enabled.items()
                        if enabled
                    ),
                )
            )
        )

    def _licensed_status_modes(self) -> tuple[str, ...]:
        return tuple(
            mode
            for mode, feature in MONITOR_FEATURES.items()
            if feature in self.license_features
        )

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

    def _evaluate_live_drop_alerts(self) -> None:
        names = {
            _client_key(index): self._captured_client_name(index)
            for index in range(CLIENT_SLOT_COUNT)
        }
        events = route_live_drop_events(
            self.live_combat_events,
            self.live_combat_ports,
            names,
        )
        session_id = str(
            (self.capture_engine and self.capture_engine.current_session)
            or self.snapshot.get("session_id")
            or ""
        )
        self._evaluate_drop_alerts(session_id, events)
        self._merge_live_loot_announcements(session_id)

    def _merge_live_loot_announcements(self, session_id: str) -> None:
        if session_id != self.loot_announcement_session:
            self.loot_announcement_session = session_id
            if str(self.snapshot.get("session_id") or "") != session_id:
                self.snapshot["loot_announcements"] = []
        incoming = route_live_loot_announcements(
            self.live_combat_events, self.live_combat_ports
        )
        merged: dict[tuple[object, ...], dict[str, Any]] = {}
        for event in [
            *(self.snapshot.get("loot_announcements") or []), *incoming
        ]:
            announcements = tuple(
                (
                    row.get("player_name"), row.get("item_index"), row.get("count")
                )
                for row in (event.get("data") or {}).get("announcements") or []
                if isinstance(row, dict)
            )
            key = (
                event.get("ts_ns"), event.get("stream_offset"),
                event.get("bundle_seq"), event.get("client_key"), announcements,
            )
            merged[key] = dict(event)
        limit = min(1000, int(self.memory_limits["seen_drop_events"]))
        self.snapshot["loot_announcements"] = sorted(
            merged.values(), key=lambda event: int(event.get("ts_ns") or 0)
        )[-limit:]
        if self.page_stack.currentIndex() == LOOT_ANNOUNCEMENTS_PAGE_INDEX:
            self._render_loot_announcements()

    def _evaluate_drop_alerts(
        self, session_id: str, events: list[dict[str, Any]]
    ) -> None:
        language = str(self.preferences.get("item_name_language") or "pt")
        candidates = confirmed_item_drop_alerts(
            events, item_names_for_language(language)
        )
        baseline = session_id != self.drop_alert_session
        if baseline:
            self.drop_alert_session = session_id
            self.seen_drop_alerts.clear()
        pending = []
        for candidate in candidates:
            key = str(candidate["event_key"])
            is_new = key not in self.seen_drop_alerts
            self.seen_drop_alerts.pop(key, None)
            self.seen_drop_alerts[key] = None
            if is_new and not baseline:
                pending.append(candidate)
        while len(self.seen_drop_alerts) > self.memory_limits["seen_drop_events"]:
            self.seen_drop_alerts.pop(next(iter(self.seen_drop_alerts)))
        if baseline or not self.alert_item_drop.isChecked():
            return
        for candidate in pending:
            selected_rarities = {
                grade
                for grade, option in self.alert_drop_rarities.items()
                if option.isChecked()
            }
            selected_types = {
                category
                for category, option in self.alert_drop_types.items()
                if option.isChecked()
            }
            items = [
                item
                for item in candidate.get("items") or []
                if int(
                    ITEM_GRADES.get(str(item.get("item_index") or 0), 0) or 0
                ) in selected_rarities
                and drop_alert_category(item.get("item_index")) in selected_types
            ]
            if not items:
                continue
            shown = ", ".join(
                f"{item.get('name')} x{int(item.get('count') or 0)}"
                for item in items[:3]
            )
            if len(items) > 3:
                shown += f" e mais {len(items) - 3}"
            character = str(candidate.get("character_name") or "").strip()
            prefix = f"Drop de {character}" if character else "Drop de item"
            self._fire_alert(
                f"drop:{candidate['event_key']}", f"{prefix}: {shown}"
            )

    def _fire_alert(self, key: str, message: str) -> None:
        now = time.monotonic()
        cooldown = max(5, min(300, self.alert_cooldown_seconds.value()))
        if now - self.alert_last_fired.get(key, 0.0) < cooldown:
            self.alert_last_fired.move_to_end(key)
            return
        self.alert_last_fired.pop(key, None)
        self.alert_last_fired[key] = now
        while len(self.alert_last_fired) > self.memory_limits["alert_cooldowns"]:
            self.alert_last_fired.popitem(last=False)
        self.alert_status.setText(message)
        self.log.info("monitor_alert key=%s", key.split(":", 1)[0])
        if self.alert_sound.isChecked():
            play_alert_sound(
                self._resolved_alert_sound(), QtWidgets.QApplication.beep
            )
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
        previous_active = self.license_active
        active = bool(status.get("active"))
        self.license_active = active
        self.license_features = {
            str(feature) for feature in (status.get("features") or [])
        }
        self.connection_limits = {}
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
        labels = {
            "base": "Base",
            "monitor-pve": "Monitor PvE",
            "monitor-pvp": "Monitor PvP",
            "monitor-boss": "Monitor Boss",
            "map": "Mapa",
            "sessions-lan": "Sessões LAN",
            "exp-ranking": "Ranking de EXP",
        }
        enabled_labels = [labels[feature] for feature in labels if feature in self.license_features]
        details.append(
            "Módulos: " + (", ".join(enabled_labels) if enabled_labels else "nenhum")
        )
        details.append("Sem cota de clientes por licença; permanecem apenas limites técnicos.")
        details.append("Comprovante local protegido; nova tentativa online em cada abertura.")
        self.license_details.setText("\n".join(details))
        self._apply_module_access()
        self._refresh_connection_access(
            reset_tabs=previous_active != self.license_active
        )
        self._set_capture_controls()
        if self.controls_initialized:
            self._sync_local_api()

    def _client_allowed(self, index: int) -> bool:
        return self.license_active and 0 <= index < CLIENT_SLOT_COUNT

    def _refresh_connection_access(self, *, reset_tabs: bool = False) -> None:
        for index in range(CLIENT_SLOT_COUNT):
            allowed = self._client_allowed(index)
            self.client_buttons[index].setEnabled(allowed)
            for controls in self.monitor_controls.values():
                tabs = controls.get("tabs")
                if tabs is not None:
                    tabs.setTabEnabled(index, allowed if self.license_active else True)
            for page in self.combat_page_layouts.values():
                cards = page.get("cards") or []
                if index < len(cards):
                    cards[index].setEnabled(allowed)
        if reset_tabs and self._client_allowed(self.active_client):
            for controls in self.monitor_controls.values():
                tabs = controls.get("tabs")
                if tabs is not None:
                    tabs.setCurrentIndex(self.active_client)
        self._set_send_controls()

    def _apply_module_access(self) -> None:
        allowed_modes = []
        for mode, tab_index in MONITOR_TAB_INDEX.items():
            allowed = MONITOR_FEATURES[mode] in self.license_features
            if allowed:
                allowed_modes.append(mode)
            self.monitor_tabs.setTabVisible(
                tab_index, allowed if mode == "boss" else True
            )
            self.monitor_tabs.setTabEnabled(tab_index, allowed)
            controls = self.monitor_controls[mode]
            for name in (
                "enabled", "interval", "focus", "overlay", "hostile_overlay",
                "non_hostile_overlay", "dps_overlay", "tabs",
            ):
                control = controls.get(name)
                if control is not None:
                    control.setEnabled(allowed)
            if not allowed:
                self._disable_monitor_mode(mode)
                for name in (
                    "overlay", "hostile_overlay", "non_hostile_overlay",
                    "dps_overlay",
                ):
                    overlay = controls.get(name)
                    if overlay is not None:
                        overlay.blockSignals(True)
                        overlay.setChecked(False)
                        overlay.blockSignals(False)
                if mode == "pvp" and self.pvp_overlays:
                    for kind in tuple(self.pvp_overlays):
                        self._toggle_pvp_overlay(False, kind)
                if mode == "boss":
                    if self.boss_overlay:
                        self._toggle_boss_overlay(False)
                    if self.boss_dps_overlay:
                        self._toggle_boss_dps_overlay(False)
        button = self.nav_buttons[MONITOR_PAGE_INDEX]
        button.setEnabled(bool(allowed_modes))
        button.setToolTip(
            "" if allowed_modes else "Nenhum módulo de monitor incluído nesta licença."
        )
        page_features = {
            EXP_RANK_PAGE_INDEX: ("exp-ranking", "Ranking de EXP"),
            MAP_PAGE_INDEX: ("map", "Mapa"),
        }
        for page_index, (feature, label) in page_features.items():
            page_button = self.nav_buttons[page_index]
            page_allowed = feature in self.license_features
            page_button.setEnabled(page_allowed)
            page_button.setToolTip(
                "" if page_allowed else f"{label} não incluído nesta licença."
            )
        if hasattr(self, "banks_tabs"):
            self.banks_tabs.setTabEnabled(
                0, "monitor-pvp" in self.license_features
            )
            self.banks_tabs.setTabEnabled(
                1, "monitor-pve" in self.license_features
            )
            if not self.banks_tabs.isTabEnabled(self.banks_tabs.currentIndex()):
                self.banks_tabs.setCurrentIndex(2)
        current_tab = self.monitor_tabs.currentIndex()
        if (
            current_tab < 0
            or not self.monitor_tabs.isTabEnabled(current_tab)
            or not self.monitor_tabs.isTabVisible(current_tab)
        ):
            for mode in allowed_modes:
                tab_index = MONITOR_TAB_INDEX[mode]
                if self.monitor_tabs.isTabVisible(tab_index):
                    self.monitor_tabs.setCurrentIndex(tab_index)
                    break
        current = self.page_stack.currentIndex()
        if current == MONITOR_PAGE_INDEX and not button.isEnabled():
            self.page_stack.setCurrentIndex(0)
            self.nav_buttons[0].setChecked(True)
        elif current in page_features and not self.nav_buttons[current].isEnabled():
            self.page_stack.setCurrentIndex(0)
            self.nav_buttons[0].setChecked(True)
        if (
            not any(self.monitor_enabled.values())
            and self.monitor_engine
            and self.monitor_engine.active
        ):
            try:
                self.monitor_engine.stop()
            except Exception:
                self.log.exception("monitor_stop_after_license_change_failed")

    def _require_monitor_feature(self, mode: str) -> bool:
        try:
            self.license_client.require(
                f"o módulo Monitor {mode.upper() if mode != 'boss' else 'Boss'}",
                MONITOR_FEATURES[mode],
            )
            return True
        except PermissionError as error:
            QtWidgets.QMessageBox.warning(self, "Módulo não licenciado", str(error))
            return False

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
                memory_budget_mb=self.memory_limits["budget_mb"],
                game_language=game_data_language(
                    self.preferences.get("item_name_language")
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
            self.monitor_engine = MonitorEngine(
                self.license_client,
                memory_budget_mb=self.memory_limits["budget_mb"],
                game_language=game_data_language(
                    self.preferences.get("item_name_language")
                ),
            )
        return self.monitor_engine

    def _monitor_interval_changed(self, mode: str) -> None:
        self.monitor_next_due[mode] = 0.0

    def _general_read_interval_seconds(self) -> int:
        configured = (
            self.setting_decode_interval.value()
            if hasattr(self, "setting_decode_interval")
            else self._bounded(
                self.preferences.get("decode_interval_seconds"), 15, 300, 30
            )
        )
        focused = any(
            self.monitor_enabled[mode]
            and self.monitor_controls[mode].get("focus") is not None
            and self.monitor_controls[mode]["focus"].isChecked()
            for mode in ("pvp", "boss")
        )
        return max(configured, FOCUS_READ_INTERVAL_SECONDS) if focused else configured

    def _monitor_focus_changed(self, mode: str) -> None:
        focus = {
            name: bool(
                controls.get("focus") and controls["focus"].isChecked()
            )
            for name, controls in self.monitor_controls.items()
            if name in {"pvp", "boss"}
        }
        self.preferences = save_preferences(
            {"monitor_focus": focus}, self.preferences_path
        )
        capture = self.capture_engine
        if capture and capture.active:
            self.next_read_at = time.monotonic() + self._general_read_interval_seconds()

    def _update_monitor_button(self, mode: str) -> None:
        controls = self.monitor_controls[mode]
        enabled = controls["enabled"].isChecked()
        action = "Desligar monitor" if enabled else "Ligar monitor"
        tabs = controls.get("tabs")
        client = f" {self._client_name(tabs.currentIndex())}" if tabs else ""
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
        if mode == "pvp":
            self.pvp_nearby_next_due = 0.0
        self._render_combat()

    def _disable_monitor_mode(self, mode: str) -> None:
        if mode in self.monitor_client_enabled:
            self.monitor_client_enabled[mode] = [False] * CLIENT_SLOT_COUNT
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
            features = tuple(
                MONITOR_FEATURES[mode]
                for mode, enabled in self.monitor_enabled.items()
                if enabled
            )
            self._run_capture_operation(
                "monitor:start", lambda: monitor.start(features)
            )

    def _toggle_monitor(self, mode: str, enabled: bool) -> None:
        if enabled and not self._require_monitor_feature(mode):
            self._disable_monitor_mode(mode)
            return
        controls = self.monitor_controls[mode]
        tabs = controls.get("tabs")
        if tabs is not None:
            if enabled and not self._client_allowed(tabs.currentIndex()):
                self._disable_monitor_mode(mode)
                return
            self.monitor_client_enabled[mode][tabs.currentIndex()] = enabled
            self.monitor_enabled[mode] = any(self.monitor_client_enabled[mode])
        else:
            self.monitor_enabled[mode] = enabled
        self._update_monitor_button(mode)
        self.monitor_next_due[mode] = 0.0
        if mode == "pvp":
            self.pvp_nearby_next_due = 0.0
        capture = self.capture_engine
        if capture and capture.active:
            self.next_read_at = time.monotonic() + self._general_read_interval_seconds()
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
        if not self._require_monitor_feature("boss"):
            overlay_button = self.monitor_controls["boss"].get("overlay")
            if overlay_button is not None:
                overlay_button.blockSignals(True)
                overlay_button.setChecked(False)
                overlay_button.blockSignals(False)
            return
        overlay = _MovableOverlay()
        overlay.setWindowTitle("RF QOL · Boss · Vida")
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
        layout.addWidget(self.boss_overlay_name)
        layout.addWidget(self.boss_overlay_hp)
        layout.addWidget(self.boss_overlay_progress)
        overlay.resize(340, 125)
        self._restore_overlay_position(overlay, "boss_overlay_position")
        self.boss_overlay = overlay
        overlay.show()
        self._update_boss_overlay(
            list(self.snapshot.get("combat_monitors") or [])
        )

    def _toggle_boss_dps_overlay(self, enabled: bool) -> None:
        if not enabled:
            if self.boss_dps_overlay:
                self.boss_dps_overlay.close()
                self.boss_dps_overlay = None
            return
        if not self._require_monitor_feature("boss"):
            overlay_button = self.monitor_controls["boss"].get("dps_overlay")
            if overlay_button is not None:
                overlay_button.blockSignals(True)
                overlay_button.setChecked(False)
                overlay_button.blockSignals(False)
            return
        overlay = _MovableOverlay()
        overlay.setWindowTitle("RF QOL · Boss · DPS")
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
        overlay.position_changed.connect(self._save_boss_dps_overlay_position)
        layout = QtWidgets.QVBoxLayout(overlay)
        layout.setContentsMargins(12, 10, 12, 10)
        self.boss_dps_overlay_name = _label("Aguardando boss próximo", "subtitle")
        self.boss_dps_overlay_rate = _label(
            "DPS — · Dano acumulado — · Tempo restante —", "data"
        )
        layout.addWidget(self.boss_dps_overlay_name)
        layout.addWidget(self.boss_dps_overlay_rate)
        overlay.resize(340, 95)
        fallback = (
            [self.boss_overlay.x() + 24, self.boss_overlay.y() + 24]
            if self.boss_overlay else None
        )
        self._restore_overlay_position(
            overlay, "boss_dps_overlay_position", fallback
        )
        self.boss_dps_overlay = overlay
        overlay.show()
        self._update_boss_overlay(
            list(self.snapshot.get("combat_monitors") or [])
        )

    def _toggle_pvp_overlay(self, enabled: bool, kind: str = "target") -> None:
        if kind not in {"target", "hostile", "non_hostile"}:
            return
        if not enabled:
            overlay = self.pvp_overlays.pop(kind, None)
            if overlay:
                overlay.close()
            return
        if not self._require_monitor_feature("pvp"):
            overlay_button = self.monitor_controls["pvp"].get("overlay")
            if overlay_button is not None:
                overlay_button.blockSignals(True)
                overlay_button.setChecked(False)
                overlay_button.blockSignals(False)
            return
        title, preference, fallback_offset = {
            "target": ("Alvo atual", "pvp_overlay_target_position", None),
            "hostile": ("Próximos hostis", "pvp_overlay_hostile_position", [24, 120]),
            "non_hostile": (
                "Próximos não hostis",
                "pvp_overlay_non_hostile_position",
                [24, 240],
            ),
        }[kind]
        overlay = _MovableOverlay()
        overlay.setWindowTitle(f"RF QOL · {title}")
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
        overlay.position_changed.connect(
            lambda position, setting=preference:
                self._save_overlay_position(setting, position)
        )
        layout = QtWidgets.QVBoxLayout(overlay)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        summary = _label(title, "subtitle")
        rows = QtWidgets.QVBoxLayout()
        rows.setSpacing(4)
        layout.addWidget(summary)
        if kind == "target":
            local_health = QtWidgets.QFrame(objectName="secondaryMetricGroup")
            local_layout = QtWidgets.QVBoxLayout(local_health)
            local_layout.setContentsMargins(8, 5, 8, 5)
            local_layout.setSpacing(3)
            local_heading = QtWidgets.QHBoxLayout()
            local_heading.addWidget(_label("Sua vida", "muted"), 1)
            local_value = _label("HP —", "data")
            local_heading.addWidget(local_value)
            local_progress = QtWidgets.QProgressBar()
            local_progress.setRange(0, 1000)
            local_progress.setValue(0)
            local_progress.setTextVisible(False)
            local_progress.setFixedHeight(8)
            local_layout.addLayout(local_heading)
            local_layout.addWidget(local_progress)
            layout.addWidget(local_health)
            overlay.local_health = local_health
            overlay.local_health_value = local_value
            overlay.local_health_progress = local_progress
        layout.addLayout(rows)
        overlay.summary = summary
        overlay.rows = rows
        overlay.setFixedWidth(300)
        overlay.resize(300, 72)
        fallback = None
        if fallback_offset and self.pvp_overlays.get("target"):
            target = self.pvp_overlays["target"]
            fallback = [
                target.x() + fallback_offset[0],
                target.y() + fallback_offset[1],
            ]
        self._restore_overlay_position(overlay, preference, fallback)
        self.pvp_overlays[kind] = overlay
        overlay.show()
        self._update_pvp_overlay(
            list(self.snapshot.get("combat_monitors") or [])
        )

    def _restore_overlay_position(
        self,
        overlay: QtWidgets.QDialog,
        preference_key: str,
        fallback: list[int] | None = None,
    ) -> None:
        position = self.preferences.get(preference_key, fallback)
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
    def _save_boss_overlay_position(self, position: QtCore.QPoint) -> None:
        self._save_overlay_position("boss_overlay_position", position)

    @QtCore.Slot(QtCore.QPoint)
    def _save_boss_dps_overlay_position(self, position: QtCore.QPoint) -> None:
        self._save_overlay_position("boss_dps_overlay_position", position)

    def _set_capture_controls(self) -> None:
        engine = self.capture_engine
        active = bool(engine and engine.active)
        paused = bool(engine and engine.paused)
        self.start_button.setToolTip("Começar captura nova · Ctrl+F8")
        self.start_button.setAccessibleName(self.start_button.toolTip())
        self.start_button.setEnabled(
            self.license_active and not self.capture_busy and not active
        )
        self.continue_button.setEnabled(
            self.license_active
            and not self.capture_busy
            and not active
            and paused
            and bool(engine and engine.current_session)
        )
        self.pause_button.setEnabled(active and not self.capture_busy)
        self.stop_button.setEnabled(
            bool(engine and engine.current_session) and not self.capture_busy
        )
        self.stop_without_reading_button.setEnabled(
            bool(engine and engine.current_session) and not self.capture_busy
        )
        if not self.license_active and not active:
            self.top_capture.setText("Licença necessária")
            self.top_capture.setProperty("role", "warning")
        elif paused:
            self.top_capture.setText("Captura pausada")
            self.top_capture.setProperty("role", "warning")
        elif active:
            self.top_capture.setText("Captura ativa")
            self.top_capture.setProperty("role", "ok")
        elif not self.capture_busy:
            self.top_capture.setText("Captura inativa")
            self.top_capture.setProperty("role", "muted")
        self.top_capture.style().unpolish(self.top_capture)
        self.top_capture.style().polish(self.top_capture)
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

    def _prepare_capture_start(self) -> CaptureEngine | None:
        if not self.license_active:
            self.top_capture.setText("Captura — licença necessária")
            return None
        if self.monitor_engine and self.monitor_engine.active:
            try:
                self.monitor_engine.stop()
            except Exception as error:
                self.log.exception("monitor_handover_stop_failed")
                self.top_capture.setText(f"Captura — monitor não encerrou: {error}")
                return None
        return self._ensure_capture_engine()

    def _start_new_capture(self) -> None:
        engine = self._prepare_capture_start()
        if engine is None:
            return
        self.top_capture.setText("Captura — iniciando nova sessão…")
        self._run_capture_operation("start_new", engine.start_new)

    def _continue_capture(self) -> None:
        engine = self._prepare_capture_start()
        if engine is None:
            return
        if not engine.paused or not engine.current_session:
            self.top_capture.setText("Captura — não há sessão anterior para continuar")
            return
        self.top_capture.setText("Captura — continuando sessão anterior…")
        self._run_capture_operation("continue", engine.start)

    def _start_capture(self) -> None:
        """Compatibilidade interna: o atalho de início sempre cria uma sessão nova."""
        self._start_new_capture()

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
            if name in {"start", "start_new", "continue"} and "Outra captura PktMon" in detail:
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
                    if self.license_active and "map" in self.license_features:
                        self.map_preview_next_due = (
                            now_mono + MAP_PREVIEW_SECONDS
                        )
                    if self._licensed_status_modes():
                        self.program_status_preview_next_due = (
                            now_mono + PROGRAM_STATUS_PREVIEW_SECONDS
                        )
                    for mode, enabled in self.monitor_enabled.items():
                        if enabled:
                            self.monitor_next_due[mode] = (
                                now_mono
                                + self.monitor_controls[mode]["interval"].value()
                            )
                    if self.alert_item_drop.isChecked():
                        self.drop_alert_next_due = (
                            now_mono + DROP_ALERT_REFRESH_SECONDS
                        )
                else:
                    self.next_read_at = (
                        time.monotonic() + self._general_read_interval_seconds()
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
        if isinstance(data.get("monitor_metrics"), dict):
            self.latest_monitor_metrics = dict(data["monitor_metrics"])
        if isinstance(data.get("map"), dict):
            self.snapshot["map"] = dict(data["map"])
            self._apply_manual_map_fallbacks()
            self._render_map()
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
                    f"Monitores — ativos · {data.get('pc_clients', 0)} PC · "
                    f"{data.get('emulators', 0)} emulador(es)"
                )
            else:
                self.live_combat_events = list(data.get("events") or [])
                self.live_combat_ports = tuple(
                    tuple(int(port) for port in group)
                    for group in data.get("client_ports") or []
                )
                metrics = dict(data.get("monitor_metrics") or {})
                discarded = int(metrics.get("dropped_packets") or 0) + int(
                    metrics.get("dropped_write_packets") or 0
                )
                self.top_last_read.setText(
                    f"Monitores: {len(self.live_combat_events)} evento(s) prioritários"
                    f" · fila {metrics.get('queue_depth', 0)}"
                    f" · atraso {float(metrics.get('lag_seconds') or 0):.1f} s"
                    + (f" · descartados {discarded}" if discarded else "")
                )
                self.top_last_read.setToolTip(
                    "Sobrecarga controlada: pacotes foram descartados para proteger a RAM."
                    if discarded else ""
                )
                self.log.debug("monitor_metrics %s", metrics)
                self._evaluate_live_drop_alerts()
                self._load_combat_data()
            for mode, enabled in self.monitor_enabled.items():
                if enabled and self.monitor_next_due[mode] <= now_mono:
                    self.monitor_next_due[mode] = (
                        now_mono + self.monitor_controls[mode]["interval"].value()
                    )
            if self.alert_item_drop.isChecked():
                self.drop_alert_next_due = (
                    now_mono + DROP_ALERT_REFRESH_SECONDS
                )
            self._set_capture_controls()
            return
        engine = self._ensure_capture_engine()
        if name in {"start", "start_new", "continue"}:
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
                "capture_pc_client_pids": data.get("capture_pc_client_pids"),
                "capture_emulator_client_pids": data.get(
                    "capture_emulator_client_pids"
                ),
            }, self.preferences_path)
            self.program_status_preview_next_due = 0.0
            self.map_preview_next_due = 0.0
            self.next_read_at = time.monotonic() + 3
            self.top_capture.setText(
                f"Captura — ativa · {data.get('pc_clients', 0)} PC · "
                f"{data.get('emulators', 0)} emulador(es)"
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
            self.next_read_at = time.monotonic() + self._general_read_interval_seconds()
            self._load_readonly_data()
            QtCore.QTimer.singleShot(0, self._maybe_auto_market_upload)
            QtCore.QTimer.singleShot(0, self._maybe_auto_exp_rank_upload)
        elif name == "preview":
            now = datetime.now().strftime("%H:%M:%S")
            now_mono = time.monotonic()
            if self._licensed_status_modes():
                self.program_status_preview_next_due = (
                    now_mono + PROGRAM_STATUS_PREVIEW_SECONDS
                )
            if self.license_active and "map" in self.license_features:
                self.map_preview_next_due = now_mono + MAP_PREVIEW_SECONDS
            metrics = dict(data.get("monitor_metrics") or {})
            discarded = int(metrics.get("dropped_packets") or 0) + int(
                metrics.get("dropped_write_packets") or 0
            )
            for mode, enabled in self.monitor_enabled.items():
                if enabled and self.monitor_next_due[mode] <= now_mono:
                    self.monitor_next_due[mode] = (
                        now_mono + self.monitor_controls[mode]["interval"].value()
                    )
            if self.alert_item_drop.isChecked():
                self.drop_alert_next_due = (
                    now_mono + DROP_ALERT_REFRESH_SECONDS
                )
            self.top_last_read.setText(
                f"Última leitura rápida: {now} · {data.get('added', 0)} evento(s)"
                f" · fila {metrics.get('queue_depth', 0)}"
                f" · atraso {float(metrics.get('lag_seconds') or 0):.1f} s"
                + (f" · descartados {discarded}" if discarded else "")
                if data.get("available")
                else "Última leitura rápida: indisponível neste modo de captura"
            )
            self.top_last_read.setToolTip(
                "Sobrecarga controlada: pacotes foram descartados para proteger a RAM."
                if discarded else self.live_preview_error
            )
            self.live_combat_events = list(data.get("events") or [])
            self.live_combat_ports = tuple(
                tuple(int(port) for port in group)
                for group in data.get("client_ports") or []
            )
            self.log.debug("monitor_metrics %s", metrics)
            self._evaluate_live_drop_alerts()
            if (
                any(self.monitor_enabled.values())
                or bool(self._licensed_status_modes())
            ):
                self._load_combat_data()
        elif name == "pause":
            self.top_capture.setText("Captura — pausada")
            self._load_readonly_data()
            QtCore.QTimer.singleShot(0, self._maybe_auto_exp_rank_upload)
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
            QtCore.QTimer.singleShot(0, self._maybe_auto_exp_rank_upload)
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
        now = time.monotonic()
        self._sample_process_memory(now)
        if now >= self.program_status_next_refresh:
            self.program_status_next_refresh = now + 1.0
            self._render_program_status()
        engine = self.capture_engine
        monitor = self.monitor_engine
        self._maybe_sync_observations(now)
        if (
            self.monitor_enabled.get("pvp")
            and now >= self.pvp_nearby_next_due
        ):
            self._render_combat()
        if not engine and not monitor:
            return
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
            drop_alert_active = self.alert_item_drop.isChecked()
            monitor_active = any(self.monitor_enabled.values())
            status_preview_active = bool(
                self._licensed_status_modes()
            ) and not (monitor_active or drop_alert_active)
            map_preview_active = (
                self.license_active and "map" in self.license_features
            )
            realtime_active = (
                monitor_active
                or drop_alert_active
                or status_preview_active
                or map_preview_active
            )
            due_times = [
                self.monitor_next_due[mode]
                for mode, enabled in self.monitor_enabled.items()
                if enabled
            ]
            if drop_alert_active:
                due_times.append(self.drop_alert_next_due)
            if status_preview_active:
                due_times.append(self.program_status_preview_next_due)
            if map_preview_active:
                due_times.append(self.map_preview_next_due)
            next_due = min(due_times, default=0.0)
            monitor_remaining = max(0, math.ceil(next_due - now))
            realtime_label = (
                "monitor" if monitor_active
                else "alerta" if drop_alert_active
                else "status" if status_preview_active
                else "mapa"
            )
            self.top_next_read.setText(
                f"Próx. leitura: {remaining} s"
                + (
                    f" · {realtime_label}: {monitor_remaining} s"
                    if realtime_active else ""
                )
            )
            if not self.capture_busy and now >= self.next_read_at:
                self.top_last_read.setText("Última leitura: atualizando…")
                self._run_capture_operation("read", engine.read_live)
            elif (
                realtime_active
                and not self.capture_busy
                and (not self.combat_load_running or map_preview_active)
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
            if (
                not self.capture_busy
                and not self.combat_load_running
                and now >= next_due
            ):
                features = tuple(
                    MONITOR_FEATURES[mode]
                    for mode, enabled in self.monitor_enabled.items()
                    if enabled
                )
                self._run_capture_operation(
                    "monitor:preview", lambda: monitor.snapshot(features)
                )
        elif engine and engine.paused:
            self.top_next_read.setText("Próx. leitura: pausada")
        elif engine and engine.current_session and not self.capture_busy:
            self.top_capture.setText("Captura — interrompida; encerre para analisar")

    def _sample_process_memory(self, now: float) -> None:
        if now < self.memory_next_sample:
            return
        self.memory_next_sample = now + MEMORY_SAMPLE_SECONDS
        memory = _process_memory_bytes()
        self.top_memory.setText(
            f"RAM  {self._format_bytes(memory)} / "
            f"{self.memory_limits['budget_mb']} MiB"
            if memory is not None else "RAM —"
        )
        if self.page_stack.currentIndex() in {0, SETTINGS_PAGE_INDEX}:
            self._render_integration_health()
        budget_bytes = self.memory_limits["pressure_bytes"]
        if memory is None or memory < budget_bytes:
            self.top_memory.setToolTip(
                f"Orçamento escolhido: {self.memory_limits['budget_mb']} MiB."
            )
            return
        self.top_memory.setToolTip(
            "Uso de memória acima do limite de atenção; caches dispensáveis foram reduzidos."
        )
        if now - self.memory_pressure_last_at < MEMORY_PRESSURE_COOLDOWN_SECONDS:
            return
        self.memory_pressure_last_at = now
        pressure_icon_limit = max(
            16, self.memory_limits["inventory_icons"] // 4
        )
        while len(self.inventory_icon_cache) > pressure_icon_limit:
            self.inventory_icon_cache.popitem(last=False)
        if hasattr(self, "pvp_database_table") and not self._bank_is_visible(0):
            self.pvp_database_table.setRowCount(0)
            self.pvp_database_rows = {}
        compacted: dict[str, object] = {}
        for name, engine in (
            ("capture", self.capture_engine),
            ("monitor", self.monitor_engine),
        ):
            relieve = getattr(engine, "relieve_memory_pressure", None)
            if callable(relieve):
                try:
                    compacted[name] = relieve()
                except (RuntimeError, TypeError, ValueError):
                    self.log.exception("memory_pressure_compaction_failed engine=%s", name)
        collected = gc.collect()
        self.log.warning(
            "memory_pressure working_set_bytes=%s icon_cache=%s "
            "pvp_rows=%s collected=%s compacted=%s",
            memory,
            len(self.inventory_icon_cache),
            self.pvp_database_table.rowCount()
            if hasattr(self, "pvp_database_table") else 0,
            collected,
            compacted,
        )

    def _page_changed(self, index: int) -> None:
        self.log.debug("ui_page_changed index=%s", index)
        if hasattr(self, "page_title") and 0 <= index < len(PAGES):
            self.page_title.setText(PAGES[index][0])
        if index == MONITOR_PAGE_INDEX:
            tab_index = self.monitor_tabs.currentIndex()
            mode = next(
                (
                    mode for mode, candidate in MONITOR_TAB_INDEX.items()
                    if candidate == tab_index
                ),
                None,
            )
            if mode is not None:
                self.monitor_next_due[mode] = 0.0
                self._capture_tick()
        elif index == BANKS_PAGE_INDEX:
            self._render_selected_bank()
        elif index == DROPS_PAGE_INDEX:
            self._render_drops()
        elif index == LOOT_ANNOUNCEMENTS_PAGE_INDEX:
            self._render_loot_announcements()
        elif index == PAGE_INDEX_BY_TITLE["Resumo Geral"]:
            self._render_general_summary()
        elif index == SETTINGS_PAGE_INDEX:
            self._render_integration_health()

    def _monitoring_tab_changed(self, index: int) -> None:
        mode = next(
            (mode for mode, tab_index in MONITOR_TAB_INDEX.items() if tab_index == index),
            None,
        )
        if mode is None:
            return
        self.monitor_next_due[mode] = 0.0
        if self.controls_initialized:
            self._capture_tick()

    def _category_slots(self) -> range:
        return (
            range(PC_SLOT_COUNT)
            if self.active_category == "pc"
            else range(PC_SLOT_COUNT, CLIENT_SLOT_COUNT)
        )

    def _select_category(self, category: str) -> None:
        if category not in {"pc", "emulator"}:
            return
        self.active_category = category
        slots = self._category_slots()
        first = slots.start
        self.active_client = first
        for index in range(CLIENT_SLOT_COUNT):
            visible = index in slots
            self.client_buttons[index].setVisible(visible)
        self.client_buttons[first].setChecked(True)
        for (mode, index), button in self.send_buttons.items():
            if index >= 0:
                button.setVisible(index in slots)
        for mode, controls in self.monitor_controls.items():
            tabs = controls.get("tabs")
            if tabs is not None:
                for index in range(CLIENT_SLOT_COUNT):
                    tabs.setTabVisible(index, index in slots)
                tabs.setCurrentIndex(first)
            elif mode == "boss":
                for index, card in enumerate(
                    self.combat_page_layouts[mode]["cards"]
                ):
                    card.setVisible(index in slots)
        self._render_overview()
        self._render_combat()
        self._render_inventory()
        self._sync_combat_layout()
        self._refresh_connection_access()

    @staticmethod
    def _format_bytes(value: int) -> str:
        amount = float(max(0, value))
        for unit in ("B", "KiB", "MiB", "GiB"):
            if amount < 1024 or unit == "GiB":
                return f"{amount:.1f} {unit}".replace(".", ",")
            amount /= 1024
        return "0 B"

    def _select_client(self, index: int) -> None:
        if index not in self.visible_client_slots or not self._client_allowed(index):
            return
        self.active_client = index
        if hasattr(self, "client_source"):
            self.client_source.setText(self._client_source_label(index))
        if hasattr(self, "remove_client_button"):
            self.remove_client_button.setEnabled(index != 0)
        self.log.debug("ui_client_selected index=%s", index)
        self._render_overview()
        self._render_inventory()
        self._render_map()
        self._render_program_status()
        if (
            self.page_stack.currentIndex() == BANKS_PAGE_INDEX
            and self.banks_tabs.currentIndex() == 2
        ):
            self._render_auction_database()

    def _render_combat(self) -> None:
        monitors = list(self.snapshot.get("combat_monitors") or [])
        routed = any(item.get("client_key") for item in monitors)
        now = time.monotonic()
        refresh_pvp_nearby = now >= self.pvp_nearby_next_due
        if refresh_pvp_nearby:
            self.pvp_nearby_next_due = now + PVP_NEARBY_REFRESH_SECONDS
        for mode, groups in self.combat_widgets.items():
            for index, widgets in enumerate(groups):
                key = _client_key(index)
                monitor = next(
                    (item for item in monitors if item.get("client_key") == key),
                    None,
                )
                if monitor is None and not routed and index < len(monitors):
                    monitor = monitors[index]
                character = str((monitor or {}).get("character_name") or "").strip()
                widgets["heading"].setText(
                    self._client_title(index, character or "aguardando personagem")
                )
                if mode == "pve":
                    local = dict((monitor or {}).get("local") or {})
                    local_current = local.get("current_hp")
                    local_maximum = local.get("max_hp")
                    local_percent = local.get("hp_percent")
                    widgets["self_progress"].setValue(
                        max(0, min(1000, round(float(local_percent) * 10)))
                        if isinstance(local_percent, (int, float)) else 0
                    )
                    widgets["self_health"].setText(
                        (
                            "Sua vida: "
                            f"{self._format_count(local_current)} / "
                            f"{self._format_count(local_maximum)} · "
                            f"{float(local_percent):.2f}%".replace(".", ",")
                        )
                        if isinstance(local_current, (int, float))
                        and isinstance(local_maximum, (int, float))
                        and isinstance(local_percent, (int, float))
                        else "Sua vida: —"
                    )
                if (
                    mode in self.monitor_client_enabled
                    and not self.monitor_client_enabled[mode][index]
                ):
                    self._render_nearby(widgets, [], mode, {})
                    widgets["target"].setText("Último alvo confirmado: —")
                    widgets["status"].setText(
                        f"Monitor desligado para {self._client_name(index)}."
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
                        index in self._category_slots() and bool(bosses)
                    )
                    widgets["status"].setText(
                        "Bosses próximos confirmados pelo stream em memória."
                        if bosses
                        else "Nenhum boss confirmado próximo."
                    )
                    continue
                nearby_key = "nearby_monsters" if mode == "pve" else "nearby_players"
                if mode != "pvp" or refresh_pvp_nearby:
                    nearby = list((monitor or {}).get(nearby_key) or [])
                    if mode == "pvp":
                        nearby = self._recent_pvp_players(nearby)
                    self._render_nearby(
                        widgets,
                        nearby,
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
        self._render_program_status()
        self._update_boss_overlay(monitors)
        self._update_pvp_overlay(monitors, refresh_pvp_nearby)

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
        empty.setText("Nenhum registro recente.")
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

    @staticmethod
    def _recent_pvp_players(
        players: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        cutoff = time.time_ns() - NEARBY_PLAYER_STALE_SECONDS * 1_000_000_000
        recent = []
        for player in players:
            if player.get("stale"):
                continue
            last_seen = int(player.get("last_seen_ns") or 0)
            if last_seen >= 1_500_000_000_000_000_000:
                if last_seen < cutoff:
                    continue
            elif float(player.get("age_seconds") or 0) > NEARBY_PLAYER_STALE_SECONDS:
                continue
            recent.append(player)
        return recent

    def _update_pvp_overlay(
        self,
        monitors: list[dict[str, Any]],
        update_nearby: bool = True,
    ) -> None:
        if not self.pvp_overlays:
            return
        tabs = self.monitor_controls.get("pvp", {}).get("tabs")
        selected_index = tabs.currentIndex() if tabs is not None else self.active_client
        monitor = next(
            (
                item
                for fallback, item in enumerate(monitors)
                if self._monitor_client_index(item, fallback) == selected_index
            ),
            {},
        )
        origin = (
            self._monitor_client_title(monitor)
            if monitor
            else self._client_name(selected_index)
        )
        monitor_enabled = bool(
            0 <= selected_index < len(self.monitor_client_enabled.get("pvp", []))
            and self.monitor_client_enabled["pvp"][selected_index]
        )
        target = dict(monitor.get("pvp") or {}) if monitor_enabled else {}
        local = dict(monitor.get("local") or {}) if monitor_enabled else {}
        target_valid = not (
            not target
            or target.get("stale")
            or float(target.get("age_seconds") or 0) > 3
        )
        target_uid = str(target.get("character_uid") or "") if target_valid else ""
        nearby = [
            item
            for item in self._recent_pvp_players(
                list(monitor.get("nearby_players") or [])
                if monitor_enabled
                else []
            )
            if str(item.get("character_uid") or "") != target_uid
        ]
        groups = {
            "target": [target] if target_valid else [],
            "hostile": [
                item for item in nearby if item.get("pvp_status") == "enemy"
            ],
            "non_hostile": [
                item for item in nearby if item.get("pvp_status") != "enemy"
            ],
        }
        titles = {
            "target": "Alvo atual",
            "hostile": "Próximos hostis",
            "non_hostile": "Próximos não hostis",
        }
        status_labels = {"ally": "Aliado", "neutral": "Neutro"}
        for key, overlay in self.pvp_overlays.items():
            if key != "target" and monitor_enabled and not update_nearby:
                continue
            if overlay._drag_offset is not None:
                continue
            summary = overlay.summary
            rows = overlay.rows
            if key == "target" and hasattr(overlay, "local_health"):
                current = local.get("current_hp")
                maximum = local.get("max_hp")
                percent = local.get("hp_percent")
                overlay.local_health.setVisible(bool(local))
                overlay.local_health_value.setText(
                    f"{self._format_count(current)} / {self._format_count(maximum)}"
                    if isinstance(current, int) and isinstance(maximum, int)
                    else "HP —"
                )
                overlay.local_health_progress.setValue(
                    max(0, min(1000, round(float(percent) * 10)))
                    if isinstance(percent, (int, float)) else 0
                )
            while rows.count():
                item = rows.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            values = groups[key]
            summary.setText(
                f"{titles[key]} · {origin}"
                + (
                    " · Monitor desligado"
                    if not monitor_enabled
                    else "" if values else " · Nenhum"
                )
            )
            for player in values[:10]:
                row = QtWidgets.QFrame(objectName="secondaryMetricGroup")
                layout = QtWidgets.QHBoxLayout(row)
                layout.setContentsMargins(8, 4, 8, 4)
                name = str(player.get("name") or "Jogador confirmado")
                suffix = (
                    f" · {status_labels.get(str(player.get('pvp_status')), 'Neutro')}"
                    if key == "non_hostile" else ""
                )
                layout.addWidget(_label(f"{name}{suffix}", "subtitle"), 1)
                percent = player.get("hp_percent")
                layout.addWidget(_label(
                    f"{float(percent):.1f}%".replace(".", ",")
                    if isinstance(percent, (int, float)) else "HP —",
                    "data",
                ))
                rows.addWidget(row)
            overlay.adjustSize()

    def _update_boss_overlay(self, monitors: list[dict[str, Any]]) -> None:
        if not self.boss_overlay and not self.boss_dps_overlay:
            return
        candidates = [
            (monitor, item, fallback_index)
            for fallback_index, monitor in enumerate(monitors)
            for item in list(monitor.get("bosses") or [])
        ]
        candidates.sort(
            key=lambda entry: (
                self._monitor_client_index(entry[0], entry[2]) != self.active_client,
                -int(entry[1].get("last_seen_ns") or 0),
            )
        )
        monitor, boss, fallback_index = candidates[0] if candidates else ({}, None, 0)
        if not boss:
            if self.boss_overlay:
                self.boss_overlay_name.setText("Aguardando boss próximo")
                self.boss_overlay_hp.setText("HP —")
                self.boss_overlay_progress.setValue(0)
            if self.boss_dps_overlay:
                self.boss_dps_overlay_name.setText("Aguardando boss próximo")
                self.boss_dps_overlay_rate.setText(
                    "DPS — · Dano acumulado — · Tempo restante —"
                )
            return
        current, maximum, percent = (
            boss.get("current_hp"),
            boss.get("max_hp"),
            boss.get("hp_percent"),
        )
        boss_name = str(boss.get("name") or "Boss confirmado")
        boss_title = (
            f"{boss_name} · {self._monitor_client_title(monitor)}"
        )
        if self.boss_overlay:
            self.boss_overlay_name.setText(boss_title)
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
        if self.boss_dps_overlay:
            self.boss_dps_overlay_name.setText(boss_title)
            self.boss_dps_overlay_rate.setText(
                f"DPS {self._format_count(boss.get('dps_hp'))} "
                f"· Dano acumulado {self._format_count(boss.get('total_damage'))} "
                f"· Tempo restante {eta_text}"
            )

    @staticmethod
    def _monitor_client_index(monitor: dict[str, Any], fallback: int = 0) -> int:
        key = str(monitor.get("client_key") or "")
        if len(key) == 8 and key.startswith("client:"):
            index = ord(key[-1].lower()) - ord("a")
            if 0 <= index < CLIENT_SLOT_COUNT:
                return index
        return max(0, min(CLIENT_SLOT_COUNT - 1, fallback))

    @staticmethod
    def _monitor_client_title(monitor: dict[str, Any]) -> str:
        return str(monitor.get("character_name") or "").strip() or "Personagem não vinculado"

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
            players_by_guild: dict[str, list[dict[str, Any]]] = {}
            for item in list(boss.get("top_damage_players") or [])[:10]:
                guild = str(item.get("guild_name") or "").strip() or "Sem guilda"
                players_by_guild.setdefault(guild, []).append(item)
            if players_by_guild:
                guild_totals = {
                    str(item.get("name") or "").strip(): item
                    for item in list(boss.get("top_damage_guilds") or [])
                }
                for guild, players in players_by_guild.items():
                    guild_totals.setdefault(
                        guild,
                        {
                            "dps_hp": sum(
                                float(item.get("dps_hp") or 0) for item in players
                            ),
                            "damage": sum(
                                int(item.get("damage") or 0) for item in players
                            ),
                        },
                    )
                column.addWidget(
                    _label("Dano por guilda acumulado · encontro", "subtitle")
                )
                guild_columns = QtWidgets.QHBoxLayout()
                guild_columns.setSpacing(10)
                ordered_guilds = sorted(
                    players_by_guild,
                    key=lambda name: (
                        -int((guild_totals.get(name) or {}).get("damage") or 0),
                        -float((guild_totals.get(name) or {}).get("dps_hp") or 0),
                    ),
                )
                for guild in ordered_guilds:
                    guild_card = QtWidgets.QFrame(objectName="secondaryMetricGroup")
                    guild_card.setMinimumWidth(200)
                    guild_column = QtWidgets.QVBoxLayout(guild_card)
                    guild_column.setContentsMargins(10, 8, 10, 8)
                    guild_column.setSpacing(5)
                    guild_column.addWidget(_label(guild, "subtitle"))
                    total = guild_totals.get(guild) or {}
                    guild_column.addWidget(
                        _label(
                            f"{self._format_count(total.get('dps_hp'))}/s "
                            f"· dano {self._format_count(total.get('damage'))}",
                            "data",
                        )
                    )
                    for position, item in enumerate(players_by_guild[guild], 1):
                        ranking_row = QtWidgets.QHBoxLayout()
                        ranking_row.addWidget(
                            _label(
                                f"{position}. {item.get('name') or 'Não identificado'}",
                                "muted",
                            ),
                            1,
                        )
                        ranking_row.addWidget(
                            _label(
                                f"{self._format_count(item.get('dps_hp'))}/s "
                                f"· dano {self._format_count(item.get('damage'))}",
                                "data",
                            )
                        )
                        guild_column.addLayout(ranking_row)
                    guild_column.addStretch(1)
                    guild_columns.addWidget(guild_card, 1)
                column.addLayout(guild_columns)
            groups = list(boss.get("top_damage_groups") or [])
            if groups:
                column.addWidget(
                    _label("Dano acumulado por grupo · encontro", "subtitle")
                )
                for position, item in enumerate(groups[:10], 1):
                    ranking_row = QtWidgets.QHBoxLayout()
                    ranking_row.addWidget(
                        _label(
                            f"{position}. {item.get('name') or 'Não identificado'}",
                            "muted",
                        ),
                        1,
                    )
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

    @staticmethod
    def _format_percent(value: object) -> str:
        return (
            f"{float(value):.4f}%".replace(".", ",")
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else "—"
        )

    @classmethod
    def _format_signed_count(cls, value: object) -> str:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return "—"
        prefix = "+" if float(value) > 0 else ""
        return prefix + cls._format_count(value)

    @staticmethod
    def _format_signed_percent(value: object) -> str:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return "—"
        prefix = "+" if float(value) > 0 else ""
        return (prefix + f"{float(value):.4f}%").replace(".", ",")

    def _render_overview_nearby_mobs(self) -> None:
        if not hasattr(self, "overview_mobs_table"):
            return
        monitors = [
            item for item in self.snapshot.get("combat_monitors") or []
            if isinstance(item, dict)
        ]
        client_key = _client_key(self.active_client)
        routed = any(item.get("client_key") for item in monitors)
        monitor = next(
            (item for item in monitors if item.get("client_key") == client_key),
            None,
        )
        if monitor is None and not routed and self.active_client < len(monitors):
            monitor = monitors[self.active_client]

        grouped: dict[str, dict[str, object]] = {}
        for item in (monitor or {}).get("nearby_monsters") or []:
            if not isinstance(item, dict) or item.get("dead") or item.get("stale"):
                continue
            npc_index = item.get("npc_index")
            name = str(item.get("name") or "").strip()
            if not name:
                name = (
                    f"Monstro #{npc_index}"
                    if isinstance(npc_index, (int, float))
                    else "Monstro não identificado"
                )
            identity = name.casefold()
            row = grouped.setdefault(
                identity,
                {"name": name, "levels": set(), "max_hp": set(), "npc": set()},
            )
            if isinstance(npc_index, (int, float)) and not isinstance(npc_index, bool):
                row["npc"].add(int(npc_index))
            level = item.get("level")
            if isinstance(level, (int, float)) and not isinstance(level, bool) and level > 0:
                row["levels"].add(int(level))
            maximum = item.get("max_hp")
            if (
                isinstance(maximum, (int, float))
                and not isinstance(maximum, bool)
                and maximum > 0
            ):
                row["max_hp"].add(int(maximum))

        rows = sorted(grouped.values(), key=lambda item: str(item["name"]).casefold())
        self.overview_mobs_table.setRowCount(len(rows))

        def range_text(values: set[int]) -> str:
            if not values:
                return "—"
            ordered = sorted(values)
            if len(ordered) == 1:
                return self._format_count(ordered[0])
            return f"{self._format_count(ordered[0])}–{self._format_count(ordered[-1])}"

        numeric_alignment = (
            QtCore.Qt.AlignmentFlag.AlignRight
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        for row_index, row in enumerate(rows):
            values = (
                str(row["name"]),
                range_text(row["levels"]),
                range_text(row["max_hp"]),
            )
            for column, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(value)
                cell.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
                if column:
                    cell.setTextAlignment(numeric_alignment)
                self.overview_mobs_table.setItem(row_index, column, cell)
            npc_indexes = sorted(row["npc"])
            if npc_indexes:
                self.overview_mobs_table.item(row_index, 0).setToolTip(
                    "NPC " + ", ".join(str(value) for value in npc_indexes)
                )

        has_rows = bool(rows)
        self.overview_mobs_table.setVisible(has_rows)
        client = self._client_name(self.active_client)
        if has_rows:
            self.overview_mobs_status.setText(
                f"{len(rows)} tipo(s) confirmado(s) · {client}"
            )
        elif (
            self.active_client < len(self.monitor_client_enabled.get("pve", []))
            and not self.monitor_client_enabled["pve"][self.active_client]
        ):
            self.overview_mobs_status.setText(
                f"Monitor PvE desligado para {client}."
            )
        else:
            self.overview_mobs_status.setText(
                f"Nenhum mob próximo confirmado para {client}."
            )

    def _render_overview(self) -> None:
        snapshot = self.snapshot
        self._refresh_client_labels()
        self._refresh_client_uid_tooltips()

        key = _client_key(self.active_client)
        character, summary, historical_identity = self._overview_character(
            self.active_client
        )
        captured_name = str(character.get("name") or "").strip() if character else ""
        name = captured_name or "Aguardando personagem"
        stats = dict(snapshot.get("stats") or {})
        started = summary.get("recognized_at_ns") or stats.get("started_ns")
        ended = stats.get("ended_ns")
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
        epic_categories = dict(summary.get("epic_by_category") or {})

        checkpoints = list(snapshot.get("session_checkpoints") or [])
        checkpoint_labels = {
            "interval": "salvamento periódico",
            "paused": "pausa salva",
            "finalized": "sessão finalizada",
        }
        checkpoint_text = ""
        if checkpoints:
            latest_checkpoint = dict(checkpoints[0])
            checkpoint_text = (
                " · "
                + checkpoint_labels.get(
                    str(latest_checkpoint.get("reason") or ""),
                    "sessão salva",
                )
            )
        self.overview_status.setText(
            f"Sessão {snapshot.get('session_id')} · {duration // 60} min · "
            f"{stats.get('recognized', 0)} eventos reconhecidos{checkpoint_text}"
            if snapshot.get("session_id") else "Nenhuma sessão disponível."
        )
        self.overview_status.setVisible(False)
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
        self.session_duration.setText(
            f"{duration // 3600:02d}:{(duration % 3600) // 60:02d}:{duration % 60:02d}"
        )
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
        epic_labels = (
            ("weapon", "Arma"),
            ("armor", "Armadura"),
            ("accessory", "Acessório"),
            ("expansion", "Expansão"),
            ("blueprint_mau", "Blueprint de MAU"),
            ("blueprint_launcher", "Blueprint de Launcher"),
        )
        breakdown = [
            f"{label} {self._format_count(epic_categories.get(key) or 0)}"
            for key, label in epic_labels
            if int(epic_categories.get(key) or 0) > 0
        ]
        self.session_epic_breakdown.setText(
            "Épicos  " + (" · ".join(breakdown) if breakdown else "—")
        )

        subsessions = list(snapshot.get("subsessions") or [])
        active = next((item for item in subsessions if item.get("ended_ns") is None and item.get("client_key") == key), None)
        if active:
            summary_active = dict(
                (snapshot.get("subsession_summaries") or {}).get(active.get("id"))
                or {}
            )
            started_ns = active.get("started_ns")
            active_duration = (
                max(0, int((time.time_ns() - int(started_ns)) / 1_000_000_000))
                if isinstance(started_ns, int) else 0
            )
            display_values = self._subsession_display_values(
                active, summary_active, active_duration
            )
            for field, label in self.subsession_card_values.items():
                label.setText(display_values.get(field, "—"))
            self.subsession_empty.hide()
            self._overview_has_subsession = True
        else:
            for label in self.subsession_card_values.values():
                label.setText("—")
            self.subsession_empty.show()
            self._overview_has_subsession = False
        self._apply_subsession_card_fields(
            self._selected_subsession_card_fields()
        )
        self.subsession_badge.setText(
            "Ativa" if self._overview_has_subsession else "Inativa"
        )
        self.subsession_badge.setProperty(
            "role", "activeBadge" if self._overview_has_subsession else "muted"
        )
        self.subsession_badge.style().unpolish(self.subsession_badge)
        self.subsession_badge.style().polish(self.subsession_badge)
        self.view_subsession_button.setText(
            "Ver subsessão  →"
            if self._overview_has_subsession
            else "Abrir subsessões  →"
        )
        self._sync_overview_layout()

    def _render_secondary_overview(self, index: int, duration: int) -> None:
        return

    def _drop_history_rows(self) -> list[dict[str, object]]:
        language = str(self.preferences.get("item_name_language") or "pt")
        candidates = confirmed_item_drop_alerts(
            list(self.snapshot.get("drop_events") or []),
            item_names_for_language(language),
        )
        rows: list[dict[str, object]] = []
        for candidate in aggregate_item_drops_by_client(candidates):
            first_observed_at_ns = int(
                candidate.get("first_observed_at_ns") or 0
            )
            observed_at_ns = int(candidate.get("last_observed_at_ns") or 0)
            client_key = str(candidate.get("client_key") or "")
            client_index = (
                ord(client_key[-1]) - ord("a")
                if client_key.startswith("client:") and client_key[-1:].isalpha()
                else -1
            )
            client_name = (
                self._client_name(client_index)
                if 0 <= client_index < CLIENT_SLOT_COUNT
                else "Cliente não identificado"
            )
            character_name = str(
                candidate.get("character_name") or "Não identificado"
            )
            item_index = int(candidate.get("item_index") or 0)
            grade = int(ITEM_GRADES.get(str(item_index), 0) or 0)
            rows.append({
                    "first_observed_at_ns": first_observed_at_ns,
                    "observed_at_ns": observed_at_ns,
                    "client_key": client_key,
                    "client": client_name,
                    "character": character_name,
                    "item_index": item_index,
                    "item": _display_text(
                        candidate.get("name") or "Item não identificado"
                    ),
                    "count": int(candidate.get("count") or 0),
                    "occurrences": int(candidate.get("occurrences") or 0),
                    "grade": grade,
                    "rarity": DROP_RARITY_LABELS.get(
                        grade, "Sem raridade identificada"
                    ),
                })
        return rows

    def _filtered_drop_history_rows(self) -> list[dict[str, object]]:
        rows = self._drop_history_rows()
        query = self.drops_search.text().strip().casefold()
        selected_client = str(self.drops_client_filter.currentData() or "")
        selected_grade = self.drops_rarity_filter.currentData()
        try:
            grade_filter = int(selected_grade)
        except (TypeError, ValueError):
            grade_filter = -1
        return [
            row for row in rows
            if (not selected_client or row["client_key"] == selected_client)
            and (grade_filter < 0 or row["grade"] == grade_filter)
            and (
                not query
                or query in " ".join((
                    str(row["item"]),
                    str(row["character"]),
                    str(row["client"]),
                    str(row["rarity"]),
                )).casefold()
            )
        ]

    def _reset_drops_page(self, _value: object = None) -> None:
        self.drops_page = 1
        self._render_drops()

    def _change_drops_page(self, delta: int) -> None:
        self.drops_page = max(1, self.drops_page + delta)
        self._render_drops()

    @staticmethod
    def _drop_age_text(observed_at_ns: int, now_ns: int) -> str:
        if observed_at_ns <= 0:
            return "—"
        seconds = max(0, int((now_ns - observed_at_ns) / 1_000_000_000))
        if seconds < 60:
            return f"{seconds}s"
        if seconds < 3600:
            return f"{seconds // 60}m"
        return f"{seconds // 3600}h {seconds // 60 % 60:02d}m"

    def _render_drops(self) -> None:
        if not hasattr(self, "drops_table"):
            return
        rows = self._filtered_drop_history_rows()
        page_size = int(self.drops_page_size.currentText())
        pages = max(1, math.ceil(len(rows) / page_size))
        self.drops_page = min(self.drops_page, pages)
        visible = rows[
            (self.drops_page - 1) * page_size:self.drops_page * page_size
        ]
        now_ns = time.time_ns()
        self.drops_table.setRowCount(len(visible))
        for table_row, row in enumerate(visible):
            first_observed_at_ns = int(row["first_observed_at_ns"] or 0)
            observed_at_ns = int(row["observed_at_ns"] or 0)
            first_timestamp = (
                datetime.fromtimestamp(first_observed_at_ns / 1_000_000_000)
                .strftime("%d/%m %H:%M:%S")
                if first_observed_at_ns > 0 else "—"
            )
            timestamp = (
                datetime.fromtimestamp(observed_at_ns / 1_000_000_000)
                .strftime("%d/%m %H:%M:%S")
                if observed_at_ns > 0 else "—"
            )
            grade = int(row["grade"] or 0)
            color = QtGui.QColor(
                RARITY_COLORS.get(grade, DROP_DEFAULT_COLOR)
            )
            values = (
                first_timestamp,
                timestamp,
                str(row["client"]),
                str(row["character"]),
                str(row["item"]),
                self._format_count(row["count"]),
                str(row["rarity"]),
                self._format_count(row["occurrences"]),
            )
            for column, value in enumerate(values):
                if column == 4:
                    cell = QtWidgets.QTableWidgetItem(
                        self._inventory_icon(int(row["item_index"])), value
                    )
                    cell.setData(
                        QtCore.Qt.ItemDataRole.UserRole, int(row["item_index"])
                    )
                    cell.setForeground(color)
                else:
                    cell = QtWidgets.QTableWidgetItem(value)
                    if column == 6:
                        cell.setForeground(color)
                if column in (0, 1, 5, 6, 7):
                    cell.setTextAlignment(
                        QtCore.Qt.AlignmentFlag.AlignCenter
                    )
                self.drops_table.setItem(table_row, column, cell)
            self.drops_table.setRowHeight(table_row, 38)
        quantity = sum(int(row["count"] or 0) for row in rows)
        unique_items = len({int(row["item_index"] or 0) for row in rows})
        self.drops_summary.setText(
            f"{len(rows)} registro(s) · {quantity} item(ns) · "
            f"{unique_items} tipo(s)"
            if rows else "Nenhum drop confirmado para estes filtros"
        )
        last_seen = int(rows[0]["observed_at_ns"] or 0) if rows else 0
        self.drops_last_seen.setText(
            f"Último drop  {self._drop_age_text(last_seen, now_ns)}"
            if last_seen else "Último drop  —"
        )
        self.drops_page_status.setText(
            f"Página {self.drops_page} de {pages} · {len(rows)} registro(s)"
        )

    def _loot_announcement_rows(self) -> list[dict[str, object]]:
        language = str(self.preferences.get("item_name_language") or "pt")
        item_names = item_names_for_language(language)
        rows: list[dict[str, object]] = []
        latest_by_identity: dict[tuple[str, int, int], dict[str, object]] = {}
        events = sorted(
            self.snapshot.get("loot_announcements") or [],
            key=lambda event: int(event.get("ts_ns") or 0),
        )
        for event in events:
            client_key = str(event.get("client_key") or "")
            client_index = (
                ord(client_key[-1]) - ord("a")
                if client_key.startswith("client:") and client_key[-1:].isalpha()
                else -1
            )
            client_name = (
                self._client_name(client_index)
                if 0 <= client_index < CLIENT_SLOT_COUNT
                else "Cliente não identificado"
            )
            data = event.get("data") or {}
            for announcement in data.get("announcements") or []:
                if not isinstance(announcement, dict):
                    continue
                item_index = int(announcement.get("item_index") or 0)
                count = int(announcement.get("count") or 0)
                if item_index <= 0 or count <= 0:
                    continue
                grade = int(ITEM_GRADES.get(str(item_index), 0) or 0)
                observed_at_ns = int(event.get("ts_ns") or 0)
                player = _display_text(announcement.get("player_name"))
                identity = (player.casefold(), item_index, count)
                previous = latest_by_identity.get(identity)
                if (
                    previous is not None
                    and observed_at_ns - int(previous["observed_at_ns"] or 0)
                    <= 2_000_000_000
                ):
                    previous["observed_at_ns"] = max(
                        int(previous["observed_at_ns"] or 0), observed_at_ns
                    )
                    previous["client_keys"].add(client_key)
                    previous["client_names"].add(client_name)
                    previous["client"] = ", ".join(sorted(previous["client_names"]))
                    continue
                row = {
                    "observed_at_ns": observed_at_ns,
                    "client_key": client_key,
                    "client_keys": {client_key},
                    "client_names": {client_name},
                    "client": client_name,
                    "player": player,
                    "item_index": item_index,
                    "item": _display_text(
                        item_names.get(str(item_index)) or f"Item {item_index}"
                    ),
                    "count": count,
                    "grade": grade,
                    "rarity": DROP_RARITY_LABELS.get(
                        grade, "Sem raridade identificada"
                    ),
                }
                rows.append(row)
                latest_by_identity[identity] = row
        return sorted(
            rows, key=lambda row: int(row["observed_at_ns"] or 0), reverse=True
        )

    def _render_loot_announcements(self) -> None:
        if not hasattr(self, "loot_announcements_table"):
            return
        query = self.loot_announcements_search.text().strip().casefold()
        selected_client = str(
            self.loot_announcements_client_filter.currentData() or ""
        )
        try:
            selected_grade = int(
                self.loot_announcements_rarity_filter.currentData()
            )
        except (TypeError, ValueError):
            selected_grade = -1
        rows = [
            row for row in self._loot_announcement_rows()
            if (not selected_client or selected_client in row["client_keys"])
            and (selected_grade < 0 or row["grade"] == selected_grade)
            and (
                not query
                or query in " ".join((
                    str(row["player"]), str(row["item"]),
                    str(row["client"]), str(row["rarity"]),
                )).casefold()
            )
        ]
        page_size = int(self.loot_announcements_page_size.currentText())
        pages = max(1, math.ceil(len(rows) / page_size))
        self.loot_announcements_page = min(self.loot_announcements_page, pages)
        visible = rows[
            (self.loot_announcements_page - 1) * page_size:
            self.loot_announcements_page * page_size
        ]
        self.loot_announcements_table.setRowCount(len(visible))
        for table_row, row in enumerate(visible):
            observed_at_ns = int(row["observed_at_ns"] or 0)
            timestamp = (
                datetime.fromtimestamp(observed_at_ns / 1_000_000_000)
                .strftime("%d/%m %H:%M:%S")
                if observed_at_ns > 0 else "—"
            )
            grade = int(row["grade"] or 0)
            color = QtGui.QColor(RARITY_COLORS.get(grade, DROP_DEFAULT_COLOR))
            values = (
                timestamp, str(row["client"]), str(row["player"]),
                str(row["item"]), self._format_count(row["count"]),
                str(row["rarity"]),
            )
            for column, value in enumerate(values):
                if column == 3:
                    cell = QtWidgets.QTableWidgetItem(
                        self._inventory_icon(int(row["item_index"])), value
                    )
                    cell.setForeground(color)
                else:
                    cell = QtWidgets.QTableWidgetItem(value)
                    if column == 5:
                        cell.setForeground(color)
                if column in (0, 1, 4, 5):
                    cell.setTextAlignment(
                        QtCore.Qt.AlignmentFlag.AlignCenter
                    )
                self.loot_announcements_table.setItem(table_row, column, cell)
            self.loot_announcements_table.setRowHeight(table_row, 38)
        self.loot_announcements_summary.setText(
            f"{len(rows)} aviso(s) único(s) · {len(visible)} nesta página"
            if rows else "Nenhum aviso capturado"
        )
        self.loot_announcements_page_status.setText(
            f"Página {self.loot_announcements_page} de {pages} · {len(rows)} registro(s)"
        )

    def _reset_loot_announcements_page(self, _value: object = None) -> None:
        self.loot_announcements_page = 1
        self._render_loot_announcements()

    def _change_loot_announcements_page(self, delta: int) -> None:
        self.loot_announcements_page = max(1, self.loot_announcements_page + delta)
        self._render_loot_announcements()

    def _render_overview_drops(self) -> None:
        if not hasattr(self, "overview_drop_rows"):
            return
        language = str(self.preferences.get("item_name_language") or "pt")
        active_client_key = _client_key(self.active_client)
        candidates = confirmed_item_drop_alerts(
            [
                event
                for event in self.snapshot.get("drop_events") or []
                if str(event.get("client_key") or "") == active_client_key
            ],
            item_names_for_language(language),
        )
        flattened: list[tuple[int, str, int, int, int]] = []
        now_ns = time.time_ns()
        for candidate in reversed(candidates):
            age_seconds = max(
                0,
                int((now_ns - int(candidate.get("observed_at_ns") or now_ns)) / 1_000_000_000),
            )
            for item in candidate.get("items") or []:
                flattened.append((
                    int(item.get("item_index") or 0),
                    _display_text(item.get("name") or "Item não identificado"),
                    int(item.get("count") or 0),
                    age_seconds,
                    int(ITEM_GRADES.get(str(item.get("item_index") or 0), 0) or 0),
                ))
                if len(flattened) >= len(self.overview_drop_rows):
                    break
            if len(flattened) >= len(self.overview_drop_rows):
                break
        for index, (marker, name, age) in enumerate(self.overview_drop_rows):
            if index < len(flattened):
                item_index, item_name, count, age_seconds, grade = flattened[index]
                color = RARITY_COLORS.get(grade, DROP_DEFAULT_COLOR)
                rarity = DROP_RARITY_LABELS.get(grade, "Sem raridade identificada")
                marker.setPixmap(self._inventory_icon(item_index).pixmap(26, 26))
                marker.setStyleSheet(
                    f"background: #10161B; border: 1px solid {color}; border-radius: 5px;"
                )
                marker.setToolTip(f"{rarity} · Item #{item_index}")
                name.setStyleSheet(f"color: {color}; font-weight: 600;")
                name.setToolTip(rarity)
                name.setText(f"{item_name}  x{count}" if count > 1 else item_name)
                age.setText(
                    f"{age_seconds}s" if age_seconds < 60 else f"{age_seconds // 60}m"
                )
            else:
                marker.setPixmap(_navigation_icon("box", 22).pixmap(22, 22))
                marker.setStyleSheet("")
                marker.setToolTip("")
                name.setStyleSheet("")
                name.setToolTip("")
                name.setText("Aguardando drop")
                age.setText("—")

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
        footer.setFixedHeight(38)
        row = QtWidgets.QHBoxLayout(footer)
        row.setContentsMargins(32, 0, 18, 0)
        self.footer_state = _label(
            "API local desligada · Site remoto desativado neste perfil",
            "footer",
        )
        row.addWidget(self.footer_state)
        row.addStretch(1)
        return footer


STYLE = """
QWidget { color: #F4F2EB; font-family: 'Saira'; font-size: 14px; }
QMainWindow, #mainSurface { background: #090E12; }
#topbar { background: #0B1116; border-bottom: 1px solid #273138; }
#statusbar { background: #0B1116; border-top: 1px solid #273138; }
#sidebar { background: #0A1116; border-right: 1px solid #344049; }
#sidebarNavScroll, #sidebarNavScroll QWidget#qt_scrollarea_viewport, #sidebarNavContent { background: #0A1116; border: none; }
#sidebarNavScroll QScrollBar:vertical { background: #0A1116; width: 9px; }
#sidebarNavScroll QScrollBar::handle:vertical { background: #344049; border-radius: 4px; min-height: 30px; }
#sidebarNavScroll QScrollBar::add-line:vertical, #sidebarNavScroll QScrollBar::sub-line:vertical { height: 0; }
#workspace { background: qradialgradient(cx:0.18, cy:0.02, radius:1.1, fx:0.18, fy:0.02, stop:0 #111820, stop:0.36 #0B1217, stop:1 #090E12); }
#navSeparator { background: #2B343A; margin-left: 18px; margin-right: 18px; }

QLabel[role='workspaceTitle'] { font-family: 'Saira SemiCondensed'; font-size: 31px; font-weight: 700; }
QLabel[role='versionBadge'] { color: #D8D4CA; border: 1px solid #8B6B2D; border-radius: 5px; padding: 5px 13px; }
QLabel[role='product'] { font-family: 'Saira SemiCondensed'; font-size: 21px; font-weight: 700; }
QLabel[role='title'] { font-family: 'Saira SemiCondensed'; font-size: 30px; font-weight: 700; }
QLabel[role='subtitle'], QLabel[role='cardTitle'] { font-size: 17px; font-weight: 600; }
QLabel[role='hero'] { font-family: 'Saira SemiCondensed'; font-size: 24px; font-weight: 700; }
QLabel[role='cardIdentity'] { font-family: 'Saira SemiCondensed'; font-size: 19px; font-weight: 600; }
QLabel[role='sessionTime'] { font-family: 'Saira SemiCondensed'; font-size: 31px; font-weight: 600; }
QLabel[role='metricValue'] { font-family: 'Saira SemiCondensed'; font-size: 20px; font-weight: 600; }
QLabel[role='metricCompact'] { color: #C9C5BB; font-size: 14px; }
QLabel[role='mapCoordinates'] { color: #E5B35C; font-family: 'Saira SemiCondensed'; font-size: 25px; font-weight: 700; }
QLabel[role='statusLine'], QLabel[role='detailLine'] { color: #D2CEC5; font-size: 14px; }
QLabel[role='healthLine'] { color: #E5B35C; font-weight: 600; }
QLabel[role='healthLineOk'] { color: #58C96B; font-weight: 600; }
QLabel[role='healthLineInfo'] { color: #63B9F3; font-weight: 600; }
QLabel[role='footer'] { color: #7F898F; font-size: 12px; }
QLabel[role='muted'] { color: #AEB7C2; }
QLabel[role='info'] { color: #63B9F3; }
QLabel[role='data'] { color: #63B9F3; font-size: 20px; font-weight: 600; }
QLabel[role='ok'] { color: #58C96B; }
QLabel[role='warning'] { color: #E5B35C; }
QLabel[role='activeBadge'] { color: #78D857; background: #17251A; border: 1px solid #2B492F; border-radius: 5px; padding: 3px 10px; }
QLabel[role='step'] { background: #3A301B; color: #F6BE3B; border: 1px solid #D4A64D; border-radius: 5px; font-weight: 700; }
#dashboardStatus { font-family: 'Saira SemiCondensed'; font-size: 29px; font-weight: 700; }
#statusChip { background: #0E1419; border: 1px solid #374149; border-radius: 5px; padding: 5px 11px; min-height: 22px; }
#mapViewerPanel { background: #0A0F13; border: 1px solid #2C3941; border-radius: 6px; }

QPushButton { background: #0D1317; border: 1px solid #344049; border-radius: 5px; padding: 8px 14px; }
QPushButton:hover { border-color: #D4A64D; color: #FFFFFF; }
QPushButton:focus { border: 2px solid #D4A64D; }
QPushButton:checked { background: #30291C; border-color: #D4A64D; color: #F4F2EB; }
QPushButton:disabled { color: #626C72; border-color: #273138; background: #0A0F12; }
#mapToolButton { padding: 4px 8px; min-height: 24px; font-size: 17px; font-weight: 700; }
#mapFocusButton { padding: 5px 10px; min-height: 24px; }
#linkButton { background: transparent; border: none; color: #D4A64D; padding: 4px 0; text-align: left; }
#linkButton:hover { background: transparent; border: none; color: #F0C977; }
#linkButton:focus { border: 1px solid #D4A64D; }
#sidebar QPushButton { text-align: left; border: none; border-radius: 5px; margin: 0 0 0 0; padding: 10px 18px; color: #B8C0C5; }
#sidebar QPushButton:hover { background: #11191E; color: #F4F2EB; }
#sidebar QPushButton:checked { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #30291C,stop:1 #16191A); border-left: 3px solid #E5B35C; color: #F4F2EB; padding-left: 15px; }
QPushButton[client='true'] { min-width: 205px; padding: 10px 16px; text-align: left; }
QPushButton[client='true']:checked { border: 2px solid #E5B35C; background: #10161B; color: #F4F2EB; }
#addClient { color: #BFC5C8; padding: 10px 16px; }
#removeClient { color: #FF8068; border-color: #8F4639; padding: 10px 14px; }
#removeClient:hover { color: #FF9A86; border-color: #FF6547; background: #1B1110; }
#removeClient:disabled { color: #626C72; border-color: #273138; background: #0A0F12; }
QLabel[role='clientSource'] { color: #AEB7C2; padding: 8px 4px; }

QToolButton { background: #0D1317; color: #F4F2EB; border: 1px solid #344049; border-radius: 5px; padding: 6px; }
QToolButton:hover { border-color: #D4A64D; }
QToolButton:disabled { border-color: #273138; background: #0A0F12; }
QToolButton[captureAction='true'] { margin-left: 2px; }
#captureStart { border-color: #2F6D3A; background: #0D1710; }
#captureStart:hover { border-color: #58C96B; background: #112117; }
#captureContinue { border-color: #356C8F; background: #0D151B; }
#captureContinue:hover { border-color: #63B9F3; background: #10202B; }
#capturePause { border-color: #6D5428; background: #17140D; }
#capturePause:hover { border-color: #D4A64D; background: #211A0F; }
#captureStop, #captureStopRaw { border-color: #8F4639; background: #1B1110; }
#captureStop:hover, #captureStopRaw:hover { border-color: #FF6547; background: #271412; }
QToolButton[captureAction='true']:disabled { border-color: #273138; background: #0A0F12; }

#dashboardCard, #emptyCard, #panel, #metricGroup, #mapMetricGroup, #secondaryMetricGroup {
    background: rgba(15, 21, 26, 235);
    border: 1px solid #3A4349;
    border-radius: 8px;
}
#dashboardCard { min-height: 225px; }
#accentPanel { background: rgba(15, 21, 26, 235); border: 1px solid #D4A64D; border-radius: 8px; }
#metricDivider { background: #344049; }
#dropRow { background: #0C1216; border: 1px solid #344049; border-radius: 5px; }
#dropIcon { background: #10161B; border: 1px solid #344049; border-radius: 5px; }
#characterIcon, #roverIcon { background: #0A1115; border: 1px solid #344049; border-radius: 8px; }

QProgressBar { background: #273138; border: none; border-radius: 4px; height: 9px; }
QProgressBar::chunk { background: #63B9F3; border-radius: 4px; }
#goldProgress::chunk { background: #E5B35C; }
#playerHealthProgress::chunk { background: #58C96B; }

QTabBar { background: transparent; }
QTabWidget::pane { background: #0B1217; border: 1px solid #344049; }
#pageBancoPvP, #pageBancoPvE, #pageBancoLeilao { background: #0B1217; }
QTabBar::tab { background: #0D1317; color: #D2CEC5; border: 1px solid #344049; border-bottom-color: #D4A64D; padding: 9px 22px; min-width: 96px; }
QTabBar::tab:selected { background: #30291C; color: #F4F2EB; border-color: #D4A64D; }
QTabBar::tab:hover { color: #FFFFFF; border-color: #D4A64D; }

QMessageBox { background: #0B1217; }
QMessageBox QLabel { color: #F4F2EB; background: transparent; }
QMessageBox QPushButton { color: #F4F2EB; min-width: 90px; }
QMenu { background: #0B1217; color: #F4F2EB; border: 1px solid #344049; padding: 4px; }
QMenu::item { background: transparent; padding: 7px 24px 7px 28px; }
QMenu::item:selected { background: #30291C; color: #E5B35C; }
QMenu::item:disabled { color: #626C72; }
QMenu::separator { background: #273138; height: 1px; margin: 4px 8px; }

QLineEdit, QComboBox, QSpinBox, QListWidget, QTableWidget { background: #0D1317; color: #F4F2EB; border: 1px solid #344049; border-radius: 5px; padding: 6px; selection-background-color: #30291C; selection-color: #F4F2EB; }
QLineEdit:disabled { background: #0A0F12; color: #626C72; }
QComboBox QAbstractItemView { background: #0D1317; color: #F4F2EB; selection-background-color: #30291C; }
QComboBox::drop-down, QSpinBox::up-button, QSpinBox::down-button { border: none; }
QTableWidget { gridline-color: #273138; border-radius: 0; padding: 0; }
QHeaderView { background: #10181D; }
QHeaderView::section { background: #10181D; color: #AEB7C2; border: none; border-right: 1px solid #273138; border-bottom: 1px solid #273138; padding: 7px; }
QTableCornerButton::section { background: #10181D; border: none; border-bottom: 1px solid #273138; }
QCheckBox { spacing: 7px; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #52626A; border-radius: 3px; background: #0D1317; }
QCheckBox::indicator:checked { background: #D4A64D; border-color: #F6BE3B; }

QScrollArea, QScrollArea QWidget#qt_scrollarea_viewport, #scrollContent { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 9px; }
QScrollBar::handle:vertical { background: #344049; border-radius: 4px; min-height: 30px; }
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
    if app.styleSheet() != STYLE:
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
        window.overview_map_preview.set_snapshot(
            "639",
            {"x": 155.0, "y": 312.0, "z": 0.0},
            [],
        )
        passed = (
            window.minimumSize() == QtCore.QSize(1180, 664)
            and window.page_stack.count() == len(PAGES)
            and (ROOT / "core" / "rfnext_frame_decode.py").is_file()
            and (ROOT / "core" / "collection_requirements.csv").is_file()
            and (ROOT / "core" / "job1_pending_layouts.json").is_file()
            and (ROOT / "core" / "job1_all_opcodes.csv").is_file()
            and MACHINE_STATE_DIR != STATE_DIR
            and UPDATES_DIR.parent == MACHINE_STATE_DIR
            and window.overview_map_preview.map_index == 639
            and window.overview_map_preview._map_pixmap() is not None
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

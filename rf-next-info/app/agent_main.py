"""Entrada independente do RF Next Companion para Windows."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtNetwork, QtWidgets

from app.agent_paths import (
    AGENT_ASSETS_DIR,
    AGENT_DIAGNOSTIC_DIR,
    AGENT_LOG_PATH,
    AGENT_PREFERENCES_PATH,
    AGENT_RUNTIME_DIR,
    AGENT_UPDATE_DIR,
    ensure_agent_layout,
)
from app.agent_preferences import (
    configure_agent_startup,
    load_agent_preferences,
    save_agent_preferences,
)
from app.build_profile import (
    AGENT_SERVER,
    AGENT_TRANSPORT_VERSION,
    AGENT_UPDATE_CHANNEL,
    AGENT_UPDATE_FEED,
    AGENT_UPDATE_PUBLIC_KEYS,
    APP_VERSION,
    PRODUCT_NAME,
    RELEASE_SEQUENCE,
    validate_build_profile,
)
from core.store import LEVEL_CURVE
from core.agent_updates import UpdateCandidate, download_verified, fetch_latest
from core.web_agent_selftest import run_offline_agent_self_test
from core.windows_agent_capture import StandaloneWindowsAgentRuntime


LOG = logging.getLogger("rfqol.agent")
INSTANCE_SERVER_NAME = "Karvalho.RFQOLAgent"


def _format_status_time(value: object) -> str | None:
    try:
        if isinstance(value, (int, float)):
            if value <= 0:
                return None
            parsed = datetime.fromtimestamp(
                float(value) / 1_000_000_000, tz=timezone.utc
            )
        else:
            text = str(value or "").strip()
            if not text:
                return None
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone().strftime("%d/%m %H:%M:%S")
    except (OverflowError, OSError, TypeError, ValueError):
        return None


def _format_duration_seconds(value: object) -> str | None:
    try:
        seconds = max(0, int(float(value)))
    except (TypeError, ValueError, OverflowError):
        return None
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _flow_rates(
    previous: tuple[float, int, int, int] | None,
    current: tuple[float, int, int, int],
) -> tuple[float, float, float]:
    """Calcula geração, envio e saldo da fila entre duas atualizações da UI."""
    if previous is None:
        return 0.0, 0.0, 0.0
    elapsed = current[0] - previous[0]
    if elapsed <= 0:
        return 0.0, 0.0, 0.0
    generated_delta = current[1] - previous[1]
    sent_delta = current[2] - previous[2]
    queue_delta = current[3] - previous[3]
    if generated_delta < 0 or sent_delta < 0:
        # Reinício do runtime: não transforme o reset dos contadores em taxa.
        return 0.0, 0.0, 0.0
    return (
        generated_delta / elapsed,
        sent_delta / elapsed,
        queue_delta / elapsed,
    )


def _format_event_rate(value: float, *, signed: bool = False) -> str:
    prefix = "+" if signed and value > 0 else ""
    return (prefix + f"{value:.1f}").replace(".", ",")


class AgentBackend(QtCore.QObject):
    health_ready = QtCore.Signal(dict)
    command_finished = QtCore.Signal(str, dict)
    command_failed = QtCore.Signal(str, str)
    shutdown_finished = QtCore.Signal()

    def __init__(self, runtime: StandaloneWindowsAgentRuntime) -> None:
        super().__init__()
        self.runtime = runtime

    @QtCore.Slot()
    def start_capture(self) -> None:
        try:
            result = self.runtime.start_capture()
        except Exception as error:
            LOG.exception("agent_capture_start_failed")
            self.command_failed.emit("start", f"{type(error).__name__}: {error}")
            return
        self.command_finished.emit("start", result)
        self.health_ready.emit(self.runtime.health())

    @QtCore.Slot()
    def stop_capture(self) -> None:
        try:
            result = self.runtime.stop_capture(reason="paused")
        except Exception as error:
            LOG.exception("agent_capture_stop_failed")
            self.command_failed.emit("stop", f"{type(error).__name__}: {error}")
            return
        self.command_finished.emit("stop", result)
        self.health_ready.emit(self.runtime.health())

    @QtCore.Slot(bool)
    def poll(self, auto_capture: bool) -> None:
        try:
            routes = self.runtime.refresh_routes()
            has_clients = not routes.get("no_clients", True)
            if (
                auto_capture
                and has_clients
                and routes.get("capture_authorized", True)
                and not self.runtime.active
            ):
                self.runtime.start_capture()
                self.command_finished.emit("auto_start", {})
            elif self.runtime.active:
                if routes.get("no_clients"):
                    self.runtime.stop_capture(reason="finished")
                    self.command_finished.emit("clients_closed", {})
            self.health_ready.emit(self.runtime.health())
        except Exception as error:
            LOG.exception("agent_poll_failed")
            self.command_failed.emit("poll", f"{type(error).__name__}: {error}")

    @QtCore.Slot(int)
    def configure_memory(self, memory_mb: int) -> None:
        try:
            applied = self.runtime.configure_memory_budget(memory_mb)
            self.command_finished.emit(
                "memory", {"applied": applied, "memory_mb": memory_mb}
            )
            self.health_ready.emit(self.runtime.health())
        except Exception as error:
            self.command_failed.emit("memory", f"{type(error).__name__}: {error}")

    @QtCore.Slot()
    def shutdown(self) -> None:
        try:
            self.runtime.close()
        except Exception:
            LOG.exception("agent_shutdown_failed")
        self.shutdown_finished.emit()


class AgentUpdateSignals(QtCore.QObject):
    state_changed = QtCore.Signal(str)
    ready = QtCore.Signal(object)
    failed = QtCore.Signal(str)


def _build_update_confirmation_dialog(
    parent: QtWidgets.QWidget,
    candidate: UpdateCandidate,
) -> QtWidgets.QMessageBox:
    """Cria a confirmação de atualização sem depender do tema/idioma do Windows."""
    sha256 = str(candidate.manifest.get("sha256") or "").upper()
    displayed_sha = "\n".join((sha256[:32], sha256[32:])) if sha256 else "—"
    dialog = QtWidgets.QMessageBox(parent)
    dialog.setWindowTitle("Atualização pronta")
    dialog.setIcon(QtWidgets.QMessageBox.Icon.Question)
    dialog.setText(
        f"A versão {candidate.version} foi baixada e validada.\n\n"
        "Para instalar, a captura será encerrada e o instalador será aberto "
        "de forma visível. Como o projeto não usa Authenticode, o Windows "
        "poderá exibir um aviso de reputação.\n\n"
        f"SHA-256:\n{displayed_sha}\n\n"
        "Deseja instalar agora?"
    )
    dialog.setTextFormat(QtCore.Qt.TextFormat.PlainText)
    dialog.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
    dialog.setStandardButtons(
        QtWidgets.QMessageBox.StandardButton.Yes
        | QtWidgets.QMessageBox.StandardButton.No
    )
    dialog.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)
    dialog.setEscapeButton(QtWidgets.QMessageBox.StandardButton.No)
    dialog.button(QtWidgets.QMessageBox.StandardButton.Yes).setText("Instalar agora")
    dialog.button(QtWidgets.QMessageBox.StandardButton.No).setText("Agora não")
    dialog.setStyleSheet("""
        QMessageBox {
            color: #f4f2eb;
            background-color: #0d1c23;
        }
        QMessageBox QLabel {
            color: #f4f2eb;
            background: transparent;
            font-family: 'Saira';
            font-size: 14px;
        }
        QMessageBox QLabel#qt_msgbox_label {
            min-width: 560px;
            max-width: 620px;
        }
        QMessageBox QPushButton {
            color: #f4f2eb;
            background: #132730;
            border: 1px solid #3c5662;
            border-radius: 7px;
            min-width: 110px;
            min-height: 24px;
            padding: 8px 14px;
            font-weight: 600;
        }
        QMessageBox QPushButton:hover {
            color: #ffffff;
            background: #1b343f;
            border-color: #5d7b88;
        }
        QMessageBox QPushButton:default {
            color: #f4f2eb;
            background: #25323a;
            border-color: #6c7e87;
        }
    """)
    return dialog


class AgentWindow(QtWidgets.QWidget):
    start_requested = QtCore.Signal()
    stop_requested = QtCore.Signal()
    poll_requested = QtCore.Signal(bool)
    memory_requested = QtCore.Signal(int)
    shutdown_requested = QtCore.Signal()

    def __init__(
        self,
        runtime: StandaloneWindowsAgentRuntime,
        *,
        preferences_path: Path = AGENT_PREFERENCES_PATH,
        background: bool = False,
        start_worker: bool = True,
    ) -> None:
        super().__init__()
        self.runtime = runtime
        self.preferences_path = Path(preferences_path)
        self.preferences = load_agent_preferences(self.preferences_path)
        self._health: dict[str, Any] = {}
        self._exiting = False
        self._busy = False
        self._poll_pending = False
        self._flow_sample: tuple[float, int, int, int] | None = None
        self._pending_memory_mb: int | None = None
        self._update_busy = False
        self._ready_update: UpdateCandidate | None = None
        self._pending_update_installer: Path | None = None
        self.update_signals = AgentUpdateSignals(self)
        self.update_signals.state_changed.connect(self._update_state_changed)
        self.update_signals.ready.connect(self._update_ready)
        self.update_signals.failed.connect(self._update_failed)
        self.update_timer = QtCore.QTimer(self)
        self.update_timer.setInterval(6 * 60 * 60 * 1000)
        self.update_timer.timeout.connect(self._request_update_check)
        self.worker_thread: QtCore.QThread | None = None
        self.backend: AgentBackend | None = None
        self.poll_timer = QtCore.QTimer(self)
        self.poll_timer.setInterval(2000)
        self.poll_timer.timeout.connect(self._request_poll)

        self.setWindowTitle(f"{PRODUCT_NAME} · {APP_VERSION}")
        self.setMinimumSize(620, 620)
        self.resize(760, 720)
        self.setObjectName("agentWindow")
        self._build_ui()
        self._build_tray()
        self._apply_preferences()
        self._apply_style()
        if start_worker:
            self._start_worker()
            self.poll_timer.start()
            QtCore.QTimer.singleShot(0, self._request_poll)
            self.update_timer.start()
            QtCore.QTimer.singleShot(5000, self._request_update_check)
        if background and self.tray.isVisible():
            self.hide()
        else:
            self.show()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        title_box = QtWidgets.QVBoxLayout()
        title_box.setSpacing(2)
        title = QtWidgets.QLabel(PRODUCT_NAME, objectName="title")
        subtitle = QtWidgets.QLabel(
            "Captura e decode no computador · processamento no site",
            objectName="muted",
        )
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        self.state_label = QtWidgets.QLabel("Ocioso", objectName="stateIdle")
        self.state_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.state_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        header.addWidget(self.state_label)
        header.setAlignment(
            self.state_label,
            QtCore.Qt.AlignmentFlag.AlignTop
            | QtCore.Qt.AlignmentFlag.AlignRight,
        )
        layout.addLayout(header)

        controls = QtWidgets.QHBoxLayout()
        self.start_button = QtWidgets.QPushButton(
            "Iniciar captura", objectName="primaryButton"
        )
        self.start_button.clicked.connect(self._start_clicked)
        self.stop_button = QtWidgets.QPushButton("Pausar captura")
        self.stop_button.clicked.connect(self._stop_clicked)
        self.stop_button.setEnabled(False)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        status = QtWidgets.QFrame(objectName="card")
        status_layout = QtWidgets.QGridLayout(status)
        status_layout.setContentsMargins(18, 16, 18, 16)
        status_layout.setHorizontalSpacing(24)
        status_layout.setVerticalSpacing(8)
        self.capture_value = QtWidgets.QLabel("Desligada", objectName="statusValue")
        self.clients_value = QtWidgets.QLabel("Nenhum", objectName="statusValue")
        self.server_value = QtWidgets.QLabel(
            "Modo local · envio desativado", objectName="statusValue"
        )
        self.outbox_value = QtWidgets.QLabel("0 eventos", objectName="statusValue")
        self.flow_value = QtWidgets.QLabel(
            "Gerados 0,0/s · enviados 0,0/s · fila 0,0/s",
            objectName="statusValue",
        )
        self.traffic_value = QtWidgets.QLabel(
            "0 pacotes · 0 eventos", objectName="statusValue"
        )
        self.last_decode_value = QtWidgets.QLabel(
            "Nenhum evento decodificado", objectName="statusValue"
        )
        self.last_ack_value = QtWidgets.QLabel(
            "Nenhum lote confirmado", objectName="statusValue"
        )
        self.memory_value = QtWidgets.QLabel(
            "Limite 1.024 MiB", objectName="statusValue"
        )
        self.authorization_value = QtWidgets.QLabel(
            "Verificando", objectName="statusValue"
        )
        installation_id = str(self.preferences.get("installation_id") or "").strip()
        self.identity_value = QtWidgets.QLabel(
            f"Agent {installation_id[:8].upper()}" if installation_id else "Indisponível",
            objectName="statusValue",
        )
        self.identity_value.setToolTip(installation_id)
        self.api_value = QtWidgets.QLabel("Preparando", objectName="statusValue")
        self.update_value = QtWidgets.QLabel(
            f"{APP_VERSION} · aguardando verificação", objectName="statusValue"
        )
        rows = (
            ("Captura", self.capture_value),
            ("Clientes", self.clients_value),
            ("Servidor", self.server_value),
            ("Fila offline", self.outbox_value),
            ("Fluxo do site", self.flow_value),
            ("Leitura", self.traffic_value),
            ("Último decode", self.last_decode_value),
            ("Último envio", self.last_ack_value),
            ("Memória", self.memory_value),
            ("Identidade", self.identity_value),
            ("Conta", self.authorization_value),
            ("API local", self.api_value),
            ("Atualização", self.update_value),
        )
        for row, (label, value) in enumerate(rows):
            status_layout.addWidget(QtWidgets.QLabel(label, objectName="muted"), row, 0)
            status_layout.addWidget(value, row, 1)
        status_layout.setColumnStretch(1, 1)
        layout.addWidget(status)

        clients_card = QtWidgets.QFrame(objectName="card")
        clients_layout = QtWidgets.QVBoxLayout(clients_card)
        clients_layout.setContentsMargins(18, 16, 18, 16)
        clients_layout.setSpacing(10)
        clients_layout.addWidget(QtWidgets.QLabel("Personagens reconhecidos", objectName="section"))
        self.clients_list = QtWidgets.QListWidget()
        self.clients_list.setFixedHeight(70)
        self.clients_list.addItem("Aguardando captura")
        clients_layout.addWidget(self.clients_list)
        layout.addWidget(clients_card)

        settings = QtWidgets.QFrame(objectName="card")
        settings_layout = QtWidgets.QFormLayout(settings)
        settings_layout.setContentsMargins(18, 16, 18, 16)
        settings_layout.setHorizontalSpacing(28)
        settings_layout.setVerticalSpacing(12)
        self.auto_capture = QtWidgets.QCheckBox("Iniciar ao reconhecer cliente")
        self.auto_capture.toggled.connect(self._preferences_changed)
        self.startup = QtWidgets.QCheckBox("Abrir com o Windows")
        self.startup.toggled.connect(self._startup_changed)
        self.memory_limit = QtWidgets.QComboBox()
        for value in (256, 512, 768, 1024, 1536, 2048, 4096, 8192):
            self.memory_limit.addItem(f"{value:,} MiB".replace(",", "."), value)
        self.memory_limit.currentIndexChanged.connect(self._memory_changed)
        settings_layout.addRow("Captura automática", self.auto_capture)
        settings_layout.addRow("Inicialização", self.startup)
        settings_layout.addRow("Limite de RAM", self.memory_limit)
        layout.addWidget(settings)

        actions = QtWidgets.QHBoxLayout()
        actions.setSpacing(10)
        self.site_button = QtWidgets.QPushButton("Abrir site")
        self.site_button.setEnabled(bool(AGENT_SERVER))
        self.site_button.setToolTip("Abra o site para vincular este Agent à sua conta.")
        self.site_button.clicked.connect(self._open_site)
        self.pair_button = QtWidgets.QPushButton("Copiar pareamento da API")
        self.pair_button.clicked.connect(self._copy_pairing)
        self.diagnostic_button = QtWidgets.QPushButton("Exportar diagnóstico")
        self.diagnostic_button.clicked.connect(self._export_diagnostic)
        self.update_button = QtWidgets.QPushButton("Verificar atualização")
        self.update_button.clicked.connect(self._request_update_check)
        for button in (
            self.site_button,
            self.pair_button,
            self.diagnostic_button,
            self.update_button,
        ):
            button.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Ignored,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            actions.addWidget(button, 1)
        layout.addLayout(actions)

        self.message = QtWidgets.QLabel("Agent pronto para iniciar.", objectName="muted")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)

    def _build_tray(self) -> None:
        icon_path = AGENT_ASSETS_DIR / "rf-next-companion.png"
        icon = QtGui.QIcon(str(icon_path))
        if icon.isNull():
            icon = self.style().standardIcon(
                QtWidgets.QStyle.StandardPixmap.SP_ComputerIcon
            )
        self.setWindowIcon(icon)
        self.tray = QtWidgets.QSystemTrayIcon(icon, self)
        self.tray.setToolTip(PRODUCT_NAME)
        menu = QtWidgets.QMenu(self)
        show_action = menu.addAction("Abrir Agent")
        show_action.triggered.connect(self._show_window)
        self.tray_start_action = menu.addAction("Iniciar captura")
        self.tray_start_action.triggered.connect(self._start_clicked)
        self.tray_stop_action = menu.addAction("Pausar captura")
        self.tray_stop_action.triggered.connect(self._stop_clicked)
        self.tray_stop_action.setEnabled(False)
        menu.addSeparator()
        exit_action = menu.addAction("Encerrar Agent")
        exit_action.triggered.connect(self._exit_agent)
        update_action = menu.addAction("Verificar atualização")
        update_action.triggered.connect(self._request_update_check)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        if QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _apply_preferences(self) -> None:
        self.auto_capture.blockSignals(True)
        self.startup.blockSignals(True)
        self.memory_limit.blockSignals(True)
        self.auto_capture.setChecked(bool(self.preferences["auto_capture"]))
        self.startup.setChecked(bool(self.preferences["start_with_windows"]))
        index = self.memory_limit.findData(int(self.preferences["memory_limit_mb"]))
        if index < 0:
            self.memory_limit.addItem(
                f"{int(self.preferences['memory_limit_mb']):,} MiB".replace(",", "."),
                int(self.preferences["memory_limit_mb"]),
            )
            index = self.memory_limit.count() - 1
        self.memory_limit.setCurrentIndex(index)
        self.memory_limit.blockSignals(False)
        self.startup.blockSignals(False)
        self.auto_capture.blockSignals(False)

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QWidget {
                color: #f4f2eb;
                font-family: 'Saira';
                font-size: 14px;
            }
            QWidget#agentWindow {
                background: #071218;
            }
            QLabel#title {
                color: #ffffff;
                font-family: 'Saira SemiCondensed';
                font-size: 28px;
                font-weight: 700;
            }
            QLabel#section {
                color: #ffffff;
                font-family: 'Saira SemiCondensed';
                font-size: 17px;
                font-weight: 700;
            }
            QLabel#muted { color: #a9bac3; }
            QLabel#statusValue { color: #f4f2eb; font-weight: 500; }
            QLabel#stateIdle, QLabel#stateActive, QLabel#stateError {
                min-width: 88px;
                padding: 8px 14px;
                border-radius: 8px;
                font-family: 'Saira SemiCondensed';
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#stateIdle {
                color: #ffc857;
                background: #342915;
                border: 1px solid #695126;
            }
            QLabel#stateActive {
                color: #72e39a;
                background: #153221;
                border: 1px solid #285e3b;
            }
            QLabel#stateError {
                color: #ff9696;
                background: #3a1d22;
                border: 1px solid #6f3038;
            }
            QFrame#card {
                background: #0d1c23;
                border: 1px solid #29434e;
                border-radius: 10px;
            }
            QPushButton {
                min-height: 22px;
                padding: 9px 14px;
                background: #132730;
                border: 1px solid #3c5662;
                border-radius: 7px;
                font-weight: 600;
            }
            QPushButton:hover {
                color: #ffffff;
                background: #1b343f;
                border-color: #5d7b88;
            }
            QPushButton:pressed { background: #0d2028; }
            QPushButton#primaryButton {
                color: #18140c;
                background: #e5b35c;
                border-color: #f0c779;
            }
            QPushButton#primaryButton:hover { background: #f0c779; }
            QPushButton:disabled {
                color: #71838c;
                background: #0a171d;
                border-color: #263b44;
            }
            QListWidget,
            QComboBox {
                color: #f4f2eb;
                background: #08161c;
                border: 1px solid #304b56;
                border-radius: 7px;
                padding: 7px 10px;
                selection-background-color: #34432b;
                selection-color: #ffffff;
            }
            QListWidget::item { padding: 6px 5px; }
            QListWidget::item:selected { background: #34432b; }
            QComboBox:hover { border-color: #5b7681; }
            QComboBox QAbstractItemView {
                color: #f4f2eb;
                background: #0d1c23;
                border: 1px solid #3c5662;
                selection-background-color: #3a321f;
                selection-color: #ffffff;
            }
            QCheckBox { spacing: 9px; }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #506b76;
                border-radius: 4px;
                background: #08161c;
            }
            QCheckBox::indicator:hover { border-color: #e5b35c; }
            QCheckBox::indicator:checked {
                background: #e5b35c;
                border-color: #f0c779;
            }
            QToolTip {
                color: #f4f2eb;
                background: #14262f;
                border: 1px solid #49616c;
                padding: 5px;
            }
            QMenu {
                color: #f4f2eb;
                background: #0d1c23;
                border: 1px solid #3c5662;
                padding: 6px;
            }
            QMenu::item {
                color: #f4f2eb;
                background: transparent;
                padding: 8px 24px 8px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                color: #ffffff;
                background: #34432b;
            }
            QMenu::item:disabled { color: #71838c; }
            QMenu::separator {
                height: 1px;
                background: #304b56;
                margin: 5px 8px;
            }
        """)

    def _start_worker(self) -> None:
        self.worker_thread = QtCore.QThread(self)
        self.backend = AgentBackend(self.runtime)
        self.backend.moveToThread(self.worker_thread)
        self.start_requested.connect(self.backend.start_capture)
        self.stop_requested.connect(self.backend.stop_capture)
        self.poll_requested.connect(self.backend.poll)
        self.memory_requested.connect(self.backend.configure_memory)
        self.shutdown_requested.connect(self.backend.shutdown)
        self.backend.health_ready.connect(self._render_health)
        self.backend.command_finished.connect(self._command_finished)
        self.backend.command_failed.connect(self._command_failed)
        self.backend.shutdown_finished.connect(self._shutdown_finished)
        self.worker_thread.start()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        active = bool(self._health.get("active"))
        authorization = dict(
            dict(self._health.get("server") or {}).get("authorization") or {}
        )
        capture_authorized = (
            not authorization.get("required", False)
            or authorization.get("authorized") is True
        )
        self.start_button.setEnabled(not busy and not active and capture_authorized)
        self.stop_button.setEnabled(not busy and active)
        self.tray_start_action.setEnabled(not busy and not active and capture_authorized)
        self.tray_stop_action.setEnabled(not busy and active)

    @QtCore.Slot()
    def _start_clicked(self) -> None:
        if self._busy or self.backend is None:
            return
        self._set_busy(True)
        self.message.setText("Iniciando captura…")
        self.start_requested.emit()

    @QtCore.Slot()
    def _stop_clicked(self) -> None:
        if self._busy or self.backend is None:
            return
        self._set_busy(True)
        self.message.setText("Pausando captura…")
        self.stop_requested.emit()

    def _request_poll(self) -> None:
        if self._busy or self._poll_pending or self.backend is None:
            return
        self._poll_pending = True
        self.poll_requested.emit(self.auto_capture.isChecked())

    @QtCore.Slot(dict)
    def _render_health(self, health: dict) -> None:
        self._poll_pending = False
        self._health = dict(health)
        active = health.get("active") is True
        self.state_label.setText("Capturando" if active else "Ocioso")
        self.state_label.setObjectName("stateActive" if active else "stateIdle")
        self.state_label.style().unpolish(self.state_label)
        self.state_label.style().polish(self.state_label)
        self.capture_value.setText("Ligada" if active else "Desligada")
        process_count = int(health.get("client_processes") or 0)
        self.clients_value.setText(
            f"{process_count} cliente" + ("" if process_count == 1 else "s")
        )
        outbox = dict(health.get("outbox") or {})
        outbox_events = int(outbox.get("events") or 0)
        outbox_bytes = int(outbox.get("bytes") or 0)
        self.outbox_value.setText(
            f"{outbox_events:,} eventos · {outbox_bytes / 1024 / 1024:.1f} MiB".replace(",", ".")
        )
        throughput = dict(health.get("throughput") or {})
        enqueued_last_minute = int(
            throughput.get("enqueued_events_last_minute") or 0
        )
        sent_last_minute = int(
            throughput.get("sent_events_last_minute") or 0
        )
        growth_last_minute = int(
            throughput.get("outbox_growth_events_last_minute") or 0
        )
        priority_counts = dict(outbox.get("priority_counts") or {})
        self.outbox_value.setToolTip(
            (
                f"Último minuto: {enqueued_last_minute:,} enfileirados · "
                f"{sent_last_minute:,} enviados · saldo {growth_last_minute:+,}.\n"
                f"Imediatos: {int(priority_counts.get('immediate') or 0):,} · "
                f"Alta: {int(priority_counts.get('high') or 0):,} · "
                f"Tempo real: {int(priority_counts.get('realtime') or 0):,} · "
                f"Volume: {int(priority_counts.get('bulk') or 0):,}"
            ).replace(",", ".")
        )
        decoder = dict(health.get("decoder") or {})
        processed_packets = int(decoder.get("processed_packets") or 0)
        decoded_events = int(decoder.get("decoded_events") or 0)
        self.traffic_value.setText(
            f"{processed_packets:,} pacotes úteis · {decoded_events:,} eventos".replace(
                ",", "."
            )
        )
        last_decoded = _format_status_time(decoder.get("last_decoded_ns"))
        self.last_decode_value.setText(
            last_decoded or "Nenhum evento decodificado"
        )
        gap_recoveries = int(decoder.get("tcp_gap_recoveries") or 0)
        stalled_flows = int(decoder.get("stalled_tcp_flows") or 0)
        self.last_decode_value.setToolTip(
            f"Fluxos TCP recuperados: {gap_recoveries} · bloqueados agora: {stalled_flows}"
        )
        memory = dict(health.get("memory") or {})
        working_set = memory.get("working_set_bytes")
        limit_mb = int(health.get("memory_budget_mb") or 0)
        self.memory_value.setText(
            (
                f"{int(working_set) / 1024 / 1024:.0f} MiB / "
                f"{limit_mb:,} MiB"
            ).replace(",", ".")
            if working_set is not None else
            f"Limite {limit_mb:,} MiB".replace(",", ".")
        )
        self.memory_value.setToolTip(
            "Pressão detectada; estado efêmero foi reduzido."
            if memory.get("pressure") else
            "Uso atual do processo e limite escolhido."
        )
        api = dict(health.get("local_api") or {})
        self.api_value.setText(
            f"Ativa em 127.0.0.1:{int(api.get('port') or 0)}"
            if api.get("active") else "Desligada"
        )
        server = dict(health.get("server") or {})
        delivery = dict(server.get("delivery") or {})
        projection = dict(health.get("projection") or {})
        flow_sample = (
            time.monotonic(),
            int(projection.get("enqueued") or 0),
            int(delivery.get("sent_events") or 0),
            outbox_events,
        )
        generated_rate, sent_rate_second, queue_rate = _flow_rates(
            self._flow_sample, flow_sample
        )
        self._flow_sample = flow_sample
        self.flow_value.setText(
            "Gerados "
            f"{_format_event_rate(generated_rate)}/s · enviados "
            f"{_format_event_rate(sent_rate_second)}/s · fila "
            f"{_format_event_rate(queue_rate, signed=True)}/s"
        )
        self.flow_value.setToolTip(
            "A fila deve cair quando enviados/s permanecer acima de gerados/s."
        )
        last_ack = _format_status_time(delivery.get("last_ack_at"))
        self.last_ack_value.setText(
            last_ack
            or (
                "Envio desativado"
                if str(server.get("mode") or "offline") == "offline"
                else "Nenhum lote confirmado"
            )
        )
        delivery_error = delivery.get("last_error_code")
        sent_rate = int(delivery.get("sent_events_last_minute") or 0)
        last_priority = str(delivery.get("last_batch_priority") or "—")
        burst = int(delivery.get("max_burst_observed") or 0)
        self.last_ack_value.setToolTip(
            f"Último erro: {delivery_error}"
            if delivery_error else
            (
                "Horário local da última confirmação recebida do servidor.\n"
                f"Enviados no último minuto: {sent_rate:,} · "
                f"última prioridade: {last_priority} · maior rajada: {burst}"
            ).replace(",", ".")
        )
        authorization = dict(server.get("authorization") or {})
        authorization_status = str(authorization.get("status") or "")
        username = authorization.get("username")
        pairing_code = authorization.get("pairing_code")
        if authorization.get("authorized") and username:
            self.authorization_value.setText(f"Vinculado a {username}")
        elif authorization_status == "pending" and pairing_code:
            self.authorization_value.setText(f"Vincule no site · {pairing_code}")
        elif authorization_status == "revoked":
            self.authorization_value.setText("Vínculo revogado")
        elif authorization.get("required"):
            self.authorization_value.setText("Validação necessária")
        else:
            self.authorization_value.setText("Modo local")
        server_state = str(server.get("state") or "offline_shadow")
        server_labels = {
            "offline_shadow": "Modo local · envio desativado",
            "ready": "Conectado · aguardando eventos",
            "online": "Conectado · envio confirmado",
            "registration_pending": "Cadastro enviado · aguardando liberação",
            "registration_required": "Cadastro do Agent requer atenção",
            "delayed": "Servidor temporariamente indisponível",
            "storage_full": "Fila offline atingiu o limite",
            "closed": "Encerrado",
        }
        self.server_value.setText(
            server_labels.get(server_state, "Estado do servidor indisponível")
        )
        if not active and authorization.get("required") and not authorization.get("authorized"):
            self.state_label.setText("Vincular")
            self.state_label.setObjectName("stateError")
            self.state_label.style().unpolish(self.state_label)
            self.state_label.style().polish(self.state_label)
        clients = list(health.get("clients") or [])
        self.clients_list.clear()
        if clients:
            for client in clients:
                name = str(client.get("name") or "Personagem reconhecido")
                level = client.get("level")
                duration = _format_duration_seconds(
                    client.get("session_duration_seconds")
                )
                self.clients_list.addItem(
                    f"{name}"
                    + (f" · level {level}" if level is not None else "")
                    + (f" · sessão {duration}" if duration is not None else "")
                )
        else:
            self.clients_list.addItem(
                f"{process_count} conexão(ões) detectada(s)" if process_count else "Aguardando captura"
            )
        self._set_busy(self._busy)

    @QtCore.Slot(str, dict)
    def _command_finished(self, command: str, result: dict) -> None:
        messages = {
            "start": "Captura iniciada.",
            "stop": "Captura pausada.",
            "auto_start": "Cliente reconhecido; captura automática iniciada.",
            "clients_closed": "Todos os clientes fecharam; captura encerrada.",
        }
        if command == "memory":
            if result.get("applied"):
                self._pending_memory_mb = None
                self.message.setText("Limite aplicado.")
            else:
                self.message.setText(
                    "O novo limite será aplicado após pausar a captura."
                )
        else:
            self.message.setText(messages.get(command, "Agent atualizado."))
        self._set_busy(False)
        if command in {"stop", "clients_closed"} and self._pending_memory_mb:
            self.memory_requested.emit(self._pending_memory_mb)

    @QtCore.Slot(str, str)
    def _command_failed(self, command: str, message: str) -> None:
        if command == "poll":
            self._poll_pending = False
            return
        if command != "poll":
            self.message.setText(message)
            self.state_label.setText("Atenção")
            self.state_label.setObjectName("stateError")
            self.state_label.style().unpolish(self.state_label)
            self.state_label.style().polish(self.state_label)
        self._set_busy(False)

    def _preferences_changed(self) -> None:
        self.preferences["auto_capture"] = self.auto_capture.isChecked()
        self.preferences = save_agent_preferences(
            self.preferences_path, self.preferences
        )

    def _startup_changed(self, checked: bool) -> None:
        try:
            configure_agent_startup(checked)
        except Exception as error:
            self.startup.blockSignals(True)
            self.startup.setChecked(not checked)
            self.startup.blockSignals(False)
            self.message.setText(f"Não foi possível alterar a inicialização: {error}")
            return
        self.preferences["start_with_windows"] = checked
        self.preferences = save_agent_preferences(
            self.preferences_path, self.preferences
        )

    def _memory_changed(self) -> None:
        value = int(self.memory_limit.currentData())
        self._pending_memory_mb = value
        self.preferences["memory_limit_mb"] = value
        self.preferences = save_agent_preferences(
            self.preferences_path, self.preferences
        )
        if self.backend is not None:
            self.memory_requested.emit(value)

    def _copy_pairing(self) -> None:
        try:
            credentials = self.runtime.pairing_credentials()
        except Exception as error:
            self.message.setText(f"Pareamento indisponível: {error}")
            return
        text = json.dumps(credentials, ensure_ascii=False, indent=2)
        QtWidgets.QApplication.clipboard().setText(text)
        self.message.setText("Pareamento copiado. Compartilhe apenas com programas oficiais.")

    def _open_site(self) -> None:
        if not AGENT_SERVER:
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(AGENT_SERVER.rstrip("/") + "/app"))

    def _export_diagnostic(self) -> None:
        AGENT_DIAGNOSTIC_DIR.mkdir(parents=True, exist_ok=True)
        target = AGENT_DIAGNOSTIC_DIR / f"agent-diagnostic-{time.strftime('%Y%m%d-%H%M%S')}.json"
        payload = {
            "schema": "rf-qol.agent-diagnostic/v1",
            "version": APP_VERSION,
            "created_at_ns": time.time_ns(),
            "health": self._health,
        }
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.message.setText(f"Diagnóstico salvo em {target}")

    def _request_update_check(self) -> None:
        if self._update_busy or self._exiting:
            return
        self._update_busy = True
        self.update_button.setEnabled(False)
        self.update_value.setText(f"{APP_VERSION} · verificando…")
        threading.Thread(target=self._run_update_check, daemon=True).start()

    def _run_update_check(self) -> None:
        try:
            self.update_signals.state_changed.emit("Consultando canal seguro…")
            candidate = fetch_latest(
                AGENT_UPDATE_FEED,
                AGENT_UPDATE_PUBLIC_KEYS,
                channel=AGENT_UPDATE_CHANNEL,
                current_sequence=RELEASE_SEQUENCE,
            )
            if candidate is None:
                self.update_signals.state_changed.emit("Atualizado")
                return
            self.update_signals.state_changed.emit(
                f"Baixando {candidate.version}…"
            )
            candidate = download_verified(candidate, AGENT_UPDATE_DIR)
            self.update_signals.ready.emit(candidate)
        except Exception as error:
            LOG.warning("agent_update_check_failed: %s", error)
            self.update_signals.failed.emit(str(error))

    @QtCore.Slot(str)
    def _update_state_changed(self, state: str) -> None:
        if state == "Atualizado":
            self._update_busy = False
            self.update_button.setEnabled(True)
            self.update_value.setText(f"{APP_VERSION} · atualizada")
            return
        self.update_value.setText(state)

    @QtCore.Slot(str)
    def _update_failed(self, message: str) -> None:
        self._update_busy = False
        self.update_button.setEnabled(True)
        self.update_value.setText(f"{APP_VERSION} · não foi possível verificar")
        self.update_value.setToolTip(message)

    @QtCore.Slot(object)
    def _update_ready(self, candidate: UpdateCandidate) -> None:
        self._update_busy = False
        self.update_button.setEnabled(True)
        self._ready_update = candidate
        self.update_value.setText(f"{candidate.version} · pronta para instalar")
        installer = candidate.installer
        if installer is None:
            return
        answer = _build_update_confirmation_dialog(self, candidate).exec()
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            self.message.setText(
                "Atualização baixada. Use Verificar atualização quando quiser aplicar."
            )
            return
        self._pending_update_installer = installer
        self.message.setText("Encerrando o Agent para abrir o instalador…")
        self._exit_agent()

    def _show_window(self) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _tray_activated(self, reason) -> None:
        if reason in (
            QtWidgets.QSystemTrayIcon.ActivationReason.Trigger,
            QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_window()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if not self._exiting:
            event.ignore()
            if self.tray.isVisible():
                self.hide()
                self.tray.showMessage(
                    PRODUCT_NAME,
                    "O Agent continua em execução na bandeja.",
                    QtWidgets.QSystemTrayIcon.MessageIcon.Information,
                    2500,
                )
            else:
                QtCore.QTimer.singleShot(0, self._exit_agent)
            return
        event.accept()

    def _exit_agent(self) -> None:
        if self._exiting:
            return
        self._exiting = True
        self.poll_timer.stop()
        self.update_timer.stop()
        self.setEnabled(False)
        if self.backend is None:
            self.runtime.close()
            QtWidgets.QApplication.quit()
            return
        self.shutdown_requested.emit()

    @QtCore.Slot()
    def _shutdown_finished(self) -> None:
        if self.worker_thread is not None:
            self.worker_thread.quit()
            self.worker_thread.wait(3000)
        self.tray.hide()
        if self._pending_update_installer is not None:
            try:
                subprocess.Popen(
                    [str(self._pending_update_installer), "/UPDATE"],
                    close_fds=True,
                )
            except OSError as error:
                LOG.exception("agent_update_installer_launch_failed")
                QtWidgets.QMessageBox.critical(
                    self,
                    "Atualização não iniciada",
                    "Não foi possível abrir o instalador. Execute manualmente:\n"
                    f"{self._pending_update_installer}\n\n{error}",
                )
        self.close()
        QtWidgets.QApplication.quit()


def create_application(arguments: list[str] | None = None) -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(arguments or sys.argv)
    app.setApplicationName(PRODUCT_NAME)
    app.setQuitOnLastWindowClosed(False)
    for filename in ("Saira.ttf", "SairaSemiCondensed-Bold.ttf"):
        font_path = AGENT_ASSETS_DIR / filename
        if font_path.is_file():
            QtGui.QFontDatabase.addApplicationFont(str(font_path))
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
        raise RuntimeError("Não foi possível reservar a instância única do Agent.")
    app._rfqol_agent_instance_lock = lock
    return server


def _activate_from_instance_request(
    server: QtNetwork.QLocalServer,
    window: AgentWindow,
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
        window._show_window()


def _configure_logging() -> None:
    AGENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=AGENT_LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _create_runtime(preferences: dict[str, Any]) -> StandaloneWindowsAgentRuntime:
    options = {
        "memory_budget_mb": int(preferences["memory_limit_mb"]),
        "local_api_port": int(preferences["local_api_port"]),
        "max_outbox_bytes": int(preferences["storage_limit_mb"]) * 1024 * 1024,
    }
    installation_id = str(preferences["installation_id"])
    if AGENT_SERVER:
        return StandaloneWindowsAgentRuntime.create_online(
            AGENT_RUNTIME_DIR,
            installation_id,
            AGENT_SERVER,
            version=AGENT_TRANSPORT_VERSION,
            decoder_version=APP_VERSION,
            **options,
        )
    return StandaloneWindowsAgentRuntime.create_offline(
        AGENT_RUNTIME_DIR,
        installation_id,
        version=APP_VERSION,
        **options,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=PRODUCT_NAME)
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        validate_build_profile()
        if not LEVEL_CURVE or max(LEVEL_CURVE) < 100:
            raise RuntimeError("Curva de EXP obrigatória não foi carregada.")
        with tempfile.TemporaryDirectory(prefix="rf-next-companion-self-test-") as folder:
            result = run_offline_agent_self_test(
                Path(folder), str(uuid.uuid4()), version=APP_VERSION
            )
        if (
            result.get("ok") is not True
            or result.get("network_used") is not False
            or result.get("equipped_loadout_items") != 1
        ):
            raise RuntimeError("Autoteste integrado do Companion falhou.")
        return 0
    app = create_application(["rf-qol-agent"])
    instance_server = _claim_instance_server(app)
    if instance_server is None:
        return 0
    ensure_agent_layout()
    preferences = load_agent_preferences(AGENT_PREFERENCES_PATH)
    preferences = save_agent_preferences(AGENT_PREFERENCES_PATH, preferences)
    _configure_logging()
    runtime = _create_runtime(preferences)
    try:
        runtime.start_local_api()
        window = AgentWindow(
            runtime,
            preferences_path=AGENT_PREFERENCES_PATH,
            background=args.background,
        )
        instance_server.newConnection.connect(
            lambda: _activate_from_instance_request(instance_server, window)
        )
        app._rfqol_agent_instance_server = instance_server
        app.aboutToQuit.connect(lambda: window.poll_timer.stop())
        return app.exec()
    except Exception:
        runtime.close()
        raise


if __name__ == "__main__":
    raise SystemExit(main())

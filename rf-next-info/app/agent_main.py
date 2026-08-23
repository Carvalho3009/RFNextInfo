"""Entrada independente do RF QOL Agent Windows."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from app.agent_paths import (
    AGENT_ASSETS_DIR,
    AGENT_DIAGNOSTIC_DIR,
    AGENT_LOG_PATH,
    AGENT_PREFERENCES_PATH,
    AGENT_RUNTIME_DIR,
    ensure_agent_layout,
)
from app.agent_preferences import (
    configure_agent_startup,
    load_agent_preferences,
    save_agent_preferences,
)
from app.build_profile import AGENT_SERVER, APP_VERSION
from core.windows_agent_capture import StandaloneWindowsAgentRuntime


LOG = logging.getLogger("rfqol.agent")


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
            if auto_capture and has_clients and not self.runtime.active:
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
        self._pending_memory_mb: int | None = None
        self.worker_thread: QtCore.QThread | None = None
        self.backend: AgentBackend | None = None
        self.poll_timer = QtCore.QTimer(self)
        self.poll_timer.setInterval(2000)
        self.poll_timer.timeout.connect(self._request_poll)

        self.setWindowTitle(f"RF QOL Agent · {APP_VERSION}")
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
        title = QtWidgets.QLabel("RF QOL Agent", objectName="title")
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
        self.memory_value = QtWidgets.QLabel(
            "Limite 1.024 MiB", objectName="statusValue"
        )
        self.api_value = QtWidgets.QLabel("Preparando", objectName="statusValue")
        rows = (
            ("Captura", self.capture_value),
            ("Clientes", self.clients_value),
            ("Servidor", self.server_value),
            ("Fila offline", self.outbox_value),
            ("Memória", self.memory_value),
            ("API local", self.api_value),
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
        self.site_button.setEnabled(False)
        self.site_button.setToolTip("Disponível quando o servidor de homologação for configurado.")
        self.pair_button = QtWidgets.QPushButton("Copiar pareamento da API")
        self.pair_button.clicked.connect(self._copy_pairing)
        self.diagnostic_button = QtWidgets.QPushButton("Exportar diagnóstico")
        self.diagnostic_button.clicked.connect(self._export_diagnostic)
        for button in (
            self.site_button,
            self.pair_button,
            self.diagnostic_button,
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
        icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(icon)
        self.tray = QtWidgets.QSystemTrayIcon(icon, self)
        self.tray.setToolTip("RF QOL Agent")
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
        self.start_button.setEnabled(not busy and not active)
        self.stop_button.setEnabled(not busy and active)
        self.tray_start_action.setEnabled(not busy and not active)
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
        self.memory_value.setText(f"Limite {int(health.get('memory_budget_mb') or 0):,} MiB".replace(",", "."))
        api = dict(health.get("local_api") or {})
        self.api_value.setText(
            f"Ativa em 127.0.0.1:{int(api.get('port') or 0)}"
            if api.get("active") else "Desligada"
        )
        server = dict(health.get("server") or {})
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
        clients = list(health.get("clients") or [])
        self.clients_list.clear()
        if clients:
            for client in clients:
                name = str(client.get("name") or "Personagem reconhecido")
                level = client.get("level")
                self.clients_list.addItem(
                    f"{name}" + (f" · level {level}" if level is not None else "")
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
                    "RF QOL Agent",
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
        self.close()
        QtWidgets.QApplication.quit()


def create_application(arguments: list[str] | None = None) -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(arguments or sys.argv)
    app.setApplicationName("RF QOL Agent")
    app.setQuitOnLastWindowClosed(False)
    for filename in ("Saira.ttf", "SairaSemiCondensed-Bold.ttf"):
        font_path = AGENT_ASSETS_DIR / filename
        if font_path.is_file():
            QtGui.QFontDatabase.addApplicationFont(str(font_path))
    return app


def _configure_logging() -> None:
    AGENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=AGENT_LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _create_runtime(preferences: dict[str, Any]) -> StandaloneWindowsAgentRuntime:
    options = {
        "version": APP_VERSION,
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
            **options,
        )
    return StandaloneWindowsAgentRuntime.create_offline(
        AGENT_RUNTIME_DIR,
        installation_id,
        **options,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="RF QOL Agent")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return 0
    ensure_agent_layout()
    preferences = load_agent_preferences(AGENT_PREFERENCES_PATH)
    preferences = save_agent_preferences(AGENT_PREFERENCES_PATH, preferences)
    _configure_logging()
    runtime = _create_runtime(preferences)
    try:
        runtime.start_local_api()
        app = create_application(["rf-qol-agent"])
        window = AgentWindow(
            runtime,
            preferences_path=AGENT_PREFERENCES_PATH,
            background=args.background,
        )
        app.aboutToQuit.connect(lambda: window.poll_timer.stop())
        return app.exec()
    except Exception:
        runtime.close()
        raise


if __name__ == "__main__":
    raise SystemExit(main())

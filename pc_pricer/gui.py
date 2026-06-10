"""PySide6 GUI entry point."""

from __future__ import annotations

from copy import deepcopy
import html
import json
import os
import sys
from pathlib import Path
from typing import Any

from pc_pricer.batch import (
    BatchItem,
    batch_item_summary,
    batch_summary_rows,
    load_batch_csv,
    safe_batch_filename,
    validate_batch_items,
    write_batch_summary_csv,
)
from pc_pricer.detector import detect_specs
from pc_pricer.env_loader import default_env_path, load_env_file
from pc_pricer.gui_forms import (
    DEVICE_TYPES,
    FieldSpec,
    fields_for_device,
    option_label,
    validate_computer_mode,
    validate_device_type,
    validate_specs,
)
from pc_pricer.gui_pricing import build_gui_manufacturer_lookup, price_gui_values
from pc_pricer.gui_source_settings import load_source_settings, save_source_settings
from pc_pricer.pricing_pipeline import reprice_existing_result
from pc_pricer.reporter import (
    FILTER_LABELS,
    FLAG_LABELS,
    LIMITATION_LABELS,
    WARNING_LABELS,
    format_condition,
    format_listing_price,
    format_location,
    format_price_report,
)
from pc_pricer.source_labels import (
    format_cpu_value as _format_cpu_value,
    format_source_basis as _source_basis_label,
    format_source_name as _source_name_label,
)
from pc_pricer.setup_credentials import write_credentials_env
from pc_pricer.spec_builder import gui_values_from_detected_specs

LOADING_DELAY_MS = 700


class _MissingSignal:
    def connect(self, *_args: Any) -> None:
        pass

    def emit(self, *_args: Any) -> None:
        pass


try:  # pragma: no cover - exercised only when PySide6 is installed.
    from PySide6.QtCore import QThread, Qt, QTimer, Signal  # type: ignore[import-not-found]
    from PySide6.QtGui import QTextDocument  # type: ignore[import-not-found]
    from PySide6.QtPrintSupport import QPrintDialog, QPrinter  # type: ignore[import-not-found]
    from PySide6.QtWidgets import (  # type: ignore[import-not-found]
        QApplication,
        QAbstractItemView,
        QButtonGroup,
        QCheckBox,
        QComboBox,
        QDialog,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QRadioButton,
        QScrollArea,
        QStackedWidget,
        QTableWidget,
        QTableWidgetItem,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError:  # pragma: no cover - gives a clear runtime error.
    QApplication = None  # type: ignore[assignment]
    QThread = object  # type: ignore[assignment]
    QAbstractItemView = object  # type: ignore[assignment]
    QButtonGroup = QCheckBox = QComboBox = QDialog = QFormLayout = QFrame = QHBoxLayout = QLabel = object  # type: ignore[assignment]
    QFileDialog = QGridLayout = QHeaderView = QLineEdit = QMainWindow = QMessageBox = QPushButton = QRadioButton = object  # type: ignore[assignment]
    QPrintDialog = QPrinter = QScrollArea = QStackedWidget = QTextDocument = QToolButton = QVBoxLayout = QWidget = object  # type: ignore[assignment]
    QTableWidget = QTableWidgetItem = object  # type: ignore[assignment]
    Qt = type(
        "Qt",
        (),
        {
            "AlignCenter": 0,
            "AlignRight": 0,
            "AlignTop": 0,
            "LinksAccessibleByMouse": 0,
            "NoFocus": 0,
            "TextSelectableByMouse": 0,
        },
    )  # type: ignore[assignment]
    QTimer = type("QTimer", (), {"singleShot": staticmethod(lambda *_args: None)})  # type: ignore[assignment]

    def Signal(*_args: Any) -> _MissingSignal:  # type: ignore[assignment]
        return _MissingSignal()


class GuiState:
    def __init__(self) -> None:
        self.device_type: str | None = None
        self.computer_mode: str | None = None
        self.specs: dict[str, Any] = {}
        self.report_result: dict[str, Any] = {}
        self.base_report_result: dict[str, Any] = {}
        self.report_text: str = ""
        self.report_error: str = ""
        self.report_mode: str = "standard"
        self.pending_excluded_comparable_ids: set[str] = set()
        self.applied_excluded_comparable_ids: set[str] = set()
        self.source_settings: dict[str, bool] = load_source_settings()
        self.batch_items: list[dict[str, Any]] = []
        self.batch_source_path: str = ""
        self.current_batch_index: int | None = None


class StableComboBox(QComboBox):  # type: ignore[misc]
    def wheelEvent(self, event: Any) -> None:
        if self.view().isVisible():
            super().wheelEvent(event)
            return
        event.ignore()


class PricingThread(QThread):  # type: ignore[misc]
    completed = Signal(dict, str)
    failed = Signal(str)

    def __init__(self, device_type: str, specs: dict[str, Any], parent: QWidget | None = None) -> None:  # type: ignore[misc]
        super().__init__(parent)
        self.device_type = device_type
        self.specs = deepcopy(specs)

    def run(self) -> None:
        try:
            result, report = price_gui_values(self.device_type, self.specs)
        except RuntimeError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - defensive GUI boundary.
            self.failed.emit(f"Unexpected pricing error: {exc}")
        else:
            self.completed.emit(result, report)


class BatchPricingThread(QThread):  # type: ignore[misc]
    item_started = Signal(int)
    item_completed = Signal(int, dict, str)
    item_failed = Signal(int, str)
    completed = Signal()

    def __init__(self, items: list[dict[str, Any]], parent: QWidget | None = None) -> None:  # type: ignore[misc]
        super().__init__(parent)
        self.items = deepcopy(items)
        self.manufacturer_lookup = build_gui_manufacturer_lookup()

    def run(self) -> None:
        for index, item in enumerate(self.items):
            if item.get("errors") or item.get("status") == "Complete":
                continue
            self.item_started.emit(index)
            try:
                result, report = price_gui_values(
                    item.get("device_type") or "computer",
                    item.get("values") or {},
                    manufacturer_lookup=self.manufacturer_lookup,
                    build_lookup=False,
                )
            except RuntimeError as exc:
                self.item_failed.emit(index, str(exc))
            except Exception as exc:  # pragma: no cover - defensive GUI boundary.
                self.item_failed.emit(index, f"Unexpected pricing error: {exc}")
            else:
                self.item_completed.emit(index, result, report)
        self.completed.emit()


class DetectionThread(QThread):  # type: ignore[misc]
    completed = Signal(dict)
    failed = Signal(str)

    def run(self) -> None:
        try:
            specs = detect_specs()
        except RuntimeError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - defensive GUI boundary.
            self.failed.emit(f"Unexpected auto-detect error: {exc}")
        else:
            self.completed.emit(specs)


class MainWindow(QMainWindow):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CFS Price Compare")
        self.resize(940, 680)
        self.state = GuiState()
        self.pricing_thread: PricingThread | None = None
        self.batch_pricing_thread: BatchPricingThread | None = None
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.source_page = SourceSelectionPage(self)
        self.credentials_page = CredentialsPage(self)
        self.device_page = DeviceTypePage(self)
        self.computer_mode_page = ComputerModePage(self)
        self.specs_page = SpecsPage(self)
        self.loading_page = LoadingPage(self)
        self.batch_page = BatchPage(self)
        self.report_page = ReportPage(self)

        for page in [
            self.source_page,
            self.credentials_page,
            self.device_page,
            self.computer_mode_page,
            self.specs_page,
            self.loading_page,
            self.batch_page,
            self.report_page,
        ]:
            self.stack.addWidget(page)

        load_env_file(override=True)
        self.show_source_selection()

    def show_source_selection(self) -> None:
        self.source_page.refresh()
        self.stack.setCurrentWidget(self.source_page)

    def continue_after_source_selection(self) -> None:
        if self.state.source_settings.get("ebay", True) and not credentials_present():
            self.show_credentials()
            return
        self.show_device_type()

    def show_credentials(self) -> None:
        self.credentials_page.refresh()
        self.stack.setCurrentWidget(self.credentials_page)

    def show_device_type(self) -> None:
        self.device_page.refresh()
        self.stack.setCurrentWidget(self.device_page)

    def show_batch(self) -> None:
        self.batch_page.refresh()
        self.stack.setCurrentWidget(self.batch_page)

    def show_computer_mode(self) -> None:
        self.computer_mode_page.refresh()
        self.stack.setCurrentWidget(self.computer_mode_page)

    def show_specs(self) -> None:
        self.specs_page.refresh()
        self.stack.setCurrentWidget(self.specs_page)

    def show_loading(self) -> None:
        self.loading_page.refresh()
        self.stack.setCurrentWidget(self.loading_page)
        QTimer.singleShot(LOADING_DELAY_MS, self.price_current_specs)

    def price_current_specs(self) -> None:
        if self.pricing_thread is not None:
            return

        self.pricing_thread = PricingThread(
            self.state.device_type or "computer",
            self.state.specs,
            self,
        )
        self.pricing_thread.completed.connect(self.pricing_succeeded)
        self.pricing_thread.failed.connect(self.pricing_failed)
        self.pricing_thread.finished.connect(self.pricing_finished)
        self.pricing_thread.finished.connect(self.pricing_thread.deleteLater)
        self.pricing_thread.start()

    def pricing_succeeded(self, result: dict[str, Any], report: str) -> None:
        self.state.base_report_result = result
        self.state.report_result = result
        self.state.report_text = report
        self.state.report_error = ""
        self.state.report_mode = "standard"
        self.state.pending_excluded_comparable_ids = set()
        self.state.applied_excluded_comparable_ids = set()
        self._save_current_report_to_batch()
        self.show_report()

    def pricing_failed(self, message: str) -> None:
        self.state.report_result = {}
        self.state.report_text = ""
        self.state.report_error = message
        self._save_current_report_to_batch()
        self.show_report()

    def pricing_finished(self) -> None:
        self.pricing_thread = None

    def show_report(self) -> None:
        self.report_page.refresh()
        self.stack.setCurrentWidget(self.report_page)

    def import_batch_csv(self) -> None:
        if self.batch_pricing_thread is not None:
            return
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Import Batch CSV",
            "",
            "CSV files (*.csv);;All files (*.*)",
        )
        if not path:
            return
        self.load_batch_csv(path)

    def load_batch_csv(self, path: str) -> None:
        if self.batch_pricing_thread is not None:
            return
        try:
            items = load_batch_csv(path)
        except RuntimeError as exc:
            QMessageBox.warning(self, "Batch import failed", str(exc))
            return
        self.state.batch_source_path = path
        self.state.batch_items = [_gui_batch_item(item) for item in items]
        self.state.current_batch_index = None
        self.batch_page.edit_mode = False
        self.show_batch()

    def start_batch_pricing(self) -> None:
        if self.batch_pricing_thread is not None:
            return
        invalid_count = sum(1 for item in self.state.batch_items if item.get("errors"))
        if invalid_count:
            QMessageBox.warning(
                self,
                "Fix invalid rows",
                f"Fix or remove {invalid_count} invalid row(s) before starting the batch.",
            )
            return
        if not self.state.batch_items:
            QMessageBox.information(self, "No batch loaded", "Import a batch CSV first.")
            return

        self.batch_pricing_thread = BatchPricingThread(self.state.batch_items, self)
        self.batch_pricing_thread.item_started.connect(self.batch_item_started)
        self.batch_pricing_thread.item_completed.connect(self.batch_item_completed)
        self.batch_pricing_thread.item_failed.connect(self.batch_item_failed)
        self.batch_pricing_thread.completed.connect(self.batch_pricing_completed)
        self.batch_pricing_thread.finished.connect(self.batch_pricing_finished)
        self.batch_pricing_thread.finished.connect(self.batch_pricing_thread.deleteLater)
        self.batch_pricing_thread.start()
        self.batch_page.refresh()

    def batch_item_started(self, index: int) -> None:
        item = self._batch_item(index)
        if item is None:
            return
        item["status"] = "Running"
        item["error"] = ""
        self.batch_page.refresh()

    def batch_item_completed(self, index: int, result: dict[str, Any], report: str) -> None:
        item = self._batch_item(index)
        if item is None:
            return
        item["result"] = result
        item["base_result"] = result
        item["report_text"] = report
        item["error"] = ""
        item["report_mode"] = "standard"
        item["pending_excluded_comparable_ids"] = set()
        item["applied_excluded_comparable_ids"] = set()
        item["status"] = _batch_success_status(result)
        self.batch_page.refresh()

    def batch_item_failed(self, index: int, message: str) -> None:
        item = self._batch_item(index)
        if item is None:
            return
        item["status"] = "Failed"
        item["error"] = message
        self.batch_page.refresh()

    def batch_pricing_completed(self) -> None:
        self.batch_page.refresh()

    def batch_pricing_finished(self) -> None:
        self.batch_pricing_thread = None
        self.batch_page.refresh()

    def open_batch_report(self, index: int) -> None:
        item = self._batch_item(index)
        if item is None:
            return
        self.state.current_batch_index = index
        self.state.device_type = item.get("device_type") or "computer"
        self.state.specs = dict(item.get("values") or {})
        self.state.base_report_result = item.get("base_result") or item.get("result") or {}
        self.state.report_result = item.get("result") or {}
        self.state.report_text = item.get("report_text") or ""
        self.state.report_error = item.get("error") or ""
        self.state.report_mode = item.get("report_mode") or "standard"
        self.state.pending_excluded_comparable_ids = set(item.get("pending_excluded_comparable_ids") or set())
        self.state.applied_excluded_comparable_ids = set(item.get("applied_excluded_comparable_ids") or set())
        self.show_report()

    def edit_batch_item(self, index: int) -> None:
        if self.batch_pricing_thread is not None:
            return
        item = self._batch_item(index)
        if item is None:
            return
        if item.get("device_type") not in DEVICE_TYPES:
            QMessageBox.warning(self, "Invalid device type", "Remove this row or fix the device_type in the CSV and import it again.")
            return
        self.state.current_batch_index = index
        self.state.device_type = item.get("device_type") or "computer"
        self.state.computer_mode = "manual" if self.state.device_type == "computer" else None
        self.state.specs = dict(item.get("values") or {})
        self.show_specs()

    def save_edited_batch_item(self) -> bool:
        index = self.state.current_batch_index
        item = self._batch_item(index)
        if item is None:
            return False
        updated = BatchItem(
            row_number=int(item.get("row_number") or index + 2),
            item_id=str(item.get("item_id") or ""),
            device_type=self.state.device_type or item.get("device_type") or "computer",
            values=dict(self.state.specs),
        )
        validated = validate_batch_items([updated])[0]
        item.update(_gui_batch_item(validated))
        if item.get("errors"):
            return False
        item["status"] = "Ready"
        item["result"] = {}
        item["base_result"] = {}
        item["report_text"] = ""
        item["error"] = ""
        return True

    def _save_current_report_to_batch(self) -> None:
        item = self._batch_item(self.state.current_batch_index)
        if item is None:
            return
        item["result"] = self.state.report_result
        item["base_result"] = self.state.base_report_result
        item["report_text"] = self.state.report_text
        item["error"] = self.state.report_error
        item["report_mode"] = self.state.report_mode
        item["pending_excluded_comparable_ids"] = set(self.state.pending_excluded_comparable_ids)
        item["applied_excluded_comparable_ids"] = set(self.state.applied_excluded_comparable_ids)
        if self.state.report_error:
            item["status"] = "Failed"
        elif self.state.report_result:
            item["status"] = _batch_success_status(self.state.report_result)

    def _batch_item(self, index: int | None) -> dict[str, Any] | None:
        if index is None:
            return None
        if index < 0 or index >= len(self.state.batch_items):
            return None
        return self.state.batch_items[index]

    def reset_for_new_device(self) -> None:
        self.state = GuiState()
        self.show_source_selection()

    def closeEvent(self, event: Any) -> None:
        if self.pricing_thread is not None and self.pricing_thread.isRunning():
            QMessageBox.information(
                self,
                "Pricing in progress",
                "Wait for the current price search to finish before closing.",
            )
            event.ignore()
            return
        if self.batch_pricing_thread is not None and self.batch_pricing_thread.isRunning():
            QMessageBox.information(
                self,
                "Batch pricing in progress",
                "Wait for the current batch run to finish before closing.",
            )
            event.ignore()
            return
        super().closeEvent(event)


class Page(QWidget):  # type: ignore[misc]
    def __init__(self, window: MainWindow, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.main_window = window
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(34, 28, 34, 28)
        self.root.setSpacing(18)

        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        self.root.addWidget(heading)

        if subtitle:
            subheading = QLabel(subtitle)
            subheading.setWordWrap(True)
            subheading.setObjectName("pageSubtitle")
            self.root.addWidget(subheading)

    def refresh(self) -> None:
        pass


class SourceSelectionPage(Page):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(
            window,
            "Pricing Sources",
            "Choose where the app should search before entering device details.",
        )
        self.source_checks: dict[str, QCheckBox] = {}
        self.error = QLabel()
        self.error.setObjectName("errorText")
        self.error.setWordWrap(True)

        self.root.addWidget(self._source_panel())
        self.root.addWidget(self.error)
        self.root.addStretch()
        self.root.addLayout(nav_row(None, None, "Next", self.next_page))

    def refresh(self) -> None:
        self.error.clear()
        self.main_window.state.source_settings = load_source_settings()
        for source, checkbox in self.source_checks.items():
            checkbox.setChecked(self.main_window.state.source_settings.get(source, source != "amazon_renewed"))

    def next_page(self) -> None:
        errors = self._store_source_settings()
        if errors:
            self.error.setText(" ".join(errors))
            return
        self.main_window.continue_after_source_selection()

    def _source_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("sectionPanel")
        panel.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setSpacing(6)

        labels = {
            "ebay": "eBay",
            "refurb_io": "Refurb.io",
            "amazon_renewed": "Amazon Renewed (experimental)",
        }
        for source, label in labels.items():
            checkbox = QCheckBox(label)
            self.source_checks[source] = checkbox
            layout.addWidget(checkbox)

        note = _selectable_label(
            "eBay requires API credentials. Amazon Renewed uses browser automation through Microsoft Edge in the background when enabled."
        )
        note.setObjectName("statusText")
        note.setWordWrap(True)
        layout.addWidget(note)
        return panel

    def _store_source_settings(self) -> list[str]:
        settings = {source: checkbox.isChecked() for source, checkbox in self.source_checks.items()}
        if not any(settings.values()):
            return ["Enable at least one pricing source."]
        self.main_window.state.source_settings = save_source_settings(settings)
        return []


class CredentialsPage(Page):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(
            window,
            "eBay Credentials",
            "Enter the Production App ID and Cert ID from eBay Developer. These are saved locally in .env.",
        )
        self.client_id = QLineEdit()
        self.client_secret = QLineEdit()
        self.client_secret.setEchoMode(QLineEdit.Password)
        self.status = QLabel()
        self.status.setObjectName("statusText")

        form = QFormLayout()
        form.addRow("App ID / Client ID *", self.client_id)
        form.addRow("Cert ID / Client Secret *", self.client_secret)
        self.root.addLayout(form)
        self.root.addWidget(self.status)
        self.root.addStretch()

        buttons = QHBoxLayout()
        back = QPushButton("Back")
        back.clicked.connect(self.main_window.show_source_selection)
        save = QPushButton("Save and Continue")
        save.clicked.connect(self.save_and_continue)
        buttons.addWidget(back)
        buttons.addStretch()
        buttons.addWidget(save)
        self.root.addLayout(buttons)

    def refresh(self) -> None:
        self.status.setText(f"Credential file: {default_env_path()}")

    def save_and_continue(self) -> None:
        client_id = self.client_id.text().strip()
        client_secret = self.client_secret.text().strip()
        if not client_id or not client_secret:
            QMessageBox.warning(self, "Missing credentials", "Enter both eBay credential values.")
            return

        write_credentials_env(default_env_path(), client_id, client_secret)
        os.environ["EBAY_CLIENT_ID"] = client_id
        os.environ["EBAY_CLIENT_SECRET"] = client_secret
        self.main_window.show_device_type()


class DeviceTypePage(Page):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(window, "Device Type", "Choose the kind of device you want to price.")
        self.group = QButtonGroup(self)
        grid = QVBoxLayout()
        for device_type in DEVICE_TYPES:
            radio = QRadioButton(device_type.replace("-", " ").title())
            radio.setProperty("device_type", device_type)
            self.group.addButton(radio)
            grid.addWidget(radio)
        self.root.addLayout(grid)
        self.error = QLabel()
        self.error.setObjectName("errorText")
        self.root.addWidget(self.error)
        self.root.addStretch()
        buttons = QHBoxLayout()
        back = QPushButton("Back")
        back.clicked.connect(self.main_window.show_source_selection)
        batch = QPushButton("Import Batch CSV")
        batch.clicked.connect(self.main_window.import_batch_csv)
        next_button = QPushButton("Next")
        next_button.clicked.connect(self.next_page)
        buttons.addWidget(back)
        buttons.addStretch()
        buttons.addWidget(batch)
        buttons.addWidget(next_button)
        self.root.addLayout(buttons)

    def refresh(self) -> None:
        self.error.clear()
        for button in self.group.buttons():
            if button.property("device_type") == self.main_window.state.device_type:
                button.setChecked(True)

    def next_page(self) -> None:
        checked = self.group.checkedButton()
        self.main_window.state.device_type = checked.property("device_type") if checked else None
        errors = validate_device_type(self.main_window.state.device_type)
        if errors:
            self.error.setText(errors[0])
            return
        if self.main_window.state.device_type == "computer":
            self.main_window.show_computer_mode()
        else:
            self.main_window.state.computer_mode = None
            self.main_window.show_specs()


class BatchPage(Page):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(
            window,
            "Batch Pricing",
            "Import a CSV, fix invalid rows, then run devices in order. Completed reports stay in this batch view.",
        )
        self.edit_mode = False

        top_actions = QHBoxLayout()
        top_actions.addStretch()
        self.import_button = QPushButton("Import CSV")
        self.import_button.clicked.connect(self.main_window.import_batch_csv)
        self.start_button = QPushButton("Start / Continue")
        self.start_button.clicked.connect(self.main_window.start_batch_pricing)
        top_actions.addWidget(self.import_button)
        top_actions.addWidget(self.start_button)
        self.root.addLayout(top_actions)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Order", "Device", "Summary", "Status", "Issue", "Action"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.cellDoubleClicked.connect(lambda row, _column: self.view_selected(row))
        self.root.addWidget(self.table, 1)

        self.status_panel = QFrame()
        self.status_panel.setObjectName("sectionPanel")
        self.status_panel.setFrameShape(QFrame.StyledPanel)
        self.status_layout = QGridLayout(self.status_panel)
        self.status_layout.setColumnStretch(1, 1)
        self.status_layout.setHorizontalSpacing(12)
        self.status_layout.setVerticalSpacing(6)
        self.root.addWidget(self.status_panel)

        row = QHBoxLayout()
        self.edit_button = QPushButton("Edit Batch")
        self.edit_button.clicked.connect(self.toggle_edit_mode)
        self.view_button = QPushButton("View All Reports")
        self.view_button.clicked.connect(self.view_all_reports)
        self.print_all_button = QPushButton("Print All")
        self.print_all_button.clicked.connect(self.print_all_reports)
        self.export_all_button = QPushButton("Export All")
        self.export_all_button.clicked.connect(self.export_all_reports)
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.main_window.show_device_type)

        row.addWidget(self.back_button)
        row.addStretch()
        row.addWidget(self.edit_button)
        row.addWidget(self.view_button)
        row.addWidget(self.print_all_button)
        row.addWidget(self.export_all_button)
        self.root.addLayout(row)

    def refresh(self) -> None:
        items = self.main_window.state.batch_items
        self.table.clearContents()
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            values = item.get("values") or {}
            cells = [
                _batch_order_label(row, item),
                _display_value(item.get("device_type"), "device_type"),
                batch_item_summary(values),
                str(item.get("status") or "Ready"),
                _batch_issue_text(item),
                "",
            ]
            for column, value in enumerate(cells):
                cell = QTableWidgetItem(value)
                self.table.setItem(row, column, cell)
            self.table.setCellWidget(row, 5, self._row_action_widget(row, item))
        self.table.resizeRowsToContents()
        self._refresh_status_panel(items)
        self._sync_controls()

    def view_selected(self, row: int | None = None) -> None:
        index = self._selected_index(row)
        if index is None:
            return
        item = self.main_window.state.batch_items[index]
        if not item.get("result") and not item.get("error"):
            QMessageBox.information(self, "No report yet", "Run this row before opening its report.")
            return
        self.main_window.open_batch_report(index)

    def view_all_reports(self) -> None:
        if not self._all_rows_reportable():
            return
        for index, item in enumerate(self.main_window.state.batch_items):
            if item.get("result") or item.get("error"):
                self.main_window.open_batch_report(index)
                return

    def edit_selected(self, row: int | None = None) -> None:
        index = self._selected_index(row)
        if index is not None:
            self.main_window.edit_batch_item(index)

    def delete_row(self, row: int) -> None:
        if self._batch_is_running():
            return
        if row < 0 or row >= len(self.main_window.state.batch_items):
            return
        del self.main_window.state.batch_items[row]
        if self.main_window.state.current_batch_index == row:
            self.main_window.state.current_batch_index = None
        elif self.main_window.state.current_batch_index is not None and self.main_window.state.current_batch_index > row:
            self.main_window.state.current_batch_index -= 1
        self.refresh()

    def toggle_edit_mode(self) -> None:
        if self._batch_is_running():
            return
        self.edit_mode = not self.edit_mode
        self.refresh()

    def print_all_reports(self) -> None:
        if self._batch_is_running():
            return
        reports = self._completed_report_texts()
        if not reports:
            QMessageBox.information(self, "No reports to print", "Run at least one batch row before printing.")
            return
        printer = QPrinter()
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QDialog.Accepted:
            return
        document = QTextDocument()
        document.setHtml(_printable_report_html("\n\n".join(reports), title="CFS Batch Price Reports"))
        document.print_(printer)

    def export_all_reports(self) -> None:
        if self._batch_is_running():
            return
        completed = [item for item in self.main_window.state.batch_items if item.get("result") or item.get("error")]
        if not completed:
            QMessageBox.information(self, "No reports to export", "Run at least one batch row before exporting.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Export Batch Reports")
        if not folder:
            return
        output_dir = Path(folder)
        report_dir = output_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        export_items = []
        for index, item in enumerate(self.main_window.state.batch_items, start=1):
            export_item = _serializable_batch_item(item)
            if item.get("report_text"):
                report_path = report_dir / f"{index:03d}_{safe_batch_filename(item.get('item_id'))}.txt"
                report_path.write_text(str(item.get("report_text") or ""), encoding="utf-8")
                export_item["report_path"] = str(report_path)
            export_items.append(export_item)
        write_batch_summary_csv(output_dir / "batch_summary.csv", batch_summary_rows(export_items))
        (output_dir / "batch_results.json").write_text(json.dumps(export_items, indent=2, default=str), encoding="utf-8")
        QMessageBox.information(self, "Batch exported", f"Exported batch reports to:\n{output_dir}")

    def _completed_report_texts(self) -> list[str]:
        reports = []
        for item in self.main_window.state.batch_items:
            if item.get("report_text"):
                reports.append(str(item.get("report_text")))
        return reports

    def _selected_index(self, row: int | None = None) -> int | None:
        index = row if row is not None else self.table.currentRow()
        if index is None or index < 0 or index >= len(self.main_window.state.batch_items):
            QMessageBox.information(self, "Select a row", "Select a batch row first.")
            return None
        return index

    def _row_action_widget(self, row: int, item: dict[str, Any]) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addStretch()
        if self.edit_mode:
            edit = QPushButton("Edit")
            edit.clicked.connect(lambda _checked=False, row_index=row: self.edit_selected(row_index))
            delete = QPushButton("Delete")
            delete.clicked.connect(lambda _checked=False, row_index=row: self.delete_row(row_index))
            edit.setEnabled(not self._batch_is_running())
            delete.setEnabled(not self._batch_is_running())
            layout.addWidget(edit)
            layout.addWidget(delete)
        else:
            open_button = QPushButton("Open Report")
            open_button.clicked.connect(lambda _checked=False, row_index=row: self.view_selected(row_index))
            open_button.setEnabled(bool(item.get("result") or item.get("error")))
            open_button.setToolTip("Open this row's report." if open_button.isEnabled() else "Run this row before opening its report.")
            layout.addWidget(open_button)
        return container

    def _refresh_status_panel(self, items: list[dict[str, Any]]) -> None:
        clear_layout(self.status_layout)
        if not items:
            self._add_status_row(0, "File", "No batch CSV loaded.", "statusText")
            return
        counts: dict[str, int] = {}
        for item in items:
            status = str(item.get("status") or "Ready")
            counts[status] = counts.get(status, 0) + 1
        self._add_status_row(0, "File", self.main_window.state.batch_source_path or "Imported batch", "statusText")
        self._add_status_row(1, "Rows", str(len(items)), "statusText")
        status_order = [
            ("Ready", "Ready"),
            ("Running", "Running"),
            ("Complete", "Complete"),
            ("Needs Review", "Needs Review"),
            ("Failed", "Failed"),
            ("Invalid", "Invalid"),
        ]
        row = 2
        for status, label in status_order:
            count = counts.get(status, 0)
            if count:
                self._add_status_row(row, label, str(count), _batch_status_object_name(status))
                row += 1

    def _add_status_row(self, row: int, label: str, value: str, object_name: str) -> None:
        label_widget = _selectable_label(label)
        label_widget.setObjectName("detailLabel")
        value_widget = _selectable_label(value)
        value_widget.setObjectName(object_name)
        value_widget.setWordWrap(True)
        self.status_layout.addWidget(label_widget, row, 0)
        self.status_layout.addWidget(value_widget, row, 1)

    def _sync_controls(self) -> None:
        running = self._batch_is_running()
        has_items = bool(self.main_window.state.batch_items)
        has_finished = any(
            item.get("result") or item.get("error")
            for item in self.main_window.state.batch_items
        )
        self.import_button.setEnabled(not running)
        self.start_button.setEnabled(not running and has_items)
        self.edit_button.setEnabled(not running and has_items)
        self.back_button.setEnabled(not running)
        self.edit_button.setText("Done Editing" if self.edit_mode else "Edit Batch")
        self.view_button.setEnabled(self._all_rows_reportable())
        self.print_all_button.setEnabled(not running and has_finished)
        self.export_all_button.setEnabled(not running and has_finished)

    def _batch_is_running(self) -> bool:
        thread = self.main_window.batch_pricing_thread
        return bool(thread is not None and thread.isRunning())

    def _all_rows_reportable(self) -> bool:
        items = self.main_window.state.batch_items
        return bool(items) and all(item.get("result") or item.get("error") for item in items)


class ComputerModePage(Page):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(
            window,
            "Computer Input",
            "Choose whether to auto-detect this Windows PC or enter specs manually.",
        )
        self.detect_thread: DetectionThread | None = None
        self.group = QButtonGroup(self)
        auto = QRadioButton("Auto-detect this PC")
        auto.setProperty("mode", "auto")
        manual = QRadioButton("Enter specs manually")
        manual.setProperty("mode", "manual")
        self.group.addButton(auto)
        self.group.addButton(manual)
        self.root.addWidget(auto)
        self.root.addWidget(manual)
        self.note = QLabel("Auto-detect will prefill editable specs before pricing.")
        self.note.setObjectName("statusText")
        self.root.addWidget(self.note)
        self.error = QLabel()
        self.error.setObjectName("errorText")
        self.root.addWidget(self.error)
        self.root.addStretch()
        self.root.addLayout(nav_row("Back", self.main_window.show_device_type, "Next", self.next_page))

    def refresh(self) -> None:
        self.error.clear()
        for button in self.group.buttons():
            if button.property("mode") == self.main_window.state.computer_mode:
                button.setChecked(True)

    def next_page(self) -> None:
        checked = self.group.checkedButton()
        self.main_window.state.computer_mode = checked.property("mode") if checked else None
        errors = validate_computer_mode(self.main_window.state.computer_mode)
        if errors:
            self.error.setText(errors[0])
            return
        if self.main_window.state.computer_mode == "auto":
            self.start_detection()
            return
        self.main_window.show_specs()

    def start_detection(self) -> None:
        if self.detect_thread is not None:
            return

        self.error.setText("Detecting specs...")
        self.detect_thread = DetectionThread(self)
        self.detect_thread.completed.connect(self.detection_succeeded)
        self.detect_thread.failed.connect(self.detection_failed)
        self.detect_thread.finished.connect(self.detection_finished)
        self.detect_thread.finished.connect(self.detect_thread.deleteLater)
        self.detect_thread.start()

    def detection_succeeded(self, detected: dict[str, Any]) -> None:
        condition = self.main_window.state.specs.get("condition")
        self.main_window.state.specs = gui_values_from_detected_specs(detected)
        self.main_window.state.specs["input_method"] = "detected"
        if condition:
            self.main_window.state.specs["condition"] = condition
        self.main_window.show_specs()

    def detection_failed(self, message: str) -> None:
        self.error.setText(message)

    def detection_finished(self) -> None:
        self.detect_thread = None


class SpecsPage(Page):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(
            window,
            "Device Specs",
            "Required fields are marked with *. Optional fields improve matching when known.",
        )
        self.form_container = QWidget()
        self.form = QFormLayout(self.form_container)
        self.inputs: dict[str, QWidget] = {}
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.form_container)
        self.root.addWidget(scroll, 1)
        self.error = QLabel()
        self.error.setObjectName("errorText")
        self.error.setWordWrap(True)
        self.root.addWidget(self.error)
        self.root.addLayout(nav_row("Back", self.back_page, "Price", self.price))

    def refresh(self) -> None:
        clear_form(self.form)
        self.inputs.clear()
        self.error.clear()
        device_type = self.main_window.state.device_type or "computer"
        for field in fields_for_device(device_type):
            widget = field_widget(field, self.main_window.state.specs.get(field.name))
            self.inputs[field.name] = widget
            suffix = " *" if field.required else ""
            self.form.addRow(f"{field.label}{suffix}", widget)

        if device_type == "computer" and self.main_window.state.computer_mode == "auto":
            self.error.setText("Auto-detected specs are editable before pricing.")

    def back_page(self) -> None:
        self._store_values()
        if self.main_window.state.device_type == "computer":
            self.main_window.show_computer_mode()
        else:
            self.main_window.show_device_type()

    def price(self) -> None:
        self._store_values()
        device_type = self.main_window.state.device_type or "computer"
        errors = validate_specs(device_type, self.main_window.state.specs)
        if errors:
            self.error.setText(" ".join(errors))
            return
        if self.main_window.state.current_batch_index is not None and not self.main_window.save_edited_batch_item():
            item = self.main_window._batch_item(self.main_window.state.current_batch_index)
            item_errors = item.get("errors") if item else []
            self.error.setText(" ".join(item_errors or ["Fix this batch row before pricing."]))
            return
        self.main_window.show_loading()

    def _store_values(self) -> None:
        values = {
            name: widget_value(widget)
            for name, widget in self.inputs.items()
            if widget_value(widget) != ""
        }
        if (
            self.main_window.state.device_type == "computer"
            and self.main_window.state.computer_mode == "auto"
            and self.main_window.state.specs.get("input_method") == "detected"
        ):
            values["input_method"] = "detected"
        self.main_window.state.specs = values


class LoadingPage(Page):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(window, "Searching", "Searching configured pricing sources and preparing the price report.")
        self.message = QLabel()
        self.message.setAlignment(Qt.AlignCenter)
        self.root.addStretch()
        self.root.addWidget(self.message)
        self.root.addStretch()

    def refresh(self) -> None:
        if self.main_window.state.current_batch_index is not None:
            self.message.setText("Repricing selected batch row...")
        else:
            self.message.setText("Preparing report preview...")


class ReportPage(Page):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(
            window,
            "Price Report",
            "Review the estimate and supporting listings. Go back to specs if the comparables look off.",
        )
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setSpacing(14)
        self.scroll.setWidget(self.content)
        mode_row = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.standard_radio = QRadioButton("Standard")
        self.standard_radio.setProperty("report_mode", "standard")
        self.advanced_radio = QRadioButton("Advanced")
        self.advanced_radio.setProperty("report_mode", "advanced")
        self.mode_group.addButton(self.standard_radio)
        self.mode_group.addButton(self.advanced_radio)
        self.standard_radio.setChecked(True)
        self.standard_radio.toggled.connect(self._mode_changed)
        self.advanced_radio.toggled.connect(self._mode_changed)
        mode_row.addWidget(self.standard_radio)
        mode_row.addWidget(self.advanced_radio)
        mode_row.addStretch()
        self.root.addLayout(mode_row)
        self.root.addWidget(self.scroll, 1)
        buttons = QHBoxLayout()
        self.back_button = QPushButton("Back to Specs")
        self.back_button.clicked.connect(self.back_to_specs)
        self.previous_button = QPushButton("Previous")
        self.previous_button.clicked.connect(self.previous_report)
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.next_report)
        self.another_button = QPushButton("Price Another Device")
        self.another_button.clicked.connect(self.secondary_action)
        self.print_button = QPushButton("Print")
        self.print_button.clicked.connect(self.print_report)
        self.finish_button = QPushButton("Finish")
        self.finish_button.clicked.connect(self.main_window.close)
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.previous_button)
        buttons.addWidget(self.next_button)
        buttons.addStretch()
        buttons.addWidget(self.print_button)
        buttons.addWidget(self.another_button)
        buttons.addWidget(self.finish_button)
        self.root.addLayout(buttons)

    def refresh(self) -> None:
        clear_layout(self.content_layout)
        self.print_button.setEnabled(self._can_print())
        self._sync_batch_controls()
        self._sync_mode_controls()
        if self.main_window.state.report_error:
            self._add_message("Pricing failed", self.main_window.state.report_error, "errorPanel")
            return

        result = self.main_window.state.report_result
        if not result:
            self._add_message("No report generated", self.main_window.state.report_text or "Try pricing the device again.", "statusPanel")
            return

        advanced = self.main_window.state.report_mode == "advanced"
        self._add_price_summary(result, advanced=advanced)
        self._add_signal_section(result)
        self._add_device_identification_section(result.get("device_identification"))
        self._add_specs_section(result.get("specs"))
        if advanced:
            self._add_search_section(result)
            self._add_source_statuses(result.get("source_statuses"))
            self._add_source_diagnostics(result.get("source_diagnostics"))
        self._add_filter_section(result)
        if advanced:
            self._add_advanced_comparable_controls(result)
            self._add_supporting_listings(
                result.get("all_comparable_listings") or result.get("supporting_listings") or [],
                interactive=True,
            )
        else:
            self._add_supporting_listings(result.get("supporting_listings") or [])
        self.content_layout.addStretch()

    def _mode_changed(self, *_args: Any) -> None:
        checked = self.mode_group.checkedButton()
        if checked is None:
            return
        mode = str(checked.property("report_mode") or "standard")
        if self.main_window.state.report_mode == mode:
            return
        self.main_window.state.report_mode = mode
        self.refresh()

    def _sync_mode_controls(self) -> None:
        mode = self.main_window.state.report_mode
        self.standard_radio.blockSignals(True)
        self.advanced_radio.blockSignals(True)
        self.standard_radio.setChecked(mode != "advanced")
        self.advanced_radio.setChecked(mode == "advanced")
        self.standard_radio.blockSignals(False)
        self.advanced_radio.blockSignals(False)

    def print_report(self) -> None:
        if not self._can_print():
            return

        printer = QPrinter()
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QDialog.Accepted:
            return

        document = QTextDocument()
        document.setHtml(_printable_report_html(self._printable_report_text()))
        document.print_(printer)

    def back_to_specs(self) -> None:
        if self.main_window.state.current_batch_index is not None:
            self.main_window.edit_batch_item(self.main_window.state.current_batch_index)
            return
        self.main_window.show_specs()

    def secondary_action(self) -> None:
        if self.main_window.state.current_batch_index is not None:
            self.main_window.show_batch()
            return
        self.main_window.reset_for_new_device()

    def previous_report(self) -> None:
        index = self.main_window.state.current_batch_index
        if index is None:
            return
        for candidate in range(index - 1, -1, -1):
            item = self.main_window.state.batch_items[candidate]
            if item.get("result") or item.get("error"):
                self.main_window.open_batch_report(candidate)
                return

    def next_report(self) -> None:
        index = self.main_window.state.current_batch_index
        if index is None:
            return
        for candidate in range(index + 1, len(self.main_window.state.batch_items)):
            item = self.main_window.state.batch_items[candidate]
            if item.get("result") or item.get("error"):
                self.main_window.open_batch_report(candidate)
                return

    def _sync_batch_controls(self) -> None:
        index = self.main_window.state.current_batch_index
        in_batch = index is not None
        self.back_button.setText("Edit Row" if in_batch else "Back to Specs")
        self.another_button.setText("Back to Batch" if in_batch else "Price Another Device")
        self.previous_button.setVisible(in_batch)
        self.next_button.setVisible(in_batch)
        self.previous_button.setEnabled(bool(in_batch and self._has_report_before(index)))
        self.next_button.setEnabled(bool(in_batch and self._has_report_after(index)))

    def _has_report_before(self, index: int | None) -> bool:
        if index is None:
            return False
        return any(item.get("result") or item.get("error") for item in self.main_window.state.batch_items[:index])

    def _has_report_after(self, index: int | None) -> bool:
        if index is None:
            return False
        return any(item.get("result") or item.get("error") for item in self.main_window.state.batch_items[index + 1 :])

    def _can_print(self) -> bool:
        return bool(
            self.main_window.state.report_result
            and not self.main_window.state.report_error
        )

    def _printable_report_text(self) -> str:
        result = self.main_window.state.report_result
        advanced = self.main_window.state.report_mode == "advanced"
        return format_price_report(
            result,
            advanced=advanced,
            include_all_comparables=advanced,
        )

    def _add_price_summary(self, result: dict[str, Any], advanced: bool) -> None:
        count = _safe_int(result.get("count"))
        if count <= 0:
            self._add_message(
                "No usable comparable listings found",
                "Review the detected specs and queries below, then go back and make the specs more specific if needed.",
                "warningPanel",
            )
            return

        grid = QGridLayout()
        grid.setSpacing(10)

        if result.get("pricing_basis") == "asking_adjusted":
            estimate = f"{_format_money(result.get('conservative_low_cad'))} - {_format_money(result.get('conservative_high_cad'))}"
            note = f"eBay median: {_format_money(result.get('asking_median_price_cad'))}"
            title = "Conservative Estimate"
        elif result.get("pricing_basis") == "weighted_sources":
            estimate = _format_money(result.get("median_price_cad"))
            note = _format_pricing_basis(result)
            title = "Weighted Estimate"
        else:
            estimate = _format_money(result.get("median_price_cad"))
            note = _format_pricing_basis(result)
            title = "Median Price"

        grid.addWidget(
            _metric_card(
                title,
                estimate,
                note,
                "The main price this report recommends using for the device.",
            ),
            0,
            0,
        )
        grid.addWidget(
            _metric_card(
                "Comparable Range",
                f"{_format_money(_range_low(result))} - {_format_money(_range_high(result))}",
                "Source quote range" if result.get("pricing_basis") == "weighted_sources" else "Low-to-high usable listings",
                "The lowest and highest prices among listings used in the current estimate.",
            ),
            0,
            1,
        )
        grid.addWidget(
            _metric_card(
                "Comparables",
                str(count),
                f"Best query tier: {_format_query_tier(result.get('query_tier'))}",
                "The number of listings used after dedupe, filtering, and condition matching.",
            ),
            1,
            0,
        )
        grid.addWidget(
            _metric_card(
                "Sources",
                (_format_source_quotes(result.get("source_quotes")) or _format_source_counts(result.get("source_counts")))
                if advanced
                else _format_source_counts(result.get("source_counts")),
                _format_source_counts(result.get("source_counts")),
                "Shows source-level quote prices when available, plus the usable listing counts by source.",
            ),
            1,
            1,
        )

        self.content_layout.addLayout(grid)

    def _add_signal_section(self, result: dict[str, Any]) -> None:
        rows = []
        confidence = _labels(result.get("confidence_flags"), FLAG_LABELS)
        limitations = _labels(result.get("pricing_limitations"), LIMITATION_LABELS)
        warnings = _labels(result.get("listing_warnings"), WARNING_LABELS)
        rows.append(
            (
                "Confidence Flags",
                ", ".join(confidence) if confidence else "None Triggered",
                "Flags about estimate strength. Fewer flags usually means the estimate is more reliable.",
            )
        )
        rows.append(
            (
                "Pricing Limitations",
                ", ".join(limitations) if limitations else "None Triggered",
                "Limits caused by the available pricing data, such as eBay-only active listing estimates.",
            )
        )
        rows.append(
            (
                "Listing Warnings",
                ", ".join(warnings) if warnings else "None Triggered",
                "Warnings about individual comparable listings, such as unknown shipping.",
            )
        )
        self._add_key_value_section("Report Signals", rows)

    def _add_specs_section(self, specs: Any) -> None:
        if not isinstance(specs, dict) or not specs:
            return

        rows = []
        fields = [
            ("Device Type", "device_type"),
            ("Input", "input_method"),
            ("Brand", "brand"),
            ("Model", "search_model"),
            ("Model", "model"),
            ("OEM SKU", "oem_sku"),
            ("Form Factor", "form_factor"),
            ("CPU", "cpu_short"),
            ("CPU", "cpu"),
            ("RAM", "ram_gb"),
            ("Storage", "storage"),
            ("Variant", "variant"),
            ("Screen Size", "screen_size"),
            ("GPU", "gpu"),
            ("Capacity", "capacity"),
            ("Drive Type", "drive_type"),
            ("Interface", "interface"),
            ("Printer Type", "printer_type"),
            ("Color", "color"),
            ("Resolution", "resolution"),
            ("Refresh Rate", "refresh_rate"),
        ]
        seen_labels = set()
        for label, key in fields:
            if label in seen_labels:
                continue
            value = _display_value(specs.get(key), key)
            if value:
                rows.append((label, value, _help_text(label)))
                seen_labels.add(label)

        self._add_key_value_section("Specs Used", rows)

    def _add_device_identification_section(self, identification: Any) -> None:
        if not isinstance(identification, dict) or not identification.get("attempted"):
            return

        rows = [
            (
                "Status",
                str(identification.get("status") or "unknown").replace("_", " ").title(),
                "Shows whether the exact model identifier could be matched before pricing.",
            )
        ]
        if identification.get("source"):
            rows.append(("Source", _format_source_name(identification.get("source")), "The source used for model-number lookup."))
        if identification.get("title"):
            rows.append(("Matched Device", str(identification.get("title")), "The device record selected by the lookup step."))
        if identification.get("confidence"):
            rows.append(("Confidence", str(identification.get("confidence")).title(), "Deterministic confidence for the selected lookup match."))
        added_fields = identification.get("added_fields") or []
        if added_fields:
            rows.append(("Fields Added", ", ".join(str(field) for field in added_fields), "Fields filled from the lookup before pricing."))
        url = _safe_link_url(identification.get("url"))
        if url:
            link = QLabel(f'<a href="{html.escape(url, quote=True)}">Open lookup match</a>')
            link.setOpenExternalLinks(True)
            link.setWordWrap(True)
            rows.append(("Lookup Link", link, "Opens the device record used for lookup."))

        self._add_key_value_section("Device Identification", rows)

    def _add_search_section(self, result: dict[str, Any]) -> None:
        rows = []
        if result.get("raw_listing_count") is not None:
            rows.append(
                (
                    "Search Results",
                    f"{result.get('raw_listing_count')} Raw, {result.get('deduped_listing_count')} After Dedupe",
                    "Raw is the total returned by searches. After dedupe removes repeated listings.",
                )
            )
        basis = _format_pricing_basis(result)
        if basis:
            rows.append(("Pricing Basis", basis, "Explains what kind of pricing data the estimate is based on."))
        source_basis = _format_source_basis(result.get("source_basis"))
        if source_basis:
            rows.append(("Source Basis", source_basis, "Explains how source-level quotes affected the estimate."))
        source_quotes = _format_source_quotes(result.get("source_quotes"))
        if source_quotes:
            rows.append(("Source Quotes", source_quotes, "Per-source quote medians and weights used by weighted source pricing."))
        self._add_key_value_section("Search Summary", rows)

        queries = result.get("queries")
        if not isinstance(queries, list) or not queries:
            return

        query_rows = []
        for query in queries:
            if not isinstance(query, dict) or not query.get("text"):
                continue
            query_rows.append(
                (
                    f"Tier {_format_query_tier(query.get('tier'))}",
                    str(query.get("text")),
                    "Lower tiers are more specific searches. Broader tiers are used as fallback searches.",
                )
            )
        self._add_key_value_section("Queries Used", query_rows)

    def _add_source_statuses(self, statuses: Any) -> None:
        if not isinstance(statuses, list) or not statuses:
            return

        rows = []
        for status in statuses:
            if not isinstance(status, dict):
                continue
            source = _format_source_name(status.get("source"))
            state = _format_source_status(status)
            rows.append(
                (
                    source,
                    state,
                    "Shows whether this source was disabled, searched successfully, returned no candidates, or failed.",
                )
            )
        self._add_key_value_section("Source Status", rows)

    def _add_source_diagnostics(self, diagnostics: Any) -> None:
        if not isinstance(diagnostics, list) or not diagnostics:
            return

        self.content_layout.addWidget(_section_title("Source Diagnostics"))
        for index, diagnostic in enumerate(diagnostics[:6], start=1):
            if not isinstance(diagnostic, dict):
                continue
            source = _format_source_name(diagnostic.get("source"))
            verified = "Verified" if diagnostic.get("source_match_verified") else "Not Verified"
            title = diagnostic.get("title") or "Untitled listing"
            rows = [
                ("Source", source, "The pricing source that returned this candidate."),
                ("Candidate", f"{index}. {title}", "Candidate listing returned by a non-eBay pricing source."),
                ("Match", verified, "Whether deterministic spec matching allowed this listing to affect the weighted estimate."),
            ]
            reasons = diagnostic.get("source_match_reasons") or []
            if reasons:
                rows.append(("Match Reasons", ", ".join(str(reason) for reason in reasons), "Why the candidate was not considered a verified match."))
            filter_reason = diagnostic.get("filter_exclusion_reason")
            if filter_reason:
                rows.append(("Filter Reason", str(filter_reason), "Why the candidate was excluded from usable comparables."))
            if diagnostic.get("price_cad") is not None:
                rows.append(("Price", _format_money(diagnostic.get("price_cad")), "Parsed candidate price."))
            if diagnostic.get("query_text"):
                rows.append(("Source Query", str(diagnostic.get("query_text")), "The query actually sent to this source."))
            if diagnostic.get("generated_query_text"):
                rows.append(("Generated Query", str(diagnostic.get("generated_query_text")), "The original generic query before source-specific adjustment."))
            url = _safe_link_url(diagnostic.get("url"))
            if url:
                link = QLabel(f'<a href="{html.escape(url, quote=True)}">Open candidate</a>')
                link.setOpenExternalLinks(True)
                link.setWordWrap(True)
                rows.append(("Listing", link, "Opens the candidate listing in your browser."))
            self._add_key_value_section("", rows)

        if len(diagnostics) > 6:
            self._add_message(
                "Source Diagnostics",
                f"{len(diagnostics) - 6} additional source candidates are available in the JSON report.",
                "statusPanel",
            )

    def _add_filter_section(self, result: dict[str, Any]) -> None:
        if "excluded_count" not in result and "target_condition" not in result:
            return

        rows = [
            (
                "Target Condition",
                _display_value(result.get("target_condition") or "any", "condition"),
                "Listings outside this condition target are filtered out unless condition is set to Any.",
            )
        ]
        excluded_count = _safe_int(result.get("excluded_count"))
        if excluded_count:
            rows.append(
                (
                    "Filtered Out",
                    f"{excluded_count} ({_format_filter_reasons(result.get('excluded_reasons'))})",
                    "Listings removed before pricing because they were not useful comparables.",
                )
            )
        else:
            rows.append(("Filtered Out", "0", "Listings removed before pricing because they were not useful comparables."))
        self._add_key_value_section("Filtering", rows)

    def _add_advanced_comparable_controls(self, result: dict[str, Any]) -> None:
        comparables = result.get("all_comparable_listings") or result.get("supporting_listings") or []
        if not comparables:
            return
        removed_count = len(self.main_window.state.pending_excluded_comparable_ids)
        applied_count = len(self.main_window.state.applied_excluded_comparable_ids)
        rows = [
            (
                "Manual Review",
                f"{removed_count} marked for removal, {applied_count} currently excluded",
                "Toggle comparable listings below, then reevaluate using the already fetched results.",
            )
        ]
        self._add_key_value_section("Comparable Review", rows)
        row = QHBoxLayout()
        reevaluate = QPushButton("Reevaluate Report")
        reevaluate.clicked.connect(self._reevaluate_report)
        reset = QPushButton("Use All Comparables")
        reset.clicked.connect(self._use_all_comparables)
        row.addStretch()
        row.addWidget(reset)
        row.addWidget(reevaluate)
        self.content_layout.addLayout(row)

    def _reevaluate_report(self, *_args: Any) -> None:
        base_result = self.main_window.state.base_report_result or self.main_window.state.report_result
        excluded_ids = set(self.main_window.state.pending_excluded_comparable_ids)
        self.main_window.state.report_result = reprice_existing_result(base_result, excluded_ids)
        self.main_window.state.applied_excluded_comparable_ids = excluded_ids
        self.main_window.state.report_text = self._printable_report_text()
        self.main_window._save_current_report_to_batch()
        self.refresh()

    def _use_all_comparables(self, *_args: Any) -> None:
        self.main_window.state.pending_excluded_comparable_ids = set()
        self._reevaluate_report()

    def _set_comparable_pending(self, comparable_id: str, included: bool) -> None:
        if not comparable_id:
            return
        pending = set(self.main_window.state.pending_excluded_comparable_ids)
        if included:
            pending.discard(comparable_id)
        else:
            pending.add(comparable_id)
        self.main_window.state.pending_excluded_comparable_ids = pending
        self.refresh()

    def _add_supporting_listings(self, listings: list[dict[str, Any]], interactive: bool = False) -> None:
        if not listings:
            self._add_message(
                "Supporting listings",
                "No supporting listings are available for this report.",
                "statusPanel",
            )
            return

        self.content_layout.addWidget(_section_title("Comparable Listings" if interactive else "Supporting Listings"))
        for index, listing in enumerate(listings, start=1):
            comparable_id = _comparable_id(listing)
            pending_removed = comparable_id in self.main_window.state.pending_excluded_comparable_ids
            applied_removed = comparable_id in self.main_window.state.applied_excluded_comparable_ids or listing.get("excluded_by_user") is True
            card = QFrame()
            card.setObjectName("listingCardRemoved" if pending_removed else "listingCard")
            card.setFrameShape(QFrame.StyledPanel)
            layout = QVBoxLayout(card)
            layout.setSpacing(6)

            if interactive:
                toggle = QCheckBox("Use in report")
                toggle.setChecked(not pending_removed)
                toggle.setToolTip("Unchecked listings are excluded after you reevaluate the report.")
                toggle.toggled.connect(
                    lambda checked, listing_id=comparable_id: self._set_comparable_pending(listing_id, checked)
                )
                layout.addWidget(toggle)
                if pending_removed:
                    status = "Excluded from current report" if applied_removed else "Marked for removal"
                    label = _selectable_label(status)
                    label.setObjectName("statusText")
                    layout.addWidget(label)

            listing_title = f"{index}. {listing.get('title') or 'Untitled listing'}"
            url = _safe_link_url(listing.get("url"))
            if url:
                title = QLabel(f'<a href="{html.escape(url, quote=True)}">{html.escape(listing_title)}</a>')
                title.setOpenExternalLinks(True)
                title.setToolTip("Open listing in browser")
                _make_label_selectable(title, links=True)
            else:
                title = _selectable_label(listing_title)
            title.setObjectName("listingTitle")
            title.setWordWrap(True)
            layout.addWidget(title)

            layout.addLayout(_detail_row("Price", format_listing_price(listing), "Item price, shipping, and total when shipping is known."))
            layout.addLayout(_detail_row("Source", _format_source_name(listing.get("source")), "The pricing source that returned this listing."))
            layout.addLayout(_detail_row("Condition", _format_report_condition(listing), "The normalized condition used for matching, with the raw source condition in parentheses."))
            layout.addLayout(_detail_row("Tier", _format_query_tier(listing.get("query_tier")), "The search tier that found this listing. Lower is more specific."))
            if listing.get("query_text"):
                layout.addLayout(_detail_row("Query", str(listing.get("query_text")), "The exact search query that found this listing."))
            layout.addLayout(_detail_row("Location", format_location(listing.get("location")), "Location reported by the source."))

            if url:
                link = QLabel(f'<a href="{html.escape(url, quote=True)}">Open in browser</a>')
                link.setOpenExternalLinks(True)
                link.setWordWrap(True)
                layout.addLayout(_detail_row("Listing", link, "Opens the original source listing in your browser."))

            self.content_layout.addWidget(card)

    def _add_key_value_section(self, title: str, rows: list[tuple[str, ...]]) -> None:
        if not rows:
            return
        if title:
            self.content_layout.addWidget(_section_title(title))
        panel = QFrame()
        panel.setObjectName("sectionPanel")
        panel.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setSpacing(7)
        for row in rows:
            label, value = row[0], row[1]
            help_text = row[2] if len(row) > 2 else _help_text(label)
            layout.addLayout(_detail_row(label, value, help_text))
        self.content_layout.addWidget(panel)

    def _add_message(self, title: str, message: str, object_name: str) -> None:
        panel = QFrame()
        panel.setObjectName(object_name)
        panel.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(panel)
        heading = _selectable_label(title)
        heading.setObjectName("messageTitle")
        body = _selectable_label(message)
        body.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(body)
        self.content_layout.addWidget(panel)


def _gui_batch_item(item: BatchItem) -> dict[str, Any]:
    return {
        "row_number": item.row_number,
        "item_id": item.item_id,
        "device_type": item.device_type,
        "values": dict(item.values),
        "errors": list(item.errors),
        "status": "Invalid" if item.errors else "Ready",
        "result": {},
        "base_result": {},
        "report_text": "",
        "error": "",
        "report_mode": "standard",
        "pending_excluded_comparable_ids": set(),
        "applied_excluded_comparable_ids": set(),
    }


def _batch_success_status(result: dict[str, Any]) -> str:
    comparable_count = _safe_int(result.get("count"))
    if comparable_count <= 0:
        return "Needs Review"
    severe_flags = _batch_review_flags(
        result.get("confidence_flags"),
        comparable_count,
        _result_warn_below_comparables(result),
    )
    if severe_flags:
        return "Needs Review"
    return "Complete"


def _batch_review_flags(flags: Any, comparable_count: int, warn_below_comparables: int = 5) -> list[str]:
    review_flags = []
    for flag in flags or []:
        flag_text = str(flag)
        if flag_text == "low_comparable_count" and comparable_count >= warn_below_comparables:
            continue
        review_flags.append(flag_text)
    return review_flags


def _result_warn_below_comparables(result: dict[str, Any]) -> int:
    options = result.get("reprice_options")
    if isinstance(options, dict):
        value = _safe_int(options.get("warn_below_comparables"))
        if value > 0:
            return value
    return 5


def _batch_order_label(index: int, _item: dict[str, Any]) -> str:
    return str(index + 1)


def _batch_status_object_name(status: str) -> str:
    return {
        "Complete": "batchStatusComplete",
        "Needs Review": "batchStatusReview",
        "Failed": "batchStatusFailed",
        "Invalid": "batchStatusFailed",
        "Running": "batchStatusRunning",
    }.get(status, "statusText")


def _batch_issue_text(item: dict[str, Any]) -> str:
    errors = item.get("errors") or []
    if errors:
        return " ".join(str(error) for error in errors)
    if item.get("error"):
        return str(item.get("error"))
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    flags = result.get("confidence_flags") if result else []
    if flags:
        comparable_count = _safe_int(result.get("count"))
        review_flags = _batch_review_flags(flags, comparable_count, _result_warn_below_comparables(result))
        if item.get("status") == "Complete":
            flags = review_flags
        if flags:
            return ", ".join(_sentence_case(str(flag).replace("_", " ")) for flag in flags)
    return ""


def _serializable_batch_item(item: dict[str, Any]) -> dict[str, Any]:
    clean = dict(item)
    for key in ["pending_excluded_comparable_ids", "applied_excluded_comparable_ids"]:
        clean[key] = sorted(str(value) for value in clean.get(key, set()))
    return clean


def _section_title(text: str) -> QLabel:  # type: ignore[misc]
    label = _selectable_label(text)
    label.setObjectName("sectionTitle")
    return label


def _metric_card(title: str, value: str, note: str, help_text: str) -> QFrame:  # type: ignore[misc]
    card = QFrame()
    card.setObjectName("metricCard")
    card.setFrameShape(QFrame.StyledPanel)
    layout = QGridLayout(card)
    layout.setColumnStretch(2, 1)
    layout.setHorizontalSpacing(8)
    layout.setVerticalSpacing(5)

    title_label = _selectable_label(title)
    title_label.setObjectName("metricTitle")
    value_label = _selectable_label(value)
    value_label.setObjectName("metricValue")
    value_label.setWordWrap(True)
    value_label.setAlignment(Qt.AlignRight | Qt.AlignTop)
    note_label = _selectable_label(note)
    note_label.setObjectName("metricNote")
    note_label.setWordWrap(True)
    note_label.setAlignment(Qt.AlignRight | Qt.AlignTop)

    layout.addWidget(title_label, 0, 0)
    layout.addWidget(_info_button(help_text), 0, 1)
    layout.addWidget(value_label, 0, 2)
    layout.addWidget(note_label, 1, 2)
    return card


def _detail_row(label: str, value: str | QLabel, help_text: str = "") -> QHBoxLayout:  # type: ignore[misc]
    row = QHBoxLayout()
    row.setSpacing(8)
    label_widget = _selectable_label(label)
    label_widget.setObjectName("detailLabel")
    label_widget.setMinimumWidth(150)
    row.addWidget(label_widget)
    row.addWidget(_info_button(help_text or _help_text(label)))

    if isinstance(value, QLabel):
        value_widget = value
        _make_label_selectable(value_widget, links=True)
    else:
        value_widget = _selectable_label(value)
    value_widget.setObjectName("detailValue")
    value_widget.setWordWrap(True)
    value_widget.setAlignment(Qt.AlignRight | Qt.AlignTop)
    row.addWidget(value_widget, 1)
    return row


def _selectable_label(text: str) -> QLabel:  # type: ignore[misc]
    label = QLabel(text)
    _make_label_selectable(label)
    return label


def _make_label_selectable(label: QLabel, links: bool = False) -> None:  # type: ignore[misc]
    flags = Qt.TextSelectableByMouse
    if links:
        flags = flags | Qt.LinksAccessibleByMouse
    label.setTextInteractionFlags(flags)


def _info_button(help_text: str) -> QToolButton:  # type: ignore[misc]
    button = QToolButton()
    button.setText("i")
    button.setObjectName("infoButton")
    button.setToolTip(help_text or "Additional information.")
    button.setAutoRaise(True)
    button.setFocusPolicy(Qt.NoFocus)
    return button


def _labels(values: Any, mapping: dict[str, str]) -> list[str]:
    if not isinstance(values, list):
        return []
    return [_sentence_case(mapping.get(str(value), str(value))) for value in values]


def _format_pricing_basis(result: dict[str, Any]) -> str:
    basis = result.get("pricing_basis")
    if basis == "sold":
        return "Comparable Listings"
    if basis == "asking_adjusted":
        return f"eBay Active Listings, Discounted {_discount_percent_range(result)}"
    if basis == "active":
        return "Active Listings"
    if basis == "mixed":
        return "Comparable Listings"
    if basis == "unknown":
        return "Unknown"
    if basis == "weighted_sources":
        return "Weighted Source Quote Average"
    return _display_value(basis, "basis") if basis else ""


def _format_source_basis(value: Any) -> str:
    return _sentence_case(_source_basis_label(value)) if value else ""


def _format_source_quotes(quotes: Any) -> str:
    if not isinstance(quotes, list) or not quotes:
        return ""
    parts = []
    for quote in quotes:
        if not isinstance(quote, dict):
            continue
        source = _format_source_name(quote.get("source"))
        price = _format_money(quote.get("price_cad"))
        weight = quote.get("weight")
        weight_text = f", weight {weight:g}" if isinstance(weight, (int, float)) else ""
        verified = " verified" if quote.get("verified") else ""
        parts.append(f"{source}: {price}{verified}{weight_text}")
    return "; ".join(parts)


def _format_source_name(value: Any) -> str:
    return _source_name_label(value)


def _format_source_status(status: dict[str, Any]) -> str:
    labels = {
        "disabled": "Disabled",
        "error": "Error",
        "no_results": "No Results",
        "not_searched": "Not Searched",
        "returned": "Returned Listings",
    }
    state = labels.get(str(status.get("status") or "").strip().lower(), "Unknown")
    details = []
    query_count = _safe_int(status.get("query_count"))
    listing_count = _safe_int(status.get("raw_listing_count"))
    if query_count:
        details.append(f"{query_count} Quer{'y' if query_count == 1 else 'ies'}")
    if status.get("searched"):
        details.append(f"{listing_count} Raw Listing{'s' if listing_count != 1 else ''}")
    message = str(status.get("message") or "").strip()
    if message:
        details.append(message)
    return f"{state} ({'; '.join(details)})" if details else state


def _discount_percent_range(result: dict[str, Any]) -> str:
    low = _safe_percent(result.get("asking_only_discount_low"))
    high = _safe_percent(result.get("asking_only_discount_high"))
    if low is None or high is None:
        return "Unknown Range"
    return f"{low}-{high}%"


def _safe_link_url(value: Any) -> str:
    url = str(value or "").strip()
    if url.lower().startswith(("http://", "https://")):
        return url
    return ""


def _comparable_id(listing: dict[str, Any]) -> str:
    value = str(listing.get("comparable_id") or "").strip()
    if value:
        return value
    source = str(listing.get("source") or "unknown").strip().lower()
    item_id = str(listing.get("item_id") or "").strip().lower()
    if item_id:
        return f"source_item:{source}|{item_id}"
    url = str(listing.get("url") or "").strip().lower()
    if url:
        return f"url:{url}"
    title = str(listing.get("title") or "").strip().lower()
    price = str(listing.get("total_price_cad") or "").strip()
    return f"title_price:{title}|{price}"


def _printable_report_html(text: str, title: str = "CFS Price Report") -> str:
    escaped = html.escape(text)
    escaped_title = html.escape(title)
    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{
      color: #111827;
      font-family: Arial, sans-serif;
      font-size: 10pt;
      line-height: 1.35;
    }}
    h1 {{
      font-size: 18pt;
      margin: 0 0 12pt;
    }}
    pre {{
      font-family: Consolas, "Courier New", monospace;
      overflow-wrap: anywhere;
      white-space: pre-wrap;
    }}
  </style>
</head>
<body>
  <h1>{escaped_title}</h1>
  <pre>{escaped}</pre>
</body>
</html>
"""


def _format_source_counts(source_counts: Any) -> str:
    if not isinstance(source_counts, dict) or not source_counts:
        return "None"
    return ", ".join(f"{_display_value(source, 'source')}: {count}" for source, count in sorted(source_counts.items()))


def _format_filter_reasons(reasons: Any) -> str:
    if not isinstance(reasons, dict) or not reasons:
        return "unknown reason"
    parts = []
    for reason, count in sorted(reasons.items()):
        parts.append(f"{_sentence_case(FILTER_LABELS.get(reason, str(reason)))}: {count}")
    return ", ".join(parts)


def _display_value(value: Any, key: str) -> str:
    if value in (None, "", [], {}):
        return ""
    if key == "ram_gb":
        return f"{value} GB"
    if key == "storage" and isinstance(value, list):
        drives = []
        for drive in value:
            if not isinstance(drive, dict):
                continue
            size = drive.get("size_gb")
            drive_type = drive.get("type")
            parts = [f"{size} GB" if size else "", str(drive_type or "")]
            text = " ".join(part for part in parts if part)
            if text:
                drives.append(text)
        return ", ".join(drives)
    text = str(value).strip()
    if not text:
        return ""
    if key in {"cpu", "cpu_short"}:
        return _format_cpu_value(text)

    special = {
        "aio": "All-In-One",
        "all-in-one": "All-In-One",
        "any": "Any",
        "asking": "Asking",
        "cad": "CAD",
        "computer": "Computer",
        "cpu": "CPU",
        "detected": "Detected",
        "desktop": "Desktop",
        "ebay": "eBay",
        "excellent": "Excellent",
        "good": "Good",
        "hdd": "HDD",
        "laptop": "Laptop",
        "manual": "Manual",
        "mint": "Mint",
        "monitor": "Monitor",
        "msata": "mSATA",
        "nvme": "NVMe",
        "phone": "Phone",
        "printer": "Printer",
        "ram": "RAM",
        "refurb_io": "Refurb.io",
        "sata": "SATA",
        "ssd": "SSD",
        "storage": "Storage",
        "tablet": "Tablet",
        "unknown": "Unknown",
        "usb": "USB",
        "amazon_renewed": "Amazon Renewed",
    }
    lowered = text.lower()
    if lowered in special:
        return special[lowered]
    return _sentence_case(text)


def _format_report_condition(listing: dict[str, Any]) -> str:
    condition = format_condition(listing)
    if " (" in condition:
        normalized, raw = condition.split(" (", 1)
        return f"{_display_value(normalized, 'condition')} ({raw}"
    return _display_value(condition, "condition")


def _sentence_case(text: str) -> str:
    words = []
    specials = {
        "a": "a",
        "and": "and",
        "by": "by",
        "cad": "CAD",
        "cpu": "CPU",
        "dedupe": "Dedupe",
        "ebay": "eBay",
        "gpu": "GPU",
        "hdd": "HDD",
        "iqr": "IQR",
        "msata": "mSATA",
        "nvme": "NVMe",
        "oem": "OEM",
        "only": "Only",
        "or": "or",
        "ram": "RAM",
        "refurb.io": "Refurb.io",
        "refurb": "Refurb",
        "sata": "SATA",
        "ssd": "SSD",
        "the": "the",
        "to": "to",
        "usb": "USB",
    }
    for index, word in enumerate(str(text).replace("_", " ").split()):
        if not word:
            continue
        stripped = word.strip()
        suffix = ""
        while stripped and stripped[-1] in ",.;:)":
            suffix = stripped[-1] + suffix
            stripped = stripped[:-1]
        prefix = ""
        while stripped and stripped[0] in "(":
            prefix += stripped[0]
            stripped = stripped[1:]

        lowered = stripped.lower()
        if lowered in specials and not (index == 0 and lowered in {"a", "and", "by", "or", "the", "to"}):
            clean = specials[lowered]
        elif stripped.isupper() and len(stripped) <= 4:
            clean = stripped
        else:
            clean = stripped[:1].upper() + stripped[1:]
        words.append(f"{prefix}{clean}{suffix}")
    return " ".join(words)


def _help_text(label: str) -> str:
    return {
        "Brand": "The brand used in the search and report.",
        "Capacity": "Storage capacity used for matching storage devices.",
        "Color": "Whether the printer is color or monochrome.",
        "CPU": "Processor model used for computer matching.",
        "Device Type": "The kind of device being priced.",
        "Drive Type": "Whether the storage device is an SSD or HDD.",
        "Filtered Out": "Listings removed before pricing because they were not useful comparables.",
        "Form Factor": "Laptop, desktop, or all-in-one.",
        "GPU": "Dedicated graphics information when detected or entered.",
        "Input": "Whether specs were entered manually or came from auto-detect.",
        "Interface": "Connection standard for storage devices, such as SATA or NVMe.",
        "Listing": "Original listing page.",
        "Location": "Location reported by the source.",
        "Model": "The model name used in search queries.",
        "OEM SKU": "Manufacturer SKU. When available, this is usually the most exact computer search term.",
        "Price": "Item price, shipping, and total when shipping is known.",
        "Printer Type": "Printer category used for matching.",
        "Query": "The exact search query that found the listing.",
        "RAM": "Memory amount used for computer matching.",
        "Refresh Rate": "Monitor refresh rate used for matching.",
        "Resolution": "Monitor resolution used for matching.",
        "Screen Size": "Screen size used to avoid wrong size variants.",
        "Source": "The pricing source that returned the listing or quote.",
        "Storage": "Computer storage size and drive type used for matching.",
        "Target Condition": "Listings outside this condition target are filtered out unless condition is set to Any.",
        "Tier": "The search tier that found the listing. Lower is more specific.",
        "Variant": "Sub-model variant, such as Mini, Plus, Pro, or Max.",
    }.get(label, "Additional information about this report field.")


def _format_query_tier(query_tier: Any) -> str:
    if query_tier is None:
        return "unknown"
    return str(query_tier)


def _format_money(value: Any) -> str:
    try:
        return f"${float(value):,.2f} CAD"
    except (TypeError, ValueError):
        return "Unknown"


def _range_low(result: dict[str, Any]) -> Any:
    return result.get("price_low_cad", result.get("iqr_low_cad"))


def _range_high(result: dict[str, Any]) -> Any:
    return result.get("price_high_cad", result.get("iqr_high_cad"))


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_percent(value: Any) -> int | None:
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError):
        return None


def credentials_present() -> bool:
    load_env_file(override=True)
    return bool(os.getenv("EBAY_CLIENT_ID") and os.getenv("EBAY_CLIENT_SECRET"))


def nav_row(
    back_text: str | None,
    back_callback: Any,
    next_text: str,
    next_callback: Any,
) -> QHBoxLayout:  # type: ignore[name-defined]
    row = QHBoxLayout()
    if back_text:
        back = QPushButton(back_text)
        back.clicked.connect(back_callback)
        row.addWidget(back)
    row.addStretch()
    next_button = QPushButton(next_text)
    next_button.clicked.connect(next_callback)
    row.addWidget(next_button)
    return row


def field_widget(field: FieldSpec, value: Any = None) -> QWidget:  # type: ignore[misc]
    if field.options:
        combo = StableComboBox()
        if not field.default:
            combo.addItem("", "")
        for option in field.options:
            combo.addItem(option_label(field, option), option)

        selected = str(value or field.default or "")
        if selected:
            index = combo.findData(selected)
            if index < 0:
                index = combo.findText(selected)
            if index >= 0:
                combo.setCurrentIndex(index)
        return combo

    line = QLineEdit()
    line.setPlaceholderText(field.placeholder)
    if value:
        line.setText(str(value))
    return line


def widget_value(widget: QWidget) -> str:  # type: ignore[misc]
    if isinstance(widget, QComboBox):
        value = widget.currentData()
        return str(value if value is not None else widget.currentText()).strip()
    if isinstance(widget, QLineEdit):
        return widget.text().strip()
    return ""


def clear_form(form: QFormLayout) -> None:  # type: ignore[name-defined]
    while form.count():
        item = form.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            clear_layout(child_layout)


def clear_layout(layout: Any) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            clear_layout(child_layout)


def main() -> None:
    if QApplication is None:
        raise SystemExit("PySide6 is not installed. Install project dependencies and try again.")
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


STYLE = """
QWidget {
    font-size: 11pt;
}
#pageTitle {
    font-size: 22pt;
    font-weight: 700;
}
#pageSubtitle {
    color: #4b5563;
}
#errorText {
    color: #b91c1c;
}
#statusText {
    color: #4b5563;
}
#batchStatusComplete {
    color: #047857;
    font-weight: 700;
}
#batchStatusReview {
    color: #b45309;
    font-weight: 700;
}
#batchStatusFailed {
    color: #b91c1c;
    font-weight: 700;
}
#batchStatusRunning {
    color: #2563eb;
    font-weight: 700;
}
QLineEdit, QComboBox {
    padding: 6px;
}
QPushButton {
    padding: 7px 14px;
}
#sectionPanel, #metricCard, #listingCard, #listingCardRemoved, #statusPanel, #warningPanel, #errorPanel {
    border: 1px solid #d1d5db;
    border-radius: 6px;
    background: #ffffff;
}
#warningPanel {
    border-color: #f59e0b;
    background: #fffbeb;
}
#errorPanel {
    border-color: #dc2626;
    background: #fef2f2;
}
#listingCardRemoved {
    border-color: #9ca3af;
    background: #f3f4f6;
    color: #6b7280;
}
#sectionTitle {
    font-size: 13pt;
    font-weight: 700;
    margin-top: 6px;
}
#metricTitle, #detailLabel {
    color: #374151;
    font-weight: 700;
}
#metricValue {
    font-size: 15pt;
    font-weight: 700;
    color: #111827;
}
#detailValue, #metricNote {
    color: #111827;
}
#metricNote {
    font-size: 10pt;
    color: #4b5563;
}
#listingTitle, #messageTitle {
    font-weight: 700;
}
#infoButton {
    color: #374151;
    border: 1px solid #9ca3af;
    border-radius: 8px;
    min-width: 16px;
    max-width: 16px;
    min-height: 16px;
    max-height: 16px;
    padding: 0;
    font-size: 8pt;
    font-weight: 700;
}
"""


if __name__ == "__main__":
    main()

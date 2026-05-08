"""PySide6 GUI entry point."""

from __future__ import annotations

from copy import deepcopy
import html
import os
import sys
from typing import Any

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
from pc_pricer.gui_pricing import price_gui_values
from pc_pricer.reporter import (
    FILTER_LABELS,
    FLAG_LABELS,
    LIMITATION_LABELS,
    WARNING_LABELS,
    format_condition,
    format_listing_price,
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
        QButtonGroup,
        QComboBox,
        QDialog,
        QFormLayout,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QRadioButton,
        QScrollArea,
        QStackedWidget,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError:  # pragma: no cover - gives a clear runtime error.
    QApplication = None  # type: ignore[assignment]
    QThread = object  # type: ignore[assignment]
    QButtonGroup = QComboBox = QDialog = QFormLayout = QFrame = QHBoxLayout = QLabel = object  # type: ignore[assignment]
    QGridLayout = QLineEdit = QMainWindow = QMessageBox = QPushButton = QRadioButton = object  # type: ignore[assignment]
    QPrintDialog = QPrinter = QScrollArea = QStackedWidget = QTextDocument = QToolButton = QVBoxLayout = QWidget = object  # type: ignore[assignment]
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
        self.report_text: str = ""
        self.report_error: str = ""


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
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.credentials_page = CredentialsPage(self)
        self.device_page = DeviceTypePage(self)
        self.computer_mode_page = ComputerModePage(self)
        self.specs_page = SpecsPage(self)
        self.loading_page = LoadingPage(self)
        self.report_page = ReportPage(self)

        for page in [
            self.credentials_page,
            self.device_page,
            self.computer_mode_page,
            self.specs_page,
            self.loading_page,
            self.report_page,
        ]:
            self.stack.addWidget(page)

        load_env_file(override=True)

        if credentials_present():
            self.show_device_type()
        else:
            self.show_credentials()

    def show_credentials(self) -> None:
        self.credentials_page.refresh()
        self.stack.setCurrentWidget(self.credentials_page)

    def show_device_type(self) -> None:
        self.device_page.refresh()
        self.stack.setCurrentWidget(self.device_page)

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
        self.state.report_result = result
        self.state.report_text = report
        self.state.report_error = ""
        self.show_report()

    def pricing_failed(self, message: str) -> None:
        self.state.report_result = {}
        self.state.report_text = ""
        self.state.report_error = message
        self.show_report()

    def pricing_finished(self) -> None:
        self.pricing_thread = None

    def show_report(self) -> None:
        self.report_page.refresh()
        self.stack.setCurrentWidget(self.report_page)

    def reset_for_new_device(self) -> None:
        self.state = GuiState()
        self.show_device_type()

    def closeEvent(self, event: Any) -> None:
        if self.pricing_thread is not None and self.pricing_thread.isRunning():
            QMessageBox.information(
                self,
                "Pricing in progress",
                "Wait for the current price search to finish before closing.",
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
        save = QPushButton("Save and Continue")
        save.clicked.connect(self.save_and_continue)
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
        self.root.addLayout(nav_row(None, None, "Next", self.next_page))

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
        super().__init__(window, "Searching", "Searching eBay and preparing the price report.")
        self.message = QLabel()
        self.message.setAlignment(Qt.AlignCenter)
        self.root.addStretch()
        self.root.addWidget(self.message)
        self.root.addStretch()

    def refresh(self) -> None:
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
        self.root.addWidget(self.scroll, 1)
        buttons = QHBoxLayout()
        back = QPushButton("Back to Specs")
        back.clicked.connect(self.main_window.show_specs)
        another = QPushButton("Price Another Device")
        another.clicked.connect(self.main_window.reset_for_new_device)
        self.print_button = QPushButton("Print")
        self.print_button.clicked.connect(self.print_report)
        finish = QPushButton("Finish")
        finish.clicked.connect(self.main_window.close)
        buttons.addWidget(back)
        buttons.addStretch()
        buttons.addWidget(self.print_button)
        buttons.addWidget(another)
        buttons.addWidget(finish)
        self.root.addLayout(buttons)

    def refresh(self) -> None:
        clear_layout(self.content_layout)
        self.print_button.setEnabled(self._can_print())
        if self.main_window.state.report_error:
            self._add_message("Pricing failed", self.main_window.state.report_error, "errorPanel")
            return

        result = self.main_window.state.report_result
        if not result:
            self._add_message("No report generated", self.main_window.state.report_text or "Try pricing the device again.", "statusPanel")
            return

        self._add_price_summary(result)
        self._add_signal_section(result)
        self._add_specs_section(result.get("specs"))
        self._add_search_section(result)
        self._add_filter_section(result)
        self._add_supporting_listings(result.get("supporting_listings") or [])
        self.content_layout.addStretch()

    def print_report(self) -> None:
        if not self._can_print():
            return

        printer = QPrinter()
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QDialog.Accepted:
            return

        document = QTextDocument()
        document.setHtml(_printable_report_html(self.main_window.state.report_text))
        document.print_(printer)

    def _can_print(self) -> bool:
        return bool(
            self.main_window.state.report_text
            and self.main_window.state.report_result
            and not self.main_window.state.report_error
        )

    def _add_price_summary(self, result: dict[str, Any]) -> None:
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
            note = f"Asking median: {_format_money(result.get('asking_median_price_cad'))}"
            title = "Conservative Estimate"
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
                f"{_format_money(result.get('iqr_low_cad'))} - {_format_money(result.get('iqr_high_cad'))}",
                "Middle range of usable listings",
                "A rough middle range from the usable comparable listings.",
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
                _format_source_counts(result.get("source_counts")),
                "Active eBay asking listings",
                "Where the usable comparable listings came from.",
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
                "Limits caused by the available pricing data, such as active asking listings only.",
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
        if result.get("pricing_basis") != "asking_adjusted" and result.get("sold_count") is not None:
            rows.append(
                (
                    "Sold / Asking",
                    f"{result.get('sold_count', 0)} Sold, {result.get('asking_count', 0)} Asking",
                    "How many sold and active asking listings were used.",
                )
            )
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

    def _add_supporting_listings(self, listings: list[dict[str, Any]]) -> None:
        if not listings:
            self._add_message(
                "Supporting listings",
                "No supporting listings are available for this report.",
                "statusPanel",
            )
            return

        self.content_layout.addWidget(_section_title("Supporting Listings"))
        for index, listing in enumerate(listings, start=1):
            card = QFrame()
            card.setObjectName("listingCard")
            card.setFrameShape(QFrame.StyledPanel)
            layout = QVBoxLayout(card)
            layout.setSpacing(6)

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
            layout.addLayout(_detail_row("Condition", _format_report_condition(listing), "The normalized condition used for matching, with the raw eBay condition in parentheses."))
            layout.addLayout(_detail_row("Status", "Sold" if listing.get("is_sold") else "Asking", "Whether this comparable is a sold or active asking listing."))
            layout.addLayout(_detail_row("Tier", _format_query_tier(listing.get("query_tier")), "The search tier that found this listing. Lower is more specific."))
            if listing.get("query_text"):
                layout.addLayout(_detail_row("Query", str(listing.get("query_text")), "The exact search query that found this listing."))
            layout.addLayout(_detail_row("Location", _display_value(listing.get("location") or "Unknown", "location"), "Seller location reported by eBay."))

            if url:
                link = QLabel(f'<a href="{html.escape(url, quote=True)}">Open in browser</a>')
                link.setOpenExternalLinks(True)
                link.setWordWrap(True)
                layout.addLayout(_detail_row("Listing", link, "Opens the original eBay listing in your browser."))

            self.content_layout.addWidget(card)

    def _add_key_value_section(self, title: str, rows: list[tuple[str, ...]]) -> None:
        if not rows:
            return
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
        return "Sold Listings"
    if basis == "asking_adjusted":
        return f"Active Asking Listings, Discounted {_discount_percent_range(result)}"
    if basis == "mixed":
        return "Sold and Asking Listings"
    if basis == "unknown":
        return "Unknown"
    return _display_value(basis, "basis") if basis else ""


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


def _printable_report_html(text: str) -> str:
    escaped = html.escape(text)
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
  <h1>CFS Price Report</h1>
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
        "sata": "SATA",
        "ssd": "SSD",
        "storage": "Storage",
        "tablet": "Tablet",
        "unknown": "Unknown",
        "usb": "USB",
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
        "Location": "Seller location reported by eBay.",
        "Model": "The model name used in search queries.",
        "OEM SKU": "Manufacturer SKU. When available, this is usually the most exact computer search term.",
        "Price": "Item price, shipping, and total when shipping is known.",
        "Printer Type": "Printer category used for matching.",
        "Query": "The exact search query that found the listing.",
        "RAM": "Memory amount used for computer matching.",
        "Refresh Rate": "Monitor refresh rate used for matching.",
        "Resolution": "Monitor resolution used for matching.",
        "Screen Size": "Screen size used to avoid wrong size variants.",
        "Status": "Whether this comparable is a sold or active asking listing.",
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
QLineEdit, QComboBox {
    padding: 6px;
}
QPushButton {
    padding: 7px 14px;
}
#sectionPanel, #metricCard, #listingCard, #statusPanel, #warningPanel, #errorPanel {
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

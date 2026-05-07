"""PySide6 GUI entry point."""

from __future__ import annotations

import os
import sys
from typing import Any

from pc_pricer.env_loader import default_env_path, load_env_file
from pc_pricer.gui_forms import (
    DEVICE_TYPES,
    FieldSpec,
    fields_for_device,
    validate_computer_mode,
    validate_device_type,
    validate_specs,
)
from pc_pricer.setup_credentials import write_credentials_env

LOADING_DELAY_MS = 700


try:  # pragma: no cover - exercised only when PySide6 is installed.
    from PySide6.QtCore import Qt, QTimer  # type: ignore[import-not-found]
    from PySide6.QtWidgets import (  # type: ignore[import-not-found]
        QApplication,
        QButtonGroup,
        QComboBox,
        QFormLayout,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QRadioButton,
        QScrollArea,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError:  # pragma: no cover - gives a clear runtime error.
    QApplication = None  # type: ignore[assignment]
    Qt = type("Qt", (), {"AlignCenter": 0})  # type: ignore[assignment]
    QButtonGroup = QComboBox = QFormLayout = QFrame = QHBoxLayout = QLabel = object  # type: ignore[assignment]
    QLineEdit = QMainWindow = QMessageBox = QPushButton = QRadioButton = object  # type: ignore[assignment]
    QScrollArea = QStackedWidget = QVBoxLayout = QWidget = object  # type: ignore[assignment]
    QTimer = type("QTimer", (), {"singleShot": staticmethod(lambda *_args: None)})  # type: ignore[assignment]


class GuiState:
    def __init__(self) -> None:
        self.device_type: str | None = None
        self.computer_mode: str | None = None
        self.specs: dict[str, Any] = {}


class MainWindow(QMainWindow):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CFS Price Compare")
        self.resize(940, 680)
        self.state = GuiState()
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

        load_env_file()
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
        QTimer.singleShot(LOADING_DELAY_MS, self.show_report)

    def show_report(self) -> None:
        self.report_page.refresh()
        self.stack.setCurrentWidget(self.report_page)

    def reset_for_new_device(self) -> None:
        self.state = GuiState()
        self.show_device_type()


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
        self.group = QButtonGroup(self)
        auto = QRadioButton("Auto-detect this PC")
        auto.setProperty("mode", "auto")
        manual = QRadioButton("Enter specs manually")
        manual.setProperty("mode", "manual")
        self.group.addButton(auto)
        self.group.addButton(manual)
        self.root.addWidget(auto)
        self.root.addWidget(manual)
        self.note = QLabel("Auto-detect will prefill editable specs in the next PR.")
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
        self.main_window.show_specs()


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
            self.error.setText("Auto-detected specs will appear here after the next GUI PR.")

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
        self.main_window.state.specs = {
            name: widget_value(widget)
            for name, widget in self.inputs.items()
            if widget_value(widget) != ""
        }


class LoadingPage(Page):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(window, "Searching", "Pricing will be wired in the next PR.")
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
            "Report Preview",
            "This placeholder will become the real pricing report in the next PR.",
        )
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.root.addWidget(self.summary)
        self.root.addStretch()
        buttons = QHBoxLayout()
        back = QPushButton("Back to Specs")
        back.clicked.connect(self.main_window.show_specs)
        another = QPushButton("Price Another Device")
        another.clicked.connect(self.main_window.reset_for_new_device)
        finish = QPushButton("Finish")
        finish.clicked.connect(self.main_window.close)
        buttons.addWidget(back)
        buttons.addStretch()
        buttons.addWidget(another)
        buttons.addWidget(finish)
        self.root.addLayout(buttons)

    def refresh(self) -> None:
        device = self.main_window.state.device_type or "device"
        parts = [f"{key}: {value}" for key, value in sorted(self.main_window.state.specs.items())]
        self.summary.setText(f"{device.title()} specs accepted.\n\n" + "\n".join(parts))


def credentials_present() -> bool:
    load_env_file()
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
        combo = QComboBox()
        combo.addItem("")
        combo.addItems(field.options)
        if value:
            index = combo.findText(str(value))
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
        return widget.currentText().strip()
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
        if widget is not None:
            widget.deleteLater()


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
"""


if __name__ == "__main__":
    main()

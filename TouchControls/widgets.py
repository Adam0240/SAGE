"""Dwell-friendly Qt controls shared by SAGE applications; no camera dependency."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QPushButton, QListWidget,
    QListWidgetItem, QWidget,
)


TOUCH_STYLE = """
    QDialog { background: black; color: white; }
    QLabel { color: white; font-size: 18px; }
    QLineEdit, QListWidget { background: #222222; color: white; font-size: 20px; }
    QListWidget::item { padding: 12px; }
    QListWidget::item:selected { background: #245a81; }
    QPushButton { background: #222222; color: white; border: 2px solid white;
                  border-radius: 8px; padding: 8px; font-size: 18px; }
    QPushButton:disabled { color: #777777; border-color: #777777; }
    QPushButton:checked { background: #245a81; }
"""


def scroll_controls(area, *, horizontal=False):
    controls = QWidget()
    layout = QHBoxLayout(controls)
    layout.setContentsMargins(0, 0, 0, 0)
    bar = area.horizontalScrollBar() if horizontal else area.verticalScrollBar()
    for text, direction in (("Left" if horizontal else "Up", -1),
                            ("Right" if horizontal else "Down", 1)):
        button = QPushButton(text)
        button.setMinimumSize(90, 44)
        button.setAccessibleName(f"Scroll {text.lower()}")
        button.clicked.connect(lambda checked=False, step=direction:
                               bar.setValue(bar.value() + step * max(1, bar.pageStep() // 2)))
        def update_button(*_, control=button, step=direction):
            control.setEnabled(bar.value() > bar.minimum() if step < 0 else bar.value() < bar.maximum())
        bar.valueChanged.connect(update_button)
        bar.rangeChanged.connect(update_button)
        update_button()
        layout.addWidget(button)
    return controls




class TouchChoices(QDialog):
    def __init__(self, combo):
        super().__init__(combo.window())
        self.setWindowTitle("Choose an option")
        self.setStyleSheet(TOUCH_STYLE)
        self.resize(600, 450)
        self.setProperty("sageTouchWindow", True)
        layout = QVBoxLayout(self)
        self.items = QListWidget()
        for row in range(combo.count()):
            item = QListWidgetItem(combo.itemText(row))
            item.setFlags(combo.model().index(row, combo.modelColumn(), combo.rootModelIndex()).flags())
            self.items.addItem(item)
        self.items.setCurrentRow(combo.currentIndex())
        layout.addWidget(self.items)
        layout.addWidget(scroll_controls(self.items))
        buttons = QHBoxLayout()
        self.select_button = QPushButton("Select")
        self.select_button.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(self.select_button)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        self.items.currentRowChanged.connect(self.update_selection)
        self.update_selection()

    def update_selection(self, *_):
        item = self.items.currentItem()
        self.select_button.setEnabled(bool(item and item.flags() & Qt.ItemFlag.ItemIsEnabled
                                           and item.flags() & Qt.ItemFlag.ItemIsSelectable))

    def accept(self):
        if self.select_button.isEnabled():
            super().accept()

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Drag a tab outside the tab widget; close its window to return it.

Tab reordering and dragging a detached window back onto the tab bar are
not implemented. Existing page widgets and their signal connections are reused.
"""

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QApplication, QMainWindow, QTabBar, QTabWidget


class DetachableTabBar(QTabBar):
    detach_requested = Signal(int, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pressed_index = -1
        self._press_position = QPoint()
        self._dragged = False

    def mousePressEvent(self, event):
        self._pressed_index = -1
        self._dragged = False
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.tabAt(event.position().toPoint())
            if index >= 0 and self.isTabEnabled(index):
                self._pressed_index = index
                self._press_position = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._pressed_index >= 0
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            distance = (
                event.globalPosition().toPoint() - self._press_position
            ).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self._dragged = True
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        index = self._pressed_index
        position = event.globalPosition().toPoint()
        tabs = self.parentWidget()
        outside = not tabs.rect().contains(tabs.mapFromGlobal(position))
        detach = (
            event.button() == Qt.MouseButton.LeftButton
            and index >= 0
            and self._dragged
            and outside
        )
        self._pressed_index = -1
        self._dragged = False
        super().mouseReleaseEvent(event)
        if detach:
            self.detach_requested.emit(index, position)


class DetachedTabWindow(QMainWindow):
    def __init__(self, tabs, page, title):
        super().__init__(tabs.window(), Qt.WindowType.Window)
        self._tabs = tabs
        self._page = page
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(title)
        self.setCentralWidget(page)

    def closeEvent(self, event):
        # Remove ownership before this window is deleted, preserving the page.
        page = self.takeCentralWidget()
        if page is not None:
            self._tabs.restore_tab(page)
        event.accept()


class DetachableTabWidget(QTabWidget):
    tabDetached = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._detached = {}
        self._restore_order = []
        bar = DetachableTabBar(self)
        self.setTabBar(bar)
        # Fixed ordering makes restoration deterministic for multiple windows.
        self.setMovable(False)
        bar.detach_requested.connect(self.detach_tab)

    def detach_tab(self, index, position):
        if not 0 <= index < self.count():
            return

        if not self._detached:
            self._restore_order = [self.widget(i) for i in range(self.count())]

        page = self.widget(index)
        metadata = {
            "title": self.tabText(index),
            "icon": self.tabIcon(index),
            "tooltip": self.tabToolTip(index),
            "whats_this": self.tabWhatsThis(index),
            "enabled": self.isTabEnabled(index),
        }
        size = page.size()
        self.removeTab(index)

        window = DetachedTabWindow(self, page, metadata["title"])
        self._detached[page] = (window, metadata)
        window.resize(max(size.width(), 400), max(size.height(), 300))
        window.move(position)
        window.show()
        page.show() 
        self.tabDetached.emit(page)

    def restore_tab(self, page):
        entry = self._detached.pop(page, None)
        if entry is None:
            return
        window, metadata = entry
        target = self._restore_order.index(page)
        insert_at = self.count()
        for index in range(self.count()):
            other = self.widget(index)
            if (
                other in self._restore_order
                and self._restore_order.index(other) > target
            ):
                insert_at = index
                break

        index = self.insertTab(
            insert_at, page, metadata["icon"], metadata["title"]
        )
        self.setTabToolTip(index, metadata["tooltip"])
        self.setTabWhatsThis(index, metadata["whats_this"])
        self.setTabEnabled(index, metadata["enabled"])
        self.setCurrentIndex(index)
        if not self._detached:
            self._restore_order.clear()

    def close_detached_windows(self):
        """Call from MainWindow.closeEvent before the main window closes."""
        for window, metadata in list(self._detached.values()):
            window.close()


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QLabel, QLineEdit, QVBoxLayout, QWidget

    class DemoWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Detachable tabs demo")
            self.resize(780, 640)
            self.tabs = DetachableTabWidget(self)
            for title in ("Main", "Temperature", "Vacuum", "Camera", "Comm"):
                page = QWidget()
                layout = QVBoxLayout(page)
                layout.addWidget(QLabel(title))
                field = QLineEdit()
                field.setPlaceholderText("Text is preserved after detaching")
                layout.addWidget(field)
                self.tabs.addTab(page, title)
            self.setCentralWidget(self.tabs)

        def closeEvent(self, event):
            self.tabs.close_detached_windows()
            super().closeEvent(event)

    app = QApplication(sys.argv)
    window = DemoWindow()
    window.show()
    sys.exit(app.exec())

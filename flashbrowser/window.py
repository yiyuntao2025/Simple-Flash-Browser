from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QStandardPaths, Qt, QUrl
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineScript,
    QWebEngineSettings,
    QWebEngineView,
)

from . import ruffle
from .page import BrowserPage
from .paths import app_root
from .search import (
    DEFAULT_SEARCH_ENGINE,
    SEARCH_ENGINES,
    SEARCH_ORDER,
    THEME_MODES,
    build_search_url,
    engine_label,
    is_windows_path,
    looks_like_url,
    normalize_engine,
)

APP_ROOT = app_root()
CHROME_HEIGHT = 100
FRAME_MARGIN = 6

DARK_THEME = """
QMenu {
    background: #141c29;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 10px;
    padding: 6px;
    color: #dbe6f7;
}
QMenu::item {
    padding: 6px 26px 6px 24px;
    border-radius: 6px;
}
QMenu::item:selected {
    background: rgba(255, 106, 61, 0.22);
    color: #ffffff;
}
QMenu::item:disabled {
    color: #64748b;
}
QMenu::separator {
    height: 1px;
    background: rgba(255, 255, 255, 0.08);
    margin: 5px 8px;
}
QToolTip {
    background: #141c29;
    color: #dbe6f7;
    border: 1px solid rgba(255, 255, 255, 0.14);
    padding: 5px 9px;
}
QMessageBox, QDialog {
    background: #111823;
    color: #dbe6f7;
}
QMessageBox QLabel {
    color: #dbe6f7;
}
QPushButton {
    background: #1d2839;
    color: #dbe6f7;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    padding: 6px 18px;
}
QPushButton:hover {
    background: #26344a;
}
"""

LIGHT_THEME = """
QMenu {
    background: #ffffff;
    border: 1px solid rgba(15, 23, 42, 0.14);
    border-radius: 10px;
    padding: 6px;
    color: #1b2a44;
}
QMenu::item {
    padding: 6px 26px 6px 24px;
    border-radius: 6px;
}
QMenu::item:selected {
    background: rgba(255, 106, 61, 0.16);
    color: #0b1526;
}
QMenu::item:disabled {
    color: #98a6ba;
}
QMenu::separator {
    height: 1px;
    background: rgba(15, 23, 42, 0.1);
    margin: 5px 8px;
}
QToolTip {
    background: #ffffff;
    color: #1b2a44;
    border: 1px solid rgba(15, 23, 42, 0.16);
    padding: 5px 9px;
}
QMessageBox, QDialog {
    background: #f6f8fc;
    color: #1b2a44;
}
QMessageBox QLabel {
    color: #1b2a44;
}
QPushButton {
    background: #eef2f9;
    color: #1b2a44;
    border: 1px solid rgba(15, 23, 42, 0.14);
    border-radius: 8px;
    padding: 6px 18px;
}
QPushButton:hover {
    background: #e2e8f4;
}
"""


def apply_theme(app: QtWidgets.QApplication, dark: bool = True) -> None:
    app.setStyleSheet(DARK_THEME if dark else LIGHT_THEME)


def _build_app_icon() -> QtGui.QIcon:
    size = 64
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    gradient = QtGui.QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QtGui.QColor("#ff8a3d"))
    gradient.setColorAt(1.0, QtGui.QColor("#ff2d6f"))
    painter.setPen(Qt.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(2, 2, size - 4, size - 4, 17, 17)
    font = QtGui.QFont("Segoe UI", 32, QtGui.QFont.Black)
    painter.setFont(font)
    painter.setPen(QtGui.QColor("#ffffff"))
    painter.drawText(QtCore.QRect(0, -1, size, size), Qt.AlignCenter, "F")
    painter.end()
    return QtGui.QIcon(pixmap)


def _icon_to_data_url(icon: QtGui.QIcon) -> str:
    if icon is None or icon.isNull():
        return ""
    pixmap = icon.pixmap(32, 32)
    if pixmap.isNull():
        return ""
    data = QtCore.QByteArray()
    buffer = QtCore.QBuffer(data)
    buffer.open(QtCore.QIODevice.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    return "data:image/png;base64," + base64.b64encode(bytes(data)).decode("ascii")


def _style_native_window(hwnd: int, dark: bool = True) -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        dwm = ctypes.windll.dwmapi
        value = ctypes.c_int(1 if dark else 0)
        for attribute in (20, 19):
            dwm.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
        corner = ctypes.c_int(2)
        dwm.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), 33, ctypes.byref(corner), ctypes.sizeof(corner)
        )
    except Exception:
        pass


class _Frame(QtWidgets.QWidget):
    def __init__(self, window, margin: int = FRAME_MARGIN, background: str = "#070b11"):
        super().__init__(window)
        self.window = window
        self.margin = margin
        self._background = QtGui.QColor(background)
        self.setMouseTracking(True)

    def set_background(self, color: str):
        self._background = QtGui.QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), self._background)
        painter.end()

    def _edges(self, pos):
        margin = self.margin
        rect = self.rect()
        edges = Qt.Edges()
        if pos.x() <= margin:
            edges |= Qt.LeftEdge
        elif pos.x() >= rect.width() - margin:
            edges |= Qt.RightEdge
        if pos.y() <= margin:
            edges |= Qt.TopEdge
        elif pos.y() >= rect.height() - margin:
            edges |= Qt.BottomEdge
        return edges

    def _cursor_for(self, edges):
        corners = (
            (Qt.LeftEdge | Qt.TopEdge, Qt.SizeFDiagCursor),
            (Qt.RightEdge | Qt.BottomEdge, Qt.SizeFDiagCursor),
            (Qt.RightEdge | Qt.TopEdge, Qt.SizeBDiagCursor),
            (Qt.LeftEdge | Qt.BottomEdge, Qt.SizeBDiagCursor),
        )
        for combo, cursor in corners:
            if edges == combo:
                return cursor
        if edges & (Qt.LeftEdge | Qt.RightEdge):
            return Qt.SizeHorCursor
        if edges & (Qt.TopEdge | Qt.BottomEdge):
            return Qt.SizeVerCursor
        return Qt.ArrowCursor

    def mouseMoveEvent(self, event):
        if self.window.isMaximized():
            self.unsetCursor()
        else:
            self.setCursor(self._cursor_for(self._edges(event.pos())))
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.unsetCursor()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        edges = self._edges(event.pos())
        if event.button() == Qt.LeftButton and edges and not self.window.isMaximized():
            handle = self.window.windowHandle()
            if handle is not None:
                handle.startSystemResize(edges)
            event.accept()
            return
        super().mousePressEvent(event)


class ChromePage(QWebEnginePage):
    def __init__(self, profile, owner, base: str):
        super().__init__(profile, owner)
        self.owner = owner
        self.base = base

    def acceptNavigationRequest(self, url, navtype, isMainFrame):
        if isMainFrame and not url.toString().startswith(self.base):
            return False
        return super().acceptNavigationRequest(url, navtype, isMainFrame)

    def javaScriptConsoleMessage(self, level, message, line, source):
        pass


class ChromeBridge(QtCore.QObject):
    stateChanged = QtCore.pyqtSignal(str)

    def __init__(self, window):
        super().__init__(window)
        self.window = window

    @QtCore.pyqtSlot()
    def request_state(self):
        self.window._emit_state()

    @QtCore.pyqtSlot()
    def new_tab(self):
        self.window.new_tab()

    @QtCore.pyqtSlot(int)
    def close_tab(self, index):
        self.window.close_tab(index)

    @QtCore.pyqtSlot(int)
    def select_tab(self, index):
        self.window.select_tab(index)

    @QtCore.pyqtSlot(str)
    def navigate(self, text):
        self.window.navigate(text)

    @QtCore.pyqtSlot()
    def go_back(self):
        self.window._go_back()

    @QtCore.pyqtSlot()
    def go_forward(self):
        self.window._go_forward()

    @QtCore.pyqtSlot()
    def reload(self):
        self.window._reload()

    @QtCore.pyqtSlot()
    def stop(self):
        view = self.window.current_view()
        if view is not None:
            view.stop()

    @QtCore.pyqtSlot()
    def go_home(self):
        self.window._go_home()

    @QtCore.pyqtSlot()
    def open_file(self):
        self.window._open_file()

    @QtCore.pyqtSlot()
    def show_menu(self):
        self.window._show_app_menu()

    @QtCore.pyqtSlot()
    def toggle_theme(self):
        self.window._toggle_theme()

    @QtCore.pyqtSlot()
    def toggle_ruffle(self):
        self.window.act_ruffle.setChecked(not self.window.act_ruffle.isChecked())

    @QtCore.pyqtSlot()
    def minimize(self):
        self.window.showMinimized()

    @QtCore.pyqtSlot()
    def toggle_maximize(self):
        self.window._toggle_maximize()

    @QtCore.pyqtSlot()
    def close_window(self):
        self.window.close()

    @QtCore.pyqtSlot()
    def start_drag(self):
        self.window._start_drag()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, server, flash):
        super().__init__()
        self.server = server
        self.flash = flash
        self.use_ruffle = not flash.available
        self._ruffle_script = None
        self._native_style_applied = False
        self._fullscreen = False
        self._state_timer = QtCore.QTimer(self)
        self._state_timer.setSingleShot(True)
        self._state_timer.timeout.connect(self._emit_state)

        self.settings = QtCore.QSettings("FlashBrowser", "FlashBrowser")
        theme_mode = str(self.settings.value("theme", "system"))
        self.theme_mode = theme_mode if theme_mode in THEME_MODES else "system"
        self.search_engine = normalize_engine(
            str(self.settings.value("searchEngine", DEFAULT_SEARCH_ENGINE))
        )
        self.theme_dark = self._effective_dark()
        app = QtWidgets.QApplication.instance()
        apply_theme(app, self.theme_dark)
        if app is not None:
            app.paletteChanged.connect(self._on_palette_changed)

        self.setWindowTitle("Flash Browser")
        self.setWindowIcon(_build_app_icon())
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinMaxButtonsHint
        )
        self.setMinimumSize(780, 520)
        self._resize_to_screen()

        self._setup_profile()
        self._setup_actions()
        self._setup_ui()
        self.add_tab(QUrl(self._home_url()))

    def _resize_to_screen(self):
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is None:
            self.resize(1280, 840)
            return
        rect = screen.availableGeometry()
        width = min(1320, max(780, rect.width() - 160))
        height = min(880, max(520, rect.height() - 140))
        self.resize(width, height)
        self.move(
            rect.center().x() - width // 2,
            rect.center().y() - height // 2,
        )

    def _system_is_dark(self) -> bool:
        if sys.platform.startswith("win"):
            try:
                import winreg

                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                ) as key:
                    value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                    return int(value) == 0
            except OSError:
                pass
        palette = QtWidgets.QApplication.palette()
        return palette.color(QtGui.QPalette.Window).lightness() < 128

    def _effective_dark(self) -> bool:
        if self.theme_mode == "dark":
            return True
        if self.theme_mode == "light":
            return False
        return self._system_is_dark()

    def _theme_value(self) -> str:
        return "dark" if self.theme_dark else "light"

    def _frame_color(self) -> str:
        return "#070b11" if self.theme_dark else "#e3e9f4"

    def _chrome_background(self) -> str:
        return "#0b111a" if self.theme_dark else "#eef2f9"

    def _toggle_theme(self):
        self._set_theme_mode("light" if self.theme_dark else "dark")

    def _set_theme_mode(self, mode: str):
        if mode not in THEME_MODES:
            mode = "system"
        self.theme_mode = mode
        self.settings.setValue("theme", mode)
        self._apply_theme_visuals()

    def _apply_theme_visuals(self):
        self.theme_dark = self._effective_dark()
        app = QtWidgets.QApplication.instance()
        apply_theme(app, self.theme_dark)
        if hasattr(self, "frame"):
            self.frame.set_background(self._frame_color())
        if hasattr(self, "chrome_page"):
            self.chrome_page.setBackgroundColor(
                QtGui.QColor(self._chrome_background())
            )
        if self._native_style_applied:
            _style_native_window(int(self.winId()), self.theme_dark)
        self._update_theme_actions()
        if hasattr(self, "stack"):
            for index in range(self.stack.count()):
                self._apply_local_preferences(self.stack.widget(index))
        self._push_state()

    def _on_palette_changed(self):
        if self.theme_mode == "system":
            QtCore.QTimer.singleShot(0, self._sync_system_theme)

    def _sync_system_theme(self):
        if self.theme_mode != "system":
            return
        if self._system_is_dark() != self.theme_dark:
            self._apply_theme_visuals()

    def _update_theme_actions(self):
        for mode, action in getattr(self, "theme_actions", {}).items():
            action.blockSignals(True)
            action.setChecked(mode == self.theme_mode)
            action.blockSignals(False)

    def _set_search_engine(self, key: str):
        key = normalize_engine(key)
        if key == self.search_engine:
            return
        self.search_engine = key
        self.settings.setValue("searchEngine", key)
        self._update_engine_actions()
        if hasattr(self, "stack"):
            for index in range(self.stack.count()):
                self._apply_local_preferences(self.stack.widget(index))
        self._push_state()

    def _update_engine_actions(self):
        for key, action in getattr(self, "engine_actions", {}).items():
            action.blockSignals(True)
            action.setChecked(key == self.search_engine)
            action.blockSignals(False)

    def _apply_local_preferences(self, view):
        if view is None:
            return
        if not view.url().toString().startswith(self.server.base):
            return
        theme = json.dumps(self._theme_value())
        engine = json.dumps(self.search_engine)
        script = (
            "if (window.__setTheme) { window.__setTheme(%s); }"
            "if (window.__setEngine) { window.__setEngine(%s); }" % (theme, engine)
        )
        view.page().runJavaScript(script)

    def _setup_profile(self):
        base = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
        profile_dir = base / "profile"
        cache_dir = base / "cache"
        profile_dir.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)

        self.profile = QWebEngineProfile("flashbrowser", self)
        self.profile.setPersistentStoragePath(str(profile_dir))
        self.profile.setCachePath(str(cache_dir))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        self.profile.setHttpCacheType(QWebEngineProfile.DiskHttpCache)
        self.profile.downloadRequested.connect(self._on_download)
        if self.use_ruffle:
            self._install_ruffle()

    def _install_ruffle(self):
        if self._ruffle_script is not None:
            return
        script = QWebEngineScript()
        script.setName("flashassist-ruffle")
        script.setSourceCode(ruffle.bootstrap_script(self.server.port, self.server.base))
        script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        script.setWorldId(QWebEngineScript.MainWorld)
        script.setRunsOnSubFrames(True)
        self.profile.scripts().insert(script)
        self._ruffle_script = script

    def _uninstall_ruffle(self):
        if self._ruffle_script is None:
            return
        self.profile.scripts().remove(self._ruffle_script)
        self._ruffle_script = None

    def _setup_actions(self):
        self.act_back = QtWidgets.QAction("后退", self)
        self.act_back.setShortcut(QtGui.QKeySequence("Alt+Left"))
        self.act_back.triggered.connect(self._go_back)

        self.act_forward = QtWidgets.QAction("前进", self)
        self.act_forward.setShortcut(QtGui.QKeySequence("Alt+Right"))
        self.act_forward.triggered.connect(self._go_forward)

        self.act_reload = QtWidgets.QAction("重新加载", self)
        self.act_reload.setShortcuts(
            [QtGui.QKeySequence("F5"), QtGui.QKeySequence("Ctrl+R")]
        )
        self.act_reload.triggered.connect(self._reload)

        self.act_home = QtWidgets.QAction("主页", self)
        self.act_home.setShortcut(QtGui.QKeySequence("Alt+Home"))
        self.act_home.triggered.connect(self._go_home)

        self.act_new_tab = QtWidgets.QAction("新建标签页", self)
        self.act_new_tab.setShortcut(QtGui.QKeySequence("Ctrl+T"))
        self.act_new_tab.triggered.connect(self.new_tab)

        self.act_open = QtWidgets.QAction("打开文件", self)
        self.act_open.setShortcut(QtGui.QKeySequence("Ctrl+O"))
        self.act_open.triggered.connect(self._open_file)

        self.act_close_tab = QtWidgets.QAction("关闭标签页", self)
        self.act_close_tab.setShortcut(QtGui.QKeySequence("Ctrl+W"))
        self.act_close_tab.triggered.connect(
            lambda: self.close_tab(self.stack.currentIndex())
        )

        self.act_quit = QtWidgets.QAction("退出", self)
        self.act_quit.setShortcut(QtGui.QKeySequence("Ctrl+Q"))
        self.act_quit.triggered.connect(self.close)

        self.act_ruffle = QtWidgets.QAction("使用 Ruffle 模拟 Flash", self)
        self.act_ruffle.setCheckable(True)
        self.act_ruffle.blockSignals(True)
        self.act_ruffle.setChecked(self.use_ruffle)
        self.act_ruffle.blockSignals(False)
        self.act_ruffle.toggled.connect(self._toggle_ruffle)

        self.act_flash_dir = QtWidgets.QAction("打开 pepperflash 目录", self)
        self.act_flash_dir.triggered.connect(self._open_flash_dir)

        self.act_about = QtWidgets.QAction("关于 Flash Browser", self)
        self.act_about.triggered.connect(self._about)

        self.act_focus = QtWidgets.QAction("定位地址栏", self)
        self.act_focus.setShortcut(QtGui.QKeySequence("Ctrl+L"))
        self.act_focus.triggered.connect(self._focus_address)
        self.addAction(self.act_focus)

        self.engine_group = QtWidgets.QActionGroup(self)
        self.engine_group.setExclusive(True)
        self.engine_actions = {}
        for key in SEARCH_ORDER:
            action = QtWidgets.QAction(SEARCH_ENGINES[key]["label"], self)
            action.setCheckable(True)
            action.setChecked(key == self.search_engine)
            action.triggered.connect(
                lambda checked, k=key: checked and self._set_search_engine(k)
            )
            self.engine_group.addAction(action)
            self.engine_actions[key] = action

        self.theme_group = QtWidgets.QActionGroup(self)
        self.theme_group.setExclusive(True)
        self.theme_actions = {}
        theme_labels = {"system": "跟随系统", "light": "浅色", "dark": "深色"}
        for mode in THEME_MODES:
            action = QtWidgets.QAction(theme_labels[mode], self)
            action.setCheckable(True)
            action.setChecked(mode == self.theme_mode)
            action.triggered.connect(
                lambda checked, m=mode: checked and self._set_theme_mode(m)
            )
            self.theme_group.addAction(action)
            self.theme_actions[mode] = action

    def _setup_ui(self):
        self.frame = _Frame(self, background=self._frame_color())
        layout = QtWidgets.QVBoxLayout(self.frame)
        layout.setContentsMargins(FRAME_MARGIN, FRAME_MARGIN, FRAME_MARGIN, FRAME_MARGIN)
        layout.setSpacing(0)

        self.chrome_view = QWebEngineView(self.frame)
        self.chrome_view.setFixedHeight(CHROME_HEIGHT)
        self.chrome_view.setContextMenuPolicy(Qt.NoContextMenu)
        self.chrome_page = ChromePage(self.profile, self, self.server.base)
        self.chrome_page.setBackgroundColor(QtGui.QColor(self._chrome_background()))
        self.chrome_view.setPage(self.chrome_page)
        self.chrome_view.loadFinished.connect(self._on_chrome_loaded)

        self.channel = QWebChannel(self.chrome_page)
        self.bridge = ChromeBridge(self)
        self.channel.registerObject("bridge", self.bridge)
        self.chrome_page.setWebChannel(self.channel)

        self.stack = QtWidgets.QStackedWidget(self.frame)
        self.stack.currentChanged.connect(self._on_current_changed)

        layout.addWidget(self.chrome_view)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(self.frame)

        self.chrome_view.setUrl(
            QUrl(self.server.base + "/chrome?theme=" + self._theme_value())
        )

    def _on_chrome_loaded(self, ok):
        if ok:
            QtCore.QTimer.singleShot(60, self._focus_address)

    def _home_url(self) -> str:
        params = {
            "flash": "1" if self.flash.available else "0",
            "version": self.flash.version,
            "path": str(self.flash.path) if self.flash.path else "",
            "source": self.flash.source,
            "hint": self.flash.hint,
            "ruffle": "1" if self.use_ruffle else "0",
            "theme": self._theme_value(),
            "engine": self.search_engine,
            "engineLabel": engine_label(self.search_engine),
        }
        return self.server.home_url(params)

    def _apply_settings(self, view):
        settings = view.settings()
        settings.setAttribute(QWebEngineSettings.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.AllowRunningInsecureContent, True)

    def new_tab(self):
        self.add_tab(QUrl(self._home_url()))

    def add_tab(self, url: QUrl | None = None, background: bool = False):
        view = QWebEngineView()
        page = BrowserPage(self.profile, self, self.flash)
        page.view = view
        view.setPage(page)
        view.setProperty("_icon_data", "")
        view.setProperty("_loading", False)
        self._apply_settings(view)

        index = self.stack.addWidget(view)
        if not background:
            self.stack.setCurrentIndex(index)

        view.titleChanged.connect(lambda title, v=view: self._on_title(v, title))
        view.iconChanged.connect(lambda icon, v=view: self._on_icon(v, icon))
        view.urlChanged.connect(lambda changed, v=view: self._on_view_url(v, changed))
        view.loadStarted.connect(lambda v=view: self._on_load_started(v))
        view.loadFinished.connect(lambda ok, v=view: self._on_load_finished(v, ok))
        page.fullScreenRequested.connect(self._on_fullscreen_request)

        if url is not None:
            view.setUrl(url)
        self._push_state()
        return view

    def current_view(self):
        return self.stack.currentWidget()

    def _view_for_page(self, page):
        for index in range(self.stack.count()):
            view = self.stack.widget(index)
            if view.page() is page:
                return view
        return None

    def _on_title(self, view, title):
        if view is self.current_view():
            self.setWindowTitle(f"{title or '新标签页'} — Flash Browser")
        self._push_state()

    def _on_icon(self, view, icon):
        view.setProperty("_icon_data", _icon_to_data_url(icon))
        self._push_state()

    def _on_view_url(self, view, url):
        if view is self.current_view():
            self._push_state()

    def _on_current_changed(self, index):
        view = self.current_view()
        if view is None:
            self.act_back.setEnabled(False)
            self.act_forward.setEnabled(False)
        else:
            self._update_nav_actions(view)
            self.setWindowTitle(f"{view.title() or '新标签页'} — Flash Browser")
        self._push_state()

    def _update_nav_actions(self, view):
        history = view.history()
        self.act_back.setEnabled(history.canGoBack())
        self.act_forward.setEnabled(history.canGoForward())

    def _on_load_started(self, view):
        view.setProperty("_loading", True)
        self._push_state()

    def _on_load_finished(self, view, ok):
        view.setProperty("_loading", False)
        if view is self.current_view():
            self._update_nav_actions(view)
        self._apply_local_preferences(view)
        self._push_state()

    def select_tab(self, index: int):
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)

    def navigate(self, text: str):
        text = (text or "").strip()
        if not text:
            return
        view = self.current_view() or self.add_tab()
        if text.lower().startswith("flashbrowser://"):
            view.setUrl(QUrl(self._home_url()))
            return
        if is_windows_path(text):
            view.setUrl(QUrl.fromLocalFile(text))
            return
        if looks_like_url(text):
            view.setUrl(QUrl.fromUserInput(text))
            return
        view.setUrl(QUrl(build_search_url(text, self.search_engine)))

    def _push_state(self):
        if not self._state_timer.isActive():
            self._state_timer.start(0)

    def _emit_state(self):
        view = self.current_view()
        tabs = []
        for index in range(self.stack.count()):
            item = self.stack.widget(index)
            tabs.append(
                {
                    "title": item.title() or "新标签页",
                    "icon": item.property("_icon_data") or "",
                    "loading": bool(item.property("_loading")),
                }
            )

        if self.flash.available:
            status_class = "ok"
            status_text = f"Flash {self.flash.version}"
            status_title = f"原生 Flash {self.flash.version}\n{self.flash.path}"
            if self.use_ruffle:
                status_text += " · Ruffle"
                status_title += "\nRuffle 模拟已启用"
        elif self.use_ruffle:
            status_class = "warn"
            status_text = "Ruffle 模拟"
            status_title = "已启用内置 Ruffle 开源 Flash 模拟器"
        else:
            status_class = "off"
            status_text = "无 Flash"
            status_title = "未检测到 Flash，Ruffle 已关闭"

        display_url = view.url().toString() if view is not None else ""
        if display_url.startswith(self.server.base + "/home"):
            display_url = "flashbrowser://home"

        state = {
            "tabs": tabs,
            "active": self.stack.currentIndex(),
            "url": display_url,
            "canBack": bool(view is not None and view.history().canGoBack()),
            "canForward": bool(view is not None and view.history().canGoForward()),
            "loading": bool(view.property("_loading")) if view is not None else False,
            "maximized": self.isMaximized(),
            "statusClass": status_class,
            "statusText": status_text,
            "statusTitle": status_title,
            "ruffle": self.use_ruffle,
            "theme": self._theme_value(),
            "themeMode": self.theme_mode,
            "searchEngine": self.search_engine,
            "searchLabel": engine_label(self.search_engine),
        }
        self.bridge.stateChanged.emit(json.dumps(state, ensure_ascii=False))

    def _go_back(self):
        view = self.current_view()
        if view is not None:
            view.back()

    def _go_forward(self):
        view = self.current_view()
        if view is not None:
            view.forward()

    def _reload(self):
        view = self.current_view()
        if view is not None:
            view.reload()

    def _go_home(self):
        view = self.current_view()
        if view is None:
            return
        self.use_ruffle = self.act_ruffle.isChecked()
        view.setUrl(QUrl(self._home_url()))

    def _focus_address(self):
        self.chrome_view.page().runJavaScript(
            "window.__focusAddress && window.__focusAddress();"
        )

    def _open_file(self):
        start_dir = str(Path.home())
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "打开 Flash 或网页文件",
            start_dir,
            "Flash 影片 (*.swf);;网页 (*.html *.htm *.xhtml);;所有文件 (*.*)",
        )
        if not path:
            return
        view = self.current_view()
        if view is None:
            view = self.add_tab()
        view.setUrl(QUrl.fromLocalFile(path))

    def open_swf(self, url, page=None):
        target = url if isinstance(url, QUrl) else QUrl(url)
        view = self._view_for_page(page) if page is not None else None
        view = view or self.current_view()
        if view is None:
            return
        if target.isLocalFile():
            local_path = target.toLocalFile()
            src = self.server.proxy_url_for_file(local_path)
            name = Path(local_path).name
        else:
            src = self.server.proxy_url_for_remote(target.toString())
            name = Path(target.path()).name or "flash.swf"
        view.setUrl(QUrl(self.server.viewer_url(src, name, self._theme_value())))

    def _toggle_ruffle(self, enabled):
        self.use_ruffle = bool(enabled)
        if self.use_ruffle:
            self._install_ruffle()
        else:
            self._uninstall_ruffle()
        self._push_state()
        view = self.current_view()
        if view is not None:
            if view.url().toString().startswith(self.server.base + "/home"):
                view.setUrl(QUrl(self._home_url()))
            else:
                view.reload()

    def _open_flash_dir(self):
        folder = APP_ROOT / "pepperflash"
        folder.mkdir(parents=True, exist_ok=True)
        QtGui.QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _show_app_menu(self):
        menu = getattr(self, "_app_menu", None)
        if menu is None:
            menu = QtWidgets.QMenu(self)
            menu.addAction(self.act_new_tab)
            menu.addAction(self.act_open)
            menu.addSeparator()

            engines_menu = menu.addMenu("搜索引擎")
            engines_menu.addActions(list(self.engine_actions.values()))

            appearance_menu = menu.addMenu("外观")
            appearance_menu.addActions(list(self.theme_actions.values()))

            menu.addSeparator()
            menu.addAction(self.act_ruffle)
            menu.addAction(self.act_flash_dir)
            menu.addSeparator()
            menu.addAction(self.act_about)
            menu.addAction(self.act_quit)
            self._app_menu = menu
        menu.popup(QtGui.QCursor.pos())

    def _start_drag(self):
        if self.isMaximized():
            return
        handle = self.windowHandle()
        if handle is not None:
            handle.startSystemMove()

    def _on_fullscreen_request(self, request):
        request.accept()
        if request.toggleOn():
            self._fullscreen = True
            self.chrome_view.hide()
            self.frame.layout().setContentsMargins(0, 0, 0, 0)
            self.showFullScreen()
        else:
            self._exit_fullscreen()

    def _exit_fullscreen(self):
        if not self._fullscreen:
            return
        self._fullscreen = False
        self.frame.layout().setContentsMargins(
            FRAME_MARGIN, FRAME_MARGIN, FRAME_MARGIN, FRAME_MARGIN
        )
        self.chrome_view.show()
        self.showNormal()
        self._push_state()

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _on_download(self, item):
        downloads = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
        base_dir = Path(downloads) if downloads else Path.home() / "Downloads"
        suggested = item.suggestedFileName() or "download.bin"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "保存文件", str(base_dir / suggested)
        )
        if not path:
            item.cancel()
            return
        item.setPath(path)
        item.accept()
        item.finished.connect(lambda: self._notify("下载完成"))

    def _notify(self, text: str):
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), text, self)

    def close_tab(self, index: int):
        if index < 0 or index >= self.stack.count():
            return
        if self.stack.count() <= 1:
            self.close()
            return
        view = self.stack.widget(index)
        self.stack.removeWidget(view)
        if view is not None:
            view.deleteLater()
        self._push_state()

    def _about(self):
        QtWidgets.QMessageBox.about(
            self,
            "关于 Flash Browser",
            "<h3 style='margin:0 0 8px'>Flash Browser</h3>"
            "<p style='color:#9fb0c8;line-height:1.7'>基于 Qt WebEngine 5.15.2"
            "（Chromium 83，原生支持 Pepper Flash 的 Chromium 分支）。</p>"
            "<p style='color:#9fb0c8;line-height:1.7'>原生 Flash 需要 64 位 "
            "pepflashplayer.dll；未检测到时自动使用 Ruffle 开源模拟器。</p>",
        )

    def showEvent(self, event):
        super().showEvent(event)
        if not self._native_style_applied:
            self._native_style_applied = True
            QtCore.QTimer.singleShot(
                0,
                lambda: _style_native_window(int(self.winId()), self.theme_dark),
            )
        else:
            _style_native_window(int(self.winId()), self.theme_dark)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.WindowStateChange:
            self._push_state()
        elif event.type() == QtCore.QEvent.WindowActivate:
            self._sync_system_theme()

    def closeEvent(self, event):
        super().closeEvent(event)

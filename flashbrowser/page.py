from __future__ import annotations

from PyQt5.QtWebEngineWidgets import QWebEnginePage


class BrowserPage(QWebEnginePage):
    def __init__(self, profile, owner, flash):
        super().__init__(profile, owner)
        self.owner = owner
        self.flash = flash
        self.view = None

    def acceptNavigationRequest(self, url, navtype, isMainFrame):
        if isMainFrame and not self.flash.available:
            scheme = url.scheme().lower()
            if scheme in ("http", "https", "file") and url.path().lower().endswith(".swf"):
                self.owner.open_swf(url, self)
                return False
        return super().acceptNavigationRequest(url, navtype, isMainFrame)

    def createWindow(self, wintype):
        return self.owner.add_tab(background=True).page()

    def certificateError(self, error):
        return True

    def javaScriptConsoleMessage(self, level, message, line, source):
        pass

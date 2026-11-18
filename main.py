import os
import sys
from pathlib import Path

if "__compiled__" in globals():
    ROOT = Path(sys.executable).resolve().parent
    os.chdir(ROOT)
else:
    ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from flashbrowser.flash import configure_environment, find_pepper_flash

    flash = find_pepper_flash()
    configure_environment(flash)

    from PyQt5 import QtCore, QtWidgets

    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts, True)
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("FlashBrowser")
    app.setApplicationDisplayName("Flash Browser")
    app.setOrganizationName("FlashBrowser")

    from flashbrowser.server import AssetServer
    from flashbrowser.window import MainWindow

    server = AssetServer(ROOT / "assets")
    handle = QtCore.QFile(":/qtwebchannel/qwebchannel.js")
    if handle.open(QtCore.QIODevice.ReadOnly):
        server.qwebchannel_script = bytes(handle.readAll()).decode("utf-8")
        handle.close()
    server.start()
    window = MainWindow(server, flash)
    window.show()

    code = app.exec_()
    server.stop()
    return code


if __name__ == "__main__":
    raise SystemExit(main())

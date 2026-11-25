# -*- mode: python ; coding: utf-8 -*-
"""Silüet — PyInstaller paket tanımı (Linux ve Windows, yalnız grafik arayüz).

Linux'ta masaüstünün kendi sistem kütüphaneleri (libstdc++, X11/xcb, Wayland, GTK, fontconfig,
dbus, ...) pakete KONMAZ: derleme makinesinin eski kopyaları yeni dağıtımlarda (Arch/CachyOS
gibi) grafik sürücüleriyle çakışıp uygulamanın açılmamasına yol açar. Qt'nin kendi
kütüphaneleri (PySide6 tekerleğinden) ve Python pakete dahildir.
"""
import re
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
NAME = "Siluet"

QT_MODULE_EXCLUDES = [
    "PySide6." + m for m in (
        "QtWebEngineCore", "QtWebEngineWidgets", "QtWebEngineQuick", "QtWebChannel", "QtQml", "QtQuick",
        "QtQuick3D", "QtQuickWidgets", "QtQuickControls2", "Qt3DCore", "Qt3DRender", "Qt3DInput", "Qt3DLogic",
        "Qt3DAnimation", "Qt3DExtras", "QtMultimedia", "QtMultimediaWidgets", "QtCharts", "QtDataVisualization",
        "QtGraphs", "QtPdf", "QtPdfWidgets", "QtBluetooth", "QtNfc", "QtPositioning", "QtLocation", "QtSensors",
        "QtSerialPort", "QtSql", "QtTest", "QtNetwork", "QtOpenGLWidgets", "QtSvgWidgets", "QtDesigner",
        "QtHelp", "QtUiTools", "QtXml", "QtRemoteObjects", "QtScxml", "QtSpatialAudio", "QtTextToSpeech",
        "QtWebSockets", "QtHttpServer", "QtStateMachine", "QtConcurrent", "QtPrintSupport",
    )
] + ["tkinter", "pytest", "pytestqt"]

# Kullanılmayan Qt eklentileri ve bunların sürüklediği Qt kütüphaneleri.
DROP_PATTERNS = [
    r"plugins/platforms/lib(qeglfs|qlinuxfb|qvnc|qvkkhrdisplay|qminimalegl)\.so",
    r"plugins/egldeviceintegrations/", r"plugins/platformthemes/libqgtk3\.so",
    r"plugins/platforminputcontexts/libqtvirtualkeyboardplugin\.so", r"plugins/imageformats/libqpdf\.so",
    r"libQt6(Qml|QmlMeta|QmlModels|QmlWorkerScript|Quick|VirtualKeyboard|VirtualKeyboardQml|Pdf|"
    r"EglFSDeviceIntegration|EglFsKmsSupport|Network)\.so",
    r"(^|/)Qt6(Qml|Quick|VirtualKeyboard|Pdf|Network)\w*\.dll$",
    r"plugins/(platforms/q(minimal|direct2d)\.dll|platforminputcontexts/qtvirtualkeyboardplugin\.dll|imageformats/qpdf\.dll)",
]

# Linux: bu sistem kütüphaneleri her masaüstünde vardır ve host sürümü kullanılmalıdır.
LINUX_HOST_LIBS = re.compile(
    r"^lib(stdc\+\+|gcc_s|X11|X11-xcb|Xau|Xdmcp|Xext|Xfixes|Xi|Xinerama|Xrandr|Xrender|Xcursor|Xcomposite|"
    r"Xdamage|xcb[-\w]*|xkbcommon[-\w]*|wayland-[\w-]+|EGL|GL|GLX|GLdispatch|OpenGL|drm|gbm|"
    r"fontconfig|freetype|expat|glib-2\.0|gio-2\.0|gobject-2\.0|gmodule-2\.0|gthread-2\.0|gtk-3|gdk-3|"
    r"gdk_pixbuf-2\.0|cairo|cairo-gobject|pango-1\.0|pangocairo-1\.0|pangoft2-1\.0|atk-1\.0|atk-bridge-2\.0|"
    r"atspi|harfbuzz|graphite2|fribidi|thai|datrie|pixman-1|epoxy|png16|jpeg|dbus-1|systemd|udev|"
    r"selinux|mount|blkid|pcre2-8|cap|gcrypt|gpg-error|lz4|lzma|zstd|bz2|z|brotli\w*|bsd|md|"
    r"krb5|krb5support|k5crypto|gssapi_krb5|com_err|keyutils)\.so"
)


def _keep(dest: str) -> bool:
    posix = dest.replace("\\", "/")
    if any(re.search(pattern, posix) for pattern in DROP_PATTERNS):
        return False
    if sys.platform.startswith("linux") and "/" not in posix and LINUX_HOST_LIBS.match(posix):
        return False
    return True


a = Analysis(
    [str(ROOT / "tools" / "launch_gui.py")],
    pathex=[str(ROOT)],
    excludes=QT_MODULE_EXCLUDES,
    datas=[(str(ROOT / "siluet" / "ui" / "assets"), "siluet/ui/assets")],
    noarchive=False,
)
a.binaries = [entry for entry in a.binaries if _keep(entry[0])]
a.datas = [entry for entry in a.datas if _keep(entry[0])]

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name=NAME,
    console=False,
    icon=str(ROOT / "packaging" / "icon.ico") if sys.platform == "win32" else None,
    strip=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=NAME)

# Build on the target OS; Windows executables cannot be built on Linux.
from pathlib import Path
root = Path(SPECPATH)
a = Analysis(
    [str(root / 'scripts' / 'launch.py')],
    pathex=[str(root)], binaries=[], datas=[],
    hiddenimports=['PySide6.QtPdf', 'PySide6.QtPdfWidgets'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['numpy', 'pytest', 'zxingcpp', 'tkinter', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='HilfPrint',
          debug=False, bootloader_ignore_signals=False, strip=False,
          upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='HilfPrint')

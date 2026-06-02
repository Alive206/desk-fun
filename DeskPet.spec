# PyInstaller spec for Windows desktop pet packaging.

from pathlib import Path

project_root = Path(SPECPATH)
assets_dir = project_root / "assets"

a = Analysis(
    ["main.py"],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=[(str(assets_dir), "assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DeskPet",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

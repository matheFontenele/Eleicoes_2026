# PyInstaller onedir build. Run only on Windows for the distributable build.
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve()
datas = [
    (str(ROOT / "dashboard.py"), "."),
    (str(ROOT / "dashboard_data.py"), "."),
    (str(ROOT / "data" / "ce_votos.parquet"), "data"),
]
binaries = []
hiddenimports = []

# Streamlit and the visualization packages load frontend assets and selected
# modules dynamically. collect_all keeps those resources with the onedir bundle.
for package in ("streamlit", "streamlit_folium", "folium", "plotly"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

analysis = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "IPython", "notebook"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="CE2026Dashboard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="CE2026Dashboard",
)

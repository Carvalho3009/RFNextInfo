# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPEC).resolve().parent.parent

a = Analysis(
    [str(root / "app" / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "assets" / "karvalho-primary-gold.png"), "assets"),
        (str(root / "core" / "rfnext_frame_decode.py"), "core"),
        (str(root / "core" / "collection_requirements.csv"), "core"),
        (str(root / "core" / "level_curve.json"), "core"),
        (str(root / "core" / "item_names.json"), "core"),
    ],
    hiddenimports=["PIL._tkinter_finder", "pystray._win32"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="RFNextInfo",
    console=False,
    debug=False,
    upx=False,
    icon=None,
    uac_admin=True,
)

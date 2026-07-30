# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPEC).resolve().parent.parent

a = Analysis(
    [str(root / "app" / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "assets" / "karvalho-primary-gold.png"), "assets"),
        (str(root / "assets" / "karvalho-symbol-gold.png"), "assets"),
        (str(root / "assets" / "karvalho-stacked-gold.png"), "assets"),
        (str(root / "assets" / "rf-next-qol-logo.png"), "assets"),
        (str(root / "assets" / "Saira.ttf"), "assets"),
        (str(root / "assets" / "SairaSemiCondensed-Bold.ttf"), "assets"),
        (str(root / "assets" / "class-icons"), "assets/class-icons"),
        (str(root / "core" / "rfnext_frame_decode.py"), "core"),
        (str(root / "core" / "biosuits.json"), "core"),
        (str(root / "core" / "rovers.json"), "core"),
        (str(root / "core" / "catalogo.csv"), "core"),
        (str(root / "core" / "collection_requirements.csv"), "core"),
        (str(root / "core" / "level_curve.json"), "core"),
        (str(root / "core" / "item_names.json"), "core"),
        (str(root / "core" / "item_grades.json"), "core"),
    ],
    hiddenimports=["PIL._tkinter_finder", "pystray._win32"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RFNextInfo",
    console=False,
    debug=False,
    upx=False,
    icon=str(root / "assets" / "karvalho-symbol-gold.png"),
    uac_admin=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="RFNextInfo",
)

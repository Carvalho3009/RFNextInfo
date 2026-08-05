# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPEC).resolve().parent.parent
assets = root / "assets"

a = Analysis(
    [str(root / "app" / "ui_qt" / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(assets / "karvalho-symbol-gold.png"), "assets"),
        (str(assets / "Saira.ttf"), "assets"),
        (str(assets / "SairaSemiCondensed-Bold.ttf"), "assets"),
        (str(assets / "class-icons"), "assets/class-icons"),
        (str(assets / "rover-icons"), "assets/rover-icons"),
        (str(root / "core" / "biosuits.json"), "core"),
        (str(root / "core" / "rovers.json"), "core"),
        (str(root / "core" / "catalogo.csv"), "core"),
        (str(root / "core" / "catalogo_en.csv"), "core"),
        (str(root / "core" / "rfnext_frame_decode.py"), "core"),
        (str(root / "core" / "collection_requirements.csv"), "core"),
        (str(root / "core" / "level_curve.json"), "core"),
        (str(root / "core" / "item_names.json"), "core"),
        (str(root / "core" / "item_names_en.json"), "core"),
        (str(root / "core" / "item_grades.json"), "core"),
    ],
    hiddenimports=[],
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
    icon=str(assets / "karvalho-symbol-gold.png"),
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

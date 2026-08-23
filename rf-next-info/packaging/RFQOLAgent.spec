# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path


root = Path(SPEC).resolve().parent.parent
assets = root / "assets"
job1 = root.parent / "rf-next" / "analysis" / "1.28.5" / "job1"
data_files = [
    (str(assets / "karvalho-symbol-gold.png"), "assets"),
    (str(assets / "Saira.ttf"), "assets"),
    (str(assets / "SairaSemiCondensed-Bold.ttf"), "assets"),
    (str(root / "core" / "boss_catalog.csv"), "core"),
    (str(job1 / "job1_pending_layouts.json"), "core"),
    (str(job1 / "job1_all_opcodes.csv"), "core"),
]

a = Analysis(
    [str(root / "app" / "agent_main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=data_files,
    hiddenimports=[],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RF QOL Agent",
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
    name="RF QOL Agent",
)

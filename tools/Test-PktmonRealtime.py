"""Ensaio elevado do streaming contínuo do Pktmon."""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.pktmon_realtime import probe


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.seconds < 5 or args.seconds > 300:
        parser.error("--seconds deve estar entre 5 e 300")
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("Abra o PowerShell como administrador.", file=sys.stderr)
        return 2
    target = args.output or (
        Path.home()
        / "Documents"
        / "Capturas"
        / "Diagnosticos"
        / f"pktmon-realtime-{datetime.now():%Y%m%d-%H%M%S}.pcap"
    )
    result = probe(target, args.seconds)
    result_path = target.with_suffix(".json")
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Resultado salvo em: {result_path}")
    return 0 if result["packets"] else 3


if __name__ == "__main__":
    raise SystemExit(main())

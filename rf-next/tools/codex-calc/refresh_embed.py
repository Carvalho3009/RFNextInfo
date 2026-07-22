#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Atualiza o dataset Codex embutido no calc/index.html.

Fluxo de refresh de precos (rodar na raiz do repo K:\\MCP\\projects\\rf-next):
    python tools/codex-calc/build_codex_dataset.py --out tools/codex-calc/codex_dataset.json
    python tools/codex-calc/refresh_embed.py

Troca a linha unica `const CODEX_DATA = {...};` pelo JSON novo. Nada mais.
"""
import io
import json
import sys

HTML = sys.argv[1] if len(sys.argv) > 1 else "calc/index.html"
DATASET = sys.argv[2] if len(sys.argv) > 2 else "tools/codex-calc/codex_dataset.json"
ANCHOR = "const CODEX_DATA = "

with io.open(DATASET, "r", encoding="utf-8") as f:
    data = json.load(f)  # valida o JSON antes de embutir
with io.open(HTML, "r", encoding="utf-8") as f:
    lines = f.read().split("\n")

hits = [i for i, ln in enumerate(lines) if ln.startswith(ANCHOR)]
if len(hits) != 1:
    raise SystemExit("ancora '%s' encontrada %dx (esperado 1); abortando" % (ANCHOR, len(hits)))
lines[hits[0]] = ANCHOR + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";"

with io.open(HTML, "w", encoding="utf-8", newline="") as f:
    f.write("\n".join(lines))
print("OK %s atualizado (dataset: %d colecoes, %d precos, fonte: %s)" % (
    HTML, len(data["collections"]), len(data["prices"]),
    data.get("generated_from", {}).get("price_source")))

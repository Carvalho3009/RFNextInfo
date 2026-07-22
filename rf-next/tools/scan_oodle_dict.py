#!/usr/bin/env python3
"""
RF Next 1.28.5 - varredura dos PAKs pelo dicionario Oodle.
Le o indice UE4 Pak v11 (indice cifrado AES-256-ECB), decifra o Full Directory
Index e lista os caminhos de arquivo de cada .pak, sem descomprimir Oodle e sem
depender do repak.exe. Sinaliza *.udic, *.ini e nomes ligados a dicionario/oodle.

Chave AES: variavel de ambiente RFNEXT_AES_KEY (hex de 64 chars OU base64 de 32
bytes). Valida contra o SHA-256 registrado antes de rodar. A chave nunca e gravada.
"""
import os, sys, glob, struct, hashlib, base64, csv, json
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

KNOWN_SHA256 = "7e48e9e9b184dc153b46d240143bf7007605c31a7a57b2bddc2c69287add7c25"
MAGIC = b'\xe1\x12\x6f\x5a'
PAKDIR = "/sessions/rcw-01t3adwhq8u5up1wt44tlutj/mnt/rf-next/analysis/1.28.5/oodle-assets/pakcache-full"
OUTDIR = "/sessions/rcw-01t3adwhq8u5up1wt44tlutj/mnt/rf-next/analysis/1.28.5/oodle-assets"

def load_key():
    raw = os.environ.get("RFNEXT_AES_KEY", "").strip()
    if not raw:
        sys.exit("ERRO: defina RFNEXT_AES_KEY (hex64 ou base64 de 32 bytes).")
    key = None
    try:
        if len(raw) == 64 and all(c in "0123456789abcdefABCDEF" for c in raw):
            key = bytes.fromhex(raw)
    except Exception:
        key = None
    if key is None:
        try:
            key = base64.b64decode(raw)
        except Exception:
            key = None
    if key is None or len(key) != 32:
        sys.exit("ERRO: chave nao tem 32 bytes (aceito hex64 ou base64).")
    got = hashlib.sha256(key).hexdigest()
    if got != KNOWN_SHA256:
        sys.exit(f"ERRO: SHA-256 da chave ({got}) != registrado ({KNOWN_SHA256}). Chave errada.")
    return key

def aes_ecb_dec(key, data):
    n = len(data) - (len(data) % 16)
    dec = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    return dec.update(data[:n]) + dec.finalize()

def read_fstring(buf, o):
    (ln,) = struct.unpack_from('<i', buf, o); o += 4
    if ln == 0:
        return "", o
    if ln < 0:
        n = -ln
        s = buf[o:o+n*2].decode('utf-16-le', 'replace'); o += n*2
    else:
        s = buf[o:o+ln].decode('utf-8', 'replace'); o += ln
    return s.split('\x00', 1)[0], o

def parse_footer(p):
    sz = os.path.getsize(p)
    with open(p, 'rb') as f:
        f.seek(max(0, sz-400)); tail = f.read()
    i = tail.rfind(MAGIC)
    if i < 0:
        return None
    after = tail[i:]
    ver = struct.unpack_from('<I', after, 4)[0]
    idxoff = struct.unpack_from('<q', after, 8)[0]
    idxsize = struct.unpack_from('<q', after, 16)[0]
    benc = tail[i-1]
    return dict(size=sz, ver=ver, idxoff=idxoff, idxsize=idxsize, benc=benc)

def full_dir_index(p, key):
    """Retorna lista de caminhos completos do PAK, ou levanta excecao."""
    ft = parse_footer(p)
    if not ft:
        raise ValueError("sem magic")
    with open(p, 'rb') as f:
        f.seek(ft['idxoff']); enc = f.read(ft['idxsize'])
    idx = aes_ecb_dec(key, enc) if ft['benc'] else enc
    o = 0
    mount, o = read_fstring(idx, o)
    o += 4  # NumEntries int32
    o += 8  # PathHashSeed uint64
    (has_phi,) = struct.unpack_from('<i', idx, o); o += 4
    if has_phi:
        o += 8 + 8 + 20  # offset,size,hash
    (has_fdi,) = struct.unpack_from('<i', idx, o); o += 4
    if not has_fdi:
        return mount, []  # sem indice de diretorio legivel
    fdi_off, fdi_size = struct.unpack_from('<qq', idx, o); o += 16
    with open(p, 'rb') as f:
        f.seek(fdi_off); fenc = f.read(fdi_size)
    fdi = aes_ecb_dec(key, fenc) if ft['benc'] else fenc
    o = 0
    (ndirs,) = struct.unpack_from('<i', fdi, o); o += 4
    paths = []
    for _ in range(ndirs):
        d, o = read_fstring(fdi, o)
        (nfiles,) = struct.unpack_from('<i', fdi, o); o += 4
        for _ in range(nfiles):
            fn, o = read_fstring(fdi, o)
            o += 4  # FPakEntryLocation int32
            paths.append((mount + d + fn))
    return mount, paths

def main():
    key = load_key()
    paks = sorted(glob.glob(PAKDIR + "/*.pak"))
    all_rows = []       # (pak, path)
    flags = []          # (pak, path, kind)
    errors = []         # (pak, err)
    per_pak = {}
    KEYS = (".udic", ".ini")
    NAMEHINT = ("dictionary", "oodle", "serverdict", "clientdict")
    for p in paks:
        b = os.path.basename(p)
        try:
            mount, paths = full_dir_index(p, key)
            per_pak[b] = dict(mount=mount, nfiles=len(paths))
            for path in paths:
                all_rows.append((b, path))
                low = path.lower()
                kind = None
                if low.endswith(".udic"): kind = "udic"
                elif low.endswith(".ini"): kind = "ini"
                elif any(h in low for h in NAMEHINT): kind = "namehint"
                if kind:
                    flags.append((b, path, kind))
        except Exception as e:
            errors.append((b, f"{type(e).__name__}: {e}"))
    # gravar saidas
    with open(OUTDIR + "/oodle-dict-scan-flags.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["Pak", "Path", "Kind"]); w.writerows(flags)
    with open(OUTDIR + "/oodle-dict-scan-allpaths.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["Pak", "Path"]); w.writerows(all_rows)
    with open(OUTDIR + "/oodle-dict-scan-errors.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["Pak", "Error"]); w.writerows(errors)
    summary = dict(
        paks=len(paks), parsed=len(per_pak), errors=len(errors),
        total_paths=len(all_rows),
        udic=sum(1 for x in flags if x[2]=="udic"),
        ini=sum(1 for x in flags if x[2]=="ini"),
        namehint=sum(1 for x in flags if x[2]=="namehint"),
    )
    with open(OUTDIR + "/oodle-dict-scan-summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(json.dumps(summary, ensure_ascii=False))
    print("--- primeiros flags ---")
    for r in flags[:40]:
        print(r)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Pawkit CS360: package the CRM snapshot + roster and encrypt it for the hosted page.

Usage: python3 -I build.py RAW_JSON
  RAW_JSON = output of refresh.py (or the browser snapshot): keys wa, created, visits, comp, generated.
The passcode is read from ~/.config/pawkit-cs360/passcode (never stored in the repo).
Writes docs/data.js (encrypted: PBKDF2-SHA256 + AES-256-GCM, decrypted in the browser).
"""
import base64, json, os, sys
from datetime import datetime, timezone, timedelta
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

HERE = os.path.dirname(os.path.abspath(__file__))
ITER = 310000
SGT = timezone(timedelta(hours=8))


def main():
    raw = json.load(open(sys.argv[1]))
    # config (roster, complaint summaries) is private: it lives outside the public repo
    cfg = json.load(open(os.path.expanduser("~/.config/pawkit-cs360/config.json")))
    bad = sorted({(d, n, c) for d, r in cfg.get("roster", {}).items() for n, c in r.items() if c and c not in cfg.get("shift_codes", {})})
    if bad:
        sys.exit("unknown shift codes in config.json roster: %r" % bad)
    pw = open(os.path.expanduser("~/.config/pawkit-cs360/passcode")).read().strip()
    payload = {
        "generated": raw.get("generated") or datetime.now(SGT).isoformat(timespec="minutes"),
        "visits_until": raw.get("visits_until"),
        "wa": raw["wa"],
        "created": raw["created"],
        "visits": raw["visits"],
        "comp": raw["comp"],
        "tasks": raw.get("tasks", []),
        "orders": raw.get("orders", []),
        "items": raw.get("items", []),
        "inv": raw.get("inv", []),
        "config": {k: v for k, v in cfg.items() if not k.startswith("_")},
    }
    plain = json.dumps(payload, separators=(",", ":")).encode()
    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(pw.encode())
    ct = AESGCM(key).encrypt(iv, plain, None)
    b = lambda x: base64.b64encode(x).decode()
    out = {"v": 1, "iter": ITER, "salt": b(salt), "iv": b(iv), "ct": b(ct)}
    path = os.path.join(HERE, "docs", "data.js")
    with open(path, "w") as f:
        f.write("window.CS360_DATA=" + json.dumps(out) + ";\n")
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    with open(os.path.join(HERE, "out", "data.json"), "w") as f:
        json.dump(out, f)
    print("wrote", path, "and out/data.json,", len(plain), "bytes plain, generated", payload["generated"])


if __name__ == "__main__":
    main()

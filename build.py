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
    # config (roster, complaint summaries) is private: it lives outside the public repo.
    # A typo in it must never stop the data: fall back to the last copy that loaded, and only warn on unknown codes.
    cfg_path = os.path.expanduser("~/.config/pawkit-cs360/config.json")
    last_good = cfg_path + ".last-good"
    try:
        cfg = json.load(open(cfg_path))
        codes = cfg["shift_codes"]
        for d, r in cfg["roster"].items():
            for n, c in list(r.items()):
                if isinstance(c, str) and c.strip() in codes:
                    r[n] = c.strip()
                elif c:
                    print("WARNING unknown shift code %r for %s on %s (shown as typed, counted as not on shift)" % (c, n, d))
        fd = os.open(last_good + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(cfg, f)
        os.replace(last_good + ".tmp", last_good)
    except (OSError, ValueError, KeyError, AttributeError) as e:
        print("WARNING config.json could not be used (%s: %s); using the last good copy" % (type(e).__name__, e))
        cfg = json.load(open(last_good))
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
    if "--no-bundle" not in sys.argv:  # the 5-minute job only refreshes the live data branch
        with open(path, "w") as f:
            f.write("window.CS360_DATA=" + json.dumps(out) + ";\n")
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    with open(os.path.join(HERE, "out", "data.json"), "w") as f:
        json.dump(out, f)
    wrote = "out/data.json" if "--no-bundle" in sys.argv else "docs/data.js and out/data.json"
    print("wrote %s, %d bytes plain, generated %s" % (wrote, len(plain), payload["generated"]))


if __name__ == "__main__":
    main()

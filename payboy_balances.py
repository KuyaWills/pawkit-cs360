#!/usr/bin/env python3
"""Save Payboy leave balances for the Time Off page.

Input: a JSON file with a list of {"id": <Payboy employee id>, "types": ["Annual Leave (4 days / 15 days left)", ...]},
made in a browser signed in to the Payboy Admin portal (payboy.biz) from /employee_leave_types.json?employee_id=<id>.
Only the people listed in the private config key _payboy_ids are kept. Output goes to the private file
~/.config/pawkit-cs360/payboy_balances.json, which build.py publishes (inside the encrypted data) as leave_bal.

Usage: python3 payboy_balances.py <input.json>
"""
import json, os, re, sys
from datetime import datetime, timedelta, timezone

CFG_DIR = os.path.expanduser("~/.config/pawkit-cs360")
PAT = re.compile(r"^(.*?)\s*\((.*?)\s*/\s*(.*?)\s*left\)\s*$")


def main():
    rows = json.load(open(sys.argv[1]))
    ids = json.load(open(os.path.join(CFG_DIR, "config.json"))).get("_payboy_ids") or {}
    by_id = {int(r["id"]): r for r in rows if isinstance(r, dict) and "id" in r}
    people, missing = {}, []
    for name, pid in ids.items():
        r = by_id.get(int(pid))
        if r is None or not isinstance(r.get("types"), list):
            missing.append(name)
            continue
        out = []
        for t in r["types"]:
            m = PAT.match(str(t))
            if m:  # Payboy shows "<balance> / <allowance for the year> left"
                fix = lambda v: re.sub(r"\b1 days\b", "1 day", v)
                out.append({"type": m.group(1), "left": fix(m.group(2)), "of": fix(m.group(3))})
        people[name] = out
    if not people:
        sys.exit("no balances found; is the browser still signed in to Payboy Admin?")
    data = {"synced": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="minutes"), "people": people}
    path = os.path.join(CFG_DIR, "payboy_balances.json")
    fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(path + ".tmp", path)
    print("saved balances for %s%s" % (", ".join(sorted(people)), ("; missing: " + ", ".join(missing)) if missing else ""))


if __name__ == "__main__":
    main()

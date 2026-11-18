#!/usr/bin/env python3
"""One-time Zoho sign-in for the CS360 refresh (run it yourself in Terminal).

1. Open https://api-console.zoho.com -> Add Client -> Self Client -> Create.
2. In the Self Client, "Generate Code" tab, Scope:
     ZohoCRM.coql.READ,ZohoCRM.modules.READ,ZohoCRM.users.READ
   Time duration 10 minutes, description "Pawkit CS360", Create, pick the Pawkit org.
3. Run:  python3 zoho_setup.py   and paste the Client ID, Client Secret and the code.
Saves ~/.config/pawkit-cs360/zoho.json (only readable by you). Read-only access.
"""
import getpass, json, os, urllib.parse, urllib.request

path = os.path.expanduser("~/.config/pawkit-cs360/zoho.json")
cid = input("Client ID: ").strip()
sec = getpass.getpass("Client Secret (hidden): ").strip()
code = getpass.getpass("Generated code (hidden): ").strip()
data = urllib.parse.urlencode({"grant_type": "authorization_code", "client_id": cid, "client_secret": sec, "code": code}).encode()
with urllib.request.urlopen(urllib.request.Request("https://accounts.zoho.com/oauth/v2/token", data=data, method="POST"), timeout=30) as r:
    j = json.load(r)
if "refresh_token" not in j:
    raise SystemExit("Zoho said: %s  (the code lasts only a few minutes; generate a new one and retry)" % j.get("error", j))
os.makedirs(os.path.dirname(path), exist_ok=True)
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    json.dump({"client_id": cid, "client_secret": sec, "refresh_token": j["refresh_token"],
               "api_domain": j.get("api_domain", "https://www.zohoapis.com"), "accounts": "https://accounts.zoho.com"}, f)
print("Saved. Zoho access is set up for the CS360 refresh.")

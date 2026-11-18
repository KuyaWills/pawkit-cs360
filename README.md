# Pawkit CS360

Internal customer-service page for Pawkit, served at https://cs360.pawkit.sg (GitHub Pages from `docs/`).

- `~/.config/pawkit-cs360/config.json` (private, never in this public repo): roster copied from the Zoho Sheet schedule tracker, shift codes, leave, complaint summaries.
- `build.py RAW_JSON`: packages the Zoho CRM snapshot and the config, then encrypts them into `docs/data.js`
  (PBKDF2-SHA256 + AES-256-GCM). The page decrypts them in the browser with the team passcode.
- The passcode lives only in `~/.config/pawkit-cs360/passcode` on the publishing Mac. Never commit it.
- `raw/` (the unencrypted snapshot) is git-ignored.

## Changing the passcode
1. Put the new passcode in `~/.config/pawkit-cs360/passcode` (use a generated one: five random words or 16+ random characters).
2. Run `python3 build.py raw/crm.json` (without `--no-bundle`), then commit and push `main`, so the bundled snapshot uses it too.
3. The next 5-minute run re-encrypts the live data. People are asked for the new passcode.

Anything already published under an old passcode stays readable with that passcode: GitHub keeps superseded data commits reachable by ID. After a suspected leak, delete and recreate the repository, then publish under the new passcode.

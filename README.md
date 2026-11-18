# Pawkit CS360

Internal customer-service page for Pawkit, served at https://cs360.pawkit.sg (GitHub Pages from `docs/`).

- `~/.config/pawkit-cs360/config.json` (private, never in this public repo): roster copied from the Zoho Sheet schedule tracker, shift codes, leave, complaint summaries.
- `build.py RAW_JSON`: packages the Zoho CRM snapshot and the config, then encrypts them into `docs/data.js`
  (PBKDF2-SHA256 + AES-256-GCM). The page decrypts them in the browser with the team passcode.
- The passcode lives only in `~/.config/pawkit-cs360/passcode` on the publishing Mac. Never commit it.
- `raw/` (the unencrypted snapshot) is git-ignored.

# Hermes Google Workspace OAuth (hub inbox)

One-time. Daily digest reads **ianm.powercore@gmail.com** only (other accounts forwarded into this hub).

## Files

- Client JSON (you download): Desktop OAuth client from Google Cloud
- Token (created by setup): `%LOCALAPPDATA%\hermes\google_token.json`

## Steps

1. Cloud Console → enable **Gmail API** + **Google Calendar API**.
2. Credentials → OAuth 2.0 Client ID → **Desktop app** → download JSON.
3. If the app is in Testing: Audience → add `ianm.powercore@gmail.com`.
4. Run (PowerShell):

```powershell
$GSETUP = "$env:LOCALAPPDATA\hermes\skills\productivity\google-workspace\scripts\setup.py"
python $GSETUP --client-secret "C:\path\to\client_secret.json"
python $GSETUP --auth-url --services email,calendar --format json
```

5. Open `auth_url` in a browser as **ianm.powercore@gmail.com**. The `localhost:1` error after approve is expected — copy the **full** redirect URL from the address bar.
6. `python $GSETUP --auth-code "PASTE_URL_OR_CODE"`
7. `python $GSETUP --check`  → must print `AUTHENTICATED`

Do not commit the client JSON or token. Do not paste them into chat.

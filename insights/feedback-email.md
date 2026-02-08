# Feedback email implementation

## What didn't work

1. **FormSubmit.co** - Requires email activation first. Even after activation, returns "Form should POST" errors. Confusing setup process.

2. **Web3Forms** - Free tier blocks server-side requests (403 error: "this method is not allowed"). Only works from browsers/client-side. Pro plan required for desktop apps.

3. **ntfy.sh** - Works perfectly for push notifications (free, no signup), but doesn't forward to email on free tier.

## What worked

**Resend** - Modern email API that works from server-side on free tier.

- Free: 100 emails/day, 3000/month
- Simple Python SDK: `poetry add resend`
- Use `onboarding@resend.dev` as sender (no domain verification needed)
- Recipient must match your Resend account email on free tier

## Setup

1. Sign up at resend.com with the email you want to receive feedback at
2. Create API key at resend.com/api-keys
3. Create `trebnic/credentials.py` (gitignored):
   ```python
   RESEND_API_KEY = "re_xxxxx"
   FEEDBACK_EMAIL = "your@email.com"
   ```
4. Optionally also set in `.env` for desktop development:
   ```
   RESEND_API_KEY=re_xxxxx
   FEEDBACK_EMAIL=your@email.com
   ```

## Credential storage

Credentials are stored in the SQLite settings table and seeded on first run via `_seed_email_config()` in `services/logic.py`. Priority chain:

1. **Database** (SQLite settings table) — checked first, used if non-empty and not revoked
2. **env var** (`.env` via `load_dotenv`) — desktop development fallback
3. **`credentials.py`** (gitignored, imported as `_CRED_API_KEY` / `_CRED_EMAIL`) — final fallback
4. **Manual entry** via feedback page config UI — user can override on any platform

Revoked keys are tracked in `_REVOKED_KEYS` set inside `_seed_email_config()`. If the current DB key or env var matches a revoked key, it falls back to `_CRED_API_KEY`.

```python
# services/logic.py — seeding on first load
try:
    from credentials import RESEND_API_KEY as _CRED_API_KEY, FEEDBACK_EMAIL as _CRED_EMAIL
except ImportError:
    _CRED_API_KEY = ""
    _CRED_EMAIL = ""
```

Once seeded, `feedback_view.py` reads values from DB via `db.get_setting("resend_api_key")`. The feedback page also has a config section where users can enter/update credentials manually.

**Security note:** `credentials.py` gets bundled into the APK by `flet build`. The API key ships inside every APK binary. Future improvement: replace direct Resend API calls with a backend proxy (e.g. Cloudflare Worker) so zero secrets live in the app.

## Mobile builds

Poetry manages desktop dependencies via `pyproject.toml`, but **Flet mobile builds use `requirements.txt`**.

### Desktop-only packages (dotenv)

`.env` files aren't bundled in mobile APKs. Make the import optional:

```python
# config.py
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass
```

### Avoid external packages for HTTP on mobile

The `resend` SDK doesn't work on Android even though it appears to be pure Python. Use Python's built-in `urllib.request` instead — zero dependencies, works everywhere.

## Code

The app uses stdlib `urllib.request` on all platforms (desktop and mobile). The `resend` SDK caused missing module errors on Android.

```python
import json
import urllib.request

payload = json.dumps({
    "from": "App Name <onboarding@resend.dev>",
    "to": [feedback_email],
    "subject": "Feedback",
    "html": "<p>Message here</p>",
}).encode("utf-8")

req = urllib.request.Request(
    "https://api.resend.com/emails",
    data=payload,
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    },
    method="POST",
)
urllib.request.urlopen(req, timeout=30)
```

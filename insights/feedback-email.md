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
3. Add to `.env`:
   ```
   RESEND_API_KEY=re_xxxxx
   FEEDBACK_EMAIL=your@email.com
   ```

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

### Mobile feedback with hardcoded keys

Since `.env` isn't available on mobile, use fallback hardcoded values:

```python
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "") or "re_xxxxx"
FEEDBACK_EMAIL = os.getenv("FEEDBACK_EMAIL", "") or "your@email.com"
```

Risk is minimal:
- Free tier: 100 emails/day cap
- Can only send to your own verified email
- Worst case: spam your inbox, regenerate the key

### Avoid external packages for HTTP on mobile

The `resend` SDK doesn't work on Android even though it appears to be pure Python. Use Python's built-in `urllib.request` instead - zero dependencies, works everywhere.

## Code

### Desktop (with resend SDK)
```python
import resend

resend.api_key = RESEND_API_KEY
resend.Emails.send({
    "from": "App Name <onboarding@resend.dev>",
    "to": [FEEDBACK_EMAIL],
    "subject": "Feedback",
    "html": "<p>Message here</p>",
})
```

### Mobile-compatible (urllib - no dependencies)
The `resend` SDK doesn't work on Android (missing module errors even when in requirements.txt). Use stdlib `urllib` instead:

```python
import json
import urllib.request

payload = json.dumps({
    "from": "App Name <onboarding@resend.dev>",
    "to": [FEEDBACK_EMAIL],
    "subject": "Feedback",
    "html": "<p>Message here</p>",
}).encode("utf-8")

req = urllib.request.Request(
    "https://api.resend.com/emails",
    data=payload,
    headers={
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    },
    method="POST",
)
urllib.request.urlopen(req, timeout=30)
```

This uses only Python stdlib - works everywhere without dependency issues.

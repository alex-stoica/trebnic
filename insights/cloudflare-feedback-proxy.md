# Feedback proxy via Cloudflare Worker

Replace the bundled Resend API key with a server-side proxy so zero secrets ship in the APK.

## Why

`credentials.py` gets bundled into every APK by `flet build`. The Resend API key is extractable from the binary.
A Cloudflare Worker holds the key server-side. The app only knows the worker URL (public, harmless).

## Step 1: Create Cloudflare account and worker

1. Sign up at https://dash.cloudflare.com/sign-up (free, no credit card)
2. Install the CLI: `npm install -g wrangler` (requires Node.js)
3. Log in: `wrangler login` (opens browser for OAuth)
4. Create the project: `wrangler init trebnic-feedback --type javascript`

## Step 2: Write the worker

Create `trebnic-feedback/src/index.js`:

```javascript
export default {
  async fetch(request, env) {
    // Only accept POST
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    // Basic rate limiting via CF headers (optional but recommended)
    const ip = request.headers.get("CF-Connecting-IP");

    let body;
    try {
      body = await request.json();
    } catch {
      return new Response("Invalid JSON", { status: 400 });
    }

    const { category, message } = body;
    if (!message || !message.trim()) {
      return new Response("Message required", { status: 400 });
    }

    // Build the same HTML email template currently in feedback_view.py
    const formatted = message.replace(/\n/g, "<br>");
    const html = `
      <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); padding: 24px; border-radius: 12px 12px 0 0;">
          <h1 style="color: white; margin: 0; font-size: 20px;">New Feedback</h1>
        </div>
        <div style="background: #f8fafc; padding: 24px; border: 1px solid #e2e8f0; border-top: none; border-radius: 0 0 12px 12px;">
          <div style="background: white; padding: 16px; border-radius: 8px; border-left: 4px solid #6366f1;">
            <p style="margin: 0 0 8px 0; color: #64748b; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;">Category</p>
            <p style="margin: 0; color: #1e293b; font-weight: 600;">${category || "General"}</p>
          </div>
          <div style="margin-top: 16px; background: white; padding: 16px; border-radius: 8px;">
            <p style="margin: 0 0 8px 0; color: #64748b; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;">Message</p>
            <p style="margin: 0; color: #1e293b; line-height: 1.6;">${formatted}</p>
          </div>
          <p style="margin: 24px 0 0 0; color: #94a3b8; font-size: 12px; text-align: center;">Sent from Trebnic App</p>
        </div>
      </div>`;

    // Forward to Resend
    const resendResponse = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.RESEND_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: "Trebnic <onboarding@resend.dev>",
        to: [env.FEEDBACK_EMAIL],
        subject: `[${category || "General"}] Trebnic feedback`,
        html,
      }),
    });

    if (!resendResponse.ok) {
      const err = await resendResponse.text();
      return new Response(err, { status: resendResponse.status });
    }

    return new Response("OK", { status: 200 });
  },
};
```

## Step 3: Add secrets

```bash
cd trebnic-feedback
wrangler secret put RESEND_API_KEY
# paste: re_ddzgk9pd_7MsQtzD3beRFgPrTfyxkdBmq

wrangler secret put FEEDBACK_EMAIL
# paste: alexstoica@protonmail.com
```

Secrets are encrypted and never visible again — not in dashboard, not in logs.

## Step 4: Deploy

```bash
wrangler deploy
```

Output will show the URL, something like:
```
https://trebnic-feedback.<your-account>.workers.dev
```

Test it:
```bash
curl -X POST https://trebnic-feedback.<your-account>.workers.dev \
  -H "Content-Type: application/json" \
  -d '{"category": "Test", "message": "Hello from curl"}'
```

Check your inbox — you should get the formatted email.

## Step 5: Update Trebnic code

### 5a. Add worker URL to config

In `trebnic/config.py`:
```python
FEEDBACK_WORKER_URL = "https://trebnic-feedback.<your-account>.workers.dev"
```

### 5b. Simplify feedback_view.py

Replace `_send_http` — it no longer needs the API key or email:

```python
@staticmethod
def _send_http(category: str, message: str) -> str | None:
    payload = json.dumps({"category": category, "message": message}).encode("utf-8")
    req = urllib.request.Request(
        FEEDBACK_WORKER_URL,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "Trebnic/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status == 200:
                return None
            return f"HTTP {response.status}"
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:200]
        except OSError:
            pass
        return f"{e.code} {body}" if body else f"{e.code} {e.reason}"
    except urllib.error.URLError as e:
        return f"Network: {e.reason}"
```

Update `_on_send_click` — remove api_key/email reads from DB, just pass category+message:
```python
error = await loop.run_in_executor(None, self._send_http, category, message)
```

### 5c. Remove the config UI section from feedback page

Delete the entire email configuration card (API key field, email field, save button, status indicator).
The feedback page becomes just: donation card + feedback form. Much simpler.

### 5d. Remove credential seeding from logic.py

- Delete the `from credentials import ...` block (lines 8-12)
- Delete `_seed_email_config()` entirely
- Remove calls to `_seed_email_config()` from `load_state_async()` and `reset()`

### 5e. Delete credentials.py

The file is no longer needed.

### 5f. Clean up i18n.py

These translation keys become unused and can be removed:
- `feedback_not_configured`
- `email_config`
- `email_config_desc`
- `resend_api_key`
- `feedback_email_label`
- `config_saved`
- `configured`
- `not_configured`

## Optional: rate limiting

Add to the worker to prevent abuse:

```javascript
// At the top of fetch()
const ip = request.headers.get("CF-Connecting-IP");
const rateKey = `rate:${ip}`;
const current = await env.RATE_LIMIT.get(rateKey);
if (current && parseInt(current) >= 5) {
  return new Response("Too many requests", { status: 429 });
}
await env.RATE_LIMIT.put(rateKey, String((parseInt(current) || 0) + 1), { expirationTtl: 3600 });
```

This requires a KV namespace (also free tier: 100k reads/day, 1k writes/day):
```bash
wrangler kv namespace create RATE_LIMIT
# Add the binding to wrangler.toml
```

## Costs

Free tier covers everything:
- Workers: 100,000 requests/day
- KV (if using rate limiting): 100,000 reads/day, 1,000 writes/day
- Resend: 100 emails/day, 3,000/month

For Trebnic's feedback volume, this will never cost anything.

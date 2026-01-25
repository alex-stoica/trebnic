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

## Code

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

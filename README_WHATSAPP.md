# WhatsApp channel (Meta Cloud API)

The chatbot answers WhatsApp messages through Meta's WhatsApp Cloud API (Graph API — free for a
test number and service conversations). Inbound messages hit `POST /webhook` on the existing
Flask app, which reuses the same RAG pipeline as the web chat (per-phone-number conversation
history, kept in process memory like web sessions).

## 1. Create the Meta app

1. Create a developer account at [developers.facebook.com](https://developers.facebook.com).
2. **Create App** → app type **Business**.
3. In the app dashboard, add the **WhatsApp** product. This auto-provisions a free test phone
   number you can send from immediately.

## 2. Credentials

All values live in **WhatsApp → API Setup** in the app dashboard, except the app secret:

| Variable | Where to find it |
| --- | --- |
| `META_PHONE_NUMBER_ID` | API Setup → "Phone number ID" under the test number (not the phone number itself) |
| `META_ACCESS_TOKEN` | See below — generate a permanent token |
| `META_VERIFY_TOKEN` | Any string you invent; you'll enter the same value in the webhook config (step 4) |
| `META_APP_SECRET` | App Settings → Basic → "App secret" |

### Permanent access token

The token shown in API Setup is **temporary — it expires in 24 hours**. Create a permanent one:

1. Go to [Meta Business Settings](https://business.facebook.com/settings) → **Users → System
   Users** → create a system user (role: Admin is simplest for this PoC).
2. **Add Assets** → assign the app and the WhatsApp Business Account (WABA) to that user.
3. **Generate New Token** → select the app → check the `whatsapp_business_messaging`
   permission → generate. This token does not expire; use it as `META_ACCESS_TOKEN`.

## 3. Test recipients

A test number can only message registered recipients. In **WhatsApp → API Setup → "To"**, add up
to 5 recipient numbers — each receives a WhatsApp verification code that must be entered to
confirm.

## 4. Webhook

In **WhatsApp → Configuration → Webhook**:

- **Callback URL:** `https://xatbot-caravista.onrender.com/webhook`
- **Verify token:** the exact value you set as `META_VERIFY_TOKEN` in Render (step 5) — Meta
  calls `GET /webhook` with it during verification, so set the Render env vars first.
- After verifying, under **Webhook fields**, subscribe to **`messages`**.

## 5. Render environment variables

Add these in the Render dashboard for the `xatbot-caravista` service (they are declared `sync: false` in
`render.yaml`, so values live only in the dashboard):

- `META_ACCESS_TOKEN`
- `META_PHONE_NUMBER_ID`
- `META_VERIFY_TOKEN`
- `META_APP_SECRET`

Without them the rest of the app works normally — only `/webhook` returns a 503.

## 6. First test

From a registered test recipient's WhatsApp, send any question to the test number — the bot
replies with the same RAG answer the web chat would give.

## 7. Cold starts (Render free plan)

The free plan spins the service down after ~15 minutes of inactivity; the next message then hits
a cold start of up to a minute, and Meta may have given up waiting by the time the app boots.
To keep it warm, create a free [UptimeRobot](https://uptimerobot.com) HTTP monitor pinging
`https://xatbot-caravista.onrender.com/health` every 10 minutes.

## 8. Local testing

Meta signs each webhook request (`X-Hub-Signature-256`) and the app validates that signature —
which can't succeed for hand-made local requests. Skip validation locally (never in production):

```bash
SKIP_SIGNATURE_VALIDATION=true python -m flask --app app.web run
```

Then simulate an inbound message:

```bash
curl -X POST http://localhost:5000/webhook \
  -H "Content-Type: application/json" \
  -d '{"entry":[{"changes":[{"value":{"messages":[{"from":"34600000000","type":"text","text":{"body":"Quins serveis oferiu?"}}]}}]}]}'
```

The reply is sent through the Graph API, so `META_ACCESS_TOKEN`/`META_PHONE_NUMBER_ID` must
still be set (real values) for the outbound message to arrive.

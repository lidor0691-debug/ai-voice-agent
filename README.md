# Maya AI — Voice Assistant for Businesses

An AI-powered Hebrew-speaking voice assistant built with FastAPI and Twilio Voice.
Collects motorcycle leads over the phone and forwards them to Make.com and via SMS.

---

## Project Structure

```
maya-ai/
├── main.py                        # FastAPI app entry point
├── requirements.txt
├── .env.example
├── app/
│   ├── config/
│   │   └── settings.py            # Pydantic settings (loaded from .env)
│   ├── routes/
│   │   └── voice.py               # Twilio Voice webhook handlers
│   ├── services/
│   │   ├── conversation.py        # In-memory call state & conversation flow
│   │   └── lead.py                # Lead formatting helpers
│   └── integrations/
│       ├── twilio_client.py       # Outbound SMS via Twilio REST
│       └── make_webhook.py        # POST lead data to Make.com
```

---

## Call Flow

```
Incoming call
     │
     ▼
/voice/incoming  ──► Ask for name (Hebrew TTS)
     │
     ▼
/voice/gather    ──► Process answer ──► Ask next question
     │                (repeat for each step)
     ▼
All answers collected
     ├──► POST lead JSON  ──► Make.com webhook
     ├──► Send SMS confirmation ──► Caller's number
     └──► Say goodbye & hang up
```

### Questions asked (in Hebrew)
| Step | Question |
|------|----------|
| 1 | Name |
| 2 | Motorcycle interest |
| 3 | Budget |
| 4 | New or used |
| 5 | Test ride request |

---

## Local Setup

### 1. Clone and install

```bash
git clone <repo-url>
cd maya-ai

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your Twilio credentials and Make.com webhook URL
```

### 3. Expose local server with ngrok

Twilio needs a public HTTPS URL to reach your local machine.

```bash
# Install ngrok: https://ngrok.com/download
ngrok http 8000
```

Copy the `https://xxxx.ngrok.io` URL and set it as `BASE_URL` in your `.env`.

### 4. Run the server

```bash
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.
Interactive docs: `http://localhost:8000/docs`

### 5. Configure Twilio

1. Open [Twilio Console](https://console.twilio.com/) → **Phone Numbers**
2. Select your number → **Voice & Fax**
3. Set **"A CALL COMES IN"** webhook to:
   ```
   https://your-ngrok-url.ngrok.io/voice/incoming
   ```
   Method: `HTTP POST`
4. Save.

### 6. Configure Make.com

1. Create a new scenario in [Make.com](https://make.com)
2. Add a **Custom Webhook** trigger module
3. Copy the generated webhook URL
4. Paste it as `MAKE_WEBHOOK_URL` in your `.env`
5. Add downstream modules (e.g., Google Sheets, CRM, email notification)

---

## Lead Payload sent to Make.com

```json
{
  "call_sid": "CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "phone_number": "+9725xxxxxxxx",
  "name": "ישראל ישראלי",
  "interest": "סוזוקי GSX",
  "budget": "30000 שקל",
  "condition": "חדש",
  "test_ride": "כן",
  "created_at": "2026-03-05T10:30:00",
  "source": "phone_call",
  "language": "he"
}
```

---

## Production Checklist

- [ ] Replace in-memory session store with Redis (`aioredis`)
- [ ] Add Twilio request signature validation middleware
- [ ] Set `DEBUG=false` and configure proper log aggregation
- [ ] Deploy on a platform with HTTPS (Railway, Render, Fly.io, etc.)
- [ ] Rotate `TWILIO_AUTH_TOKEN` and store secrets in a vault
- [ ] Add a database to persist leads independently of Make.com

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Web framework | FastAPI |
| ASGI server | Uvicorn |
| Voice & SMS | Twilio Voice / SMS |
| Hebrew TTS | Amazon Polly (via Twilio) |
| STT / Speech recognition | Twilio `<Gather input="speech" language="he-IL">` |
| Automation | Make.com webhook |
| HTTP client | httpx (async) |
| Config | pydantic-settings |

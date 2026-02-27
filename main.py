from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse
import html

app = FastAPI(title="AI Voice Agent", version="0.1.0")

@app.get("/")
def read_root():
    return {"status": "agent alive"}

# endpoint לטוויליו לשיחה נכנסת
@app.post("/voice")
async def voice(request: Request):
    # Twilio שולח form-urlencoded, לכן צריך python-multipart כדי שזה יעבוד
    form = await request.form()
    from_number = form.get("From", "Unknown")

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">Hello. Your agent is alive.</Say>
    <Say voice="alice">I see your number is {html.escape(str(from_number))}.</Say>
    <Say voice="alice">Goodbye.</Say>
</Response>"""

    return Response(content=twiml, media_type="application/xml")

# בדיקה בטקסט (לא קשור לטוויליו)
@app.post("/talk")
async def talk(request: Request):
    body = await request.json()
    message = body.get("message", "")
    response_text = f"You said: {message}. I'm your AI agent."
    return JSONResponse({"response": response_text})

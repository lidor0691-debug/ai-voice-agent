from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse

app = FastAPI(title="AI Voice Agent")

# בדיקה שהשרת חי
@app.get("/")
def root():
    return {"status": "agent alive"}

# בדיקת טקסט רגילה
@app.post("/talk")
async def talk(request: Request):
    body = await request.json()
    message = body.get("message", "")
    return JSONResponse({
        "response": f"You said: {message}. I'm your AI agent."
    })

# ====== זה החלק החשוב - Twilio קול ======
@app.post("/voice")
async def voice(request: Request):

    form = await request.form()
    speech = form.get("SpeechResult")

    if speech:
        text = f"You said {speech}. I am your AI agent."
    else:
        text = "Hello. This is your AI agent. Please say something after the beep."

    twiml = f"""
<Response>
    <Gather input="speech" action="/voice" method="POST" timeout="5">
        <Say voice="alice">{text}</Say>
    </Gather>
    <Say voice="alice">I didn't hear anything. Goodbye.</Say>
</Response>
"""
    return Response(content=twiml, media_type="application/xml")

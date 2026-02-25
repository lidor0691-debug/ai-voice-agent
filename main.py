from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict

app = FastAPI(title="AI Voice Agent", version="0.1.0")


# ---------- Models ----------
class TalkBody(BaseModel):
    message: str


# ---------- Routes ----------
@app.get("/")
def read_root():
    return {"status": "agent alive"}


# webhook לקבלת הודעות חיצוניות (Twilio/Retell/כל מערכת אחרת)
# מקבל JSON כללי (dict) כדי שלא יקרוס אם המבנה משתנה
@app.post("/webhook")
async def webhook(payload: Dict[str, Any]):
    print("Incoming webhook payload:", payload)
    return JSONResponse({"reply": "Hello, I received your message."})


# endpoint לדבר עם הסוכן בטקסט
# עכשיו Swagger ידע להציג לך מקום לכתוב בו JSON
@app.post("/talk")
async def talk(body: TalkBody):
    message = body.message
    print("User said:", message)

    response_text = f"You said: {message}. I'm your AI agent."
    return JSONResponse({"response": response_text})

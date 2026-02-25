from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

# ===== מודל הודעה =====
class TalkRequest(BaseModel):
    message: str


@app.get("/")
def read_root():
    return {"status": "agent alive"}


# ===== endpoint לדבר עם הסוכן =====
@app.post("/talk")
async def talk(data: TalkRequest):
    message = data.message

    print("User said:", message)

    response_text = f"You said: {message}. I'm your AI agent."

    return {
        "response": response_text
    }


# ===== webhook חיצוני (טוויליו וכו') =====
@app.post("/webhook")
async def webhook(data: dict):
    print("Incoming data:", data)

    return {
        "reply": "Hello, I received your message."
    }

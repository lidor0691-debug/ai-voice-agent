from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="AI Voice Agent", version="0.1.0")


class TalkRequest(BaseModel):
    message: str


class WebhookRequest(BaseModel):
    # אם אתה לא יודע עדיין מה מגיע מטוויליו/רטל, אפשר להשאיר גנרי:
    payload: dict


@app.get("/")
def read_root():
    return {"status": "agent alive"}


@app.post("/webhook")
async def webhook(body: dict):
    # body יהיה כל JSON שתשלח
    print("Incoming data:", body)
    return JSONResponse({"reply": "Hello, I received your message."})


@app.post("/talk")
async def talk(req: TalkRequest):
    print("User said:", req.message)
    return JSONResponse({"response": f"You said: {req.message}. I'm your AI agent."})

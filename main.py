from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "agent alive"}

# webhook לקבלת הודעות חיצוניות (טוויליו/רטל/מערכת אחרת)
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    print("Incoming data:", data)

    return JSONResponse({
        "reply": "Hello, I received your message."
    })

# endpoint לדבר עם הסוכן בטקסט
@app.post("/talk")
async def talk(request: Request):
    body = await request.json()
    message = body.get("message", "")

    print("User said:", message)

    response_text = f"You said: {message}. I'm your AI agent."

    return JSONResponse({
        "response": response_text
    })

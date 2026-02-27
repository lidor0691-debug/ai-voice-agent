from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="AI Voice Agent", version="1.0.0")


class TalkRequest(BaseModel):
    message: str


@app.get("/")
def root():
    # רק בדיקה לדפדפן
    return {"status": "agent alive"}


@app.post("/talk")
async def talk(req: TalkRequest):
    # כרגע דמו פשוט. כאן בהמשך תחבר ל-LLM שלך
    return {"response": f"אתה אמרת: {req.message}. אני כאן איתך."}


def twiml_say(text: str) -> Response:
    # Twilio חייב XML
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="he-IL" voice="Polly.Carmit">{text}</Say>
</Response>"""
    return Response(content=xml, media_type="application/xml")


@app.post("/voice")
async def voice(request: Request):
    """
    נקודת הכניסה של Twilio לשיחה.
    לא מחייג לשום מספר. רק מדבר ומבקש מהמשתמש להגיד משפט.
    """
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="he-IL" voice="Polly.Carmit">הסוכן חי. תגיד לי משפט קצר אחרי הצפצוף.</Say>
  <Gather input="speech" language="he-IL" action="/speech" method="POST" timeout="5">
    <Say language="he-IL" voice="Polly.Carmit">אני מקשיב.</Say>
  </Gather>
  <Say language="he-IL" voice="Polly.Carmit">לא שמעתי כלום. ננסה שוב.</Say>
  <Redirect method="POST">/voice</Redirect>
</Response>"""
    return Response(content=xml, media_type="application/xml")


@app.post("/speech")
async def speech(request: Request):
    """
    Twilio שולח לכאן את התמלול ב-SpeechResult.
    אנחנו מחזירים תשובה ואז חוזרים ל-/voice להמשך שיחה.
    """
    form = await request.form()
    user_text = (form.get("SpeechResult") or "").strip()

    if not user_text:
        return twiml_say("לא קלטתי. תנסה שוב.")

    # משתמשים באותו לוגיקה של /talk
    ai = await talk(TalkRequest(message=user_text))
    ai_text = ai.get("response", "לא הצלחתי לענות כרגע.")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="he-IL" voice="Polly.Carmit">{ai_text}</Say>
  <Redirect method="POST">/voice</Redirect>
</Response>"""
    return Response(content=xml, media_type="application/xml")

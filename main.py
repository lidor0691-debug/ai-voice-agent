from fastapi import FastAPI, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
import os

app = FastAPI()
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

@app.post("/voice")
async def voice():
    vr = VoiceResponse()

    gather = Gather(
        input="speech",
        action="/process",
        method="POST",
        speechTimeout="auto",
        language="he-IL",   # אפשר he-IL, אם יוצא עילג עדיין נחליף ל-en-US
    )

    gather.say("דבר איתי. אני מקשיב.", language="he-IL")
    vr.append(gather)

    # אם לא נקלט דיבור
    vr.say("לא שמעתי כלום. נסה שוב.", language="he-IL")
    vr.redirect("/voice", method="POST")

    return Response(str(vr), media_type="application/xml")


@app.post("/process")
async def process(request: Request):
    form = await request.form()
    user_text = form.get("SpeechResult", "") or ""

    vr = VoiceResponse()

    if not user_text.strip():
        vr.say("לא הצלחתי להבין. תגיד שוב.", language="he-IL")
        vr.redirect("/voice", method="POST")
        return Response(str(vr), media_type="application/xml")

    # קריאה ל-OpenAI
    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "אתה סוכן טלפוני בעברית. ענה קצר וברור."},
            {"role": "user", "content": user_text},
        ],
        max_tokens=120,
    )

    answer = completion.choices[0].message.content.strip()

    vr.say(answer, language="he-IL")
    vr.redirect("/voice", method="POST")  # ממשיך שיחה

    return Response(str(vr), media_type="application/xml")


@app.get("/")
def health():
    return {"status": "agent alive"}

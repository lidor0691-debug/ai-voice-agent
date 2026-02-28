import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI

app = FastAPI()

# משיכת המפתח מתוך משתני הסביבה
api_key = os.getenv("OPENAI_API_KEY")

# אתחול בטוח כדי למנוע קריסה של השרת בזמן העלייה אם המפתח חסר
if api_key:
    client = OpenAI(api_key=api_key)
else:
    client = None
    print("WARNING: OPENAI_API_KEY is missing!")

SYSTEM_PROMPT = "אתה עוזרת אדמיניסטרטיבית חכמה לקליניקה. תעני בקצרה, בעברית, ותנסי להבין מה המטרה של המתקשר."

@app.post("/voice")
async def voice_entry():
    response = VoiceResponse()
    
    gather = Gather(
        input='speech',
        action='/process',
        language='he-IL',
        speechTimeout='auto',
        enhanced=True
    )
    gather.say("שלום, הגעתם לקליניקה. איך אפשר לעזור?", language='he-IL')
    response.append(gather)
    
    response.redirect('/voice')
    
    return Response(content=str(response), media_type="application/xml")

@app.post("/process")
async def process_speech(SpeechResult: str = Form(default="")):
    if not client:
        ai_response = "חסר מפתח מערכת, אנא עדכן את השרת."
    else:
        try:
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": SpeechResult}
                ]
            )
            ai_response = completion.choices[0].message.content
        except Exception as e:
            print(f"Error calling OpenAI: {e}")
            ai_response = "סליחה, אני חווה תקלה קלה. תוכל לחזור על זה?"

    response = VoiceResponse()
    
    gather = Gather(
        input='speech',
        action='/process',
        language='he-IL',
        speechTimeout='auto'
    )
    
    gather.say(ai_response, language='he-IL')
    response.append(gather)
    
    response.redirect('/voice')

    return Response(content=str(response), media_type="application/xml")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

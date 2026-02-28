import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI

app = FastAPI()

# משיכת המפתח וניקוי אגרסיבי של תווים נסתרים או רווחים שהועתקו בטעות
raw_api_key = os.getenv("OPENAI_API_KEY")
if raw_api_key:
    clean_api_key = raw_api_key.strip().replace('\u2028', '').replace('\u2029', '')
    client = OpenAI(api_key=clean_api_key)
else:
    client = None
    print("WARNING: OPENAI_API_KEY is missing!")

# שימוש בקול נשי ישראלי של גוגל הנתמך ב-Twilio
HEBREW_VOICE = 'Google.he-IL-Wavenet-B'
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
    # הוספת הגדרת הקול המפורשת
    gather.say("שלום, הגעתם לקליניקה. איך אפשר לעזור?", language='he-IL', voice=HEBREW_VOICE)
    response.append(gather)
    
    response.redirect('/voice')
    
    # הוספת קידוד UTF-8 כדי לוודא שעברית עוברת חלק
    return Response(content=str(response), media_type="application/xml; charset=utf-8")

@app.post("/process")
async def process_speech(SpeechResult: str = Form(default="")):
    if not client:
        ai_response = "חסר מפתח מערכת, אנא בדוק הגדרות."
    else:
        try:
            # ניקוי הטקסט שהגיע מ-Twilio מתווים נסתרים
            clean_speech = SpeechResult.replace('\u2028', ' ').replace('\u2029', ' ').strip()
            
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": clean_speech}
                ]
            )
            ai_response = completion.choices[0].message.content
        except Exception as e:
            print(f"Error calling OpenAI: {e}")
            ai_response = "סליחה, אני חווה תקלה קלה במערכת. אפשר לחזור על זה?"

    response = VoiceResponse()
    
    gather = Gather(
        input='speech',
        action='/process',
        language='he-IL',
        speechTimeout='auto'
    )
    
    gather.say(ai_response, language='he-IL', voice=HEBREW_VOICE)
    response.append(gather)
    
    response.redirect('/voice')

    return Response(content=str(response), media_type="application/xml; charset=utf-8")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))   

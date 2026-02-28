import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import Response
    from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI

app = FastAPI()

# הגדרת OpenAI - ודא שה-API KEY נמצא ב-Variables ב-Railway
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = "אתה עוזרת אדמיניסטרטיבית חכמה לקליניקה. תעני בקצרה, בעברית, ותנסי להבין מה המטרה של המתקשר."

@app.post("/voice")
async def voice_entry():
    """נקודת הכניסה של השיחה - כאן הכל מתחיל"""
    response = VoiceResponse()
    
    # הודעת פתיחה ואיסוף דיבור
    gather = Gather(
        input='speech',
        action='/process', # לאן לשלוח את מה שנאמר
        language='he-IL',  # תמיכה בעברית
        speechTimeout='auto',
        enhanced=True      # איכות זיהוי גבוהה יותר
    )
    gather.say("שלום, הגעתם לקליניקה. איך אפשר לעזור?", language='he-IL')
    response.append(gather)
    
    # אם המשתמש שתק ולא אמר כלום
    response.redirect('/voice')
    
    return Response(content=str(response), media_type="application/xml")

@app.post("/process")
async def process_speech(SpeechResult: str = Form(...)):
    """כאן קורה הקסם - עיבוד הדיבור ושליחה ל-AI"""
    
    # 1. שליחת הטקסט מ-Twilio ל-OpenAI
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini", # מהיר וזול יותר לשיחות קוליות
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": SpeechResult}
            ]
        )
        ai_response = completion.choices[0].message.content
    except Exception as e:
        print(f"Error calling OpenAI: {e}")
        ai_response = "סליחה, אני חווה תקלה קלה. תוכל לחזור על זה?"

    # 2. בניית תגובה ל-Twilio
    response = VoiceResponse()
    
    # יצירת Gather חדש כדי להמשיך את הלולאה
    gather = Gather(
        input='speech',
        action='/process',
        language='he-IL',
        speechTimeout='auto'
    )
    
    # ה-AI מדבר את התשובה ואז מחכה שוב לדיבור
    gather.say(ai_response, language='he-IL')
    response.append(gather)
    
    # גיבוי - אם המשתמש לא עונה, נחזור לתחילת הלולאה
    response.redirect('/voice')

    return Response(content=str(response), media_type="application/xml")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

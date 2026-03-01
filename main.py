import os
import urllib.parse
from fastapi import FastAPI, Request, Form
from fastapi.responses import Response, StreamingResponse
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI

app = FastAPI()

# משיכת המפתח וניקוי תווים נסתרים
raw_api_key = os.getenv("OPENAI_API_KEY")
if raw_api_key:
    clean_api_key = raw_api_key.strip().replace('\u2028', '').replace('\u2029', '')
    client = OpenAI(api_key=clean_api_key)
else:
    client = None
    print("WARNING: OPENAI_API_KEY is missing!")

SYSTEM_PROMPT = "אתה עוזרת אדמיניסטרטיבית חכמה לקליניקה. תעני בקצרה, בעברית, בסגנון שירותי ונעים, ותנסי להבין מה המטרה של המתקשר. אל תחפרי, עני במשפטים קצרים בלבד."

@app.post("/voice")
async def voice_entry():
    """נקודת הכניסה - עונה לשיחה ומנגנת את פתיח האודיו הראשון"""
    response = VoiceResponse()
    
    gather = Gather(
        input='speech',
        action='/process',
        language='he-IL',
        speechTimeout='auto',
        enhanced=True
    )
    
    # במקום להקריא טקסט ברובוטיות, אנחנו שולחים ל-Twilio אודיו להשמעה
    intro_text = "שלום, הגעתם לקליניקה. איך אפשר לעזור?"
    encoded_text = urllib.parse.quote(intro_text)
    gather.play(f"/tts?text={encoded_text}")
    
    response.append(gather)
    response.redirect('/voice')
    
    return Response(content=str(response), media_type="application/xml; charset=utf-8")

@app.post("/process")
async def process_speech(SpeechResult: str = Form(default="")):
    """מעבד את התשובה ומחזיר אודיו חדש"""
    if not client:
        ai_response = "חסר מפתח מערכת."
    else:
        try:
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
            ai_response = "סליחה, לא שמעתי טוב. תוכל לחזור על זה?"

    response = VoiceResponse()
    
    gather = Gather(
        input='speech',
        action='/process',
        language='he-IL',
        speechTimeout='auto'
    )
    
    # ממירים את תשובת ה-AI לאודיו ריאליסטי ומנגנים אותה
    encoded_ai_response = urllib.parse.quote(ai_response)
    gather.play(f"/tts?text={encoded_ai_response}")
    
    response.append(gather)
    response.redirect('/voice')

    return Response(content=str(response), media_type="application/xml; charset=utf-8")

@app.get("/tts")
async def generate_tts(text: str):
    """Endpoint חדש שמייצר אודיו ריאליסטי מ-OpenAI ומשדר אותו ל-Twilio"""
    if not client:
         return Response(status_code=500)
         
    # פנייה למנוע הקול של OpenAI (המודל nova מייצר קול נשי טבעי)
    response = client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=text
    )
    
    # שידור קובץ ה-MP3 חזרה לשיחה
    return StreamingResponse(response.iter_bytes(), media_type="audio/mpeg")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

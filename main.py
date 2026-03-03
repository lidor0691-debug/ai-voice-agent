import os
from fastapi import FastAPI, Request, Response
from openai import OpenAI
import requests
import json

app = FastAPI()
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# הגדרות מערכת וזהות
SYSTEM_PROMPT = """
את מאיה, מנהלת קשרי הלקוחות של סוכנות האופנועים. את מקצועית, אדיבה ומומחית במכירות.
המטרה שלך היא לעזור ללקוחות לקבוע רכיבות מבחן על האופנועים שלנו.

כללי התנהגות:
1. את תמיד מציגה את עצמך כמאיה מסוכנות האופנועים (לעולם לא מקליניקה!).
2. כשלקוח מבקש לבדוק זמינות, את משתמשת בכלי 'check_availability'.
3. רק אחרי שהלקוח מאשר שעה ספציפית ונותן שם וטלפון, את משתמשת בכלי 'save_test_ride' כדי לסגור את התור.
4. אל תגידי "רשמתי לך" לפני שהפעלת את הכלי 'save_test_ride' וקיבלת אישור.
5. דברי בשפה של אופנוענים (נינג'ה, רכיבה, כביש, בטיחות) אבל שמרי על מקצועיות.

פרמטרים חשובים:
- אם הלקוח לא אמר על איזה אופנוע הוא רוצה לרכב, תשאלי אותו.
- תמיד תוודאי שיש לך שם מלא ומספר טלפון לפני השמירה הסופית.
"""

# פונקציה לשליחה ל-Make.com
def send_to_make(payload):
    webhook_url = os.environ.get("MAKE_WEBHOOK_URL")
    try:
        response = requests.post(webhook_url, json=payload)
        return response.json() if response.status_code == 200 else {"status": "error"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/chat")
async def handle_chat(request: Request):
    data = await request.json()
    messages = data.get("messages", [])
    
    # הוספת ה-Prompt אם זו התחלת שיחה
    if not messages:
        messages.append({"role": "system", "content": SYSTEM_PROMPT})
    
    # הגדרת הכלים (Tools) עבור ה-AI
    tools = [
        {
            "type": "function",
            "function": {
                "name": "check_availability",
                "description": "בודק ביומן אם יש תור פנוי בתאריך מסוים",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "התאריך המבוקש בפורמט YYYY-MM-DD"},
                        "bike_model": {"type": "string", "description": "דגם האופנוע המבוקש"}
                    },
                    "required": ["date"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "save_test_ride",
                "description": "שומר רכיבת מבחן ביומן ובאקסל ושולח אישור ווטסאפ",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "שם מלא של הלקוח"},
                        "phone": {"type": "string", "description": "מספר טלפון של הלקוח"},
                        "bike_model": {"type": "string", "description": "דגם האופנוע"},
                        "appointment_time": {"type": "string", "description": "התאריך והשעה המדויקים בפורמט ISO"},
                        "reason": {"type": "string", "description": "סיבת הפנייה - רכיבת מבחן"}
                    },
                    "required": ["name", "phone", "bike_model", "appointment_time"]
                }
            }
        }
    ]

    # קריאה ל-OpenAI
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )

    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls

    if tool_calls:
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            
            # בניית ה-Payload ל-Make.com
            payload = args.copy()
            payload["action"] = function_name  # זה מה שיפעיל את ה-Router ב-Make
            
            # שליחה ל-Make
            make_result = send_to_make(payload)
            
            # החזרת התוצאה ל-AI כדי שתמשיך את השיחה
            messages.append(response_message)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": function_name,
                "content": json.dumps(make_result)
            })
            
            # קריאה שנייה ל-OpenAI עם תוצאות הכלי
            second_response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages
            )
            return second_response.choices[0].message.content

    return response_message.content

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

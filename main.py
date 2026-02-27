from fastapi import FastAPI
from fastapi.responses import Response

app = FastAPI()

@app.post("/voice")
async def voice():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say>עכשיו זה עובד באמת. אם אתה שומע את זה, אין יותר באגים.</Say>
</Response>"""
    return Response(content=xml, media_type="application/xml")

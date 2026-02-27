from fastapi import FastAPI, Request
from fastapi.responses import Response
import urllib.parse

app = FastAPI()

def twiml(xml: str):
    return Response(content=xml, media_type="application/xml")

@app.api_route("/voice", methods=["GET", "POST"])
async def voice(request: Request):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="en-US" voice="alice">Tell me something, and I will repeat it.</Say>
  <Gather input="speech" action="/gather" method="POST" speechTimeout="auto" />
  <Say>Sorry, I did not hear you.</Say>
</Response>"""
    return twiml(xml)

@app.post("/gather")
async def gather(request: Request):
    form = await request.form()
    text = form.get("SpeechResult") or ""
    safe = urllib.parse.quote(text)  # כדי שלא ישבור XML
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="en-US" voice="alice">You said: {text}</Say>
  <Redirect method="POST">/voice</Redirect>
</Response>"""
    return twiml(xml)

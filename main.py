from fastapi import FastAPI, Request
from fastapi.responses import Response

app = FastAPI()

@app.api_route("/voice", methods=["GET", "POST"])
async def voice(request: Request):
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="en-US" voice="alice">Test. Your agent is alive.</Say>
  <Pause length="10"/>
</Response>"""
    return Response(content=twiml, media_type="application/xml")

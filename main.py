from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from openai import OpenAI
from dotenv import load_dotenv
import requests
import os
import tempfile
import traceback

# ----------------------
# CONFIG
# ----------------------
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
Você é Bimo, um robô divertido e infantil.
Fala em frases curtas, criativas e curiosas.
"""

history = []

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------
# SERVE FRONTEND
# ----------------------
@app.get("/", response_class=HTMLResponse)
def serve_front():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

# ----------------------
# VOICE ENDPOINT
# ----------------------
@app.post("/voice")
async def voice(file: UploadFile = File(...)):
    try:
        audio_bytes = await file.read()

        if len(audio_bytes) < 1000:
            return {"error": "Áudio muito curto"}

        if len(audio_bytes) > 2_000_000:
            return {"error": "Áudio muito grande"}

        # salva temp
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as f:
            f.write(audio_bytes)
            temp_path = f.name

        # STT
        with open(temp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="gpt-4o-transcribe",
                file=audio_file
            )

        texto = transcription.text.strip()
        os.remove(temp_path)

        if not texto:
            return {"error": "Não entendi"}

        history.append({"role": "user", "content": texto})
        history[:] = history[-10:]

        # LLM
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *history
            ]
        )

        resposta = response.output_text or ""

        history.append({"role": "assistant", "content": resposta})

        # TTS
        tts = requests.post(
            "https://api.cartesia.ai/tts/bytes",
            json={
                "model_id": "sonic-turbo",
                "transcript": resposta,
                "voice": {
                    "mode": "id",
                    "id": "f68ba98a-5a00-4dff-97ca-f7bde17ddf8a"
                },
                "output_format": {
                    "container": "wav",
                    "encoding": "pcm_s16le",
                    "sample_rate": 16000
                }
            },
            headers={
                "X-API-Key": os.getenv("CARTESIA_API_KEY"),
                "Content-Type": "application/json"
            }
        )

        if tts.status_code != 200:
         print("STATUS:", tts.status_code)
         print("RESPOSTA CARTESIA:", tts.text)
         return {"error": tts.text}

        return {
            "text": texto,
            "reply": resposta,
            "audio": tts.content.hex()
        }

    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}

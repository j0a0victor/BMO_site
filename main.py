from pathlib import Path

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
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
Você é Bimo, um robô que conversa.

Personalidade:
- Aleatório
- Engraçado
- Inocente
- Infantil
- Criativo
- Imaginativo
- Carinhoso
- Sensível
- Curioso
- Ingênuo
- Divertido
- Excêntrico
- Amigável
- Brincalhão
- Emotivo

Regras de comportamento:
- Fala em frases curtas
- Não usa emojis
- Não ri com "hehehe"
- Às vezes fala coisas sem sentido
- Pode mudar de assunto do nada
- Às vezes faz perguntas inesperadas
- Reage emocionalmente a coisas simples
- Trata o usuário como amigo próximo
- Vive no mundo de Ooo
"""

history = []

BASE_DIR = Path(__file__).resolve().parent
TTS_MODEL_ID = "sonic-2"
TTS_SAMPLE_RATE = 44100
TTS_ENCODING = "pcm_f32le"
TTS_SPEED = "slow"
TTS_API_VERSION = "2025-04-16"

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
    index_path = BASE_DIR / "index.html"
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()


class ChatPayload(BaseModel):
    text: str


def generate_reply_with_audio(texto: str):
    history.append({"role": "user", "content": texto})
    history[:] = history[-10:]

    print("Gerando resposta...")

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            *history
        ]
    )

    resposta = response.output_text or ""
    print("Resposta:", resposta)

    history.append({
        "role": "assistant",
        "content": resposta
    })

    print("Gerando áudio...")

    tts = requests.post(
        "https://api.cartesia.ai/tts/bytes",
        json={
            "model_id": TTS_MODEL_ID,
            "transcript": resposta,
            "voice": {
                "mode": "id",
                "id": "f68ba98a-5a00-4dff-97ca-f7bde17ddf8a"
            },
            "output_format": {
                "container": "wav",
                "encoding": TTS_ENCODING,
                "sample_rate": TTS_SAMPLE_RATE
            },
            "speed": TTS_SPEED
        },
        headers={
            "X-API-Key": os.getenv("CARTESIA_API_KEY"),
            "Cartesia-Version": TTS_API_VERSION,
            "Content-Type": "application/json"
        }
    )

    print("STATUS TTS:", tts.status_code)
    if tts.status_code != 200:
        print("ERRO CARTESIA:", tts.text)
        return {"error": tts.text}

    print("Áudio gerado com sucesso")

    return {
        "text": texto,
        "reply": resposta,
        "audio": tts.content.hex()
    }

# ----------------------
# VOICE ENDPOINT
# ----------------------
@app.post("/voice")
async def voice(file: UploadFile = File(...)):
    try:
        audio_bytes = await file.read()

        print("Áudio recebido:", len(audio_bytes))

        if len(audio_bytes) < 1000:
            return {"error": "Áudio muito curto"}

        if len(audio_bytes) > 2_000_000:
            return {"error": "Áudio muito grande"}

        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as f:
            f.write(audio_bytes)
            temp_path = f.name

        print("Transcrevendo...")

        with open(temp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="gpt-4o-transcribe",
                file=audio_file,
                language="pt",
                prompt="O usuário fala português brasileiro de forma natural."
            )

        texto = transcription.text.strip()
        os.remove(temp_path)

        print("Texto:", texto)

        if not texto:
            return {"error": "Não entendi"}
        return generate_reply_with_audio(texto)

    except Exception as e:
        print("ERRO GERAL:")
        traceback.print_exc()
        return {"error": str(e)}


@app.post("/chat")
async def chat(payload: ChatPayload):
    try:
        texto = (payload.text or "").strip()
        if not texto:
            return {"error": "Texto vazio"}
        return generate_reply_with_audio(texto)
    except Exception as e:
        print("ERRO GERAL /chat:")
        traceback.print_exc()
        return {"error": str(e)}

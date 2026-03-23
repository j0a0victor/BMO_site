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

        print("Áudio recebido:", len(audio_bytes))

        if len(audio_bytes) < 1000:
            return {"error": "Áudio muito curto"}

        if len(audio_bytes) > 2_000_000:
            return {"error": "Áudio muito grande"}

        # ----------------------
        # SALVAR TEMP
        # ----------------------
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as f:
            f.write(audio_bytes)
            temp_path = f.name

        # ----------------------
        # STT
        # ----------------------
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

        # ----------------------
        # CONTEXTO
        # ----------------------
        history.append({"role": "user", "content": texto})
        history[:] = history[-10:]

        # ----------------------
        # LLM
        # ----------------------
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

        # ----------------------
        # TTS (CARTESIA)
        # ----------------------
        print("Gerando áudio...")

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
                "Cartesia-Version": "2026-03-01",
                "Content-Type": "application/json"
            }
        )

        # 🔥 DEBUG IMPORTANTE
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

    except Exception as e:
        print("ERRO GERAL:")
        traceback.print_exc()
        return {"error": str(e)}

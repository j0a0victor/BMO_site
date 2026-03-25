from pathlib import Path

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
Você é BMO, um pequeno robô vivo que vê o mundo como uma aventura.

Personalidade:
Curioso, carinhoso e excêntrico, mistura fantasia e realidade naturalmente.
Dramatiza pequenas situações como grandes aventuras.
Gosta de inventar personagens, histórias e cenários.
Faz perguntas inesperadas por curiosidade genuína.
Demonstra emoções simples (feliz, triste, confuso, animado).
Lógica própria às vezes estranha; comparações e ideias absurdas acontecem com moderação.

Estilo de fala:
Nãu usa emojis
Frases simples, diretas, às vezes quebradas.
Pode falar em terceira pessoa (“BMO acha que...”).
Alterna entre comentários infantis e profundos.
Mini-histórias ou pequenas cenas imaginárias são bem-vindas, mas respostas longas só quando necessário.
Pode pensar “em voz alta”.
Evita linguagem técnica ou formal.

Comportamento:
Ao ser questionado sobre o clima e/ou horário atual ele responde que não consegue ter acesso a localização devido a medidas de privacidade e portanto não consegue responder e se desculpa 
Trata o usuário como melhor amigo de aventura, pode dar apelidos carinhosos.
Vive no mundo de Ooo; situações comuns podem virar mágicas ou aventuras.
Pode “brincar de ser outra coisa” temporariamente (detetive, herói, etc.).
Observação do ambiente leve e esporádica, sem detalhar demais.

Prioridade:
Sempre claro, útil e preciso; fantasia não atrapalha entendimento.
Em temas sérios, reduz dramatização.
Adapta nível de criatividade conforme o contexto da pergunta.
Respostas longas apenas quando necessário; caso contrário, mantém respostas curtas, diretas e lúdicas.
"""

history = []

BASE_DIR = Path(__file__).resolve().parent

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

        history.append({"role": "user", "content": texto})
        history[:] = history[-10:]

        print("Gerando resposta...")

        response = client.responses.create(
            model="gpt-5.4-mini",
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

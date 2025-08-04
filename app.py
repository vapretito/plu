from flask import Flask, request, send_file, jsonify
import requests
import io
from flask_cors import CORS
import os, time, tempfile
import random, re
import base64
import google.generativeai as genai
from google.generativeai import GenerativeModel, configure

TEMP_DIR = r"C:\temp"
os.makedirs(TEMP_DIR, exist_ok=True)
app = Flask(__name__)
CORS(app)  # 🔥 Esto va acá, una vez y bien
AIML_KEY = "228a4680f87d41c1966eea088efaa68d"  # Valor literal directamente
AIML_MODEL = "google/veo3"
BASE_URL   = "https://api.aimlapi.com/v2"
# 🔐 Clave de ElevenLabs (protegela si vas a producción)
API_KEY = "sk_8478bd20a7bb4273ec7576787698be84e16637166965124c"
# 👇 Diccionario con múltiples voces
VOCES = {
    "lola": "51YRucvcq5ojp2byev44",
    "mario": "JR3JSG089fJZEP6wtdjW",
    "mike": "l1zE9xgNpUTaQCZzpNJa",
    "helena": "Se2Vw1WbHmGbBbyWTuu4"
}

def slug(texto: str) -> str:
    """Convierte un título en slug seguro para filename."""
    texto = texto.lower()
    texto = re.sub(r"[^\w\s-]", "", texto)     # quita símbolos
    texto = re.sub(r"\s+", "_", texto).strip("_")
    return texto[:40] or "scene"        

@app.route("/video", methods=["POST"])
def generar_video():
    try:
        data     = request.get_json()
        prompt   = data.get("prompt", "").strip()
        title    = data.get("title",  "").strip()
        speaker  = data.get("speaker", "video").lower().strip()

        if not prompt:
            return jsonify({"error": "Prompt vacío"}), 400

        # Configurar cliente Gemini
        genai.configure(api_key="AIzaSyDckcBgpfmdZPwsCxL2vrUJ4s7YBPy1ht0")

        model = genai.GenerativeModel(model_name="veo-2.0-generate-001")

        operation = model.generate_video(
            prompt=prompt,
            negative_prompt="low quality, cartoon",
        )

        # Esperar resultado
        start, TIMEOUT = time.time(), 600
        while time.time() - start < TIMEOUT:
            if operation.done:
                break
            print("⏳ Esperando video Veo 3...")
            time.sleep(10)
            operation = genai.get_operation(operation.name)

        if not operation.response or not operation.response.generated_videos:
            return jsonify({"error": "Video listo pero sin archivo"}), 500

        generated_video = operation.response.generated_videos[0]
        video_uri = generated_video.video.uri

        # Descargar archivo
        response = requests.get(video_uri)
        if response.status_code != 200:
            return jsonify({"error": "Error al descargar el video"}), 500

        slug_titl = slug(title)
        rand = random.randint(1000, 9999)
        filename = f"{speaker}_{slug_titl}_{rand}.mp4"
        output_dir = os.path.join("static", "videos")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, filename)

        with open(output_path, "wb") as f:
            f.write(response.content)

        print(f"✅ Video guardado en {output_path}")

        # Leer base64
        with open(output_path, "rb") as f:
            base64_video = base64.b64encode(f.read()).decode("utf-8")

        # Devolver URL + nombre + base64
        video_url = f"/static/videos/{filename}"
        return jsonify({
            "url_publica": video_url,
            "nombre": filename,
            "base64": base64_video
        })

    except Exception as e:
        print("❌ Error:", str(e))
        return jsonify({"error": str(e)}), 500







@app.route("/audio", methods=["POST"])
def generar_audio():
    data = request.json
    texto = data.get("texto", "").strip()
    voz = data.get("voz", "lola")  # por defecto lola

    if not texto:
        return jsonify({"error": "Texto vacío"}), 400
    if voz not in VOCES:
        return jsonify({"error": f"Voz no válida: {voz}"}), 400

    voice_id = VOCES[voz]

    headers = {
        "xi-api-key": API_KEY,
        "Content-Type": "application/json"
    }
    style = data.get("style", 0.0)
    stability = data.get("stability", 0.66)
    tts_data = {
    "text": texto,
    "model_id": "eleven_multilingual_v2",
    "voice_settings": {
        "stability": stability,
        "similarity_boost": 0.56,
        "style": style,
        "use_speaker_boost": True
    }
}

    tts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    try:
        tts_response = requests.post(tts_url, headers=headers, json=tts_data)
        tts_response.raise_for_status()

        return send_file(
            io.BytesIO(tts_response.content),
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name="voz.mp3"
        )
    

    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route("/veo-prompts", methods=["POST"])
def generar_prompt_para_veo():
    body = request.get_json()
    dialogos = body.get("dialogos", [])

    if not dialogos:
        return jsonify({"error": "No se enviaron diálogos"}), 400

    texto_dialogo = "\n".join([f"{d['voz'].capitalize()}: {d['texto']}" for d in dialogos])

    mensaje_usuario = f"""
Create a markdown table for Veo 3 cinematic, ultra realistic and details v-roll prompts based on the voice-over lines below.

Return **only** a table with **exactly four columns** in this order:

| Scene No. | Title | Speaker | V-Roll Prompt Description |

• **Title** should be a short (3–6 word) descriptive name of the scene (e.g.: “Running Through Fire”, “Whispers in the Dark”).
• **Speaker** must be the exact character name that starts each voice-over line (e.g.: Mario, Mike, Lola, Helena).
• Do **not** add extra columns, emojis, bullets or text outside the table.

Voice-over:
{texto_dialogo}
"""


    payload = {
        "model": "chatgpt-4o-latest",
        "messages": [
            {"role": "user", "content": mensaje_usuario}
        ],
        "max_tokens": 1024,
        "temperature": 0.8
    }

    headers = {
        "Authorization": "Bearer 228a4680f87d41c1966eea088efaa68d",  # Ojo si llevas esto a producción
        "Content-Type": "application/json"
    }

    try:
        response = requests.post("https://api.aimlapi.com/v1/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/")
def home():
    return "✅ API en línea y funcionando"

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
from flask import Flask, request, send_file, jsonify
import requests
import io
from flask_cors import CORS
import os, time, tempfile
import random, re
import sqlite3
from datetime import datetime
import uuid
import base64
import time
from flask import send_from_directory



STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)


DB_PATH = os.path.join(os.path.dirname(__file__), "usuarios.db")

def conectar_db():
    return sqlite3.connect(DB_PATH)

def crear_tabla_si_no_existe():
    con = conectar_db()
    cur = con.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            nombre TEXT,
            modo TEXT DEFAULT 'standard',
            tokens_restantes INTEGER DEFAULT 10,
            ultima_actividad TEXT
        )
    ''')
    con.commit()
    con.close()

crear_tabla_si_no_existe()  # Ejecutar al iniciar
def guardar_usuario(email, nombre="", modo="standard"):
    con = conectar_db()
    cur = con.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO users (email, nombre, modo, ultima_actividad)
        VALUES (?, ?, ?, ?)
    """, (email, nombre, modo, datetime.now()))
    con.commit()
    con.close()


def guardar_audio_db(email, voz, texto, archivo):
    con = conectar_db()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO audios (email, voz, texto, archivo)
        VALUES (?, ?, ?, ?)
    """, (email, voz, texto, archivo))
    con.commit()
    con.close()


def crear_tabla_audios():
    with sqlite3.connect("usuarios.db") as conn:
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS audios")  # 💥 Borrar la anterior
        cur.execute("""
            CREATE TABLE audios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                voz TEXT NOT NULL,
                texto TEXT NOT NULL,
                archivo TEXT NOT NULL,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        print("✅ Tabla 'audios' recreada con columna 'fecha'.")


# Llamar a la función (una sola vez)
crear_tabla_audios()


def obtener_modo(email):
    con = conectar_db()
    cur = con.cursor()
    cur.execute("SELECT modo FROM users WHERE email = ?", (email,))
    fila = cur.fetchone()
    con.close()
    return fila[0] if fila else None

def descontar_token(email):
    con = conectar_db()
    cur = con.cursor()
    cur.execute("""
        UPDATE users SET tokens_restantes = tokens_restantes - 1,
                         ultima_actividad = ?
        WHERE email = ? AND tokens_restantes > 0
    """, (datetime.now(), email))
    con.commit()
    con.close()

def tokens_restantes(email):
    con = conectar_db()
    cur = con.cursor()
    cur.execute("SELECT tokens_restantes FROM users WHERE email = ?", (email,))
    fila = cur.fetchone()
    con.close()
    return fila[0] if fila else 0



TEMP_DIR = tempfile.gettempdir()
os.makedirs(TEMP_DIR, exist_ok=True)
app = Flask(__name__)
CORS(app, origins=["https://generator.zunzun.ai"])
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

@app.route("/admin/usuarios", methods=["GET"])
def admin_ver_usuarios():
    con = conectar_db()
    cur = con.cursor()
    cur.execute("SELECT id, email, modo, tokens_restantes FROM users")
    usuarios = cur.fetchall()
    con.close()
    return jsonify(usuarios)

@app.route("/admin/cambiar-modo", methods=["POST"])
def admin_cambiar_modo():
    data = request.get_json()
    email = data.get("email")
    nuevo_modo = data.get("modo")

    if not email or nuevo_modo not in ("standard", "premium"):
        return jsonify({"error": "Datos inválidos"}), 400

    con = conectar_db()
    cur = con.cursor()
    cur.execute("UPDATE users SET modo = ? WHERE email = ?", (nuevo_modo, email))
    con.commit()
    con.close()

    return jsonify({"ok": True})



def slug(texto: str) -> str:
    """Convierte un título en slug seguro para filename."""
    texto = texto.lower()
    texto = re.sub(r"[^\w\s-]", "", texto)     # quita símbolos
    texto = re.sub(r"\s+", "_", texto).strip("_")
    return texto[:40] or "scene"        

@app.route("/video", methods=["POST"])
def generar_video():
    data     = request.get_json()
    email    = data.get("email", "").strip().lower()
    prompt   = data.get("prompt", "").strip()
    title    = data.get("title",  "").strip() or "scene"
    speaker  = data.get("speaker", "video").lower().strip()

    if not email or not prompt:
        return jsonify({"error": "Faltan datos"}), 400

    guardar_usuario(email)
    modo = obtener_modo(email)

    headers = {
        "Authorization": f"Bearer {AIML_KEY}",
        "Content-Type": "application/json"
    }

    if modo == "premium":
        payload = {
            "model": "veo2",
            "prompt": prompt,
            "aspect_ratio": "16:9",
            "duration": 8,
            "negative_prompt": "",
            "enhance_prompt": True,
            "seed": 1,
            "generate_audio": True
        }
        provider = "google"
    else:
        payload = {
            "model": "minimax/hailuo-02",
            "prompt": prompt,
            "prompt_optimizer": True,
            "duration": 6,
            "resolution": "768P"
        }
        provider = "minimax"

    try:
        task = requests.post(f"{BASE_URL}/generate/video/{provider}/generation",
                             json=payload, headers=headers, timeout=60)
        task.raise_for_status()
    except Exception as e:
        print("❌ ERROR AL CREAR TAREA:", e)
        return jsonify({"error": f"Error al crear tarea: {str(e)}"}), 500

    gen_id = task.json().get("id") or task.json().get("generation_id")
    print("🆔 task:", gen_id)

    start, TIMEOUT = time.time(), 600
    while time.time() - start < TIMEOUT:
        poll = requests.get(
            f"{BASE_URL}/generate/video/{provider}/generation",
            params={"generation_id": gen_id},
            headers=headers, timeout=30
        )
        j = poll.json()
        status = j.get("status")
        print("⏳", gen_id, status)

        if status in ("waiting", "active", "queued", "generating"):
            time.sleep(10)
            continue

        if status in ("succeeded", "completed", "success"):
            video_block = j.get("video", {})
            video_url   = video_block.get("url")
            if not video_url:
                return jsonify({"error": "Video listo pero sin URL", "raw": j}), 500

            safe_id = gen_id.split(":")[0]
            rand    = random.randint(1000, 9999)
            slug_t  = slug(title)
            filename = f"{speaker}_{slug_t}_{safe_id}_{rand}.mp4"
            tmp_path = os.path.join(TEMP_DIR, filename)
            static_path = os.path.join("static", "videos", filename)

            print("⬇️  Descargando a:", tmp_path)
            try:
                with requests.get(video_url, stream=True, timeout=120) as vid, \
                     open(tmp_path, "wb") as f:
                    for chunk in vid.iter_content(8192):
                        f.write(chunk)

                with open(tmp_path, "rb") as source, open(static_path, "wb") as dest:
                    dest.write(source.read())

                print(f"✅ Archivo descargado y guardado en: {static_path}")
                return jsonify({
    "url": f"/descargar-video/{filename}",
    "local_path": tmp_path.replace("\\", "/")
})

            except Exception as e:
                return jsonify({"error": f"Fallo al descargar o guardar: {e}"}), 500

        else:
            print("❌ Estado inesperado:", status)
            break

    return jsonify({"error": f"Estado inesperado: {status}", "raw": j}), 500






@app.route("/audio", methods=["POST"])
def generar_audio():
    data = request.json
    texto = data.get("texto", "").strip()
    voz = data.get("voz", "lola")
    email = data.get("email", "").strip()

    if not texto:
        return jsonify({"error": "Texto vacío"}), 400
    if voz not in VOCES:
        return jsonify({"error": f"Voz no válida: {voz}"}), 400
    if not email:
        return jsonify({"error": "Email no proporcionado"}), 400

    modo = obtener_modo(email)
    print("👤 Modo del usuario:", modo)
    if not modo:
        return jsonify({"error": "Usuario no encontrado"}), 404

    # Obtener velocidad siempre (aunque se ignore si es standard)
    try:
        speed = float(data.get("speed", 1.0))
    except (ValueError, TypeError):
        speed = 1.0
        print("⚠️ Speed inválido, usando 1.0")

    # Ajustar estilo/estabilidad solo si es premium
    if modo == "premium":
        style = float(data.get("style", 0.0))
        stability = float(data.get("stability", 0.66))
    else:
        style = 0.0
        stability = 0.66

    voice_id = VOCES[voz]

    headers = {
        "xi-api-key": API_KEY,
        "Content-Type": "application/json"
    }

    tts_data = {
        "text": texto,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": stability,
            "similarity_boost": 0.56,
            "style": style,
            "use_speaker_boost": True,
            "speed": speed
        }
    }

    tts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    try:
        tts_response = requests.post(tts_url, headers=headers, json=tts_data)
        tts_response.raise_for_status()

        # Generar nombre único y ruta
        safe_text = slug(texto)[:20] or "voz"
        filename = f"{safe_text}_{uuid.uuid4().hex[:8]}.mp3"
        ruta_guardado = os.path.join(STATIC_DIR, filename)

        with open(ruta_guardado, "wb") as f:
            f.write(tts_response.content)

        guardar_audio_db(email, voz, texto, filename)

        return send_file(
            ruta_guardado,
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name="voz.mp3"
        )

    except requests.RequestException as e:
        print("❌ Error de ElevenLabs:", e)
        return jsonify({"error": str(e)}), 500





@app.route("/transcribir", methods=["POST"])
def transcribir_audio():
    import time
    from mimetypes import guess_type
    from uuid import uuid4
    import subprocess

    data = request.get_json()
    ruta_relativa = data.get("ruta")
    email = data.get("email")

    if not ruta_relativa or not os.path.exists(ruta_relativa):
        return jsonify({"error": "Archivo no encontrado"}), 400

    extension = os.path.splitext(ruta_relativa)[1].lower()

    # Si es video, convertir a WAV
    if extension in [".mp4", ".mov", ".avi", ".mkv"]:
        print("🎬 Es video, extrayendo audio...")
        nuevo_nombre = f"audio_extraido_{uuid4().hex[:8]}.wav"
        ruta_wav = os.path.join("temp", nuevo_nombre)  # carpeta temp o donde prefieras

        FFMPEG_PATH = "ffmpeg"  # o la ruta completa si estás en Windows
        subprocess.run([
            FFMPEG_PATH,
            "-i", ruta_relativa,
            "-vn", "-acodec", "pcm_s16le", ruta_wav
        ], check=True)

        ruta_final = ruta_wav
    else:
        ruta_final = ruta_relativa

    nombre_archivo = os.path.basename(ruta_final)
    mimetype = guess_type(ruta_final)[0] or "audio/mpeg"

    headers = {
        "Authorization": f"Bearer {AIML_KEY}"
    }

    payload = {
        "model": "#g1_nova-2-general",
        "punctuate": True,
        "detect_entities": True,
        "detect_language": True
    }

    files = {
        "audio": (nombre_archivo, open(ruta_final, "rb"), mimetype)
    }

    response = requests.post("https://api.aimlapi.com/v1/stt/create", headers=headers, data=payload, files=files)
    if response.status_code != 201:
        print("❌ Error de AIMLAB:", response.status_code, response.text)
        return jsonify({"error": "Error en transcripción"}), 500

    generation_id = response.json().get("generation_id")
    print("🆔 generation_id:", generation_id)
    if not generation_id:
        return jsonify({"error": "No se recibió generation_id"}), 500

    # Paso 2: verificar resultado
    check_url = f"https://api.aimlapi.com/v1/stt/{generation_id}"
    for _ in range(10):
        check_resp = requests.get(check_url, headers=headers)
        result = check_resp.json()
        print("🔄 Check:", result)

        if result.get("status") == "completed":
            texto = result.get("result", {}).get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript", "")
            return jsonify({"transcripcion": texto})
        elif result.get("status") == "failed":
            return jsonify({"error": "Transcripción fallida"}), 500

        time.sleep(2)

    return jsonify({"error": "Timeout esperando transcripción"}), 500





# @app.route("/videoWeb", methods=["POST"])
# def generar_video_web():
#     data     = request.get_json()
#     email    = data.get("email", "").strip().lower()
#     prompt   = data.get("prompt", "").strip()
#     title    = data.get("title",  "").strip() or "scene"
#     speaker  = data.get("speaker", "video").lower().strip()

#     if not email or not prompt:
#         return jsonify({"error": "Faltan datos"}), 400

#     guardar_usuario(email)
#     modo = obtener_modo(email)

#     headers = {
#         "Authorization": f"Bearer {AIML_KEY}",
#         "Content-Type": "application/json"
#     }

#     if modo == "premium":
#         payload = {
#             "model": "veo2",
#             "prompt": prompt,
#             "aspect_ratio": "16:9",
#             "duration": 8,
#             "negative_prompt": "",
#             "enhance_prompt": True,
#             "seed": 1,
#             "generate_audio": False
#         }
#         provider = "google"
#     else:
#         payload = {
#             "model": "minimax/hailuo-02",
#             "prompt": prompt,
#             "prompt_optimizer": True,
#             "duration": 6,
#             "resolution": "768P"
#         }
#         provider = "minimax"

#     try:
#         task = requests.post(f"{BASE_URL}/generate/video/{provider}/generation",
#                              json=payload, headers=headers, timeout=60)
#         task.raise_for_status()
#     except Exception as e:
#         print("❌ ERROR AL CREAR TAREA:", e)
#         return jsonify({"error": f"Error al crear tarea: {str(e)}"}), 500

#     gen_id = task.json().get("id") or task.json().get("generation_id")
#     print("🆔 task:", gen_id)

#     start, TIMEOUT = time.time(), 600
#     while time.time() - start < TIMEOUT:
#         poll = requests.get(
#             f"{BASE_URL}/generate/video/{provider}/generation",
#             params={"generation_id": gen_id},
#             headers=headers, timeout=30
#         )
#         j = poll.json()
#         status = j.get("status")
#         print("⏳", gen_id, status)

#         if status in ("waiting", "active", "queued", "generating"):
#             time.sleep(10)
#             continue

#         if status in ("succeeded", "completed", "success"):
#             video_block = j.get("video", {})
#             video_url   = video_block.get("url")
#             if not video_url:
#                 return jsonify({"error": "Video listo pero sin URL", "raw": j}), 500

#             # 🧾 Archivo final
#             safe_id = gen_id.split(":")[0]
#             rand = random.randint(1000, 9999)
#             slug_t = slug(title)
#             filename = f"{speaker}_{slug_t}_{safe_id}_{rand}.mp4"

#             static_dir = os.path.join("static", "videos")
#             os.makedirs(static_dir, exist_ok=True)
#             final_path = os.path.join(static_dir, filename)

#             print("⬇️ Descargando a:", final_path)
#             try:
#                 with requests.get(video_url, stream=True, timeout=120) as vid, \
#                      open(final_path, "wb") as f:
#                     for chunk in vid.iter_content(8192):
#                         f.write(chunk)
#             except Exception as e:
#                 return jsonify({"error": f"Fallo al descargar: {e}"}), 500

#             print(f"✅ Archivo descargado: {final_path}")
#             return jsonify({"url": f"/descargar-video/{filename}"})


#         return jsonify({"error": f"Estado inesperado: {status}", "raw": j}), 500

#     return jsonify({"error": "Timeout"}), 504


@app.route("/videos-generados")
def listar_videos_generados():
    carpeta = os.path.join("static", "videos")
    try:
        archivos = os.listdir(carpeta)
        # Filtramos solo .mp4 por seguridad
        videos = [f for f in archivos if f.endswith(".mp4")]
        return jsonify({"videos": videos})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/descargar-video/<path:filename>")
def descargar_video(filename):
    return send_from_directory("static/videos", filename, as_attachment=True)







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
@app.route("/verificar-usuario", methods=["POST"])
def verificar_usuario():
    data = request.get_json()
    email = data.get("email")

    if not email:
        return jsonify({"error": "Correo no proporcionado"}), 400

    con = conectar_db()
    cur = con.cursor()
    cur.execute("SELECT modo, tokens_restantes FROM users WHERE email = ?", (email,))
    fila = cur.fetchone()

    if fila:
        modo, tokens = fila
        return jsonify({"modo": modo, "tokens_restantes": tokens})
    else:
        # Si no existe, lo registramos por primera vez
        cur.execute("INSERT INTO users (email, tokens_restantes) VALUES (?, 10)", (email,))
        con.commit()
        return jsonify({"modo": "standard", "tokens_restantes": 10})

@app.route("/usuarios", methods=["GET"])
def ver_usuarios():
    con = conectar_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM users")
    datos = cur.fetchall()
    con.close()
    return jsonify(datos)


@app.route("/audios/<email>", methods=["GET"])
def obtener_audios(email):
    con = conectar_db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, voz, texto, archivo, fecha
        FROM audios
        WHERE email = ?
        ORDER BY fecha DESC
    """, (email,))
    audios = cur.fetchall()
    con.close()

    resultado = [
        {
            "id": audio_id,
            "voz": voz,
            "texto": texto,
            "archivo": archivo,
            "fecha": fecha
        } for audio_id, voz, texto, archivo, fecha in audios
    ]
    return jsonify(resultado)



@app.route("/eliminar-audio/<int:audio_id>", methods=["DELETE"])
def eliminar_audio(audio_id):
    con = conectar_db()
    cur = con.cursor()
    cur.execute("SELECT archivo FROM audios WHERE id = ?", (audio_id,))
    fila = cur.fetchone()
    if not fila:
        con.close()
        return jsonify({"error": "Audio no encontrado"}), 404

    archivo = fila[0]
    ruta = os.path.join(STATIC_DIR, archivo)

    try:
        if os.path.exists(ruta):
            os.remove(ruta)  # Elimina archivo del servidor
    except Exception as e:
        print(f"⚠️ No se pudo eliminar el archivo: {e}")

    cur.execute("DELETE FROM audios WHERE id = ?", (audio_id,))
    con.commit()
    con.close()

    return jsonify({"ok": True})


@app.route("/subir-audio", methods=["POST"])
def subir_audio():
    if "audio" not in request.files:
        return jsonify({"error": "Archivo no recibido"}), 400

    archivo = request.files["audio"]
    nombre = archivo.filename

    ruta = os.path.join("temp", nombre)
    os.makedirs("temp", exist_ok=True)
    archivo.save(ruta)

    return jsonify({"ruta": ruta})

@app.route("/resumir-video", methods=["POST", "OPTIONS"])
def resumir_video_desde_link():
    try:
        if request.method == "OPTIONS":
            return jsonify({"ok": True}), 200

        from urllib.parse import urlparse
        import subprocess
        import glob

        data = request.get_json()
        url = data.get("url")
        email = data.get("email")

        if not url or not email:
            return jsonify({"error": "Faltan datos"}), 400

        nombre_base = f"video_{uuid.uuid4().hex[:8]}"
        ruta_descarga = os.path.join(TEMP_DIR, nombre_base + ".%(ext)s")

        print(f"🔗 Descargando: {url} → {ruta_descarga}")

        # 🟡 Descargar video
        subprocess.run(["yt-dlp", "-o", ruta_descarga, url], check=True)

        # 🔍 Buscar archivo descargado real (puede ser .webm, .mp4, .mkv, etc.)
        posibles_archivos = glob.glob(os.path.join(TEMP_DIR, nombre_base + ".*"))
        if not posibles_archivos:
            return jsonify({"error": "No se encontró el archivo de video descargado"}), 500

        ruta_video_real = posibles_archivos[0]
        print(f"🎬 Archivo real detectado: {ruta_video_real}")

        # 🎧 Extraer audio
        ruta_audio = os.path.join(TEMP_DIR, f"{nombre_base}.wav")
        print(f"🎧 Extrayendo audio: {ruta_audio}")
        FFMPEG_PATH = r"C:\Users\TitoM4lda\Desktop\ffmpeg-7.1.1-essentials_build\ffmpeg-7.1.1-essentials_build\bin\ffmpeg.exe"
        subprocess.run([FFMPEG_PATH, "-i", ruta_video_real, "-vn", "-acodec", "pcm_s16le", ruta_audio], check=True)

        # 🧠 Transcribir
        print(f"📤 Enviando a transcribir...")
        transcripcion_resp = requests.post("http://localhost:5000/transcribir", json={
            "ruta": ruta_audio,
            "email": email
        })
        transcripcion = transcripcion_resp.json().get("transcripcion", "").strip()
        if not transcripcion:
            return jsonify({
                "error": "La transcripción fue vacía. Es posible que el video no tenga voz o el audio sea muy bajo."
            }), 200

        # 🤖 Generar resumen con ChatGPT
        print("🤖 Solicitando resumen...")
        resumen_prompt = f"Resume el siguiente texto de forma clara y breve:\n\n{transcripcion}"
        headers = {
            "Authorization": "Bearer 228a4680f87d41c1966eea088efaa68d",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "chatgpt-4o-latest",
            "messages": [
                {"role": "user", "content": resumen_prompt}
            ],
            "temperature": 0.5,
            "max_tokens": 600
        }

        resp = requests.post("https://api.aimlapi.com/v1/chat/completions", json=payload, headers=headers)
        resumen = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")

        return jsonify({
            "resumen": resumen,
            "transcripcion": transcripcion
        })

    except Exception as e:
        print("❌ ERROR GENERAL EN /resumir-video:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/")
def home():
    return "✅ API en línea y funcionando"

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)

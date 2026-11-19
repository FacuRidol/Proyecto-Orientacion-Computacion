# servidor/rutas/voz.py
"""Reconocimiento de voz offline (Vosk, reconocimiento_voz.py).

RUTAS (las usa static/js/voz.js)
  GET  /api/voz/estado    ¿están Vosk y el modelo disponibles? (la página lo consulta al cargar).
  POST /api/voz/iniciar   abre la sesión de escucha (botón «Activar micrófono»).
  POST /api/voz/audio     recibe un fragmento de audio PCM (16 bits, 16 kHz) y devuelve el texto que se entiende (parcial o final).
  POST /api/voz/detener   cierra la sesión de escucha.
"""
from flask import Blueprint, current_app, jsonify, request

from funciones.reconocimiento_voz import servicio_voz

bp = Blueprint("voz", __name__)

# Tamaño máximo de un fragmento de audio aceptado (bytes).
AUDIO_MAXIMO_BYTES = 128_000


@bp.route("/api/voz/estado")
def estado_voz():
    return jsonify(servicio_voz.estado())


@bp.route("/api/voz/iniciar", methods=["POST"])
def iniciar_voz():
    try:
        servicio_voz.iniciar()
        return jsonify({"ok": True, "mensaje": "Micrófono activo. Reconocimiento offline iniciado."})
    except RuntimeError as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 503
    except Exception:
        current_app.logger.exception("Error al iniciar Vosk")
        return jsonify({"ok": False, "mensaje": "No se pudo iniciar el reconocimiento de voz."}), 500


@bp.route("/api/voz/audio", methods=["POST"])
def recibir_audio():
    audio_pcm = request.get_data(cache=False)
    # Rechaza audio vacío, demasiado grande o con un número impar de bytes (no sería PCM de 16 bits).
    if not audio_pcm or len(audio_pcm) > AUDIO_MAXIMO_BYTES or len(audio_pcm) % 2:
        return jsonify({"ok": False, "mensaje": "El fragmento de audio no es válido."}), 400

    try:
        # Si el navegador tuvo que descartar bloques antiguos para limitar la
        # latencia, Vosk limpia su contexto parcial antes de reconocer el audio nuevo.
        discontinuidad = request.headers.get("X-Audio-Discontinuity") == "1"
        return jsonify(
            servicio_voz.procesar_audio(
                audio_pcm,
                discontinuidad=discontinuidad,
            )
        )
    except RuntimeError as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 409
    except ValueError as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 400
    except Exception:
        current_app.logger.exception("Error al procesar audio con Vosk")
        return jsonify({"ok": False, "mensaje": "No se pudo procesar el audio."}), 500


@bp.route("/api/voz/detener", methods=["POST"])
def detener_voz():
    servicio_voz.detener()
    return jsonify({"ok": True, "mensaje": "Reconocimiento detenido."})

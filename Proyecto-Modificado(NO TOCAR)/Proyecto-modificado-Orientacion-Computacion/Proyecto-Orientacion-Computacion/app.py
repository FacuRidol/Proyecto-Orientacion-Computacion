# app.py

import re
import unicodedata

from flask import Flask, jsonify, render_template, request

import dispositivos as hw
from reconocimiento_voz import servicio_voz


app = Flask(__name__)


# ==========================================
# NORMALIZACION DE TEXTO
# ==========================================

def normalizar(texto):
    texto = texto.lower().strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(
        caracter
        for caracter in texto
        if unicodedata.category(caracter) != "Mn"
    )
    return texto


# ==========================================
# NUMEROS EN ESPANOL
# ==========================================

UNIDADES = {
    "cero": 0,
    "uno": 1,
    "una": 1,
    "un": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "once": 11,
    "doce": 12,
    "trece": 13,
    "catorce": 14,
    "quince": 15,
    "dieciseis": 16,
    "diecisiete": 17,
    "dieciocho": 18,
    "diecinueve": 19,
    "veinte": 20,
    "treinta": 30,
    "cuarenta": 40,
    "cincuenta": 50,
    "sesenta": 60,
    "setenta": 70,
    "ochenta": 80,
    "noventa": 90,
    "cien": 100,
    "ciento": 100,
    "ciento ochenta": 180,
}


def extraer_numero(texto):
    coincidencia = re.search(r"\b(\d{1,3})\b", texto)
    if coincidencia:
        return int(coincidencia.group(1))

    palabras = texto.split()
    for longitud in (3, 2, 1):
        for inicio in range(len(palabras) - longitud + 1):
            frase = " ".join(palabras[inicio:inicio + longitud])
            if frase not in UNIDADES:
                continue

            valor = UNIDADES[frase]
            if (
                30 <= valor < 100
                and inicio + longitud + 1 < len(palabras)
                and palabras[inicio + longitud] == "y"
            ):
                siguiente = UNIDADES.get(palabras[inicio + longitud + 1])
                if siguiente is not None and 1 <= siguiente <= 9:
                    valor += siguiente
            return valor
    return None


# ==========================================
# PAGINA PRINCIPAL Y ESTADO
# ==========================================

@app.route("/")
def inicio():
    return render_template("index.html")


@app.route("/api/estado")
def estado():
    return jsonify(hw.obtener_estado())


# ==========================================
# CONTROL DE LED
# ==========================================

@app.route("/api/led/<int:numero>", methods=["POST"])
def controlar_led(numero):
    datos = request.get_json(silent=True) or {}
    accion = datos.get("accion")
    if accion not in ("encender", "apagar"):
        return jsonify({"ok": False, "mensaje": "Acción no válida."}), 400

    try:
        encendido = accion == "encender"
        hw.controlar_led(numero, encendido)
        return jsonify({
            "ok": True,
            "mensaje": f"LED {numero}: {accion}.",
            "encendido": encendido,
        })
    except ValueError as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 400


# ==========================================
# CONTROL DEL SERVO
# ==========================================

@app.route("/api/servo", methods=["POST"])
def controlar_servo():
    datos = request.get_json(silent=True) or {}
    angulo = datos.get("angulo")

    if isinstance(angulo, bool) or not isinstance(angulo, int):
        return jsonify({
            "ok": False,
            "mensaje": "El ángulo debe ser un número entero.",
        }), 400
    if not 0 <= angulo <= 180:
        return jsonify({
            "ok": False,
            "mensaje": "El ángulo debe estar entre 0 y 180.",
        }), 400

    try:
        hw.mover_servo(angulo)
        return jsonify({
            "ok": True,
            "mensaje": f"Posición solicitada: {angulo}°.",
            "angulo": angulo,
        })
    except Exception:
        app.logger.exception("Error al mover el servo")
        return jsonify({
            "ok": False,
            "mensaje": "No se pudo controlar el servo.",
        }), 500


# ==========================================
# SENSOR ULTRASONICO
# ==========================================

@app.route("/api/sensor", methods=["POST"])
def controlar_sensor():
    datos = request.get_json(silent=True) or {}
    accion = datos.get("accion")
    if accion not in ("activar", "desactivar"):
        return jsonify({"ok": False, "mensaje": "Acción de sensor no válida."}), 400

    activo = accion == "activar"
    hw.configurar_sensor(activo)
    if activo:
        mensaje = "Medición continua activada."
    else:
        mensaje = "Medición continua desactivada."

    return jsonify({
        "ok": True,
        "mensaje": mensaje,
        "sensor_activo": activo,
    })


@app.route("/api/distancia")
def distancia():
    if not hw.sensor_esta_activo():
        return jsonify({
            "ok": False,
            "sensor_activo": False,
            "distancia_cm": None,
            "mensaje": "El sensor está desactivado.",
        })

    try:
        valor = hw.medir_distancia()
        return jsonify({
            "ok": valor is not None,
            "sensor_activo": True,
            "distancia_cm": valor,
            "mensaje": "Medición actualizada." if valor is not None else "No se obtuvo una medición válida.",
        })
    except Exception:
        app.logger.exception("Error al medir la distancia")
        return jsonify({
            "ok": False,
            "sensor_activo": True,
            "distancia_cm": None,
            "mensaje": "No se pudo consultar el sensor.",
        }), 500


# ==========================================
# RECONOCIMIENTO DE VOZ OFFLINE (VOSK)
# ==========================================

@app.route("/api/voz/estado")
def estado_voz():
    return jsonify(servicio_voz.estado())


@app.route("/api/voz/iniciar", methods=["POST"])
def iniciar_voz():
    try:
        servicio_voz.iniciar()
        return jsonify({"ok": True, "mensaje": "Micrófono activo. Reconocimiento offline iniciado."})
    except RuntimeError as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 503
    except Exception:
        app.logger.exception("Error al iniciar Vosk")
        return jsonify({"ok": False, "mensaje": "No se pudo iniciar el reconocimiento de voz."}), 500


@app.route("/api/voz/audio", methods=["POST"])
def recibir_audio():
    audio_pcm = request.get_data(cache=False)
    if not audio_pcm or len(audio_pcm) > 128_000 or len(audio_pcm) % 2:
        return jsonify({"ok": False, "mensaje": "El fragmento de audio no es válido."}), 400

    try:
        return jsonify(servicio_voz.procesar_audio(audio_pcm))
    except RuntimeError as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 409
    except ValueError as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 400
    except Exception:
        app.logger.exception("Error al procesar audio con Vosk")
        return jsonify({"ok": False, "mensaje": "No se pudo procesar el audio."}), 500


@app.route("/api/voz/detener", methods=["POST"])
def detener_voz():
    servicio_voz.detener()
    return jsonify({"ok": True, "mensaje": "Reconocimiento detenido."})


# ==========================================
# COMANDOS DE VOZ
# ==========================================

@app.route("/api/comando", methods=["POST"])
def comando():
    datos = request.get_json(silent=True) or {}
    texto = normalizar(str(datos.get("comando", "")))

    if not texto or len(texto) > 200:
        return jsonify({"ok": False, "mensaje": "El comando está vacío o es demasiado largo."}), 400

    # El sensor tiene prioridad si el comando pide activarlo o desactivarlo.
    menciona_sensor = re.search(
        r"\b(sensor|medicion|mediciones|ultrasonico|ultrasonica|distancia)\b",
        texto,
    )
    if menciona_sensor:
        if re.search(r"\b(desactivar|desactiva|apagar|apaga|detener|detene|parar|para|finalizar|finaliza|desconectar|desconecta)\b", texto):
            hw.configurar_sensor(False)
            return jsonify({"ok": True, "mensaje": "Medición continua desactivada.", "sensor_activo": False})
        if re.search(r"\b(activar|activa|encender|encende|prender|prende|iniciar|inicia|comenzar|comienza)\b", texto):
            hw.configurar_sensor(True)
            return jsonify({"ok": True, "mensaje": "Medición continua activada.", "sensor_activo": True})

    # LED individual.
    coincidencia = re.search(r"\bled\s+(\d+|[a-z]+)\b", texto)
    if coincidencia:
        numero_texto = coincidencia.group(1)
        numero = int(numero_texto) if numero_texto.isdigit() else UNIDADES.get(numero_texto)
        if numero is None:
            return jsonify({"ok": False, "mensaje": "No pude identificar el número del LED."}), 400

        if re.search(r"\b(encender|prender|activar|enciende|prende|prendeme|enciendeme)\b", texto):
            accion = "encender"
        elif re.search(r"\b(apagar|desactivar|apaga|desactiva)\b", texto):
            accion = "apagar"
        else:
            return jsonify({"ok": False, "mensaje": "Indicá si querés encender o apagar el LED."}), 400

        try:
            hw.controlar_led(numero, accion == "encender")
            return jsonify({"ok": True, "mensaje": f"LED {numero}: {accion}.", "led": numero, "encendido": accion == "encender"})
        except ValueError as error:
            return jsonify({"ok": False, "mensaje": str(error)}), 400

    # Servomotor.
    if "servo" in texto:
        angulo = extraer_numero(texto)
        if angulo is None or not 0 <= angulo <= 180:
            return jsonify({"ok": False, "mensaje": "Indicá un ángulo entre 0 y 180 grados."}), 400
        try:
            hw.mover_servo(angulo)
            return jsonify({"ok": True, "mensaje": f"Servo: posición solicitada de {angulo}°.", "angulo": angulo})
        except Exception:
            app.logger.exception("Error al mover el servo mediante voz")
            return jsonify({"ok": False, "mensaje": "No se pudo mover el servo."}), 500

    # Lectura puntual de distancia; para una lectura en vivo primero se activa.
    if re.search(r"\b(distancia|cerca|lejos|medir|medime)\b", texto):
        if not hw.sensor_esta_activo():
            return jsonify({
                "ok": False,
                "mensaje": "El sensor está desactivado. Decí ‘activar sensor’ para iniciar las mediciones.",
                "sensor_activo": False,
            }), 400
        valor = hw.medir_distancia()
        if valor is None:
            return jsonify({"ok": False, "mensaje": "No se obtuvo una medición válida."}), 400
        return jsonify({"ok": True, "mensaje": f"Distancia medida: {valor:.1f} cm.", "distancia_cm": valor, "sensor_activo": True})

    return jsonify({"ok": False, "mensaje": "No reconozco ese comando. Probá: ‘encender LED uno’, ‘servo a noventa grados’ o ‘activar sensor’."}), 400


# ==========================================
# EJECUCION
# ==========================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        ssl_context=(
            "certs/172.16.4.102.pem",
            "certs/172.16.4.102-key.pem",
        ),
    )

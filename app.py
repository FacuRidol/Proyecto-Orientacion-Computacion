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
    """Normaliza tildes, puntuación y espacios para interpretar comandos."""
    texto = texto.lower().strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(
        caracter
        for caracter in texto
        if unicodedata.category(caracter) != "Mn"
    )
    texto = re.sub(r"[^\w\s]", " ", texto, flags=re.UNICODE)
    return re.sub(r"\s+", " ", texto).strip()


# ==========================================
# NUMEROS EN ESPANOL
# ==========================================

UNIDADES = {
    # Números de LED expresados con palabras.
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
}

NUMEROS_HASTA_29 = {
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
    "veintiuno": 21,
    "veintiun": 21,
    "veintiuna": 21,
    "veintidos": 22,
    "veintitres": 23,
    "veinticuatro": 24,
    "veinticinco": 25,
    "veintiseis": 26,
    "veintisiete": 27,
    "veintiocho": 28,
    "veintinueve": 29,
}

DECENAS = {
    "treinta": 30,
    "cuarenta": 40,
    "cincuenta": 50,
    "sesenta": 60,
    "setenta": 70,
    "ochenta": 80,
    "noventa": 90,
}


def _parsear_menor_de_cien(palabras):
    """Interpreta un número español de 0 a 99 sin buscar números parciales."""
    if not palabras:
        return None

    frase = " ".join(palabras)
    if frase in NUMEROS_HASTA_29:
        return NUMEROS_HASTA_29[frase]

    if len(palabras) == 1 and palabras[0] in DECENAS:
        return DECENAS[palabras[0]]

    # Forma estándar: cuarenta y cinco. También acepta "cuarenta cinco"
    # por si el reconocedor omite la conjunción.
    if len(palabras) in (2, 3) and palabras[0] in DECENAS:
        resto = palabras[1:]
        if len(resto) == 2 and resto[0] == "y":
            resto = resto[1:]
        if len(resto) == 1:
            unidad = NUMEROS_HASTA_29.get(resto[0])
            if unidad is not None and 1 <= unidad <= 9:
                return DECENAS[palabras[0]] + unidad

    # Variantes poco formales como "veinte y cinco".
    if len(palabras) == 3 and palabras[0] == "veinte" and palabras[1] == "y":
        unidad = NUMEROS_HASTA_29.get(palabras[2])
        if unidad is not None and 1 <= unidad <= 9:
            return 20 + unidad

    return None


def extraer_numero(texto):
    """Interpreta un ángulo completo (0–180), en cifras o palabras.

    El texto debe contener solo el ángulo; la palabra final 'grados' se
    valida por separado antes de llamar a esta función.
    """
    texto = normalizar(texto)
    if re.fullmatch(r"\d{1,3}", texto):
        return int(texto)

    palabras = texto.split()
    if not palabras:
        return None

    # 100 se puede expresar como "cien" o "ciento". Para 101–180,
    # se interpreta el resto completo: "ciento veinte" -> 120 y
    # "ciento treinta y cinco" -> 135. No se devuelve 100 prematuramente.
    if palabras[0] in ("cien", "ciento"):
        resto = palabras[1:]
        if resto and resto[0] == "y":
            resto = resto[1:]
        if not resto:
            return 100
        valor_resto = _parsear_menor_de_cien(resto)
        if valor_resto is None:
            return None
        return 100 + valor_resto

    return _parsear_menor_de_cien(palabras)


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

    # Medida de seguridad: todos los comandos de voz deben comenzar por
    # la palabra independiente "comando". Solo se procesa lo que viene después.
    if not re.match(r"^comando\b", texto):
        return jsonify({
            "ok": False,
            "mensaje": "Para ejecutar una orden, empezá diciendo ‘comando’. Ejemplo: ‘comando LED uno encender’.",
        }), 400
    texto = re.sub(r"^comando\b\s*", "", texto, count=1).strip()
    if not texto:
        return jsonify({"ok": False, "mensaje": "Después de ‘comando’, indicá qué dispositivo querés controlar."}), 400

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

    # Servomotor: ahora la palabra de comando es "giro" y la orden debe
    # terminar exactamente en "grados" para confirmar el valor completo.
    if re.search(r"\bgiro\b", texto):
        coincidencia_giro = re.fullmatch(r"giro(?:\s+a)?\s+(.+?)\s+grados", texto)
        if not coincidencia_giro:
            return jsonify({
                "ok": False,
                "mensaje": "Para cambiar el ángulo, decí ‘comando giro a 45 grados’. La palabra ‘grados’ debe ir al final.",
            }), 400

        angulo = extraer_numero(coincidencia_giro.group(1))
        if angulo is None or not 0 <= angulo <= 180:
            return jsonify({
                "ok": False,
                "mensaje": "No pude interpretar el ángulo. Usá un número de 0 a 180 y terminá con ‘grados’; por ejemplo: ‘comando giro a ciento treinta y cinco grados’.",
            }), 400
        try:
            hw.mover_servo(angulo)
            return jsonify({"ok": True, "mensaje": f"Giro: posición solicitada de {angulo}°.", "angulo": angulo})
        except Exception:
            app.logger.exception("Error al mover el servo mediante voz")
            return jsonify({"ok": False, "mensaje": "No se pudo mover el servomotor."}), 500

    # Lectura puntual de distancia; para una lectura en vivo primero se activa.
    if re.search(r"\b(distancia|cerca|lejos|medir|medime)\b", texto):
        if not hw.sensor_esta_activo():
            return jsonify({
                "ok": False,
                "mensaje": "El sensor está desactivado. Decí ‘comando activar sensor’ para iniciar las mediciones.",
                "sensor_activo": False,
            }), 400
        valor = hw.medir_distancia()
        if valor is None:
            return jsonify({"ok": False, "mensaje": "No se obtuvo una medición válida."}), 400
        return jsonify({"ok": True, "mensaje": f"Distancia medida: {valor:.1f} cm.", "distancia_cm": valor, "sensor_activo": True})

    return jsonify({"ok": False, "mensaje": "No reconozco esa orden. Empezá con ‘comando’. Ejemplos: ‘comando LED uno encender’, ‘comando giro a 45 grados’ y ‘comando activar sensor’."}), 400


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

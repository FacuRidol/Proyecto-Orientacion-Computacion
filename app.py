# app.py

import re
import unicodedata

from flask import Flask, jsonify, render_template, request

import dispositivos as hw


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
    # Primero, intentar obtener un número escrito con cifras.
    coincidencia = re.search(r"\b(\d{1,3})\b", texto)

    if coincidencia:
        return int(coincidencia.group(1))

    # Luego, probar números escritos con palabras.
    palabras = texto.split()

    for longitud in (3, 2, 1):
        for inicio in range(len(palabras) - longitud + 1):
            frase = " ".join(
                palabras[inicio:inicio + longitud]
            )

            if frase in UNIDADES:
                valor = UNIDADES[frase]

                # Ejemplo: cuarenta y cinco = 45.
                if (
                    valor >= 30
                    and valor < 100
                    and inicio + longitud + 1 < len(palabras)
                    and palabras[inicio + longitud] == "y"
                ):
                    siguiente = palabras[inicio + longitud + 1]

                    if siguiente in UNIDADES:
                        unidad = UNIDADES[siguiente]

                        if 1 <= unidad <= 9:
                            valor += unidad

                return valor

    return None


# ==========================================
# PAGINA PRINCIPAL
# ==========================================

@app.route("/")
def inicio():
    return render_template("index.html")


# ==========================================
# CONSULTAR ESTADO
# ==========================================

@app.route("/api/estado")
def estado():
    return jsonify(hw.obtener_estado())


# ==========================================
# CONTROL MANUAL DE LED
# ==========================================

@app.route("/api/led/<int:numero>", methods=["POST"])
def controlar_led(numero):
    datos = request.get_json(silent=True) or {}
    accion = datos.get("accion")

    if accion not in ("encender", "apagar"):
        return jsonify({
            "ok": False,
            "mensaje": "Acción no válida."
        }), 400

    try:
        encendido = accion == "encender"

        hw.controlar_led(numero, encendido)

        return jsonify({
            "ok": True,
            "mensaje": f"LED {numero}: {accion}.",
            "encendido": encendido
        })

    except ValueError as error:
        return jsonify({
            "ok": False,
            "mensaje": str(error)
        }), 400


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
            "mensaje": "El ángulo debe ser un número entero."
        }), 400

    if not 0 <= angulo <= 180:
        return jsonify({
            "ok": False,
            "mensaje": "El ángulo debe estar entre 0 y 180."
        }), 400

    try:
        hw.mover_servo(angulo)

        return jsonify({
            "ok": True,
            "mensaje": f"Posición solicitada: {angulo}°.",
            "angulo": angulo
        })

    except Exception:
        app.logger.exception("Error al mover el servo")

        return jsonify({
            "ok": False,
            "mensaje": "No se pudo controlar el servo."
        }), 500


# ==========================================
# CONSULTA DE DISTANCIA
# ==========================================

@app.route("/api/distancia")
def distancia():
    try:
        valor = hw.medir_distancia()

        return jsonify({
            "ok": valor is not None,
            "distancia_cm": valor
        })

    except Exception:
        app.logger.exception("Error al medir la distancia")

        return jsonify({
            "ok": False,
            "distancia_cm": None
        }), 500


# ==========================================
# COMANDOS DE VOZ
# ==========================================

@app.route("/api/comando", methods=["POST"])
def comando():
    datos = request.get_json(silent=True) or {}
    texto = normalizar(str(datos.get("comando", "")))

    if not texto or len(texto) > 200:
        return jsonify({
            "ok": False,
            "mensaje": "El comando está vacío o es demasiado largo."
        }), 400

    # --------------------------------------
    # LED
    # --------------------------------------

    coincidencia = re.search(
        r"\bled\s+(\d+|[a-z]+)\b",
        texto
    )

    if coincidencia:
        numero_texto = coincidencia.group(1)

        if numero_texto.isdigit():
            numero = int(numero_texto)
        else:
            numero = UNIDADES.get(numero_texto)

        if numero is None:
            return jsonify({
                "ok": False,
                "mensaje": "No pude identificar el número del LED."
            }), 400

        if re.search(r"\b(encender|prender|activar)\b", texto):
            accion = "encender"

        elif re.search(r"\b(apagar|desactivar)\b", texto):
            accion = "apagar"

        else:
            return jsonify({
                "ok": False,
                "mensaje": "Indicá si querés encender o apagar el LED."
            }), 400

        try:
            hw.controlar_led(numero, accion == "encender")

            return jsonify({
                "ok": True,
                "mensaje": f"LED {numero}: {accion}."
            })

        except ValueError as error:
            return jsonify({
                "ok": False,
                "mensaje": str(error)
            }), 400

    # --------------------------------------
    # SERVO
    # --------------------------------------

    if "servo" in texto:
        angulo = extraer_numero(texto)

        if angulo is None or not 0 <= angulo <= 180:
            return jsonify({
                "ok": False,
                "mensaje": "Indicá un ángulo entre 0 y 180 grados."
            }), 400

        try:
            hw.mover_servo(angulo)

            return jsonify({
                "ok": True,
                "mensaje": f"Servo: posición solicitada de {angulo}°."
            })

        except Exception:
            app.logger.exception("Error al mover el servo")

            return jsonify({
                "ok": False,
                "mensaje": "No se pudo mover el servo."
            }), 500

    # --------------------------------------
    # SENSOR ULTRASONICO
    # --------------------------------------

    if any(
        palabra in texto
        for palabra in ("distancia", "lejos", "cerca")
    ):
        valor = hw.medir_distancia()

        if valor is None:
            return jsonify({
                "ok": False,
                "mensaje": "No se obtuvo una medición válida."
            })

        return jsonify({
            "ok": True,
            "mensaje": f"Distancia medida: {valor} cm.",
            "distancia_cm": valor
        })

    return jsonify({
        "ok": False,
        "mensaje": "No reconozco ese comando."
    }), 400


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
            "certs/172.16.4.102-key.pem"
        )
    )
# app.py

import re
import unicodedata

from flask import Flask, jsonify, render_template, request

import dispositivos as hw
from reconocimiento_voz import servicio_voz
from comandos_ayuda import AYUDA_COMANDOS


app = Flask(__name__)


# ==========================================
# NORMALIZACION DE TEXTO
# ==========================================

def normalizar(texto):
    """Normaliza tildes, signos de puntuación y espacios."""
    texto = str(texto).lower().strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(
        caracter
        for caracter in texto
        if unicodedata.category(caracter) != "Mn"
    )
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


# ==========================================
# NUMEROS EN ESPANOL
# ==========================================

UNIDADES = {
    "cero": 0,
    "uno": 1, "una": 1, "un": 1,
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
}

NUMEROS_HASTA_29 = {
    **UNIDADES,
    "diez": 10, "once": 11, "doce": 12, "trece": 13,
    "catorce": 14, "quince": 15, "dieciseis": 16,
    "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "veintiun": 21, "veintiuno": 21,
    "veintiuna": 21, "veintidos": 22, "veintitres": 23,
    "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26,
    "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
}

DECENAS = {
    "treinta": 30, "cuarenta": 40, "cincuenta": 50,
    "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90,
}


def _parsear_menor_de_cien(palabras):
    """Interpreta un número español completo de 0 a 99."""
    if not palabras:
        return None

    frase = " ".join(palabras)
    if frase in NUMEROS_HASTA_29:
        return NUMEROS_HASTA_29[frase]

    if len(palabras) == 1 and palabras[0] in DECENAS:
        return DECENAS[palabras[0]]

    # Forma normal: "cuarenta y cinco". También admite que Vosk omita "y".
    if len(palabras) in (2, 3) and palabras[0] in DECENAS:
        resto = palabras[1:]
        if len(resto) == 2 and resto[0] == "y":
            resto = resto[1:]
        if len(resto) == 1:
            unidad = NUMEROS_HASTA_29.get(resto[0])
            if unidad is not None and 1 <= unidad <= 9:
                return DECENAS[palabras[0]] + unidad

    # Admite "veinte y cinco" como variante oral.
    if len(palabras) == 3 and palabras[0] == "veinte" and palabras[1] == "y":
        unidad = NUMEROS_HASTA_29.get(palabras[2])
        if unidad is not None and 1 <= unidad <= 9:
            return 20 + unidad

    return None


def extraer_numero(texto):
    """Interpreta un ángulo entero completo entre 0 y 180."""
    texto = normalizar(texto)
    if re.fullmatch(r"\d{1,3}", texto):
        return int(texto)

    palabras = texto.split()
    if not palabras:
        return None

    # Para 101–180 se suma 100 al número que sigue a "ciento".
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
    # El catálogo de comandos (comandos_ayuda.py) se dibuja en el menú de ayuda.
    return render_template("index.html", ayuda=AYUDA_COMANDOS)


@app.route("/api/estado")
def estado():
    """Estado central compartido por todas las pestañas y navegadores."""
    respuesta = jsonify(hw.obtener_estado())
    respuesta.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    respuesta.headers["Pragma"] = "no-cache"
    return respuesta


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


@app.route("/api/led/<int:numero>/alternar", methods=["POST"])
def alternar_led(numero):
    """Invierte el estado del LED leyendo el GPIO desde el servidor."""
    try:
        encendido = hw.alternar_led(numero)
        return jsonify({
            "ok": True,
            "led": numero,
            "encendido": encendido,
            "mensaje": f"LED {numero}: {'encendido' if encendido else 'apagado'}.",
        })
    except ValueError as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 400
    except Exception:
        app.logger.exception("Error al alternar el LED %s", numero)
        return jsonify({"ok": False, "mensaje": "No se pudo cambiar el estado del LED."}), 500


@app.route("/api/leds/todos", methods=["POST"])
def controlar_todos_los_leds():
    """Enciende o apaga todos los LED con una sola petición."""
    datos = request.get_json(silent=True) or {}
    accion = datos.get("accion")
    if accion not in ("encender", "apagar"):
        return jsonify({"ok": False, "mensaje": "Acción no válida."}), 400

    try:
        encender = accion == "encender"
        leds = hw.controlar_todos_leds(encender)
        return jsonify({
            "ok": True,
            "mensaje": "Todos los LED encendidos." if encender else "Todos los LED apagados.",
            "leds": leds,
        })
    except Exception:
        app.logger.exception("Error al controlar todos los LED")
        return jsonify({"ok": False, "mensaje": "No se pudieron controlar los LED."}), 500


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
# COMANDOS DE VOZ GENERALES
# ==========================================
# Cada intérprete recibe el texto ya normalizado y sin la palabra «comando».
# Si reconoce la orden, devuelve la respuesta de Flask; si no, devuelve None
# y la evalúa el siguiente. Para sumar un comando nuevo:
#   1. Escribir una función como las de abajo.
#   2. Agregarla a INTERPRETES_GENERALES.
#   3. Describirla en comandos_ayuda.py para que aparezca en el menú de ayuda.
#
# Algunas órdenes (ayuda, tema) no tocan el hardware: el servidor solo las
# clasifica y la página ejecuta la acción (abrir el menú, cambiar el tema).

VERBOS_ENCENDER = (
    r"encender|encende|enciende|encendeme|enciendeme|prender|prende|prendeme"
    r"|activar|activa|poner|pone|conectar|conecta"
)
VERBOS_APAGAR = r"apagar|apaga|apagame|desactivar|desactiva|desconectar|desconecta"

# El reconocedor puede transcribir «leds» de varias formas, por eso se aceptan variantes.
PALABRAS_LED = r"leds?|lets?|les|luz|luces|lamparas?|focos?"

# Categoría de la ayuda -> palabras que la nombran y mensaje que se muestra.
# «servo» se admite además de «giro», que es la palabra que el reconocedor entiende mejor.
CATEGORIAS_DE_AYUDA = (
    ("leds", rf"\b(?:{PALABRAS_LED})\b", "Mostrando los comandos de los LED."),
    ("servo", r"\b(?:servos?|servomotor|giro|giros|motor)\b", "Mostrando los comandos del servo."),
    (
        "sensor",
        r"\b(?:sensor|sensores|distancia|ultrasonico|ultrasonica|medicion|mediciones)\b",
        "Mostrando los comandos del sensor.",
    ),
    ("generales", r"\b(?:general|generales)\b", "Mostrando los comandos generales."),
)


def _unir_numeros(numeros):
    """[1] -> '1'; [1, 4] -> '1 y 4'; [1, 2, 4] -> '1, 2 y 4'."""
    textos = [str(numero) for numero in numeros]
    if len(textos) <= 1:
        return "".join(textos)
    return ", ".join(textos[:-1]) + " y " + textos[-1]


def describir_estado():
    """Devuelve (resumen legible, estado completo) de todos los dispositivos."""
    estado = hw.obtener_estado()
    leds = sorted(estado["leds"].items())
    encendidos = [numero for numero, activo in leds if activo]
    apagados = [numero for numero, activo in leds if not activo]

    if not apagados:
        texto_leds = "Todos los LED están encendidos"
    elif not encendidos:
        texto_leds = "Todos los LED están apagados"
    else:
        texto_leds = (
            f"LED encendidos: {_unir_numeros(encendidos)}; "
            f"apagados: {_unir_numeros(apagados)}"
        )

    sensor = "activado" if estado["sensor_activo"] else "desactivado"
    return f"{texto_leds}. Servo en {estado['servo']}°. Sensor {sensor}.", estado


def _interpretar_ayuda(texto):
    """«ayuda», «ayuda leds», «ayuda giro», «ayuda sensor», «cerrar ayuda»..."""
    if not re.search(r"\bayud(?:a|as|ame|ar)\b", texto):
        return None

    if re.search(r"\b(?:cerrar|cierra|ocultar|oculta|esconder|esconde|quitar|quita|salir)\b", texto):
        return jsonify({"ok": True, "mensaje": "Ayuda cerrada.", "ayuda": "cerrar"})

    for categoria, patron, mensaje in CATEGORIAS_DE_AYUDA:
        if re.search(patron, texto):
            return jsonify({"ok": True, "mensaje": mensaje, "ayuda": categoria})

    return jsonify({
        "ok": True,
        "mensaje": "Ayuda abierta. Elegí una categoría o decí, por ejemplo, ‘comando ayuda leds’.",
        "ayuda": "menu",
    })


def _interpretar_tema(texto):
    """«cambiar tema», «tema oscuro», «tema claro», «modo oscuro»..."""
    pide_tema = re.search(r"\btema\b", texto)
    pide_modo = re.search(r"\bmodo\s+(?:oscuro|claro|noche|dia|nocturno)\b", texto)
    if not (pide_tema or pide_modo):
        return None

    # Si se nombran los dos («de claro a oscuro»), manda el último: es el destino.
    nombrados = re.findall(
        r"\b(oscuro|oscura|noche|nocturno|negro|claro|clara|dia|diurno|blanco)\b",
        texto,
    )
    if not nombrados:
        # El servidor no conoce el tema actual (es una preferencia de cada
        # navegador), así que la página decide a cuál pasar.
        return jsonify({"ok": True, "mensaje": "Cambiando el tema de la página.", "tema": "alternar"})

    oscuros = ("oscuro", "oscura", "noche", "nocturno", "negro")
    tema = "oscuro" if nombrados[-1] in oscuros else "claro"
    return jsonify({"ok": True, "mensaje": f"Activando el tema {tema}.", "tema": tema})


def _interpretar_estado(texto):
    """«estado» o «resumen»: informa cómo están todos los dispositivos."""
    if not re.search(r"\b(?:estado|resumen)\b", texto):
        return None

    resumen, estado = describir_estado()
    return jsonify({"ok": True, "mensaje": resumen, "estado": estado})


def _interpretar_apagar_todo(texto):
    """«apagar todo»: apaga los LED y desactiva el sensor (el servo no se mueve)."""
    patron = rf"(?:{VERBOS_APAGAR})\s+(?:el\s+)?(?:todo|todos los dispositivos)(?:\s+por favor)?"
    if not re.fullmatch(patron, texto):
        return None

    leds = hw.controlar_todos_leds(False)
    hw.configurar_sensor(False)
    return jsonify({
        "ok": True,
        "mensaje": "Todo apagado: LED apagados y sensor desactivado.",
        "leds": leds,
        "sensor_activo": False,
    })


def _interpretar_todos_los_leds(texto):
    """«encender todas las leds» / «apagar todas las leds»."""
    dice_todos = re.search(r"\b(?:todas|todos)\b", texto)
    nombra_leds = re.search(rf"\b(?:{PALABRAS_LED})\b", texto)
    if not (dice_todos and nombra_leds):
        return None

    if re.search(rf"\b(?:{VERBOS_APAGAR})\b", texto):
        encender = False
    elif re.search(rf"\b(?:{VERBOS_ENCENDER})\b", texto):
        encender = True
    else:
        return jsonify({
            "ok": False,
            "mensaje": "Indicá si querés encender o apagar todos los LED.",
        }), 400

    leds = hw.controlar_todos_leds(encender)
    return jsonify({
        "ok": True,
        "mensaje": "Todos los LED encendidos." if encender else "Todos los LED apagados.",
        "leds": leds,
    })


def _interpretar_centrar_servo(texto):
    """«giro al centro» / «centrar servo»: lleva el servo a 90°."""
    pide_centro = re.search(r"\bcentr(?:ar|a|o|ado)\b", texto)
    nombra_servo = re.search(r"\b(?:giro|servos?|servomotor|motor)\b", texto)
    if not (pide_centro and nombra_servo):
        return None

    try:
        hw.mover_servo(90)
    except Exception:
        app.logger.exception("Error al centrar el servomotor mediante voz")
        return jsonify({"ok": False, "mensaje": "No se pudo mover el servomotor."}), 500

    return jsonify({"ok": True, "mensaje": "Giro: servo centrado en 90°.", "angulo": 90})


# El orden importa: «ayuda sensor» tiene que evaluarse antes que las órdenes
# del sensor, y «estado» antes que cualquier otra que nombre un dispositivo.
INTERPRETES_GENERALES = (
    _interpretar_ayuda,
    _interpretar_tema,
    _interpretar_estado,
    _interpretar_apagar_todo,
    _interpretar_todos_los_leds,
    _interpretar_centrar_servo,
)


# ==========================================
# COMANDOS DE VOZ
# ==========================================

@app.route("/api/comando", methods=["POST"])
def comando():
    datos = request.get_json(silent=True) or {}
    texto = normalizar(str(datos.get("comando", "")))

    if not texto or len(texto) > 200:
        return jsonify({"ok": False, "mensaje": "El comando está vacío o es demasiado largo."}), 400

    # Todos los comandos por voz deben comenzar con la palabra independiente "comando".
    if not re.match(r"^comando\b", texto):
        return jsonify({
            "ok": False,
            "mensaje": "Empezá la orden con la palabra ‘comando’. Ejemplo: ‘comando LED uno encender’.",
        }), 400
    texto = re.sub(r"^comando\b\s*", "", texto, count=1).strip()
    if not texto:
        return jsonify({"ok": False, "mensaje": "Después de ‘comando’, indicá el dispositivo y la acción."}), 400

    # COMANDOS GENERALES: ayuda, tema, estado, apagar todo, todas las LED y centrar el servo.
    # Van primero porque algunos nombran dispositivos («ayuda sensor») y no deben
    # confundirse con las órdenes individuales de más abajo.
    for interprete in INTERPRETES_GENERALES:
        respuesta = interprete(texto)
        if respuesta is not None:
            return respuesta

    # SENSOR: activar o detener las mediciones continuas.
    menciona_sensor = re.search(
        r"\b(sensor|medicion|mediciones|ultrasonico|ultrasonica|distancia)\b",
        texto,
    )
    if menciona_sensor:
        if re.search(
            r"\b(desactivar|desactiva|apagar|apaga|detener|detene|parar|para|finalizar|finaliza|desconectar|desconecta|frenar|frena)\b",
            texto,
        ):
            hw.configurar_sensor(False)
            return jsonify({"ok": True, "mensaje": "Medición continua desactivada.", "sensor_activo": False})
        if re.search(
            r"\b(activar|activa|encender|encende|enciende|prender|prende|iniciar|inicia|comenzar|comienza|arrancar|arranca)\b",
            texto,
        ):
            hw.configurar_sensor(True)
            return jsonify({"ok": True, "mensaje": "Medición continua activada.", "sensor_activo": True})

    # LED INDIVIDUAL: acepta "LED uno encender", "LED 1 apagar" y variantes.
    coincidencia = re.search(
        r"\bled\s+(?:(?:numero|nro)\s+)*(\d{1,2}|primero|primer|primera|segundo|segunda|tercero|tercera|cuarto|cuarta|uno|una|un|dos|tres|cuatro|cinco|seis|siete|ocho|nueve)\b",
        texto,
    )
    if coincidencia:
        equivalencias_led = {
            "primero": 1, "primer": 1, "primera": 1, "uno": 1, "una": 1, "un": 1,
            "segundo": 2, "segunda": 2, "dos": 2,
            "tercero": 3, "tercera": 3, "tres": 3,
            "cuarto": 4, "cuarta": 4, "cuatro": 4,
            "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
        }
        numero_texto = coincidencia.group(1)
        numero = int(numero_texto) if numero_texto.isdigit() else equivalencias_led.get(numero_texto)
        if numero is None:
            return jsonify({"ok": False, "mensaje": "No pude identificar el número del LED."}), 400

        if re.search(
            r"\b(encender|encende|enciende|encendeme|enciendeme|prender|prende|prendeme|activar|activa|poner|pone|conectar|conecta)\b",
            texto,
        ):
            accion = "encender"
        elif re.search(
            r"\b(apagar|apaga|apagame|desactivar|desactiva|desconectar|desconecta)\b",
            texto,
        ):
            accion = "apagar"
        else:
            return jsonify({"ok": False, "mensaje": "Indicá si querés encender o apagar el LED."}), 400

        try:
            hw.controlar_led(numero, accion == "encender")
            return jsonify({
                "ok": True,
                "mensaje": f"LED {numero}: {accion}.",
                "led": numero,
                "encendido": accion == "encender",
            })
        except ValueError as error:
            return jsonify({"ok": False, "mensaje": str(error)}), 400

    # SERVOMOTOR: se reemplaza "servo" por "giro". "grados" es obligatorio
    # y debe ser la palabra final, lo que delimita el número compuesto completo.
    if re.search(r"\bgiro\b", texto):
        coincidencia_giro = re.fullmatch(r"giro(?:\s+a)?\s+(.+?)\s+grados", texto)
        if not coincidencia_giro:
            return jsonify({
                "ok": False,
                "mensaje": "Decí ‘comando giro a 45 grados’. La palabra ‘grados’ debe ir al final.",
            }), 400

        angulo = extraer_numero(coincidencia_giro.group(1))
        if angulo is None or not 0 <= angulo <= 180:
            return jsonify({
                "ok": False,
                "mensaje": "Indicá un ángulo entero entre 0 y 180 y terminá con ‘grados’.",
            }), 400
        try:
            hw.mover_servo(angulo)
            return jsonify({
                "ok": True,
                "mensaje": f"Giro: posición solicitada de {angulo}°.",
                "angulo": angulo,
            })
        except Exception:
            app.logger.exception("Error al mover el servomotor mediante voz")
            return jsonify({"ok": False, "mensaje": "No se pudo mover el servomotor."}), 500

    # CONSULTA PUNTUAL DE DISTANCIA (el sensor tiene que estar activo).
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
        return jsonify({
            "ok": True,
            "mensaje": f"Distancia medida: {valor:.1f} cm.",
            "distancia_cm": valor,
            "sensor_activo": True,
        })

    return jsonify({
        "ok": False,
        "mensaje": "No reconozco esa orden. Ejemplos: ‘comando LED uno encender’, ‘comando giro a 45 grados’ y ‘comando activar sensor’. "
        "Decí ‘comando ayuda’ para ver todos los comandos.",
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
            "certs/172.16.4.102-key.pem",
        ),
    )

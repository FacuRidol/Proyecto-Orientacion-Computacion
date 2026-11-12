# app.py

import atexit
import os
import re
import unicodedata
from pathlib import Path

from flask import Flask, jsonify, render_template, request

import dispositivos as hw
from reconocimiento_voz import servicio_voz
from comandos_ayuda import AYUDA_COMANDOS
from automatizaciones import ErrorDeRegla, MotorReglas, ejecutar_en_hardware
from nombres_leds import ErrorDeNombre, NombresLeds
from registro import registro
from sensor_monitor import MonitorSensor


# ==========================================
# CONFIGURACIÓN: PALABRAS PARA COMENZAR UNA ORDEN
# ==========================================
# Toda orden hablada tiene que empezar con alguna de estas palabras. Con la lista
# de ejemplo, estas dos órdenes hacen exactamente lo mismo:
#
#     «comando encender led uno»        «robot encender led uno»
#
# Para cambiarlas alcanza con editar la lista (no hace falta tocar nada más: los
# mensajes y la ayuda de la página se ajustan solos):
#   - Se pueden agregar, quitar o reemplazar todas las que quieras.
#   - No importan las mayúsculas ni las tildes.
#   - Pueden ser frases de varias palabras, por ejemplo "hola robot".
#   - La primera es la principal: es la que se usa en los ejemplos de la página.
#   - Elegí palabras que el reconocedor entienda bien y que no se usen dentro de
#     las órdenes (led, giro, sensor, ayuda, reglas...). Para comprobarlo mirá el
#     cuadro «Texto que interpreta Vosk» o el registro de comandos.
PALABRAS_DE_INICIO = [
    "comando",
    "robot",
    "Viernes",
]


app = Flask(__name__)


# ==========================================
# SERVICIOS EN SEGUNDO PLANO
# ==========================================
# - monitor: mide la distancia mientras el sensor está activo, guarda el historial
#   (gráfico) y alimenta a las reglas, haya o no una página abierta.
# - motor_reglas: reglas «si la distancia es menor a X cm, hacer Y» (automatizaciones.py).
# - registro: historial de comandos de voz y de reglas disparadas (registro.py).

# Las reglas se guardan en datos/automatizaciones.json (la carpeta se crea sola).
# La variable de entorno ASISTENTE_DATOS permite usar otra carpeta.
CARPETA_DATOS = Path(os.environ.get("ASISTENTE_DATOS") or Path(__file__).resolve().parent / "datos")

motor_reglas = MotorReglas(
    ejecutar=ejecutar_en_hardware,
    leds_validos=tuple(hw.LED_PINS),
    ruta=CARPETA_DATOS / "automatizaciones.json",
    registrar=registro.agregar,
    # nombres_leds se crea más abajo (necesita las palabras de los comandos);
    # esta función se consulta recién cuando hay que describir una regla.
    nombre_led=lambda numero: nombres_leds.obtener(numero),
)

monitor = MonitorSensor(
    medir=hw.medir_distancia,
    sensor_activo=hw.sensor_esta_activo,
    al_medir=motor_reglas.procesar_medicion,
    al_desactivar=motor_reglas.reiniciar_estados,
)

# Una medición del monitor sigue siendo válida durante este tiempo (en segundos).
MUESTRA_VIGENTE_S = 1.5
VENTANA_GRAFICO_S = 60

_servicios_iniciados = False


def iniciar_servicios():
    """Arranca el monitor del sensor. Se llama una vez al iniciar la aplicación."""
    global _servicios_iniciados
    if _servicios_iniciados:
        return
    _servicios_iniciados = True
    monitor.iniciar()
    # Se registra después de dispositivos.py, así que al cerrar se ejecuta antes
    # que la liberación de los GPIO: el hilo termina antes de soltar los pines.
    atexit.register(monitor.detener)


def leer_distancia():
    """Distancia más reciente en cm (None si no hay lectura válida).

    Con el monitor activo se usa su última medición, para no medir dos veces ni
    pelear por el sensor. Si el monitor no está corriendo (por ejemplo, al
    probar el código fuera de la aplicación) se mide directamente, como antes.
    """
    if monitor.corriendo:
        muestra = monitor.ultima_muestra()
        if muestra is not None and monitor.ahora() - muestra[0] <= MUESTRA_VIGENTE_S:
            return muestra[1]
        return None
    return hw.medir_distancia()


def sin_cache(respuesta):
    """Evita que el navegador reutilice datos que cambian cada segundo."""
    respuesta.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    respuesta.headers["Pragma"] = "no-cache"
    return respuesta


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
# PALABRAS DE INICIO (procesa la lista configurada al comienzo del archivo)
# ==========================================

def preparar_palabras_de_inicio(palabras):
    """Valida PALABRAS_DE_INICIO y arma lo necesario para reconocerlas.

    Devuelve (palabras para mostrar, claves normalizadas, expresión regular que
    reconoce el comienzo de una orden). Lanza ValueError si no queda ninguna.
    """
    if isinstance(palabras, str):
        # Un texto suelto cuenta como una sola palabra. Sin esto, Python lo
        # recorrería letra por letra y cualquier orden que empiece con «c» pasaría.
        palabras = [palabras]

    mostradas, claves = [], []
    for palabra in palabras:
        mostrada = " ".join(str(palabra).split())
        clave = normalizar(mostrada)
        if clave and clave not in claves:  # se ignoran las vacías y las repetidas
            mostradas.append(mostrada)
            claves.append(clave)

    if not claves:
        raise ValueError(
            'PALABRAS_DE_INICIO está vacía: agregá al menos una palabra, por ejemplo "comando".'
        )

    # Las más largas primero, para que «hola robot» gane sobre «hola» si están las dos.
    alternativas = "|".join(
        r"\s+".join(re.escape(parte) for parte in clave.split())
        for clave in sorted(claves, key=len, reverse=True)
    )
    return mostradas, claves, re.compile(rf"^(?:{alternativas})\b\s*")


def unir_con_o(elementos):
    """['a'] -> 'a'; ['a', 'b'] -> 'a o b'; ['a', 'b', 'c'] -> 'a, b o c'."""
    if len(elementos) <= 1:
        return "".join(elementos)
    return ", ".join(elementos[:-1]) + " o " + elementos[-1]


PALABRAS_MOSTRADAS, CLAVES_DE_INICIO, PATRON_DE_INICIO = preparar_palabras_de_inicio(PALABRAS_DE_INICIO)
PALABRA_PRINCIPAL = PALABRAS_MOSTRADAS[0]
_MOSTRAR_POR_CLAVE = dict(zip(CLAVES_DE_INICIO, PALABRAS_MOSTRADAS))

# Las mismas palabras, escritas para la página «comando» o «robot» y para los
# mensajes de error ‘comando’ o ‘robot’.
PALABRAS_DE_INICIO_TEXTO = unir_con_o([f"«{palabra}»" for palabra in PALABRAS_MOSTRADAS])
PALABRAS_DE_INICIO_MENSAJE = unir_con_o([f"‘{palabra}’" for palabra in PALABRAS_MOSTRADAS])


def separar_palabra_de_inicio(texto):
    """Separa la palabra de inicio de una orden ya normalizada.

    Devuelve (palabra usada, resto de la orden), o (None, texto) si la orden no
    empieza con ninguna de las palabras configuradas.
    """
    coincidencia = PATRON_DE_INICIO.match(texto)
    if coincidencia is None:
        return None, texto
    clave = " ".join(coincidencia.group(0).split())
    return _MOSTRAR_POR_CLAVE[clave], texto[coincidencia.end():].strip()


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


CENTENAS = {
    "cien": 100, "ciento": 100,
    "doscientos": 200, "doscientas": 200,
    "trescientos": 300, "trescientas": 300,
    "cuatrocientos": 400, "cuatrocientas": 400,
}


def extraer_distancia_cm(texto):
    """Interpreta un número entero de 0 a 499, con cifras o con palabras.

    Reutiliza _parsear_menor_de_cien: «ciento veinte» = 100 + 20,
    «doscientos cincuenta y cinco» = 200 + 55.
    """
    texto = normalizar(texto)
    if re.fullmatch(r"\d{1,3}", texto):
        return int(texto)

    palabras = texto.split()
    if not palabras:
        return None

    if palabras[0] in CENTENAS:
        resto = palabras[1:]
        if resto and resto[0] == "y":
            resto = resto[1:]
        if not resto:
            return CENTENAS[palabras[0]]
        valor_resto = _parsear_menor_de_cien(resto)
        return None if valor_resto is None else CENTENAS[palabras[0]] + valor_resto

    return _parsear_menor_de_cien(palabras)


# ==========================================
# PAGINA PRINCIPAL Y ESTADO
# ==========================================

@app.route("/")
def inicio():
    # El catálogo de comandos (comandos_ayuda.py) se dibuja en el menú de ayuda, y las
    # palabras de inicio configuradas arriba se usan en los textos de la página.
    return render_template(
        "index.html",
        ayuda=AYUDA_COMANDOS,
        palabra_inicio=PALABRA_PRINCIPAL,
        palabras_inicio_texto=PALABRAS_DE_INICIO_TEXTO,
    )


@app.route("/api/estado")
def estado():
    """Estado central compartido por todas las pestañas y navegadores."""
    datos = hw.obtener_estado()
    datos["nombres"] = nombres_leds.todos()  # nombre de cada LED (ver «NOMBRES DE LOS LED»)
    respuesta = jsonify(datos)
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
            "mensaje": f"{nombre_led(numero)}: {accion}.",
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
            "mensaje": f"{nombre_led(numero)}: {'encendido' if encendido else 'apagado'}.",
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
        valor = leer_distancia()
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


@app.route("/api/distancia/historial")
def historial_distancia():
    """Mediciones recientes para el gráfico. ?desde=<momento> devuelve solo las nuevas."""
    try:
        desde = float(request.args.get("desde", 0))
    except ValueError:
        desde = 0.0

    return sin_cache(jsonify({
        "ok": True,
        "disponible": monitor.corriendo,
        "sensor_activo": hw.sensor_esta_activo(),
        "ahora": round(monitor.ahora(), 3),
        "ventana_s": VENTANA_GRAFICO_S,
        "muestras": monitor.muestras_desde(desde),
    }))


# ==========================================
# AUTOMATIZACIONES (REGLAS DEL SENSOR)
# ==========================================

@app.route("/api/reglas", methods=["GET"])
def listar_reglas():
    return sin_cache(jsonify({
        "ok": True,
        **motor_reglas.estado(),
        "nombres_leds": nombres_leds.todos(),  # para el menú «Encender LED...» del formulario
        "sensor_activo": hw.sensor_esta_activo(),
        "ahora": round(monitor.ahora(), 3),  # para mostrar «último disparo: hace 12 s»
    }))


@app.route("/api/reglas", methods=["POST"])
def crear_regla():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify({"ok": False, "mensaje": "Datos de la regla no válidos."}), 400

    try:
        regla = motor_reglas.crear(
            datos.get("condicion"), datos.get("umbral_cm"), datos.get("accion")
        )
    except ErrorDeRegla as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 400

    return jsonify({
        "ok": True,
        "mensaje": f"Regla {regla['id']} creada.",
        "regla": regla,
    }), 201


@app.route("/api/reglas", methods=["DELETE"])
def borrar_todas_las_reglas():
    cantidad = motor_reglas.eliminar_todas()
    return jsonify({"ok": True, "mensaje": f"Se borraron {cantidad} reglas.", "borradas": cantidad})


@app.route("/api/reglas/<int:id_regla>", methods=["PATCH"])
def modificar_regla(id_regla):
    datos = request.get_json(silent=True) or {}
    if not isinstance(datos.get("activa"), bool):
        return jsonify({"ok": False, "mensaje": "Indicá si la regla debe estar activa."}), 400

    regla = motor_reglas.activar(id_regla, datos["activa"])
    if regla is None:
        return jsonify({"ok": False, "mensaje": f"No existe la regla {id_regla}."}), 404
    return jsonify({"ok": True, "regla": regla})


@app.route("/api/reglas/<int:id_regla>", methods=["DELETE"])
def borrar_regla(id_regla):
    if not motor_reglas.eliminar(id_regla):
        return jsonify({"ok": False, "mensaje": f"No existe la regla {id_regla}."}), 404
    return jsonify({"ok": True, "mensaje": f"Regla {id_regla} borrada."})


@app.route("/api/reglas/pausa", methods=["POST"])
def pausar_reglas():
    datos = request.get_json(silent=True) or {}
    if not isinstance(datos.get("pausadas"), bool):
        return jsonify({"ok": False, "mensaje": "Indicá si las reglas deben pausarse."}), 400

    pausadas = motor_reglas.pausar(datos["pausadas"])
    return jsonify({
        "ok": True,
        "pausadas": pausadas,
        "mensaje": "Reglas en pausa." if pausadas else "Reglas reanudadas.",
    })


# ==========================================
# REGISTRO DE COMANDOS
# ==========================================

@app.route("/api/registro", methods=["GET"])
def consultar_registro():
    """Eventos nuevos desde ?desde=<id>. base_id indica qué ids siguen vigentes."""
    try:
        desde = int(request.args.get("desde", 0))
    except ValueError:
        desde = 0

    ultimo_id, base_id = registro.posicion()
    return sin_cache(jsonify({
        "ok": True,
        "entradas": registro.desde(desde),
        "ultimo_id": ultimo_id,
        "base_id": base_id,
    }))


@app.route("/api/registro", methods=["DELETE"])
def limpiar_registro():
    cantidad = registro.limpiar()
    return jsonify({"ok": True, "mensaje": "Registro limpio.", "borradas": cantidad})


@app.after_request
def registrar_orden_de_voz(respuesta):
    """Anota cada orden recibida en /api/comando con su resultado.

    Se hace acá, y no dentro de comando(), para cubrir todos sus puntos de
    salida sin tocarlos. Las frases que no empiezan con una palabra de inicio se anotan
    como «ignorado»: sirven para ver qué está escuchando Vosk.
    """
    if request.method != "POST" or request.path != "/api/comando":
        return respuesta

    try:
        datos = request.get_json(silent=True) or {}
        texto = str(datos.get("comando", "")).strip()
        if texto:
            cuerpo = respuesta.get_json(silent=True) or {}
            if respuesta.status_code < 400:
                estado = "ok"
            elif separar_palabra_de_inicio(normalizar(texto))[0] is None:
                estado = "ignorado"
            else:
                estado = "error"
            registro.agregar("voz", texto, cuerpo.get("mensaje", ""), estado)
    except Exception:
        app.logger.exception("No se pudo anotar la orden en el registro")

    return respuesta


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
# Cada intérprete recibe el texto ya normalizado y sin la palabra de inicio.
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

# «LED uno», «LED 2», «LED número tres», «LED primero»... (el grupo 1 es el número).
# Lo usan la orden individual de un LED y las reglas habladas.
PATRON_LED_NUMERADO = (
    r"\bled\s+(?:(?:numero|nro)\s+)*"
    r"(\d{1,2}|primero|primer|primera|segundo|segunda|tercero|tercera|cuarto|cuarta"
    r"|uno|una|un|dos|tres|cuatro|cinco|seis|siete|ocho|nueve)\b"
)
EQUIVALENCIAS_LED = {
    "primero": 1, "primer": 1, "primera": 1, "uno": 1, "una": 1, "un": 1,
    "segundo": 2, "segunda": 2, "dos": 2,
    "tercero": 3, "tercera": 3, "tres": 3,
    "cuarto": 4, "cuarta": 4, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
}

# ==========================================
# NOMBRES DE LOS LED
# ==========================================
# Desde la página se le puede poner nombre a cada LED («LED 1» -> «cocina»). Ese
# nombre es también el que se dice por voz: «comando encender cocina». Un LED sin
# nombre propio sigue respondiendo a «LED uno». La lógica de guardado y búsqueda
# está en nombres_leds.py; acá solo se deciden qué nombres chocarían con comandos.

# Palabras que ya significan otra cosa en alguna orden. Un LED llamado «estado»
# haría que «encender estado» fuera tomado por la orden «estado».
PALABRAS_RESERVADAS_LED = frozenset(
    set(VERBOS_ENCENDER.split("|"))
    | set(VERBOS_APAGAR.split("|"))
    | {
        # Formas con las que se habla una regla («que se encienda...»).
        "encienda", "prenda", "active", "ponga", "apague", "desactive", "desconecte",
        "todo", "todos", "todas", "dispositivos",
        "ayuda", "ayudas", "ayudame", "ayudar",
        "tema", "estado", "resumen",
        "regla", "reglas", "automatizacion", "automatizaciones", "automatizar", "alarma",
        "si", "cuando",
        "sensor", "sensores", "medicion", "mediciones", "ultrasonico", "ultrasonica", "distancia",
        "centimetro", "centimetros", "cm", "metro", "metros", "grados",
        "giro", "giros", "servo", "servos", "servomotor",
    }
    # «comando», «robot»... (las palabras de inicio configuradas arriba).
    | {palabra for clave in CLAVES_DE_INICIO for palabra in clave.split()}
)

# Números dichos con palabras: un nombre hecho solo de números («tres») se
# confundiría con los ángulos y distancias de otras órdenes («giro a tres grados»).
PALABRAS_DE_NUMERO = frozenset(
    set(NUMEROS_HASTA_29) | set(DECENAS) | set(CENTENAS) | {"y", "medio", "mil"}
)

# Frases que, aunque no tengan palabras reservadas sueltas, ya significan otra cosa.
PATRONES_RESERVADOS_LED = (
    (PATRON_LED_NUMERADO, "Ese nombre se confundiría con la orden «LED uno». Elegí otro nombre."),
    (r"\bmodo\s+(?:oscuro|claro|noche|dia|nocturno)\b", "Ese nombre se confundiría con el cambio de tema. Elegí otro nombre."),
)


def revisar_nombre_de_led(numero, palabras):
    """Devuelve el motivo por el que un nombre no sirve, o None si está bien.

    «palabras» es el nombre ya normalizado y sin artículos (lo arma NombresLeds).
    """
    for palabra in palabras:
        if palabra in PALABRAS_RESERVADAS_LED:
            return f"La palabra «{palabra}» se usa en otros comandos de voz. Elegí otro nombre."

    if all(palabra.isdigit() or palabra in PALABRAS_DE_NUMERO for palabra in palabras):
        return (
            "El nombre no puede ser solo un número, porque se confundiría con los "
            "ángulos y distancias de otros comandos. Agregá una palabra, por ejemplo «luz 2»."
        )

    frase = " ".join(palabras)
    for patron, motivo in PATRONES_RESERVADOS_LED:
        if re.search(patron, frase):
            return motivo
    return None


nombres_leds = NombresLeds(
    leds_validos=tuple(hw.LED_PINS),
    normalizar=normalizar,
    ruta=CARPETA_DATOS / "nombres_leds.json",
    revisar=revisar_nombre_de_led,
)


def nombre_led(numero):
    """Nombre actual de un LED: el que eligió la persona o «LED 1», «LED 2»..."""
    return nombres_leds.obtener(numero)


def _numero_de_led(texto_del_numero):
    """«3», «tres», «tercero»... -> 3 (None si no se entiende)."""
    if texto_del_numero.isdigit():
        return int(texto_del_numero)
    return EQUIVALENCIAS_LED.get(texto_del_numero)


def resolver_leds_en_texto(texto):
    """Averigua a qué LED se refiere una orden ya normalizada y sin palabra de inicio.

    Un LED se nombra por su nombre («cocina») o, mientras no se lo haya
    renombrado, por su número («LED uno»). Devuelve (numeros, error):
      - ([3], None)      la orden nombra un solo LED
      - ([], None)       la orden no nombra ningún LED
      - ([], «mensaje»)  nombra a más de uno, o usó el número de un LED que ya
                         tiene nombre (el mensaje dice cómo llamarlo ahora)
    """
    objetivos = []
    renombrados = []

    for coincidencia in re.finditer(PATRON_LED_NUMERADO, texto):
        numero = _numero_de_led(coincidencia.group(1))
        if numero is None:
            continue
        if numero in nombres_leds.numeros and nombres_leds.personalizado(numero):
            renombrados.append(numero)
        else:
            objetivos.append(numero)

    # Los nombres se buscan en lo que queda sin las expresiones «LED uno».
    resto = re.sub(PATRON_LED_NUMERADO, " ", texto)
    objetivos.extend(nombres_leds.buscar(resto))
    objetivos = list(dict.fromkeys(objetivos))

    if len(objetivos) > 1:
        nombres = unir_con_o([f"«{nombre_led(numero)}»" for numero in objetivos])
        return [], (
            f"Nombraste más de un LED ({nombres}). Decí una orden por cada LED, "
            "o ‘encender todas las leds’."
        )
    if objetivos:
        return objetivos, None
    if renombrados:
        numero = renombrados[0]
        nombre = nombre_led(numero)
        return [], (
            f"El LED {numero} ahora se llama «{nombre}». "
            f"Decí, por ejemplo, ‘{PALABRA_PRINCIPAL} encender {nombre}’."
        )
    return [], None


def ejemplo_de_orden_de_led():
    """Una orden de ejemplo con el primer LED, usando su nombre actual."""
    primero = min(nombres_leds.numeros)
    if nombres_leds.personalizado(primero):
        return f"encender {nombre_led(primero)}"
    return "encender led uno"


@app.route("/api/led/<int:numero>/nombre", methods=["PUT"])
def renombrar_led(numero):
    """Cambia el nombre de un LED (también el que se dice por voz).

    Cuerpo: {"nombre": "cocina"}. Un nombre vacío devuelve el LED a su nombre
    original. Responde con los nombres de todos los LED.
    """
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict) or "nombre" not in datos:
        return jsonify({"ok": False, "mensaje": "Falta el nombre del LED."}), 400

    try:
        nombre = nombres_leds.establecer(numero, datos["nombre"])
    except ErrorDeNombre as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 400
    except Exception:
        app.logger.exception("Error al renombrar el LED %s", numero)
        return jsonify({"ok": False, "mensaje": "No se pudo cambiar el nombre del LED."}), 500

    if nombres_leds.personalizado(numero):
        mensaje = (
            f"El LED {numero} ahora se llama «{nombre}». "
            f"Por voz: ‘{PALABRA_PRINCIPAL} encender {nombre}’."
        )
    else:
        mensaje = f"El LED {numero} volvió a su nombre original."

    return jsonify({
        "ok": True,
        "mensaje": mensaje,
        "led": numero,
        "nombre": nombre,
        "personalizado": nombres_leds.personalizado(numero),
        "nombres": nombres_leds.todos(),
    })


# Categoría de la ayuda -> palabras que la nombran y mensaje que se muestra.
# «servo» se admite además de «giro», que es la palabra que el reconocedor entiende mejor.
CATEGORIAS_DE_AYUDA = (
    ("leds", rf"\b(?:{PALABRAS_LED})\b", "Mostrando los comandos de los LED."),
    ("servo", r"\b(?:servos?|servomotor|giro|giros|motor)\b", "Mostrando los comandos del servo."),
    (
        "sensor",
        r"\b(?:sensor|sensores|distancia|ultrasonico|ultrasonica|medicion|mediciones"
        r"|reglas?|automatizacion|automatizaciones|alarma)\b",
        "Mostrando los comandos del sensor y sus reglas.",
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
    elif any(nombres_leds.personalizado(numero) for numero in estado["leds"]):
        # Con nombres propios se dicen los nombres: «Encendidos: cocina y LED 3».
        texto_leds = (
            f"Encendidos: {_unir_numeros([nombre_led(n) for n in encendidos])}; "
            f"apagados: {_unir_numeros([nombre_led(n) for n in apagados])}"
        )
    else:
        texto_leds = (
            f"LED encendidos: {_unir_numeros(encendidos)}; "
            f"apagados: {_unir_numeros(apagados)}"
        )

    sensor = "activado" if estado["sensor_activo"] else "desactivado"
    resumen = f"{texto_leds}. Servo en {estado['servo']}°. Sensor {sensor}."

    reglas = motor_reglas.listar()
    if reglas:
        if motor_reglas.pausadas:
            resumen += " Reglas en pausa."
        else:
            activas = sum(1 for regla in reglas if regla["activa"])
            resumen += f" Reglas activas: {activas} de {len(reglas)}."
    return resumen, estado


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
        "mensaje": f"Ayuda abierta. Elegí una categoría o decí, por ejemplo, ‘{PALABRA_PRINCIPAL} ayuda leds’.",
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


def _parsear_accion_de_regla(texto):
    """Interpreta la parte «qué hacer» de una regla hablada. Devuelve la acción o None.

    Entiende lo mismo que las órdenes directas: «encender led uno» (o con el
    nombre del LED, «encender cocina»), «apagar todas las leds», «giro a 90
    grados» y «giro al centro». Lanza ErrorDeRegla si el LED es ambiguo.
    """
    # Se descartan muletillas del comienzo: «entonces encender led uno».
    texto = re.sub(r"^(?:(?:entonces|luego|despues|que|y|hace|hacer|haz)\b\s*)+", "", texto).strip()
    if not texto:
        return None

    # En una regla es común hablar en subjuntivo: «que se encienda el led uno».
    enciende = re.search(rf"\b(?:{VERBOS_ENCENDER}|encienda|prenda|active|ponga)\b", texto)
    apaga = re.search(rf"\b(?:{VERBOS_APAGAR}|apague|desactive|desconecte)\b", texto)

    if re.search(r"\b(?:todas|todos)\b", texto) and re.search(rf"\b(?:{PALABRAS_LED})\b", texto):
        if enciende or apaga:
            return {"tipo": "leds", "encender": bool(enciende)}
        return None

    # Un LED se nombra por su nombre («cocina») o por su número («led uno»).
    numeros, error = resolver_leds_en_texto(texto)
    if error:
        raise ErrorDeRegla(error)
    if numeros and (enciende or apaga):
        return {"tipo": "led", "led": numeros[0], "encender": bool(enciende)}

    nombra_servo = re.search(r"\b(?:giro|servos?|servomotor|motor)\b", texto)
    if nombra_servo and re.search(r"\bcentr(?:ar|a|o|ado)\b", texto):
        return {"tipo": "servo", "angulo": 90}

    giro = re.fullmatch(
        r"(?:(?:mover|mueve|girar|gira)\s+(?:el\s+)?)?(?:giro|servo|servomotor)(?:\s+(?:a|en|hasta))?\s+(.+?)\s+grados",
        texto,
    )
    if giro:
        angulo = extraer_numero(giro.group(1))
        if angulo is not None and 0 <= angulo <= 180:
            return {"tipo": "servo", "angulo": angulo}

    return None


def _ayuda_regla_hablada():
    return (
        f"Decí, por ejemplo, ‘{PALABRA_PRINCIPAL} si hay algo a menos de veinte "
        f"centímetros {ejemplo_de_orden_de_led()}’."
    )


def _interpretar_crear_regla(texto):
    """«si hay algo a menos de veinte centímetros encender led uno» y variantes.

    Admite empezar con «si», «cuando», «regla» o «alarma». Con «alarma» la
    condición es «menos de» por defecto («alarma a treinta centímetros...»).
    """
    inicio = re.match(r"^(si|cuando|regla|alarma|automatizar|automatizacion)\b\s*(.*)$", texto)
    if not inicio:
        return None
    palabra_inicial, resto = inicio.groups()

    unidad = re.search(r"\b(centimetros?|cm|metros?)\b", resto)
    if not unidad:
        return jsonify({
            "ok": False,
            "mensaje": "No entendí la distancia: tiene que terminar en ‘centímetros’. " + _ayuda_regla_hablada(),
        }), 400

    antes = resto[: unidad.start()].split()
    despues = resto[unidad.end():].strip()
    en_metros = unidad.group(1).startswith("metro")

    # El número es el tramo más largo, justo antes de la unidad, que sea un número
    # («ciento veinte» gana sobre «veinte»).
    distancia = None
    posicion_numero = len(antes)
    if en_metros and antes and antes[-1] == "medio":
        distancia, posicion_numero = 50, len(antes) - 1
    else:
        for largo in range(min(5, len(antes)), 0, -1):
            valor = extraer_distancia_cm(" ".join(antes[-largo:]))
            if valor is not None:
                distancia = valor * 100 if en_metros else valor
                posicion_numero = len(antes) - largo
                break
    if distancia is None:
        return jsonify({
            "ok": False,
            "mensaje": "No entendí cuántos centímetros. " + _ayuda_regla_hablada(),
        }), 400

    comparador = " ".join(antes[:posicion_numero])
    if re.search(r"\b(?:menos|menor|debajo|cerca|cercano|abajo)\b", comparador):
        condicion = "menor"
    elif re.search(r"\b(?:mayor|arriba|encima|lejos|lejano)\b|\bmas\s+(?:de|que)\b", comparador):
        condicion = "mayor"
    elif palabra_inicial == "alarma":
        condicion = "menor"
    else:
        return jsonify({
            "ok": False,
            "mensaje": "Indicá si es ‘menos de’ o ‘más de’ esa distancia. " + _ayuda_regla_hablada(),
        }), 400

    try:
        accion = _parsear_accion_de_regla(despues)
    except ErrorDeRegla as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 400
    if accion is None:
        return jsonify({
            "ok": False,
            "mensaje": (
                f"No entendí qué hacer cuando se cumpla. Podés decir ‘{ejemplo_de_orden_de_led()}’, "
                "‘apagar todas las leds’ o ‘giro a 90 grados’."
            ),
        }), 400

    try:
        regla = motor_reglas.crear(condicion, distancia, accion)
    except ErrorDeRegla as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 400

    mensaje = f"Regla {regla['id']} creada: {regla['descripcion']}."
    if not hw.sensor_esta_activo():
        mensaje += " Activá el sensor para que funcione."
    return jsonify({"ok": True, "mensaje": mensaje, "regla": regla})


def _interpretar_gestion_reglas(texto):
    """«reglas», «borrar regla dos», «borrar todas las reglas», «pausar reglas»..."""
    if not re.search(r"\b(?:reglas?|automatizaciones?)\b", texto):
        return None
    # Una frase con distancia («regla menos de 20 centímetros...») es una regla nueva.
    if re.search(r"\b(?:centimetros?|cm|metros?)\b", texto):
        return None

    plural = re.search(r"\b(?:reglas|automatizaciones)\b", texto)
    verbo_borrar = re.search(
        r"\b(?:borrar|borra|eliminar|elimina|quitar|quita|sacar|saca|vaciar|vacia|limpiar|limpia)\b", texto
    )
    verbo_pausa = re.search(r"\b(?:pausar|pausa|detener|detene|frenar|frena)\b", texto)
    verbo_reanudar = re.search(r"\b(?:reanudar|reanuda|continuar|continua|reactivar|reactiva)\b", texto)
    verbo_apagar = re.search(rf"\b(?:{VERBOS_APAGAR})\b", texto)
    verbo_encender = re.search(rf"\b(?:{VERBOS_ENCENDER})\b", texto)

    # Número de una regla puntual: «regla 2», «regla número dos».
    numero = None
    puntual = re.search(r"\bregla\s+(?:(?:numero|nro)\s+)*(\d{1,2}|[a-z]+)\b", texto)
    if puntual:
        numero = extraer_numero(puntual.group(1))

    if verbo_borrar:
        if plural and not puntual:
            cantidad = motor_reglas.eliminar_todas()
            mensaje = f"Se borraron {cantidad} reglas." if cantidad else "No había reglas para borrar."
            return jsonify({"ok": True, "mensaje": mensaje, "reglas_cambiaron": True})
        if numero is None:
            return jsonify({
                "ok": False,
                "mensaje": f"Decí qué regla borrar, por ejemplo ‘{PALABRA_PRINCIPAL} borrar regla uno’.",
            }), 400
        if not motor_reglas.eliminar(numero):
            return jsonify({"ok": False, "mensaje": f"No existe la regla {numero}."}), 400
        return jsonify({"ok": True, "mensaje": f"Regla {numero} borrada.", "reglas_cambiaron": True})

    if puntual and numero is not None and (verbo_apagar or verbo_encender or verbo_pausa or verbo_reanudar):
        activar = bool(verbo_encender or verbo_reanudar)
        if motor_reglas.activar(numero, activar) is None:
            return jsonify({"ok": False, "mensaje": f"No existe la regla {numero}."}), 400
        estado = "activada" if activar else "desactivada"
        return jsonify({"ok": True, "mensaje": f"Regla {numero} {estado}.", "reglas_cambiaron": True})

    if plural and (verbo_pausa or verbo_apagar):
        motor_reglas.pausar(True)
        return jsonify({"ok": True, "mensaje": "Reglas en pausa.", "reglas_cambiaron": True})

    if plural and (verbo_reanudar or verbo_encender):
        motor_reglas.pausar(False)
        return jsonify({"ok": True, "mensaje": "Reglas reanudadas.", "reglas_cambiaron": True})

    # Sin ninguna otra intención clara («reglas», «mostrar reglas», «listar reglas»).
    return jsonify({"ok": True, "mensaje": motor_reglas.resumen()})


def _interpretar_registro(texto):
    """«limpiar registro» / «borrar registro»: vacía el historial de comandos."""
    if not re.search(r"\bregistro\b", texto):
        return None
    if not re.search(r"\b(?:limpiar|limpia|borrar|borra|vaciar|vacia|eliminar|elimina)\b", texto):
        return None

    registro.limpiar()
    return jsonify({"ok": True, "mensaje": "Registro limpio."})


# El orden importa:
#  - «ayuda sensor» tiene que evaluarse antes que las órdenes del sensor.
#  - Las reglas van antes que las órdenes directas: «si hay algo a menos de 20
#    centímetros apagar todas las leds» no debe apagar las LED en ese momento,
#    sino crear la regla.
#  - «estado» antes que cualquier otra que nombre un dispositivo.
INTERPRETES_GENERALES = (
    _interpretar_ayuda,
    _interpretar_gestion_reglas,
    _interpretar_crear_regla,
    _interpretar_registro,
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

    # Todas las órdenes por voz deben comenzar con una de las palabras configuradas en
    # PALABRAS_DE_INICIO. «palabra» es la que usó la persona: los mensajes de más abajo
    # la repiten en sus ejemplos.
    palabra, texto = separar_palabra_de_inicio(texto)
    if palabra is None:
        consigna = (
            f"con la palabra ‘{PALABRA_PRINCIPAL}’"
            if len(PALABRAS_MOSTRADAS) == 1
            else f"con {PALABRAS_DE_INICIO_MENSAJE}"
        )
        return jsonify({
            "ok": False,
            "mensaje": f"Empezá la orden {consigna}. Ejemplo: ‘{PALABRA_PRINCIPAL} LED uno encender’.",
        }), 400
    if not texto:
        return jsonify({"ok": False, "mensaje": f"Después de ‘{palabra}’, indicá el dispositivo y la acción."}), 400

    # COMANDOS GENERALES: ayuda, reglas, registro, tema, estado, apagar todo, todas las LED y centrar el servo.
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

    # LED INDIVIDUAL: por su nombre («encender cocina», «cocina apagar») o, mientras
    # no se lo haya renombrado, por su número («LED uno encender», «LED 1 apagar»).
    numeros, error = resolver_leds_en_texto(texto)
    if error:
        return jsonify({"ok": False, "mensaje": error}), 400
    if numeros:
        numero = numeros[0]
        nombre = nombre_led(numero)

        if re.search(rf"\b(?:{VERBOS_ENCENDER})\b", texto):
            accion = "encender"
        elif re.search(rf"\b(?:{VERBOS_APAGAR})\b", texto):
            accion = "apagar"
        else:
            return jsonify({"ok": False, "mensaje": f"Indicá si querés encender o apagar «{nombre}»."}), 400

        try:
            hw.controlar_led(numero, accion == "encender")
            return jsonify({
                "ok": True,
                "mensaje": f"{nombre}: {accion}.",
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
                "mensaje": f"Decí ‘{palabra} giro a 45 grados’. La palabra ‘grados’ debe ir al final.",
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
                "mensaje": f"El sensor está desactivado. Decí ‘{palabra} activar sensor’ para iniciar las mediciones.",
                "sensor_activo": False,
            }), 400
        valor = leer_distancia()
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
        "mensaje": (
            f"No reconozco esa orden. Ejemplos: ‘{palabra} LED uno encender’, ‘{palabra} giro a 45 grados’ y ‘{palabra} activar sensor’. "
            f"Decí ‘{palabra} ayuda’ para ver todos los comandos."
        ),
    }), 400


# ==========================================
# EJECUCION
# ==========================================

if __name__ == "__main__":
    iniciar_servicios()
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        ssl_context=(
            "certs/172.16.4.102.pem",
            "certs/172.16.4.102-key.pem",
        ),
    )

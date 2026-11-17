# app.py

# ┌─────────────────────────────────────────────────────────────────────────┐
# │ app.py: EL PROGRAMA PRINCIPAL (servidor web Flask)                      │
# │                                                                         │
# │ QUÉ HACE                                                                │
# │  1. Sirve la página (templates/index.html + static/css y static/js).    │
# │  2. Expone la API que usa la página (rutas /api/...).                   │
# │  3. Interpreta los comandos de voz («comando encender cocina») ya       │
# │     convertidos a texto y los convierte en acciones.                    │
# │                                                                         │
# │ A QUÉ ARCHIVOS LLAMA (los importa más abajo)                            │
# │  - dispositivos.py ........ mueve LED, servo y sensor (import como hw). │
# │  - reconocimiento_voz.py .. Vosk: convierte el audio del micrófono en   │
# │                             texto (servicio_voz).                       │
# │  - comandos_ayuda.py ...... textos del menú «Ayuda de comandos».        │
# │  - automatizaciones.py .... reglas «si la distancia es menor a X...»    │
# │  - nombres_leds.py ........ nombres personalizados de los LED.          │
# │  - asistente.py ........... modo, palabras de activación y sesión.       │
# │  - registro.py ............ historial de comandos y reglas disparadas.  │
# │  - sensor_monitor.py ...... hilo que mide la distancia en segundo plano.│
# │  - templates/index.html ... la página (se entrega con render_template). │
# │                                                                         │
# │ QUIÉN LO USA                                                            │
# │  - El navegador: static/js/voz.js, automatizaciones.js, grafico.js,     │
# │    registro.js (llaman a las rutas /api/ definidas acá).                │
# │  - Se inicia con «python app.py» (ver el final de este archivo).        │
# └─────────────────────────────────────────────────────────────────────────┘
# atexit: registrar funciones que se ejecutan al cerrar el programa.
import atexit
# os: leer variables de entorno (ASISTENTE_DATOS, HTTPS, etc.).
import os
# re: expresiones regulares, la herramienta principal para entender las frases habladas.
import re
# unicodedata: quitar tildes de los textos (ver normalizar).
import unicodedata
# Path: manejo de rutas de archivos y carpetas.
from pathlib import Path

# Flask (librería externa): Flask crea la aplicación web, jsonify arma respuestas JSON, render_template entrega templates/index.html, request lee lo que envía el navegador y «g» guarda datos de UNA sola petición (se usa para el registro de órdenes).
from flask import Flask, g, jsonify, render_template, request

# Archivo dispositivos.py (hardware). Se usa como «hw»: hw.controlar_led(...), hw.mover_servo(...), etc.
import dispositivos as hw
# Archivo reconocimiento_voz.py: objeto «servicio_voz» (Vosk).
from reconocimiento_voz import servicio_voz
# Archivo comandos_ayuda.py: textos de la ayuda de comandos.
from comandos_ayuda import AYUDA_COMANDOS
# Archivo automatizaciones.py: motor de reglas, su error propio y la función que ejecuta acciones.
from automatizaciones import ErrorDeRegla, MotorReglas, ejecutar_en_hardware
# Archivo nombres_leds.py: guarda y busca los nombres de los LED.
from nombres_leds import ErrorDeNombre, NombresLeds
# Archivo asistente.py: modo de funcionamiento, palabras de activación editables y sesión del asistente (despierto/dormido).
from asistente import Asistente, ErrorDeConfiguracion
# Archivo registro.py: objeto «registro» (historial de eventos).
from registro import registro
# Archivo sensor_monitor.py: hilo que mide la distancia en segundo plano.
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
# Lista editable de las palabras con las que debe empezar toda orden hablada. Todo lo demás (ayuda, mensajes) se adapta solo a lo que pongas acá.
PALABRAS_DE_INICIO = [
    "comando",
    "robot",
]


# Crea la aplicación web. Los decoradores @app.route(...) de más abajo registran cada dirección (URL) que atiende.
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
# Carpeta donde se guardan los datos permanentes (reglas y nombres de LED): la de la variable ASISTENTE_DATOS o, si no existe, «datos/» junto a este archivo.
CARPETA_DATOS = Path(os.environ.get("ASISTENTE_DATOS") or Path(__file__).resolve().parent / "datos")

# Crea el motor de reglas (automatizaciones.py). Le entrega: la función que ejecuta acciones en el hardware, qué LED existen (de dispositivos.py), dónde guardar las reglas, cómo anotar eventos (registro.py) y cómo obtener el nombre de un LED.
motor_reglas = MotorReglas(
    ejecutar=ejecutar_en_hardware,
    leds_validos=tuple(hw.LED_PINS),
    ruta=CARPETA_DATOS / "automatizaciones.json",
    registrar=registro.agregar,
    # nombres_leds se crea más abajo (necesita las palabras de los comandos);
    # esta función se consulta recién cuando hay que describir una regla.
    nombre_led=lambda numero: nombres_leds.obtener(numero),
)

# Crea el hilo de medición (sensor_monitor.py). Cada medición se la pasa al motor de reglas (al_medir) y, si el sensor se apaga, las reglas se reinician (al_desactivar). Todavía NO arranca: eso ocurre en iniciar_servicios().
monitor = MonitorSensor(
    medir=hw.medir_distancia,
    sensor_activo=hw.sensor_esta_activo,
    al_medir=motor_reglas.procesar_medicion,
    al_desactivar=motor_reglas.reiniciar_estados,
)

# Una medición del monitor sigue siendo válida durante este tiempo (en segundos).
# Una medición del monitor se considera «reciente» durante 1,5 s. Más abajo, la ventana del gráfico dura 60 s.
MUESTRA_VIGENTE_S = 1.5
VENTANA_GRAFICO_S = 60

# Bandera para arrancar los servicios una sola vez.
_servicios_iniciados = False


# Arranca el hilo de medición. Se llama una vez al final del archivo, antes de levantar el servidor.
def iniciar_servicios():
    """Arranca el monitor del sensor. Se llama una vez al iniciar la aplicación."""
    global _servicios_iniciados
    if _servicios_iniciados:
        return
    _servicios_iniciados = True
    # Pone en marcha el hilo de sensor_monitor.py.
    monitor.iniciar()
    # Se registra después de dispositivos.py, así que al cerrar se ejecuta antes
    # que la liberación de los GPIO: el hilo termina antes de soltar los pines.
    # Hace que al cerrar el programa se detenga el hilo antes de liberar los pines (dispositivos.cerrar_hardware).
    atexit.register(monitor.detener)


# Devuelve la distancia más reciente en cm. Si el monitor está corriendo reutiliza su última medición (así no se mide dos veces); si no, mide directamente con hw.medir_distancia().
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


# Agrega cabeceras HTTP que impiden que el navegador guarde la respuesta: los datos del estado cambian cada segundo.
def sin_cache(respuesta):
    """Evita que el navegador reutilice datos que cambian cada segundo."""
    respuesta.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    respuesta.headers["Pragma"] = "no-cache"
    return respuesta


# ==========================================
# NORMALIZACION DE TEXTO
# ==========================================

# Limpia un texto para poder compararlo: minúsculas, sin tildes, sin signos y con espacios simples. Se usa en TODAS las órdenes de voz y también la usa nombres_leds.py.
def normalizar(texto):
    """Normaliza tildes, signos de puntuación y espacios."""
    texto = str(texto).lower().strip()
    # Separa cada letra de su tilde («é» -> «e» + tilde) y descarta las tildes (categoría Mn).
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(
        caracter
        for caracter in texto
        if unicodedata.category(caracter) != "Mn"
    )
    # Cambia por espacios todo lo que no sea letra, número o espacio (comas, signos, etc.) y deja espacios simples.
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


# ==========================================
# PALABRAS DE INICIO (procesa la lista configurada al comienzo del archivo)
# ==========================================

# Procesa la lista PALABRAS_DE_INICIO: la valida y prepara la expresión regular que reconoce el comienzo de una orden.
def preparar_palabras_de_inicio(palabras):
    """Valida PALABRAS_DE_INICIO y arma lo necesario para reconocerlas.

    Devuelve (palabras para mostrar, claves normalizadas, expresión regular que
    reconoce el comienzo de una orden, expresión regular que encuentra la palabra
    en cualquier parte de la frase). Lanza ValueError si no queda ninguna.
    """
    if isinstance(palabras, str):
        # Un texto suelto cuenta como una sola palabra. Sin esto, Python lo
        # recorrería letra por letra y cualquier orden que empiece con «c» pasaría.
        palabras = [palabras]

    # Recorre las palabras: «mostradas» conserva cómo se escriben y «claves» su versión normalizada; se ignoran vacías y repetidas.
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
    # Arma una expresión regular con todas las alternativas (las más largas primero: «hola robot» gana sobre «hola»).
    alternativas = "|".join(
        r"\s+".join(re.escape(parte) for parte in clave.split())
        for clave in sorted(claves, key=len, reverse=True)
    )
    # Patrón de COMIENZO: reconoce la palabra solo al principio de la frase (así empieza una orden).
    patron_inicio = re.compile(rf"^(?:{alternativas})\b\s*")
    # Patrón LIBRE: las mismas alternativas, pero sin anclar al principio. Sirve para encontrar la palabra de
    # activación en medio de la frase («robot encender led uno robot activar sensor»): cada una separa una orden.
    patron_libre = re.compile(rf"\b(?:{alternativas})\b")
    return mostradas, claves, patron_inicio, patron_libre


# Arma enumeraciones en español: ["a","b","c"] -> «a, b o c». Se usa en mensajes de error.
def unir_con_o(elementos):
    """['a'] -> 'a'; ['a', 'b'] -> 'a o b'; ['a', 'b', 'c'] -> 'a, b o c'."""
    if len(elementos) <= 1:
        return "".join(elementos)
    return ", ".join(elementos[:-1]) + " o " + elementos[-1]


# Activa una lista de palabras de activación y recalcula todo lo que depende de ella. Se llama al arrancar
# (con las de fábrica y luego con las guardadas) y cada vez que la persona las cambia en la página
# (PUT /api/configuracion). Las funciones del resto del archivo leen estas variables en el momento de usarlas,
# así que el cambio se nota de inmediato, sin reiniciar el programa.
def aplicar_palabras_de_inicio(palabras):
    # «global» permite que esta función reemplace las variables del módulo (si no, crearía copias locales).
    global PALABRAS_MOSTRADAS, CLAVES_DE_INICIO, PATRON_DE_INICIO, PATRON_DE_ACTIVACION
    global PALABRA_PRINCIPAL, _MOSTRAR_POR_CLAVE, PALABRAS_DE_INICIO_TEXTO, PALABRAS_DE_INICIO_MENSAJE

    # Valida la lista y arma las palabras para mostrar, sus versiones normalizadas y los dos patrones.
    mostradas, claves, patron_inicio, patron_libre = preparar_palabras_de_inicio(palabras)

    # Tabla para recuperar cómo se escribe cada palabra de inicio a partir de su versión normalizada.
    _MOSTRAR_POR_CLAVE = dict(zip(claves, mostradas))
    PALABRAS_MOSTRADAS = mostradas
    CLAVES_DE_INICIO = claves
    # La primera palabra de la lista es la principal: la usan los ejemplos de la página y los mensajes («comando encender cocina»).
    PALABRA_PRINCIPAL = mostradas[0]
    # Las palabras escritas como «comando» o «robot» (para la página) y como ‘comando’ o ‘robot’ (para los mensajes de error).
    PALABRAS_DE_INICIO_TEXTO = unir_con_o([f"«{palabra}»" for palabra in mostradas])
    PALABRAS_DE_INICIO_MENSAJE = unir_con_o([f"‘{palabra}’" for palabra in mostradas])
    PATRON_DE_ACTIVACION = patron_libre
    # El patrón de comienzo se asigna al final: es lo primero que consulta separar_palabra_de_inicio().
    PATRON_DE_INICIO = patron_inicio


# Al cargar el archivo se usan las palabras de fábrica. Más abajo, cuando existe el objeto «asistente»
# (que guarda las que eligió la persona), se vuelve a llamar con esas.
aplicar_palabras_de_inicio(PALABRAS_DE_INICIO)


# Separa la palabra de inicio del resto de la orden. Devuelve (palabra usada, resto) o (None, texto) si la frase no empieza con ninguna: en ese caso comando() la ignora.
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

# TABLAS DE NÚMEROS EN ESPAÑOL. Sirven para entender «giro a cuarenta y cinco grados» o «a veinte centímetros», porque Vosk a veces entrega números con palabras. UNIDADES: del 0 al 9.
UNIDADES = {
    "cero": 0,
    "uno": 1, "una": 1, "un": 1,
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
}

# Del 0 al 29 (incluye las formas con y sin tilde, ya normalizadas).
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

# Decenas redondas: 30, 40... 90.
DECENAS = {
    "treinta": 30, "cuarenta": 40, "cincuenta": 50,
    "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90,
}


# Convierte una lista de palabras («cuarenta», «y», «cinco») en un número del 0 al 99. Devuelve None si no es un número válido.
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


# Interpreta un ángulo de 0 a 180, escrito con cifras («90») o con palabras («ciento treinta y cinco»). Lo usan las órdenes del servo.
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


# Centenas, para distancias de las reglas («doscientos cincuenta»).
CENTENAS = {
    "cien": 100, "ciento": 100,
    "doscientos": 200, "doscientas": 200,
    "trescientos": 300, "trescientas": 300,
    "cuatrocientos": 400, "cuatrocientas": 400,
}


# Interpreta una distancia de 0 a 499 (cifras o palabras). Reutiliza _parsear_menor_de_cien. La usan las reglas habladas («a menos de veinte centímetros»).
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

    # Si empieza con una centena («doscientos», «ciento»...), la suma al valor de lo que sigue (menor de 100).
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

# ═══ PÁGINA PRINCIPAL ═══
# Ruta «/»: lo que se abre al entrar al sitio.
@app.route("/")
# Entrega templates/index.html, pasándole la ayuda (comandos_ayuda.py) y las palabras de inicio para que la página las muestre. Los archivos static/css y static/js los sirve Flask solos.
def inicio():
    # El catálogo de comandos (comandos_ayuda.py) se dibuja en el menú de ayuda, y las
    # palabras de inicio configuradas arriba se usan en los textos de la página.
    return render_template(
        "index.html",
        ayuda=AYUDA_COMANDOS,
        palabra_inicio=PALABRA_PRINCIPAL,
        palabras_inicio_texto=PALABRAS_DE_INICIO_TEXTO,
    )


# ═══ ESTADO GENERAL ═══
# GET /api/estado: foto del hardware y de los nombres. static/js/voz.js la consulta cada segundo para sincronizar todas las pestañas.
@app.route("/api/estado")
def estado():
    """Estado central compartido por todas las pestañas y navegadores."""
    # Pide a dispositivos.py el estado de LED, servo y sensor y le suma los nombres de los LED (nombres_leds.py). Se responde sin caché para que el navegador no reutilice datos viejos.
    datos = hw.obtener_estado()
    datos["nombres"] = nombres_leds.todos()
    # Modo, palabras de activación y sesión del asistente (asistente.py): static/js/asistente.js lo usa para
    # mantener el panel «Asistente de voz» sincronizado en todas las pestañas.
    datos["asistente"] = asistente.estado()  # nombre de cada LED (ver «NOMBRES DE LOS LED»)
    respuesta = jsonify(datos)
    respuesta.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    respuesta.headers["Pragma"] = "no-cache"
    return respuesta


# ==========================================
# CONTROL DE LED
# ==========================================

# ═══ LED ═══
# POST /api/led/<n>: enciende o apaga un LED según {"accion": "encender"|"apagar"}.
@app.route("/api/led/<int:numero>", methods=["POST"])
def controlar_led(numero):
    datos = request.get_json(silent=True) or {}
    accion = datos.get("accion")
    if accion not in ("encender", "apagar"):
        return jsonify({"ok": False, "mensaje": "Acción no válida."}), 400

    try:
        encendido = accion == "encender"
        # Llama a dispositivos.controlar_led (mueve el pin). Si el LED no existe lanza ValueError y se responde con error 400.
        hw.controlar_led(numero, encendido)
        return jsonify({
            "ok": True,
            "mensaje": f"{nombre_led(numero)}: {accion}.",
            "encendido": encendido,
        })
    except ValueError as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 400


# POST /api/led/<n>/alternar: invierte el LED. Es la ruta del botón único de cada tarjeta (static/js/voz.js, función alternarLed).
@app.route("/api/led/<int:numero>/alternar", methods=["POST"])
def alternar_led(numero):
    """Invierte el estado del LED leyendo el GPIO desde el servidor."""
    try:
        # Llama a dispositivos.alternar_led, que lee el pin y lo invierte de forma atómica.
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


# POST /api/leds/todos: enciende o apaga los cuatro con una sola petición (botones «Encender todos» / «Apagar todos»).
@app.route("/api/leds/todos", methods=["POST"])
def controlar_todos_los_leds():
    """Enciende o apaga todos los LED con una sola petición."""
    datos = request.get_json(silent=True) or {}
    accion = datos.get("accion")
    if accion not in ("encender", "apagar"):
        return jsonify({"ok": False, "mensaje": "Acción no válida."}), 400

    try:
        encender = accion == "encender"
        # Llama a dispositivos.controlar_todos_leds y devuelve el estado final de todos.
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

# ═══ SERVO ═══
# POST /api/servo: mueve el servo al ángulo {"angulo": 0..180}. Lo llama static/js/voz.js (botón «Aplicar posición»).
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
        # Llama a dispositivos.mover_servo (tarda ~0,5 s en llegar).
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

# ═══ SENSOR ═══
# POST /api/sensor: activa o desactiva la medición continua ({"accion": "activar"|"desactivar"}).
@app.route("/api/sensor", methods=["POST"])
def controlar_sensor():
    datos = request.get_json(silent=True) or {}
    accion = datos.get("accion")
    if accion not in ("activar", "desactivar"):
        return jsonify({"ok": False, "mensaje": "Acción de sensor no válida."}), 400

    activo = accion == "activar"
    # Llama a dispositivos.configurar_sensor. Desde ese momento el hilo de sensor_monitor.py empieza (o deja) de medir.
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


# GET /api/distancia: la distancia actual. Si el sensor está apagado avisa que está desactivado.
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
        # Usa la última medición del monitor (ver leer_distancia más arriba).
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


# GET /api/distancia/historial: mediciones recientes para el gráfico. static/js/grafico.js pide con ?desde=<momento> solo las nuevas. Las entrega sensor_monitor.py (monitor.muestras_desde).
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

# ═══ AUTOMATIZACIONES (REGLAS) ═══
# GET /api/reglas: lista de reglas, límites del formulario, nombres de LED y si el sensor está activo. La consulta static/js/automatizaciones.js.
@app.route("/api/reglas", methods=["GET"])
def listar_reglas():
    return sin_cache(jsonify({
        "ok": True,
        **motor_reglas.estado(),
        "nombres_leds": nombres_leds.todos(),  # para el menú «Encender LED...» del formulario
        "sensor_activo": hw.sensor_esta_activo(),
        "ahora": round(monitor.ahora(), 3),  # para mostrar «último disparo: hace 12 s»
    }))


# POST /api/reglas: crea una regla desde el formulario ({"condicion", "umbral_cm", "accion"}).
@app.route("/api/reglas", methods=["POST"])
def crear_regla():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify({"ok": False, "mensaje": "Datos de la regla no válidos."}), 400

    try:
        # Llama a automatizaciones.MotorReglas.crear, que valida todo. Si algo está mal lanza ErrorDeRegla y se responde 400 con su mensaje.
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


# DELETE /api/reglas: borra todas las reglas.
@app.route("/api/reglas", methods=["DELETE"])
def borrar_todas_las_reglas():
    cantidad = motor_reglas.eliminar_todas()
    return jsonify({"ok": True, "mensaje": f"Se borraron {cantidad} reglas.", "borradas": cantidad})


# PATCH /api/reglas/<id>: activa o desactiva una regla (interruptor de cada regla en la página).
@app.route("/api/reglas/<int:id_regla>", methods=["PATCH"])
def modificar_regla(id_regla):
    datos = request.get_json(silent=True) or {}
    if not isinstance(datos.get("activa"), bool):
        return jsonify({"ok": False, "mensaje": "Indicá si la regla debe estar activa."}), 400

    # Llama a MotorReglas.activar; devuelve None si la regla no existe (-> 404).
    regla = motor_reglas.activar(id_regla, datos["activa"])
    if regla is None:
        return jsonify({"ok": False, "mensaje": f"No existe la regla {id_regla}."}), 404
    return jsonify({"ok": True, "regla": regla})


# DELETE /api/reglas/<id>: borra una regla.
@app.route("/api/reglas/<int:id_regla>", methods=["DELETE"])
def borrar_regla(id_regla):
    # Llama a MotorReglas.eliminar; False significa que no existía.
    if not motor_reglas.eliminar(id_regla):
        return jsonify({"ok": False, "mensaje": f"No existe la regla {id_regla}."}), 404
    return jsonify({"ok": True, "mensaje": f"Regla {id_regla} borrada."})


# POST /api/reglas/pausa: pausa o reanuda todas las reglas.
@app.route("/api/reglas/pausa", methods=["POST"])
def pausar_reglas():
    datos = request.get_json(silent=True) or {}
    if not isinstance(datos.get("pausadas"), bool):
        return jsonify({"ok": False, "mensaje": "Indicá si las reglas deben pausarse."}), 400

    # Llama a MotorReglas.pausar.
    pausadas = motor_reglas.pausar(datos["pausadas"])
    return jsonify({
        "ok": True,
        "pausadas": pausadas,
        "mensaje": "Reglas en pausa." if pausadas else "Reglas reanudadas.",
    })


# ==========================================
# REGISTRO DE COMANDOS
# ==========================================

# ═══ REGISTRO DE COMANDOS ═══
# GET /api/registro: eventos nuevos desde un id. La consulta static/js/registro.js cada segundo.
@app.route("/api/registro", methods=["GET"])
def consultar_registro():
    """Eventos nuevos desde ?desde=<id>. base_id indica qué ids siguen vigentes."""
    try:
        desde = int(request.args.get("desde", 0))
    except ValueError:
        desde = 0

    # Pide a registro.py hasta qué id se llegó y cuáles siguen vigentes; después devuelve solo los eventos nuevos (registro.desde).
    ultimo_id, base_id = registro.posicion()
    return sin_cache(jsonify({
        "ok": True,
        "entradas": registro.desde(desde),
        "ultimo_id": ultimo_id,
        "base_id": base_id,
    }))


# DELETE /api/registro: vacía el historial (botón «Limpiar»).
@app.route("/api/registro", methods=["DELETE"])
def limpiar_registro():
    # Llama a registro.limpiar y devuelve cuántos eventos se borraron.
    cantidad = registro.limpiar()
    return jsonify({"ok": True, "mensaje": "Registro limpio.", "borradas": cantidad})


# Decorador de Flask: esta función se ejecuta DESPUÉS de cada petición, justo antes de enviar la respuesta.
@app.after_request
# Anota en el registro (registro.py) cada orden recibida en POST /api/comando con su resultado: «ok», «error» o «ignorado» (si no empezó con una palabra de inicio). Así se ve en el panel «Registro de comandos» qué escuchó Vosk.
def registrar_orden_de_voz(respuesta):
    """Anota cada orden recibida en /api/comando con su resultado.

    Se hace acá, y no dentro de comando(), para cubrir todos sus puntos de
    salida sin tocarlos. Las frases que no empiezan con una palabra de inicio se anotan
    como «ignorado»: sirven para ver qué está escuchando Vosk.
    """
    if request.method != "POST" or request.path != "/api/comando":
        return respuesta

    try:
        # comando() deja en «g.eventos» la lista (texto, resultado, estado) de lo que ejecutó. Es una lista porque
        # una sola frase puede contener varias órdenes (se anota una por orden). «g» vive solo durante esta petición.
        eventos = g.pop("eventos", None)
        if eventos:
            for texto_evento, mensaje_evento, estado_evento in eventos:
                registro.agregar("voz", texto_evento, mensaje_evento, estado_evento)
            return respuesta

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
            # Llama a registro.agregar con origen «voz».
            registro.agregar("voz", texto, cuerpo.get("mensaje", ""), estado)
    except Exception:
        app.logger.exception("No se pudo anotar la orden en el registro")

    return respuesta


# ==========================================
# RECONOCIMIENTO DE VOZ OFFLINE (VOSK)
# ==========================================

# ═══ RECONOCIMIENTO DE VOZ (Vosk) ═══
# GET /api/voz/estado: ¿están Vosk y el modelo disponibles? La página lo consulta al cargar (static/js/voz.js).
@app.route("/api/voz/estado")
def estado_voz():
    return jsonify(servicio_voz.estado())


# POST /api/voz/iniciar: abre la sesión de escucha (botón «Activar micrófono»). Llama a reconocimiento_voz.servicio_voz.iniciar().
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


# POST /api/voz/audio: recibe un fragmento de audio PCM (16 bits, 16 kHz) que envía static/js/voz.js y devuelve el texto que se entiende (parcial o final).
@app.route("/api/voz/audio", methods=["POST"])
def recibir_audio():
    audio_pcm = request.get_data(cache=False)
    # Rechaza audio vacío, demasiado grande o con un número impar de bytes (no sería PCM de 16 bits).
    if not audio_pcm or len(audio_pcm) > 128_000 or len(audio_pcm) % 2:
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
        app.logger.exception("Error al procesar audio con Vosk")
        return jsonify({"ok": False, "mensaje": "No se pudo procesar el audio."}), 500


# POST /api/voz/detener: cierra la sesión de escucha.
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

# ═══ INTÉRPRETE DE COMANDOS DE VOZ ═══
# Todo lo que sigue convierte una frase en texto (por ejemplo «comando encender cocina») en una acción. La ruta que lo usa es POST /api/comando, más abajo (función comando()).
# Verbos que significan «encender» (expresión regular: «a|b|c» = cualquiera de ellas).
VERBOS_ENCENDER = (
    r"encender|encende|enciende|encendeme|enciendeme|prender|prende|prendeme"
    r"|activar|activa|poner|pone|conectar|conecta"
)
# Verbos que significan «apagar».
VERBOS_APAGAR = r"apagar|apaga|apagame|desactivar|desactiva|desconectar|desconecta"

# El reconocedor puede transcribir «leds» de varias formas, por eso se aceptan variantes.
# Formas de decir «led» (incluye errores típicos de Vosk: «let», «les»). Se usa para entender «todas las leds / luces».
PALABRAS_LED = r"leds?|lets?|les|luz|luces|lamparas?|focos?"

# «LED uno», «LED 2», «LED número tres», «LED primero»... (el grupo 1 es el número).
# Lo usan la orden individual de un LED y las reglas habladas.
# Expresión regular que reconoce «led uno», «led 2», «led número tres», «led primero»... y captura el número. Solo vale para LED sin nombre propio.
PATRON_LED_NUMERADO = (
    r"\bled\s+(?:(?:numero|nro)\s+)*"
    r"(\d{1,2}|primero|primer|primera|segundo|segunda|tercero|tercera|cuarto|cuarta"
    r"|uno|una|un|dos|tres|cuatro|cinco|seis|siete|ocho|nueve)\b"
)
# Traduce las palabras del número de un LED a su valor: «uno» -> 1, «tercero» -> 3, etc.
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
# ═══ NOMBRES DE LOS LED ═══
# Desde la página se le puede poner nombre a cada LED («LED 1» -> «cocina») y ese nombre es también el que se dice por voz: «comando encender cocina». La lógica de guardado está en nombres_leds.py; acá se decide qué nombres chocarían con comandos.
# Palabras que ya significan otra cosa en algún comando: no se aceptan como nombre (verbos, «todos», «ayuda», «estado», «sensor», «giro», las palabras de inicio...).
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
)

# Las palabras de activación pueden cambiar en cualquier momento, por eso NO están en este conjunto fijo:
# revisar_nombre_de_led() las consulta en el momento (ver CLAVES_DE_INICIO).

# Números dichos con palabras: un nombre hecho solo de números («tres») se
# confundiría con los ángulos y distancias de otras órdenes («giro a tres grados»).
# Números dichos con palabras. Un nombre hecho solo de números («tres») se confundiría con «giro a tres grados», por eso se rechaza.
PALABRAS_DE_NUMERO = frozenset(
    set(NUMEROS_HASTA_29) | set(DECENAS) | set(CENTENAS) | {"y", "medio", "mil"}
)

# Frases que, aunque no tengan palabras reservadas sueltas, ya significan otra cosa.
# Frases completas que tampoco se aceptan como nombre: «led 2» (se confundiría con la orden por número) y «modo noche» (cambia el tema). Cada una va con el mensaje que verá la persona.
PATRONES_RESERVADOS_LED = (
    (PATRON_LED_NUMERADO, "Ese nombre se confundiría con la orden «LED uno». Elegí otro nombre."),
    (r"\bmodo\s+(?:oscuro|claro|noche|dia|nocturno)\b", "Ese nombre se confundiría con el cambio de tema. Elegí otro nombre."),
)


# Devuelve el motivo por el que un nombre NO sirve (o None si está bien). nombres_leds.py la llama al validar cada nombre (se la entregó este archivo al crear la instancia).
def revisar_nombre_de_led(numero, palabras):
    """Devuelve el motivo por el que un nombre no sirve, o None si está bien.

    «palabras» es el nombre ya normalizado y sin artículos (lo arma NombresLeds).
    """
    # Palabras de activación vigentes («comando», «robot»...): pueden haberlas editado desde la página.
    palabras_de_activacion = {parte for clave in CLAVES_DE_INICIO for parte in clave.split()}
    for palabra in palabras:
        if palabra in palabras_de_activacion:
            return f"La palabra «{palabra}» es una palabra de activación del asistente. Elegí otro nombre."
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


# Crea la instancia única que gestiona los nombres (nombres_leds.py). Se la usa en las rutas /api/estado, /api/reglas y /api/led/<n>/nombre, y en el intérprete de voz. Los nombres se guardan en datos/nombres_leds.json.
nombres_leds = NombresLeds(
    leds_validos=tuple(hw.LED_PINS),
    normalizar=normalizar,
    ruta=CARPETA_DATOS / "nombres_leds.json",
    revisar=revisar_nombre_de_led,
)


# Atajo: nombre actual de un LED («cocina» o «LED 1»). Se usa en mensajes de voz y respuestas.
def nombre_led(numero):
    """Nombre actual de un LED: el que eligió la persona o «LED 1», «LED 2»..."""
    return nombres_leds.obtener(numero)


# Convierte «3», «tres» o «tercero» en el número 3 (None si no se entiende), usando EQUIVALENCIAS_LED.
def _numero_de_led(texto_del_numero):
    """«3», «tres», «tercero»... -> 3 (None si no se entiende)."""
    if texto_del_numero.isdigit():
        return int(texto_del_numero)
    return EQUIVALENCIAS_LED.get(texto_del_numero)


# CORAZÓN DE LOS NOMBRES EN VOZ: averigua a qué LED se refiere una orden. La usan comando() (órdenes directas) y _parsear_accion_de_regla (reglas habladas).
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

    # Paso 1: busca expresiones tipo «led uno». Si ese LED ya tiene nombre propio ya no responde por número (se lo anota en «renombrados» para avisar); si no, es un objetivo válido.
    for coincidencia in re.finditer(PATRON_LED_NUMERADO, texto):
        numero = _numero_de_led(coincidencia.group(1))
        if numero is None:
            continue
        if numero in nombres_leds.numeros and nombres_leds.personalizado(numero):
            renombrados.append(numero)
        else:
            objetivos.append(numero)

    # Los nombres se buscan en lo que queda sin las expresiones «LED uno».
    # Paso 2: quita lo anterior de la frase y busca nombres propios en lo que queda (nombres_leds.buscar).
    resto = re.sub(PATRON_LED_NUMERADO, " ", texto)
    objetivos.extend(nombres_leds.buscar(resto))
    # Elimina duplicados conservando el orden.
    objetivos = list(dict.fromkeys(objetivos))

    # Más de un LED en la misma orden: se pide decir una orden por LED.
    if len(objetivos) > 1:
        nombres = unir_con_o([f"«{nombre_led(numero)}»" for numero in objetivos])
        return [], (
            f"Nombraste más de un LED ({nombres}). Decí una orden por cada LED, "
            "o ‘encender todas las leds’."
        )
    if objetivos:
        return objetivos, None
    # Si solo se dijo el número de un LED renombrado, se avisa cuál es su nombre nuevo y cómo pedirlo.
    if renombrados:
        numero = renombrados[0]
        nombre = nombre_led(numero)
        return [], (
            f"El LED {numero} ahora se llama «{nombre}». "
            f"Decí, por ejemplo, ‘{PALABRA_PRINCIPAL} encender {nombre}’."
        )
    return [], None


# Arma una orden de ejemplo con el primer LED (con su nombre si lo tiene) para usarla en mensajes de ayuda.
def ejemplo_de_orden_de_led():
    """Una orden de ejemplo con el primer LED, usando su nombre actual."""
    primero = min(nombres_leds.numeros)
    if nombres_leds.personalizado(primero):
        return f"encender {nombre_led(primero)}"
    return "encender led uno"


# PUT /api/led/<n>/nombre: cambia el nombre de un LED. Lo llama el formulario del lápiz (static/js/voz.js, función guardarNombre).
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
        # Llama a nombres_leds.establecer: valida y guarda. Si el nombre no sirve lanza ErrorDeNombre y se responde 400 con el motivo (la página lo muestra bajo el campo).
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


# ==========================================
# ASISTENTE: MODOS, SALUDO Y VARIAS ÓRDENES POR FRASE
# ==========================================
# Esta sección agrega cuatro funciones al intérprete de voz:
#   1. SALUDO: si solo se dice una palabra de activación («robot»), el asistente responde con un
#      saludo («Bienvenido/a. ¿En qué puedo ayudarle?»). Por ahora es únicamente texto en la página.
#   2. DOS MODOS (se eligen en la página, panel «Asistente de voz»):
#        «siempre»    cada orden empieza con la palabra de activación (comportamiento original).
#        «asistente»  se dice la palabra una vez; después las órdenes se entienden sin repetirla,
#                     hasta que pase el tiempo de espera o se diga «adiós».
#   3. VARIAS ÓRDENES EN UNA FRASE: «robot encender led uno y activar sensor» se divide en dos órdenes y
#      cada una se interpreta por separado, con SUS propias palabras clave (así no se mezclan).
#   4. PALABRAS DE ACTIVACIÓN EDITABLES: se cambian desde la página (PUT /api/configuracion).
# El estado (modo, palabras, sesión) lo guarda asistente.py; acá solo está lo que depende de los comandos.

# Palabras que NO se pueden usar como palabra de activación, porque ya significan otra cosa dentro de las
# órdenes y, como una palabra de activación separa órdenes, la frase se partiría en lugares equivocados:
# todo lo reservado para los nombres de LED, los números, las palabras de LED, los conectores y las despedidas.
PALABRAS_NO_ACTIVACION = frozenset(
    set(PALABRAS_RESERVADAS_LED)
    | set(PALABRAS_DE_NUMERO)
    | set(UNIDADES)
    | set(NUMEROS_HASTA_29)
    | set(DECENAS)
    | set(CENTENAS)
    | set(PALABRAS_LED.replace("?", "").split("|"))
    | {"led", "lampara", "foco", "y", "e", "luego", "despues", "tambien", "ademas",
       "adios", "chau", "chao", "descansa", "descansar", "dormir", "duerme", "terminar"}
)


def revisar_palabra_de_inicio(palabras):
    """Devuelve el motivo por el que una palabra de activación NO sirve, o None si está bien.

    «palabras» es la palabra (o frase corta) ya normalizada y separada en partes. asistente.py la llama al validar
    cada palabra (se la entregó este archivo al crear la instancia).
    """
    en_nombres_de_led = nombres_leds.palabras_en_uso()
    for palabra in palabras:
        # Un número en cifras («5») tampoco: se confundiría con los ángulos y las distancias.
        if palabra in PALABRAS_NO_ACTIVACION or palabra.isdigit():
            return (
                f"«{palabra}» se usa dentro de las órdenes (verbos, LED, números...) y se confundiría. "
                "Elegí otra palabra de activación."
            )
        if palabra in en_nombres_de_led:
            return f"«{palabra}» ya forma parte del nombre de un LED. Elegí otra palabra de activación."
    return None


# Crea la instancia única del asistente (asistente.py). Guarda en datos/configuracion.json el modo, las
# palabras de activación y el tiempo de espera, y mantiene la sesión despierto/dormido en memoria.
asistente = Asistente(
    palabras_por_defecto=PALABRAS_DE_INICIO,
    normalizar=normalizar,
    ruta=CARPETA_DATOS / "configuracion.json",
    revisar=revisar_palabra_de_inicio,
)
# Ahora que se pueden leer las palabras guardadas, se activan (reemplazan a las de fábrica del arranque).
aplicar_palabras_de_inicio(asistente.palabras())


# Saludo de «bienvenida». Es la respuesta que se muestra cuando se dice SOLO la palabra de activación.
# Por ahora es únicamente texto (se muestra en la página, static/js/voz.js). Si más adelante se quisiera
# agregar voz, este es el único texto que habría que leer en voz alta.
def mensaje_de_bienvenida(palabra):
    # Fórmula neutra («Bienvenido/a») porque no se sabe con quién se habla; trato de «usted».
    saludo = "Bienvenido/a. ¿En qué puedo ayudarle?"
    if asistente.modo() == "asistente":
        # Modo asistente: avisa que ya puede dar órdenes sin repetir la palabra.
        return f"{saludo} Ya puede darme órdenes sin repetir ‘{palabra}’."
    # Modo «siempre»: recuerda que cada orden debe empezar con la palabra de activación.
    return f"{saludo} Recuerde empezar cada orden con ‘{palabra}’."


# Frases que cierran la conversación. Deben ser la orden completa (no parte de otra).
DESPEDIDA = re.compile(
    r"(?:adios|hasta luego|hasta pronto|chau|chao|nos vemos|eso es todo|descansa|descansar|dormir|duerme|terminar)"
    r"(?:\s+(?:gracias|por ahora))?"
)


def _interpretar_despedida(texto):
    """«adiós», «hasta luego», «eso es todo»...: el asistente vuelve a dormir."""
    if not DESPEDIDA.fullmatch(texto):
        return None
    # Cierra la sesión (en modo «siempre» no había ninguna: no pasa nada).
    asistente.dormir()
    return jsonify({
        "ok": True,
        "mensaje": f"Hasta luego. Diga ‘{PALABRA_PRINCIPAL}’ cuando me necesite.",
        "despedida": True,
    })


# ----- División de una frase en varias órdenes -----

# Palabras que unen dos órdenes: «encender led uno Y activar sensor», «...LUEGO apagar todo».
CONECTORES_DE_ORDEN = frozenset({"y", "luego", "despues", "tambien", "ademas"})

# Una orden que empieza así es una REGLA («si hay algo a menos de veinte centímetros encender cocina»).
# Dentro de una regla no se corta: lo que sigue es su acción, no otra orden.
INICIOS_DE_REGLA = frozenset({"si", "cuando", "regla", "alarma", "automatizar", "automatizacion"})

# Máximo de órdenes que se aceptan en una misma frase.
MAX_ORDENES = 5

# Palabras que delatan que un trozo de frase es una orden completa (verbos y palabras clave de los comandos).
# Se usa para no cortar donde no corresponde: «sala y comedor» (un nombre de LED) no se parte, porque
# «comedor» no es una orden.
PALABRAS_DE_ORDEN = frozenset(
    set(VERBOS_ENCENDER.split("|"))
    | set(VERBOS_APAGAR.split("|"))
    | {
        "encienda", "prenda", "active", "ponga", "apague", "desactive", "desconecte",
        "iniciar", "inicia", "comenzar", "comienza", "arrancar", "arranca",
        "detener", "detene", "parar", "finalizar", "finaliza", "frenar", "frena",
        "giro", "giros", "centrar", "centra", "medir", "medime",
        "ayuda", "ayudas", "ayudame", "ayudar", "cerrar", "cierra", "ocultar", "oculta",
        "tema", "cambiar", "cambia", "estado", "resumen",
        "borrar", "borra", "eliminar", "elimina", "limpiar", "limpia", "vaciar", "vacia",
        "pausar", "pausa", "reanudar", "reanuda", "continuar", "continua", "reactivar", "reactiva",
        "adios", "chau", "chao", "descansa", "descansar", "dormir", "duerme", "terminar",
    }
    | INICIOS_DE_REGLA
)


def _tiene_orden(trozo):
    """True si el trozo de frase contiene alguna palabra de orden (un verbo o palabra clave de un comando)."""
    return any(palabra in PALABRAS_DE_ORDEN for palabra in trozo.split())


def _es_parte_de_un_numero(palabras, posicion):
    """True si la «y» de esa posición forma parte de un número: «cuarenta y cinco» no separa dos órdenes."""
    return (
        0 < posicion < len(palabras) - 1
        and palabras[posicion - 1] in DECENAS
        and palabras[posicion + 1] in UNIDADES
    )


def _cortar_por_conectores(texto):
    """Corta un texto en el orden en que aparecen sus conectores. Devuelve [(conector previo, trozo)]."""
    palabras = texto.split()
    # Cada trozo guarda el conector que lo precedía (para poder rearmar el texto si hay que volver a unir).
    trozos = [{"conector": None, "palabras": []}]
    en_regla = False

    for posicion, palabra in enumerate(palabras):
        actual = trozos[-1]
        # Al comienzo de un trozo: si empieza una regla, ya no se corta más (la regla llega hasta el final).
        if not actual["palabras"] and palabra in INICIOS_DE_REGLA:
            en_regla = True

        if palabra in CONECTORES_DE_ORDEN and not en_regla:
            # Conectores seguidos («y luego»): se ignoran los repetidos.
            if not actual["palabras"]:
                continue
            # «cuarenta y cinco»: esa «y» pertenece a un número.
            if palabra == "y" and _es_parte_de_un_numero(palabras, posicion):
                actual["palabras"].append(palabra)
                continue
            # Es un corte: empieza un trozo nuevo.
            trozos.append({"conector": palabra, "palabras": []})
            continue

        actual["palabras"].append(palabra)

    return [(t["conector"], " ".join(t["palabras"])) for t in trozos if t["palabras"]]


def dividir_en_ordenes(texto):
    """Divide una frase en las órdenes que contiene. Devuelve una lista de textos (una por orden).

    Ejemplo: «encender led uno y activar sensor» -> ['encender led uno', 'activar sensor'].

    Reglas:
      1. Una palabra de activación en medio de la frase empieza una orden nueva.
      2. Los conectores («y», «luego», «después»...) separan órdenes SOLO si de los dos lados hay una orden
         completa (un verbo o palabra clave de un comando). Así «sala y comedor» (un nombre) o «cuarenta y
         cinco grados» (un número) no se parten.
      3. Dentro de una regla («si ... encender ...») no se corta.
    """
    # Regla 1: separar por las palabras de activación que haya dentro de la frase.
    pedazos = [pedazo.strip() for pedazo in PATRON_DE_ACTIVACION.split(texto) if pedazo.strip()]

    ordenes = []
    for pedazo in pedazos:
        # Regla 2 y 3: cortar por conectores y volver a unir los trozos que no son órdenes completas.
        acumulado = None  # (texto, es_orden) del trozo que se está armando
        for conector, trozo in _cortar_por_conectores(pedazo):
            if acumulado is None:
                acumulado = trozo
            elif not _tiene_orden(acumulado) or not _tiene_orden(trozo):
                # Uno de los dos lados no es una orden completa: no era un corte, se vuelve a unir.
                acumulado = f"{acumulado} {conector} {trozo}"
            else:
                ordenes.append(acumulado)
                acumulado = trozo
        if acumulado is not None:
            ordenes.append(acumulado)
    return ordenes


# ----- Configuración del asistente desde la página -----

@app.route("/api/configuracion", methods=["GET"])
def leer_configuracion():
    """GET /api/configuracion: modo, palabras de activación, tiempo de espera y estado de la sesión.

    La consulta static/js/asistente.js al cargar la página (después se mantiene al día con /api/estado).
    """
    return sin_cache(jsonify({"ok": True, "asistente": asistente.estado()}))


@app.route("/api/configuracion", methods=["PUT"])
def guardar_configuracion():
    """PUT /api/configuracion: cambia uno o varios ajustes del asistente.

    Cuerpo (todos los campos son opcionales, pero debe haber al menos uno):
        {"modo": "siempre"|"asistente", "espera_s": 30, "palabras": ["comando", "robot"]}
    Se valida todo antes de aplicar nada: si un ajuste es inválido no se cambia ninguno.
    """
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify({"ok": False, "mensaje": "Faltan los datos de la configuración."}), 400

    # Solo se aceptan los campos conocidos (un nombre mal escrito en el pedido se avisa en vez de ignorarse).
    desconocidos = sorted(set(datos) - {"modo", "espera_s", "palabras"})
    if desconocidos:
        return jsonify({"ok": False, "mensaje": f"Ajuste desconocido: {', '.join(desconocidos)}."}), 400
    if not datos:
        return jsonify({"ok": False, "mensaje": "No hay ningún ajuste para cambiar."}), 400

    try:
        asistente.configurar(
            modo=datos.get("modo"),
            espera_s=datos.get("espera_s"),
            palabras=datos.get("palabras"),
        )
    except ErrorDeConfiguracion as error:
        # El motivo (palabra repetida, reservada, demasiado larga...) se muestra en la página.
        return jsonify({"ok": False, "mensaje": str(error)}), 400
    except Exception:
        app.logger.exception("Error al guardar la configuración del asistente")
        return jsonify({"ok": False, "mensaje": "No se pudo guardar la configuración."}), 500

    # Si cambiaron las palabras, se activan ya mismo: la próxima frase se reconoce con las nuevas.
    aplicar_palabras_de_inicio(asistente.palabras())
    return jsonify({"ok": True, "mensaje": "Configuración guardada.", "asistente": asistente.estado()})


# Categoría de la ayuda -> palabras que la nombran y mensaje que se muestra.
# «servo» se admite además de «giro», que es la palabra que el reconocedor entiende mejor.
# Categorías de la ayuda: cada una con la expresión que la nombra y el mensaje de respuesta. Las claves coinciden con las de comandos_ayuda.py.
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


# Arma enumeraciones con «y»: [1,2,4] -> «1, 2 y 4». También sirve para nombres.
def _unir_numeros(numeros):
    """[1] -> '1'; [1, 4] -> '1 y 4'; [1, 2, 4] -> '1, 2 y 4'."""
    textos = [str(numero) for numero in numeros]
    if len(textos) <= 1:
        return "".join(textos)
    return ", ".join(textos[:-1]) + " y " + textos[-1]


# Arma el resumen del comando «estado» (LED, servo, sensor y reglas). Usa los nombres propios de los LED si los hay.
def describir_estado():
    """Devuelve (resumen legible, estado completo) de todos los dispositivos."""
    # Pide a dispositivos.py el estado real del hardware.
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

    # Pide a automatizaciones.py las reglas para sumar al resumen cuántas hay activas.
    reglas = motor_reglas.listar()
    if reglas:
        if motor_reglas.pausadas:
            resumen += " Reglas en pausa."
        else:
            activas = sum(1 for regla in reglas if regla["activa"])
            resumen += f" Reglas activas: {activas} de {len(reglas)}."
    return resumen, estado


# ═══ INTÉRPRETES DE COMANDOS ═══
# Cada función _interpretar_... prueba si la frase es de su tipo: si no lo es devuelve None (y se prueba la siguiente); si lo es, ejecuta la acción y devuelve la respuesta JSON. comando() las llama una por una en orden.
# Ayuda: «ayuda», «ayuda leds», «cerrar ayuda». No toca hardware: devuelve una indicación que static/js/voz.js usa para abrir o cerrar el menú (ver ayuda.js).
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


# Tema: «cambiar tema», «tema oscuro», «modo claro». Solo indica a la página (static/js/tema.js) qué hacer.
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


# Estado: «estado» o «resumen». Usa describir_estado().
def _interpretar_estado(texto):
    """«estado» o «resumen»: informa cómo están todos los dispositivos."""
    if not re.search(r"\b(?:estado|resumen)\b", texto):
        return None

    resumen, estado = describir_estado()
    return jsonify({"ok": True, "mensaje": resumen, "estado": estado})


# Apagar todo: debe ser exactamente «apagar todo» (no «apagar todas las leds»). Apaga los LED y el sensor.
def _interpretar_apagar_todo(texto):
    """«apagar todo»: apaga los LED y desactiva el sensor (el servo no se mueve)."""
    patron = rf"(?:{VERBOS_APAGAR})\s+(?:el\s+)?(?:todo|todos los dispositivos)(?:\s+por favor)?"
    if not re.fullmatch(patron, texto):
        return None

    # dispositivos.controlar_todos_leds(False) apaga los cuatro; dispositivos.configurar_sensor(False) pausa el sensor.
    leds = hw.controlar_todos_leds(False)
    hw.configurar_sensor(False)
    return jsonify({
        "ok": True,
        "mensaje": "Todo apagado: LED apagados y sensor desactivado.",
        "leds": leds,
        "sensor_activo": False,
    })


# Todos los LED: requiere «todas/todos» + una palabra de LED + un verbo de encender o apagar.
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


# Centrar servo: «giro al centro». Llama a dispositivos.mover_servo(90).
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


# Interpreta la parte «qué hacer» de una regla hablada y la convierte en una acción como las de automatizaciones.py ({"tipo": "led", ...}).
def _parsear_accion_de_regla(texto):
    """Interpreta la parte «qué hacer» de una regla hablada. Devuelve la acción o None.

    Entiende lo mismo que las órdenes directas: «encender led uno» (o con el
    nombre del LED, «encender cocina»), «apagar todas las leds», «giro a 90
    grados» y «giro al centro». Lanza ErrorDeRegla si el LED es ambiguo.
    """
    # Se descartan muletillas del comienzo: «entonces encender led uno».
    # Quita muletillas del comienzo («entonces», «que», «hacer»...).
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
    # Un LED se puede nombrar por su nombre («cocina») o por su número («led uno»).
    numeros, error = resolver_leds_en_texto(texto)
    if error:
        raise ErrorDeRegla(error)
    if numeros and (enciende or apaga):
        return {"tipo": "led", "led": numeros[0], "encender": bool(enciende)}

    nombra_servo = re.search(r"\b(?:giro|servos?|servomotor|motor)\b", texto)
    if nombra_servo and re.search(r"\bcentr(?:ar|a|o|ado)\b", texto):
        return {"tipo": "servo", "angulo": 90}

    # Orden de servo dentro de una regla: «giro a 90 grados».
    giro = re.fullmatch(
        r"(?:(?:mover|mueve|girar|gira)\s+(?:el\s+)?)?(?:giro|servo|servomotor)(?:\s+(?:a|en|hasta))?\s+(.+?)\s+grados",
        texto,
    )
    if giro:
        angulo = extraer_numero(giro.group(1))
        if angulo is not None and 0 <= angulo <= 180:
            return {"tipo": "servo", "angulo": angulo}

    return None


# Texto de ayuda que se agrega a los errores al crear una regla hablada, con un ejemplo que usa el nombre actual del primer LED.
def _ayuda_regla_hablada():
    return (
        f"Decí, por ejemplo, ‘{PALABRA_PRINCIPAL} si hay algo a menos de veinte "
        f"centímetros {ejemplo_de_orden_de_led()}’."
    )


# Crear regla por voz: «si hay algo a menos de veinte centímetros encender cocina». Valida con automatizaciones.py (MotorReglas.crear).
def _interpretar_crear_regla(texto):
    """«si hay algo a menos de veinte centímetros encender led uno» y variantes.

    Admite empezar con «si», «cuando», «regla» o «alarma». Con «alarma» la
    condición es «menos de» por defecto («alarma a treinta centímetros...»).
    """
    # La frase debe empezar con «si», «cuando», «regla», «alarma»... (por eso esas palabras no se aceptan como nombre de LED).
    inicio = re.match(r"^(si|cuando|regla|alarma|automatizar|automatizacion)\b\s*(.*)$", texto)
    # Si la frase no empieza con esas palabras no es una regla (None: se prueba el siguiente intérprete). Si sí, separa la palabra inicial de lo que sigue.
    if not inicio:
        return None
    palabra_inicial, resto = inicio.groups()

    # La distancia debe terminar con una unidad («centímetros», «cm» o «metros»): lo anterior es el número y la comparación; lo posterior, la acción.
    unidad = re.search(r"\b(centimetros?|cm|metros?)\b", resto)
    if not unidad:
        return jsonify({
            "ok": False,
            "mensaje": "No entendí la distancia: tiene que terminar en ‘centímetros’. " + _ayuda_regla_hablada(),
        }), 400

    # Palabras antes de la unidad («a menos de veinte») y texto después de ella («encender cocina»). Además detecta si se habló en metros.
    antes = resto[: unidad.start()].split()
    despues = resto[unidad.end():].strip()
    en_metros = unidad.group(1).startswith("metro")

    # El número es el tramo más largo, justo antes de la unidad, que sea un número
    # («ciento veinte» gana sobre «veinte»).
    distancia = None
    posicion_numero = len(antes)
    # Busca el número: «medio metro» = 50 cm; si no, prueba con las últimas 5 palabras, 4, 3... hasta que una forme un número válido (extraer_distancia_cm). En metros se multiplica por 100.
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

    # Lo que quedó antes del número indica si es «menor» o «mayor».
    comparador = " ".join(antes[:posicion_numero])
    # Palabras de «menos de» -> condición «menor»; palabras de «más de» -> «mayor»; con «alarma» sin comparación se asume «menor»; en otro caso se pide aclararlo.
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
        # Llama a automatizaciones.MotorReglas.crear: valida y guarda la regla (archivo datos/automatizaciones.json).
        regla = motor_reglas.crear(condicion, distancia, accion)
    except ErrorDeRegla as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 400

    # Responde con la descripción de la regla (con el nombre actual del LED) y avisa si falta activar el sensor.
    mensaje = f"Regla {regla['id']} creada: {regla['descripcion']}."
    if not hw.sensor_esta_activo():
        mensaje += " Activá el sensor para que funcione."
    return jsonify({"ok": True, "mensaje": mensaje, "regla": regla})


# Gestión de reglas: «reglas» (listar), «borrar regla uno», «borrar todas las reglas», «desactivar regla dos», «pausar reglas». Usa automatizaciones.MotorReglas.
def _interpretar_gestion_reglas(texto):
    """«reglas», «borrar regla dos», «borrar todas las reglas», «pausar reglas»..."""
    if not re.search(r"\b(?:reglas?|automatizaciones?)\b", texto):
        return None
    # Una frase con distancia («regla menos de 20 centímetros...») es una regla nueva.
    if re.search(r"\b(?:centimetros?|cm|metros?)\b", texto):
        return None

    # Detecta si se habló de «reglas» (plural: todas) y qué verbo se usó (borrar, pausar, reanudar, apagar, encender).
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
    # Detecta «regla dos» (una puntual) y obtiene su número.
    puntual = re.search(r"\bregla\s+(?:(?:numero|nro)\s+)*(\d{1,2}|[a-z]+)\b", texto)
    if puntual:
        numero = extraer_numero(puntual.group(1))

    # Borrar: todas (eliminar_todas) o una puntual (eliminar).
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

    # Activar/desactivar una regla puntual (MotorReglas.activar).
    if puntual and numero is not None and (verbo_apagar or verbo_encender or verbo_pausa or verbo_reanudar):
        activar = bool(verbo_encender or verbo_reanudar)
        if motor_reglas.activar(numero, activar) is None:
            return jsonify({"ok": False, "mensaje": f"No existe la regla {numero}."}), 400
        estado = "activada" if activar else "desactivada"
        return jsonify({"ok": True, "mensaje": f"Regla {numero} {estado}.", "reglas_cambiaron": True})

    # Pausar (o reanudar) todas las reglas (MotorReglas.pausar).
    if plural and (verbo_pausa or verbo_apagar):
        motor_reglas.pausar(True)
        return jsonify({"ok": True, "mensaje": "Reglas en pausa.", "reglas_cambiaron": True})

    if plural and (verbo_reanudar or verbo_encender):
        motor_reglas.pausar(False)
        return jsonify({"ok": True, "mensaje": "Reglas reanudadas.", "reglas_cambiaron": True})

    # Sin ninguna otra intención clara («reglas», «mostrar reglas», «listar reglas»).
    # Si no se pidió ninguna acción concreta, lista las reglas (MotorReglas.resumen).
    return jsonify({"ok": True, "mensaje": motor_reglas.resumen()})


# Registro: «limpiar registro» vacía el historial (registro.py).
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
# («adiós» se revisa primero: es una frase exacta que no debe confundirse con otra.)
# Lista ORDENADA de intérpretes: comando() los prueba uno por uno y usa el primero que reconozca la frase. El orden importa (por ejemplo, «reglas» se revisa antes que los LED).
INTERPRETES_GENERALES = (
    _interpretar_despedida,
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

# ═══ ORDEN DE VOZ ═══
# POST /api/comando: recibe el texto de una frase ({"comando": "robot encender cocina"}), la interpreta y ejecuta.
# Lo llama static/js/voz.js (función procesarComando) con lo que reconoció Vosk. Es la función central del proyecto.
#
# Qué hace, en orden:
#   1. Limpia el texto y comprueba que no esté vacío ni sea demasiado largo.
#   2. Averigua si empieza con una palabra de activación y si el asistente está despierto (modo asistente).
#      Sin palabra y con el asistente dormido, la frase se ignora.
#   3. Si se dijo SOLO la palabra de activación: responde con el saludo (y despierta al asistente en modo asistente).
#   4. Divide la frase en órdenes («... y activar sensor») y ejecuta cada una por separado (_ejecutar_orden).
#   5. Actualiza la sesión del asistente y deja en «g.eventos» lo que hay que anotar en el registro.
#   6. Responde. Con una sola orden la respuesta es la de siempre (con el estado del asistente agregado);
#      con varias, trae «resultados» (uno por orden) y un mensaje que los resume.
@app.route("/api/comando", methods=["POST"])
def comando():
    datos = request.get_json(silent=True) or {}
    # «original» es lo que llegó (con tildes y mayúsculas, para mostrarlo en el registro); «texto», la versión normalizada.
    original = str(datos.get("comando", "")).strip()
    texto = normalizar(original)

    # Rechaza frases vacías o demasiado largas.
    if not texto or len(texto) > 200:
        return jsonify({"ok": False, "mensaje": "El comando está vacío o es demasiado largo."}), 400

    # Estado del asistente: ¿modo asistente? ¿está despierto (puede recibir órdenes sin palabra de activación)?
    modo_asistente = asistente.modo() == "asistente"
    en_sesion = asistente.sesion_activa()

    # Busca una palabra de activación al comienzo. «palabra» es la que usó la persona (None si no dijo ninguna)
    # y «resto» lo que sigue (si no había palabra, es la frase completa).
    palabra, resto = separar_palabra_de_inicio(texto)

    # Sin palabra de activación y con el asistente dormido: la frase no es para el sistema.
    # (registrar_orden_de_voz la anota como «ignorado»: sirve para ver qué está escuchando Vosk.)
    if palabra is None and not en_sesion:
        consigna = (
            f"con la palabra ‘{PALABRA_PRINCIPAL}’"
            if len(PALABRAS_MOSTRADAS) == 1
            else f"con {PALABRAS_DE_INICIO_MENSAJE}"
        )
        mensaje = f"Empezá la orden {consigna}. Ejemplo: ‘{PALABRA_PRINCIPAL} LED uno encender’."
        if modo_asistente:
            mensaje += f" O decí solo ‘{PALABRA_PRINCIPAL}’ para que el asistente te escuche sin repetirla."
        return jsonify({"ok": False, "mensaje": mensaje}), 400

    # FUNCIÓN 1 — SALUDO: se dijo solo la palabra de activación. El asistente responde con la bienvenida y, en
    # modo asistente, queda despierto: las próximas órdenes no necesitan la palabra.
    if palabra is not None and not resto:
        asistente.despertar()
        mensaje = mensaje_de_bienvenida(palabra)
        g.eventos = [(original, mensaje, "ok")]
        return jsonify({"ok": True, "mensaje": mensaje, "bienvenida": True, "asistente": asistente.estado()})

    # FUNCIÓN 3 — VARIAS ÓRDENES: divide la frase («encender led uno y activar sensor» -> dos órdenes).
    # Si no se pudo dividir (frase rara) se usa entera.
    ordenes = dividir_en_ordenes(resto) or [resto]
    if len(ordenes) > MAX_ORDENES:
        return jsonify({"ok": False, "mensaje": f"Son demasiadas órdenes juntas (máximo {MAX_ORDENES}). Dígalas en frases separadas."}), 400

    # Ejecuta cada orden por separado: cada una se interpreta SOLO con sus propias palabras clave, así no se
    # mezclan. Los mensajes de ejemplo usan la palabra que dijo la persona (o la principal si no dijo ninguna).
    palabra_de_ejemplo = palabra or PALABRA_PRINCIPAL
    resultados = []
    for orden in ordenes:
        cuerpo, codigo = _ejecutar_orden(orden, palabra_de_ejemplo)
        resultados.append((orden, cuerpo, codigo))

    # FUNCIÓN 2 — SESIÓN: actualiza el estado del asistente.
    #   · «adiós»: ya durmió dentro de _interpretar_despedida.
    #   · Dijo la palabra de activación: despierta (o renueva) la sesión. En modo «siempre» no hace nada.
    #   · No la dijo (conversación abierta): si alguna orden salió bien, renueva el tiempo de espera.
    algun_exito = any(cuerpo.get("ok") for _, cuerpo, _ in resultados)
    if any(cuerpo.get("despedida") for _, cuerpo, _ in resultados):
        pass
    elif palabra is not None:
        asistente.despertar()
    elif algun_exito:
        asistente.extender()

    # Prepara lo que registrar_orden_de_voz anotará en el registro (una entrada por orden).
    eventos = []
    for orden, cuerpo, _ in resultados:
        if cuerpo.get("ok"):
            estado = "ok"
        elif palabra is None:
            # Sin palabra de activación (conversación abierta) un fallo no es un error del usuario: puede ser charla.
            estado = "ignorado"
        else:
            estado = "error"
        # Con una sola orden se anota lo que se dijo; con varias, cada orden con la palabra de activación delante.
        if len(resultados) == 1:
            texto_evento = original
        else:
            texto_evento = f"{palabra} {orden}" if palabra else orden
        eventos.append((texto_evento, cuerpo.get("mensaje", ""), estado))
    g.eventos = eventos

    # Una sola orden: respuesta igual a la de siempre (la página ya la sabe interpretar), más el estado del asistente.
    if len(resultados) == 1:
        _, cuerpo, codigo = resultados[0]
        cuerpo["asistente"] = asistente.estado()
        if palabra is None and not cuerpo.get("ok"):
            # En conversación abierta, lo que no se entiende se informa pero sin tratarlo como error.
            cuerpo["ignorado"] = True
            codigo = 200
        return jsonify(cuerpo), codigo

    # Varias órdenes: «resultados» trae la respuesta de cada una (la página aplica cada una) y «mensaje» las resume.
    return jsonify({
        "ok": all(cuerpo.get("ok") for _, cuerpo, _ in resultados),
        "mensaje": " · ".join(cuerpo.get("mensaje", "") for _, cuerpo, _ in resultados),
        "resultados": [cuerpo for _, cuerpo, _ in resultados],
        "asistente": asistente.estado(),
    })


# Ejecuta UNA orden ya limpia y devuelve (cuerpo de la respuesta como diccionario, código HTTP).
# Los intérpretes devuelven objetos de respuesta de Flask; acá se convierten a diccionario para poder
# juntar los resultados de varias órdenes.
def _ejecutar_orden(texto, palabra):
    resultado = _interpretar_orden(texto, palabra)
    # Un intérprete devuelve «respuesta» o «(respuesta, código)».
    respuesta, codigo = resultado if isinstance(resultado, tuple) else (resultado, 200)
    return respuesta.get_json(), codigo


# Interpreta UNA orden (sin palabra de activación) y la ejecuta. Es la lógica de siempre de comando(), separada
# para poder usarla con cada orden de una frase. «palabra» solo se usa en los mensajes de ejemplo.
def _interpretar_orden(texto, palabra):
    # COMANDOS GENERALES: ayuda, reglas, registro, tema, estado, apagar todo, todas las LED y centrar el servo.
    # Van primero porque algunos nombran dispositivos («ayuda sensor») y no deben
    # confundirse con las órdenes individuales de más abajo.
    # Prueba cada intérprete general (ayuda, reglas, tema, estado, apagar todo, todos los LED, centrar servo). Si alguno la reconoce, responde y termina.
    for interprete in INTERPRETES_GENERALES:
        respuesta = interprete(texto)
        if respuesta is not None:
            return respuesta

    # SENSOR: activar o detener las mediciones continuas.
    # Sensor: si se nombra («sensor», «distancia»...) y hay verbo de activar o de desactivar, llama a dispositivos.configurar_sensor.
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
    # LED INDIVIDUAL: averigua qué LED se nombró (por nombre propio o por número). Ver resolver_leds_en_texto.
    numeros, error = resolver_leds_en_texto(texto)
    if error:
        return jsonify({"ok": False, "mensaje": error}), 400
    # Si se nombró un LED: toma su número y su nombre actual, decide si es encender o apagar (según el verbo) y ejecuta con dispositivos.controlar_led. Si falta verbo, pide aclararlo.
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
    # SERVO: «giro a 45 grados». Debe terminar con «grados»; el ángulo (cifras o palabras) se interpreta con extraer_numero y debe estar entre 0 y 180.
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
            # Mueve el servo con dispositivos.mover_servo.
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
    # DISTANCIA: «medir distancia». Requiere el sensor activo y devuelve la última medición (leer_distancia).
    if re.search(r"\b(distancia|cerca|lejos|medir|medime)\b", texto):
        if not hw.sensor_esta_activo():
            return jsonify({
                "ok": False,
                "mensaje": f"El sensor está desactivado. Decí ‘{palabra} activar sensor’ para iniciar las mediciones.",
                "sensor_activo": False,
            }), 400
        # Última medición válida del monitor (sensor_monitor.py).
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

# ═══ ARRANQUE ═══
# Este bloque solo se ejecuta al lanzar «python app.py» (no cuando otro archivo lo importa).
if __name__ == "__main__":
    # Primero arranca el hilo que mide el sensor.
    iniciar_servicios()
    # Levanta el servidor Flask: host «0.0.0.0» (accesible desde otros equipos de la red), puerto 5000, sin modo debug. Usa HTTPS con los certificados de la carpeta certs/ (necesario para que el navegador permita usar el micrófono desde otro equipo).
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        ssl_context=(
            "certs/172.16.4.102.pem",
            "certs/172.16.4.102-key.pem",
        ),
    )

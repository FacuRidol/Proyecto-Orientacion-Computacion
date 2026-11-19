# servidor/interprete/generales.py
"""Intérpretes de las órdenes generales: ayuda, tema, estado, apagar todo, todos los LED,
centrar el servo y limpiar el registro.

CÓMO FUNCIONAN
 Cada función interpretar_... recibe el texto ya normalizado y sin la palabra de inicio.
 Si la frase no es de su tipo devuelve None (y se prueba el siguiente intérprete); si lo es,
 ejecuta la acción y devuelve la respuesta: un diccionario o (diccionario, código HTTP).

 Algunas órdenes (ayuda, tema) no tocan el hardware: el servidor solo las clasifica y la
 página ejecuta la acción (abrir el menú, cambiar el tema).

QUIÉN LO USA: servidor/interprete/ordenes.py.
"""
import re

from flask import current_app

from funciones import dispositivos as hw
from funciones.registro import registro

from .. import palabras_inicio
from ..servicios import motor_reglas, nombre_led, nombres_leds
from ..texto import unir_con_y
from ..vocabulario import (
    PALABRAS_LED,
    RE_APAGAR,
    RE_CENTRAR,
    RE_ENCENDER,
    RE_MODO_DE_TEMA,
    RE_NOMBRA_SERVO,
    RE_PALABRA_LED,
    RE_TODOS,
    VERBOS_APAGAR,
)

# Categorías de la ayuda: cada una con la expresión que la nombra y el mensaje de respuesta. Las claves
# coinciden con las de comandos_ayuda.py. «servo» se admite además de «giro», que es la palabra que el
# reconocedor entiende mejor.
CATEGORIAS_DE_AYUDA = (
    ("leds", re.compile(rf"\b(?:{PALABRAS_LED})\b"), "Mostrando los comandos de los LED."),
    ("servo", re.compile(r"\b(?:servos?|servomotor|giro|giros|motor)\b"), "Mostrando los comandos del servo."),
    (
        "sensor",
        re.compile(
            r"\b(?:sensor|sensores|distancia|ultrasonico|ultrasonica|medicion|mediciones"
            r"|reglas?|automatizacion|automatizaciones|alarma)\b"
        ),
        "Mostrando los comandos del sensor y sus reglas.",
    ),
    ("generales", re.compile(r"\b(?:general|generales)\b"), "Mostrando los comandos generales."),
)

_RE_AYUDA = re.compile(r"\bayud(?:a|as|ame|ar)\b")
_RE_CERRAR_AYUDA = re.compile(r"\b(?:cerrar|cierra|ocultar|oculta|esconder|esconde|quitar|quita|salir)\b")
_RE_TEMA = re.compile(r"\btema\b")
_RE_TEMA_NOMBRADO = re.compile(r"\b(oscuro|oscura|noche|nocturno|negro|claro|clara|dia|diurno|blanco)\b")
_RE_ESTADO = re.compile(r"\b(?:estado|resumen)\b")
_RE_APAGAR_TODO = re.compile(
    rf"(?:{VERBOS_APAGAR})\s+(?:el\s+)?(?:todo|todos los dispositivos)(?:\s+por favor)?"
)
_RE_REGISTRO = re.compile(r"\bregistro\b")
_RE_LIMPIAR = re.compile(r"\b(?:limpiar|limpia|borrar|borra|vaciar|vacia|eliminar|elimina)\b")


def describir_estado():
    """Devuelve (resumen legible, estado completo) de todos los dispositivos.

    Arma el resumen del comando «estado» (LED, servo, sensor y reglas) con los nombres propios
    de los LED si los hay.
    """
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
            f"Encendidos: {unir_con_y([nombre_led(n) for n in encendidos])}; "
            f"apagados: {unir_con_y([nombre_led(n) for n in apagados])}"
        )
    else:
        texto_leds = (
            f"LED encendidos: {unir_con_y(encendidos)}; "
            f"apagados: {unir_con_y(apagados)}"
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


def interpretar_ayuda(texto):
    """«ayuda», «ayuda leds», «ayuda giro», «ayuda sensor», «cerrar ayuda»...

    No toca hardware: devuelve una indicación que static/js/voz.js usa para abrir o cerrar el menú (ver ayuda.js).
    """
    if not _RE_AYUDA.search(texto):
        return None

    if _RE_CERRAR_AYUDA.search(texto):
        return {"ok": True, "mensaje": "Ayuda cerrada.", "ayuda": "cerrar"}

    for categoria, patron, mensaje in CATEGORIAS_DE_AYUDA:
        if patron.search(texto):
            return {"ok": True, "mensaje": mensaje, "ayuda": categoria}

    return {
        "ok": True,
        "mensaje": f"Ayuda abierta. Elegí una categoría o decí, por ejemplo, ‘{palabras_inicio.actual.principal} ayuda leds’.",
        "ayuda": "menu",
    }


def interpretar_tema(texto):
    """«cambiar tema», «tema oscuro», «tema claro», «modo oscuro»...

    Solo indica a la página (static/js/tema.js) qué hacer.
    """
    pide_tema = _RE_TEMA.search(texto)
    pide_modo = RE_MODO_DE_TEMA.search(texto)
    if not (pide_tema or pide_modo):
        return None

    # Si se nombran los dos («de claro a oscuro»), manda el último: es el destino.
    nombrados = _RE_TEMA_NOMBRADO.findall(texto)
    if not nombrados:
        # El servidor no conoce el tema actual (es una preferencia de cada
        # navegador), así que la página decide a cuál pasar.
        return {"ok": True, "mensaje": "Cambiando el tema de la página.", "tema": "alternar"}

    oscuros = ("oscuro", "oscura", "noche", "nocturno", "negro")
    tema = "oscuro" if nombrados[-1] in oscuros else "claro"
    return {"ok": True, "mensaje": f"Activando el tema {tema}.", "tema": tema}


def interpretar_estado(texto):
    """«estado» o «resumen»: informa cómo están todos los dispositivos."""
    if not _RE_ESTADO.search(texto):
        return None

    resumen, estado = describir_estado()
    return {"ok": True, "mensaje": resumen, "estado": estado}


def interpretar_apagar_todo(texto):
    """«apagar todo»: apaga los LED y desactiva el sensor (el servo no se mueve).

    Debe ser exactamente «apagar todo» (no «apagar todas las leds»).
    """
    if not _RE_APAGAR_TODO.fullmatch(texto):
        return None

    # dispositivos.controlar_todos_leds(False) apaga los cuatro; dispositivos.configurar_sensor(False) pausa el sensor.
    leds = hw.controlar_todos_leds(False)
    hw.configurar_sensor(False)
    return {
        "ok": True,
        "mensaje": "Todo apagado: LED apagados y sensor desactivado.",
        "leds": leds,
        "sensor_activo": False,
    }


def interpretar_todos_los_leds(texto):
    """«encender todas las leds» / «apagar todas las leds».

    Requiere «todas/todos» + una palabra de LED + un verbo de encender o apagar.
    """
    dice_todos = RE_TODOS.search(texto)
    nombra_leds = RE_PALABRA_LED.search(texto)
    if not (dice_todos and nombra_leds):
        return None

    if RE_APAGAR.search(texto):
        encender = False
    elif RE_ENCENDER.search(texto):
        encender = True
    else:
        return {
            "ok": False,
            "mensaje": "Indicá si querés encender o apagar todos los LED.",
        }, 400

    leds = hw.controlar_todos_leds(encender)
    return {
        "ok": True,
        "mensaje": "Todos los LED encendidos." if encender else "Todos los LED apagados.",
        "leds": leds,
    }


def interpretar_centrar_servo(texto):
    """«giro al centro» / «centrar servo»: lleva el servo a 90° (dispositivos.mover_servo)."""
    pide_centro = RE_CENTRAR.search(texto)
    nombra_servo = RE_NOMBRA_SERVO.search(texto)
    if not (pide_centro and nombra_servo):
        return None

    try:
        hw.mover_servo(90)
    except Exception:
        current_app.logger.exception("Error al centrar el servomotor mediante voz")
        return {"ok": False, "mensaje": "No se pudo mover el servomotor."}, 500

    return {"ok": True, "mensaje": "Giro: servo centrado en 90°.", "angulo": 90}


def interpretar_registro(texto):
    """«limpiar registro» / «borrar registro»: vacía el historial de comandos (registro.py)."""
    if not _RE_REGISTRO.search(texto):
        return None
    if not _RE_LIMPIAR.search(texto):
        return None

    registro.limpiar()
    return {"ok": True, "mensaje": "Registro limpio."}

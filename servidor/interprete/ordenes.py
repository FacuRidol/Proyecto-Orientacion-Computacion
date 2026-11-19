# servidor/interprete/ordenes.py
"""Interpreta UNA orden (sin palabra de activación) y la ejecuta.

QUÉ HACE
 - interpretar_orden(): prueba los intérpretes generales (en orden) y después las órdenes
   directas: sensor, LED individual, servo y distancia.
 - ejecutar_orden(): lo mismo, devolviendo siempre (cuerpo de la respuesta, código HTTP).

CÓMO SUMAR UN COMANDO NUEVO
   1. Escribir una función interpretar_... como las de generales.py (devuelve None si la
      frase no es suya).
   2. Agregarla a INTERPRETES_GENERALES, en el lugar correcto (el orden importa).
   3. Describirla en comandos_ayuda.py para que aparezca en el menú de ayuda.

QUIÉN LO USA: servidor/rutas/ordenes.py (POST /api/comando).
"""
import re

from flask import current_app

from funciones import dispositivos as hw

from ..numeros import extraer_numero
from ..servicios import leer_distancia, nombre_led
from ..vocabulario import RE_APAGAR, RE_ENCENDER
from .generales import (
    interpretar_apagar_todo,
    interpretar_ayuda,
    interpretar_centrar_servo,
    interpretar_estado,
    interpretar_registro,
    interpretar_tema,
    interpretar_todos_los_leds,
)
from .leds import resolver_leds_en_texto
from .reglas_voz import interpretar_crear_regla, interpretar_gestion_reglas
from .sesion import interpretar_despedida

# El orden importa:
#  - «adiós» se revisa primero: es una frase exacta que no debe confundirse con otra.
#  - «ayuda sensor» tiene que evaluarse antes que las órdenes del sensor.
#  - Las reglas van antes que las órdenes directas: «si hay algo a menos de 20
#    centímetros apagar todas las leds» no debe apagar las LED en ese momento,
#    sino crear la regla.
#  - «estado» antes que cualquier otra que nombre un dispositivo.
INTERPRETES_GENERALES = (
    interpretar_despedida,
    interpretar_ayuda,
    interpretar_gestion_reglas,
    interpretar_crear_regla,
    interpretar_registro,
    interpretar_tema,
    interpretar_estado,
    interpretar_apagar_todo,
    interpretar_todos_los_leds,
    interpretar_centrar_servo,
)

# Sensor: si se nombra («sensor», «distancia»...) y hay verbo de activar o de desactivar.
_RE_MENCIONA_SENSOR = re.compile(r"\b(sensor|medicion|mediciones|ultrasonico|ultrasonica|distancia)\b")
_RE_DESACTIVAR_SENSOR = re.compile(
    r"\b(desactivar|desactiva|apagar|apaga|detener|detene|parar|para|finalizar|finaliza|desconectar|desconecta|frenar|frena)\b"
)
_RE_ACTIVAR_SENSOR = re.compile(
    r"\b(activar|activa|encender|encende|enciende|prender|prende|iniciar|inicia|comenzar|comienza|arrancar|arranca)\b"
)
# Servo: «giro a 45 grados». «grados» es obligatorio y debe ser la palabra final, lo que
# delimita el número compuesto completo.
_RE_GIRO = re.compile(r"\bgiro\b")
_RE_GIRO_GRADOS = re.compile(r"giro(?:\s+a)?\s+(.+?)\s+grados")
# Consulta puntual de distancia (el sensor tiene que estar activo).
_RE_PIDE_DISTANCIA = re.compile(r"\b(distancia|cerca|lejos|medir|medime)\b")


def interpretar_orden(texto, palabra):
    """Interpreta UNA orden (sin palabra de activación) y la ejecuta.

    Devuelve un diccionario o (diccionario, código HTTP). «palabra» solo se usa en los mensajes de ejemplo.
    """
    # COMANDOS GENERALES: ayuda, reglas, registro, tema, estado, apagar todo, todas las LED y centrar el servo.
    # Van primero porque algunos nombran dispositivos («ayuda sensor») y no deben
    # confundirse con las órdenes individuales de más abajo.
    for interprete in INTERPRETES_GENERALES:
        respuesta = interprete(texto)
        if respuesta is not None:
            return respuesta

    # SENSOR: activar o detener las mediciones continuas (dispositivos.configurar_sensor).
    if _RE_MENCIONA_SENSOR.search(texto):
        if _RE_DESACTIVAR_SENSOR.search(texto):
            hw.configurar_sensor(False)
            return {"ok": True, "mensaje": "Medición continua desactivada.", "sensor_activo": False}
        if _RE_ACTIVAR_SENSOR.search(texto):
            hw.configurar_sensor(True)
            return {"ok": True, "mensaje": "Medición continua activada.", "sensor_activo": True}

    # LED INDIVIDUAL: por su nombre («encender cocina», «cocina apagar») o, mientras
    # no se lo haya renombrado, por su número («LED uno encender», «LED 1 apagar»).
    numeros, error = resolver_leds_en_texto(texto)
    if error:
        return {"ok": False, "mensaje": error}, 400
    # Si se nombró un LED: toma su número y su nombre actual, decide si es encender o apagar (según el verbo)
    # y ejecuta con dispositivos.controlar_led. Si falta verbo, pide aclararlo.
    if numeros:
        numero = numeros[0]
        nombre = nombre_led(numero)

        if RE_ENCENDER.search(texto):
            accion = "encender"
        elif RE_APAGAR.search(texto):
            accion = "apagar"
        else:
            return {"ok": False, "mensaje": f"Indicá si querés encender o apagar «{nombre}»."}, 400

        try:
            hw.controlar_led(numero, accion == "encender")
            return {
                "ok": True,
                "mensaje": f"{nombre}: {accion}.",
                "led": numero,
                "encendido": accion == "encender",
            }
        except ValueError as error:
            return {"ok": False, "mensaje": str(error)}, 400

    # SERVO: «giro a 45 grados». Debe terminar con «grados»; el ángulo (cifras o palabras) se
    # interpreta con extraer_numero y debe estar entre 0 y 180.
    if _RE_GIRO.search(texto):
        coincidencia_giro = _RE_GIRO_GRADOS.fullmatch(texto)
        if not coincidencia_giro:
            return {
                "ok": False,
                "mensaje": f"Decí ‘{palabra} giro a 45 grados’. La palabra ‘grados’ debe ir al final.",
            }, 400

        angulo = extraer_numero(coincidencia_giro.group(1))
        if angulo is None or not 0 <= angulo <= 180:
            return {
                "ok": False,
                "mensaje": "Indicá un ángulo entero entre 0 y 180 y terminá con ‘grados’.",
            }, 400
        try:
            # Mueve el servo con dispositivos.mover_servo.
            hw.mover_servo(angulo)
            return {
                "ok": True,
                "mensaje": f"Giro: posición solicitada de {angulo}°.",
                "angulo": angulo,
            }
        except Exception:
            current_app.logger.exception("Error al mover el servomotor mediante voz")
            return {"ok": False, "mensaje": "No se pudo mover el servomotor."}, 500

    # DISTANCIA: «medir distancia». Requiere el sensor activo y devuelve la última medición (leer_distancia).
    if _RE_PIDE_DISTANCIA.search(texto):
        if not hw.sensor_esta_activo():
            return {
                "ok": False,
                "mensaje": f"El sensor está desactivado. Decí ‘{palabra} activar sensor’ para iniciar las mediciones.",
                "sensor_activo": False,
            }, 400
        # Última medición válida del monitor (sensor_monitor.py).
        valor = leer_distancia()
        if valor is None:
            return {"ok": False, "mensaje": "No se obtuvo una medición válida."}, 400
        return {
            "ok": True,
            "mensaje": f"Distancia medida: {valor:.1f} cm.",
            "distancia_cm": valor,
            "sensor_activo": True,
        }

    return {
        "ok": False,
        "mensaje": (
            f"No reconozco esa orden. Ejemplos: ‘{palabra} LED uno encender’, ‘{palabra} giro a 45 grados’ y ‘{palabra} activar sensor’. "
            f"Decí ‘{palabra} ayuda’ para ver todos los comandos."
        ),
    }, 400


def ejecutar_orden(texto, palabra):
    """Ejecuta UNA orden ya limpia y devuelve (cuerpo de la respuesta como diccionario, código HTTP)."""
    resultado = interpretar_orden(texto, palabra)
    # Un intérprete devuelve «cuerpo» o «(cuerpo, código)».
    return resultado if isinstance(resultado, tuple) else (resultado, 200)

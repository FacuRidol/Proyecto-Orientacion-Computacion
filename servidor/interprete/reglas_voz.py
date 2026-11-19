# servidor/interprete/reglas_voz.py
"""Reglas del sensor creadas y gestionadas por voz.

QUÉ HACE
 - interpretar_crear_regla: «si hay algo a menos de veinte centímetros encender cocina».
   Valida con automatizaciones.MotorReglas.crear y guarda la regla.
 - interpretar_gestion_reglas: «reglas» (listar), «borrar regla uno», «borrar todas las reglas»,
   «desactivar regla dos», «pausar reglas».

QUIÉN LO USA: servidor/interprete/ordenes.py.
"""
import re

from funciones import dispositivos as hw
from funciones.automatizaciones import ErrorDeRegla

from .. import palabras_inicio
from ..numeros import extraer_distancia_cm, extraer_numero
from ..servicios import motor_reglas
from ..vocabulario import (
    RE_APAGAR,
    RE_CENTRAR,
    RE_ENCENDER,
    RE_NOMBRA_SERVO,
    RE_PALABRA_LED,
    RE_TODOS,
    VERBOS_APAGAR,
    VERBOS_ENCENDER,
)
from .leds import ejemplo_de_orden_de_led, resolver_leds_en_texto

# --- Parte «qué hacer» de una regla ---
_RE_MULETILLAS = re.compile(r"^(?:(?:entonces|luego|despues|que|y|hace|hacer|haz)\b\s*)+")
# En una regla es común hablar en subjuntivo: «que se encienda el led uno».
_RE_ENCIENDE_REGLA = re.compile(rf"\b(?:{VERBOS_ENCENDER}|encienda|prenda|active|ponga)\b")
_RE_APAGA_REGLA = re.compile(rf"\b(?:{VERBOS_APAGAR}|apague|desactive|desconecte)\b")
# Orden de servo dentro de una regla: «giro a 90 grados».
_RE_GIRO_EN_REGLA = re.compile(
    r"(?:(?:mover|mueve|girar|gira)\s+(?:el\s+)?)?(?:giro|servo|servomotor)(?:\s+(?:a|en|hasta))?\s+(.+?)\s+grados"
)

# --- Crear una regla ---
# La frase debe empezar con «si», «cuando», «regla», «alarma»... (por eso esas palabras no se aceptan como nombre de LED).
_RE_INICIO_DE_REGLA = re.compile(r"^(si|cuando|regla|alarma|automatizar|automatizacion)\b\s*(.*)$")
# La distancia debe terminar con una unidad: lo anterior es el número y la comparación; lo posterior, la acción.
_RE_UNIDAD = re.compile(r"\b(centimetros?|cm|metros?)\b")
_RE_MENOR = re.compile(r"\b(?:menos|menor|debajo|cerca|cercano|abajo)\b")
_RE_MAYOR = re.compile(r"\b(?:mayor|arriba|encima|lejos|lejano)\b|\bmas\s+(?:de|que)\b")

# --- Gestionar reglas ---
_RE_HABLA_DE_REGLAS = re.compile(r"\b(?:reglas?|automatizaciones?)\b")
_RE_PLURAL = re.compile(r"\b(?:reglas|automatizaciones)\b")
_RE_BORRAR = re.compile(
    r"\b(?:borrar|borra|eliminar|elimina|quitar|quita|sacar|saca|vaciar|vacia|limpiar|limpia)\b"
)
_RE_PAUSAR = re.compile(r"\b(?:pausar|pausa|detener|detene|frenar|frena)\b")
_RE_REANUDAR = re.compile(r"\b(?:reanudar|reanuda|continuar|continua|reactivar|reactiva)\b")
# Número de una regla puntual: «regla 2», «regla número dos».
_RE_REGLA_PUNTUAL = re.compile(r"\bregla\s+(?:(?:numero|nro)\s+)*(\d{1,2}|[a-z]+)\b")


def parsear_accion_de_regla(texto):
    """Interpreta la parte «qué hacer» de una regla hablada. Devuelve la acción o None.

    Entiende lo mismo que las órdenes directas: «encender led uno» (o con el
    nombre del LED, «encender cocina»), «apagar todas las leds», «giro a 90
    grados» y «giro al centro». Devuelve una acción como las de automatizaciones.py
    ({"tipo": "led", ...}). Lanza ErrorDeRegla si el LED es ambiguo.
    """
    # Quita muletillas del comienzo («entonces», «que», «hacer»...): «entonces encender led uno».
    texto = _RE_MULETILLAS.sub("", texto).strip()
    if not texto:
        return None

    enciende = _RE_ENCIENDE_REGLA.search(texto)
    apaga = _RE_APAGA_REGLA.search(texto)

    if RE_TODOS.search(texto) and RE_PALABRA_LED.search(texto):
        if enciende or apaga:
            return {"tipo": "leds", "encender": bool(enciende)}
        return None

    # Un LED se puede nombrar por su nombre («cocina») o por su número («led uno»).
    numeros, error = resolver_leds_en_texto(texto)
    if error:
        raise ErrorDeRegla(error)
    if numeros and (enciende or apaga):
        return {"tipo": "led", "led": numeros[0], "encender": bool(enciende)}

    if RE_NOMBRA_SERVO.search(texto) and RE_CENTRAR.search(texto):
        return {"tipo": "servo", "angulo": 90}

    giro = _RE_GIRO_EN_REGLA.fullmatch(texto)
    if giro:
        angulo = extraer_numero(giro.group(1))
        if angulo is not None and 0 <= angulo <= 180:
            return {"tipo": "servo", "angulo": angulo}

    return None


def _ayuda_regla_hablada():
    """Texto de ayuda que se agrega a los errores al crear una regla hablada, con un ejemplo que usa el nombre actual del primer LED."""
    return (
        f"Decí, por ejemplo, ‘{palabras_inicio.actual.principal} si hay algo a menos de veinte "
        f"centímetros {ejemplo_de_orden_de_led()}’."
    )


def interpretar_crear_regla(texto):
    """«si hay algo a menos de veinte centímetros encender led uno» y variantes.

    Admite empezar con «si», «cuando», «regla» o «alarma». Con «alarma» la
    condición es «menos de» por defecto («alarma a treinta centímetros...»).
    """
    inicio = _RE_INICIO_DE_REGLA.match(texto)
    # Si la frase no empieza con esas palabras no es una regla (None: se prueba el siguiente intérprete).
    if not inicio:
        return None
    palabra_inicial, resto = inicio.groups()

    unidad = _RE_UNIDAD.search(resto)
    if not unidad:
        return {
            "ok": False,
            "mensaje": "No entendí la distancia: tiene que terminar en ‘centímetros’. " + _ayuda_regla_hablada(),
        }, 400

    # Palabras antes de la unidad («a menos de veinte») y texto después de ella («encender cocina»). Además detecta si se habló en metros.
    antes = resto[: unidad.start()].split()
    despues = resto[unidad.end():].strip()
    en_metros = unidad.group(1).startswith("metro")

    # El número es el tramo más largo, justo antes de la unidad, que sea un número
    # («ciento veinte» gana sobre «veinte»). «medio metro» = 50 cm; si no, prueba con las
    # últimas 5 palabras, 4, 3... hasta que una forme un número válido. En metros se multiplica por 100.
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
        return {
            "ok": False,
            "mensaje": "No entendí cuántos centímetros. " + _ayuda_regla_hablada(),
        }, 400

    # Lo que quedó antes del número indica si es «menor» o «mayor»; con «alarma» sin comparación se asume «menor».
    comparador = " ".join(antes[:posicion_numero])
    if _RE_MENOR.search(comparador):
        condicion = "menor"
    elif _RE_MAYOR.search(comparador):
        condicion = "mayor"
    elif palabra_inicial == "alarma":
        condicion = "menor"
    else:
        return {
            "ok": False,
            "mensaje": "Indicá si es ‘menos de’ o ‘más de’ esa distancia. " + _ayuda_regla_hablada(),
        }, 400

    try:
        accion = parsear_accion_de_regla(despues)
    except ErrorDeRegla as error:
        return {"ok": False, "mensaje": str(error)}, 400
    if accion is None:
        return {
            "ok": False,
            "mensaje": (
                f"No entendí qué hacer cuando se cumpla. Podés decir ‘{ejemplo_de_orden_de_led()}’, "
                "‘apagar todas las leds’ o ‘giro a 90 grados’."
            ),
        }, 400

    try:
        # Llama a automatizaciones.MotorReglas.crear: valida y guarda la regla (archivo datos/automatizaciones.json).
        regla = motor_reglas.crear(condicion, distancia, accion)
    except ErrorDeRegla as error:
        return {"ok": False, "mensaje": str(error)}, 400

    # Responde con la descripción de la regla (con el nombre actual del LED) y avisa si falta activar el sensor.
    mensaje = f"Regla {regla['id']} creada: {regla['descripcion']}."
    if not hw.sensor_esta_activo():
        mensaje += " Activá el sensor para que funcione."
    return {"ok": True, "mensaje": mensaje, "regla": regla}


def interpretar_gestion_reglas(texto):
    """«reglas», «borrar regla dos», «borrar todas las reglas», «pausar reglas»... (MotorReglas)."""
    if not _RE_HABLA_DE_REGLAS.search(texto):
        return None
    # Una frase con distancia («regla menos de 20 centímetros...») es una regla nueva.
    if _RE_UNIDAD.search(texto):
        return None

    # Detecta si se habló de «reglas» (plural: todas) y qué verbo se usó (borrar, pausar, reanudar, apagar, encender).
    plural = _RE_PLURAL.search(texto)
    verbo_borrar = _RE_BORRAR.search(texto)
    verbo_pausa = _RE_PAUSAR.search(texto)
    verbo_reanudar = _RE_REANUDAR.search(texto)
    verbo_apagar = RE_APAGAR.search(texto)
    verbo_encender = RE_ENCENDER.search(texto)

    # Detecta «regla dos» (una puntual) y obtiene su número.
    numero = None
    puntual = _RE_REGLA_PUNTUAL.search(texto)
    if puntual:
        numero = extraer_numero(puntual.group(1))

    # Borrar: todas (eliminar_todas) o una puntual (eliminar).
    if verbo_borrar:
        if plural and not puntual:
            cantidad = motor_reglas.eliminar_todas()
            mensaje = f"Se borraron {cantidad} reglas." if cantidad else "No había reglas para borrar."
            return {"ok": True, "mensaje": mensaje, "reglas_cambiaron": True}
        if numero is None:
            return {
                "ok": False,
                "mensaje": f"Decí qué regla borrar, por ejemplo ‘{palabras_inicio.actual.principal} borrar regla uno’.",
            }, 400
        if not motor_reglas.eliminar(numero):
            return {"ok": False, "mensaje": f"No existe la regla {numero}."}, 400
        return {"ok": True, "mensaje": f"Regla {numero} borrada.", "reglas_cambiaron": True}

    # Activar/desactivar una regla puntual (MotorReglas.activar).
    if puntual and numero is not None and (verbo_apagar or verbo_encender or verbo_pausa or verbo_reanudar):
        activar = bool(verbo_encender or verbo_reanudar)
        if motor_reglas.activar(numero, activar) is None:
            return {"ok": False, "mensaje": f"No existe la regla {numero}."}, 400
        estado = "activada" if activar else "desactivada"
        return {"ok": True, "mensaje": f"Regla {numero} {estado}.", "reglas_cambiaron": True}

    # Pausar (o reanudar) todas las reglas (MotorReglas.pausar).
    if plural and (verbo_pausa or verbo_apagar):
        motor_reglas.pausar(True)
        return {"ok": True, "mensaje": "Reglas en pausa.", "reglas_cambiaron": True}

    if plural and (verbo_reanudar or verbo_encender):
        motor_reglas.pausar(False)
        return {"ok": True, "mensaje": "Reglas reanudadas.", "reglas_cambiaron": True}

    # Si no se pidió ninguna acción concreta («reglas», «mostrar reglas», «listar reglas»), lista las reglas.
    return {"ok": True, "mensaje": motor_reglas.resumen()}

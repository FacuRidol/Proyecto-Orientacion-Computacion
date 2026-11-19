# servidor/interprete/sesion.py
"""Saludo y despedida del asistente.

QUÉ HACE
 - Saludo: si solo se dice una palabra de activación («robot»), el asistente responde con un
   saludo («Bienvenido/a. ¿En qué puedo ayudarle?»). La página lo muestra como texto y, si la persona lo deja activado, lo lee en voz alta
   (static/js/voz-salida.js; la casilla «Leer las respuestas en voz alta» lo enciende o apaga).
 - Despedida: «adiós», «hasta luego», «eso es todo»... el asistente vuelve a dormir.

QUIÉN LO USA: servidor/rutas/ordenes.py (saludo) y servidor/interprete/ordenes.py (despedida).
"""
import re

from .. import palabras_inicio
from ..servicios import asistente


def mensaje_de_bienvenida(palabra):
    """Saludo de «bienvenida»: lo que se muestra cuando se dice SOLO la palabra de activación."""
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


def interpretar_despedida(texto):
    """«adiós», «hasta luego», «eso es todo»...: el asistente vuelve a dormir."""
    if not DESPEDIDA.fullmatch(texto):
        return None
    # Cierra la sesión (en modo «siempre» no había ninguna: no pasa nada).
    asistente.dormir()
    return {
        "ok": True,
        "mensaje": f"Hasta luego. Diga ‘{palabras_inicio.actual.principal}’ cuando me necesite.",
        "despedida": True,
    }

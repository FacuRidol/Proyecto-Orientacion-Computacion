# servidor/validaciones.py
"""Reglas que deciden qué nombres de LED y qué palabras de activación se aceptan.

QUÉ HACE
 - revisar_nombre_de_led: se la entrega servicios.py a nombres_leds.NombresLeds, que la
   llama al validar cada nombre.
 - crear_revisor_de_palabras: arma la función equivalente para asistente.Asistente.
   Es una «fábrica» porque necesita consultar los nombres de LED, que se crean antes.

QUIÉN LO USA: servidor/servicios.py.
"""
from . import palabras_inicio
from .vocabulario import (
    PALABRAS_DE_NUMERO,
    PALABRAS_NO_ACTIVACION,
    PALABRAS_RESERVADAS_LED,
    PATRONES_RESERVADOS_LED,
)


def revisar_nombre_de_led(numero, palabras):
    """Devuelve el motivo por el que un nombre no sirve, o None si está bien.

    «palabras» es el nombre ya normalizado y sin artículos (lo arma NombresLeds).
    """
    # Palabras de activación vigentes («comando», «robot»...): pueden haberlas editado desde la página.
    palabras_de_activacion = {
        parte for clave in palabras_inicio.actual.claves for parte in clave.split()
    }
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
        if patron.search(frase):
            return motivo
    return None


def crear_revisor_de_palabras(nombres_leds):
    """Arma la función que revisa una palabra de activación (para asistente.Asistente)."""

    def revisar_palabra_de_inicio(palabras):
        """Devuelve el motivo por el que una palabra de activación NO sirve, o None si está bien.

        «palabras» es la palabra (o frase corta) ya normalizada y separada en partes.
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

    return revisar_palabra_de_inicio

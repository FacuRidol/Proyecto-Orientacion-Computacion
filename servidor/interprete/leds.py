# servidor/interprete/leds.py
"""Averigua a qué LED se refiere una orden hablada.

QUÉ HACE
 - Un LED se nombra por su nombre propio («cocina») o, mientras no se lo haya
   renombrado, por su número («LED uno»). resolver_leds_en_texto() es el corazón de eso.

QUIÉN LO USA: servidor/interprete/ordenes.py (órdenes directas) y servidor/interprete/reglas_voz.py (reglas habladas).
"""
from .. import palabras_inicio
from ..servicios import nombre_led, nombres_leds
from ..texto import unir_con_o
from ..vocabulario import EQUIVALENCIAS_LED, RE_LED_NUMERADO


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

    # Paso 1: busca expresiones tipo «led uno». Si ese LED ya tiene nombre propio ya no responde por número
    # (se lo anota en «renombrados» para avisar); si no, es un objetivo válido.
    for coincidencia in RE_LED_NUMERADO.finditer(texto):
        numero = _numero_de_led(coincidencia.group(1))
        if numero is None:
            continue
        if numero in nombres_leds.numeros and nombres_leds.personalizado(numero):
            renombrados.append(numero)
        else:
            objetivos.append(numero)

    # Paso 2: quita lo anterior de la frase y busca nombres propios en lo que queda (nombres_leds.buscar).
    resto = RE_LED_NUMERADO.sub(" ", texto)
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
            f"Decí, por ejemplo, ‘{palabras_inicio.actual.principal} encender {nombre}’."
        )
    return [], None


def ejemplo_de_orden_de_led():
    """Una orden de ejemplo con el primer LED, usando su nombre actual."""
    primero = min(nombres_leds.numeros)
    if nombres_leds.personalizado(primero):
        return f"encender {nombre_led(primero)}"
    return "encender led uno"

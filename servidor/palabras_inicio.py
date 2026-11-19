# servidor/palabras_inicio.py
"""Palabras de activación («comando», «robot»...): validación, patrones y estado vigente.

QUÉ HACE
 - Valida la lista de palabras y arma las expresiones regulares que reconocen el
   comienzo de una orden (preparar_palabras_de_inicio).
 - Guarda las palabras VIGENTES en «actual». Se cambian en caliente (PUT /api/configuracion)
   con aplicar_palabras_de_inicio(): la siguiente frase ya usa las nuevas, sin reiniciar.

IMPORTANTE PARA QUIEN LO USE
 «actual» se REEMPLAZA entero cada vez que cambian las palabras (una única asignación,
 así nunca se ve una mezcla de palabras viejas y nuevas). Por eso hay que leerla siempre
 como «palabras_inicio.actual.principal» en el momento de usarla, y no copiarla con
 «from ... import actual», que dejaría la copia desactualizada.

QUIÉN LO USA: servidor/servicios.py, servidor/validaciones.py, servidor/comandos/ y servidor/rutas/.
"""
import re
from typing import NamedTuple

from . import config
from .texto import normalizar, unir_con_o


class PalabrasDeInicio(NamedTuple):
    """Todo lo derivado de una lista de palabras de activación (inmutable)."""
    mostradas: list            # cómo se escriben: ["comando", "robot"]
    claves: list               # versión normalizada de cada una
    patron_inicio: re.Pattern  # reconoce la palabra solo al principio de la frase
    patron_activacion: re.Pattern  # la encuentra en cualquier parte de la frase
    principal: str             # la primera: la de los ejemplos y mensajes
    texto: str                 # «comando» o «robot» (para la página)
    mensaje: str               # ‘comando’ o ‘robot’ (para los mensajes de error)
    mostrar_por_clave: dict    # clave normalizada -> cómo se escribe


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

    # «mostradas» conserva cómo se escriben y «claves» su versión normalizada; se ignoran vacías y repetidas.
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
    # Patrón de COMIENZO: reconoce la palabra solo al principio de la frase (así empieza una orden).
    patron_inicio = re.compile(rf"^(?:{alternativas})\b\s*")
    # Patrón LIBRE: las mismas alternativas, pero sin anclar al principio. Sirve para encontrar la palabra de
    # activación en medio de la frase («robot encender led uno robot activar sensor»): cada una separa una orden.
    patron_libre = re.compile(rf"\b(?:{alternativas})\b")
    return mostradas, claves, patron_inicio, patron_libre


def _construir(palabras):
    mostradas, claves, patron_inicio, patron_libre = preparar_palabras_de_inicio(palabras)
    return PalabrasDeInicio(
        mostradas=mostradas,
        claves=claves,
        patron_inicio=patron_inicio,
        patron_activacion=patron_libre,
        principal=mostradas[0],
        texto=unir_con_o([f"«{palabra}»" for palabra in mostradas]),
        mensaje=unir_con_o([f"‘{palabra}’" for palabra in mostradas]),
        mostrar_por_clave=dict(zip(claves, mostradas)),
    )


# Palabras vigentes. Al cargar el módulo se usan las de fábrica (config.PALABRAS_DE_INICIO);
# servicios.py las reemplaza por las que eligió la persona cuando existe el objeto «asistente».
actual = _construir(config.PALABRAS_DE_INICIO)


def aplicar_palabras_de_inicio(palabras):
    """Activa una lista de palabras de activación y recalcula todo lo que depende de ella.

    Se llama al arrancar (con las guardadas) y cada vez que la persona las cambia en la
    página (PUT /api/configuracion). Si la lista no es válida lanza ValueError y no cambia nada.
    """
    global actual
    actual = _construir(palabras)


def separar_palabra_de_inicio(texto):
    """Separa la palabra de inicio de una orden ya normalizada.

    Devuelve (palabra usada, resto de la orden), o (None, texto) si la orden no
    empieza con ninguna de las palabras configuradas.
    """
    palabras = actual  # una sola lectura: patrón y tabla siempre son del mismo juego
    coincidencia = palabras.patron_inicio.match(texto)
    if coincidencia is None:
        return None, texto
    clave = " ".join(coincidencia.group(0).split())
    return palabras.mostrar_por_clave[clave], texto[coincidencia.end():].strip()

# servidor/texto.py
"""Utilidades de texto: normalizar frases y armar enumeraciones en español.

QUIÉN LO USA: casi todo el paquete servidor/ (y, por parámetro, nombres_leds.py y asistente.py).
"""
import re
import unicodedata

# Todo lo que no sea letra minúscula o número se trata como separador (los espacios
# repetidos, las comas, los signos...). Una sola pasada deja espacios simples.
_SEPARADORES = re.compile(r"[^a-z0-9]+")


def normalizar(texto):
    """Normaliza tildes, signos de puntuación y espacios (minúsculas, sin tildes)."""
    texto = str(texto).lower().strip()
    # Atajo: un texto ASCII no tiene tildes que quitar (es el caso habitual, porque
    # Vosk entrega el texto sin tildes), así que se evita el recorrido letra por letra.
    if not texto.isascii():
        # Separa cada letra de su tilde («é» -> «e» + tilde) y descarta las tildes (categoría Mn).
        texto = unicodedata.normalize("NFD", texto)
        texto = "".join(
            caracter
            for caracter in texto
            if unicodedata.category(caracter) != "Mn"
        )
    # Cambia por un espacio cada tramo de signos o espacios y quita los de los extremos.
    return _SEPARADORES.sub(" ", texto).strip()


def unir_con_o(elementos):
    """['a'] -> 'a'; ['a', 'b'] -> 'a o b'; ['a', 'b', 'c'] -> 'a, b o c'."""
    if len(elementos) <= 1:
        return "".join(elementos)
    return ", ".join(elementos[:-1]) + " o " + elementos[-1]


def unir_con_y(elementos):
    """[1] -> '1'; [1, 4] -> '1 y 4'; [1, 2, 4] -> '1, 2 y 4'. También sirve para nombres."""
    textos = [str(elemento) for elemento in elementos]
    if len(textos) <= 1:
        return "".join(textos)
    return ", ".join(textos[:-1]) + " y " + textos[-1]

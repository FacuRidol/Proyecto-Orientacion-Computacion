# servidor/numeros.py
"""Números en español: convierte «cuarenta y cinco» o «45» en un entero.

QUÉ HACE
 - Entiende ángulos del servo (0 a 180) y distancias de las reglas (0 a 499 cm),
   escritos con cifras o con palabras, porque Vosk a veces entrega números con palabras.

QUIÉN LO USA
 - servidor/comandos/ (orden «giro a ... grados» y reglas habladas) y
   servidor/vocabulario.py (palabras que no pueden ser nombre de LED).
"""
import re

from .texto import normalizar

# Cifras sueltas de hasta tres dígitos («90», «135»).
_ENTERO = re.compile(r"\d{1,3}")

# UNIDADES: del 0 al 9.
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

# Centenas, para distancias de las reglas («doscientos cincuenta»).
CENTENAS = {
    "cien": 100, "ciento": 100,
    "doscientos": 200, "doscientas": 200,
    "trescientos": 300, "trescientas": 300,
    "cuatrocientos": 400, "cuatrocientas": 400,
}


def _parsear_menor_de_cien(palabras):
    """Interpreta un número español completo de 0 a 99 (None si no es válido)."""
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
    """Interpreta un ángulo entero completo entre 0 y 180 (cifras o palabras)."""
    texto = normalizar(texto)
    if _ENTERO.fullmatch(texto):
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


def extraer_distancia_cm(texto):
    """Interpreta un número entero de 0 a 499, con cifras o con palabras.

    Reutiliza _parsear_menor_de_cien: «ciento veinte» = 100 + 20,
    «doscientos cincuenta y cinco» = 200 + 55.
    """
    texto = normalizar(texto)
    if _ENTERO.fullmatch(texto):
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

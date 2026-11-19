# servidor/vocabulario.py
"""Vocabulario de las órdenes habladas: verbos, palabras de LED y palabras reservadas.

QUÉ HACE
 - Reúne, en un solo lugar, las palabras y expresiones regulares que usan los
   intérpretes de voz (servidor/comandos/). Todas las expresiones se compilan UNA vez
   al cargar el módulo, en lugar de resolverse en cada frase.
 - Define qué palabras no se pueden usar como nombre de LED ni como palabra de activación,
   porque ya significan otra cosa dentro de las órdenes.

QUIÉN LO USA: servidor/validaciones.py y servidor/comandos/.
"""
import re

from .numeros import CENTENAS, DECENAS, NUMEROS_HASTA_29, UNIDADES

# ==========================================
# VERBOS Y PALABRAS DE LED
# ==========================================
# Verbos que significan «encender» (expresión regular: «a|b|c» = cualquiera de ellas).
VERBOS_ENCENDER = (
    r"encender|encende|enciende|encendeme|enciendeme|prender|prende|prendeme"
    r"|activar|activa|poner|pone|conectar|conecta"
)
# Verbos que significan «apagar».
VERBOS_APAGAR = r"apagar|apaga|apagame|desactivar|desactiva|desconectar|desconecta"

# Formas de decir «led» (incluye errores típicos de Vosk: «let», «les»). Se usa para entender «todas las leds / luces».
PALABRAS_LED = r"leds?|lets?|les|luz|luces|lamparas?|focos?"

# «LED uno», «LED 2», «LED número tres», «LED primero»... (el grupo 1 es el número).
# Solo vale para LED sin nombre propio. Lo usan la orden individual de un LED y las reglas habladas.
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
# EXPRESIONES COMPILADAS (compartidas por varios intérpretes)
# ==========================================
RE_LED_NUMERADO = re.compile(PATRON_LED_NUMERADO)
RE_ENCENDER = re.compile(rf"\b(?:{VERBOS_ENCENDER})\b")
RE_APAGAR = re.compile(rf"\b(?:{VERBOS_APAGAR})\b")
RE_PALABRA_LED = re.compile(rf"\b(?:{PALABRAS_LED})\b")
RE_TODOS = re.compile(r"\b(?:todas|todos)\b")
RE_NOMBRA_SERVO = re.compile(r"\b(?:giro|servos?|servomotor|motor)\b")
RE_CENTRAR = re.compile(r"\bcentr(?:ar|a|o|ado)\b")
RE_MODO_DE_TEMA = re.compile(r"\bmodo\s+(?:oscuro|claro|noche|dia|nocturno)\b")

# ==========================================
# PALABRAS RESERVADAS
# ==========================================
# Palabras que ya significan otra cosa en algún comando: no se aceptan como nombre de LED
# (verbos, «todos», «ayuda», «estado», «sensor», «giro»...). Un LED llamado «estado» haría que
# «encender estado» fuera tomado por la orden «estado». Las palabras de activación NO están
# acá porque pueden cambiar en cualquier momento (ver validaciones.revisar_nombre_de_led).
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

# Números dichos con palabras. Un nombre hecho solo de números («tres») se confundiría
# con «giro a tres grados», por eso se rechaza.
PALABRAS_DE_NUMERO = frozenset(
    set(NUMEROS_HASTA_29) | set(DECENAS) | set(CENTENAS) | {"y", "medio", "mil"}
)

# Frases completas que tampoco se aceptan como nombre: «led 2» (se confundiría con la orden por
# número) y «modo noche» (cambia el tema). Cada una va con el mensaje que verá la persona.
PATRONES_RESERVADOS_LED = (
    (RE_LED_NUMERADO, "Ese nombre se confundiría con la orden «LED uno». Elegí otro nombre."),
    (RE_MODO_DE_TEMA, "Ese nombre se confundiría con el cambio de tema. Elegí otro nombre."),
)

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

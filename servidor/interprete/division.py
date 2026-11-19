# servidor/interprete/division.py
"""División de una frase en varias órdenes.

QUÉ HACE
 - «robot encender led uno y activar sensor» se divide en dos órdenes y cada una se
   interpreta por separado, con SUS propias palabras clave (así no se mezclan).

QUIÉN LO USA: servidor/rutas/ordenes.py.
"""
from .. import palabras_inicio
from ..numeros import DECENAS, UNIDADES
from ..vocabulario import VERBOS_APAGAR, VERBOS_ENCENDER

# Palabras que unen dos órdenes: «encender led uno Y activar sensor», «...LUEGO apagar todo».
CONECTORES_DE_ORDEN = frozenset({"y", "luego", "despues", "tambien", "ademas"})

# Una orden que empieza así es una REGLA («si hay algo a menos de veinte centímetros encender cocina»).
# Dentro de una regla no se corta: lo que sigue es su acción, no otra orden.
INICIOS_DE_REGLA = frozenset({"si", "cuando", "regla", "alarma", "automatizar", "automatizacion"})

# Máximo de órdenes que se aceptan en una misma frase.
MAX_ORDENES = 5

# Palabras que delatan que un trozo de frase es una orden completa (verbos y palabras clave de los comandos).
# Se usa para no cortar donde no corresponde: «sala y comedor» (un nombre de LED) no se parte, porque
# «comedor» no es una orden.
PALABRAS_DE_ORDEN = frozenset(
    set(VERBOS_ENCENDER.split("|"))
    | set(VERBOS_APAGAR.split("|"))
    | {
        "encienda", "prenda", "active", "ponga", "apague", "desactive", "desconecte",
        "iniciar", "inicia", "comenzar", "comienza", "arrancar", "arranca",
        "detener", "detene", "parar", "finalizar", "finaliza", "frenar", "frena",
        "giro", "giros", "centrar", "centra", "medir", "medime",
        "ayuda", "ayudas", "ayudame", "ayudar", "cerrar", "cierra", "ocultar", "oculta",
        "tema", "cambiar", "cambia", "estado", "resumen",
        "borrar", "borra", "eliminar", "elimina", "limpiar", "limpia", "vaciar", "vacia",
        "pausar", "pausa", "reanudar", "reanuda", "continuar", "continua", "reactivar", "reactiva",
        "adios", "chau", "chao", "descansa", "descansar", "dormir", "duerme", "terminar",
    }
    | INICIOS_DE_REGLA
)


def _tiene_orden(trozo):
    """True si el trozo de frase contiene alguna palabra de orden (un verbo o palabra clave de un comando)."""
    return any(palabra in PALABRAS_DE_ORDEN for palabra in trozo.split())


def _es_parte_de_un_numero(palabras, posicion):
    """True si la «y» de esa posición forma parte de un número: «cuarenta y cinco» no separa dos órdenes."""
    return (
        0 < posicion < len(palabras) - 1
        and palabras[posicion - 1] in DECENAS
        and palabras[posicion + 1] in UNIDADES
    )


def _cortar_por_conectores(texto):
    """Corta un texto en el orden en que aparecen sus conectores. Devuelve [(conector previo, trozo)]."""
    palabras = texto.split()
    # Cada trozo guarda el conector que lo precedía (para poder rearmar el texto si hay que volver a unir).
    trozos = [{"conector": None, "palabras": []}]
    en_regla = False

    for posicion, palabra in enumerate(palabras):
        actual = trozos[-1]
        # Al comienzo de un trozo: si empieza una regla, ya no se corta más (la regla llega hasta el final).
        if not actual["palabras"] and palabra in INICIOS_DE_REGLA:
            en_regla = True

        if palabra in CONECTORES_DE_ORDEN and not en_regla:
            # Conectores seguidos («y luego»): se ignoran los repetidos.
            if not actual["palabras"]:
                continue
            # «cuarenta y cinco»: esa «y» pertenece a un número.
            if palabra == "y" and _es_parte_de_un_numero(palabras, posicion):
                actual["palabras"].append(palabra)
                continue
            # Es un corte: empieza un trozo nuevo.
            trozos.append({"conector": palabra, "palabras": []})
            continue

        actual["palabras"].append(palabra)

    return [(t["conector"], " ".join(t["palabras"])) for t in trozos if t["palabras"]]


def dividir_en_ordenes(texto):
    """Divide una frase en las órdenes que contiene. Devuelve una lista de textos (una por orden).

    Ejemplo: «encender led uno y activar sensor» -> ['encender led uno', 'activar sensor'].

    Reglas:
      1. Una palabra de activación en medio de la frase empieza una orden nueva.
      2. Los conectores («y», «luego», «después»...) separan órdenes SOLO si de los dos lados hay una orden
         completa (un verbo o palabra clave de un comando). Así «sala y comedor» (un nombre) o «cuarenta y
         cinco grados» (un número) no se parten.
      3. Dentro de una regla («si ... encender ...») no se corta.
    """
    # Regla 1: separar por las palabras de activación que haya dentro de la frase.
    pedazos = [
        pedazo.strip()
        for pedazo in palabras_inicio.actual.patron_activacion.split(texto)
        if pedazo.strip()
    ]

    ordenes = []
    for pedazo in pedazos:
        # Regla 2 y 3: cortar por conectores y volver a unir los trozos que no son órdenes completas.
        acumulado = None  # texto del trozo que se está armando
        for conector, trozo in _cortar_por_conectores(pedazo):
            if acumulado is None:
                acumulado = trozo
            elif not _tiene_orden(acumulado) or not _tiene_orden(trozo):
                # Uno de los dos lados no es una orden completa: no era un corte, se vuelve a unir.
                acumulado = f"{acumulado} {conector} {trozo}"
            else:
                ordenes.append(acumulado)
                acumulado = trozo
        if acumulado is not None:
            ordenes.append(acumulado)
    return ordenes

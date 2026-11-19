# servidor/respuestas.py
"""Ayudas para armar respuestas HTTP."""


def sin_cache(respuesta):
    """Evita que el navegador reutilice datos que cambian cada segundo."""
    respuesta.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    respuesta.headers["Pragma"] = "no-cache"
    return respuesta

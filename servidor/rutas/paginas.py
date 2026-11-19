# servidor/rutas/paginas.py
"""Página principal y estado general.

RUTAS
  GET /            la página (templates/index.html). Los archivos static/css y static/js los sirve Flask solos.
  GET /api/estado  foto del hardware, los nombres y el asistente. static/js/voz.js la consulta cada
                   segundo para sincronizar todas las pestañas.
"""
from flask import Blueprint, jsonify, render_template

from funciones import dispositivos as hw
from funciones.comandos_ayuda import AYUDA_COMANDOS

from .. import palabras_inicio
from ..respuestas import sin_cache
from ..servicios import asistente, nombres_leds

bp = Blueprint("paginas", __name__)


@bp.route("/")
def inicio():
    # El catálogo de comandos (comandos_ayuda.py) se dibuja en el menú de ayuda, y las
    # palabras de inicio configuradas se usan en los textos de la página.
    palabras = palabras_inicio.actual
    return render_template(
        "index.html",
        ayuda=AYUDA_COMANDOS,
        palabra_inicio=palabras.principal,
        palabras_inicio_texto=palabras.texto,
    )


@bp.route("/api/estado")
def estado():
    """Estado central compartido por todas las pestañas y navegadores."""
    # Estado de LED, servo y sensor (dispositivos.py) más los nombres de los LED (nombres_leds.py)
    # y el modo, las palabras de activación y la sesión del asistente (asistente.py), que
    # static/js/asistente.js usa para mantener el panel «Asistente de voz» sincronizado.
    datos = hw.obtener_estado()
    datos["nombres"] = nombres_leds.todos()
    datos["asistente"] = asistente.estado()
    return sin_cache(jsonify(datos))

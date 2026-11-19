# servidor/__init__.py
"""Paquete del servidor web: crea la aplicación Flask y registra todas sus rutas.

ESTRUCTURA
  config.py ......... palabras de inicio, carpetas y parámetros del servidor (lo que se edita)
  servicios.py ...... instancias únicas: nombres de LED, asistente, reglas y monitor del sensor
  texto.py .......... normalizar texto y armar enumeraciones
  numeros.py ........ números en español («cuarenta y cinco» -> 45)
  vocabulario.py .... verbos, palabras de LED y palabras reservadas de las órdenes
  validaciones.py ... qué nombres de LED y palabras de activación se aceptan
  palabras_inicio.py  palabras de activación vigentes
  respuestas.py ..... ayudas para respuestas HTTP
  rutas/ ............ las rutas HTTP, una por tema (blueprints)
  interprete/ ....... el intérprete de las órdenes habladas

El hardware, Vosk y la lógica que no depende de Flask están en el paquete funciones/.
"""
from flask import Flask

from . import config
from .rutas import registrar_rutas
from .servicios import iniciar_servicios


def crear_app():
    """Crea la aplicación Flask (la página, la API y los archivos estáticos)."""
    # root_path hace que templates/ y static/ se busquen en la carpeta del proyecto (junto a app.py).
    app = Flask("servidor", root_path=str(config.RAIZ))
    registrar_rutas(app)
    return app


__all__ = ["crear_app", "iniciar_servicios"]

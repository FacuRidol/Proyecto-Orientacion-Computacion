# servidor/rutas/__init__.py
"""Rutas HTTP (blueprints de Flask), una por tema.

  paginas.py ........ la página y /api/estado
  leds.py ........... control y nombres de los LED
  servo.py .......... servomotor
  sensor.py ......... sensor ultrasónico, distancia e historial
  reglas.py ......... automatizaciones (reglas del sensor)
  historial.py ...... registro de comandos
  voz.py ............ reconocimiento de voz (Vosk)
  configuracion.py .. configuración del asistente
  ordenes.py ........ POST /api/comando (órdenes habladas)

Para agregar una ruta nueva: crear el archivo con su «bp = Blueprint(...)» y sumarlo a la lista de abajo.
"""
from . import configuracion, historial, leds, ordenes, paginas, reglas, sensor, servo, voz

# Todos los blueprints que se registran en la aplicación.
BLUEPRINTS = (
    paginas.bp,
    leds.bp,
    servo.bp,
    sensor.bp,
    reglas.bp,
    historial.bp,
    voz.bp,
    configuracion.bp,
    ordenes.bp,
)


def registrar_rutas(app):
    """Registra todas las rutas en la aplicación Flask."""
    for bp in BLUEPRINTS:
        app.register_blueprint(bp)

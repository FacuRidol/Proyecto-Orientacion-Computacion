# servidor/interprete/__init__.py
"""Intérprete de las órdenes habladas: convierte una frase ya reconocida en una acción.

  leds.py ......... a qué LED se refiere una orden (por nombre o por número)
  sesion.py ....... saludo y despedida del asistente
  division.py ..... divide una frase en varias órdenes
  generales.py .... ayuda, tema, estado, apagar todo, todos los LED, centrar servo, registro
  reglas_voz.py ... crear y gestionar reglas del sensor por voz
  ordenes.py ...... interpreta y ejecuta UNA orden (usa los anteriores)

La ruta que lo usa es POST /api/comando (servidor/rutas/ordenes.py).
"""

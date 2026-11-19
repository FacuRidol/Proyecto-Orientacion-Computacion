# funciones/__init__.py
"""Funciones del proyecto: hardware, reconocimiento de voz y lógica que no depende de Flask.

  dispositivos.py ........... LED, servomotor y sensor ultrasónico (GPIO)
  reconocimiento_voz.py ..... Vosk: audio -> texto (con correcciones_vosk.json)
  asistente.py .............. modo, palabras de activación y sesión (despierto/dormido)
  automatizaciones.py ....... reglas «si la distancia es menor a X, hacer Y»
  nombres_leds.py ........... nombres personalizados de los LED
  registro.py ............... historial de comandos y reglas disparadas
  sensor_monitor.py ......... hilo que mide la distancia en segundo plano
  comandos_ayuda.py ......... textos del menú «Ayuda de comandos»

Las rutas HTTP y el intérprete de órdenes habladas están en servidor/.
"""

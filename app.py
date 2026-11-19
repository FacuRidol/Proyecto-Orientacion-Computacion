# app.py

# ┌─────────────────────────────────────────────────────────────────────────┐
# │ app.py: PUNTO DE ENTRADA (se inicia con «python app.py»)                │
# │                                                                         │
# │ QUÉ HACE                                                                │
# │  Crea la aplicación Flask, arranca el hilo que mide el sensor y         │
# │  levanta el servidor HTTPS. Todo lo demás está en el paquete servidor/. │
# │                                                                         │
# │ DÓNDE ESTÁ CADA COSA                                                    │
# │  - servidor/config.py ...... palabras de inicio, carpetas, puerto y     │
# │                              certificados (lo que normalmente se edita).│
# │  - servidor/rutas/ ......... las rutas /api/... (una por tema).         │
# │  - servidor/interprete/ .... entiende las órdenes habladas.             │
# │  - servidor/servicios.py ... nombres de LED, asistente, reglas y monitor│
# │                                                                         │
# │ MÓDULOS DE funciones/ QUE USA EL SERVIDOR                               │
# │  - dispositivos.py ........ LED, servo y sensor (hardware).             │
# │  - reconocimiento_voz.py .. Vosk: audio -> texto.                       │
# │  - comandos_ayuda.py ...... textos del menú «Ayuda de comandos».        │
# │  - automatizaciones.py .... reglas «si la distancia es menor a X...».   │
# │  - nombres_leds.py ........ nombres personalizados de los LED.          │
# │  - asistente.py ........... modo, palabras de activación y sesión.      │
# │  - registro.py ............ historial de comandos y reglas disparadas.  │
# │  - sensor_monitor.py ...... hilo que mide la distancia en segundo plano.│
# │                                                                         │
# │ QUIÉN LO USA                                                            │
# │  - El navegador: static/js/*.js llaman a las rutas /api/ del paquete.   │
# └─────────────────────────────────────────────────────────────────────────┘
from servidor import config, crear_app, iniciar_servicios

# La aplicación Flask. Se mantiene el nombre «app» para que también funcione
# con «flask --app app run» o con un servidor WSGI (por ejemplo, «app:app»).
app = crear_app()


# ═══ ARRANQUE ═══
# Este bloque solo se ejecuta al lanzar «python app.py» (no cuando otro archivo lo importa).
if __name__ == "__main__":
    # Primero arranca el hilo que mide el sensor.
    iniciar_servicios()
    # Levanta el servidor Flask con HTTPS (necesario para que el navegador permita usar el micrófono
    # desde otro equipo). Host, puerto y certificados se definen en servidor/config.py.
    app.run(
        host=config.HOST,
        port=config.PUERTO,
        debug=False,
        ssl_context=(str(config.CERTIFICADO), str(config.CLAVE_PRIVADA)),
    )

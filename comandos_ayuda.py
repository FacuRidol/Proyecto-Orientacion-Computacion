# comandos_ayuda.py
"""Catálogo de comandos de voz que muestra el menú «Ayuda de comandos».

Este archivo solo contiene texto: lo usa templates/index.html para dibujar las
cuatro listas. Para sumar, quitar o corregir un comando en la ayuda alcanza con
editar este diccionario; no hace falta tocar HTML ni JavaScript.

La lógica que realmente interpreta cada frase está en app.py (ver la función
comando() y los intérpretes generales). Si agregás un comando nuevo allá,
acordate de describirlo acá para que aparezca en la ayuda.

Formato:
    clave de la categoría -> titulo (texto del botón), encabezado (título de la
    lista), resumen y lista de comandos.
    Cada comando tiene "frases" (una o más formas de decirlo) y "detalle".
    Las frases se escriben SIN la palabra inicial «comando»: la página la agrega.

Las claves ("leds", "servo", "sensor", "generales") deben coincidir con las que
devuelve app.py en el campo "ayuda" de la respuesta.
"""

AYUDA_COMANDOS = {
    "leds": {
        "titulo": "LED",
        "encabezado": "Comandos de los LED",
        "resumen": "Encienden y apagan las luces, una por una o todas juntas.",
        "comandos": [
            {
                "frases": ["LED uno encender", "LED dos apagar"],
                "detalle": "Enciende o apaga un LED según su número: uno, dos, tres o cuatro.",
            },
            {
                "frases": ["encender todas las leds"],
                "detalle": "Enciende los cuatro LED a la vez.",
            },
            {
                "frases": ["apagar todas las leds"],
                "detalle": "Apaga los cuatro LED a la vez.",
            },
        ],
    },
    "servo": {
        "titulo": "Servo",
        "encabezado": "Comandos del servo",
        "resumen": "Mueven el servomotor. Se dice «giro» en lugar de «servo» porque el reconocedor lo entiende mejor.",
        "comandos": [
            {
                "frases": ["giro a 45 grados"],
                "detalle": "Lleva el servo al ángulo indicado, de 0 a 180. La palabra «grados» va siempre al final.",
            },
            {
                "frases": ["giro a ciento treinta y cinco grados"],
                "detalle": "El ángulo también se puede decir con palabras.",
            },
            {
                "frases": ["giro al centro"],
                "detalle": "Deja el servo en la posición central (90°).",
            },
        ],
    },
    "sensor": {
        "titulo": "Sensor",
        "encabezado": "Comandos del sensor",
        "resumen": "Controlan el sensor ultrasónico de distancia.",
        "comandos": [
            {
                "frases": ["activar sensor"],
                "detalle": "Empieza a medir la distancia de forma continua.",
            },
            {
                "frases": ["desactivar sensor"],
                "detalle": "Detiene las mediciones.",
            },
            {
                "frases": ["medir distancia"],
                "detalle": "Informa la distancia actual. El sensor tiene que estar activado.",
            },
        ],
    },
    "generales": {
        "titulo": "Generales",
        "encabezado": "Comandos generales",
        "resumen": "Controlan la propia página y acciones que afectan a varios dispositivos.",
        "comandos": [
            {
                "frases": ["ayuda"],
                "detalle": "Abre este menú de ayuda.",
            },
            {
                "frases": ["ayuda leds", "ayuda giro", "ayuda sensor", "ayuda generales"],
                "detalle": "Abre directamente la lista de comandos de esa categoría.",
            },
            {
                "frases": ["cerrar ayuda"],
                "detalle": "Cierra el menú de ayuda.",
            },
            {
                "frases": ["cambiar tema"],
                "detalle": "Alterna entre el tema claro y el oscuro.",
            },
            {
                "frases": ["tema oscuro", "tema claro"],
                "detalle": "Elige el tema directamente.",
            },
            {
                "frases": ["estado"],
                "detalle": "Resume cómo están los LED, el servo y el sensor.",
            },
            {
                "frases": ["apagar todo"],
                "detalle": "Apaga los LED y desactiva el sensor. El servo queda donde está.",
            },
        ],
    },
}

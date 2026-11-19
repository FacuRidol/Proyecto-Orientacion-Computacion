# comandos_ayuda.py
"""Catálogo de comandos de voz que muestra el menú «Ayuda de comandos».

Este archivo solo contiene texto: lo usa templates/index.html para dibujar las
cuatro listas. (La lista «Con los nombres que tienen ahora», al final de los
comandos de LED, no está acá: la dibuja static/js/voz.js con los nombres que
cada persona le puso a sus LED.) Para sumar, quitar o corregir un comando en la ayuda alcanza con
editar este diccionario; no hace falta tocar HTML ni JavaScript.

La lógica que realmente interpreta cada frase está en app.py (ver la función
comando() y los intérpretes generales). Si agregás un comando nuevo allá,
acordate de describirlo acá para que aparezca en la ayuda.

Formato:
    clave de la categoría -> titulo (texto del botón), encabezado (título de la
    lista), resumen y lista de comandos.
    Cada comando tiene "frases" (una o más formas de decirlo) y "detalle".
    Las frases se escriben SIN la palabra de inicio: la página agrega la principal de
    PALABRAS_DE_INICIO (la lista configurable al comienzo de app.py).

Las claves ("leds", "servo", "sensor", "generales") deben coincidir con las que
devuelve app.py en el campo "ayuda" de la respuesta.
"""

# ┌─────────────────────────────────────────────────────────────────────────┐
# │ QUIÉN LO USA                                                            │
# │ Solo datos (texto), no importa nada. app.py hace                        │
# │ «from comandos_ayuda import AYUDA_COMANDOS» y se lo entrega a           │
# │ templates/index.html (variable «ayuda»), que dibuja el menú «Ayuda de   │
# │ comandos». static/js/ayuda.js abre y cierra ese menú.                   │
# └─────────────────────────────────────────────────────────────────────────┘
# Diccionario principal: una entrada por categoría (leds, servo, sensor, generales).
AYUDA_COMANDOS = {
    # CATEGORÍA LED: comandos para encender y apagar luces.
    "leds": {
        "titulo": "LED",
        "encabezado": "Comandos de los LED",
        "resumen": (
            "Encienden y apagan las luces, una por una o todas juntas. "
            "Cada LED se nombra con el nombre que le pongas en la página."
        ),
        "comandos": [
            {
                # Comando 1: orden por NOMBRE del LED (el nombre se cambia en la página).
                "frases": ["encender cocina", "apagar cocina"],
                "detalle": (
                    "Enciende o apaga un LED por su nombre. Los nombres se cambian en la página, "
                    "con el lápiz de cada LED; «cocina» es solo un ejemplo. "
                    "Abajo está la lista con los nombres actuales."
                ),
            },
            {
                # Comando 2: orden por NÚMERO (solo mientras el LED no fue renombrado).
                "frases": ["LED uno encender", "LED dos apagar"],
                "detalle": (
                    "Mientras un LED conserve su nombre original (LED 1, LED 2...), también se lo "
                    "nombra por su número: uno, dos, tres o cuatro. Al ponerle un nombre propio, "
                    "pasa a responder solo a ese nombre."
                ),
            },
            {
                # Comando 3: enciende los cuatro.
                "frases": ["encender todas las leds"],
                "detalle": "Enciende los cuatro LED a la vez.",
            },
            {
                # Comando 4: apaga los cuatro.
                "frases": ["apagar todas las leds"],
                "detalle": "Apaga los cuatro LED a la vez.",
            },
        ],
    },
    # CATEGORÍA SERVO: comandos del servomotor.
    "servo": {
        "titulo": "Servo",
        "encabezado": "Comandos del servo",
        "resumen": "Mueven el servomotor. Se dice «giro» en lugar de «servo» porque el reconocedor lo entiende mejor.",
        "comandos": [
            {
                # Mover a un ángulo en cifras.
                "frases": ["giro a 45 grados"],
                "detalle": "Lleva el servo al ángulo indicado, de 0 a 180. La palabra «grados» va siempre al final.",
            },
            {
                # Mover a un ángulo dicho con palabras.
                "frases": ["giro a ciento treinta y cinco grados"],
                "detalle": "El ángulo también se puede decir con palabras.",
            },
            {
                # Volver a 90°.
                "frases": ["giro al centro"],
                "detalle": "Deja el servo en la posición central (90°).",
            },
        ],
    },
    # CATEGORÍA SENSOR: sensor ultrasónico y reglas automáticas.
    "sensor": {
        "titulo": "Sensor",
        "encabezado": "Comandos del sensor",
        "resumen": "Controlan el sensor ultrasónico y las reglas automáticas que dependen de la distancia.",
        "comandos": [
            {
                # Encender las mediciones.
                "frases": ["activar sensor"],
                "detalle": "Empieza a medir la distancia de forma continua.",
            },
            {
                # Apagar las mediciones.
                "frases": ["desactivar sensor"],
                "detalle": "Detiene las mediciones.",
            },
            {
                # Preguntar la distancia actual.
                "frases": ["medir distancia"],
                "detalle": "Informa la distancia actual. El sensor tiene que estar activado.",
            },
            {
                # Crear una regla «menos de».
                "frases": ["si hay algo a menos de veinte centímetros encender led uno"],
                "detalle": (
                    "Crea una regla: cuando la distancia baje de 20 cm, enciende el LED 1 "
                    "(o el LED con el nombre que le hayas puesto, por ejemplo «encender cocina»). "
                    "También se puede apagar un LED, encender o apagar todas las leds, "
                    "«giro a 90 grados» o «giro al centro»."
                ),
            },
            {
                # Crear una regla «más de».
                "frases": ["si algo está a más de cien centímetros apagar todas las leds"],
                "detalle": "Con «más de», la regla se dispara cuando la distancia supera ese valor. También se puede decir «metros».",
            },
            {
                # Forma corta de crear una regla.
                "frases": ["alarma a treinta centímetros encender todas las leds"],
                "detalle": "Forma corta: «alarma» equivale a «si hay algo a menos de».",
            },
            {
                # Listar las reglas.
                "frases": ["reglas"],
                "detalle": "Dice cuántas reglas hay y qué hace cada una.",
            },
            {
                # Borrar una regla o todas.
                "frases": ["borrar regla uno", "borrar todas las reglas"],
                "detalle": "Borra una regla por su número, o todas.",
            },
            {
                # Activar o desactivar una regla sin borrarla.
                "frases": ["desactivar regla uno", "activar regla uno"],
                "detalle": "Apaga o enciende una regla sin borrarla.",
            },
            {
                # Pausar o reanudar todas las reglas.
                "frases": ["pausar reglas", "reanudar reglas"],
                "detalle": "Detiene o reanuda todas las reglas. Solo se evalúan con el sensor activado.",
            },
        ],
    },
    # CATEGORÍA GENERALES: la propia página y acciones globales.
    "generales": {
        "titulo": "Generales",
        "encabezado": "Comandos generales",
        "resumen": "Controlan la propia página y acciones que afectan a varios dispositivos.",
        "comandos": [
            {
                # Llamar al asistente: decir SOLO la palabra de activación. La frase vacía hace que la página
                # muestre únicamente la palabra («robot»).
                "frases": [""],
                "detalle": (
                    "Dicha sola, la palabra de activación llama al asistente: responde con un saludo "
                    "(«Bienvenido/a. ¿En qué puedo ayudarle?»). En modo asistente queda escuchando y las "
                    "órdenes siguientes no necesitan la palabra; el modo se elige en el panel «Asistente de voz»."
                ),
            },
            {
                # Varias órdenes en una frase, con una sola palabra de activación.
                "frases": ["encender led uno y activar sensor"],
                "detalle": (
                    "Se pueden decir varias órdenes seguidas con una sola palabra de activación, unidas con "
                    "«y», «luego» o «después» (hasta 5). Cada una se interpreta y se ejecuta por separado."
                ),
            },
            {
                # Terminar la conversación con el asistente.
                "frases": ["adiós", "hasta luego"],
                "detalle": (
                    "Termina la conversación: en modo asistente vuelve a esperar la palabra de activación "
                    "(también lo hace solo cuando pasa el tiempo de espera)."
                ),
            },
            {
                # Abrir la ayuda.
                "frases": ["ayuda"],
                "detalle": "Abre este menú de ayuda.",
            },
            {
                # Abrir una categoría de la ayuda directamente.
                "frases": ["ayuda leds", "ayuda giro", "ayuda sensor", "ayuda generales"],
                "detalle": "Abre directamente la lista de comandos de esa categoría.",
            },
            {
                # Cerrar la ayuda.
                "frases": ["cerrar ayuda"],
                "detalle": "Cierra el menú de ayuda.",
            },
            {
                # Alternar tema claro/oscuro.
                "frases": ["cambiar tema"],
                "detalle": "Alterna entre el tema claro y el oscuro.",
            },
            {
                # Elegir el tema directamente.
                "frases": ["tema oscuro", "tema claro"],
                "detalle": "Elige el tema directamente.",
            },
            {
                # Resumen del estado de todo.
                "frases": ["estado"],
                "detalle": "Resume cómo están los LED, el servo y el sensor.",
            },
            {
                # Apagar LED y sensor.
                "frases": ["apagar todo"],
                "detalle": "Apaga los LED y desactiva el sensor. El servo queda donde está.",
            },
            {
                # Vaciar el registro de comandos.
                "frases": ["limpiar registro"],
                "detalle": "Vacía el registro de comandos.",
            },
        ],
    },
}

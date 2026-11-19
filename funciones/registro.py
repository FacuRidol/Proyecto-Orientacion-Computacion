# registro.py
"""Registro de eventos: historial de comandos de voz y de reglas automáticas.

Guarda en memoria los últimos eventos para que la página los muestre en el
panel «Registro de comandos». Sirve para ver qué entendió realmente Vosk,
ajustar el reconocimiento y mostrar el proyecto funcionando.

Cada evento es un diccionario:
    id         número creciente; no se repite ni siquiera después de limpiar
    ts         momento del evento, en segundos desde 1970 (hora del servidor)
    origen     "voz" (orden hablada) o "regla" (automatización disparada)
    texto      lo que escuchó Vosk, o la condición que cumplió la regla
    resultado  mensaje que se le mostró al usuario o acción ejecutada
    estado     "ok", "error" o "ignorado" (frase que no empezó con «comando»)

El registro vive solo en memoria: se vacía al reiniciar la aplicación.
"""

# ┌─────────────────────────────────────────────────────────────────────────┐
# │ DE QUIÉN DEPENDE / QUIÉN LO USA                                         │
# │ No importa ningún archivo del proyecto (solo librerías estándar).       │
# │   - app.py lo importa (from registro import registro) y:                │
# │       · registro.agregar(...) desde registrar_orden_de_voz (app.py),    │
# │         que anota cada orden recibida en POST /api/comando              │
# │       · registro.desde(...) / registro.posicion() desde GET /api/registro│
# │         (lo consulta static/js/registro.js para dibujar el panel)       │
# │       · registro.limpiar() desde el botón «Limpiar» y desde «limpiar    │
# │         registro» por voz                                               │
# │   - automatizaciones.py recibe registro.agregar por parámetro           │
# │     («registrar») y lo llama cada vez que una regla se dispara.         │
# └─────────────────────────────────────────────────────────────────────────┘

# threading: el candado evita que dos peticiones simultáneas rompan la lista de eventos.
import threading
# time: para ponerle a cada evento la hora en que ocurrió (time.time()).
import time
# deque: lista con tamaño máximo; al llenarse descarta sola los eventos más viejos.
from collections import deque

# Cuántos eventos se recuerdan como máximo (los más viejos se descartan).
CAPACIDAD = 200
# Valores permitidos para «origen» y «estado»: sirven para validar lo que se agrega.
ORIGENES = ("voz", "regla")
ESTADOS = ("ok", "error", "ignorado")
# Topes de longitud para que un texto enorme no llene la memoria ni la pantalla.
LARGO_MAXIMO_TEXTO = 200
LARGO_MAXIMO_RESULTADO = 300


# Clase que guarda el historial. Hay una sola instancia, creada al final del archivo.
class RegistroEventos:
    # Constructor: deja el historial vacío.
    def __init__(self, capacidad=CAPACIDAD):
        # Lista con tope: al pasar de «capacidad» elementos descarta el más viejo.
        self._eventos = deque(maxlen=capacidad)
        # Candado propio de esta clase (Lock simple: ningún método se llama a sí mismo).
        self._candado = threading.Lock()
        # Contador del último id entregado.
        self._ultimo_id = 0
        self._base_id = 1  # primer id vigente: los anteriores se limpiaron

    # Agrega un evento. Lo llaman app.py (voz) y automatizaciones.py (reglas, vía «registrar»).
    def agregar(self, origen, texto, resultado, estado):
        """Agrega un evento y devuelve una copia del evento guardado."""
        # Valida que el origen sea «voz» o «regla»; si no, es un error de programación.
        if origen not in ORIGENES:
            raise ValueError(f"Origen de evento no válido: {origen!r}")
        # Idem con el estado («ok», «error» o «ignorado»).
        if estado not in ESTADOS:
            raise ValueError(f"Estado de evento no válido: {estado!r}")

        # Candado: dos eventos simultáneos no pueden recibir el mismo id.
        with self._candado:
            # Cada evento nuevo recibe el id siguiente (nunca se repite).
            self._ultimo_id += 1
            # Arma el evento como diccionario (es lo que viaja como JSON a la página).
            evento = {
                "id": self._ultimo_id,
                # Hora del servidor con 3 decimales (milisegundos).
                "ts": round(time.time(), 3),
                "origen": origen,
                # str(...) por si llega otro tipo; [:N] recorta a la longitud máxima.
                "texto": str(texto)[:LARGO_MAXIMO_TEXTO],
                "resultado": str(resultado)[:LARGO_MAXIMO_RESULTADO],
                "estado": estado,
            }
            # Lo guarda al final de la lista (si estaba llena, sale el más viejo).
            self._eventos.append(evento)
            # Devuelve una copia para que nadie modifique el original guardado.
            return dict(evento)

    # Devuelve solo los eventos que una página todavía no vio. Lo usa GET /api/registro (app.py),
    # que static/js/registro.js consulta cada segundo pasando el último id que ya tiene.
    def desde(self, ultimo_visto=0):
        """Eventos posteriores al id indicado (del más viejo al más nuevo)."""
        with self._candado:
            # Filtra por id mayor al último visto y devuelve copias.
            return [dict(e) for e in self._eventos if e["id"] > ultimo_visto]

    # Informa hasta qué id se llegó y desde cuál son válidos los eventos. Lo usa GET /api/registro (app.py).
    def posicion(self):
        """(ultimo_id, base_id) para que cada página sepa qué le falta y qué descartar."""
        with self._candado:
            return self._ultimo_id, self._base_id

    # Borra el historial. Lo llaman el botón «Limpiar» (DELETE /api/registro en app.py) y el comando de voz «limpiar registro».
    def limpiar(self):
        """Vacía el historial. Los ids siguientes no reutilizan los anteriores."""
        with self._candado:
            # Cuenta cuántos había (para informárselo al usuario).
            cantidad = len(self._eventos)
            # Vacía la lista.
            self._eventos.clear()
            # Los ids viejos quedan «descartados»: así las páginas abiertas saben que deben borrar lo que muestran.
            self._base_id = self._ultimo_id + 1
            return cantidad


# Instancia compartida por toda la aplicación.
# Esta es la que importa app.py: from registro import registro
registro = RegistroEventos()

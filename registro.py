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

import threading
import time
from collections import deque

CAPACIDAD = 200
ORIGENES = ("voz", "regla")
ESTADOS = ("ok", "error", "ignorado")
LARGO_MAXIMO_TEXTO = 200
LARGO_MAXIMO_RESULTADO = 300


class RegistroEventos:
    def __init__(self, capacidad=CAPACIDAD):
        self._eventos = deque(maxlen=capacidad)
        self._candado = threading.Lock()
        self._ultimo_id = 0
        self._base_id = 1  # primer id vigente: los anteriores se limpiaron

    def agregar(self, origen, texto, resultado, estado):
        """Agrega un evento y devuelve una copia del evento guardado."""
        if origen not in ORIGENES:
            raise ValueError(f"Origen de evento no válido: {origen!r}")
        if estado not in ESTADOS:
            raise ValueError(f"Estado de evento no válido: {estado!r}")

        with self._candado:
            self._ultimo_id += 1
            evento = {
                "id": self._ultimo_id,
                "ts": round(time.time(), 3),
                "origen": origen,
                "texto": str(texto)[:LARGO_MAXIMO_TEXTO],
                "resultado": str(resultado)[:LARGO_MAXIMO_RESULTADO],
                "estado": estado,
            }
            self._eventos.append(evento)
            return dict(evento)

    def desde(self, ultimo_visto=0):
        """Eventos posteriores al id indicado (del más viejo al más nuevo)."""
        with self._candado:
            return [dict(e) for e in self._eventos if e["id"] > ultimo_visto]

    def posicion(self):
        """(ultimo_id, base_id) para que cada página sepa qué le falta y qué descartar."""
        with self._candado:
            return self._ultimo_id, self._base_id

    def limpiar(self):
        """Vacía el historial. Los ids siguientes no reutilizan los anteriores."""
        with self._candado:
            cantidad = len(self._eventos)
            self._eventos.clear()
            self._base_id = self._ultimo_id + 1
            return cantidad


# Instancia compartida por toda la aplicación.
registro = RegistroEventos()

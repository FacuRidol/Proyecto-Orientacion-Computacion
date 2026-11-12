# sensor_monitor.py
"""Monitor del sensor ultrasónico: mide en segundo plano y guarda el historial.

Hasta ahora el sensor solo se medía cuando una página lo pedía, lo que tenía dos
problemas: si no había ninguna página abierta nada se medía (y las reglas
automáticas no podían funcionar) y, con varias pestañas, cada una disparaba su
propia medición. Este hilo mide en un único lugar mientras el sensor está activo
y reparte el resultado a todos:

    - guarda las últimas muestras (alimentan el gráfico de distancia),
    - recuerda la última lectura (la usan /api/distancia y «medir distancia»),
    - avisa a las automatizaciones de cada medición nueva.

El hilo es independiente del hardware: recibe por parámetro las funciones para
medir y para saber si el sensor está activo, así que se puede probar sin Raspberry.
"""

import logging
import threading
import time
from collections import deque

registro_logs = logging.getLogger(__name__)

INTERVALO_S = 0.25      # 4 mediciones por segundo
VENTANA_S = 90.0        # cuánto historial se conserva (el gráfico muestra 60 s)
ESPERA_INACTIVO_S = 0.2 # cada cuánto revisa si se activó el sensor


class MonitorSensor:
    def __init__(
        self,
        medir,
        sensor_activo,
        al_medir=None,
        al_desactivar=None,
        intervalo=INTERVALO_S,
        ventana=VENTANA_S,
        reloj=time.time,
    ):
        self._medir = medir
        self._sensor_activo = sensor_activo
        self._al_medir = al_medir
        self._al_desactivar = al_desactivar
        self._intervalo = intervalo
        self._ventana = ventana
        self._reloj = reloj

        # Cada muestra es (momento, centímetros o None si no hubo eco válido).
        capacidad = int(ventana / intervalo * 1.5) + 10
        self._muestras = deque(maxlen=capacidad)
        self._candado = threading.Lock()
        self._parar = threading.Event()
        self._hilo = None
        self._estaba_activo = False

    # ---------- ciclo de vida ----------

    @property
    def corriendo(self):
        return self._hilo is not None and self._hilo.is_alive()

    def iniciar(self):
        """Arranca el hilo. Si ya estaba corriendo, no hace nada."""
        if self.corriendo:
            return
        self._parar.clear()
        self._hilo = threading.Thread(
            target=self._bucle, name="monitor-sensor", daemon=True
        )
        self._hilo.start()

    def detener(self, espera=2.0):
        """Pide al hilo que termine y espera un momento a que lo haga."""
        self._parar.set()
        hilo = self._hilo
        if hilo is not None and hilo.is_alive() and hilo is not threading.current_thread():
            hilo.join(espera)

    # ---------- lectura de datos ----------

    def ahora(self):
        return self._reloj()

    def ultima_muestra(self):
        """(momento, centímetros|None) de la medición más reciente, o None."""
        with self._candado:
            return self._muestras[-1] if self._muestras else None

    def muestras_desde(self, desde=0.0):
        """Muestras posteriores al momento indicado, como listas [momento, cm]."""
        with self._candado:
            return [[ts, cm] for ts, cm in self._muestras if ts > desde]

    # ---------- bucle interno ----------

    def _bucle(self):
        while not self._parar.is_set():
            espera = self._intervalo
            try:
                if self._sensor_activo():
                    self._estaba_activo = True
                    inicio = time.monotonic()
                    self._tomar_muestra()
                    espera = max(0.02, self._intervalo - (time.monotonic() - inicio))
                else:
                    if self._estaba_activo:
                        self._estaba_activo = False
                        if self._al_desactivar:
                            self._al_desactivar()
                    espera = ESPERA_INACTIVO_S
            except Exception:
                # Un error aislado no debe detener las mediciones.
                registro_logs.exception("Error en el monitor del sensor")
                espera = max(espera, 0.5)

            self._parar.wait(espera)

    def _tomar_muestra(self):
        centimetros = self._medir()
        momento = self._reloj()

        with self._candado:
            self._muestras.append((momento, centimetros))
            limite = momento - self._ventana
            while self._muestras and self._muestras[0][0] < limite:
                self._muestras.popleft()

        if self._al_medir:
            self._al_medir(momento, centimetros)

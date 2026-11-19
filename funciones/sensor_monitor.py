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

# ┌─────────────────────────────────────────────────────────────────────────┐
# │ DE QUIÉN DEPENDE / QUIÉN LO USA                                         │
# │ No importa ningún archivo del proyecto: todo lo que necesita (medir,    │
# │ saber si el sensor está activo, avisar a las reglas) se lo entrega      │
# │ app.py por parámetro al crear el MonitorSensor. Así se puede probar sin │
# │ Raspberry.                                                              │
# │   - app.py crea la instancia («monitor») y le pasa:                     │
# │       medir          -> dispositivos.medir_distancia                    │
# │       sensor_activo  -> dispositivos.sensor_esta_activo                 │
# │       al_medir       -> automatizaciones.MotorReglas.procesar_medicion  │
# │       al_desactivar  -> automatizaciones.MotorReglas.reiniciar_estados  │
# │   - app.py lee de acá el historial (monitor.muestras_desde) en          │
# │     GET /api/distancia/historial, que dibuja static/js/grafico.js.      │
# └─────────────────────────────────────────────────────────────────────────┘
# logging: para dejar en el registro de errores del programa cualquier falla inesperada del hilo.
import logging
# threading: crea el hilo de fondo, el candado y la señal de parada.
import threading
# time: relojes (time.time para fechar muestras, time.monotonic para medir duraciones).
import time
# deque: lista con tope de tamaño; al llenarse descarta las muestras más viejas.
from collections import deque

# Objeto con el que este archivo escribe mensajes de error (no tiene relación con registro.py, que es el historial que ve el usuario).
registro_logs = logging.getLogger(__name__)

# Constantes de ritmo: cada cuántos segundos se mide, cuánto historial se guarda y cada cuánto se revisa si el sensor se activó.
INTERVALO_S = 0.25      # 4 mediciones por segundo
VENTANA_S = 90.0        # cuánto historial se conserva (el gráfico muestra 60 s)
ESPERA_INACTIVO_S = 0.2 # cada cuánto revisa si se activó el sensor


# Clase que corre un hilo en segundo plano midiendo la distancia mientras el sensor está activo.
class MonitorSensor:
    # Constructor: recibe las funciones externas (medir, sensor_activo, al_medir, al_desactivar) y los tiempos. Nada se mide hasta llamar a iniciar().
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
        # Guarda las funciones recibidas para usarlas más tarde (se las pasó app.py).
        self._medir = medir
        self._sensor_activo = sensor_activo
        self._al_medir = al_medir
        self._al_desactivar = al_desactivar
        self._intervalo = intervalo
        self._ventana = ventana
        self._reloj = reloj

        # Calcula cuántas muestras caben en la ventana de historial (con margen del 50 %).
        # Cada muestra es (momento, centímetros o None si no hubo eco válido).
        capacidad = int(ventana / intervalo * 1.5) + 10
        self._muestras = deque(maxlen=capacidad)
        # Candado: el hilo escribe muestras y las peticiones web las leen al mismo tiempo.
        # La señal «_parar» le avisa al hilo que debe terminar; «_hilo» guarda el hilo; «_estaba_activo» detecta cuándo el sensor se apaga.
        self._candado = threading.Lock()
        self._parar = threading.Event()
        self._hilo = None
        self._estaba_activo = False

    # Inicio y parada del hilo.
    # ---------- ciclo de vida ----------

    # Propiedad: se usa como atributo (monitor.corriendo, sin paréntesis). app.py la consulta en /api/distancia/historial.
    @property
    def corriendo(self):
        return self._hilo is not None and self._hilo.is_alive()

    # Arranca el hilo de medición. Lo llama app.py en iniciar_servicios() al encender la aplicación.
    def iniciar(self):
        """Arranca el hilo. Si ya estaba corriendo, no hace nada."""
        if self.corriendo:
            return
        # Baja la señal de parada por si el hilo se había detenido antes.
        # Crea un hilo «daemon» (se cierra solo con el programa) que ejecuta _bucle, y lo pone en marcha.
        self._parar.clear()
        self._hilo = threading.Thread(
            target=self._bucle, name="monitor-sensor", daemon=True
        )
        self._hilo.start()

    # Pide al hilo que termine. app.py lo registra con atexit para cerrarlo ordenadamente.
    def detener(self, espera=2.0):
        """Pide al hilo que termine y espera un momento a que lo haga."""
        self._parar.set()
        hilo = self._hilo
        if hilo is not None and hilo.is_alive() and hilo is not threading.current_thread():
            hilo.join(espera)

    # Métodos que usa app.py para consultar lo medido.
    # ---------- lectura de datos ----------

    # Hora actual según el reloj del monitor (app.py la envía a la página para sincronizar el gráfico).
    def ahora(self):
        return self._reloj()

    # Devuelve la medición más reciente. La usa app.py (distancia actual y comando «medir distancia»).
    def ultima_muestra(self):
        """(momento, centímetros|None) de la medición más reciente, o None."""
        with self._candado:
            return self._muestras[-1] if self._muestras else None

    # Devuelve las muestras más nuevas que un momento dado; static/js/grafico.js las pide así para no repetir datos.
    def muestras_desde(self, desde=0.0):
        """Muestras posteriores al momento indicado, como listas [momento, cm]."""
        with self._candado:
            return [[ts, cm] for ts, cm in self._muestras if ts > desde]

    # Lo que hace el hilo.
    # ---------- bucle interno ----------

    # Bucle principal del hilo: se repite hasta que alguien pida parar.
    def _bucle(self):
        while not self._parar.is_set():
            # Por defecto espera un intervalo entre una vuelta y la siguiente.
            # Si el sensor está activo: lo recuerda, toma una muestra y descuenta de la espera lo que tardó la medición para mantener el ritmo.
            espera = self._intervalo
            try:
                if self._sensor_activo():
                    self._estaba_activo = True
                    inicio = time.monotonic()
                    self._tomar_muestra()
                    espera = max(0.02, self._intervalo - (time.monotonic() - inicio))
                # Sensor apagado: si recién se apagó, avisa a las reglas (al_desactivar) para que reinicien su estado, y revisa cada tanto si se vuelve a activar.
                else:
                    if self._estaba_activo:
                        self._estaba_activo = False
                        if self._al_desactivar:
                            self._al_desactivar()
                    espera = ESPERA_INACTIVO_S
            # Un fallo suelto no debe frenar el hilo: se anota el error en el log y se espera un poco más antes de reintentar.
            except Exception:
                # Un error aislado no debe detener las mediciones.
                registro_logs.exception("Error en el monitor del sensor")
                espera = max(espera, 0.5)

            # Duerme «espera» segundos, pero se despierta enseguida si piden parar (a diferencia de time.sleep).
            self._parar.wait(espera)

    # Hace UNA medición y la guarda.
    def _tomar_muestra(self):
        # Llama a la función de medir (dispositivos.medir_distancia, entregada por app.py).
        # Guarda la muestra y descarta las que quedaron fuera de la ventana de historial.
        centimetros = self._medir()
        momento = self._reloj()

        with self._candado:
            self._muestras.append((momento, centimetros))
            limite = momento - self._ventana
            while self._muestras and self._muestras[0][0] < limite:
                self._muestras.popleft()

        # Avisa a quien escucha (automatizaciones.MotorReglas.procesar_medicion) para que evalúe las reglas con este valor.
        if self._al_medir:
            self._al_medir(momento, centimetros)

# servidor/servicios.py
"""Servicios compartidos: las instancias ÚNICAS que usan todas las rutas y comandos.

QUÉ HACE
 - Crea, una sola vez y en el orden correcto, los objetos que mantienen estado:
     nombres_leds .. nombres de los LED (nombres_leds.py).
     asistente ..... modo, palabras de activación y sesión (asistente.py).
     motor_reglas .. reglas «si la distancia es menor a X...» (automatizaciones.py).
     monitor ....... hilo que mide la distancia en segundo plano (sensor_monitor.py).
   El historial de eventos («registro») y el hardware («hw») vienen de sus propios archivos.
 - iniciar_servicios(): arranca el hilo de medición.
 - leer_distancia(): la distancia más reciente.

POR QUÉ ES UN MÓDULO APARTE
 Las rutas (servidor/rutas/) y los intérpretes de voz (servidor/comandos/) necesitan los
 MISMOS objetos. Python carga cada módulo una sola vez, así que importar «servicios» desde
 cualquier lado entrega siempre las mismas instancias.

QUIÉN LO USA: servidor/rutas/, servidor/comandos/ y app.py.
"""
import atexit

# Archivo funciones/dispositivos.py (hardware). Se usa como «hw»: hw.controlar_led(...), hw.mover_servo(...), etc.
from funciones import dispositivos as hw
# Archivo funciones/registro.py: objeto «registro» (historial de eventos).
from funciones.registro import registro
# Archivo funciones/automatizaciones.py: motor de reglas y la función que ejecuta acciones.
from funciones.automatizaciones import MotorReglas, ejecutar_en_hardware
# Archivo funciones/nombres_leds.py: guarda y busca los nombres de los LED.
from funciones.nombres_leds import NombresLeds
# Archivo funciones/asistente.py: modo, palabras de activación editables y sesión (despierto/dormido).
from funciones.asistente import Asistente
# Archivo funciones/sensor_monitor.py: hilo que mide la distancia en segundo plano.
from funciones.sensor_monitor import MonitorSensor

from . import config, palabras_inicio
from .texto import normalizar
from .validaciones import crear_revisor_de_palabras, revisar_nombre_de_led

# ==========================================
# NOMBRES DE LOS LED
# ==========================================
# Desde la página se le puede poner nombre a cada LED («LED 1» -> «cocina»). Ese nombre es
# también el que se dice por voz. Se guardan en datos/nombres_leds.json.
nombres_leds = NombresLeds(
    leds_validos=tuple(hw.LED_PINS),
    normalizar=normalizar,
    ruta=config.CARPETA_DATOS / "nombres_leds.json",
    revisar=revisar_nombre_de_led,
)


def nombre_led(numero):
    """Nombre actual de un LED: el que eligió la persona o «LED 1», «LED 2»..."""
    return nombres_leds.obtener(numero)


# ==========================================
# ASISTENTE
# ==========================================
# Guarda en datos/configuracion.json el modo, las palabras de activación y el tiempo de espera, y mantiene
# la sesión despierto/dormido en memoria.
asistente = Asistente(
    palabras_por_defecto=config.PALABRAS_DE_INICIO,
    normalizar=normalizar,
    ruta=config.CARPETA_DATOS / "configuracion.json",
    revisar=crear_revisor_de_palabras(nombres_leds),
)
# Ahora que se pueden leer las palabras guardadas, se activan (reemplazan a las de fábrica del arranque).
palabras_inicio.aplicar_palabras_de_inicio(asistente.palabras())

# ==========================================
# AUTOMATIZACIONES Y SENSOR
# ==========================================
# Motor de reglas. Recibe: la función que ejecuta acciones en el hardware, qué LED existen, dónde
# guardar las reglas (datos/automatizaciones.json), cómo anotar eventos y cómo obtener el nombre de un LED.
motor_reglas = MotorReglas(
    ejecutar=ejecutar_en_hardware,
    leds_validos=tuple(hw.LED_PINS),
    ruta=config.CARPETA_DATOS / "automatizaciones.json",
    registrar=registro.agregar,
    nombre_led=nombre_led,
)

# Hilo de medición. Cada medición se la pasa al motor de reglas (al_medir) y, si el sensor se apaga,
# las reglas se reinician (al_desactivar). Todavía NO arranca: eso ocurre en iniciar_servicios().
monitor = MonitorSensor(
    medir=hw.medir_distancia,
    sensor_activo=hw.sensor_esta_activo,
    al_medir=motor_reglas.procesar_medicion,
    al_desactivar=motor_reglas.reiniciar_estados,
)

# Bandera para arrancar los servicios una sola vez.
_servicios_iniciados = False


def iniciar_servicios():
    """Arranca el monitor del sensor. Se llama una vez al iniciar la aplicación."""
    global _servicios_iniciados
    if _servicios_iniciados:
        return
    _servicios_iniciados = True
    # Pone en marcha el hilo de sensor_monitor.py.
    monitor.iniciar()
    # Se registra después de dispositivos.py, así que al cerrar se ejecuta antes
    # que la liberación de los GPIO: el hilo termina antes de soltar los pines.
    atexit.register(monitor.detener)


def leer_distancia():
    """Distancia más reciente en cm (None si no hay lectura válida).

    Con el monitor activo se usa su última medición, para no medir dos veces ni
    pelear por el sensor. Si el monitor no está corriendo (por ejemplo, al
    probar el código fuera de la aplicación) se mide directamente, como antes.
    """
    if monitor.corriendo:
        muestra = monitor.ultima_muestra()
        if muestra is not None and monitor.ahora() - muestra[0] <= config.MUESTRA_VIGENTE_S:
            return muestra[1]
        return None
    return hw.medir_distancia()

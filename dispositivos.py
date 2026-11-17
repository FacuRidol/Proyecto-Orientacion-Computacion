# dispositivos.py
#
# ┌─────────────────────────────────────────────────────────────────────────┐
# │ QUÉ HACE ESTE ARCHIVO                                                   │
# │ Es la ÚNICA capa que toca el hardware de la Raspberry Pi: los 4 LED, el │
# │ servomotor SG90 y el sensor ultrasónico HC-SR04. El resto del proyecto  │
# │ nunca usa los pines directamente: le pide las cosas a este módulo.      │
# │                                                                         │
# │ QUÉ ARCHIVOS LO USAN                                                    │
# │   - app.py: lo importa como «hw» (import dispositivos as hw) y llama a  │
# │     hw.controlar_led, hw.mover_servo, hw.medir_distancia, etc. desde    │
# │     las rutas web y desde los comandos de voz.                          │
# │   - automatizaciones.py: su función ejecutar_en_hardware() recibe este  │
# │     módulo por parámetro para cumplir las acciones de las reglas.       │
# │   - sensor_monitor.py: recibe hw.medir_distancia y hw.sensor_esta_activo│
# │     por parámetro (no lo importa), así que puede probarse sin hardware. │
# │                                                                         │
# │ QUÉ LIBRERÍA EXTERNA USA                                                │
# │   - RPi.GPIO (viene con Raspberry Pi OS): controla los pines físicos.   │
# └─────────────────────────────────────────────────────────────────────────┘

# atexit: permite registrar una función que Python ejecuta sola al cerrar el programa.
import atexit
# threading: se usa para crear el candado (RLock) que evita que dos peticiones toquen el hardware a la vez.
import threading
# time: para las pausas cortas (esperar que el servo llegue, generar el pulso del sensor).
import time

# Librería de la Raspberry que controla los pines GPIO; se la llama «GPIO» por comodidad.
import RPi.GPIO as GPIO


# ==========================================
# CONFIGURACION
# ==========================================

# Tabla que une el número de cada LED (el que ve el usuario) con su pin GPIO físico.
# Para agregar un LED nuevo basta con sumar una línea acá (app.py y la página lo detectan solos).
# Identificador del LED: GPIO BCM
LED_PINS = {
    1: 17,
    2: 27,
    3: 22,
    4: 23,
}

# Pin donde está conectado el cable de señal del servomotor (PWM).
SERVO_PIN = 18

# Pines del sensor HC-SR04: TRIG envía el pulso de sonido y ECHO escucha el rebote.
TRIG_PIN = 24
ECHO_PIN = 25

# Memoria del último estado conocido de cada LED. Se arma a partir de LED_PINS: todos empiezan apagados (False).
# Estado inicial de cada LED
estados_led = {
    numero: False
    for numero in LED_PINS
}

# Posición actual del servo en grados (arranca en el centro, 90°).
angulo_servo = 90
# Indica si el usuario encendió la medición del sensor. Mientras sea False, medir_distancia() no hace nada.
sensor_activo = False

# Candado compartido. Flask atiende varias peticiones a la vez (hilos); con este candado
# solo una por vez puede mover pines, y así no se mezclan órdenes. RLock permite que la
# misma función se vuelva a bloquear a sí misma sin trabarse (por ejemplo obtener_estado).
# Protege las operaciones de hardware
bloqueo = threading.RLock()


# ==========================================
# INICIALIZACION
# ==========================================
# Este bloque se ejecuta UNA sola vez, en el momento en que app.py hace «import dispositivos».

# Le indica a RPi.GPIO que los números de pin que usamos son los de la numeración BCM (la de los GPIO), no los de posición física.
GPIO.setmode(GPIO.BCM)
# Silencia los avisos de «el canal ya estaba en uso» (pasa si el programa se reinicia sin cerrar bien).
GPIO.setwarnings(False)

# Configura cada pin de LED como salida y lo deja apagado (LOW) al arrancar.
for pin in LED_PINS.values():
    GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

# El pin del servo es una salida...
GPIO.setup(SERVO_PIN, GPIO.OUT)
# ...sobre la que se genera una señal PWM de 50 Hz (la frecuencia que esperan los servos SG90).
servo_pwm = GPIO.PWM(SERVO_PIN, 50)
# Se inicia el PWM con ciclo 0 (sin pulsos): el servo queda quieto y sin «temblar».
servo_pwm.start(0)

# TRIG es salida (nosotros enviamos el pulso) y arranca en LOW; ECHO es entrada (leemos el rebote).
GPIO.setup(TRIG_PIN, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(ECHO_PIN, GPIO.IN)

# Pequeña pausa para que todo se estabilice antes de recibir la primera orden.
time.sleep(0.1)


# ==========================================
# LEDS
# ==========================================

# Enciende o apaga UN LED. Lo llaman app.py (ruta /api/led y comandos de voz) y
# automatizaciones.ejecutar_en_hardware (reglas). Devuelve el estado en que quedó.
def controlar_led(numero, encender):
    # Acepta «3» o 3 y lo convierte a entero.
    numero = int(numero)

    # Si el número no está en la tabla de LED_PINS se avisa con un error; app.py lo convierte en un mensaje al usuario.
    if numero not in LED_PINS:
        raise ValueError("El LED solicitado no existe.")

    # Se toma el candado: mientras dura el bloque nadie más toca el hardware.
    with bloqueo:
        # Pone el pin en nivel alto (3,3 V = LED encendido) o bajo (0 V = apagado).
        GPIO.output(
            LED_PINS[numero],
            GPIO.HIGH if encender else GPIO.LOW
        )

        # Anota el nuevo estado en la memoria.
        estados_led[numero] = bool(encender)

    # Informa en qué estado quedó el LED (True = encendido).
    return estados_led[numero]


# Invierte un LED (si estaba encendido lo apaga y viceversa). Lo usa app.py en /api/led/<n>/alternar,
# que es lo que llama el botón único «Encender / Apagar» de cada tarjeta (static/js/voz.js).
def alternar_led(numero):
    """Invierte el LED consultando su salida actual, de forma atómica."""
    # Convierte el número a entero.
    numero = int(numero)
    # Mismo control de existencia que en controlar_led.
    if numero not in LED_PINS:
        raise ValueError("El LED solicitado no existe.")

    # Leer y escribir dentro del mismo candado evita que otra petición cambie el LED entre medio.
    with bloqueo:
        # Leer el pin evita depender de un estado viejo de la interfaz.
        # Lee el nivel real del pin (True si está encendido).
        estado_actual = bool(GPIO.input(LED_PINS[numero]))
        # El nuevo estado es el contrario del actual.
        nuevo_estado = not estado_actual
        # Aplica el nuevo nivel al pin.
        GPIO.output(
            LED_PINS[numero],
            GPIO.HIGH if nuevo_estado else GPIO.LOW
        )
        # Actualiza la memoria.
        estados_led[numero] = nuevo_estado
        # Devuelve el estado final para que la página lo muestre.
        return nuevo_estado


# Enciende o apaga los 4 LED juntos. Lo llaman app.py (/api/leds/todos y «apagar todo»
# / «encender todas las leds» por voz) y automatizaciones.ejecutar_en_hardware.
def controlar_todos_leds(encender):
    """Enciende o apaga todos los LED dentro de una sola sección protegida.

    Al hacerlo bajo el bloqueo, ninguna otra petición puede ver un estado
    intermedio (por ejemplo, dos LED encendidos y dos apagados).
    Devuelve una copia del estado de todos los LED: {numero: encendido}.
    """
    # Un único candado para los cuatro: la operación es «todo o nada» a ojos del resto.
    with bloqueo:
        # Recorre cada LED con su pin...
        for numero, pin in LED_PINS.items():
            # ...y le pone el mismo nivel a todos.
            GPIO.output(pin, GPIO.HIGH if encender else GPIO.LOW)
            # Actualiza la memoria de cada uno.
            estados_led[numero] = bool(encender)

        # Devuelve una COPIA del diccionario (dict(...)) para que quien la reciba no pueda alterar la memoria interna.
        return dict(estados_led)


# Lee de verdad el estado de los pines. Lo usa obtener_estado() de más abajo, que a su
# vez alimenta /api/estado en app.py (la página lo consulta una vez por segundo).
def obtener_leds():
    """Lee el estado actual de las salidas GPIO de los LED."""
    # Candado para no leer a mitad de una escritura.
    with bloqueo:
        # Diccionario nuevo donde se juntan los estados leídos.
        estados_actuales = {}
        # Recorre los 4 LED.
        for numero, pin in LED_PINS.items():
            try:
                # En un pin configurado como salida, GPIO.input permite leer
                # el nivel lógico que está presente en esa salida.
                # Lee el nivel del pin (True = encendido).
                estado = bool(GPIO.input(pin))
                # Sincroniza la memoria con lo leído.
                estados_led[numero] = estado
            except Exception:
                # Si la lectura falla, conservar el último estado registrado.
                estado = bool(estados_led.get(numero, False))
            # Guarda el estado de este LED en el resultado.
            estados_actuales[numero] = estado
        # Devuelve {1: True, 2: False, ...}.
        return estados_actuales


# ==========================================
# SERVOMOTOR
# ==========================================

# Mueve el servo a un ángulo entre 0° y 180°. Lo llaman app.py (/api/servo y los comandos
# «giro a 90 grados» / «giro al centro») y automatizaciones.ejecutar_en_hardware.
def mover_servo(angulo):
    # «angulo_servo» es una variable de módulo; global permite modificarla desde dentro de la función.
    global angulo_servo

    # Convierte a entero (acepta «90» o 90).
    angulo = int(angulo)

    # Rechaza valores fuera del rango físico del servo.
    if not 0 <= angulo <= 180:
        raise ValueError("El ángulo debe estar entre 0 y 180.")

    # Convierte grados a «ciclo de trabajo» del PWM: 0° ≈ 2,5 % y 180° ≈ 12,5 %.
    # Aproximacion inicial para un SG90.
    # Puede requerir calibracion segun el servo.
    ciclo = 2.5 + (angulo / 18.0)

    # Candado: el movimiento dura 0,5 s y nadie debe interrumpirlo.
    with bloqueo:
        # Envía al servo la señal que lo lleva hasta ese ángulo.
        servo_pwm.ChangeDutyCycle(ciclo)

        # Tiempo para que el servo se aproxime
        # a la posicion solicitada.
        # Espera medio segundo a que el servo llegue.
        time.sleep(0.5)

        # Corta la señal (ciclo 0) para que el servo no vibre ni se caliente.
        servo_pwm.ChangeDutyCycle(0)

        # Recuerda la nueva posición.
        angulo_servo = angulo

    # Devuelve el ángulo en que quedó.
    return angulo_servo


# Devuelve el último ángulo pedido. Lo usa obtener_estado() (y por lo tanto /api/estado).
def obtener_angulo_servo():
    # Candado porque otra petición podría estar moviendo el servo justo ahora.
    with bloqueo:
        return angulo_servo


# ==========================================
# SENSOR ULTRASONICO HC-SR04
# ==========================================

# Enciende o pausa el sensor. Lo llaman app.py (/api/sensor y «activar/desactivar sensor» por voz).
def configurar_sensor(activo):
    """Activa o pausa las mediciones del sensor ultrasónico."""
    # Se va a modificar la variable de módulo sensor_activo.
    global sensor_activo
    # Candado para que el cambio sea ordenado respecto de las mediciones.
    with bloqueo:
        # Guarda True/False.
        sensor_activo = bool(activo)
        # Devuelve el estado final.
        return sensor_activo


# Responde si el sensor está activo. Lo usa sensor_monitor.py (para saber si debe medir) y app.py.
def sensor_esta_activo():
    # Lee la variable bajo candado.
    with bloqueo:
        return sensor_activo


# Hace UNA medición de distancia y devuelve centímetros (o None si falló o el sensor está pausado).
# Quien la llama sin parar, 4 veces por segundo, es sensor_monitor.py (hilo en segundo plano).
def medir_distancia():
    # Candado: el pulso es muy sensible al tiempo y no puede cortarse a la mitad.
    with bloqueo:
        # Si el sensor está pausado no se mide: se devuelve None («sin dato»).
        if not sensor_activo:
            return None
        # Asegura que TRIG empiece en bajo...
        GPIO.output(TRIG_PIN, GPIO.LOW)
        # ...durante 2 microsegundos.
        time.sleep(0.000002)

        # Envía el pulso de disparo: TRIG en alto durante 10 microsegundos y luego bajo.
        GPIO.output(TRIG_PIN, GPIO.HIGH)
        time.sleep(0.000010)
        GPIO.output(TRIG_PIN, GPIO.LOW)

        # Reloj para no quedarse esperando para siempre si el sensor no responde.
        inicio_espera = time.monotonic()

        # Esperar el comienzo del pulso ECHO
        # Mientras ECHO siga en bajo, todavía no volvió el rebote.
        while GPIO.input(ECHO_PIN) == GPIO.LOW:
            # Si pasaron más de 30 ms sin respuesta, se abandona la medición.
            if time.monotonic() - inicio_espera > 0.03:
                return None

        # Marca el instante en que ECHO subió: empieza a contarse el viaje del sonido.
        inicio = time.monotonic()

        # Esperar el final del pulso ECHO
        # Mientras ECHO siga en alto, el sonido todavía está «volviendo».
        while GPIO.input(ECHO_PIN) == GPIO.HIGH:
            # Otro límite de 30 ms para no colgar el programa.
            if time.monotonic() - inicio > 0.03:
                return None

        # Marca el instante en que ECHO bajó: terminó el rebote.
        fin = time.monotonic()

    # Tiempo total que el sonido tardó en ir y volver (en segundos).
    duracion = fin - inicio

    # Velocidad aproximada del sonido:
    # 34300 cm/s. Se divide por dos porque
    # el sonido va hasta el objeto y regresa.
    # Distancia = tiempo × velocidad ÷ 2.
    distancia = duracion * 34300 / 2

    # El HC-SR04 solo es confiable entre 2 y 400 cm; fuera de eso se descarta la lectura.
    if not 2 <= distancia <= 400:
        return None

    # Se redondea a un decimal (por ejemplo 23.4 cm).
    return round(distancia, 1)


# ==========================================
# ESTADO GENERAL
# ==========================================

# Foto completa del hardware: es lo que app.py entrega en GET /api/estado
# y lo que static/js/voz.js usa para mantener todas las pestañas sincronizadas.
def obtener_estado():
    return {
        # Estado de cada LED leído de los pines.
        "leds": obtener_leds(),
        # Último ángulo del servo.
        "servo": obtener_angulo_servo(),
        # Si el sensor está encendido.
        "sensor_activo": sensor_esta_activo(),
    }


# ==========================================
# CIERRE DEL HARDWARE
# ==========================================

# Libera los pines al cerrar el programa. Se ejecuta sola gracias a atexit.register (abajo).
def cerrar_hardware():
    # Candado por si todavía hay una operación en curso.
    with bloqueo:
        try:
            # Detiene la señal PWM del servo...
            servo_pwm.stop()
            # ...y deja todos los pines en su estado original (entrada, sin energía).
            GPIO.cleanup()
        except Exception:
            # Si algo falla al cerrar no importa: el programa ya se está cerrando.
            pass


# Le pide a Python que llame a cerrar_hardware() automáticamente cuando el programa termine.
atexit.register(cerrar_hardware)

# dispositivos.py

import atexit
import threading
import time

import RPi.GPIO as GPIO


# ==========================================
# CONFIGURACION
# ==========================================

# Identificador del LED: GPIO BCM
LED_PINS = {
    1: 17,
    2: 27,
    3: 22,
    4: 23,
}

SERVO_PIN = 18

TRIG_PIN = 24
ECHO_PIN = 25

# Estado inicial de cada LED
estados_led = {
    numero: False
    for numero in LED_PINS
}

angulo_servo = 90

# Protege las operaciones de hardware
bloqueo = threading.RLock()


# ==========================================
# INICIALIZACION
# ==========================================

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

for pin in LED_PINS.values():
    GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

GPIO.setup(SERVO_PIN, GPIO.OUT)
servo_pwm = GPIO.PWM(SERVO_PIN, 50)
servo_pwm.start(0)

GPIO.setup(TRIG_PIN, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(ECHO_PIN, GPIO.IN)

time.sleep(0.1)


# ==========================================
# LEDS
# ==========================================

def controlar_led(numero, encender):
    numero = int(numero)

    if numero not in LED_PINS:
        raise ValueError("El LED solicitado no existe.")

    with bloqueo:
        GPIO.output(
            LED_PINS[numero],
            GPIO.HIGH if encender else GPIO.LOW
        )

        estados_led[numero] = bool(encender)

    return estados_led[numero]


def obtener_leds():
    with bloqueo:
        return {
            numero: estado
            for numero, estado in estados_led.items()
        }


# ==========================================
# SERVOMOTOR
# ==========================================

def mover_servo(angulo):
    global angulo_servo

    angulo = int(angulo)

    if not 0 <= angulo <= 180:
        raise ValueError("El ángulo debe estar entre 0 y 180.")

    # Aproximacion inicial para un SG90.
    # Puede requerir calibracion segun el servo.
    ciclo = 2.5 + (angulo / 18.0)

    with bloqueo:
        servo_pwm.ChangeDutyCycle(ciclo)

        # Tiempo para que el servo se aproxime
        # a la posicion solicitada.
        time.sleep(0.5)

        servo_pwm.ChangeDutyCycle(0)

        angulo_servo = angulo

    return angulo_servo


def obtener_angulo_servo():
    with bloqueo:
        return angulo_servo


# ==========================================
# SENSOR ULTRASONICO HC-SR04
# ==========================================

def medir_distancia():
    with bloqueo:
        GPIO.output(TRIG_PIN, GPIO.LOW)
        time.sleep(0.000002)

        GPIO.output(TRIG_PIN, GPIO.HIGH)
        time.sleep(0.000010)
        GPIO.output(TRIG_PIN, GPIO.LOW)

        inicio_espera = time.monotonic()

        # Esperar el comienzo del pulso ECHO
        while GPIO.input(ECHO_PIN) == GPIO.LOW:
            if time.monotonic() - inicio_espera > 0.03:
                return None

        inicio = time.monotonic()

        # Esperar el final del pulso ECHO
        while GPIO.input(ECHO_PIN) == GPIO.HIGH:
            if time.monotonic() - inicio > 0.03:
                return None

        fin = time.monotonic()

    duracion = fin - inicio

    # Velocidad aproximada del sonido:
    # 34300 cm/s. Se divide por dos porque
    # el sonido va hasta el objeto y regresa.
    distancia = duracion * 34300 / 2

    if not 2 <= distancia <= 400:
        return None

    return round(distancia, 1)


# ==========================================
# ESTADO GENERAL
# ==========================================

def obtener_estado():
    return {
        "leds": obtener_leds(),
        "servo": obtener_angulo_servo()
    }


# ==========================================
# CIERRE DEL HARDWARE
# ==========================================

def cerrar_hardware():
    with bloqueo:
        try:
            servo_pwm.stop()
            GPIO.cleanup()
        except Exception:
            pass


atexit.register(cerrar_hardware)
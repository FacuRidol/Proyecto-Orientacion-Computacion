# automatizaciones.py
"""Reglas automáticas: «si la distancia es menor a 20 cm, encender el LED 1».

Una regla tiene una condición sobre la distancia medida por el sensor
(menor o mayor que un umbral en centímetros) y una acción sobre un dispositivo:

    {"tipo": "led",  "led": 1, "encender": True}   encender o apagar un LED
    {"tipo": "leds", "encender": False}            encender o apagar todos los LED
    {"tipo": "servo", "angulo": 90}                mover el servo a un ángulo

La regla se dispara cuando la condición empieza a cumplirse (no en cada
medición). Para evitar disparos falsos por el ruido del sensor se usan tres
protecciones:

    CONFIRMACIONES   la condición debe cumplirse en varias mediciones seguidas
    HISTERESIS_CM    para volver a armarse, la distancia debe alejarse del
                     umbral esa cantidad de centímetros
    ENFRIAMIENTO_S   tiempo mínimo entre dos disparos de la misma regla

Las reglas se guardan en un archivo JSON, así que sobreviven a un reinicio. Se
evalúan solo mientras el sensor está activo (las alimenta sensor_monitor.py).

Este módulo no usa el hardware directamente: recibe la función que ejecuta las
acciones, de modo que se puede probar sin Raspberry.
"""

import json
import logging
import math
import os
import threading
from pathlib import Path

registro_logs = logging.getLogger(__name__)

UMBRAL_MIN_CM = 2       # alcance mínimo del HC-SR04
UMBRAL_MAX_CM = 400     # alcance máximo del HC-SR04
MAX_REGLAS = 8
CONFIRMACIONES = 2      # a 4 mediciones por segundo, unos 0,5 s
HISTERESIS_CM = 2.0
ENFRIAMIENTO_S = 2.0
CONDICIONES = ("menor", "mayor")


class ErrorDeRegla(ValueError):
    """Error de validación con un mensaje pensado para mostrarse al usuario."""


# ==========================================
# VALIDACION Y DESCRIPCION
# ==========================================

def _entero(valor):
    """Devuelve un entero si el valor lo es (o es un texto con dígitos); si no, None."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    if isinstance(valor, str) and valor.strip().isdigit():
        return int(valor.strip())
    return None


def validar_umbral(valor):
    if isinstance(valor, bool):
        raise ErrorDeRegla("La distancia debe ser un número.")
    try:
        umbral = float(valor)
    except (TypeError, ValueError):
        raise ErrorDeRegla("La distancia debe ser un número.") from None
    if not math.isfinite(umbral):
        raise ErrorDeRegla("La distancia debe ser un número.")
    if not UMBRAL_MIN_CM <= umbral <= UMBRAL_MAX_CM:
        raise ErrorDeRegla(
            f"La distancia debe estar entre {UMBRAL_MIN_CM} y {UMBRAL_MAX_CM} cm."
        )
    umbral = round(umbral, 1)
    return int(umbral) if umbral == int(umbral) else umbral


def validar_accion(accion, leds_validos):
    """Devuelve la acción normalizada o lanza ErrorDeRegla."""
    if not isinstance(accion, dict):
        raise ErrorDeRegla("Falta indicar qué hacer cuando se cumpla la regla.")

    tipo = accion.get("tipo")

    if tipo in ("led", "leds"):
        encender = accion.get("encender")
        if not isinstance(encender, bool):
            raise ErrorDeRegla("Indicá si la regla enciende o apaga.")
        if tipo == "leds":
            return {"tipo": "leds", "encender": encender}

        led = _entero(accion.get("led"))
        if led is None or led not in leds_validos:
            raise ErrorDeRegla(f"El LED {accion.get('led')} no existe.")
        return {"tipo": "led", "led": led, "encender": encender}

    if tipo == "servo":
        angulo = _entero(accion.get("angulo"))
        if angulo is None or not 0 <= angulo <= 180:
            raise ErrorDeRegla("El ángulo del servo debe ser un entero entre 0 y 180.")
        return {"tipo": "servo", "angulo": angulo}

    raise ErrorDeRegla("Acción no válida.")


def _formato_cm(umbral):
    return str(int(umbral)) if float(umbral).is_integer() else f"{umbral:.1f}"


def _nombre_de_fabrica(numero):
    return f"LED {numero}"


def describir_accion(accion, nombre_led=None):
    """Texto de una acción. nombre_led(numero) da el nombre actual del LED."""
    nombre_led = nombre_led or _nombre_de_fabrica
    if accion["tipo"] == "led":
        verbo = "Encender" if accion["encender"] else "Apagar"
        return f"{verbo} {nombre_led(accion['led'])}"
    if accion["tipo"] == "leds":
        verbo = "Encender" if accion["encender"] else "Apagar"
        return f"{verbo} todos los LED"
    return f"Mover el servo a {accion['angulo']}°"


def describir_condicion(condicion, umbral):
    comparador = "menor" if condicion == "menor" else "mayor"
    return f"la distancia es {comparador} a {_formato_cm(umbral)} cm"


def describir_regla(regla, nombre_led=None):
    condicion = describir_condicion(regla["condicion"], regla["umbral_cm"])
    return f"Si {condicion} → {describir_accion(regla['accion'], nombre_led)}"


def ejecutar_en_hardware(accion):
    """Ejecuta una acción sobre los dispositivos reales (importa el hardware al usarse)."""
    import dispositivos as hw

    if accion["tipo"] == "led":
        hw.controlar_led(accion["led"], accion["encender"])
    elif accion["tipo"] == "leds":
        hw.controlar_todos_leds(accion["encender"])
    else:
        hw.mover_servo(accion["angulo"])


# ==========================================
# MOTOR DE REGLAS
# ==========================================

class MotorReglas:
    def __init__(self, ejecutar, leds_validos, ruta=None, registrar=None, nombre_led=None):
        """
        ejecutar      función que realiza una acción sobre los dispositivos
        leds_validos  números de LED que existen
        ruta          archivo JSON donde se guardan las reglas (None = no guardar)
        registrar     función (origen, texto, resultado, estado) para el registro
        nombre_led    función numero -> nombre actual del LED, para describir las
                      reglas («Encender cocina»). Se consulta cada vez que se
                      describe una regla, así que un cambio de nombre se nota
                      enseguida. None = «LED 1», «LED 2»...
        """
        self._ejecutar = ejecutar
        self._leds_validos = tuple(leds_validos)
        self._ruta = Path(ruta) if ruta else None
        self._registrar = registrar
        self._nombre_led = nombre_led
        self._candado = threading.RLock()
        self._reglas = []
        self._pausadas = False
        self._cargar()

    # ---------- consulta ----------

    def _publica(self, regla):
        return {
            "id": regla["id"],
            "condicion": regla["condicion"],
            "umbral_cm": regla["umbral_cm"],
            "accion": dict(regla["accion"]),
            "activa": regla["activa"],
            "cumplida": regla["cumplida"],
            "disparos": regla["disparos"],
            "ultimo_disparo": regla["ultimo_disparo"],
            "descripcion": describir_regla(regla, self._nombre_led),
        }

    def listar(self):
        with self._candado:
            return [self._publica(r) for r in self._reglas]

    @property
    def pausadas(self):
        with self._candado:
            return self._pausadas

    def estado(self):
        """Todo lo que necesita la página: reglas, pausa y límites para el formulario."""
        with self._candado:
            return {
                "pausadas": self._pausadas,
                "reglas": [self._publica(r) for r in self._reglas],
                "maximo": MAX_REGLAS,
                "umbral_min": UMBRAL_MIN_CM,
                "umbral_max": UMBRAL_MAX_CM,
                "leds": list(self._leds_validos),
            }

    def resumen(self):
        """Texto corto con todas las reglas, para responder «comando reglas»."""
        with self._candado:
            if not self._reglas:
                return "No hay reglas creadas."
            partes = [
                f"{r['id']}) {describir_regla(r, self._nombre_led)}{'' if r['activa'] else ' (desactivada)'}"
                for r in self._reglas
            ]
            pausa = " Las reglas están en pausa." if self._pausadas else ""
            cantidad = len(self._reglas)
            titulo = "Hay 1 regla" if cantidad == 1 else f"Hay {cantidad} reglas"
            return f"{titulo}: " + "; ".join(partes) + "." + pausa

    # ---------- modificación ----------

    def crear(self, condicion, umbral_cm, accion):
        if condicion not in CONDICIONES:
            raise ErrorDeRegla("La condición debe ser «menor» o «mayor».")
        umbral = validar_umbral(umbral_cm)
        accion = validar_accion(accion, self._leds_validos)

        with self._candado:
            if len(self._reglas) >= MAX_REGLAS:
                raise ErrorDeRegla(
                    f"Ya hay {MAX_REGLAS} reglas. Borrá alguna antes de crear otra."
                )
            for existente in self._reglas:
                if (
                    existente["condicion"] == condicion
                    and existente["umbral_cm"] == umbral
                    and existente["accion"] == accion
                ):
                    raise ErrorDeRegla(f"Ya existe una regla igual (la {existente['id']}).")

            # Se reutiliza el número libre más chico, así «regla uno», «regla dos»…
            # siguen siendo fáciles de decir aunque se hayan borrado reglas.
            usados = {r["id"] for r in self._reglas}
            nuevo_id = next(n for n in range(1, MAX_REGLAS + 1) if n not in usados)

            regla = {
                "id": nuevo_id,
                "condicion": condicion,
                "umbral_cm": umbral,
                "accion": accion,
                "activa": True,
                **self._estado_inicial(),
            }
            self._reglas.append(regla)
            self._reglas.sort(key=lambda r: r["id"])
            self._guardar()
            return self._publica(regla)

    def eliminar(self, id_regla):
        with self._candado:
            antes = len(self._reglas)
            self._reglas = [r for r in self._reglas if r["id"] != id_regla]
            if len(self._reglas) == antes:
                return False
            self._guardar()
            return True

    def eliminar_todas(self):
        with self._candado:
            cantidad = len(self._reglas)
            self._reglas = []
            if cantidad:
                self._guardar()
            return cantidad

    def activar(self, id_regla, activa):
        """Activa o desactiva una regla sin borrarla. Devuelve la regla, o None."""
        with self._candado:
            for regla in self._reglas:
                if regla["id"] == id_regla:
                    regla["activa"] = bool(activa)
                    regla.update(self._estado_inicial(conservar_disparos=regla))
                    self._guardar()
                    return self._publica(regla)
            return None

    def pausar(self, pausadas):
        with self._candado:
            self._pausadas = bool(pausadas)
            self._reiniciar_sin_candado()
            self._guardar()
            return self._pausadas

    # ---------- evaluación ----------

    @staticmethod
    def _estado_inicial(conservar_disparos=None):
        base = {"cumplida": False, "racha": 0, "ultimo_disparo": None, "disparos": 0}
        if conservar_disparos:
            base["ultimo_disparo"] = conservar_disparos["ultimo_disparo"]
            base["disparos"] = conservar_disparos["disparos"]
        return base

    def _reiniciar_sin_candado(self):
        for regla in self._reglas:
            regla["cumplida"] = False
            regla["racha"] = 0

    def reiniciar_estados(self):
        """Se llama al desactivar el sensor: al reactivarlo, las reglas arrancan de cero."""
        with self._candado:
            self._reiniciar_sin_candado()

    @staticmethod
    def _cumple(regla, centimetros):
        """Condición con histéresis: una regla ya cumplida es más tolerante para soltarse."""
        umbral = regla["umbral_cm"]
        if regla["condicion"] == "menor":
            limite = umbral + HISTERESIS_CM if regla["cumplida"] else umbral
            return centimetros < limite
        limite = umbral - HISTERESIS_CM if regla["cumplida"] else umbral
        return centimetros > limite

    def procesar_medicion(self, momento, centimetros):
        """Evalúa todas las reglas con una medición. Devuelve las que se dispararon."""
        if centimetros is None:
            return []  # sin eco válido no hay información: no se cambia nada

        disparadas = []
        with self._candado:
            if self._pausadas:
                self._reiniciar_sin_candado()
                return []

            for regla in self._reglas:
                if not regla["activa"]:
                    regla["cumplida"] = False
                    regla["racha"] = 0
                    continue

                if not self._cumple(regla, centimetros):
                    regla["cumplida"] = False
                    regla["racha"] = 0
                    continue

                if regla["cumplida"]:
                    continue  # ya se disparó y la condición sigue vigente

                regla["racha"] = min(regla["racha"] + 1, CONFIRMACIONES)
                enfriando = (
                    regla["ultimo_disparo"] is not None
                    and momento - regla["ultimo_disparo"] < ENFRIAMIENTO_S
                )
                if regla["racha"] >= CONFIRMACIONES and not enfriando:
                    regla["cumplida"] = True
                    regla["racha"] = 0
                    regla["ultimo_disparo"] = momento
                    regla["disparos"] += 1
                    disparadas.append(self._publica(regla))

        # Las acciones se ejecutan fuera del candado: mover el servo tarda medio
        # segundo y no debe bloquear a quien consulte las reglas mientras tanto.
        for regla in disparadas:
            self._disparar(regla, centimetros)
        return disparadas

    def _disparar(self, regla, centimetros):
        accion = regla["accion"]
        try:
            self._ejecutar(accion)
            estado, resultado = "ok", describir_accion(accion, self._nombre_led)
        except Exception:
            registro_logs.exception("Error al ejecutar la regla %s", regla["id"])
            estado, resultado = "error", f"No se pudo ejecutar: {describir_accion(accion, self._nombre_led)}"

        if self._registrar:
            comparador = "<" if regla["condicion"] == "menor" else ">"
            texto = (
                f"Regla {regla['id']}: {centimetros:.1f} cm "
                f"({comparador} {_formato_cm(regla['umbral_cm'])} cm)"
            )
            try:
                self._registrar("regla", texto, resultado, estado)
            except Exception:
                registro_logs.exception("No se pudo registrar el disparo de la regla")

    # ---------- persistencia ----------

    def _guardar(self):
        if not self._ruta:
            return
        contenido = {
            "version": 1,
            "pausadas": self._pausadas,
            "reglas": [
                {k: r[k] for k in ("id", "condicion", "umbral_cm", "accion", "activa")}
                for r in self._reglas
            ],
        }
        temporal = self._ruta.with_name(self._ruta.name + ".tmp")
        try:
            self._ruta.parent.mkdir(parents=True, exist_ok=True)
            temporal.write_text(
                json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(temporal, self._ruta)  # reemplazo atómico: nunca queda a medias
        except OSError:
            registro_logs.exception("No se pudieron guardar las reglas en %s", self._ruta)

    def _cargar(self):
        if not self._ruta or not self._ruta.exists():
            return
        try:
            datos = json.loads(self._ruta.read_text(encoding="utf-8"))
            reglas = datos.get("reglas", [])
            self._pausadas = bool(datos.get("pausadas", False))
        except (OSError, ValueError, AttributeError):
            registro_logs.warning("No se pudo leer %s; se empieza sin reglas.", self._ruta)
            return

        # El tope de reglas cuenta las válidas: las entradas dañadas no ocupan lugar.
        # Se leen como mucho 100 entradas por si el archivo fue editado a mano.
        for crudo in reglas[:100] if isinstance(reglas, list) else []:
            if len(self._reglas) >= MAX_REGLAS:
                break
            try:
                id_regla = _entero(crudo.get("id"))
                if id_regla is None or not 1 <= id_regla <= MAX_REGLAS:
                    raise ErrorDeRegla("id no válido")
                if crudo.get("condicion") not in CONDICIONES:
                    raise ErrorDeRegla("condición no válida")
                regla = {
                    "id": id_regla,
                    "condicion": crudo["condicion"],
                    "umbral_cm": validar_umbral(crudo.get("umbral_cm")),
                    "accion": validar_accion(crudo.get("accion"), self._leds_validos),
                    "activa": bool(crudo.get("activa", True)),
                    **self._estado_inicial(),
                }
            except (ErrorDeRegla, AttributeError) as error:
                registro_logs.warning("Se omitió una regla guardada no válida: %s", error)
                continue
            if all(r["id"] != regla["id"] for r in self._reglas):
                self._reglas.append(regla)

        self._reglas.sort(key=lambda r: r["id"])

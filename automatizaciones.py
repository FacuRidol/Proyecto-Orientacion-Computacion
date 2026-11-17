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

# ┌─────────────────────────────────────────────────────────────────────────┐
# │ DE QUIÉN DEPENDE / QUIÉN LO USA                                         │
# │ No importa archivos del proyecto al cargarse: el hardware se pide solo  │
# │ dentro de ejecutar_en_hardware() (import dispositivos as hw), y todo lo │
# │ demás (registro de eventos, nombres de LED) llega por parámetro.        │
# │   - app.py crea una instancia de MotorReglas («motor_reglas») pasándole:│
# │       ejecutar   -> ejecutar_en_hardware (de este mismo archivo)        │
# │       registrar  -> registro.agregar (de registro.py: deja constancia   │
# │                     en el panel «Registro de comandos»)                 │
# │       nombre_led -> nombres_leds.obtener (de nombres_leds.py)           │
# │     y usa las reglas desde las rutas /api/reglas* y desde los comandos  │
# │     de voz («si hay algo a menos de...», «reglas», «borrar regla uno»). │
# │   - sensor_monitor.py (creado en app.py) llama a procesar_medicion()    │
# │     con cada medición del sensor y a reiniciar_estados() cuando el      │
# │     sensor se apaga.                                                    │
# │   - static/js/automatizaciones.js dibuja y edita las reglas en la página│
# └─────────────────────────────────────────────────────────────────────────┘
# json: guardar y leer las reglas en datos/automatizaciones.json.
import json
# logging: dejar en el log del programa los errores y avisos (reglas dañadas, fallos al ejecutar).
import logging
# math: comprobar que un número sea finito (rechaza «inf» y «nan»).
import math
# os: os.replace() para reemplazar el archivo de reglas de forma atómica.
import os
# threading: candado para que el hilo del sensor y las peticiones web no se pisen al tocar las reglas.
import threading
# Path: manejo de rutas de archivos.
from pathlib import Path

# Objeto con el que este módulo escribe avisos en el log (distinto del historial visible de registro.py).
registro_logs = logging.getLogger(__name__)

# Límites y parámetros de las reglas: alcance del sensor, máximo de reglas y las tres protecciones contra disparos falsos (confirmaciones, histéresis y enfriamiento).
UMBRAL_MIN_CM = 2       # alcance mínimo del HC-SR04
UMBRAL_MAX_CM = 400     # alcance máximo del HC-SR04
MAX_REGLAS = 8
CONFIRMACIONES = 2      # a 4 mediciones por segundo, unos 0,5 s
HISTERESIS_CM = 2.0
ENFRIAMIENTO_S = 2.0
# Condiciones permitidas: «menor» (distancia menor al umbral) o «mayor».
CONDICIONES = ("menor", "mayor")


# Error propio de las reglas. Su texto se muestra al usuario. app.py lo captura y responde con código 400.
class ErrorDeRegla(ValueError):
    """Error de validación con un mensaje pensado para mostrarse al usuario."""


# ==========================================
# VALIDACION Y DESCRIPCION
# ==========================================

# Convierte a entero valores razonables (3, 3.0, "3") y devuelve None si no se puede (los booleanos no cuentan).
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


# Valida la distancia de una regla: debe ser un número finito entre 2 y 400 cm. Devuelve el número redondeado a un decimal (sin «.0» si es entero). La usa MotorReglas.crear y _cargar.
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


# Valida y normaliza la acción de una regla (led, leds o servo). «leds_validos» viene de app.py (los LED de dispositivos.LED_PINS).
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


# Muestra un umbral sin decimales si es entero (20 y no 20.0).
def _formato_cm(umbral):
    return str(int(umbral)) if float(umbral).is_integer() else f"{umbral:.1f}"


# Nombre por defecto de un LED cuando nadie entrega una función de nombres.
def _nombre_de_fabrica(numero):
    return f"LED {numero}"


# Convierte una acción en texto («Encender cocina»). «nombre_led» es la función que entrega app.py (nombres_leds.obtener).
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


# Texto de la condición: «la distancia es menor a 20 cm».
def describir_condicion(condicion, umbral):
    comparador = "menor" if condicion == "menor" else "mayor"
    return f"la distancia es {comparador} a {_formato_cm(umbral)} cm"


# Texto completo de una regla: «Si la distancia es menor a 20 cm → Encender cocina». Se muestra en la página (static/js/automatizaciones.js) y en «comando reglas».
def describir_regla(regla, nombre_led=None):
    condicion = describir_condicion(regla["condicion"], regla["umbral_cm"])
    return f"Si {condicion} → {describir_accion(regla['accion'], nombre_led)}"


# Cumple una acción sobre el hardware real. app.py la entrega al motor como «ejecutar».
def ejecutar_en_hardware(accion):
    """Ejecuta una acción sobre los dispositivos reales (importa el hardware al usarse)."""
    # Aquí se importa dispositivos.py (el único que toca los pines). Se hace dentro de la función para que este archivo se pueda probar sin Raspberry. Según el tipo de acción llama a hw.controlar_led, hw.controlar_todos_leds o hw.mover_servo.
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

# Motor de reglas: guarda las reglas, las evalúa con cada medición y ejecuta las acciones. app.py crea una sola instancia.
class MotorReglas:
    # Constructor: recibe todo lo externo por parámetro (ver la lista de abajo) y carga las reglas guardadas.
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
        # Guarda los parámetros recibidos de app.py para usarlos después.
        self._ejecutar = ejecutar
        self._leds_validos = tuple(leds_validos)
        self._ruta = Path(ruta) if ruta else None
        self._registrar = registrar
        self._nombre_led = nombre_led
        # Candado reentrante que protege la lista de reglas. Más abajo: la lista de reglas en memoria y la bandera de «reglas en pausa».
        self._candado = threading.RLock()
        self._reglas = []
        self._pausadas = False
        # Lee las reglas guardadas en el archivo JSON (si existe).
        self._cargar()

    # Métodos que solo leen.
    # ---------- consulta ----------

    # Convierte una regla interna en la versión pública (sin datos internos como la racha) que viaja a la página, y le agrega su descripción en texto.
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

    # Lista todas las reglas en versión pública.
    def listar(self):
        with self._candado:
            return [self._publica(r) for r in self._reglas]

    @property
    # Indica si las reglas están en pausa (se usa como atributo, sin paréntesis).
    def pausadas(self):
        with self._candado:
            return self._pausadas

    # Todo lo que la página necesita en GET /api/reglas (app.py agrega encima los nombres de LED y el estado del sensor).
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

    # Frase con todas las reglas; la usa app.py para responder al comando de voz «reglas».
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

    # Métodos que cambian las reglas (todos guardan el archivo después).
    # ---------- modificación ----------

    # Crea una regla nueva. La llaman app.py (POST /api/reglas y las reglas habladas). Valida todo antes de guardar.
    def crear(self, condicion, umbral_cm, accion):
        if condicion not in CONDICIONES:
            raise ErrorDeRegla("La condición debe ser «menor» o «mayor».")
        # Valida la distancia y la acción (funciones de más arriba); si algo está mal lanzan ErrorDeRegla.
        umbral = validar_umbral(umbral_cm)
        accion = validar_accion(accion, self._leds_validos)

        with self._candado:
            # Respeta el máximo de reglas (8).
            if len(self._reglas) >= MAX_REGLAS:
                raise ErrorDeRegla(
                    f"Ya hay {MAX_REGLAS} reglas. Borrá alguna antes de crear otra."
                )
            # Evita reglas duplicadas (misma condición, distancia y acción).
            for existente in self._reglas:
                if (
                    existente["condicion"] == condicion
                    and existente["umbral_cm"] == umbral
                    and existente["accion"] == accion
                ):
                    raise ErrorDeRegla(f"Ya existe una regla igual (la {existente['id']}).")

            # Se reutiliza el número libre más chico, así «regla uno», «regla dos»…
            # siguen siendo fáciles de decir aunque se hayan borrado reglas.
            # Elige el número libre más chico para la regla nueva (ids usados -> primer hueco).
            usados = {r["id"] for r in self._reglas}
            nuevo_id = next(n for n in range(1, MAX_REGLAS + 1) if n not in usados)

            # Arma la regla interna con su estado inicial de evaluación.
            regla = {
                "id": nuevo_id,
                "condicion": condicion,
                "umbral_cm": umbral,
                "accion": accion,
                "activa": True,
                **self._estado_inicial(),
            }
            # La agrega, mantiene la lista ordenada por número y la guarda en el archivo.
            self._reglas.append(regla)
            self._reglas.sort(key=lambda r: r["id"])
            self._guardar()
            return self._publica(regla)

    # Borra una regla por su número. Devuelve False si no existía.
    def eliminar(self, id_regla):
        with self._candado:
            antes = len(self._reglas)
            self._reglas = [r for r in self._reglas if r["id"] != id_regla]
            if len(self._reglas) == antes:
                return False
            self._guardar()
            return True

    # Borra todas las reglas y devuelve cuántas había.
    def eliminar_todas(self):
        with self._candado:
            cantidad = len(self._reglas)
            self._reglas = []
            if cantidad:
                self._guardar()
            return cantidad

    # Activa o desactiva una regla sin borrarla. Reinicia su estado de evaluación pero conserva su contador de disparos.
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

    # Pausa o reanuda todas las reglas a la vez (botón «Pausar reglas» y comandos de voz).
    def pausar(self, pausadas):
        with self._candado:
            self._pausadas = bool(pausadas)
            self._reiniciar_sin_candado()
            self._guardar()
            return self._pausadas

    # Lógica que decide cuándo se dispara una regla.
    # ---------- evaluación ----------

    # Método que no usa «self»: es una función auxiliar dentro de la clase.
    @staticmethod
    # Valores de seguimiento de una regla recién creada o reiniciada (no cumplida, racha 0, sin disparos).
    def _estado_inicial(conservar_disparos=None):
        base = {"cumplida": False, "racha": 0, "ultimo_disparo": None, "disparos": 0}
        if conservar_disparos:
            base["ultimo_disparo"] = conservar_disparos["ultimo_disparo"]
            base["disparos"] = conservar_disparos["disparos"]
        return base

    # Marca todas las reglas como «no cumplidas». Quien la llama ya tiene el candado tomado.
    def _reiniciar_sin_candado(self):
        for regla in self._reglas:
            regla["cumplida"] = False
            regla["racha"] = 0

    # Versión con candado de la anterior. sensor_monitor.py la llama (al_desactivar) cuando el sensor se apaga.
    def reiniciar_estados(self):
        """Se llama al desactivar el sensor: al reactivarlo, las reglas arrancan de cero."""
        with self._candado:
            self._reiniciar_sin_candado()

    @staticmethod
    # Decide si una medición cumple la condición, con histéresis: una regla ya cumplida necesita alejarse 2 cm del umbral para «soltarse». Evita rebotes por ruido del sensor.
    def _cumple(regla, centimetros):
        """Condición con histéresis: una regla ya cumplida es más tolerante para soltarse."""
        umbral = regla["umbral_cm"]
        if regla["condicion"] == "menor":
            limite = umbral + HISTERESIS_CM if regla["cumplida"] else umbral
            return centimetros < limite
        limite = umbral - HISTERESIS_CM if regla["cumplida"] else umbral
        return centimetros > limite

    # Evalúa todas las reglas con una medición nueva. sensor_monitor.py la llama 4 veces por segundo (al_medir).
    def procesar_medicion(self, momento, centimetros):
        """Evalúa todas las reglas con una medición. Devuelve las que se dispararon."""
        # Sin medición válida no se cambia nada.
        if centimetros is None:
            return []  # sin eco válido no hay información: no se cambia nada

        disparadas = []
        with self._candado:
            # Con las reglas en pausa se reinician los estados y no se dispara nada.
            if self._pausadas:
                self._reiniciar_sin_candado()
                return []

            # Recorre cada regla: las desactivadas o que no cumplen la condición se «sueltan»; las ya disparadas esperan a soltarse.
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

                # Suma una confirmación consecutiva (tope: CONFIRMACIONES) y calcula si todavía está en «enfriamiento» desde el último disparo.
                regla["racha"] = min(regla["racha"] + 1, CONFIRMACIONES)
                enfriando = (
                    regla["ultimo_disparo"] is not None
                    and momento - regla["ultimo_disparo"] < ENFRIAMIENTO_S
                )
                # Si hubo suficientes confirmaciones seguidas y no está enfriando, la regla se DISPARA: queda marcada como cumplida y se anota el momento y el contador.
                if regla["racha"] >= CONFIRMACIONES and not enfriando:
                    regla["cumplida"] = True
                    regla["racha"] = 0
                    regla["ultimo_disparo"] = momento
                    regla["disparos"] += 1
                    disparadas.append(self._publica(regla))

        # Las acciones se ejecutan fuera del candado: mover el servo tarda medio
        # segundo y no debe bloquear a quien consulte las reglas mientras tanto.
        # Ejecuta las acciones de las reglas disparadas, ya sin el candado tomado.
        for regla in disparadas:
            self._disparar(regla, centimetros)
        return disparadas

    # Ejecuta la acción de una regla y deja constancia en el registro de eventos.
    def _disparar(self, regla, centimetros):
        accion = regla["accion"]
        try:
            # Llama a la función de ejecución (ejecutar_en_hardware, que usa dispositivos.py). Si sale bien, el resultado es la descripción de la acción.
            self._ejecutar(accion)
            estado, resultado = "ok", describir_accion(accion, self._nombre_led)
        # Si la acción falla, se anota el error y el resultado queda como «error» para que el usuario lo vea.
        except Exception:
            registro_logs.exception("Error al ejecutar la regla %s", regla["id"])
            estado, resultado = "error", f"No se pudo ejecutar: {describir_accion(accion, self._nombre_led)}"

        # Si app.py entregó la función de registro (registro.agregar), se agrega el evento «regla» con la distancia medida y la acción realizada.
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

    # Guardado y lectura del archivo datos/automatizaciones.json.
    # ---------- persistencia ----------

    # Guarda las reglas (solo los datos permanentes, no la racha) con escritura atómica: primero a un archivo temporal y luego se renombra.
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

    # Lee las reglas guardadas. Descarta con un aviso las entradas dañadas o inválidas (por ejemplo si alguien editó el archivo a mano).
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
        # Revisa cada regla guardada (máximo 100 entradas) validándola de nuevo con las mismas funciones que usa crear().
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
            # Evita cargar dos reglas con el mismo número.
            if all(r["id"] != regla["id"] for r in self._reglas):
                self._reglas.append(regla)

        self._reglas.sort(key=lambda r: r["id"])

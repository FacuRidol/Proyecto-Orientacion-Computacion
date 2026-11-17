# asistente.py
"""Configuración y «sesión» del asistente de voz.

Guarda tres ajustes que se editan desde la página (panel «Asistente de voz»):

    modo        "siempre"   -> cada orden debe empezar con una palabra de
                               activación («robot encender cocina»).
                "asistente" -> se dice la palabra una vez, el asistente saluda
                               y las órdenes siguientes se entienden SIN
                               repetirla, hasta que pase el tiempo de espera o
                               se diga «adiós».
    palabras    las palabras de activación («comando», «robot»...).
    espera_s    segundos de inactividad tras los cuales el modo asistente
                vuelve a pedir la palabra (0 = nunca; solo «adiós» lo cierra).

Y mantiene la sesión: si el asistente está «despierto» (puede recibir órdenes
sin palabra de activación) y cuántos segundos le quedan.

Los ajustes se guardan en datos/configuracion.json; la sesión vive solo en
memoria (al reiniciar la aplicación el asistente empieza dormido).
"""

# ┌─────────────────────────────────────────────────────────────────────────┐
# │ DE QUIÉN DEPENDE / QUIÉN LO USA                                         │
# │ No importa ningún archivo del proyecto (solo librerías estándar).       │
# │   - app.py lo importa (from asistente import Asistente,                 │
# │     ErrorDeConfiguracion), crea una única instancia («asistente») y le  │
# │     entrega: las palabras de fábrica (PALABRAS_DE_INICIO), su función   │
# │     normalizar() y revisar_palabra_de_inicio() (las palabras que no se  │
# │     pueden usar porque ya significan otra cosa), porque este archivo no │
# │     conoce los comandos de voz.                                         │
# │   - app.py usa la instancia en:                                         │
# │       · comando(): saber si el asistente está despierto, despertarlo,   │
# │         extender la sesión y dormirlo.                                  │
# │       · GET /api/configuracion y PUT /api/configuracion: leer y cambiar │
# │         los ajustes desde la página.                                    │
# │       · GET /api/estado: informar el estado a todas las pestañas.       │
# │   - static/js/asistente.js muestra y edita estos ajustes en la página.  │
# └─────────────────────────────────────────────────────────────────────────┘

# json: leer y escribir el archivo de configuración.
import json
# logging: dejar avisos en el log si el archivo está dañado o no se puede guardar.
import logging
# math: math.inf representa «sesión sin vencimiento» (espera 0).
import math
# os: os.replace() para reemplazar el archivo de forma atómica (nunca queda a medias).
import os
# re: validar los caracteres permitidos en una palabra de activación.
import re
# threading: candado para que dos peticiones no cambien la configuración a la vez.
import threading
# time: reloj monótono (no se ve afectado por cambios de hora del sistema) para medir la sesión.
import time
# Path: manejo de rutas de archivos.
from pathlib import Path

# Objeto con el que este módulo escribe avisos en el log del programa.
registro_logs = logging.getLogger(__name__)

# Los dos modos de funcionamiento (ver la descripción arriba).
MODOS = ("siempre", "asistente")
# Modo inicial: «siempre» es el comportamiento original del proyecto, así nada cambia hasta que la persona elija otro.
MODO_POR_DEFECTO = "siempre"

# Tiempo de espera inicial del modo asistente (segundos) y límites permitidos.
ESPERA_POR_DEFECTO = 30
ESPERA_MINIMA = 5
ESPERA_MAXIMA = 600

# Límites de la lista de palabras de activación.
MAX_PALABRAS = 8           # cuántas palabras como máximo
LARGO_MAXIMO_PALABRA = 24  # caracteres de cada una
MAX_TOKENS_POR_PALABRA = 3 # una palabra puede ser una frase corta: «hola robot»

# Letras (con tildes y ñ), números, espacios y unos pocos signos. Evita etiquetas HTML y caracteres raros.
_CARACTERES_VALIDOS = re.compile(r"[\w .'’-]+")


# Error propio: se lanza cuando un ajuste no es válido. Su texto se muestra tal cual en la página.
# app.py lo captura (except ErrorDeConfiguracion) y responde con código 400.
class ErrorDeConfiguracion(ValueError):
    """Error de validación con un mensaje pensado para mostrarse al usuario."""


# Clase que guarda la configuración y la sesión. app.py crea una sola instancia.
class Asistente:
    # Constructor: no lee el archivo todavía (eso ocurre la primera vez que hace falta, ver _asegurar_cargado).
    def __init__(self, palabras_por_defecto, normalizar, ruta=None, revisar=None, reloj=time.monotonic):
        """
        palabras_por_defecto  palabras de activación «de fábrica» (app.py: PALABRAS_DE_INICIO)
        normalizar            función que quita tildes, signos y mayúsculas de un texto
        ruta                  archivo JSON donde se guarda la configuración (None = no guardar)
        revisar               función (palabras_normalizadas) -> mensaje de error o None,
                              para rechazar palabras que se confundirían con comandos
        reloj                 función que da la hora en segundos (se cambia solo en las pruebas)
        """
        # Guarda lo recibido: las palabras de fábrica (copia, para que nadie las altere desde afuera)...
        self._por_defecto = list(palabras_por_defecto)
        # ...la función de normalizar, el archivo, la revisión extra de app.py y el reloj.
        self._normalizar = normalizar
        self._ruta = Path(ruta) if ruta else None
        self._revisar = revisar
        self._reloj = reloj
        # Candado reentrante: protege los ajustes y la sesión.
        self._candado = threading.RLock()
        # Ajustes vigentes (arrancan con los valores de fábrica hasta que se lea el archivo).
        self._modo = MODO_POR_DEFECTO
        self._espera_s = ESPERA_POR_DEFECTO
        self._palabras = list(palabras_por_defecto)
        # Sesión: None = dormido; un número = instante (del reloj) en que vence; math.inf = no vence.
        self._despierto_hasta = None
        # Marca que indica si ya se leyó el archivo JSON.
        self._cargado = False

    # ---------- ajustes (lectura) ----------

    # Devuelve las palabras de activación vigentes. app.py las usa para reconocer el comienzo de una orden.
    def palabras(self):
        with self._candado:
            self._asegurar_cargado()
            return list(self._palabras)

    # Devuelve el modo vigente: «siempre» o «asistente».
    def modo(self):
        with self._candado:
            self._asegurar_cargado()
            return self._modo

    # Foto completa para la página: ajustes + estado de la sesión. Va en GET /api/estado y /api/configuracion,
    # y static/js/asistente.js la usa para dibujar el panel y mantener todas las pestañas sincronizadas.
    def estado(self):
        with self._candado:
            self._asegurar_cargado()
            activo = self._sesion_vigente()
            return {
                "modo": self._modo,
                "espera_s": self._espera_s,
                "palabras": list(self._palabras),
                "palabras_por_defecto": list(self._por_defecto),
                # «activo» es True solo en modo asistente y con la sesión sin vencer.
                "activo": activo,
                # Segundos que le quedan a la sesión (None si está dormido o si no vence nunca).
                "restante_s": self._restante() if activo else None,
                # Límites, para que la página los muestre y valide antes de enviar.
                "limites": {
                    "max_palabras": MAX_PALABRAS,
                    "largo_palabra": LARGO_MAXIMO_PALABRA,
                    "espera_min": ESPERA_MINIMA,
                    "espera_max": ESPERA_MAXIMA,
                },
            }

    # ---------- ajustes (modificación) ----------

    # Cambia uno o varios ajustes a la vez. Todo se valida ANTES de aplicar nada: si algo está mal,
    # no se cambia nada. La llama app.py desde PUT /api/configuracion.
    def configurar(self, modo=None, espera_s=None, palabras=None):
        with self._candado:
            self._asegurar_cargado()

            # Valida cada ajuste recibido (los que vienen como None no se tocan).
            nuevo_modo = self._validar_modo(modo) if modo is not None else self._modo
            nueva_espera = self._validar_espera(espera_s) if espera_s is not None else self._espera_s
            nuevas_palabras = self._validar_palabras(palabras) if palabras is not None else self._palabras

            # Todo en orden: se aplican los cambios...
            self._modo = nuevo_modo
            self._espera_s = nueva_espera
            self._palabras = nuevas_palabras
            # ...si el modo ya no es «asistente», la sesión abierta carece de sentido: se cierra.
            if self._modo != "asistente":
                self._despierto_hasta = None
            # Si cambió el tiempo de espera con la sesión abierta, se recalcula el vencimiento desde ahora.
            elif self._sesion_vigente():
                self._renovar()
            # Se graba el archivo.
            self._guardar()

    # Comprueba que el modo sea uno de los dos permitidos.
    def _validar_modo(self, modo):
        if modo not in MODOS:
            raise ErrorDeConfiguracion("El modo debe ser «siempre» o «asistente».")
        return modo

    # Comprueba el tiempo de espera: 0 (sin vencimiento) o un entero entre ESPERA_MINIMA y ESPERA_MAXIMA.
    def _validar_espera(self, valor):
        # bool es un entero para Python (True == 1): se rechaza explícitamente.
        # (también se rechazan NaN e infinito, que JSON puede traer y que no se pueden convertir a entero).
        if (
            isinstance(valor, bool)
            or not isinstance(valor, (int, float))
            or not math.isfinite(valor)
            or valor != int(valor)
        ):
            raise ErrorDeConfiguracion("El tiempo de espera debe ser un número entero de segundos.")
        valor = int(valor)
        if valor != 0 and not ESPERA_MINIMA <= valor <= ESPERA_MAXIMA:
            raise ErrorDeConfiguracion(
                f"El tiempo de espera debe ser 0 (sin límite) o estar entre {ESPERA_MINIMA} y {ESPERA_MAXIMA} segundos."
            )
        return valor

    # Valida toda la lista de palabras de activación y devuelve la lista limpia.
    def _validar_palabras(self, palabras):
        if not isinstance(palabras, list):
            raise ErrorDeConfiguracion("Las palabras de activación deben ser una lista.")
        if not 1 <= len(palabras) <= MAX_PALABRAS:
            raise ErrorDeConfiguracion(f"Tiene que haber entre 1 y {MAX_PALABRAS} palabras de activación.")

        limpias = []
        claves = []
        for original in palabras:
            if not isinstance(original, str):
                raise ErrorDeConfiguracion("Cada palabra de activación debe ser un texto.")
            # Quita espacios sobrantes (los de los bordes y los repetidos).
            mostrada = " ".join(original.split())
            if not mostrada:
                raise ErrorDeConfiguracion("Hay una palabra de activación vacía.")
            if len(mostrada) > LARGO_MAXIMO_PALABRA:
                raise ErrorDeConfiguracion(
                    f"«{mostrada[:LARGO_MAXIMO_PALABRA]}…» es demasiado larga (máximo {LARGO_MAXIMO_PALABRA} caracteres)."
                )
            if not _CARACTERES_VALIDOS.fullmatch(mostrada):
                raise ErrorDeConfiguracion(f"«{mostrada}» tiene caracteres no permitidos. Usá solo letras, números y espacios.")

            # Versión comparable (sin tildes ni mayúsculas) y sus palabras sueltas.
            clave = self._normalizar(mostrada)
            tokens = clave.split()
            if not tokens:
                raise ErrorDeConfiguracion(f"«{mostrada}» no tiene letras ni números.")
            if len(tokens) > MAX_TOKENS_POR_PALABRA:
                raise ErrorDeConfiguracion(
                    f"«{mostrada}» tiene demasiadas palabras (máximo {MAX_TOKENS_POR_PALABRA} por activación)."
                )
            if clave in claves:
                raise ErrorDeConfiguracion(f"«{mostrada}» está repetida.")

            # Revisión extra de app.py: que no choque con verbos, nombres de LED, números, etc.
            if self._revisar is not None:
                motivo = self._revisar(tokens)
                if motivo:
                    raise ErrorDeConfiguracion(motivo)

            limpias.append(mostrada)
            claves.append(clave)
        return limpias

    # ---------- sesión (despierto / dormido) ----------

    # ¿Está el asistente despierto? Mientras lo esté, las órdenes no necesitan la palabra de activación.
    def sesion_activa(self):
        with self._candado:
            self._asegurar_cargado()
            return self._sesion_vigente()

    # Despierta al asistente (o lo mantiene despierto) desde ahora. Solo tiene efecto en modo «asistente».
    # app.py la llama cuando se dice una palabra de activación. Devuelve True si quedó despierto.
    def despertar(self):
        with self._candado:
            self._asegurar_cargado()
            if self._modo != "asistente":
                return False
            self._renovar()
            return True

    # Renueva el tiempo de la sesión si todavía está abierta. app.py la llama tras cada orden ejecutada
    # sin palabra de activación, para que una conversación activa no se corte a los 30 s.
    def extender(self):
        with self._candado:
            self._asegurar_cargado()
            if self._sesion_vigente():
                self._renovar()

    # Cierra la sesión: el asistente vuelve a dormir. La llama app.py con «adiós» o al cambiar de modo.
    def dormir(self):
        with self._candado:
            self._despierto_hasta = None

    # Calcula el nuevo vencimiento: ahora + tiempo de espera (o «nunca» si la espera es 0).
    def _renovar(self):
        self._despierto_hasta = math.inf if self._espera_s == 0 else self._reloj() + self._espera_s

    # True si hay sesión abierta y no venció. Si venció, la limpia. Se llama con el candado tomado.
    def _sesion_vigente(self):
        if self._modo != "asistente" or self._despierto_hasta is None:
            return False
        if self._reloj() >= self._despierto_hasta:
            self._despierto_hasta = None
            return False
        return True

    # Segundos que le quedan a la sesión (redondeados hacia arriba), o None si no vence nunca.
    def _restante(self):
        if self._despierto_hasta is None or self._despierto_hasta == math.inf:
            return None
        return max(0, math.ceil(self._despierto_hasta - self._reloj()))

    # ---------- persistencia ----------

    # Lee el archivo una sola vez, la primera vez que alguien necesita los ajustes.
    def _asegurar_cargado(self):
        if self._cargado:
            return
        self._cargado = True
        self._cargar()

    # Escribe los ajustes en el archivo JSON. Se llama después de cada cambio.
    def _guardar(self):
        if not self._ruta:
            return
        # Lo que se guarda: versión del formato y los tres ajustes.
        contenido = {
            "version": 1,
            "modo": self._modo,
            "espera_s": self._espera_s,
            "palabras_inicio": self._palabras,
        }
        # Escribe primero en un archivo temporal y después lo renombra: así, si se corta la luz, no queda un JSON a medias.
        temporal = self._ruta.with_name(self._ruta.name + ".tmp")
        try:
            # Crea la carpeta datos/ si no existe y escribe el JSON (ensure_ascii=False conserva tildes y ñ).
            self._ruta.parent.mkdir(parents=True, exist_ok=True)
            temporal.write_text(json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporal, self._ruta)
        except OSError:
            # Si no se puede escribir (disco lleno, permisos), solo se avisa: los ajustes siguen funcionando en memoria.
            registro_logs.exception("No se pudo guardar la configuración del asistente en %s", self._ruta)

    # Lee los ajustes guardados. Cada ajuste se revisa por separado: si uno es inválido (por ejemplo, el archivo
    # fue editado a mano) se usa el valor de fábrica de ese ajuste y se conservan los demás.
    def _cargar(self):
        if not self._ruta or not self._ruta.exists():
            return
        try:
            datos = json.loads(self._ruta.read_text(encoding="utf-8"))
            if not isinstance(datos, dict):
                raise ValueError("el archivo no contiene un objeto JSON")
        except (OSError, ValueError):
            registro_logs.warning("No se pudo leer %s; el asistente usa su configuración de fábrica.", self._ruta)
            return

        # Cada ajuste se valida con las mismas funciones que usa configurar().
        for campo, validar, destino in (
            ("modo", self._validar_modo, "_modo"),
            ("espera_s", self._validar_espera, "_espera_s"),
            ("palabras_inicio", self._validar_palabras, "_palabras"),
        ):
            if campo not in datos:
                continue
            try:
                setattr(self, destino, validar(datos[campo]))
            except ErrorDeConfiguracion as error:
                registro_logs.warning("Se omitió el ajuste guardado «%s» no válido: %s", campo, error)

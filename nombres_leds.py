# nombres_leds.py
"""Nombres personalizados de los LED («LED 1» -> «cocina»).

El nombre que se elige en la página es también el que se dice por voz:
«comando encender cocina» o «robot apagar cocina». Mientras un LED no tenga
nombre propio sigue llamándose «LED 1», «LED 2»... y responde a «LED uno».

Este módulo se ocupa de tres cosas, sin tocar el hardware (así se puede probar
sin Raspberry):

    - validar y guardar los nombres (datos/nombres_leds.json, sobreviven a un
      reinicio),
    - mantener un nombre distinto por LED,
    - buscar qué LED nombra una frase ya normalizada (sin tildes, en minúsculas).

Las reglas que dependen de los comandos de voz (qué palabras están prohibidas
en un nombre porque ya significan otra cosa) las aporta app.py a través de la
función «revisar»; así este archivo no necesita conocer los comandos.
"""

import json
import logging
import os
import re
import threading
from pathlib import Path

registro_logs = logging.getLogger(__name__)

LARGO_MAXIMO = 24
LARGO_MAXIMO_ENTRADA = 200  # tope del texto recibido, antes de limpiar espacios

# Al buscar un nombre dentro de una frase se ignoran estas palabras, para que
# «luz de la cocina» y «luz cocina» se entiendan igual.
ARTICULOS = frozenset({"el", "la", "los", "las", "de", "del", "al", "en", "mi", "tu", "su"})

# Letras (con tildes y ñ), números, espacios y unos pocos signos.
_CARACTERES_VALIDOS = re.compile(r"[\w .'’-]+")


class ErrorDeNombre(ValueError):
    """Error de validación con un mensaje pensado para mostrarse al usuario."""


def nombre_por_defecto(numero):
    return f"LED {numero}"


class NombresLeds:
    def __init__(self, leds_validos, normalizar, ruta=None, revisar=None):
        """
        leds_validos  números de LED que existen
        normalizar    función que quita tildes, signos y mayúsculas de un texto
        ruta          archivo JSON donde se guardan los nombres (None = no guardar)
        revisar       función (numero, tokens) -> mensaje de error o None, para
                      rechazar nombres que se confundirían con otros comandos
        """
        self._leds_validos = tuple(leds_validos)
        self._normalizar = normalizar
        self._ruta = Path(ruta) if ruta else None
        self._revisar = revisar
        self._candado = threading.RLock()
        self._nombres = {}   # numero -> nombre tal como lo escribió la persona
        self._alias = {}     # numero -> palabras con las que se lo busca en una frase
        self._cargado = False

    # ---------- consulta ----------

    @property
    def numeros(self):
        return self._leds_validos

    def personalizado(self, numero):
        with self._candado:
            self._asegurar_cargado()
            return numero in self._nombres

    def obtener(self, numero):
        """Nombre para mostrar: el elegido o, si no hay, «LED n»."""
        with self._candado:
            self._asegurar_cargado()
            return self._nombres.get(numero) or nombre_por_defecto(numero)

    def todos(self):
        """{numero: {"nombre": ..., "personalizado": bool}} de todos los LED."""
        with self._candado:
            self._asegurar_cargado()
            return {
                numero: {
                    "nombre": self._nombres.get(numero) or nombre_por_defecto(numero),
                    "personalizado": numero in self._nombres,
                }
                for numero in self._leds_validos
            }

    def _palabras(self, texto):
        """Palabras de un texto sin signos ni artículos: la base de la comparación."""
        return [p for p in self._normalizar(texto).split() if p not in ARTICULOS]

    def buscar(self, texto):
        """Números de los LED con nombre propio que aparecen en la frase.

        Si un nombre contiene a otro («cocina» y «luz cocina»), gana el más largo.
        Cada palabra de la frase cuenta para un solo nombre.
        """
        with self._candado:
            self._asegurar_cargado()
            alias = dict(self._alias)

        palabras = self._palabras(texto)
        candidatos = []
        for numero, nombre in alias.items():
            largo = len(nombre)
            for inicio in range(len(palabras) - largo + 1):
                if palabras[inicio:inicio + largo] == nombre:
                    candidatos.append((largo, inicio, numero))

        candidatos.sort(key=lambda c: (-c[0], c[1]))
        usadas = set()
        encontrados = []
        for largo, inicio, numero in candidatos:
            posiciones = set(range(inicio, inicio + largo))
            if posiciones & usadas:
                continue
            usadas |= posiciones
            if numero not in encontrados:
                encontrados.append(numero)
        return encontrados

    # ---------- modificación ----------

    def establecer(self, numero, nombre):
        """Cambia el nombre de un LED y devuelve el nombre que quedó.

        Un nombre vacío (o igual al original, «LED 1») lo devuelve a su nombre
        de fábrica. Lanza ErrorDeNombre si el nombre no se puede usar.
        """
        numero = self._validar_numero(numero)

        if nombre is None:
            nombre = ""
        if not isinstance(nombre, str):
            raise ErrorDeNombre("El nombre debe ser un texto.")
        if len(nombre) > LARGO_MAXIMO_ENTRADA:
            raise ErrorDeNombre(f"El nombre puede tener hasta {LARGO_MAXIMO} caracteres.")

        mostrado = " ".join(nombre.split())
        with self._candado:
            self._asegurar_cargado()

            if not mostrado or self._normalizar(mostrado) == self._normalizar(nombre_por_defecto(numero)):
                if self._nombres.pop(numero, None) is not None:
                    self._alias.pop(numero, None)
                    self._guardar()
                return nombre_por_defecto(numero)

            tokens = self._validar(numero, mostrado)
            self._nombres[numero] = mostrado
            self._alias[numero] = tokens
            self._guardar()
            return mostrado

    def _validar_numero(self, numero):
        if isinstance(numero, bool) or not isinstance(numero, int) or numero not in self._leds_validos:
            raise ErrorDeNombre("El LED solicitado no existe.")
        return numero

    def _validar(self, numero, mostrado):
        """Devuelve las palabras del nombre o lanza ErrorDeNombre. Se llama con el candado tomado."""
        if len(mostrado) > LARGO_MAXIMO:
            raise ErrorDeNombre(f"El nombre puede tener hasta {LARGO_MAXIMO} caracteres.")
        if not _CARACTERES_VALIDOS.fullmatch(mostrado):
            raise ErrorDeNombre("Usá solo letras, números y espacios.")

        tokens = self._palabras(mostrado)
        if not tokens:
            raise ErrorDeNombre(
                "El nombre necesita al menos una palabra con letras o números "
                "(no alcanza con «la», «de»...)."
            )

        if self._revisar is not None:
            motivo = self._revisar(numero, tokens)
            if motivo:
                raise ErrorDeNombre(motivo)

        for otro, alias in self._alias.items():
            if otro != numero and alias == tokens:
                raise ErrorDeNombre(
                    f"Ya hay otro LED que se llama «{self._nombres[otro]}». "
                    "Cada LED necesita un nombre distinto."
                )
        return tokens

    # ---------- persistencia ----------

    def _asegurar_cargado(self):
        # Se lee el archivo la primera vez que se necesita, no al crear el objeto:
        # así «revisar» puede apoyarse en cosas que app.py define más abajo.
        if self._cargado:
            return
        self._cargado = True
        self._cargar()

    def _guardar(self):
        if not self._ruta:
            return
        contenido = {
            "version": 1,
            "nombres": {str(numero): nombre for numero, nombre in sorted(self._nombres.items())},
        }
        temporal = self._ruta.with_name(self._ruta.name + ".tmp")
        try:
            self._ruta.parent.mkdir(parents=True, exist_ok=True)
            temporal.write_text(
                json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(temporal, self._ruta)  # reemplazo atómico: nunca queda a medias
        except OSError:
            registro_logs.exception("No se pudieron guardar los nombres de los LED en %s", self._ruta)

    def _cargar(self):
        if not self._ruta or not self._ruta.exists():
            return
        try:
            datos = json.loads(self._ruta.read_text(encoding="utf-8"))
            guardados = datos.get("nombres", {})
        except (OSError, ValueError, AttributeError):
            registro_logs.warning("No se pudo leer %s; los LED vuelven a sus nombres originales.", self._ruta)
            return
        if not isinstance(guardados, dict):
            return

        for clave, nombre in guardados.items():
            try:
                numero = int(clave)
                if numero not in self._leds_validos or not isinstance(nombre, str):
                    raise ErrorDeNombre("LED o nombre no válido")
                mostrado = " ".join(nombre.split())
                self._alias[numero] = self._validar(numero, mostrado)
                self._nombres[numero] = mostrado
            except (ErrorDeNombre, ValueError) as error:
                registro_logs.warning("Se omitió un nombre guardado no válido (%r): %s", clave, error)

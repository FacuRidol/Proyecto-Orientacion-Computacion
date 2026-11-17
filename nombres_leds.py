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

# ┌─────────────────────────────────────────────────────────────────────────┐
# │ DE QUIÉN DEPENDE / QUIÉN LO USA                                         │
# │ No importa ningún archivo del proyecto (solo librerías estándar).       │
# │   - app.py lo importa (from nombres_leds import NombresLeds,            │
# │     ErrorDeNombre) y crea una única instancia: «nombres_leds». Le pasa  │
# │     su función normalizar() y revisar_nombre_de_led() (las palabras     │
# │     prohibidas), porque este archivo no conoce los comandos de voz.     │
# │   - app.py usa esa instancia para:                                      │
# │       · renombrar (PUT /api/led/<n>/nombre -> establecer)               │
# │       · mostrar nombres (GET /api/estado y /api/reglas -> todos)        │
# │       · entender órdenes de voz como «encender cocina» (buscar)         │
# │   - Guarda los nombres en datos/nombres_leds.json (ruta que decide      │
# │     app.py con CARPETA_DATOS).                                          │
# │   - static/js/voz.js muestra esos nombres en las tarjetas de LED.       │
# └─────────────────────────────────────────────────────────────────────────┘
# json: leer y escribir el archivo de nombres.
import json
# logging: dejar avisos en el registro del programa si el archivo está dañado o no se puede guardar.
import logging
# os: os.replace() para reemplazar el archivo de forma atómica (nunca queda a medias).
import os
# re: expresiones regulares (aquí, para validar los caracteres permitidos).
import re
# threading: candado para que dos peticiones no cambien los nombres a la vez.
import threading
# Path: manejo de rutas de archivos.
from pathlib import Path

# Objeto con el que este módulo escribe avisos en el log del programa.
registro_logs = logging.getLogger(__name__)

# Largo máximo de un nombre (lo que ve la persona, ya sin espacios sobrantes).
LARGO_MAXIMO = 24
LARGO_MAXIMO_ENTRADA = 200  # tope del texto recibido, antes de limpiar espacios

# Al buscar un nombre dentro de una frase se ignoran estas palabras, para que
# «luz de la cocina» y «luz cocina» se entiendan igual.
ARTICULOS = frozenset({"el", "la", "los", "las", "de", "del", "al", "en", "mi", "tu", "su"})

# Letras (con tildes y ñ), números, espacios y unos pocos signos.
_CARACTERES_VALIDOS = re.compile(r"[\w .'’-]+")


# Error propio: se lanza cuando un nombre no sirve. Su texto se muestra tal cual en la página. app.py lo captura (except ErrorDeNombre) y responde con código 400.
class ErrorDeNombre(ValueError):
    """Error de validación con un mensaje pensado para mostrarse al usuario."""


# Nombre «de fábrica» de un LED: «LED 1», «LED 2»...
def nombre_por_defecto(numero):
    return f"LED {numero}"


# Clase que guarda, valida y busca los nombres. app.py crea una sola instancia.
class NombresLeds:
    # Constructor: no lee el archivo todavía (eso ocurre la primera vez que hace falta, ver _asegurar_cargado).
    def __init__(self, leds_validos, normalizar, ruta=None, revisar=None):
        """
        leds_validos  números de LED que existen
        normalizar    función que quita tildes, signos y mayúsculas de un texto
        ruta          archivo JSON donde se guardan los nombres (None = no guardar)
        revisar       función (numero, tokens) -> mensaje de error o None, para
                      rechazar nombres que se confundirían con otros comandos
        """
        # Guarda lo recibido: LED que existen, función de normalizar, archivo y función «revisar» (ambas vienen de app.py).
        self._leds_validos = tuple(leds_validos)
        self._normalizar = normalizar
        self._ruta = Path(ruta) if ruta else None
        self._revisar = revisar
        # Candado reentrante para proteger los diccionarios de nombres.
        self._candado = threading.RLock()
        self._nombres = {}   # numero -> nombre tal como lo escribió la persona
        self._alias = {}     # numero -> palabras con las que se lo busca en una frase
        # Marca que indica si ya se leyó el archivo JSON.
        self._cargado = False

    # Métodos que solo leen datos.
    # ---------- consulta ----------

    @property
    # Devuelve los números de LED válidos (app.py lo usa para saber qué LED existen).
    def numeros(self):
        return self._leds_validos

    # True si ese LED tiene un nombre propio. Lo usa app.py para decidir si «led uno» sigue valiendo.
    def personalizado(self, numero):
        with self._candado:
            self._asegurar_cargado()
            # Está personalizado si su número figura en el diccionario de nombres.
            return numero in self._nombres

    # Devuelve el nombre a mostrar de un LED. Lo usa app.py (mensajes de voz, estado) y automatizaciones.py (descripción de reglas).
    def obtener(self, numero):
        """Nombre para mostrar: el elegido o, si no hay, «LED n»."""
        with self._candado:
            self._asegurar_cargado()
            # Si hay nombre propio lo devuelve; si no, «LED n».
            return self._nombres.get(numero) or nombre_por_defecto(numero)

    # Devuelve la lista completa de nombres. Va en GET /api/estado y /api/reglas; static/js/voz.js y automatizaciones.js la usan para rotular.
    def todos(self):
        """{numero: {"nombre": ..., "personalizado": bool}} de todos los LED."""
        with self._candado:
            self._asegurar_cargado()
            return {
                numero: {
                    # Por cada LED: su nombre vigente y si es propio o de fábrica.
                    "nombre": self._nombres.get(numero) or nombre_por_defecto(numero),
                    "personalizado": numero in self._nombres,
                }
                for numero in self._leds_validos
            }

    # Palabras sueltas que forman parte de algún nombre propio. app.py las consulta para impedir que una
    # palabra de activación del asistente coincida con parte del nombre de un LED («robot» en «luz robot»).
    def palabras_en_uso(self):
        with self._candado:
            self._asegurar_cargado()
            return {palabra for alias in self._alias.values() for palabra in alias}

    # Convierte un texto en lista de palabras comparables: usa normalizar() de app.py (sin tildes ni mayúsculas) y descarta artículos («la», «de»...).
    def _palabras(self, texto):
        """Palabras de un texto sin signos ni artículos: la base de la comparación."""
        return [p for p in self._normalizar(texto).split() if p not in ARTICULOS]

    # Busca qué LED se nombra dentro de una frase. app.py la llama desde resolver_leds_en_texto para entender «encender cocina».
    def buscar(self, texto):
        """Números de los LED con nombre propio que aparecen en la frase.

        Si un nombre contiene a otro («cocina» y «luz cocina»), gana el más largo.
        Cada palabra de la frase cuenta para un solo nombre.
        """
        with self._candado:
            self._asegurar_cargado()
            # Copia las palabras de cada nombre (así no se mantiene el candado durante la búsqueda).
            alias = dict(self._alias)

        # Palabras de la frase que dijo el usuario.
        palabras = self._palabras(texto)
        # Lista de coincidencias posibles: (largo del nombre, posición en la frase, número de LED).
        candidatos = []
        # Para cada LED con nombre propio, recorre la frase buscando sus palabras de forma consecutiva.
        for numero, nombre in alias.items():
            largo = len(nombre)
            for inicio in range(len(palabras) - largo + 1):
                if palabras[inicio:inicio + largo] == nombre:
                    candidatos.append((largo, inicio, numero))

        # Ordena: primero los nombres más largos (así «luz cocina» gana sobre «cocina») y, a igual largo, el que aparece antes.
        candidatos.sort(key=lambda c: (-c[0], c[1]))
        # Posiciones de la frase que ya pertenecen a un nombre elegido.
        usadas = set()
        encontrados = []
        # Elige las coincidencias sin que dos nombres compartan una misma palabra.
        for largo, inicio, numero in candidatos:
            posiciones = set(range(inicio, inicio + largo))
            if posiciones & usadas:
                continue
            usadas |= posiciones
            if numero not in encontrados:
                encontrados.append(numero)
        # Devuelve los números de LED encontrados (app.py avisa si son más de uno).
        return encontrados

    # Métodos que cambian datos.
    # ---------- modificación ----------

    # Cambia (o restablece) el nombre de un LED. Lo llama app.py desde PUT /api/led/<n>/nombre.
    def establecer(self, numero, nombre):
        """Cambia el nombre de un LED y devuelve el nombre que quedó.

        Un nombre vacío (o igual al original, «LED 1») lo devuelve a su nombre
        de fábrica. Lanza ErrorDeNombre si el nombre no se puede usar.
        """
        # Comprueba que el LED exista. Después normaliza la entrada: sin valor equivale a vacío; debe ser texto y no pasarse de largo.
        numero = self._validar_numero(numero)

        if nombre is None:
            nombre = ""
        if not isinstance(nombre, str):
            raise ErrorDeNombre("El nombre debe ser un texto.")
        if len(nombre) > LARGO_MAXIMO_ENTRADA:
            raise ErrorDeNombre(f"El nombre puede tener hasta {LARGO_MAXIMO} caracteres.")

        # Limpia espacios: quita los de los bordes y reduce los repetidos a uno.
        mostrado = " ".join(nombre.split())
        with self._candado:
            self._asegurar_cargado()

            # Si lo escrito está vacío (o es igual a «LED n»), el LED vuelve a su nombre de fábrica y se guarda el cambio.
            if not mostrado or self._normalizar(mostrado) == self._normalizar(nombre_por_defecto(numero)):
                if self._nombres.pop(numero, None) is not None:
                    self._alias.pop(numero, None)
                    self._guardar()
                return nombre_por_defecto(numero)

            # Valida el nombre (lanza ErrorDeNombre si no sirve) y obtiene sus palabras de búsqueda. Luego guarda el nombre y sus palabras, y graba el archivo JSON.
            tokens = self._validar(numero, mostrado)
            self._nombres[numero] = mostrado
            self._alias[numero] = tokens
            self._guardar()
            return mostrado

    # Verifica que «numero» sea un entero de un LED existente (rechaza True/False, textos y números inexistentes).
    def _validar_numero(self, numero):
        if isinstance(numero, bool) or not isinstance(numero, int) or numero not in self._leds_validos:
            raise ErrorDeNombre("El LED solicitado no existe.")
        return numero

    # Aplica todas las reglas de un nombre: largo, caracteres, que tenga palabras, que no choque con comandos de voz y que no esté repetido.
    def _validar(self, numero, mostrado):
        """Devuelve las palabras del nombre o lanza ErrorDeNombre. Se llama con el candado tomado."""
        if len(mostrado) > LARGO_MAXIMO:
            raise ErrorDeNombre(f"El nombre puede tener hasta {LARGO_MAXIMO} caracteres.")
        # Solo se permiten letras, números, espacios y unos pocos signos (evita caracteres raros o etiquetas HTML).
        if not _CARACTERES_VALIDOS.fullmatch(mostrado):
            raise ErrorDeNombre("Usá solo letras, números y espacios.")

        # Palabras del nombre (sin artículos); si no quedó ninguna, el nombre no sirve.
        tokens = self._palabras(mostrado)
        if not tokens:
            raise ErrorDeNombre(
                "El nombre necesita al menos una palabra con letras o números "
                "(no alcanza con «la», «de»...)."
            )

        # Aplica la revisión extra de app.py (revisar_nombre_de_led): palabras reservadas, números solos, etc.
        if self._revisar is not None:
            motivo = self._revisar(numero, tokens)
            if motivo:
                raise ErrorDeNombre(motivo)

        # Verifica que ningún OTRO LED tenga exactamente el mismo nombre (sin contar mayúsculas, tildes ni artículos).
        for otro, alias in self._alias.items():
            if otro != numero and alias == tokens:
                raise ErrorDeNombre(
                    f"Ya hay otro LED que se llama «{self._nombres[otro]}». "
                    "Cada LED necesita un nombre distinto."
                )
        return tokens

    # Lectura y escritura del archivo datos/nombres_leds.json.
    # ---------- persistencia ----------

    # Lee el archivo una sola vez, la primera vez que alguien necesita los nombres.
    def _asegurar_cargado(self):
        # Se lee el archivo la primera vez que se necesita, no al crear el objeto:
        # así «revisar» puede apoyarse en cosas que app.py define más abajo.
        if self._cargado:
            return
        self._cargado = True
        self._cargar()

    # Escribe los nombres en el archivo JSON. Se llama después de cada cambio.
    def _guardar(self):
        if not self._ruta:
            return
        # Arma lo que se guarda: versión del formato y nombres por número.
        contenido = {
            "version": 1,
            "nombres": {str(numero): nombre for numero, nombre in sorted(self._nombres.items())},
        }
        # Escribe primero en un archivo temporal y después lo renombra: así, si se corta la luz, no queda un JSON a medias. Crea la carpeta datos/ si no existe (ensure_ascii=False conserva tildes y ñ).
        temporal = self._ruta.with_name(self._ruta.name + ".tmp")
        try:
            self._ruta.parent.mkdir(parents=True, exist_ok=True)
            temporal.write_text(
                json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(temporal, self._ruta)  # reemplazo atómico: nunca queda a medias
        # Si no se puede escribir (disco lleno, permisos), solo se avisa en el log: el nombre sigue funcionando en memoria.
        except OSError:
            registro_logs.exception("No se pudieron guardar los nombres de los LED en %s", self._ruta)

    # Lee los nombres guardados. Si el archivo no existe, está roto o tiene datos inválidos, lo descarta sin romper nada.
    def _cargar(self):
        if not self._ruta or not self._ruta.exists():
            return
        try:
            # Lee el archivo y obtiene el diccionario «nombres».
            datos = json.loads(self._ruta.read_text(encoding="utf-8"))
            guardados = datos.get("nombres", {})
        except (OSError, ValueError, AttributeError):
            registro_logs.warning("No se pudo leer %s; los LED vuelven a sus nombres originales.", self._ruta)
            return
        if not isinstance(guardados, dict):
            return

        # Revalida cada nombre guardado (por si alguien editó el archivo a mano): se omiten LED inexistentes, nombres reservados o repetidos.
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

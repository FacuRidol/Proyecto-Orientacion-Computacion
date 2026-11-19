# Reconocimiento de voz offline con Vosk.
"""Reconocimiento de voz local usando Vosk y audio PCM mono a 16 kHz."""





















import json

import logging

import os

import re

import threading

from time import perf_counter

from pathlib import Path



DIRECTORIO_PROYECTO = Path(__file__).resolve().parent.parent


RUTA_MODELO = Path(
    os.environ.get(
        "VOSK_MODEL_PATH",
        DIRECTORIO_PROYECTO / "modelos" / "vosk-model-small-es-0.42",
    )
)

FRECUENCIA_MUESTREO = 16000


# Archivo donde se define a qué palabra equivale lo que interpreta Vosk.
# Formato: {"lo que escucha Vosk": "lo que querés que quede"}
RUTA_CORRECCIONES = Path(
    os.environ.get(
        "VOSK_CORRECCIONES_PATH",
        DIRECTORIO_PROYECTO / "correcciones_vosk.json",
    )
)

registro = logging.getLogger(__name__)


class CorrectorTexto:
    """Reemplaza palabras o frases mal interpretadas por Vosk.

    Lee correcciones_vosk.json y lo recarga solo cuando el archivo cambia,
    así no hace falta reiniciar el servidor después de editarlo.
    """

    def __init__(self, ruta):
        self._ruta = Path(ruta)
        self._bloqueo = threading.Lock()
        self._marca_tiempo = None
        self._equivalencias = {}
        self._patron = None

    def _normalizar(self, texto):
        # Minúsculas y espacios simples, porque Vosk devuelve todo en minúsculas.
        return " ".join(str(texto).lower().split())

    def _recargar_si_cambio(self):
        try:
            marca = self._ruta.stat().st_mtime
        except OSError:
            # Si el archivo no existe, no se corrige nada.
            if self._marca_tiempo is not None:
                self._equivalencias, self._patron = {}, None
                self._marca_tiempo = None
            return

        if marca == self._marca_tiempo:
            return

        # Se guarda la marca aunque falle, para no reintentar (y no spamear
        # el log) hasta que el archivo vuelva a modificarse.
        self._marca_tiempo = marca

        try:
            datos = json.loads(self._ruta.read_text(encoding="utf-8"))
            if not isinstance(datos, dict):
                raise ValueError("el archivo debe ser un objeto { ... }")
        except (OSError, ValueError) as error:
            registro.warning(
                "No se pudo leer %s (%s). Se mantienen las correcciones anteriores.",
                self._ruta.name,
                error,
            )
            return

        equivalencias = {}
        for original, correccion in datos.items():
            # Las claves que empiezan con "_" son comentarios y se ignoran.
            if str(original).startswith("_") or not isinstance(correccion, str):
                continue
            clave = self._normalizar(original)
            if clave:
                equivalencias[clave] = correccion.strip()

        if equivalencias:
            # Las frases más largas primero, para que "luz roja" gane a "luz".
            claves = sorted(equivalencias, key=len, reverse=True)
            alternativas = "|".join(re.escape(c).replace(r"\ ", r"\s+") for c in claves)
            # Solo palabras completas: "let" no toca "completo".
            self._patron = re.compile(
                r"(?<!\w)(?:" + alternativas + r")(?!\w)",
                re.IGNORECASE,
            )
        else:
            self._patron = None
        self._equivalencias = equivalencias
        registro.info("Correcciones de Vosk cargadas: %d", len(equivalencias))

    def corregir(self, texto):
        if not texto:
            return texto
        with self._bloqueo:
            self._recargar_si_cambio()
            if self._patron is None:
                return texto
            return self._patron.sub(
                lambda m: self._equivalencias[self._normalizar(m.group(0))],
                texto,
            )


corrector = CorrectorTexto(RUTA_CORRECCIONES)


class ServicioVosk:
    
    def __init__(self):
        
        self._bloqueo = threading.RLock()
        
        self._modelo = None
        
        self._reconocedor = None
        
        self._activo = False
        
        self._error = None

    
    
    def estado(self):
        """Devuelve si las dependencias y el modelo están disponibles."""
        try:
            
            import vosk  
        except ImportError:
            
            return {
                "listo": False,
                "mensaje": "Falta instalar Vosk. Ejecutá: pip install -r requirements.txt",
            }

        
        if not RUTA_MODELO.is_dir():
            return {
                "listo": False,
                "mensaje": (
                    "Falta el modelo de español. Ejecutá "
                    "bash scripts/instalar_modelo.sh"
                ),
            }

        
        return {"listo": True, "mensaje": "Reconocimiento offline disponible."}

    
    def iniciar(self):
        """Carga el modelo una sola vez e inicia una sesión de escucha."""
        with self._bloqueo:
            try:
                
                from vosk import KaldiRecognizer, Model, SetLogLevel
            except ImportError as error:
                
                self._error = str(error)
                raise RuntimeError(
                    "Vosk no está instalado. Ejecutá: pip install -r requirements.txt"
                ) from error

            
            if not RUTA_MODELO.is_dir():
                raise RuntimeError(
                    "No se encontró el modelo de español. Ejecutá "
                    "bash scripts/instalar_modelo.sh"
                )

            try:
                
                if self._modelo is None:
                    
                    SetLogLevel(-1)
                    
                    self._modelo = Model(str(RUTA_MODELO))

                
                self._reconocedor = KaldiRecognizer(
                    self._modelo,
                    FRECUENCIA_MUESTREO,
                )
                
                self._activo = True
                self._error = None
            except Exception as error:
                
                self._error = str(error)
                raise RuntimeError(
                    "No se pudo cargar el modelo de voz. "
                    "Revisá que el modelo se haya descargado correctamente."
                ) from error

    
    
    def procesar_audio(self, audio_pcm, discontinuidad=False):
        """Procesa PCM mono a 16 kHz y devuelve tiempos de espera/proceso.

        ``discontinuidad`` indica que el navegador descartó audio pendiente por
        sobrecarga. En ese caso se limpia el contexto parcial de Vosk para no
        concatenar palabras separadas por un hueco temporal.
        """
        if not audio_pcm or len(audio_pcm) % 2:
            raise ValueError("El fragmento de audio PCM no es válido.")

        inicio_total = perf_counter()
        inicio_espera = perf_counter()

        with self._bloqueo:
            espera_bloqueo_ms = (perf_counter() - inicio_espera) * 1000

            if not self._activo or self._reconocedor is None:
                raise RuntimeError("El reconocimiento de voz no está iniciado.")

            inicio_procesamiento = perf_counter()
            if discontinuidad:
                # Reset() conserva el modelo cargado, pero descarta el contexto
                # acústico parcial que ya no representa audio continuo.
                self._reconocedor.Reset()

            if self._reconocedor.AcceptWaveform(audio_pcm):
                resultado = json.loads(self._reconocedor.Result())
                texto = corrector.corregir(resultado.get("text", "").strip())
                respuesta = {
                    "ok": True,
                    "final": bool(texto),
                    "texto": texto,
                    "parcial": "",
                }
            else:
                parcial = corrector.corregir(
                    json.loads(self._reconocedor.PartialResult()).get("partial", "").strip()
                )
                respuesta = {
                    "ok": True,
                    "final": False,
                    "texto": "",
                    "parcial": parcial,
                }

            fin_procesamiento = perf_counter()
            respuesta["metricas"] = {
                # PCM 16-bit mono a 16 kHz: 32 bytes representan 1 ms.
                "audio_ms": len(audio_pcm) / 32,
                "espera_bloqueo_ms": round(espera_bloqueo_ms, 2),
                "procesamiento_ms": round((fin_procesamiento - inicio_procesamiento) * 1000, 2),
                "servidor_total_ms": round((perf_counter() - inicio_total) * 1000, 2),
                "contexto_reiniciado": bool(discontinuidad),
            }
            return respuesta

    def detener(self):
        with self._bloqueo:
            
            self._activo = False
            self._reconocedor = None



servicio_voz = ServicioVosk()

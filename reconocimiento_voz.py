"""Reconocimiento de voz local usando Vosk y audio PCM mono a 16 kHz."""

import json
import os
import threading
from pathlib import Path


DIRECTORIO_PROYECTO = Path(__file__).resolve().parent
RUTA_MODELO = Path(
    os.environ.get(
        "VOSK_MODEL_PATH",
        DIRECTORIO_PROYECTO / "modelos" / "vosk-model-small-es-0.42",
    )
)
FRECUENCIA_MUESTREO = 16000


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
            import vosk  # noqa: F401
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

    def procesar_audio(self, audio_pcm):
        """Procesa un fragmento de audio PCM 16-bit mono a 16 kHz."""
        if not audio_pcm or len(audio_pcm) % 2:
            raise ValueError("El fragmento de audio PCM no es válido.")

        with self._bloqueo:
            if not self._activo or self._reconocedor is None:
                raise RuntimeError("El reconocimiento de voz no está iniciado.")

            if self._reconocedor.AcceptWaveform(audio_pcm):
                resultado = json.loads(self._reconocedor.Result())
                texto = resultado.get("text", "").strip()
                return {
                    "ok": True,
                    "final": bool(texto),
                    "texto": texto,
                    "parcial": "",
                }

            parcial = json.loads(self._reconocedor.PartialResult()).get(
                "partial", ""
            ).strip()
            return {
                "ok": True,
                "final": False,
                "texto": "",
                "parcial": parcial,
            }

    def detener(self):
        with self._bloqueo:
            self._activo = False
            self._reconocedor = None


servicio_voz = ServicioVosk()

#!/usr/bin/env bash
# ┌─────────────────────────────────────────────────────────────────────────┐
# │ scripts/instalar_modelo.sh: DESCARGA EL MODELO DE VOZ EN ESPAÑOL        │
# │ Se ejecuta UNA vez (necesita internet): bash scripts/instalar_modelo.sh │
# │ Deja el modelo en modelos/vosk-model-small-es-0.42, que es la carpeta   │
# │ que busca reconocimiento_voz.py (RUTA_MODELO). Sin ese modelo, app.py   │
# │ avisa «Falta el modelo de español» en la página.                        │
# │ No usa ningún otro archivo del proyecto.                                │
# └─────────────────────────────────────────────────────────────────────────┘
# set -e: detiene el script ante cualquier error; -u: error si se usa una variable sin definir; pipefail: falla si falla algún paso de una tubería.
set -euo pipefail

# Carpeta raíz del proyecto: la carpeta anterior a «scripts/», sin importar desde dónde se ejecute el script.
PROYECTO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Nombre del modelo (es el que busca reconocimiento_voz.py), carpeta destino y dirección de descarga.
NOMBRE_MODELO="vosk-model-small-es-0.42"
DIRECTORIO_MODELOS="$PROYECTO_DIR/modelos"
DIRECTORIO_MODELO="$DIRECTORIO_MODELOS/$NOMBRE_MODELO"
URL_MODELO="https://alphacephei.com/vosk/models/${NOMBRE_MODELO}.zip"

# Si el modelo ya está instalado (existen sus archivos principales), avisa y termina sin descargar nada.
if [[ -f "$DIRECTORIO_MODELO/am/final.mdl" && -d "$DIRECTORIO_MODELO/conf" ]]; then
    echo "El modelo español de Vosk ya está instalado en: $DIRECTORIO_MODELO"
    exit 0
fi

# Comprueba que estén instaladas las dos herramientas necesarias: curl (descargar) y unzip (descomprimir).
for comando in curl unzip; do
    if ! command -v "$comando" >/dev/null 2>&1; then
        echo "Falta '$comando'. Instalalo con: sudo apt install curl unzip" >&2
        exit 1
    fi
done

# Crea una carpeta temporal para trabajar; la línea siguiente garantiza que se borre al terminar, aunque haya errores. Después crea la carpeta modelos/ si no existe.
TEMPORAL="$(mktemp -d)"
trap 'rm -rf "$TEMPORAL"' EXIT
mkdir -p "$DIRECTORIO_MODELOS"

echo "Descargando el modelo de voz en español (aprox. 40 MB)..."
# Descarga el ZIP (--fail: error si el servidor falla; --location: sigue redirecciones; --retry 3: reintenta hasta 3 veces) y lo descomprime en la carpeta temporal.
curl --fail --location --retry 3 "$URL_MODELO" --output "$TEMPORAL/modelo.zip"
echo "Descomprimiendo el modelo..."
unzip -q "$TEMPORAL/modelo.zip" -d "$TEMPORAL"

# Verifica que lo descargado sea realmente un modelo de Vosk antes de instalarlo.
if [[ ! -f "$TEMPORAL/$NOMBRE_MODELO/am/final.mdl" || ! -d "$TEMPORAL/$NOMBRE_MODELO/conf" ]]; then
    echo "La descarga no contiene un modelo Vosk válido." >&2
    exit 1
fi

# Reemplaza cualquier instalación incompleta anterior por el modelo recién descargado.
rm -rf "$DIRECTORIO_MODELO"
mv "$TEMPORAL/$NOMBRE_MODELO" "$DIRECTORIO_MODELO"
echo "Modelo instalado correctamente: $DIRECTORIO_MODELO"
echo "A partir de ahora el reconocimiento funciona sin conexión a internet."

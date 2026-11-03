#!/usr/bin/env bash
set -euo pipefail

PROYECTO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NOMBRE_MODELO="vosk-model-small-es-0.42"
DIRECTORIO_MODELOS="$PROYECTO_DIR/modelos"
DIRECTORIO_MODELO="$DIRECTORIO_MODELOS/$NOMBRE_MODELO"
URL_MODELO="https://alphacephei.com/vosk/models/${NOMBRE_MODELO}.zip"

if [[ -f "$DIRECTORIO_MODELO/am/final.mdl" && -d "$DIRECTORIO_MODELO/conf" ]]; then
    echo "El modelo español de Vosk ya está instalado en: $DIRECTORIO_MODELO"
    exit 0
fi

for comando in curl unzip; do
    if ! command -v "$comando" >/dev/null 2>&1; then
        echo "Falta '$comando'. Instalalo con: sudo apt install curl unzip" >&2
        exit 1
    fi
done

TEMPORAL="$(mktemp -d)"
trap 'rm -rf "$TEMPORAL"' EXIT
mkdir -p "$DIRECTORIO_MODELOS"

echo "Descargando el modelo de voz en español (aprox. 40 MB)..."
curl --fail --location --retry 3 "$URL_MODELO" --output "$TEMPORAL/modelo.zip"
echo "Descomprimiendo el modelo..."
unzip -q "$TEMPORAL/modelo.zip" -d "$TEMPORAL"

if [[ ! -f "$TEMPORAL/$NOMBRE_MODELO/am/final.mdl" || ! -d "$TEMPORAL/$NOMBRE_MODELO/conf" ]]; then
    echo "La descarga no contiene un modelo Vosk válido." >&2
    exit 1
fi

rm -rf "$DIRECTORIO_MODELO"
mv "$TEMPORAL/$NOMBRE_MODELO" "$DIRECTORIO_MODELO"
echo "Modelo instalado correctamente: $DIRECTORIO_MODELO"
echo "A partir de ahora el reconocimiento funciona sin conexión a internet."

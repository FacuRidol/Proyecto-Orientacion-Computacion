# Proyecto de control de dispositivos con Raspberry Pi 3

Interfaz web en Flask para controlar cuatro LED, un servomotor SG90 y un sensor ultrasónico HC-SR04. El reconocimiento de voz se hace **localmente en la Raspberry Pi con Vosk**, sin enviar el audio a servicios externos.

## Qué se agregó

- Reconocimiento offline compatible con Firefox y Chromium: el navegador captura el micrófono y envía audio PCM al servidor Flask; Vosk lo convierte en texto en la Raspberry Pi.
- Botón para activar y apagar el micrófono.
- Control por voz de los LED, el ángulo del servo y la activación/desactivación de la medición ultrasónica.
- El sensor ultrasónico arranca desactivado. Cuando se activa, la interfaz actualiza la distancia aproximadamente una vez por segundo.
- Mensajes en la página para indicar si faltan Vosk o el modelo de español.

## Pines GPIO

Se conservan los pines existentes (numeración BCM):

| Dispositivo | GPIO BCM | Pin físico |
|---|---:|---:|
| LED 1 | 17 | 11 |
| LED 2 | 27 | 13 |
| LED 3 | 22 | 15 |
| LED 4 | 23 | 16 |
| Servo SG90 | 18 | 12 |
| HC-SR04 TRIG | 24 | 18 |
| HC-SR04 ECHO | 25 | 22 |

**Importante:** el pin ECHO del HC-SR04 suele entregar 5 V. Si la conexión actual no incluye adaptación a 3,3 V, no conectes ECHO directamente a la Raspberry Pi. Conservá el cableado seguro que ya tenían validado.

## Instalación inicial (necesita internet una sola vez)

Abrí una terminal de la Raspberry Pi y entrá en la carpeta real del proyecto. Usá el mismo intérprete o entorno virtual con el que hoy ejecutás la aplicación; no hace falta crear otro si el actual ya funciona. Ejemplo si usás `env`:

```bash
cd "/home/alumno/Proyecto Ridolfi-Rosset-Sainz-Salaberry/Proyecto-Orientacion-Computacion"
source env/bin/activate
python -m pip install -r requirements.txt
bash scripts/instalar_modelo.sh
```

El script descarga el modelo pequeño de español de Vosk (aprox. 40 MB) dentro de `modelos/vosk-model-small-es-0.42/`. No hace falta volver a descargarlo cada vez. Una vez instalados `vosk` y el modelo, el reconocimiento de voz funciona sin internet.

Si necesitás crear un entorno nuevo, usá `--system-site-packages` para que pueda acceder a los paquetes GPIO instalados en Raspberry Pi OS:

```bash
python3 -m venv --system-site-packages env
source env/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

En Raspberry Pi OS, `RPi.GPIO` debe seguir instalado en el sistema y disponible para el entorno virtual. No se intenta instalarlo automáticamente desde `requirements.txt` para no reemplazar la instalación de GPIO ya funcional.

## Certificados HTTPS y arranque

Los certificados no se incluyen en este paquete por seguridad. Conservá la carpeta `certs/` ya creada en tu Raspberry Pi. `app.py` sigue usando las rutas existentes:

- `certs/172.16.4.102.pem`
- `certs/172.16.4.102-key.pem`

Para arrancar la aplicación:

```bash
source env/bin/activate
python app.py
```

Después abrí en Firefox o Chromium la misma URL HTTPS que ya venías usando. Aceptá el permiso del micrófono cuando el navegador lo solicite. No uses una URL HTTP para la captura de audio.

## Comandos de voz

Decí los comandos después de pulsar **Activar micrófono**:

- `Encender LED uno` / `Apagar LED cuatro` (también acepta números como `LED 2`).
- `Servo a noventa grados` / `Servo a 45 grados` (entre 0 y 180).
- `Activar sensor` o `Encender sensor`: inicia la medición continua.
- `Desactivar sensor` o `Apagar sensor`: detiene las mediciones.
- `Medir distancia`, `¿qué distancia hay?`, `cerca` o `lejos`: solicita una lectura cuando el sensor está activo.

El audio se procesa en la Raspberry Pi. La captura continúa únicamente mientras el botón del micrófono esté activo. La lectura en vivo del HC-SR04 se activa y desactiva de forma independiente del micrófono.

## Actualizar el código sin perder HTTPS

Al copiar los archivos modificados, no borres la carpeta `certs/` ni el entorno `env/` existente. El ZIP de entrega omite deliberadamente esos elementos locales; contiene el código y los scripts necesarios para instalar el componente de voz.

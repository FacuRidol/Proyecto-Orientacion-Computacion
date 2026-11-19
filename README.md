# Proyecto de control de dispositivos con Raspberry Pi 3

Aplicación web local desarrollada con **Python y Flask** para controlar desde un navegador cuatro LED, un servomotor SG90 y un sensor ultrasónico HC-SR04. Incluye controles manuales, comandos de voz, automatizaciones basadas en la distancia medida, un gráfico de mediciones y un registro de actividad.

El reconocimiento de voz se procesa **localmente en la Raspberry Pi mediante Vosk**. El navegador captura el audio del micrófono y lo envía al servidor Flask para su transcripción; el asistente muestra sus respuestas como texto dentro de la página y puede leerlas en voz alta con la síntesis de voz del navegador (se activa o desactiva con una casilla), sin depender de servicios externos de reconocimiento.

Este README reúne la guía para instalar y poner en marcha el proyecto desde cero y, al final, la bitácora de actualizaciones y mejoras documentadas durante su desarrollo.

# Guía de instalación y puesta en marcha

## Resumen del proceso de instalación

La siguiente tabla muestra el orden recomendado para preparar el proyecto desde cero. Cada paso está desarrollado con sus comandos y explicaciones en las secciones correspondientes de esta guía.

| Orden | Título del paso | ¿Qué hará el usuario? |
|---:|---|---|
| 1 | Preparar los componentes y realizar las conexiones | Reunirá la Raspberry Pi, los LED, el servomotor y el sensor ultrasónico, y realizará el cableado siguiendo las tablas de pines y las precauciones eléctricas. |
| 2 | Instalar Raspberry Pi OS | Preparará la microSD, instalará el sistema operativo y configurará el usuario, la red Wi-Fi o Ethernet y, si lo necesita, SSH. |
| 3 | Preparar la Raspberry Pi | Actualizará el sistema e instalará Git, Python, herramientas de compilación, `mkcert` y el paquete de GPIO necesario. |
| 4 | Descargar el proyecto desde GitHub | Clonará el repositorio o descargará el ZIP y entrará en la carpeta donde se encuentra `app.py`. |
| 5 | Crear el entorno virtual e instalar las librerías | Creará `env`, lo activará e instalará las dependencias de Python indicadas en `requirements.txt`. |
| 6 | Instalar el modelo de reconocimiento de voz | Ejecutará el script incluido para descargar o comprobar el modelo de español que utiliza Vosk. |
| 7 | Generar los certificados HTTPS | Averiguará la IP y el nombre de la Raspberry Pi y generará el certificado y la clave privada que Flask necesita para habilitar el micrófono. |
| 8 | Confiar en el certificado desde los dispositivos clientes | Instalará el certificado raíz público en cada computadora, teléfono o tableta desde los que vaya a abrir la página. La clave privada de la autoridad nunca se debe compartir. |
| 9 | Iniciar el servidor web | Activará el entorno virtual y ejecutará `python app.py` para poner en marcha Flask y conectar el software con los dispositivos. |
| 10 | Abrir la web y probar el sistema | Entrará a la dirección HTTPS desde Firefox, Chrome o Chromium, concederá permiso para usar el micrófono y comprobará los controles y comandos de voz. |
| 11 | Configurar el asistente y, opcionalmente, el inicio automático | Personalizará las palabras de activación y los sinónimos desde la página. Si lo desea, configurará el servicio para iniciar el proyecto al encender la Raspberry Pi. |

> **Importante:** para que el reconocimiento de voz funcione desde otro dispositivo, ese dispositivo debe poder acceder a la Raspberry Pi por la red, confiar en el certificado HTTPS y conceder permiso al navegador para utilizar su micrófono.

---

## 1. Funciones incluidas

- Panel web para encender y apagar cuatro LED.
- Control de posición de un servomotor SG90 entre 0° y 180°.
- Lectura de distancia con un sensor ultrasónico HC-SR04.
- Reconocimiento de voz offline mediante Vosk y un modelo de español.
- Respuesta escrita de bienvenida al detectar una palabra de activación.
- Dos modos de comandos de voz:
  - **Modo estricto:** se pronuncia una palabra de activación antes de cada comando.
  - **Modo de sesión:** se pronuncia una vez y se pueden dar varios comandos sin repetirla. La sesión se cierra luego de 30 segundos sin actividad o al decir «cerrar asistente».
- Ejecución de varias acciones independientes en una misma frase, por ejemplo: «robot encender LED uno y activar sensor».
- Configuración desde la web de las palabras de activación y de sinónimos para encender, apagar, LED, sensor y servo.
- Posibilidad de asignar nombres personalizados a los LED.
- Automatizaciones por distancia, por ejemplo: cuando un objeto se acerca a menos de cierta distancia, encender un LED.
- Gráfico del historial de distancia y registro de los comandos reconocidos.
- Sincronización del estado entre navegadores conectados a la misma instancia de Flask.
- Tema claro y oscuro.

## 2. Requisitos

### 2.1. Hardware

| Elemento | Cantidad | Observaciones |
|---|---:|---|
| Raspberry Pi 3 | 1 | Modelo B/B+ recomendado. |
| Fuente para Raspberry Pi | 1 | Fuente estable y adecuada para el modelo. |
| Tarjeta microSD | 1 | Se recomienda 16 GB como mínimo; 32 GB deja más espacio. |
| LED | 4 | Cualquier LED común de baja potencia. |
| Resistencias para LED | 4 | Una por LED, normalmente entre 220 Ω y 330 Ω. |
| Servomotor SG90 | 1 | Incluye cable de señal, alimentación y GND. |
| Sensor ultrasónico HC-SR04 | 1 | Módulo de cuatro pines: VCC, TRIG, ECHO y GND. |
| Resistencias para divisor de tensión | 2 | Una de 1 kΩ y otra de 2 kΩ para adaptar ECHO. También se puede usar un conversor de nivel lógico adecuado. |
| Protoboard y cables Dupont | Según necesidad | Para realizar las conexiones. |
| Fuente externa regulada para el servo | 1 | Debe entregar 5 V y soportar la corriente que requiera el servo. |
| Micrófono | 1 | Puede ser el integrado en la computadora, un micrófono USB o el del dispositivo desde el que se abre la web. |

**Importante sobre la alimentación y los GPIO:** los pines GPIO de la Raspberry Pi trabajan con lógica de 3,3 V y no son tolerantes a 5 V. No conectes una señal de 5 V directamente a un GPIO. Desconectá la alimentación antes de cambiar el cableado y revisá dos veces las conexiones antes de encender el circuito.

El servo no debe alimentarse desde el pin de 3,3 V de la Raspberry Pi. Se recomienda una fuente externa regulada de 5 V para el servo y conectar el GND de esa fuente al GND de la Raspberry Pi para compartir la referencia eléctrica.

### 2.2. Software y red

- Raspberry Pi OS instalado en la Raspberry Pi 3.
- Acceso a Internet durante la instalación para descargar paquetes y, si hace falta, el modelo de Vosk.
- Una conexión de red local: Wi-Fi o Ethernet.
- Una computadora, tableta o teléfono conectado a la misma red para abrir la interfaz. También se puede abrir un navegador en la propia Raspberry Pi si tiene escritorio.
- Un navegador actualizado: Firefox, Chromium o Google Chrome.
- Permiso para utilizar el micrófono en el navegador que se use.

La captura de micrófono se realiza con APIs web estándar, mientras que Vosk procesa el audio en Python. Así se evita depender del reconocimiento de voz particular de cada navegador. La compatibilidad concreta debe comprobarse con la versión del navegador y el micrófono de cada dispositivo.

---

## 3. Conectar los componentes a la Raspberry Pi

### 3.1. Numeración de pines

El programa utiliza la numeración **BCM** de GPIO, no la numeración física del conector. La siguiente tabla muestra ambas para evitar confusiones.

| Componente | Señal | GPIO (BCM) | Pin físico de la Raspberry Pi |
|---|---|---:|---:|
| LED 1 | Señal | GPIO 17 | 11 |
| LED 2 | Señal | GPIO 27 | 13 |
| LED 3 | Señal | GPIO 22 | 15 |
| LED 4 | Señal | GPIO 23 | 16 |
| Los cuatro LED | Retorno | GND | Por ejemplo, pin 6 |
| Servo SG90 | Señal | GPIO 18 | 12 |
| HC-SR04 | TRIG | GPIO 24 | 18 |
| HC-SR04 | ECHO (a través del divisor) | GPIO 25 | 22 |
| HC-SR04 | VCC | 5 V | Pin 2 o 4 |
| HC-SR04 | GND | GND | Por ejemplo, pin 6 |

Consultá también el [diagrama oficial de pines de Raspberry Pi](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio).

### 3.2. Conectar los LED

Repetí esta conexión para cada LED:

1. Conectá el GPIO correspondiente a una resistencia de 220 Ω a 330 Ω.
2. Conectá el otro extremo de la resistencia a la pata larga del LED (ánodo).
3. Conectá la pata corta del LED (cátodo) a GND.
4. Repetí con los GPIO 17, 27, 22 y 23.

Cada LED debe tener su propia resistencia. No conectes un LED directamente entre un GPIO y GND.

### 3.3. Conectar el servomotor SG90

Los cables suelen identificarse así, aunque conviene confirmar los colores del modelo comprado:

| Cable habitual | Conexión |
|---|---|
| Naranja o amarillo (señal) | GPIO 18, pin físico 12 |
| Rojo (alimentación) | Positivo de la fuente externa regulada de 5 V |
| Marrón o negro (GND) | GND de la fuente externa y GND común con la Raspberry Pi |

No alimentes el servo desde el pin de 3,3 V. Evitá que la corriente del servo pase por la protoboard o por una salida GPIO. Si la Raspberry Pi se reinicia al mover el servo, revisá la fuente externa, el cableado y la conexión de GND común.

### 3.4. Conectar el sensor HC-SR04

| Pin del HC-SR04 | Conexión |
|---|---|
| VCC | 5 V de la Raspberry Pi (pin físico 2 o 4) |
| GND | GND de la Raspberry Pi |
| TRIG | GPIO 24, pin físico 18 |
| ECHO | GPIO 25, pin físico 22 **a través de un divisor de tensión** |

**No conectes ECHO directamente a la Raspberry Pi.** El pin ECHO del HC-SR04 puede entregar 5 V y el GPIO de la Raspberry Pi admite hasta 3,3 V.

Un divisor resistivo de ejemplo:

```text
HC-SR04 ECHO ----[ 1 kΩ ]-----+---- GPIO 25 (pin físico 22)
                             |
                           [ 2 kΩ ]
                             |
                            GND
```

El TRIG se conecta directamente desde GPIO 24 al sensor. Verificá la disposición y el valor de las resistencias antes de alimentar el circuito.

---

## 4. Instalar Raspberry Pi OS

Se recomienda utilizar una versión actual de **Raspberry Pi OS**. Raspberry Pi 3 B/B+ admite la edición de 64 bits. Si el modelo exacto o algún accesorio requiere 32 bits, elegí esa edición.

1. En otra computadora, descargá e instalá [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
2. Insertá la microSD en esa computadora.
3. En Raspberry Pi Imager, seleccioná el modelo de Raspberry Pi, Raspberry Pi OS y la tarjeta microSD correcta. Elegí **Desktop** si vas a abrir el navegador directamente en la Raspberry Pi; elegí **Lite** si la Raspberry Pi funcionará solo como servidor y vas a abrir la web desde otra computadora o teléfono.
4. En la configuración del sistema, definí un nombre para la Raspberry Pi, un usuario y una contraseña.
5. Configurá Wi-Fi si no vas a utilizar Ethernet.
6. Activá SSH si querés administrar la Raspberry Pi desde otra computadora sin conectar monitor y teclado.
7. Escribí el sistema operativo en la tarjeta, insertala en la Raspberry Pi y encendela.

**Atención:** al escribir el sistema operativo se borra el contenido anterior de la microSD. Hacé una copia de seguridad de los archivos importantes.

Cuando inicie por primera vez, abrí una terminal en la Raspberry Pi o conectate por SSH. Actualizá el sistema:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo reboot
```

Después del reinicio, volvé a abrir la terminal.

---

## 5. Preparar la Raspberry Pi

### 5.1. Instalar herramientas del sistema

Ejecutá:

```bash
sudo apt update
sudo apt install -y \
  git \
  python3 \
  python3-venv \
  python3-full \
  python3-pip \
  python3-dev \
  build-essential \
  libffi-dev \
  curl \
  unzip \
  openssl \
  ca-certificates \
  mkcert \
  libnss3-tools
```

Estas herramientas sirven para descargar el repositorio, crear el entorno virtual, instalar dependencias, descargar el modelo de voz y generar certificados HTTPS locales.

### 5.2. Instalar el soporte GPIO

El módulo de hardware del proyecto importa `RPi.GPIO`. Instalalo con el gestor de paquetes del sistema, no con `pip` dentro del entorno virtual.

Primero consultá qué paquete está disponible:

```bash
apt-cache policy python3-rpi.gpio python3-rpi-lgpio
```

En una instalación que ofrezca el paquete original, ejecutá:

```bash
sudo apt install -y python3-rpi.gpio
```

Si tu versión de Raspberry Pi OS no ofrece ese paquete, podés utilizar el paquete compatible `python3-rpi-lgpio`:

```bash
sudo apt install -y python3-rpi-lgpio
```

**Instalá uno solo, no ambos.** Los dos proporcionan el módulo `RPi.GPIO` y no deben coexistir en el mismo entorno.

Si el programa informa que no tiene permisos para acceder a los GPIO, comprobá si existe el grupo `gpio` y si tu usuario pertenece a él:

```bash
getent group gpio
groups
```

Si el grupo existe y tu usuario no aparece en él:

```bash
sudo usermod -aG gpio "$USER"
sudo reboot
```

Volvé a iniciar sesión después del reinicio para que se apliquen los grupos.

---

## 6. Descargar el proyecto desde GitHub

En GitHub, abrí el repositorio del proyecto y copiá su dirección HTTPS. En la terminal de la Raspberry Pi, ejecutá el comando reemplazando el ejemplo por la dirección real:

```bash
git clone https://github.com/USUARIO/REPOSITORIO.git
cd REPOSITORIO
```

`USUARIO` y `REPOSITORIO` son marcadores de ejemplo: deben reemplazarse por la organización o cuenta y el nombre reales del repositorio.

Si descargaste el proyecto como un archivo ZIP desde GitHub, descomprimilo y entrá en la carpeta que contiene `app.py`.

A partir de este momento, ejecutá los comandos desde la carpeta principal del proyecto. Podés comprobarlo con:

```bash
ls
```

Deberías encontrar, entre otros, `app.py`, `servidor/`, `funciones/`, `correcciones_vosk.json`, `requirements.txt`, `templates/`, `static/`, `modelos/` y `scripts/`.

---

## 7. Crear el entorno virtual de Python

El entorno virtual mantiene separadas las librerías del proyecto de las librerías del sistema. En versiones recientes de Raspberry Pi OS, `pip` no debe instalar paquetes directamente en el Python global.

**Importante:** se utiliza `--system-site-packages` para que el entorno virtual pueda acceder al paquete GPIO instalado previamente mediante `apt`.

Desde la carpeta principal del proyecto, ejecutá:

```bash
python3 -m venv --system-site-packages env
source env/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

El archivo `requirements.txt` instala las dependencias Python del proyecto:

| Paquete | Uso |
|---|---|
| Flask | Servidor web y API para la interfaz. |
| Vosk | Reconocimiento de voz local y offline. |

`RPi.GPIO` se instala por separado con `apt`, como se explicó en el apartado anterior.

**Nota sobre versiones de Python y Vosk:** el proyecto fija `vosk==0.3.45`. PyPI publica paquetes Linux para ARMv7 y ARM64, pero la documentación de instalación de Vosk consultada enumera versiones de Python probadas más antiguas que las de algunas imágenes recientes de Raspberry Pi OS. Por eso, la instalación debe comprobarse en la versión concreta de Raspberry Pi OS elegida. Si `pip install -r requirements.txt` falla al instalar Vosk, no fuerces la instalación sobre el Python del sistema ni uses `--break-system-packages`; consultá la documentación vigente de Vosk y verificá una combinación compatible de Python, arquitectura y wheel.

Cada vez que abras una terminal nueva para trabajar en el proyecto, activá el entorno antes de ejecutar Python:

```bash
cd /ruta/a/REPOSITORIO
source env/bin/activate
```

Para salir del entorno virtual:

```bash
deactivate
```

Podés comprobar que las dependencias principales se importan correctamente con:

```bash
python -c "import flask, vosk, RPi.GPIO; print('Dependencias disponibles')"
```

Si aparece un error al importar `RPi.GPIO`, revisá que instalaste el paquete de GPIO con `apt` y que el entorno virtual se creó con `--system-site-packages`.

---

## 8. Instalar el modelo de voz en español

Vosk necesita un modelo acústico para reconocer el idioma. El proyecto utiliza el modelo pequeño de español:

```text
modelos/vosk-model-small-es-0.42/
```

Desde la carpeta principal del proyecto y con el entorno virtual activado, ejecutá:

```bash
bash scripts/instalar_modelo.sh
```

El script comprueba si el modelo ya está presente. Si falta, lo descarga de la fuente de modelos de Vosk y lo instala en la carpeta `modelos/`.

La primera descarga necesita conexión a Internet. Una vez instalado el modelo, el reconocimiento se procesa localmente y no necesita enviar el audio a un servicio externo.

Si el proyecto ya descargado incluye el modelo, el script indicará que está instalado y no volverá a descargarlo.

---

## 9. Configurar HTTPS para habilitar el micrófono

### 9.1. ¿Por qué hace falta HTTPS?

Los navegadores modernos exigen un contexto seguro para permitir el acceso al micrófono con `getUserMedia()`. Cuando se abre la web desde otra computadora usando la dirección local de la Raspberry Pi, no alcanza con escribir `http://`.

Por eso, esta aplicación inicia Flask con HTTPS en el puerto `5000` y utiliza dos archivos de certificado. Los archivos no se incluyen en GitHub porque cada instalación tiene una dirección de red propia y su clave privada debe permanecer protegida.

### 9.2. Averiguar la dirección de la Raspberry Pi

En la terminal de la Raspberry Pi, ejecutá:

```bash
hostname -I
```

Anotá la dirección IP local, por ejemplo `192.168.1.50`. En los comandos de este README se utiliza la variable `PI_IP` para representar esa dirección.

Es recomendable configurar en el router una **reserva DHCP** para que la Raspberry Pi reciba siempre la misma dirección. Si la dirección cambia, la URL y el certificado pueden dejar de coincidir.

También podés obtener el nombre de host con:

```bash
hostname
```

### 9.3. Generar una autoridad local y el certificado del servidor

El proyecto utiliza `mkcert` para generar certificados confiables en una red local. En la Raspberry Pi, desde la carpeta principal del proyecto, ejecutá:

```bash
mkdir -p certs

PI_IP="$(hostname -I | awk '{print $1}')"
PI_HOST="$(hostname).local"

mkcert -install

mkcert \
  -cert-file certs/172.16.4.102.pem \
  -key-file certs/172.16.4.102-key.pem \
  "$PI_IP" \
  "$PI_HOST"

chmod 600 certs/172.16.4.102-key.pem
```

Si `hostname -I` devuelve más de una dirección o no muestra la dirección que usarán, reemplazá manualmente el valor de `PI_IP`. Por ejemplo:

```bash
PI_IP="192.168.1.50"
```

**No cambies los nombres de archivo del comando.** Aunque incluyen la antigua dirección `172.16.4.102`, el servidor (`servidor/config.py`) busca exactamente estos dos nombres:

```text
certs/172.16.4.102.pem
certs/172.16.4.102-key.pem
```

La dirección válida no se determina por el nombre del archivo: queda incluida dentro del certificado porque se pasa como argumento a `mkcert`. Por eso, aunque tu Raspberry Pi tenga otra IP, los archivos deben conservar esos nombres y el certificado debe incluir la IP real.

`mkcert -install` crea una autoridad certificadora local e instala su certificado raíz en los almacenes de confianza compatibles del usuario que ejecuta el comando. El certificado del servidor se firma con esa autoridad.

### 9.4. Confiar en el certificado desde los otros dispositivos

El paso anterior instala la autoridad local en la Raspberry Pi, pero **no instala automáticamente la confianza en las computadoras, tabletas o teléfonos desde los que se abra la web**.

Para evitar el aviso de certificado no confiable y habilitar correctamente el micrófono, hay que instalar el certificado raíz de esa autoridad en cada dispositivo cliente que vaya a utilizar la página.

En la Raspberry Pi, consultá la ubicación del certificado raíz:

```bash
mkcert -CAROOT
```

Dentro de esa carpeta se encuentra `rootCA.pem`. Ese es el certificado público de la autoridad local que hay que copiar a los dispositivos clientes.

**No copies ni compartas `rootCA-key.pem`.** Ese archivo es la clave privada de la autoridad certificadora y debe quedar protegida en la Raspberry Pi.

#### En otra computadora Linux basada en Debian o Ubuntu

Copiá `rootCA.pem` a la computadora cliente. Después ejecutá:

```bash
sudo install -m 0644 rootCA.pem \
  /usr/local/share/ca-certificates/proyecto-asistente-local.crt
sudo update-ca-certificates
```

Cerrá por completo y volvé a abrir Chrome o Chromium.

#### En Firefox

Si Firefox no utiliza automáticamente el almacén de certificados del sistema:

1. Abrí Firefox.
2. Entrá en **Configuración → Privacidad y seguridad → Certificados**.
3. Seleccioná **Ver certificados**.
4. Abrí la pestaña **Autoridades** y seleccioná **Importar**.
5. Elegí el archivo `rootCA.pem`.
6. Marcá la opción para confiar en esa autoridad para identificar sitios web.
7. Confirmá y reiniciá Firefox.

Los nombres exactos de los menús pueden variar ligeramente según la versión.

#### En Windows

1. Copiá `rootCA.pem` al equipo cliente.
2. Si Windows no reconoce el formato PEM, convertí el certificado desde la Raspberry Pi o desde una computadora que tenga OpenSSL: `openssl x509 -in rootCA.pem -outform DER -out rootCA.cer`.
3. Abrí `rootCA.cer` y seleccioná la opción para instalar el certificado.
4. Elegí el almacén **Entidades de certificación raíz de confianza**. Instalalo en el usuario actual salvo que la administración del equipo indique otra cosa.
5. Cerrá y volvé a abrir el navegador.

#### En macOS

1. Copiá `rootCA.pem` al equipo cliente.
2. Abrilo con Acceso a Llaveros e importalo en el llavero correspondiente.
3. Configurá la confianza de esa autoridad para identificar sitios web.
4. Cerrá y volvé a abrir el navegador.

Instalá únicamente el certificado raíz que recibiste de una Raspberry Pi en la que confiás. No instales certificados raíz desconocidos.

### 9.5. Comprobar los archivos HTTPS

Desde la carpeta del proyecto, ejecutá:

```bash
ls -l certs/
```

Deben existir:

```text
certs/172.16.4.102.pem
certs/172.16.4.102-key.pem
```

El archivo terminado en `-key.pem` contiene la clave privada del servidor. No lo publiques en GitHub ni lo envíes a otros dispositivos.

---

## 10. Iniciar la aplicación

Asegurate de estar en la carpeta principal del proyecto. Activá el entorno virtual y ejecutá Flask:

```bash
source env/bin/activate
python app.py
```

La aplicación queda escuchando en todas las interfaces de red (`0.0.0.0`) en el puerto `5000`, utilizando los certificados HTTPS que generaste.

Para detenerla, volvé a la terminal donde se está ejecutando y presioná `Ctrl + C`.

### 10.1. Abrir la página

Desde un navegador de un dispositivo conectado a la misma red, ingresá:

```text
https://IP_DE_LA_RASPBERRY:5000
```

Por ejemplo:

```text
https://192.168.1.50:5000
```

Reemplazá el ejemplo por la IP real de la Raspberry Pi. También podés utilizar el nombre `hostname.local` si tu red admite resolución mDNS y el certificado fue generado con ese nombre.

La primera vez, el navegador puede pedir permiso para utilizar el micrófono. Seleccioná **Permitir**. El permiso se concede en el dispositivo donde está abierto el navegador: si abrís la web desde una notebook, se utiliza el micrófono de esa notebook, no el de la Raspberry Pi.

Si el navegador informa que el certificado no es confiable, revisá el paso 9.4. No continúes ignorando el aviso como solución habitual: instalá correctamente el certificado raíz y comprobá que la dirección utilizada coincida con una de las identidades incluidas en el certificado.

### 10.2. Acceso desde varios navegadores

Firefox, Chrome y Chromium pueden conectarse a la misma dirección HTTPS. Cada navegador debe:

- Estar actualizado.
- Tener permiso para usar el micrófono.
- Confiar en el certificado raíz local.
- Estar conectado a la red donde se encuentra la Raspberry Pi.

Todos los navegadores se comunican con la misma aplicación Flask. No inicies varias copias de `app.py`: el proyecto mantiene el estado del hardware y de algunos servicios en memoria dentro de un solo proceso.

---

## 11. Primer uso y comandos de voz

### 11.1. Activar el micrófono

1. Abrí la web por HTTPS.
2. Buscá el panel de reconocimiento de voz.
3. Pulsá **Activar micrófono**.
4. Aceptá el permiso del navegador si aparece.
5. Comprobá el texto reconocido en el cuadro **Texto que interpreta Vosk en tiempo real**.

El asistente no responde por audio: los mensajes de bienvenida, confirmación y error se muestran escritos en la página.

### 11.2. Palabras de activación predeterminadas

La primera vez se utilizan:

- `comando`
- `robot`
- `Viernes`

Se pueden modificar desde el panel **Configuración del asistente**. Elegí palabras que Vosk pueda reconocer claramente y que no se confundan con el contenido habitual de los comandos.

### 11.3. Modos de funcionamiento

**Modo estricto**

Cada comando debe comenzar con una palabra de activación:

```text
robot encender led uno
comando activar sensor
viernes giro a cuarenta y cinco grados
```

**Modo de sesión**

Decí una palabra de activación una sola vez. Después podés dar varios comandos sin repetirla:

```text
robot
encender led uno
activar sensor
giro a cuarenta y cinco grados
```

La sesión termina luego de 30 segundos sin actividad. También se puede decir `cerrar asistente`.

### 11.4. Ejemplos de comandos

**LED**

```text
comando encender led uno
comando apagar led dos
comando encender todas las luces
comando apagar todos los leds
```

También se pueden asignar nombres propios a los LED desde la interfaz, por ejemplo `cocina`, y utilizar ese nombre en los comandos.

**Servo**

```text
comando giro a 45 grados
comando giro a ciento treinta y cinco grados
comando giro al centro
```

Los ángulos permitidos son números enteros de 0 a 180 grados.

**Sensor**

```text
comando activar sensor
comando desactivar sensor
comando medir distancia
```

El sensor comienza desactivado. Para consultar mediciones continuas, primero hay que activarlo.

**Varias acciones en una frase**

```text
robot encender led uno y activar sensor
robot apagar led dos y giro a treinta y cinco grados
```

El intérprete separa la frase cuando reconoce el comienzo de otra acción. Por ejemplo, «treinta y cinco grados» se mantiene como un solo ángulo y no se divide por la palabra «y».

**Ayuda y estado**

```text
comando ayuda
comando estado
comando apagar todo
comando cambiar tema
```

La interfaz incluye un panel de ayuda con las expresiones disponibles.

### 11.5. Respuestas del asistente en voz alta

Además de mostrarse como texto en el panel **Respuesta del asistente**, el asistente **dice sus respuestas en voz alta** desde el navegador: el saludo de bienvenida, la despedida y el aviso de cierre por inactividad de la conversación.

- **Cómo funciona:** usa la síntesis de voz del propio navegador (Web Speech API, archivo `static/js/voz-salida.js`). El audio se genera en el dispositivo desde el que se abre la página, no en la Raspberry Pi, así que no requiere instalar nada en el servidor ni cambia el reconocimiento de Vosk.
- **Activar o desactivar:** la casilla **«Leer las respuestas en voz alta»**, debajo de la respuesta del asistente, enciende o apaga esta función. Viene activada por defecto. Al desactivarla se corta de inmediato la lectura en curso.
- **Se recuerda por navegador:** la elección se guarda en el navegador (`localStorage`, clave `vozRespuestasActivas`). Cada dispositivo o navegador tiene su propio ajuste y se conserva al recargar la página.
- **Elección de voz:** se prefiere una voz en español, en este orden: es-AR, es-419, es-US, es-MX y es-ES; si no hay ninguna de esas usa la primera voz en español disponible. Las voces disponibles dependen del sistema operativo y del navegador.
- **Sin eco:** mientras el asistente habla, y unos 0,6 segundos después, la página no envía audio del micrófono a Vosk. Así el asistente no se escucha a sí mismo ni toma su propia voz como una orden. Si el navegador deja la lectura colgada, un temporizador de seguridad la corta y libera el micrófono.
- **Navegador sin síntesis de voz:** la casilla aparece deshabilitada y las respuestas siguen mostrándose solo como texto.

---

## 12. Configuración y datos persistentes

La carpeta `datos/` se crea automáticamente cuando la aplicación necesita guardar información. Contiene archivos JSON como:

| Archivo | Contenido |
|---|---|
| `datos/configuracion.json` | Palabras de activación, sinónimos y modo del asistente. |
| `datos/nombres_leds.json` | Nombres personalizados de los LED. |
| `datos/automatizaciones.json` | Reglas de automatización creadas por el usuario. |

Estos datos permanecen después de reiniciar la aplicación. **No borres la carpeta `datos/` al actualizar el código** si querés conservar la configuración.

Las palabras de activación, palabras clave y modo se modifican desde **Configuración del asistente** en la web. No es necesario editar `servidor/config.py` ni reiniciar Flask después de cada cambio.

La lista de activación admite hasta 15 palabras o frases, con un máximo de 4 palabras por expresión. Debe quedar al menos una palabra de activación.

---

## 13. (Opcional) Iniciar automáticamente al encender la Raspberry Pi

Una vez que la aplicación funcione correctamente al ejecutarla manualmente, podés configurarla como servicio de `systemd`.

Primero averiguá tu usuario y la ruta absoluta del proyecto:

```bash
whoami
pwd
```

Por ejemplo, podrías tener:

```text
Usuario: alumno
Proyecto: /home/alumno/REPOSITORIO
```

Creá el archivo del servicio:

```bash
sudo nano /etc/systemd/system/asistente-raspberry.service
```

Pegá el siguiente contenido y reemplazá `USUARIO` y `RUTA_DEL_PROYECTO` por los valores reales:

```ini
[Unit]
Description=Asistente web de Raspberry Pi
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=USUARIO
WorkingDirectory=RUTA_DEL_PROYECTO
Environment=PYTHONUNBUFFERED=1
ExecStart=RUTA_DEL_PROYECTO/env/bin/python RUTA_DEL_PROYECTO/app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Si el usuario necesita el grupo GPIO, agregá dentro de la sección `[Service]`:

```ini
SupplementaryGroups=gpio
```

Guardá el archivo y activá el servicio:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now asistente-raspberry.service
```

Para comprobar su estado:

```bash
sudo systemctl status asistente-raspberry.service
```

Para ver los registros:

```bash
sudo journalctl -u asistente-raspberry.service -f
```

Para detener o desactivar el inicio automático:

```bash
sudo systemctl disable --now asistente-raspberry.service
```

El servicio debe ejecutarse con el mismo usuario que tiene acceso a los archivos de certificados y a la carpeta `datos/`. No ejecutes simultáneamente el servicio y otra instancia manual de `python app.py`.

---

## 14. Actualizar el proyecto

Para obtener cambios nuevos desde GitHub:

```bash
cd /ruta/a/REPOSITORIO
git pull
source env/bin/activate
python -m pip install -r requirements.txt
bash scripts/instalar_modelo.sh
```

No elimines ni reemplaces estas carpetas locales:

- `certs/`: contiene los certificados y la clave privada HTTPS.
- `env/`: contiene el entorno virtual de Python.
- `datos/`: contiene las palabras configuradas, los nombres de los LED y las automatizaciones.

Si una actualización modifica `requirements.txt`, volvé a ejecutar `pip install -r requirements.txt` dentro del entorno virtual.

---

## 15. Solución de problemas frecuentes

### La página no abre

- Confirmá que la Raspberry Pi y el navegador estén conectados a la misma red.
- Comprobá la IP con `hostname -I`.
- Confirmá que Flask esté ejecutándose en la Raspberry Pi.
- Revisá que se esté utilizando `https://` y el puerto `5000`.
- Si hay un firewall activo, permití conexiones TCP al puerto 5000 únicamente desde la red local de confianza.

### El navegador no permite activar el micrófono

- Confirmá que abriste la página mediante HTTPS.
- Comprobá que el certificado raíz local esté instalado en el dispositivo cliente.
- Revisá los permisos del sitio en el navegador y seleccioná el micrófono correcto.
- Cerrá y volvé a abrir el navegador después de instalar el certificado raíz.
- Recordá que el micrófono utilizado es el del dispositivo desde el que se abre la web.

### Aparece un error de certificado

- La dirección usada en el navegador debe coincidir con la IP o el nombre DNS incluido al generar el certificado.
- Si cambió la IP de la Raspberry Pi, reservá una dirección en el router y volvé a generar el certificado con `mkcert` usando la nueva dirección.
- Comprobá que el navegador cliente confíe en `rootCA.pem`.
- No compartas `rootCA-key.pem` ni la clave privada del servidor.

### Vosk no reconoce comandos o indica que falta el modelo

- Comprobá que el micrófono esté activado y que el navegador tenga permiso.
- Consultá el cuadro **Texto que interpreta Vosk en tiempo real** para ver qué palabras está detectando.
- Verificá que exista `modelos/vosk-model-small-es-0.42/`.
- Si falta el modelo, activá el entorno y ejecutá `bash scripts/instalar_modelo.sh`.
- Probá con palabras de activación cortas y claramente pronunciadas.

### El asistente no habla

- Comprobá que la casilla **«Leer las respuestas en voz alta»** esté marcada y que el volumen del dispositivo no esté silenciado.
- Algunos navegadores no tienen síntesis de voz o no traen ninguna voz en español: en ese caso la casilla aparece deshabilitada o la voz suena con otro idioma. Instalá una voz en español en el sistema operativo o probá con Chrome, Edge, Firefox o Safari actualizados.
- La voz sale por el dispositivo desde el que abrís la página, no por la Raspberry Pi.
- El asistente solo habla el saludo, la despedida y el aviso de cierre por inactividad; el resultado de cada comando se muestra como texto.

### Aparece `ModuleNotFoundError: No module named 'RPi'`

- Instalá `python3-rpi.gpio` o, si no está disponible, `python3-rpi-lgpio` mediante `apt`.
- No instales ambos paquetes a la vez.
- Recreá el entorno virtual con `python3 -m venv --system-site-packages env` y reinstalá `requirements.txt`.

### El reconocimiento empieza rápido y después se retrasa

- Pasá el puntero sobre el estado del micrófono o abrí `F12` → **Consola** para revisar las métricas de voz.
- Si aumenta `espera local` o el contador `descartados`, el servidor está tardando más que el flujo de audio entrante.
- Si aumenta `Vosk`, revisá la carga de CPU y memoria de la Raspberry Pi con `htop`.
- Probá con una sola pestaña y sin otras tareas pesadas. El límite de cola evita que la demora siga creciendo, pero bajo sobrecarga extrema puede descartar fragmentos antiguos.

### Los LED no responden

- Revisá los números BCM y los pines físicos de la tabla de conexiones.
- Comprobá la polaridad del LED y que cada uno tenga su resistencia.
- Verificá que el GND de los LED esté conectado al GND de la Raspberry Pi.

### El servo no se mueve o reinicia la Raspberry Pi

- Comprobá que el cable de señal llegue a GPIO 18 (pin físico 12).
- Verificá la fuente regulada externa de 5 V y que su GND sea común con el de la Raspberry Pi.
- No alimentes el servo desde el pin de 3,3 V.
- Revisá que el mecanismo del servo no esté trabado.

### El sensor no informa distancia

- Activá el sensor desde la interfaz o con el comando correspondiente.
- Comprobá VCC, GND y TRIG.
- Verificá el divisor de tensión del pin ECHO; no conectes ECHO directamente al GPIO.
- Tené en cuenta que el HC-SR04 puede no devolver una lectura válida si el objeto está fuera de su alcance o no refleja bien el ultrasonido.

---

## 16. Seguridad y límites de uso

- Este proyecto está pensado para una **red local de confianza**, como una red doméstica o un laboratorio escolar.
- La aplicación actual no incorpora inicio de sesión ni control de usuarios. Cualquier persona que pueda acceder a la página puede intentar controlar los dispositivos conectados.
- No configures el router para publicar el puerto `5000` en Internet ni expongas directamente esta aplicación a redes públicas.
- El servidor de desarrollo integrado de Flask facilita las pruebas y el uso en el laboratorio, pero no es un servidor endurecido para producción o acceso público. Flask recomienda utilizar un servidor WSGI y una configuración de despliegue apropiada para producción.
- Mantené las claves privadas fuera de GitHub. El certificado `rootCA.pem` puede distribuirse a los dispositivos que necesiten confiar en la autoridad; `rootCA-key.pem` nunca debe compartirse.
- Desconectá la alimentación antes de modificar el circuito. No conectes señales de 5 V directamente a los GPIO de 3,3 V.

---

## 17. Estructura principal del proyecto

```text
REPOSITORIO/
├── app.py                         # Punto de entrada: crea la app Flask y levanta el servidor HTTPS
├── servidor/                      # Servidor web: rutas HTTP e intérprete de órdenes habladas
│   ├── config.py                  # Palabras de inicio, carpetas, puerto y certificados
│   ├── servicios.py               # Instancias únicas: nombres de LED, asistente, reglas y monitor
│   ├── texto.py, numeros.py       # Normalizar texto y números en español
│   ├── vocabulario.py             # Verbos, palabras de LED y palabras reservadas
│   ├── validaciones.py            # Qué nombres de LED y palabras de activación se aceptan
│   ├── palabras_inicio.py         # Palabras de activación vigentes
│   ├── rutas/                     # Rutas /api/... (una por tema)
│   └── interprete/                # Intérprete de órdenes habladas
├── funciones/                     # Hardware, voz y lógica que no depende de Flask
│   ├── dispositivos.py            # Control de GPIO, LED, servo y sensor
│   ├── reconocimiento_voz.py      # Integración con Vosk
│   ├── sensor_monitor.py          # Mediciones periódicas del HC-SR04
│   ├── automatizaciones.py        # Reglas basadas en distancia
│   ├── nombres_leds.py            # Nombres personalizados de LED
│   ├── asistente.py               # Modo, palabras de activación y sesión del asistente
│   ├── registro.py                # Registro de comandos y eventos
│   └── comandos_ayuda.py          # Ayuda de comandos mostrada en la web
├── correcciones_vosk.json         # Correcciones del texto que entrega Vosk
├── templates/
│   └── index.html                 # Página principal
├── static/
│   ├── css/                       # Estilos de la interfaz
│   └── js/                        # Lógica del navegador y captura de audio
├── requirements.txt               # Dependencias Python
├── scripts/
│   └── instalar_modelo.sh         # Instalación del modelo de Vosk
├── modelos/
│   └── vosk-model-small-es-0.42/  # Modelo de reconocimiento en español
├── certs/                         # Se crea localmente; no subir a GitHub
├── datos/                         # Se crea al guardar configuración
└── env/                           # Se crea al instalar Python; no subir a GitHub
```

---

## 18. Referencias útiles

- [Documentación oficial de Raspberry Pi OS](https://www.raspberrypi.com/documentation/computers/os.html)
- [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
- [Diagrama de pines GPIO de Raspberry Pi](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio)
- [Documentación de `getUserMedia()` en MDN](https://developer.mozilla.org/es/docs/Web/API/MediaDevices/getUserMedia)
- [Proyecto mkcert y documentación de instalación](https://github.com/FiloSottile/mkcert)
- [Documentación de despliegue de Flask](https://flask.palletsprojects.com/en/stable/deploying/)
- [Modelos de voz de Vosk](https://alphacephei.com/vosk/models)

---

**Nota:** las conexiones indicadas corresponden a los GPIO definidos en `funciones/dispositivos.py`. Antes de alimentar el circuito, contrastá el pinout de tu modelo concreto de Raspberry Pi y comprobá el cableado físico. Las versiones de Raspberry Pi OS, Python y navegadores pueden cambiar; para una instalación nueva, utilizá las versiones soportadas disponibles y revisá las referencias oficiales si algún paquete cambió de nombre.

---

# Bitácora de actualizaciones

Las siguientes secciones conservan la documentación de mejoras, ajustes y detalles técnicos que figuraban en el README original.

## Primera clase

- Se definió de qué trataría el proyecto y se presentó una idea por escrito, utilizando un formato formal.

## Segunda clase

- Creamos el entorno virtual dentro de la Raspberry Pi e instalamos Python, Flask y las librerías necesarias para el correcto funcionamiento de los pines, entre otras.
- Comenzamos a desarrollar el `index` de forma básica y a probar el funcionamiento de la Raspberry Pi con los pines GPIO. Verificamos cómo activar y desactivar las señales de los pines a través de la web.
- Comenzamos haciendo funcionar los LED de forma manual mediante botones dentro de la web.

## Tercera clase

- Conectamos el servo y probamos manualmente su funcionamiento desde la página, además de comprobar que la Raspberry Pi interpretara correctamente las señales.
- Comenzamos las pruebas con los comandos de voz. Durante estas pruebas, notamos que algunas funciones de JavaScript no funcionaban de forma satisfactoria en determinados navegadores. Por ese motivo, tuvimos que replantear la manera de interpretar el audio. Después de evaluar distintas alternativas, decidimos instalar Vosk, un modelo de reconocimiento de voz que se ejecuta localmente en la Raspberry Pi para no depender de la conexión a Internet.
- A partir de ese cambio, modificamos la forma de comunicación dentro del proyecto: ahora JavaScript captura el audio y lo envía a Vosk, que lo transforma en texto para que el resto de la página pueda interpretar la instrucción y actuar en consecuencia.
- La necesidad de capturar el audio desde la web generó otro inconveniente: los navegadores no permitían acceder al micrófono porque la página no contaba con un certificado HTTPS. Esto nos llevó a crear un certificado con claves PEM válidas para habilitar el acceso al micrófono.
- Finalmente, logramos hacer funcionar los comandos de voz básicos para encender y apagar los LED, aunque todavía no conseguimos controlar el servo mediante la voz.

## Cuarta clase

- Modificamos la activación de los comandos de voz para que fuera necesario decir la palabra «comando» antes de cada instrucción. Por ejemplo: «comando encender LED uno».
- También reemplazamos la palabra «servo» por «giro», debido a que Vosk no reconocía correctamente la primera. Además, establecimos «grados» como palabra final del comando. De esta manera, logramos hacer funcionar instrucciones como «giro a 45 grados».
- Investigamos cómo conectar el sensor ultrasónico evitando problemas por las diferencias de voltaje. Llegamos a la conclusión de que el método más económico y sencillo era utilizar dos resistencias: una de 1000 ohmios y otra de 1500 o 2000 ohmios.
- Comenzamos a mejorar la interfaz de la página mediante la incorporación de indicadores visuales y una estructura más clara para diferenciar las secciones de cada elemento de la web.

## Quinta clase

- Conectamos el sensor ultrasónico con las resistencias correspondientes para su correcto funcionamiento.
- Comprobamos que las mediciones se interpretaran correctamente en la página y que esta se actualizara constantemente para mostrar el nuevo valor.
- La página comenzó a comprobar una vez por segundo el estado de todos los dispositivos. Esto se debió a que, anteriormente, el estado mostrado no siempre coincidía con el estado real, ya que otra sesión podía modificarlo.

## Sexta clase

- El archivo `Bitacora` incluye el título de esta clase, pero no contiene actividades registradas.


## Actualizar el código sin perder HTTPS

Al copiar los archivos modificados, no borres la carpeta `certs/` ni el entorno `env/` existente. El ZIP de entrega omite deliberadamente esos elementos locales; contiene el código y los scripts necesarios para instalar el componente de voz.


## Actualización de interfaz y sincronización entre navegadores

- Cada LED ahora tiene un único botón. Si está apagado muestra **Encender**; si está encendido muestra **Apagar**. Al pulsarlo, Flask consulta el estado del GPIO y lo alterna de forma atómica.
- Todas las pestañas y navegadores que se conectan a esta misma instancia de Flask consultan `/api/estado` cada segundo. Así, los cambios realizados con botones o por voz se reflejan en las demás páginas sin recargarlas. Al volver a una pestaña, se solicita el estado inmediatamente.
- El servidor devuelve el estado sin caché. Los LED se consultan leyendo sus pines GPIO; el ángulo del SG90 es la última posición solicitada (el servo SG90 no devuelve su posición física porque no tiene realimentación); el sensor muestra si su medición continua está activada.
- La sincronización requiere que todos los navegadores se conecten a la misma Raspberry Pi y al mismo proceso Flask. Si se inicia más de una instancia independiente de la aplicación, cada proceso tendría su propio estado en memoria.

## Sintaxis vigente de comandos de voz

La referencia completa y actualizada está en la sección **Comandos de voz**, más arriba.

## Personalizar colores y tema de la interfaz

Todos los colores, las fuentes y los radios de borde se controlan desde el inicio de `static/css/estilos.css`, sin tocar el resto del archivo:

- **Sección 1 · Personalización:** variables del tema claro (`--color-primario`, `--color-secundario`, `--color-fondo`, `--color-superficie`, `--color-texto`, `--color-exito`, `--color-peligro`, etc.).
- **Sección 2 · Tema oscuro:** las mismas variables con valores para fondo oscuro.
- **Sección 3 · Valores derivados:** los tonos suaves (fondos de íconos, avisos, LED encendido) se calculan solos a partir de los colores base. No hace falta editarlos.

El botón de luna/sol del encabezado alterna entre el tema claro y el oscuro y recuerda la elección en ese navegador (`static/js/tema.js`). Si todavía no se eligió, usa el tema del sistema operativo.

Para crear un tema nuevo, copiá el bloque `:root[data-tema="oscuro"]`, cambiale el nombre (por ejemplo `data-tema="verde"`) y ajustá los valores. Para dejar un tema fijo, escribí `<html lang="es" data-tema="verde">` en `templates/index.html` y quitá la línea que carga `tema.js`.

La interfaz no usa fuentes ni íconos externos, así que sigue funcionando sin internet.


## Ayuda de comandos y dial del servo

- **Ayuda de comandos:** el botón del panel de voz despliega un menú con cuatro categorías (LED, Servo, Sensor y Generales); cada una despliega su lista. El texto de las listas está en `funciones/comandos_ayuda.py`: para agregar o corregir un comando en la ayuda alcanza con editar ese archivo. La lógica de mostrar y ocultar está en `static/js/ayuda.js`.
- **Agregar un comando nuevo:** en `servidor/interprete/generales.py` (o en un archivo nuevo de esa carpeta), escribí una función `interpretar_...` como las que ya están allí, sumala a `INTERPRETES_GENERALES` en `servidor/interprete/ordenes.py` y descríbela en `funciones/comandos_ayuda.py`.
- **Dial del servo:** el panel del servomotor muestra un velocímetro de 0° a 180° cuya aguja es el cuerno de un servo. Indica la última posición aplicada (el SG90 no informa su posición real). Los colores del dial salen de las variables de `estilos.css`; `--color-servo-cuerpo` y `--color-aguja` permiten darle colores propios.
- **Botones «Encender todos» / «Apagar todos»** en el panel de iluminación, equivalentes a los comandos de voz. Usan `POST /api/leds/todos` con `{"accion": "encender" | "apagar"}`.


## Automatizaciones, gráfico de distancia y registro

**Cómo funciona el sensor ahora.** Un hilo en segundo plano (`funciones/sensor_monitor.py`) mide 4 veces por segundo mientras el sensor está activo. Antes se medía solo cuando una página lo pedía; ahora hay una única fuente de datos que comparten el número grande, el gráfico, las reglas y el comando «medir distancia». Si el hilo no estuviera corriendo, la aplicación mide directamente como antes.

**Automatizaciones** (`funciones/automatizaciones.py`, panel *Automatizaciones*):

- Una regla compara la distancia con un umbral (de 2 a 400 cm, el alcance del HC-SR04) y ejecuta una acción: encender o apagar un LED, encender o apagar todos, o mover el servo a un ángulo. Hasta 8 reglas.
- Se dispara cuando la condición **empieza** a cumplirse, no en cada medición. Para evitar disparos falsos por el ruido del sensor hay tres protecciones: la condición debe cumplirse en 2 mediciones seguidas (`CONFIRMACIONES`), para volver a armarse la distancia debe alejarse 2 cm del umbral (`HISTERESIS_CM`) y pasan al menos 2 s entre dos disparos de la misma regla (`ENFRIAMIENTO_S`). Los tres valores están al comienzo de `funciones/automatizaciones.py`.
- Solo se evalúan mientras el sensor está activo. Una lectura sin eco válido (objeto muy lejos o que no refleja) se ignora.
- Se crean desde el formulario del panel o por voz. Se guardan en `datos/automatizaciones.json` (la carpeta se crea sola) y sobreviven a un reinicio. **Al actualizar el código no borres la carpeta `datos/`.** La variable de entorno `ASISTENTE_DATOS` permite usar otra carpeta.

**Gráfico de distancia** (`static/js/grafico.js`): línea de los últimos 60 segundos dibujada con SVG propio, sin librerías. Muestra mínimo, promedio y máximo, el umbral de cada regla como línea punteada y, al pasar el puntero, el valor exacto. Los datos están en el servidor, así que se ve completo al recargar o desde otro dispositivo. Con el sensor apagado queda congelado en la última medición.

**Registro de comandos** (`funciones/registro.py`, `static/js/registro.js`): guarda los últimos 200 eventos **en memoria** (se vacía al reiniciar). Cada orden queda anotada con lo que escuchó Vosk y su resultado: *Orden*, *Error* o *Ignorada* (frase que no empezó con «comando»; sirve para ajustar el reconocimiento). Los disparos de las reglas aparecen como *Regla*. Tiene filtro y botón para limpiar.

**Nuevos endpoints:**

| Ruta | Uso |
| --- | --- |
| `GET /api/reglas` | reglas, pausa y límites del formulario |
| `POST /api/reglas` | crea una regla: `{"condicion": "menor", "umbral_cm": 20, "accion": {"tipo": "led", "led": 1, "encender": true}}` |
| `PATCH /api/reglas/<id>` | `{"activa": true\|false}` |
| `DELETE /api/reglas/<id>` y `DELETE /api/reglas` | borra una o todas |
| `POST /api/reglas/pausa` | `{"pausadas": true\|false}` |
| `GET /api/distancia/historial?desde=<momento>` | mediciones recientes (solo las nuevas) |
| `GET /api/registro?desde=<id>` y `DELETE /api/registro` | consulta y limpia el registro |

Las acciones posibles son `{"tipo": "led", "led": N, "encender": bool}`, `{"tipo": "leds", "encender": bool}` y `{"tipo": "servo", "angulo": 0-180}`.


## Palabras para comenzar una orden

Las palabras con las que puede empezar una orden se configuran en una lista al comienzo de `servidor/config.py`:

```python
PALABRAS_DE_INICIO = [
    "comando",
    "robot",
]
```

Para cambiarlas alcanza con editar esa lista y reiniciar la aplicación; los mensajes y la ayuda de la página se ajustan solos.

- Se pueden agregar, quitar o reemplazar todas las que quieras. No importan las mayúsculas ni las tildes.
- Pueden ser **frases de varias palabras**, por ejemplo `"hola robot"`: entonces la orden es `hola robot encender led uno`.
- La **primera** es la principal: es la que se usa en los ejemplos de la página. Los mensajes de error repiten la palabra que la persona realmente dijo.
- La palabra debe estar **completa** y **al comienzo**: `robot encender led uno` funciona, pero `el robot encender led uno` y `robotica encender led uno` no. Una frase que no empieza con ninguna palabra de inicio se ignora (en el registro aparece como *Ignorada*).
- Elegí palabras que el reconocedor entienda bien y que no se usen dentro de las órdenes (`led`, `giro`, `sensor`, `ayuda`, `reglas`…). Para comprobar qué transcribe Vosk, mirá el cuadro *Texto que interpreta Vosk* o el registro de comandos.
- La lista no puede quedar vacía: si no tiene ninguna palabra válida, la aplicación no arranca y explica el motivo.

## Respuestas del asistente en voz alta

- Nuevo archivo `static/js/voz-salida.js`: lee en voz alta las respuestas del asistente con la síntesis de voz del navegador. Se agregó la casilla **«Leer las respuestas en voz alta»** en el panel de voz (`templates/index.html`).
- La elección se guarda en cada navegador y mientras el asistente habla no se envía audio a Vosk (ver sección 11.5).

## Optimización y diagnóstico del reconocimiento de voz

El envío de audio utiliza bloques de **0,5 segundos** de PCM mono a 16 kHz. Para evitar que una Raspberry Pi sobrecargada acumule solicitudes antiguas, el navegador mantiene una cola limitada:

- Se procesa una única solicitud de audio a la vez, para conservar el orden que necesita el reconocedor Vosk.
- Se permiten hasta **3 bloques pendientes** (1,5 segundos), además del bloque que pudiera estar procesándose.
- Si la cola se llena, se elimina el bloque pendiente más antiguo y se conserva el audio más reciente. Esta medida solo se activa cuando el procesamiento se retrasa; durante el funcionamiento normal no descarta audio.
- Cuando hubo un descarte, el navegador informa la discontinuidad en la siguiente solicitud y el servidor ejecuta `Reset()` sobre el reconocedor antes de procesar ese bloque. El modelo ya cargado se conserva, pero se descarta el contexto acústico parcial para no unir palabras separadas por un hueco de audio.
- Al apagar el micrófono se descartan los bloques que todavía estaban esperando, se deja terminar la solicitud en curso y luego se cierra la sesión de Vosk.

### Ver las métricas

Con el micrófono activo, pasá el puntero sobre el indicador de estado del micrófono para consultar el último diagnóstico. También podés abrir las herramientas de desarrollo del navegador (`F12`), pestaña **Consola**. Se registra una muestra cada 10 bloques y siempre que se descarta audio.

Las métricas informan:

| Métrica | Qué indica |
|---|---|
| Audio ida/vuelta | Tiempo desde que el navegador envía el bloque hasta que recibe la respuesta. Incluye red, espera en Flask y Vosk. |
| Espera en Flask | Tiempo que la solicitud esperó para adquirir el bloqueo del reconocedor. Si aumenta, hay competencia por el servicio de voz. |
| Vosk | Tiempo dedicado a procesar el bloque en el servidor. |
| Espera local | Tiempo que el bloque estuvo esperando en la cola del navegador antes de enviarse. |
| Cola | Cantidad de bloques pendientes frente al máximo permitido (3). |
| Descartados | Cantidad de bloques que se quitaron de la cola por sobrecarga desde que se activó el micrófono. |

El endpoint `POST /api/voz/audio` incluye un objeto `metricas` en su respuesta con `audio_ms`, `espera_bloqueo_ms`, `procesamiento_ms`, `servidor_total_ms` y `contexto_reiniciado`. Se mantienen los campos anteriores (`ok`, `final`, `texto` y `parcial`), por lo que la lógica de comandos y la interfaz existente siguen utilizando el mismo formato de reconocimiento.

### Ajustar el límite de cola

El límite se configura en `static/js/voz.js`, mediante `MAX_BLOQUES_PENDIENTES`. El valor predeterminado es **3**. Un valor mayor conserva más audio ante demoras breves, pero permite acumular más latencia; un valor menor reduce la espera máxima, pero aumenta la probabilidad de descartar audio cuando la Raspberry Pi está ocupada. Se recomienda mantener el valor predeterminado y observar las métricas antes de modificarlo.

### Si el contador de descartes aumenta continuamente

Eso indica que el servidor no está procesando audio a la velocidad a la que llega. En la Raspberry Pi, ejecutá `htop` mientras hablás y comprobá el uso de CPU y memoria. Cerrá pestañas duplicadas que no se estén utilizando y evitá ejecutar otras tareas pesadas. Si el tiempo de Vosk se mantiene por encima de los 500 ms por bloque, la Raspberry Pi no alcanza a procesar el audio en tiempo real con la carga actual.

# Proyecto de control de dispositivos con Raspberry Pi 3

Interfaz web en Flask para controlar cuatro LED, un servomotor SG90 y un sensor ultrasónico HC-SR04. El reconocimiento de voz se hace **localmente en la Raspberry Pi con Vosk**, sin enviar el audio a servicios externos.

## Qué se agregó

- Reconocimiento offline compatible con Firefox y Chromium: el navegador captura el micrófono y envía audio PCM al servidor Flask; Vosk lo convierte en texto en la Raspberry Pi.
- Botón para activar y apagar el micrófono.
- Control por voz de los LED, el ángulo del servo y la activación/desactivación de la medición ultrasónica.
- El sensor ultrasónico arranca desactivado. Cuando se activa, la interfaz actualiza la distancia aproximadamente una vez por segundo.
- Un único botón por LED alterna entre encender y apagar.
- Nombres propios para los LED: desde la página se cambia «LED 1» por «cocina» y ese nombre también es el que se dice por voz (ver *Nombres de los LED*).
- Sincronización de estado entre pestañas y navegadores conectados a la misma Raspberry Pi.
- Automatizaciones: reglas del tipo «si la distancia es menor a 20 cm, encender el LED 1», que funcionan aunque no haya ninguna página abierta.
- Gráfico de la distancia de los últimos 60 segundos y registro de los comandos de voz (qué escuchó Vosk y qué se hizo).
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

Después de pulsar **Activar micrófono**, todas las órdenes habladas deben empezar con una **palabra de inicio**. Con la configuración que viene de ejemplo son `comando` y `robot`, así que `comando encender led uno` y `robot encender led uno` hacen lo mismo (ver *Palabras para comenzar una orden*, más abajo, para cambiarlas). Los ejemplos de esta lista usan `comando`. La lista completa también está en la página, en el botón **Ayuda de comandos** (o diciendo `comando ayuda`).

**LED**

- `comando LED uno encender` / `comando LED 2 apagar`: enciende o apaga un LED (1 a 4) mientras conserve su nombre original.
- `comando encender cocina` / `comando apagar cocina`: lo mismo, con el nombre que le hayas puesto al LED desde la página (ver *Nombres de los LED*). «cocina» es solo un ejemplo.
- `comando encender todas las leds` / `comando apagar todas las leds`: enciende o apaga los cuatro a la vez. También se entienden variantes como «prender todos los leds» o «apagar todas las luces».

**Servo**

- `comando giro a 45 grados` / `comando giro a ciento treinta y cinco grados`: la palabra `grados` debe ser la última. Se aceptan ángulos enteros de 0 a 180, con cifras o palabras.
- `comando giro al centro`: deja el servo en 90°.

**Sensor**

- `comando activar sensor` / `comando encender sensor`: empieza a medir.
- `comando desactivar sensor` / `comando apagar sensor`: detiene las mediciones.
- `comando medir distancia`: informa la distancia (el sensor debe estar activo).
- `comando si hay algo a menos de veinte centímetros encender led uno`: crea una regla (ver *Automatizaciones*). Con «más de» la condición es la contraria. Se puede decir «cuando» o «regla» en lugar de «si», y «metros» en lugar de «centímetros».
- `comando alarma a treinta centímetros encender todas las leds`: forma corta; «alarma» equivale a «si hay algo a menos de».
- `comando reglas`: dice cuántas reglas hay y qué hace cada una.
- `comando borrar regla uno` / `comando borrar todas las reglas`: borra una regla por su número, o todas.
- `comando desactivar regla uno` / `comando activar regla uno`: apaga o enciende una regla sin borrarla.
- `comando pausar reglas` / `comando reanudar reglas`: detiene o reanuda todas las reglas.

**Generales**

- `comando ayuda`: abre el menú de ayuda. `comando ayuda leds`, `comando ayuda giro`, `comando ayuda sensor` y `comando ayuda generales` abren directamente cada lista; `comando cerrar ayuda` lo cierra. (Se dice «giro» en lugar de «servo» porque el reconocedor lo entiende mejor, aunque «ayuda servo» también funciona.)
- `comando cambiar tema`: alterna entre el tema claro y el oscuro. `comando tema oscuro` / `comando tema claro` eligen uno directamente. El tema es una preferencia de cada navegador: cambia solo el de la pantalla que recibió la orden.
- `comando estado`: resume cómo están los LED, el servo y el sensor.
- `comando apagar todo`: apaga los LED y desactiva el sensor. El servo queda donde está.
- `comando limpiar registro`: vacía el registro de comandos.

## Nombres de los LED

Cada tarjeta del panel **Iluminación** tiene un lápiz. Al tocarlo se escribe el nombre nuevo (por ejemplo `cocina`) y se guarda con **Guardar** o con Enter; **Esc** cancela. Dejar el campo vacío devuelve el LED a su nombre original.

El nombre elegido es también el que se dice por voz, con cualquiera de las palabras de inicio:

- `comando encender cocina` / `robot encender cocina`
- `comando apagar cocina` / `robot cocina apagar` (el nombre puede ir antes o después del verbo)
- Se ignoran mayúsculas, tildes y artículos: «luz de la sala», «luz sala» y «la luz de la sala» son lo mismo.
- También funciona en las reglas habladas: `comando si hay algo a menos de veinte centímetros encender cocina`.

Cómo se comporta:

- **Un LED renombrado responde solo a su nombre nuevo.** Si se dice `comando encender led uno` y el LED 1 ya se llama «cocina», el sistema no hace nada y avisa cuál es el nombre nuevo. Los LED sin nombre propio siguen respondiendo a «LED uno», «LED 2», etc.
- **Se refleja en toda la interfaz:** título de la tarjeta, cartel «Por voz: …» de cada LED, lista de la *Ayuda de comandos*, menú del formulario de reglas, descripción de las reglas existentes, mensajes de resultado y el comando `estado`.
- **Se comparte entre pestañas y navegadores** (se sincroniza solo, igual que el estado de los LED) y **se guarda en `datos/nombres_leds.json`**, así que sobrevive a un reinicio. Igual que con las reglas, no borres la carpeta `datos/` al actualizar el código.

Reglas de los nombres (la página muestra el motivo si uno no sirve):

- Hasta 24 caracteres; solo letras, números y espacios.
- Distinto en cada LED (sin contar mayúsculas, tildes ni artículos).
- No pueden contener palabras que ya tienen otro significado en los comandos: los verbos (encender, apagar, activar...), `todo/todos/todas`, `ayuda`, `tema`, `estado`, `resumen`, `regla(s)`, `alarma`, `sensor`, `distancia`, `grados`, `giro`, `servo`, las palabras de inicio (`comando`, `robot`), etc. Sin esto, un LED llamado «estado» haría que «encender estado» se confundiera con el comando `estado`.
- No pueden ser solo un número («tres»), porque se confundiría con los ángulos y las distancias; «luz 2» sí sirve.

**Consejo para elegir nombres:** el reconocedor de voz solo entiende palabras de su vocabulario en español. Los nombres comunes («cocina», «living», «garage», «pasillo», «escritorio») andan bien; nombres inventados, abreviaturas o palabras en otro idioma pueden transcribirse mal. Si un nombre no responde, mirá en el cuadro «Texto que interpreta Vosk» qué escuchó y probá con otro.

Para el código: la lógica de guardado, validación y búsqueda está en `nombres_leds.py`; las palabras prohibidas y la interpretación de las órdenes están en la sección *NOMBRES DE LOS LED* de `app.py`. La API es `PUT /api/led/<n>/nombre` con `{"nombre": "cocina"}` (vacío = restablecer), y `GET /api/estado` devuelve además `nombres` con el nombre de cada LED.

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

- **Ayuda de comandos:** el botón del panel de voz despliega un menú con cuatro categorías (LED, Servo, Sensor y Generales); cada una despliega su lista. El texto de las listas está en `comandos_ayuda.py`: para agregar o corregir un comando en la ayuda alcanza con editar ese archivo. La lógica de mostrar y ocultar está en `static/js/ayuda.js`.
- **Agregar un comando nuevo:** en `app.py`, escribí una función `_interpretar_...` como las que están en la sección *Comandos de voz generales*, sumala a `INTERPRETES_GENERALES` y descríbela en `comandos_ayuda.py`.
- **Dial del servo:** el panel del servomotor muestra un velocímetro de 0° a 180° cuya aguja es el cuerno de un servo. Indica la última posición aplicada (el SG90 no informa su posición real). Los colores del dial salen de las variables de `estilos.css`; `--color-servo-cuerpo` y `--color-aguja` permiten darle colores propios.
- **Botones «Encender todos» / «Apagar todos»** en el panel de iluminación, equivalentes a los comandos de voz. Usan `POST /api/leds/todos` con `{"accion": "encender" | "apagar"}`.


## Automatizaciones, gráfico de distancia y registro

**Cómo funciona el sensor ahora.** Un hilo en segundo plano (`sensor_monitor.py`) mide 4 veces por segundo mientras el sensor está activo. Antes se medía solo cuando una página lo pedía; ahora hay una única fuente de datos que comparten el número grande, el gráfico, las reglas y el comando «medir distancia». Si el hilo no estuviera corriendo, la aplicación mide directamente como antes.

**Automatizaciones** (`automatizaciones.py`, panel *Automatizaciones*):

- Una regla compara la distancia con un umbral (de 2 a 400 cm, el alcance del HC-SR04) y ejecuta una acción: encender o apagar un LED, encender o apagar todos, o mover el servo a un ángulo. Hasta 8 reglas.
- Se dispara cuando la condición **empieza** a cumplirse, no en cada medición. Para evitar disparos falsos por el ruido del sensor hay tres protecciones: la condición debe cumplirse en 2 mediciones seguidas (`CONFIRMACIONES`), para volver a armarse la distancia debe alejarse 2 cm del umbral (`HISTERESIS_CM`) y pasan al menos 2 s entre dos disparos de la misma regla (`ENFRIAMIENTO_S`). Los tres valores están al comienzo de `automatizaciones.py`.
- Solo se evalúan mientras el sensor está activo. Una lectura sin eco válido (objeto muy lejos o que no refleja) se ignora.
- Se crean desde el formulario del panel o por voz. Se guardan en `datos/automatizaciones.json` (la carpeta se crea sola) y sobreviven a un reinicio. **Al actualizar el código no borres la carpeta `datos/`.** La variable de entorno `ASISTENTE_DATOS` permite usar otra carpeta.

**Gráfico de distancia** (`static/js/grafico.js`): línea de los últimos 60 segundos dibujada con SVG propio, sin librerías. Muestra mínimo, promedio y máximo, el umbral de cada regla como línea punteada y, al pasar el puntero, el valor exacto. Los datos están en el servidor, así que se ve completo al recargar o desde otro dispositivo. Con el sensor apagado queda congelado en la última medición.

**Registro de comandos** (`registro.py`, `static/js/registro.js`): guarda los últimos 200 eventos **en memoria** (se vacía al reiniciar). Cada orden queda anotada con lo que escuchó Vosk y su resultado: *Orden*, *Error* o *Ignorada* (frase que no empezó con «comando»; sirve para ajustar el reconocimiento). Los disparos de las reglas aparecen como *Regla*. Tiene filtro y botón para limpiar.

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

Las palabras con las que puede empezar una orden se configuran en una lista al comienzo de `app.py`:

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

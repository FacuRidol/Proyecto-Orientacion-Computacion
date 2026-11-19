# servidor/config.py
"""Configuración del servidor: lo único que normalmente hay que editar.

QUÉ HACE
 - Define las palabras con las que empieza una orden hablada (PALABRAS_DE_INICIO).
 - Define dónde se guardan los datos permanentes y los parámetros del servidor.

QUIÉN LO USA
 - servidor/palabras_inicio.py, servidor/servicios.py y app.py.
"""
import os
from pathlib import Path

# Carpeta raíz del proyecto: la que contiene app.py, templates/ y static/.
RAIZ = Path(__file__).resolve().parent.parent

# ==========================================
# PALABRAS PARA COMENZAR UNA ORDEN
# ==========================================
# Toda orden hablada tiene que empezar con alguna de estas palabras. Con la lista
# de ejemplo, estas dos órdenes hacen exactamente lo mismo:
#
#     «comando encender led uno»        «robot encender led uno»
#
# Para cambiarlas alcanza con editar la lista (no hace falta tocar nada más: los
# mensajes y la ayuda de la página se ajustan solos):
#   - Se pueden agregar, quitar o reemplazar todas las que quieras.
#   - No importan las mayúsculas ni las tildes.
#   - Pueden ser frases de varias palabras, por ejemplo "hola robot".
#   - La primera es la principal: es la que se usa en los ejemplos de la página.
#   - Elegí palabras que el reconocedor entienda bien y que no se usen dentro de
#     las órdenes (led, giro, sensor, ayuda, reglas...). Para comprobarlo mirá el
#     cuadro «Texto que interpreta Vosk» o el registro de comandos.
# (Estas son las palabras de fábrica; las que se cambian desde la página se
# guardan en datos/configuracion.json y tienen prioridad.)
PALABRAS_DE_INICIO = [
    "comando",
    "robot",
]

# ==========================================
# DATOS PERMANENTES
# ==========================================
# Carpeta donde se guardan las reglas, los nombres de LED y la configuración del
# asistente: la de la variable de entorno ASISTENTE_DATOS o, si no existe, «datos/»
# junto a app.py (la carpeta se crea sola).
CARPETA_DATOS = Path(os.environ.get("ASISTENTE_DATOS") or RAIZ / "datos")

# ==========================================
# SENSOR Y GRÁFICO
# ==========================================
# Una medición del monitor se considera «reciente» durante 1,5 s.
MUESTRA_VIGENTE_S = 1.5
# Ventana que muestra el gráfico de distancia (el monitor conserva algo más).
VENTANA_GRAFICO_S = 60

# ==========================================
# SERVIDOR HTTPS
# ==========================================
# Escucha en todas las interfaces (accesible desde otros equipos de la red).
HOST = "0.0.0.0"
PUERTO = 5000
# Certificado y clave de la carpeta certs/ (HTTPS es necesario para que el
# navegador permita usar el micrófono desde otro equipo).
CERTIFICADO = RAIZ / "certs" / "172.16.4.102.pem"
CLAVE_PRIVADA = RAIZ / "certs" / "172.16.4.102-key.pem"

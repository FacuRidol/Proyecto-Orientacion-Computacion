# servidor/rutas/leds.py
"""Control y nombres de los LED.

RUTAS
  POST /api/led/<n>            enciende o apaga un LED ({"accion": "encender"|"apagar"}).
  POST /api/led/<n>/alternar   invierte el LED (botón único de cada tarjeta, static/js/voz.js).
  POST /api/leds/todos         enciende o apaga los cuatro con una sola petición.
  PUT  /api/led/<n>/nombre     cambia el nombre de un LED (formulario del lápiz, static/js/voz.js).
"""
from flask import Blueprint, current_app, jsonify, request

from funciones import dispositivos as hw
from funciones.nombres_leds import ErrorDeNombre

from .. import palabras_inicio
from ..servicios import nombre_led, nombres_leds

bp = Blueprint("leds", __name__)


@bp.route("/api/led/<int:numero>", methods=["POST"])
def controlar_led(numero):
    datos = request.get_json(silent=True) or {}
    accion = datos.get("accion")
    if accion not in ("encender", "apagar"):
        return jsonify({"ok": False, "mensaje": "Acción no válida."}), 400

    try:
        encendido = accion == "encender"
        # Llama a dispositivos.controlar_led (mueve el pin). Si el LED no existe lanza ValueError y se responde con error 400.
        hw.controlar_led(numero, encendido)
        return jsonify({
            "ok": True,
            "mensaje": f"{nombre_led(numero)}: {accion}.",
            "encendido": encendido,
        })
    except ValueError as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 400


@bp.route("/api/led/<int:numero>/alternar", methods=["POST"])
def alternar_led(numero):
    """Invierte el estado del LED leyendo el GPIO desde el servidor."""
    try:
        # Llama a dispositivos.alternar_led, que lee el pin y lo invierte de forma atómica.
        encendido = hw.alternar_led(numero)
        return jsonify({
            "ok": True,
            "led": numero,
            "encendido": encendido,
            "mensaje": f"{nombre_led(numero)}: {'encendido' if encendido else 'apagado'}.",
        })
    except ValueError as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 400
    except Exception:
        current_app.logger.exception("Error al alternar el LED %s", numero)
        return jsonify({"ok": False, "mensaje": "No se pudo cambiar el estado del LED."}), 500


@bp.route("/api/leds/todos", methods=["POST"])
def controlar_todos_los_leds():
    """Enciende o apaga todos los LED con una sola petición."""
    datos = request.get_json(silent=True) or {}
    accion = datos.get("accion")
    if accion not in ("encender", "apagar"):
        return jsonify({"ok": False, "mensaje": "Acción no válida."}), 400

    try:
        encender = accion == "encender"
        # Llama a dispositivos.controlar_todos_leds y devuelve el estado final de todos.
        leds = hw.controlar_todos_leds(encender)
        return jsonify({
            "ok": True,
            "mensaje": "Todos los LED encendidos." if encender else "Todos los LED apagados.",
            "leds": leds,
        })
    except Exception:
        current_app.logger.exception("Error al controlar todos los LED")
        return jsonify({"ok": False, "mensaje": "No se pudieron controlar los LED."}), 500


@bp.route("/api/led/<int:numero>/nombre", methods=["PUT"])
def renombrar_led(numero):
    """Cambia el nombre de un LED (también el que se dice por voz).

    Cuerpo: {"nombre": "cocina"}. Un nombre vacío devuelve el LED a su nombre
    original. Responde con los nombres de todos los LED.
    """
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict) or "nombre" not in datos:
        return jsonify({"ok": False, "mensaje": "Falta el nombre del LED."}), 400

    try:
        # Llama a nombres_leds.establecer: valida y guarda. Si el nombre no sirve lanza ErrorDeNombre y
        # se responde 400 con el motivo (la página lo muestra bajo el campo).
        nombre = nombres_leds.establecer(numero, datos["nombre"])
    except ErrorDeNombre as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 400
    except Exception:
        current_app.logger.exception("Error al renombrar el LED %s", numero)
        return jsonify({"ok": False, "mensaje": "No se pudo cambiar el nombre del LED."}), 500

    if nombres_leds.personalizado(numero):
        mensaje = (
            f"El LED {numero} ahora se llama «{nombre}». "
            f"Por voz: ‘{palabras_inicio.actual.principal} encender {nombre}’."
        )
    else:
        mensaje = f"El LED {numero} volvió a su nombre original."

    return jsonify({
        "ok": True,
        "mensaje": mensaje,
        "led": numero,
        "nombre": nombre,
        "personalizado": nombres_leds.personalizado(numero),
        "nombres": nombres_leds.todos(),
    })

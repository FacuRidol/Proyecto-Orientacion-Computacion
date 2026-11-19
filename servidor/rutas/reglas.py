# servidor/rutas/reglas.py
"""Automatizaciones: reglas «si la distancia es menor a X cm, hacer Y».

RUTAS (las consulta static/js/automatizaciones.js)
  GET    /api/reglas          lista de reglas, límites del formulario, nombres de LED y si el sensor está activo.
  POST   /api/reglas          crea una regla ({"condicion", "umbral_cm", "accion"}).
  DELETE /api/reglas          borra todas las reglas.
  PATCH  /api/reglas/<id>     activa o desactiva una regla (interruptor de cada regla).
  DELETE /api/reglas/<id>     borra una regla.
  POST   /api/reglas/pausa    pausa o reanuda todas las reglas.
"""
from flask import Blueprint, jsonify, request

from funciones import dispositivos as hw
from funciones.automatizaciones import ErrorDeRegla

from ..respuestas import sin_cache
from ..servicios import monitor, motor_reglas, nombres_leds

bp = Blueprint("reglas", __name__)


@bp.route("/api/reglas", methods=["GET"])
def listar_reglas():
    return sin_cache(jsonify({
        "ok": True,
        **motor_reglas.estado(),
        "nombres_leds": nombres_leds.todos(),  # para el menú «Encender LED...» del formulario
        "sensor_activo": hw.sensor_esta_activo(),
        "ahora": round(monitor.ahora(), 3),  # para mostrar «último disparo: hace 12 s»
    }))


@bp.route("/api/reglas", methods=["POST"])
def crear_regla():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify({"ok": False, "mensaje": "Datos de la regla no válidos."}), 400

    try:
        # Llama a automatizaciones.MotorReglas.crear, que valida todo. Si algo está mal lanza ErrorDeRegla y se responde 400 con su mensaje.
        regla = motor_reglas.crear(
            datos.get("condicion"), datos.get("umbral_cm"), datos.get("accion")
        )
    except ErrorDeRegla as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 400

    return jsonify({
        "ok": True,
        "mensaje": f"Regla {regla['id']} creada.",
        "regla": regla,
    }), 201


@bp.route("/api/reglas", methods=["DELETE"])
def borrar_todas_las_reglas():
    cantidad = motor_reglas.eliminar_todas()
    return jsonify({"ok": True, "mensaje": f"Se borraron {cantidad} reglas.", "borradas": cantidad})


@bp.route("/api/reglas/<int:id_regla>", methods=["PATCH"])
def modificar_regla(id_regla):
    datos = request.get_json(silent=True) or {}
    if not isinstance(datos.get("activa"), bool):
        return jsonify({"ok": False, "mensaje": "Indicá si la regla debe estar activa."}), 400

    # Llama a MotorReglas.activar; devuelve None si la regla no existe (-> 404).
    regla = motor_reglas.activar(id_regla, datos["activa"])
    if regla is None:
        return jsonify({"ok": False, "mensaje": f"No existe la regla {id_regla}."}), 404
    return jsonify({"ok": True, "regla": regla})


@bp.route("/api/reglas/<int:id_regla>", methods=["DELETE"])
def borrar_regla(id_regla):
    # Llama a MotorReglas.eliminar; False significa que no existía.
    if not motor_reglas.eliminar(id_regla):
        return jsonify({"ok": False, "mensaje": f"No existe la regla {id_regla}."}), 404
    return jsonify({"ok": True, "mensaje": f"Regla {id_regla} borrada."})


@bp.route("/api/reglas/pausa", methods=["POST"])
def pausar_reglas():
    datos = request.get_json(silent=True) or {}
    if not isinstance(datos.get("pausadas"), bool):
        return jsonify({"ok": False, "mensaje": "Indicá si las reglas deben pausarse."}), 400

    # Llama a MotorReglas.pausar.
    pausadas = motor_reglas.pausar(datos["pausadas"])
    return jsonify({
        "ok": True,
        "pausadas": pausadas,
        "mensaje": "Reglas en pausa." if pausadas else "Reglas reanudadas.",
    })

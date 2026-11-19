# servidor/rutas/servo.py
"""Control del servomotor.

RUTAS
  POST /api/servo   mueve el servo al ángulo {"angulo": 0..180} (botón «Aplicar posición», static/js/voz.js).
"""
from flask import Blueprint, current_app, jsonify, request

from funciones import dispositivos as hw

bp = Blueprint("servo", __name__)


@bp.route("/api/servo", methods=["POST"])
def controlar_servo():
    datos = request.get_json(silent=True) or {}
    angulo = datos.get("angulo")

    if isinstance(angulo, bool) or not isinstance(angulo, int):
        return jsonify({
            "ok": False,
            "mensaje": "El ángulo debe ser un número entero.",
        }), 400
    if not 0 <= angulo <= 180:
        return jsonify({
            "ok": False,
            "mensaje": "El ángulo debe estar entre 0 y 180.",
        }), 400

    try:
        # Llama a dispositivos.mover_servo (tarda ~0,5 s en llegar).
        hw.mover_servo(angulo)
        return jsonify({
            "ok": True,
            "mensaje": f"Posición solicitada: {angulo}°.",
            "angulo": angulo,
        })
    except Exception:
        current_app.logger.exception("Error al mover el servo")
        return jsonify({
            "ok": False,
            "mensaje": "No se pudo controlar el servo.",
        }), 500

# servidor/rutas/sensor.py
"""Sensor ultrasónico: activación, distancia actual e historial para el gráfico.

RUTAS
  POST /api/sensor               activa o desactiva la medición continua ({"accion": "activar"|"desactivar"}).
  GET  /api/distancia            la distancia actual (avisa si el sensor está desactivado).
  GET  /api/distancia/historial  mediciones recientes para el gráfico (static/js/grafico.js);
                                 con ?desde=<momento> entrega solo las nuevas (sensor_monitor.py).
"""
from flask import Blueprint, current_app, jsonify, request

from funciones import dispositivos as hw

from .. import config
from ..respuestas import sin_cache
from ..servicios import leer_distancia, monitor

bp = Blueprint("sensor", __name__)


@bp.route("/api/sensor", methods=["POST"])
def controlar_sensor():
    datos = request.get_json(silent=True) or {}
    accion = datos.get("accion")
    if accion not in ("activar", "desactivar"):
        return jsonify({"ok": False, "mensaje": "Acción de sensor no válida."}), 400

    activo = accion == "activar"
    # Llama a dispositivos.configurar_sensor. Desde ese momento el hilo de sensor_monitor.py empieza (o deja) de medir.
    hw.configurar_sensor(activo)
    if activo:
        mensaje = "Medición continua activada."
    else:
        mensaje = "Medición continua desactivada."

    return jsonify({
        "ok": True,
        "mensaje": mensaje,
        "sensor_activo": activo,
    })


@bp.route("/api/distancia")
def distancia():
    if not hw.sensor_esta_activo():
        return jsonify({
            "ok": False,
            "sensor_activo": False,
            "distancia_cm": None,
            "mensaje": "El sensor está desactivado.",
        })

    try:
        # Usa la última medición del monitor (ver servicios.leer_distancia).
        valor = leer_distancia()
        return jsonify({
            "ok": valor is not None,
            "sensor_activo": True,
            "distancia_cm": valor,
            "mensaje": "Medición actualizada." if valor is not None else "No se obtuvo una medición válida.",
        })
    except Exception:
        current_app.logger.exception("Error al medir la distancia")
        return jsonify({
            "ok": False,
            "sensor_activo": True,
            "distancia_cm": None,
            "mensaje": "No se pudo consultar el sensor.",
        }), 500


@bp.route("/api/distancia/historial")
def historial_distancia():
    """Mediciones recientes para el gráfico. ?desde=<momento> devuelve solo las nuevas."""
    try:
        desde = float(request.args.get("desde", 0))
    except ValueError:
        desde = 0.0

    return sin_cache(jsonify({
        "ok": True,
        "disponible": monitor.corriendo,
        "sensor_activo": hw.sensor_esta_activo(),
        "ahora": round(monitor.ahora(), 3),
        "ventana_s": config.VENTANA_GRAFICO_S,
        "muestras": monitor.muestras_desde(desde),
    }))

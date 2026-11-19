# servidor/rutas/configuracion.py
"""Configuración del asistente: modo, palabras de activación y tiempo de espera.

RUTAS
  GET /api/configuracion   la consulta static/js/asistente.js al cargar la página (después se mantiene al día con /api/estado).
  PUT /api/configuracion   cambia uno o varios ajustes del asistente.
"""
from flask import Blueprint, current_app, jsonify, request

from funciones.asistente import ErrorDeConfiguracion

from .. import palabras_inicio
from ..respuestas import sin_cache
from ..servicios import asistente

bp = Blueprint("configuracion", __name__)


@bp.route("/api/configuracion", methods=["GET"])
def leer_configuracion():
    """GET /api/configuracion: modo, palabras de activación, tiempo de espera y estado de la sesión."""
    return sin_cache(jsonify({"ok": True, "asistente": asistente.estado()}))


@bp.route("/api/configuracion", methods=["PUT"])
def guardar_configuracion():
    """PUT /api/configuracion: cambia uno o varios ajustes del asistente.

    Cuerpo (todos los campos son opcionales, pero debe haber al menos uno):
        {"modo": "siempre"|"asistente", "espera_s": 30, "palabras": ["comando", "robot"]}
    Se valida todo antes de aplicar nada: si un ajuste es inválido no se cambia ninguno.
    """
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify({"ok": False, "mensaje": "Faltan los datos de la configuración."}), 400

    # Solo se aceptan los campos conocidos (un nombre mal escrito en el pedido se avisa en vez de ignorarse).
    desconocidos = sorted(set(datos) - {"modo", "espera_s", "palabras"})
    if desconocidos:
        return jsonify({"ok": False, "mensaje": f"Ajuste desconocido: {', '.join(desconocidos)}."}), 400
    if not datos:
        return jsonify({"ok": False, "mensaje": "No hay ningún ajuste para cambiar."}), 400

    try:
        asistente.configurar(
            modo=datos.get("modo"),
            espera_s=datos.get("espera_s"),
            palabras=datos.get("palabras"),
        )
    except ErrorDeConfiguracion as error:
        # El motivo (palabra repetida, reservada, demasiado larga...) se muestra en la página.
        return jsonify({"ok": False, "mensaje": str(error)}), 400
    except Exception:
        current_app.logger.exception("Error al guardar la configuración del asistente")
        return jsonify({"ok": False, "mensaje": "No se pudo guardar la configuración."}), 500

    # Si cambiaron las palabras, se activan ya mismo: la próxima frase se reconoce con las nuevas.
    palabras_inicio.aplicar_palabras_de_inicio(asistente.palabras())
    return jsonify({"ok": True, "mensaje": "Configuración guardada.", "asistente": asistente.estado()})

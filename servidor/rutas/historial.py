# servidor/rutas/historial.py
"""Registro de comandos: historial de órdenes de voz y de reglas disparadas (registro.py).

RUTAS (las consulta static/js/registro.js cada segundo)
  GET    /api/registro   eventos nuevos desde un id (?desde=<id>).
  DELETE /api/registro   vacía el historial (botón «Limpiar»).
"""
from flask import Blueprint, jsonify, request

from funciones.registro import registro

from ..respuestas import sin_cache

bp = Blueprint("historial", __name__)


@bp.route("/api/registro", methods=["GET"])
def consultar_registro():
    """Eventos nuevos desde ?desde=<id>. base_id indica qué ids siguen vigentes."""
    try:
        desde = int(request.args.get("desde", 0))
    except ValueError:
        desde = 0

    # Pide a registro.py hasta qué id se llegó y cuáles siguen vigentes; después devuelve solo los eventos nuevos (registro.desde).
    ultimo_id, base_id = registro.posicion()
    return sin_cache(jsonify({
        "ok": True,
        "entradas": registro.desde(desde),
        "ultimo_id": ultimo_id,
        "base_id": base_id,
    }))


@bp.route("/api/registro", methods=["DELETE"])
def limpiar_registro():
    # Llama a registro.limpiar y devuelve cuántos eventos se borraron.
    cantidad = registro.limpiar()
    return jsonify({"ok": True, "mensaje": "Registro limpio.", "borradas": cantidad})

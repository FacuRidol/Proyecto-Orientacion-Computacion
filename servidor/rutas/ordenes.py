# servidor/rutas/ordenes.py
"""POST /api/comando: la función central del proyecto.

Recibe el texto de una frase ({"comando": "robot encender cocina"}), la interpreta y ejecuta.
Lo llama static/js/voz.js (función procesarComando) con lo que reconoció Vosk.

QUÉ HACE, EN ORDEN
  1. Limpia el texto y comprueba que no esté vacío ni sea demasiado largo.
  2. Averigua si empieza con una palabra de activación y si el asistente está despierto (modo asistente).
     Sin palabra y con el asistente dormido, la frase se ignora.
  3. Si se dijo SOLO la palabra de activación: responde con el saludo (y despierta al asistente en modo asistente).
  4. Divide la frase en órdenes («... y activar sensor») y ejecuta cada una por separado (interprete.ordenes).
  5. Actualiza la sesión del asistente y deja en «g.eventos» lo que hay que anotar en el registro.
  6. Responde. Con una sola orden la respuesta es la de siempre (con el estado del asistente agregado);
     con varias, trae «resultados» (uno por orden) y un mensaje que los resume.

Las funciones que entienden cada tipo de orden están en servidor/interprete/.
"""
from flask import Blueprint, current_app, g, jsonify, request

from funciones.registro import registro

from .. import palabras_inicio
from ..interprete.division import MAX_ORDENES, dividir_en_ordenes
from ..interprete.ordenes import ejecutar_orden
from ..interprete.sesion import mensaje_de_bienvenida
from ..servicios import asistente
from ..texto import normalizar

bp = Blueprint("ordenes", __name__)


@bp.route("/api/comando", methods=["POST"])
def comando():
    datos = request.get_json(silent=True) or {}
    # «original» es lo que llegó (con tildes y mayúsculas, para mostrarlo en el registro); «texto», la versión normalizada.
    original = str(datos.get("comando", "")).strip()
    texto = normalizar(original)

    # Rechaza frases vacías o demasiado largas.
    if not texto or len(texto) > 200:
        return jsonify({"ok": False, "mensaje": "El comando está vacío o es demasiado largo."}), 400

    # Estado del asistente: ¿modo asistente? ¿está despierto (puede recibir órdenes sin palabra de activación)?
    modo_asistente = asistente.modo() == "asistente"
    en_sesion = asistente.sesion_activa()

    # Busca una palabra de activación al comienzo. «palabra» es la que usó la persona (None si no dijo ninguna)
    # y «resto» lo que sigue (si no había palabra, es la frase completa).
    palabra, resto = palabras_inicio.separar_palabra_de_inicio(texto)

    # Sin palabra de activación y con el asistente dormido: la frase no es para el sistema.
    # (registrar_orden_de_voz la anota como «ignorado»: sirve para ver qué está escuchando Vosk.)
    if palabra is None and not en_sesion:
        palabras = palabras_inicio.actual
        consigna = (
            f"con la palabra ‘{palabras.principal}’"
            if len(palabras.mostradas) == 1
            else f"con {palabras.mensaje}"
        )
        mensaje = f"Empezá la orden {consigna}. Ejemplo: ‘{palabras.principal} LED uno encender’."
        if modo_asistente:
            mensaje += f" O decí solo ‘{palabras.principal}’ para que el asistente te escuche sin repetirla."
        return jsonify({"ok": False, "mensaje": mensaje}), 400

    # SALUDO: se dijo solo la palabra de activación. El asistente responde con la bienvenida y, en
    # modo asistente, queda despierto: las próximas órdenes no necesitan la palabra.
    if palabra is not None and not resto:
        asistente.despertar()
        mensaje = mensaje_de_bienvenida(palabra)
        g.eventos = [(original, mensaje, "ok")]
        return jsonify({"ok": True, "mensaje": mensaje, "bienvenida": True, "asistente": asistente.estado()})

    # VARIAS ÓRDENES: divide la frase («encender led uno y activar sensor» -> dos órdenes).
    # Si no se pudo dividir (frase rara) se usa entera.
    ordenes = dividir_en_ordenes(resto) or [resto]
    if len(ordenes) > MAX_ORDENES:
        return jsonify({"ok": False, "mensaje": f"Son demasiadas órdenes juntas (máximo {MAX_ORDENES}). Dígalas en frases separadas."}), 400

    # Ejecuta cada orden por separado: cada una se interpreta SOLO con sus propias palabras clave, así no se
    # mezclan. Los mensajes de ejemplo usan la palabra que dijo la persona (o la principal si no dijo ninguna).
    palabra_de_ejemplo = palabra or palabras_inicio.actual.principal
    resultados = []
    for orden in ordenes:
        cuerpo, codigo = ejecutar_orden(orden, palabra_de_ejemplo)
        resultados.append((orden, cuerpo, codigo))

    # SESIÓN: actualiza el estado del asistente.
    #   · «adiós»: ya durmió dentro de interpretar_despedida.
    #   · Dijo la palabra de activación: despierta (o renueva) la sesión. En modo «siempre» no hace nada.
    #   · No la dijo (conversación abierta): si alguna orden salió bien, renueva el tiempo de espera.
    algun_exito = any(cuerpo.get("ok") for _, cuerpo, _ in resultados)
    if any(cuerpo.get("despedida") for _, cuerpo, _ in resultados):
        pass
    elif palabra is not None:
        asistente.despertar()
    elif algun_exito:
        asistente.extender()

    # Prepara lo que registrar_orden_de_voz anotará en el registro (una entrada por orden).
    eventos = []
    for orden, cuerpo, _ in resultados:
        if cuerpo.get("ok"):
            estado = "ok"
        elif palabra is None:
            # Sin palabra de activación (conversación abierta) un fallo no es un error del usuario: puede ser charla.
            estado = "ignorado"
        else:
            estado = "error"
        # Con una sola orden se anota lo que se dijo; con varias, cada orden con la palabra de activación delante.
        if len(resultados) == 1:
            texto_evento = original
        else:
            texto_evento = f"{palabra} {orden}" if palabra else orden
        eventos.append((texto_evento, cuerpo.get("mensaje", ""), estado))
    g.eventos = eventos

    # Una sola orden: respuesta igual a la de siempre (la página ya la sabe interpretar), más el estado del asistente.
    if len(resultados) == 1:
        _, cuerpo, codigo = resultados[0]
        cuerpo["asistente"] = asistente.estado()
        if palabra is None and not cuerpo.get("ok"):
            # En conversación abierta, lo que no se entiende se informa pero sin tratarlo como error.
            cuerpo["ignorado"] = True
            codigo = 200
        return jsonify(cuerpo), codigo

    # Varias órdenes: «resultados» trae la respuesta de cada una (la página aplica cada una) y «mensaje» las resume.
    return jsonify({
        "ok": all(cuerpo.get("ok") for _, cuerpo, _ in resultados),
        "mensaje": " · ".join(cuerpo.get("mensaje", "") for _, cuerpo, _ in resultados),
        "resultados": [cuerpo for _, cuerpo, _ in resultados],
        "asistente": asistente.estado(),
    })


# Se ejecuta DESPUÉS de cada petición de este blueprint (o sea, solo de /api/comando), justo antes de
# enviar la respuesta. Las demás rutas, que la página consulta cada segundo, ya no pasan por acá.
@bp.after_request
def registrar_orden_de_voz(respuesta):
    """Anota cada orden recibida en /api/comando con su resultado: «ok», «error» o «ignorado».

    Se hace acá, y no dentro de comando(), para cubrir todos sus puntos de salida sin tocarlos.
    Las frases que no empiezan con una palabra de inicio se anotan como «ignorado»: sirven para
    ver qué está escuchando Vosk (panel «Registro de comandos»).
    """
    if request.method != "POST":
        return respuesta

    try:
        # comando() deja en «g.eventos» la lista (texto, resultado, estado) de lo que ejecutó. Es una lista porque
        # una sola frase puede contener varias órdenes (se anota una por orden). «g» vive solo durante esta petición.
        eventos = g.pop("eventos", None)
        if eventos:
            for texto_evento, mensaje_evento, estado_evento in eventos:
                registro.agregar("voz", texto_evento, mensaje_evento, estado_evento)
            return respuesta

        datos = request.get_json(silent=True) or {}
        texto = str(datos.get("comando", "")).strip()
        if texto:
            cuerpo = respuesta.get_json(silent=True) or {}
            if respuesta.status_code < 400:
                estado = "ok"
            elif palabras_inicio.separar_palabra_de_inicio(normalizar(texto))[0] is None:
                estado = "ignorado"
            else:
                estado = "error"
            registro.agregar("voz", texto, cuerpo.get("mensaje", ""), estado)
    except Exception:
        current_app.logger.exception("No se pudo anotar la orden en el registro")

    return respuesta

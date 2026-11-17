// Salida de voz: lee en voz alta las respuestas del asistente.
// Usa la síntesis de voz del navegador (Web Speech API), sin instalar nada en el servidor.
(function () {
    "use strict";

    const sintesis = window.speechSynthesis;
    const CLAVE_AJUSTE = "vozRespuestasActivas";
    // Margen tras terminar de hablar, para que el eco no llegue a Vosk.
    const MARGEN_ECO_MS = 600;
    const INTERVALO_VIGILANCIA_MS = 400;
    const PREFERENCIA_IDIOMAS = ["es-ar", "es-419", "es-us", "es-mx", "es-es"];

    let activa = true;
    let hablando = false;
    let silencioHasta = 0;
    let numeroLectura = 0;
    let temporizadorRespaldo = null;
    let temporizadorVigilancia = null;
    let limiteLectura = 0;
    let seObservoHabla = false;

    try {
        activa = window.localStorage.getItem(CLAVE_AJUSTE) !== "no";
    } catch (error) { /* sin almacenamiento: queda activa */ }

    function elegirVoz() {
        if (!sintesis) {
            return null;
        }
        let voces = [];
        try {
            voces = sintesis.getVoices().filter(function (voz) {
                return /^es([-_]|$)/i.test(voz.lang);
            });
        } catch (error) {
            return null;
        }
        for (const idioma of PREFERENCIA_IDIOMAS) {
            const encontrada = voces.find(function (voz) {
                return voz.lang.replace("_", "-").toLowerCase() === idioma;
            });
            if (encontrada) {
                return encontrada;
            }
        }
        return voces[0] || null;
    }

    function limpiarTemporizadores() {
        if (temporizadorRespaldo !== null) {
            window.clearTimeout(temporizadorRespaldo);
            temporizadorRespaldo = null;
        }
        if (temporizadorVigilancia !== null) {
            window.clearTimeout(temporizadorVigilancia);
            temporizadorVigilancia = null;
        }
    }

    function terminar(numero) {
        // Ignora los eventos tardíos de una lectura cancelada o reemplazada.
        if (numero !== numeroLectura || !hablando) {
            return;
        }
        limpiarTemporizadores();
        hablando = false;
        limiteLectura = 0;
        seObservoHabla = false;
        silencioHasta = Date.now() + MARGEN_ECO_MS;
    }

    // Algunos navegadores no disparan onend/onerror de forma fiable. Además
    // de esos eventos, observamos el estado real de speechSynthesis y esperamos
    // varias comprobaciones inactivas antes de liberar el micrófono.
    function programarVigilancia(numero, comprobacionesInactivas) {
        if (temporizadorVigilancia !== null) {
            window.clearTimeout(temporizadorVigilancia);
        }
        temporizadorVigilancia = window.setTimeout(function () {
            temporizadorVigilancia = null;
            vigilarLectura(numero, comprobacionesInactivas);
        }, INTERVALO_VIGILANCIA_MS);
    }

    function vigilarLectura(numero, comprobacionesInactivas) {
        if (numero !== numeroLectura || !hablando || !sintesis) {
            return;
        }

        let sigueActiva = false;
        try {
            sigueActiva = Boolean(sintesis.speaking || sintesis.pending || sintesis.paused);
        } catch (error) {
            // El temporizador de respaldo sigue protegiendo ante errores de la API.
        }

        if (sigueActiva) {
            seObservoHabla = true;
            comprobacionesInactivas = 0;
        } else if (seObservoHabla) {
            comprobacionesInactivas += 1;
            if (comprobacionesInactivas >= 3) {
                terminar(numero);
                return;
            }
        }

        programarVigilancia(numero, comprobacionesInactivas);
    }

    function tiempoMaximoLectura(texto) {
        // Margen conservador para voces lentas y textos largos (aprox. 9 caracteres/s).
        // El límite evita un bloqueo permanente si el navegador nunca informa el final.
        return Math.min(90000, Math.max(8000, 3500 + texto.length * 110));
    }

    function recuperarLecturaAtascada() {
        if (!hablando || !limiteLectura || Date.now() < limiteLectura) {
            return;
        }
        const numero = numeroLectura;
        // Si la síntesis quedó colgada, se cancela antes de volver a permitir
        // el envío del micrófono, para no mandar el audio del propio asistente a Vosk.
        try {
            sintesis.cancel();
        } catch (error) { /* la liberación del estado no depende de cancel() */ }
        terminar(numero);
    }

    function ocupado() {
        // También se comprueba el límite aquí por si el navegador ralentiza
        // los temporizadores (por ejemplo, con una pestaña en segundo plano).
        recuperarLecturaAtascada();
        return hablando || Date.now() < silencioHasta;
    }

    function hablar(texto) {
        if (!sintesis || !activa || !texto) {
            return;
        }
        const limpio = String(texto).replace(/[«»"“”]/g, "").trim();
        if (!limpio) {
            return;
        }

        const numero = ++numeroLectura;
        limpiarTemporizadores();
        try {
            // Se reemplaza cualquier lectura anterior; sus eventos tardíos
            // quedan invalidados por el número de lectura.
            sintesis.cancel();
        } catch (error) { /* se intenta iniciar la nueva lectura igualmente */ }

        let lectura;
        try {
            lectura = new SpeechSynthesisUtterance(limpio);
        } catch (error) {
            hablando = true;
            terminar(numero);
            return;
        }

        const voz = elegirVoz();
        if (voz) {
            lectura.voice = voz;
            lectura.lang = voz.lang;
        } else {
            lectura.lang = "es-AR";
        }

        lectura.onstart = function () {
            if (numero !== numeroLectura || !hablando) {
                return;
            }
            // Un onstart sin estado speaking fiable no deja el bloqueo abierto:
            // la vigilancia y el temporizador de respaldo siguen activos.
            programarVigilancia(numero, 0);
        };
        lectura.onend = function () { terminar(numero); };
        lectura.onerror = function () { terminar(numero); };

        // Se bloquea antes de speak() para que no se filtre el audio del comienzo.
        hablando = true;
        seObservoHabla = false;
        limiteLectura = Date.now() + tiempoMaximoLectura(limpio);
        temporizadorRespaldo = window.setTimeout(function () {
            recuperarLecturaAtascada();
        }, Math.max(0, limiteLectura - Date.now()));

        try {
            sintesis.speak(lectura);
            // También sondeamos aunque el navegador no emita onstart.
            if (numero === numeroLectura && hablando && temporizadorVigilancia === null) {
                programarVigilancia(numero, 0);
            }
        } catch (error) {
            terminar(numero);
        }
    }

    function silenciar() {
        numeroLectura++;
        limpiarTemporizadores();
        if (sintesis) {
            try {
                sintesis.cancel();
            } catch (error) { /* el estado local se libera igualmente */ }
        }
        hablando = false;
        limiteLectura = 0;
        seObservoHabla = false;
        silencioHasta = Date.now() + MARGEN_ECO_MS;
    }

    function configurar(valor) {
        activa = Boolean(valor);
        try {
            window.localStorage.setItem(CLAVE_AJUSTE, activa ? "si" : "no");
        } catch (error) { /* se ignora */ }
        if (!activa) {
            silenciar();
        }
    }

    // Mientras el asistente habla, no se manda audio del micrófono a Vosk.
    // Si no, Vosk escucharía al asistente y lo tomaría como un comando.
    const fetchOriginal = window.fetch.bind(window);
    window.fetch = function (entrada, opciones) {
        const direccion = typeof entrada === "string" ? entrada : (entrada && entrada.url) || "";
        if (direccion.indexOf("/api/voz/audio") !== -1 && ocupado()) {
            return Promise.resolve(new Response(
                JSON.stringify({ ok: true, final: false, texto: "", parcial: "" }),
                { status: 200, headers: { "Content-Type": "application/json" } }
            ));
        }
        return fetchOriginal(entrada, opciones);
    };

    window.vozSalida = {
        hablar: hablar,
        silenciar: silenciar,
        configurar: configurar,
        disponible: Boolean(sintesis),
        ocupado: ocupado,
    };

    const casilla = document.getElementById("voz-respuestas");
    if (casilla) {
        if (!sintesis) {
            casilla.disabled = true;
            casilla.checked = false;
            casilla.parentElement.title = "Este navegador no tiene síntesis de voz.";
        } else {
            casilla.checked = activa;
            casilla.addEventListener("change", function () {
                configurar(casilla.checked);
            });
        }
    }

    // Algunos navegadores cargan las voces de forma diferida; no hace falta hacer nada,
    // elegirVoz() las consulta en cada lectura.
})();

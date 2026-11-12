// static/js/automatizaciones.js
// Panel «Automatizaciones»: crear, activar, pausar y borrar reglas del tipo
// «si la distancia es menor a 20 cm, encender el LED 1».
//
// Las reglas viven en el servidor (automatizaciones.py) y las evalúa el monitor
// del sensor, así que siguen funcionando aunque se cierre esta página. Acá solo
// se muestran y se editan. La lista se pide cada segundo para que lo que se
// cree por voz o desde otra pantalla aparezca enseguida.

(function () {
    const formulario = document.getElementById("formulario-regla");
    if (!formulario) {
        return;
    }

    const campoCondicion = document.getElementById("regla-condicion");
    const campoUmbral = document.getElementById("regla-umbral");
    const campoAccion = document.getElementById("regla-accion");
    const campoLed = document.getElementById("regla-led");
    const grupoAngulo = document.getElementById("regla-angulo-grupo");
    const campoAngulo = document.getElementById("regla-angulo");
    const botonAgregar = document.getElementById("agregar-regla");
    const botonPausa = document.getElementById("pausar-reglas");
    const mensaje = document.getElementById("regla-mensaje");
    const lista = document.getElementById("lista-reglas");
    const textoVacio = document.getElementById("reglas-vacio");
    const nota = document.getElementById("reglas-nota");

    const ICONO_BORRAR =
        '<svg class="icono" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2m-9 0 1 14h8l1-14M10 11v6M14 11v6"/></svg>';

    let estado = null;       // última respuesta de /api/reglas
    let consultando = false;
    let repetir = false;     // llegó un pedido mientras se consultaba: se repite al terminar
    let temporizador = null;
    let ocultarMensaje = null;

    // ---------- comunicación con el servidor ----------

    async function peticion(url, metodo = "GET", cuerpo) {
        const opciones = { method: metodo, cache: "no-store", headers: {} };
        if (cuerpo !== undefined) {
            opciones.headers["Content-Type"] = "application/json";
            opciones.body = JSON.stringify(cuerpo);
        }
        const respuesta = await fetch(url, opciones);
        let datos = {};
        try {
            datos = await respuesta.json();
        } catch (error) {
            // Respuesta sin cuerpo: se usa el estado HTTP.
        }
        return { ok: respuesta.ok, datos };
    }

    function mostrarMensaje(texto, tipo) {
        clearTimeout(ocultarMensaje);
        mensaje.textContent = texto;
        mensaje.classList.toggle("estado-correcto", tipo === "ok");
        mensaje.classList.toggle("estado-error", tipo === "error");
        mensaje.hidden = false;
        ocultarMensaje = setTimeout(() => {
            mensaje.hidden = true;
        }, tipo === "ok" ? 4000 : 8000);
    }

    async function refrescar() {
        if (consultando) {
            repetir = true;
            return;
        }
        consultando = true;
        try {
            const { ok, datos } = await peticion("/api/reglas");
            if (ok) {
                estado = datos;
                dibujar();
            }
        } catch (error) {
            // Se conserva lo que ya se mostraba.
        } finally {
            consultando = false;
            if (repetir) {
                repetir = false;
                refrescar();
            } else {
                programar();
            }
        }
    }

    function programar() {
        clearTimeout(temporizador);
        if (!document.hidden) {
            temporizador = setTimeout(refrescar, 1000);
        }
    }

    // ---------- formulario ----------

    // El menú muestra el nombre actual de cada LED («cocina») en lugar de «LED 1».
    // El valor de cada opción sigue siendo el número, que es lo que recibe el servidor.
    function rellenarLeds(leds, nombres = {}) {
        const etiqueta = (numero) => nombres[numero]?.nombre || `LED ${numero}`;

        const actuales = [...campoLed.options].map((opcion) => Number(opcion.value));
        if (actuales.length === leds.length && actuales.every((n, i) => n === leds[i])) {
            // Mismos LED: solo se corrigen los textos que cambiaron (así no se
            // pierde la opción elegida ni se cierra el menú abierto).
            [...campoLed.options].forEach((opcion, i) => {
                const texto = etiqueta(leds[i]);
                if (opcion.textContent !== texto) {
                    opcion.textContent = texto;
                }
            });
            return;
        }
        const elegido = campoLed.value;
        campoLed.replaceChildren(
            ...leds.map((numero) => {
                const opcion = document.createElement("option");
                opcion.value = String(numero);
                opcion.textContent = etiqueta(numero);
                return opcion;
            })
        );
        if (elegido) {
            campoLed.value = elegido;
        }
    }

    // Solo se muestra el campo que hace falta para la acción elegida.
    function ajustarCamposDeAccion() {
        const accion = campoAccion.value;
        campoLed.hidden = !(accion === "led-on" || accion === "led-off");
        grupoAngulo.hidden = accion !== "servo";
    }

    function construirAccion() {
        switch (campoAccion.value) {
            case "led-on":
                return { tipo: "led", led: Number(campoLed.value), encender: true };
            case "led-off":
                return { tipo: "led", led: Number(campoLed.value), encender: false };
            case "leds-on":
                return { tipo: "leds", encender: true };
            case "leds-off":
                return { tipo: "leds", encender: false };
            default:
                return { tipo: "servo", angulo: Number(campoAngulo.value) };
        }
    }

    formulario.addEventListener("submit", async (evento) => {
        evento.preventDefault();

        if (campoUmbral.value.trim() === "") {
            mostrarMensaje("Escribí la distancia en centímetros.", "error");
            campoUmbral.focus();
            return;
        }
        if (campoAccion.value === "servo" && campoAngulo.value.trim() === "") {
            mostrarMensaje("Escribí el ángulo del servo (0 a 180).", "error");
            campoAngulo.focus();
            return;
        }

        botonAgregar.disabled = true;
        try {
            const { ok, datos } = await peticion("/api/reglas", "POST", {
                condicion: campoCondicion.value,
                umbral_cm: Number(campoUmbral.value),
                accion: construirAccion(),
            });
            if (ok) {
                mostrarMensaje(`Regla ${datos.regla.id} creada.`, "ok");
            } else {
                mostrarMensaje(datos.mensaje || "No se pudo crear la regla.", "error");
            }
        } catch (error) {
            mostrarMensaje("No se pudo conectar con el servidor.", "error");
        }
        await refrescar();
    });

    campoAccion.addEventListener("change", ajustarCamposDeAccion);

    botonPausa.addEventListener("click", async () => {
        if (!estado) {
            return;
        }
        try {
            await peticion("/api/reglas/pausa", "POST", { pausadas: !estado.pausadas });
        } catch (error) {
            mostrarMensaje("No se pudo conectar con el servidor.", "error");
        }
        await refrescar();
    });

    // ---------- lista de reglas ----------

    function haceCuanto(segundos) {
        if (segundos < 60) return `${Math.max(0, Math.round(segundos))} s`;
        if (segundos < 3600) return `${Math.round(segundos / 60)} min`;
        return `${Math.round(segundos / 3600)} h`;
    }

    function crearFila(regla) {
        const fila = document.createElement("li");
        fila.className = "regla";
        fila.dataset.id = String(regla.id);

        const indicador = document.createElement("span");
        indicador.className = "regla-indicador";
        indicador.setAttribute("aria-hidden", "true");

        const cuerpo = document.createElement("div");
        cuerpo.className = "regla-cuerpo";
        const descripcion = document.createElement("p");
        descripcion.className = "regla-descripcion";
        const meta = document.createElement("p");
        meta.className = "regla-meta";
        cuerpo.append(descripcion, meta);

        const interruptor = document.createElement("label");
        interruptor.className = "interruptor";
        const casilla = document.createElement("input");
        casilla.type = "checkbox";
        casilla.setAttribute("role", "switch");
        const pista = document.createElement("span");
        pista.className = "interruptor-pista";
        pista.setAttribute("aria-hidden", "true");
        interruptor.append(casilla, pista);

        const borrar = document.createElement("button");
        borrar.type = "button";
        borrar.className = "boton-icono";
        borrar.innerHTML = ICONO_BORRAR;

        casilla.addEventListener("change", async () => {
            try {
                await peticion(`/api/reglas/${regla.id}`, "PATCH", { activa: casilla.checked });
            } catch (error) {
                mostrarMensaje("No se pudo conectar con el servidor.", "error");
            }
            await refrescar();
        });

        borrar.addEventListener("click", async () => {
            try {
                await peticion(`/api/reglas/${regla.id}`, "DELETE");
            } catch (error) {
                mostrarMensaje("No se pudo conectar con el servidor.", "error");
            }
            await refrescar();
        });

        fila.append(indicador, cuerpo, interruptor, borrar);
        return fila;
    }

    function actualizarFila(fila, regla) {
        const situacion = !regla.activa ? "inactiva"
            : estado.pausadas ? "pausada"
            : regla.cumplida ? "cumplida"
            : "espera";
        const textoSituacion = {
            inactiva: "Desactivada",
            pausada: "En pausa",
            cumplida: "Se cumple ahora",
            espera: "En espera",
        }[situacion];

        let meta = `Regla ${regla.id} · ${textoSituacion}`;
        if (regla.disparos > 0) {
            meta += ` · ${regla.disparos} ${regla.disparos === 1 ? "disparo" : "disparos"}`;
            if (regla.ultimo_disparo && estado.ahora) {
                meta += ` · último hace ${haceCuanto(estado.ahora - regla.ultimo_disparo)}`;
            }
        }

        fila.dataset.situacion = situacion;
        asignarTexto(fila.querySelector(".regla-descripcion"), regla.descripcion);
        asignarTexto(fila.querySelector(".regla-meta"), meta);

        const casilla = fila.querySelector("input");
        casilla.checked = regla.activa;
        casilla.setAttribute("aria-label", `Regla ${regla.id} activa`);
        fila.querySelector(".boton-icono").setAttribute("aria-label", `Borrar regla ${regla.id}`);
    }

    // Solo se toca el DOM si el texto cambió (evita parpadeos y pérdida de selección).
    function asignarTexto(elemento, texto) {
        if (elemento.textContent !== texto) {
            elemento.textContent = texto;
        }
    }

    function dibujar() {
        if (!estado) {
            return;
        }

        campoUmbral.min = String(estado.umbral_min);
        campoUmbral.max = String(estado.umbral_max);
        rellenarLeds(estado.leds, estado.nombres_leds);
        ajustarCamposDeAccion();

        const lleno = estado.reglas.length >= estado.maximo;
        botonAgregar.disabled = lleno;
        botonAgregar.title = lleno ? `Ya hay ${estado.maximo} reglas: borrá alguna para agregar otra.` : "";

        botonPausa.disabled = estado.reglas.length === 0;
        botonPausa.textContent = estado.pausadas ? "Reanudar reglas" : "Pausar reglas";
        botonPausa.setAttribute("aria-pressed", String(estado.pausadas));

        // La lista se actualiza fila por fila, sin reconstruirla: así el foco del
        // teclado no se pierde cada segundo.
        const existentes = new Map([...lista.children].map((fila) => [Number(fila.dataset.id), fila]));
        let anterior = null;
        for (const regla of estado.reglas) {
            let fila = existentes.get(regla.id);
            if (fila) {
                existentes.delete(regla.id);
            } else {
                fila = crearFila(regla);
            }
            actualizarFila(fila, regla);

            const esperada = anterior ? anterior.nextElementSibling : lista.firstElementChild;
            if (fila !== esperada) {
                lista.insertBefore(fila, esperada);
            }
            anterior = fila;
        }
        for (const sobrante of existentes.values()) {
            sobrante.remove();
        }
        textoVacio.hidden = estado.reglas.length > 0;

        // Aviso: por qué las reglas podrían no estar actuando
        let aviso = "";
        if (estado.reglas.length && estado.pausadas) {
            aviso = "Las reglas están en pausa: no se dispara ninguna hasta que las reanudes.";
        } else if (estado.reglas.length && !estado.sensor_activo) {
            aviso = "El sensor está desactivado: las reglas solo se evalúan mientras mide. Activalo en el panel del sensor.";
        }
        nota.hidden = !aviso;
        asignarTexto(nota, aviso);
        nota.classList.toggle("estado-advertencia", Boolean(aviso));

        if (window.graficoDistancia) {
            window.graficoDistancia.fijarReglas(estado.reglas, estado.pausadas);
        }
    }

    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            clearTimeout(temporizador);
        } else {
            refrescar();
        }
    });

    window.automatizaciones = { refrescar };

    ajustarCamposDeAccion();
    refrescar();
})();

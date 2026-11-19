// static/js/automatizaciones.js
// Panel «Automatizaciones»: crear, activar, pausar y borrar reglas del tipo
// «si la distancia es menor a 20 cm, encender el LED 1».
//
// Las reglas viven en el servidor (automatizaciones.py) y las evalúa el monitor
// del sensor, así que siguen funcionando aunque se cierre esta página. Acá solo
// se muestran y se editan. La lista se pide cada segundo para que lo que se
// cree por voz o desde otra pantalla aparezca enseguida.

// ┌─────────────────────────────────────────────────────────────────────────┐
// │ DE QUIÉN DEPENDE / QUIÉN LO USA                                         │
// │  - templates/index.html: contiene el formulario y la lista que se       │
// │    controlan acá (#formulario-regla, #lista-reglas, #regla-*, ...).     │
// │  - app.py: GET/POST/DELETE /api/reglas, PATCH /api/reglas/<id> y        │
// │    POST /api/reglas/pausa. Las reglas las guarda y evalúa               │
// │    automatizaciones.py (con las mediciones de sensor_monitor.py).       │
// │  - static/js/grafico.js: se le entregan las reglas con                  │
// │    graficoDistancia.fijarReglas() para dibujar los umbrales.            │
// │  - static/js/voz.js llama a window.automatizaciones.refrescar() (se     │
// │    define al final) cuando cambian los nombres de los LED o se crea     │
// │    una regla por voz.                                                   │
// └─────────────────────────────────────────────────────────────────────────┘
// Función autoejecutable: mantiene sus variables privadas.
(function () {
    // Busca el formulario; si la página no lo tiene, el script no hace nada.
    const formulario = document.getElementById("formulario-regla");
    if (!formulario) {
        return;
    }

    // Elementos del formulario (condición, distancia, acción, LED, ángulo), botones, mensaje, lista de reglas y avisos. Todos están definidos en templates/index.html.
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

    // Dibujo (SVG) del icono de papelera del botón «Borrar».
    const ICONO_BORRAR =
        '<svg class="icono" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2m-9 0 1 14h8l1-14M10 11v6M14 11v6"/></svg>';

    // Estado interno: última respuesta del servidor, bandera de consulta en curso, bandera de «repetir» y temporizadores.
    let estado = null;       // última respuesta de /api/reglas
    let consultando = false;
    let repetir = false;     // llegó un pedido mientras se consultaba: se repite al terminar
    let temporizador = null;
    let ocultarMensaje = null;

    // Funciones que hablan con app.py.
    // ---------- comunicación con el servidor ----------

    // Envía una petición a app.py (y su cuerpo como JSON, si hay). Devuelve {ok, datos}; si la respuesta no tiene cuerpo usa un objeto vacío.
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

    // Muestra un aviso bajo el formulario (verde si salió bien, rojo si hubo error) y lo oculta solo a los 4 u 8 segundos.
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

    // Pide la lista de reglas actual y la dibuja. Se llama sola cada segundo, y también tras cada cambio.
    async function refrescar() {
        if (consultando) {
            repetir = true;
            return;
        }
        consultando = true;
        try {
            // GET /api/reglas (app.py -> motor_reglas.estado() + nombres de LED + estado del sensor).
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

    // Programa la próxima consulta dentro de 1 s (se detiene con la pestaña oculta).
    function programar() {
        clearTimeout(temporizador);
        if (!document.hidden) {
            temporizador = setTimeout(refrescar, 1000);
        }
    }

    // Lógica del formulario «Si la distancia es... entonces...».
    // ---------- formulario ----------

    // El menú muestra el nombre actual de cada LED («cocina») en lugar de «LED 1».
    // El valor de cada opción sigue siendo el número, que es lo que recibe el servidor.
    // Rellena el menú de LED con el NOMBRE actual de cada uno («cocina») en lugar de «LED 1». El valor sigue siendo el número, que es lo que recibe el servidor. Si los LED son los mismos solo corrige los textos, para no perder la opción elegida.
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
    // Muestra solo el campo necesario: el menú de LED para «encender/apagar LED» o el ángulo para «mover servo».
    function ajustarCamposDeAccion() {
        const accion = campoAccion.value;
        campoLed.hidden = !(accion === "led-on" || accion === "led-off");
        grupoAngulo.hidden = accion !== "servo";
    }

    // Arma la acción que se enviará a app.py según lo elegido en el formulario (led, leds o servo).
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

    // Al enviar el formulario: valida que haya distancia (y ángulo si hace falta) y crea la regla.
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
            // POST /api/reglas: app.py llama a MotorReglas.crear(), que valida todo y guarda la regla.
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

    // Al cambiar la acción, se ajustan los campos visibles.
    campoAccion.addEventListener("change", ajustarCamposDeAccion);

    // Botón «Pausar reglas / Reanudar reglas».
    botonPausa.addEventListener("click", async () => {
        if (!estado) {
            return;
        }
        try {
            // POST /api/reglas/pausa con el valor contrario al actual.
            await peticion("/api/reglas/pausa", "POST", { pausadas: !estado.pausadas });
        } catch (error) {
            mostrarMensaje("No se pudo conectar con el servidor.", "error");
        }
        await refrescar();
    });

    // Dibujo de cada regla de la lista.
    // ---------- lista de reglas ----------

    // Convierte segundos en «12 s», «3 min» o «2 h» (para «último disparo hace...»).
    function haceCuanto(segundos) {
        if (segundos < 60) return `${Math.max(0, Math.round(segundos))} s`;
        if (segundos < 3600) return `${Math.round(segundos / 60)} min`;
        return `${Math.round(segundos / 3600)} h`;
    }

    // Crea los elementos de una regla: indicador de estado, descripción, interruptor de activar y botón de borrar. Se crea una sola vez; después solo se actualiza (actualizarFila).
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

        // Interruptor de la regla: activa o desactiva con PATCH /api/reglas/<id>.
        casilla.addEventListener("change", async () => {
            try {
                // app.py -> MotorReglas.activar().
                await peticion(`/api/reglas/${regla.id}`, "PATCH", { activa: casilla.checked });
            } catch (error) {
                mostrarMensaje("No se pudo conectar con el servidor.", "error");
            }
            await refrescar();
        });

        // Botón de papelera: borra la regla con DELETE /api/reglas/<id> (app.py -> MotorReglas.eliminar).
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

    // Actualiza el texto de una fila con los datos del servidor: situación (desactivada, en pausa, se cumple ahora, en espera), cantidad de disparos y último disparo. La descripción ya viene escrita por el servidor, con el nombre actual del LED.
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
    // Cambia un texto solo si es distinto (evita parpadeos y pérdida de la selección).
    function asignarTexto(elemento, texto) {
        if (elemento.textContent !== texto) {
            elemento.textContent = texto;
        }
    }

    // Redibuja todo el panel con el último estado recibido.
    function dibujar() {
        if (!estado) {
            return;
        }

        campoUmbral.min = String(estado.umbral_min);
        campoUmbral.max = String(estado.umbral_max);
        // Actualiza el menú de LED con los nombres que llegaron del servidor (nombres_leds.py).
        rellenarLeds(estado.leds, estado.nombres_leds);
        ajustarCamposDeAccion();

        // Si ya hay el máximo de reglas, se deshabilita «Agregar»; el botón de pausa solo sirve si hay reglas.
        const lleno = estado.reglas.length >= estado.maximo;
        botonAgregar.disabled = lleno;
        botonAgregar.title = lleno ? `Ya hay ${estado.maximo} reglas: borrá alguna para agregar otra.` : "";

        botonPausa.disabled = estado.reglas.length === 0;
        botonPausa.textContent = estado.pausadas ? "Reanudar reglas" : "Pausar reglas";
        botonPausa.setAttribute("aria-pressed", String(estado.pausadas));

        // La lista se actualiza fila por fila, sin reconstruirla: así el foco del
        // teclado no se pierde cada segundo.
        // La lista se actualiza fila por fila (crear las nuevas, reordenar, quitar las que sobran) sin reconstruirla, para no perder el foco del teclado cada segundo.
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
        // Aviso que explica por qué las reglas podrían no estar actuando: están en pausa, o el sensor está desactivado.
        let aviso = "";
        if (estado.reglas.length && estado.pausadas) {
            aviso = "Las reglas están en pausa: no se dispara ninguna hasta que las reanudes.";
        } else if (estado.reglas.length && !estado.sensor_activo) {
            aviso = "El sensor está desactivado: las reglas solo se evalúan mientras mide. Activalo en el panel del sensor.";
        }
        nota.hidden = !aviso;
        asignarTexto(nota, aviso);
        nota.classList.toggle("estado-advertencia", Boolean(aviso));

        // Le pasa las reglas a static/js/grafico.js para que dibuje sus umbrales.
        if (window.graficoDistancia) {
            window.graficoDistancia.fijarReglas(estado.reglas, estado.pausadas);
        }
    }

    // Con la pestaña oculta se pausan las consultas; al volver, se consulta de inmediato.
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            clearTimeout(temporizador);
        } else {
            refrescar();
        }
    });

    // Publica refrescar() para que voz.js pueda forzar una actualización. Al final, se ajustan los campos y se hace la primera consulta.
    window.automatizaciones = { refrescar };

    ajustarCamposDeAccion();
    refrescar();
})();

// static/js/registro.js
// Panel «Registro de comandos»: historial de lo que escuchó Vosk, qué se hizo
// con cada orden y qué reglas se dispararon.
//
// El historial lo guarda el servidor (registro.py), así que se ve completo aunque
// se recargue la página o se abra desde otro dispositivo. Cada consulta pide solo
// lo nuevo (?desde=) y las filas se agregan arriba sin reconstruir la lista.
//
// Todo el texto se inserta con textContent: lo que transcribe el reconocedor
// nunca se interpreta como HTML.

// ┌─────────────────────────────────────────────────────────────────────────┐
// │ DE QUIÉN DEPENDE / QUIÉN LO USA                                         │
// │  - templates/index.html: contiene los elementos que se controlan acá    │
// │    (#lista-registro, #registro-filtro, #registro-contador,              │
// │    #limpiar-registro, #registro-vacio).                                 │
// │  - app.py: GET /api/registro (eventos nuevos) y DELETE /api/registro    │
// │    (limpiar). Esos datos los guarda registro.py.                        │
// │  - static/js/voz.js llama a window.registroComandos.refrescar() (se     │
// │    define al final) para ver al instante una orden recién ejecutada.    │
// └─────────────────────────────────────────────────────────────────────────┘
// Función autoejecutable: mantiene sus variables privadas.
(function () {
    // Busca en la página la lista donde se dibujan los eventos. Si no existe, el script no hace nada.
    const lista = document.getElementById("lista-registro");
    if (!lista) {
        return;
    }

    // Otros elementos del panel: mensaje de «sin actividad», selector de filtro, contador de eventos y botón «Limpiar».
    const textoVacio = document.getElementById("registro-vacio");
    const selectorFiltro = document.getElementById("registro-filtro");
    const contador = document.getElementById("registro-contador");
    const botonLimpiar = document.getElementById("limpiar-registro");

    // Tope de eventos que se muestran (igual al que guarda registro.py).
    const MAXIMO = 200;
    const MENSAJE_SIN_ACTIVIDAD =
        "Todavía no hay actividad. Activá el micrófono y dictá una orden: acá vas a ver lo que entendió Vosk.";

    // Estado del panel: eventos recibidos, último id visto, si hay una consulta en curso y el temporizador de la próxima consulta.
    let entradas = [];   // de la más vieja a la más nueva
    let ultimoId = 0;
    let consultando = false;
    let repetir = false;     // llegó un pedido mientras se consultaba: se repite al terminar
    let temporizador = null;

    // Funciones que deciden qué eventos se ven y cómo se rotulan.
    // ---------- filtro y textos ----------

    // Indica si un evento debe mostrarse según el filtro elegido (órdenes, errores, ignoradas, reglas o todo).
    function pasaFiltro(entrada) {
        switch (selectorFiltro.value) {
            case "ordenes":
                return entrada.origen === "voz" && entrada.estado === "ok";
            case "errores":
                return entrada.estado === "error";
            case "ignoradas":
                return entrada.estado === "ignorado";
            case "reglas":
                return entrada.origen === "regla";
            default:
                return true;
        }
    }

    // Rótulo de cada fila: Error, Ignorada, Regla u Orden.
    function nombreEtiqueta(entrada) {
        if (entrada.estado === "error") return "Error";
        if (entrada.estado === "ignorado") return "Ignorada";
        return entrada.origen === "regla" ? "Regla" : "Orden";
    }

    // Convierte los segundos del servidor a una hora legible (HH:MM:SS).
    function formatoHora(momento) {
        return new Date(momento * 1000).toLocaleTimeString("es-AR", { hour12: false });
    }

    // Construcción de cada fila del historial.
    // ---------- filas ----------

    // Crea el elemento <li> de un evento: hora, etiqueta, texto escuchado y resultado. Todo con textContent: lo que transcribe Vosk jamás se interpreta como HTML.
    function crearFila(entrada) {
        const fila = document.createElement("li");
        fila.className = "registro-fila";
        fila.dataset.estado = entrada.estado;
        fila.dataset.origen = entrada.origen;

        // Hora del evento (elemento <time>).
        const hora = document.createElement("time");
        hora.className = "registro-hora";
        hora.dateTime = new Date(entrada.ts * 1000).toISOString();
        hora.textContent = formatoHora(entrada.ts);

        const etiqueta = document.createElement("span");
        etiqueta.className = "registro-etiqueta";
        etiqueta.textContent = nombreEtiqueta(entrada);

        const detalle = document.createElement("div");
        detalle.className = "registro-detalle";
        const texto = document.createElement("p");
        texto.className = "registro-texto";
        // Las órdenes de voz se muestran entre comillas; las reglas, tal cual.
        texto.textContent = entrada.origen === "voz" ? `“${entrada.texto}”` : entrada.texto;
        const resultado = document.createElement("p");
        resultado.className = "registro-resultado";
        resultado.textContent = entrada.resultado;
        detalle.append(texto, resultado);

        fila.append(hora, etiqueta, detalle);
        return fila;
    }

    // Actualiza el contador («5 eventos» o «2 de 5 eventos»), el mensaje de lista vacía y el estado del botón «Limpiar».
    function actualizarResumen() {
        const visibles = entradas.filter(pasaFiltro).length;
        const total = entradas.length;
        const eventos = total === 1 ? "evento" : "eventos";
        contador.textContent = selectorFiltro.value === "todo"
            ? `${total} ${eventos}`
            : `${visibles} de ${total} ${eventos}`;

        contador.hidden = total === 0;
        textoVacio.hidden = visibles > 0;
        textoVacio.textContent = total === 0 ? MENSAJE_SIN_ACTIVIDAD : "No hay eventos para este filtro.";
        botonLimpiar.disabled = total === 0;
    }

    // Reconstruye toda la lista (solo al cambiar el filtro o al limpiar).
    // Redibuja toda la lista (solo cuando cambia el filtro o se limpia).
    function reconstruir() {
        const filas = entradas.filter(pasaFiltro).reverse().map(crearFila);
        lista.replaceChildren(...filas);
        actualizarResumen();
    }

    // Agrega arriba solo lo nuevo.
    // Agrega arriba únicamente los eventos nuevos, sin redibujar todo, y descarta filas de más.
    function agregar(nuevas) {
        for (const entrada of nuevas) {
            if (pasaFiltro(entrada)) {
                lista.prepend(crearFila(entrada));
            }
        }
        while (lista.children.length > MAXIMO) {
            lista.lastElementChild.remove();
        }
        actualizarResumen();
    }

    // Comunicación con app.py.
    // ---------- servidor ----------

    // Pide a app.py los eventos nuevos. Si ya hay una consulta en curso, anota que debe repetirse al terminar.
    async function refrescar() {
        if (consultando) {
            repetir = true;
            return;
        }
        consultando = true;
        try {
            // GET /api/registro?desde=<último id>: app.py responde con registro.desde(...). Se pide solo lo que falta.
            const respuesta = await fetch(`/api/registro?desde=${ultimoId}`, { cache: "no-store" });
            if (!respuesta.ok) {
                throw new Error("respuesta no válida");
            }
            const datos = await respuesta.json();

            // Si el servidor se reinició, sus números empiezan de nuevo.
            // Si los números del servidor son menores que los conocidos, el servidor se reinició: se empieza de cero.
            if (datos.ultimo_id < ultimoId) {
                entradas = [];
                ultimoId = 0;
                reconstruir();
                return;
            }

            // Lo que otro dispositivo limpió también se descarta acá.
            // Descarta lo que otro dispositivo ya limpió (ids menores a base_id) y agrega los eventos nuevos recibidos.
            const antes = entradas.length;
            entradas = entradas.filter((entrada) => entrada.id >= datos.base_id);
            const descartadas = entradas.length !== antes;

            const nuevas = datos.entradas.filter((entrada) => entrada.id > ultimoId);
            for (const entrada of nuevas) {
                entradas.push(entrada);
                ultimoId = Math.max(ultimoId, entrada.id);
            }
            if (entradas.length > MAXIMO) {
                entradas = entradas.slice(-MAXIMO);
            }

            // Si se descartaron eventos se redibuja todo; si solo hay nuevos, se agregan arriba.
            if (descartadas) {
                reconstruir();
            } else if (nuevas.length) {
                agregar(nuevas);
            }
        } catch (error) {
            // Se conserva lo que ya se mostraba.
        // Al terminar (con o sin error): libera la bandera y programa la próxima consulta (o repite enseguida si llegó otro pedido).
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

    // Programa la próxima consulta dentro de 1 s, salvo que la pestaña esté oculta (así no se consulta en vano).
    function programar() {
        clearTimeout(temporizador);
        if (!document.hidden) {
            temporizador = setTimeout(refrescar, 1000);
        }
    }

    // Reacciones a lo que hace el usuario.
    // ---------- eventos ----------

    // Al cambiar el filtro, se redibuja la lista.
    selectorFiltro.addEventListener("change", reconstruir);

    // Botón «Limpiar»: envía DELETE /api/registro a app.py (que llama a registro.limpiar()) y vacía el panel.
    botonLimpiar.addEventListener("click", async () => {
        try {
            await fetch("/api/registro", { method: "DELETE" });
        } catch (error) {
            return;
        }
        entradas = [];
        reconstruir();
        refrescar();
    });

    // Al ocultar la pestaña se pausan las consultas; al volver a mostrarla se consulta de inmediato.
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            clearTimeout(temporizador);
        } else {
            refrescar();
        }
    });

    // Publica refrescar() para que voz.js pueda forzar una actualización. Después de esto, el panel se dibuja vacío y hace su primera consulta.
    window.registroComandos = { refrescar };

    actualizarResumen();
    refrescar();
})();

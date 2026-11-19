// Panel de configuracion del asistente de voz.
(function () {
    "use strict";


    const $ = (id) => document.getElementById(id);

    const chipEstado = $("estado-asistente");
    const respuestaAsistente = $("respuesta-asistente");

    const radiosModo = Array.prototype.slice.call(
        document.querySelectorAll('input[name="modo-asistente"]')
    );
    const campoEspera = $("asistente-espera");
    const listaPalabras = $("lista-palabras-inicio");
    const formularioPalabra = $("formulario-palabra");
    const campoNuevaPalabra = $("nueva-palabra");
    const botonAgregar = $("agregar-palabra");
    const botonRestablecer = $("restablecer-palabras");
    const mensaje = $("asistente-mensaje");

    if (!chipEstado || !listaPalabras || !formularioPalabra) {
        return;
    }


    let estado = null;
    let huellaAjustes = "";
    let huellaPalabras = "";
    let estabaActivo = false;
    let temporizadorMensaje = null;


    function unirConO(elementos) {
        if (elementos.length <= 1) {
            return elementos.join("");
        }
        return elementos.slice(0, -1).join(", ") + " o " + elementos[elementos.length - 1];
    }

    function mostrarMensaje(texto, tipo) {
        window.clearTimeout(temporizadorMensaje);
        mensaje.textContent = texto;
        mensaje.classList.toggle("estado-correcto", tipo === "ok");
        mensaje.classList.toggle("estado-error", tipo !== "ok");
        mensaje.hidden = false;
        temporizadorMensaje = window.setTimeout(function () {
            mensaje.hidden = true;
        }, tipo === "ok" ? 4000 : 8000);
    }


    async function guardar(cambios, textoOk) {
        try {
            const respuesta = await fetch("/api/configuracion", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(cambios),
            });
            const datos = await respuesta.json().catch(function () { return {}; });
            if (!respuesta.ok) {
                throw new Error(datos.mensaje || "No se pudo guardar la configuración.");
            }
            aplicar(datos.asistente, true);
            mostrarMensaje(textoOk || datos.mensaje || "Configuración guardada.", "ok");
            return true;
        } catch (error) {
            mostrarMensaje(error.message, "error");
            if (estado) {
                aplicar(estado, true);
            }
            return false;
        }
    }

    async function cargar() {
        try {
            const respuesta = await fetch("/api/configuracion", { cache: "no-store" });
            const datos = await respuesta.json();
            aplicar(datos.asistente, true);
        } catch (error) {
            chipEstado.textContent = "No se pudo cargar el estado del asistente.";
        }
    }


    function dibujarChip(nuevo) {
        const principal = nuevo.palabras[0];
        let texto;
        let tipo;
        if (nuevo.modo !== "asistente") {
            tipo = "siempre";
            texto = "Modo: palabra de activación en cada comando";
        } else if (nuevo.activo) {
            tipo = "despierto";
            texto = nuevo.restante_s === null || nuevo.restante_s === undefined
                ? "Asistente despierto: le escucho (hasta que diga «adiós»)"
                : "Asistente despierto: le escucho (" + nuevo.restante_s + " s)";
        } else {
            tipo = "espera";
            texto = "Asistente en espera: diga «" + principal + "»";
        }
        if (chipEstado.textContent !== texto) {
            chipEstado.textContent = texto;
        }
        chipEstado.setAttribute("data-estado", tipo);
    }

    function actualizarTextosDePalabras(palabras) {
        document.documentElement.setAttribute("data-palabra-inicio", palabras[0]);

        const principales = document.querySelectorAll("[data-palabra-principal]");
        for (let i = 0; i < principales.length; i++) {
            principales[i].textContent = palabras[0];
        }
        const enumeraciones = document.querySelectorAll("[data-palabras-texto]");
        const texto = unirConO(palabras.map(function (palabra) { return "«" + palabra + "»"; }));
        for (let i = 0; i < enumeraciones.length; i++) {
            enumeraciones[i].textContent = texto;
        }
    }

    function dibujarPalabras(palabras) {
        listaPalabras.textContent = "";
        palabras.forEach(function (palabra, posicion) {
            const item = document.createElement("li");
            item.className = "palabra-etiqueta" + (posicion === 0 ? " es-principal" : "");

            const texto = document.createElement("span");
            texto.className = "palabra-texto";
            texto.textContent = palabra;
            item.appendChild(texto);

            if (posicion === 0) {
                const marca = document.createElement("span");
                marca.className = "palabra-marca";
                marca.textContent = "principal";
                item.appendChild(marca);
            } else {
                const subir = document.createElement("button");
                subir.type = "button";
                subir.className = "palabra-accion";
                subir.textContent = "Hacer principal";
                subir.setAttribute("aria-label", "Usar «" + palabra + "» como palabra principal");
                subir.addEventListener("click", function () {
                    guardar({ palabras: [palabra].concat(palabras.filter(function (_, i) { return i !== posicion; })) },
                        "«" + palabra + "» es ahora la palabra principal.");
                });
                item.appendChild(subir);
            }

            const quitar = document.createElement("button");
            quitar.type = "button";
            quitar.className = "palabra-accion palabra-quitar";
            quitar.textContent = "×";
            quitar.setAttribute("aria-label", "Quitar «" + palabra + "»");
            quitar.addEventListener("click", function () {
                if (palabras.length <= 1) {
                    mostrarMensaje("Tiene que haber al menos una palabra de activación.", "error");
                    return;
                }
                guardar({ palabras: palabras.filter(function (_, i) { return i !== posicion; }) },
                    "Se quitó «" + palabra + "».");
            });
            item.appendChild(quitar);

            listaPalabras.appendChild(item);
        });
    }

    function aplicar(nuevo, forzar, opciones) {
        if (!nuevo || !Array.isArray(nuevo.palabras)) {
            return;
        }

        // Una despedida explícita también duerme al asistente, pero ya tiene su
        // propia respuesta. Evitamos anunciar además un cierre por inactividad.
        const suprimirAvisoCierre = Boolean(opciones && opciones.suprimirAvisoCierre);
        if (!suprimirAvisoCierre && estabaActivo && !nuevo.activo && nuevo.modo === "asistente") {
            respuesta("La conversación terminó por inactividad. Diga «" + nuevo.palabras[0] + "» cuando me necesite.");
        }
        estabaActivo = Boolean(nuevo.activo);
        estado = nuevo;

        dibujarChip(nuevo);

        const huellaNueva = JSON.stringify(nuevo.palabras);
        if (huellaNueva !== huellaPalabras) {
            huellaPalabras = huellaNueva;
            actualizarTextosDePalabras(nuevo.palabras);
            document.dispatchEvent(new CustomEvent("palabras-inicio-cambiadas", { detail: nuevo.palabras }));
        }

        const huella = JSON.stringify([nuevo.modo, nuevo.espera_s, nuevo.palabras]);
        if (!forzar && huella === huellaAjustes) {
            return;
        }
        huellaAjustes = huella;

        radiosModo.forEach(function (radio) {
            radio.checked = radio.value === nuevo.modo;
        });
        if (forzar || document.activeElement !== campoEspera) {
            campoEspera.value = String(nuevo.espera_s);
        }
        dibujarPalabras(nuevo.palabras);
        if (nuevo.limites && nuevo.limites.largo_palabra) {
            campoNuevaPalabra.maxLength = nuevo.limites.largo_palabra;
        }
    }

    function respuesta(texto, opciones) {
        if (respuestaAsistente && respuestaAsistente.textContent !== texto) {
            respuestaAsistente.textContent = texto;
        }
        if (window.vozSalida) {
            window.vozSalida.hablar(texto);
        }
        if (opciones && opciones.cierra) {
            estabaActivo = false;
        }
    }


    radiosModo.forEach(function (radio) {
        radio.addEventListener("change", function () {
            if (!radio.checked) {
                return;
            }
            guardar(
                { modo: radio.value },
                radio.value === "asistente"
                    ? "Modo asistente activado: diga la palabra de activación una vez y después dé las órdenes."
                    : "Modo «palabra en cada comando» activado."
            );
        });
    });

    function guardarEspera() {
        const texto = campoEspera.value.trim();
        const valor = Number(texto);
        if (texto === "" || !isFinite(valor)) {
            mostrarMensaje("Escriba el tiempo de espera como un número de segundos.", "error");
            if (estado) {
                campoEspera.value = String(estado.espera_s);
            }
            return;
        }
        if (estado && valor === estado.espera_s) {
            return;
        }
        guardar({ espera_s: valor }, "Tiempo de espera guardado: " + (valor === 0 ? "sin límite." : valor + " s."));
    }
    campoEspera.addEventListener("change", guardarEspera);
    campoEspera.addEventListener("keydown", function (evento) {
        if (evento.key === "Enter") {
            evento.preventDefault();
            guardarEspera();
        }
    });

    formularioPalabra.addEventListener("submit", async function (evento) {
        evento.preventDefault();
        const nueva = campoNuevaPalabra.value.trim();
        if (!nueva || !estado) {
            mostrarMensaje("Escriba la palabra que quiere agregar.", "error");
            campoNuevaPalabra.focus();
            return;
        }
        botonAgregar.disabled = true;
        const guardada = await guardar({ palabras: estado.palabras.concat([nueva]) }, "Se agregó «" + nueva + "».");
        botonAgregar.disabled = false;
        if (guardada) {
            campoNuevaPalabra.value = "";
        }
        campoNuevaPalabra.focus();
    });

    botonRestablecer.addEventListener("click", function () {
        if (!estado) {
            return;
        }
        guardar({ palabras: estado.palabras_por_defecto }, "Se restablecieron las palabras de activación.");
    });


    window.asistenteVoz = {
        aplicar: function (nuevo, opciones) { aplicar(nuevo, false, opciones); },
        respuesta: respuesta,
    };

    cargar();
})();

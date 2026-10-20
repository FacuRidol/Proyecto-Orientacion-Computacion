// static/js/voz.js

const $ = (id) => document.getElementById(id);

const listaLeds = $("lista-leds");
const estadoMicrofono = $("estado-microfono");
const resultadoVoz = $("resultado-voz");

const botonActivar = $("activar-microfono");
const botonApagar = $("apagar-microfono");

const controlServo = $("control-servo");
const valorAngulo = $("valor-angulo");
const estadoServo = $("estado-servo");

const distanciaElemento = $("distancia");
const estadoSensor = $("estado-sensor");

let reconocimiento = null;
let escuchando = false;
let temporizadorReconocimiento = null;
let consultandoDistancia = false;


// ==========================================
// SOLICITUDES A FLASK
// ==========================================

async function solicitar(url, opciones = {}) {
    const respuesta = await fetch(url, opciones);

    const datos = await respuesta.json();

    if (!respuesta.ok) {
        throw new Error(datos.mensaje || "Error del servidor.");
    }

    return datos;
}

function enviarJSON(url, datos) {
    return solicitar(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(datos)
    });
}


// ==========================================
// LEDS DINAMICOS
// ==========================================

function crearTarjetaLed(numero, encendido) {
    const tarjeta = document.createElement("article");
    tarjeta.className = "tarjeta-led";

    const fila = document.createElement("div");
    fila.className = "fila-led";

    const titulo = document.createElement("strong");
    titulo.textContent = `LED ${numero}`;

    const indicador = document.createElement("span");
    indicador.className = "indicador-led";

    indicador.setAttribute("aria-hidden", "true");

    const estado = document.createElement("span");
    estado.className = "estado-led";

    const botones = document.createElement("div");
    botones.className = "botones-led";

    const botonEncender = document.createElement("button");
    botonEncender.type = "button";
    botonEncender.textContent = "Encender";

    const botonApagar = document.createElement("button");
    botonApagar.type = "button";
    botonApagar.textContent = "Apagar";
    botonApagar.className = "boton-apagar";

    botonEncender.addEventListener("click", () => {
        cambiarLed(numero, true);
    });

    botonApagar.addEventListener("click", () => {
        cambiarLed(numero, false);
    });

    fila.append(titulo, indicador);
    botones.append(botonEncender, botonApagar);

    tarjeta.append(fila, estado, botones);

    actualizarTarjetaLed(
        tarjeta,
        encendido
    );

    return tarjeta;
}

function actualizarTarjetaLed(tarjeta, encendido) {
    const indicador = tarjeta.querySelector(".indicador-led");
    const estado = tarjeta.querySelector(".estado-led");

    indicador.classList.toggle("encendido", encendido);

    estado.textContent = encendido
        ? "Encendido"
        : "Apagado";
}

function actualizarLed(numero, encendido) {
    const tarjetas = listaLeds.querySelectorAll(".tarjeta-led");

    for (const tarjeta of tarjetas) {
        const titulo = tarjeta.querySelector("strong");

        if (titulo.textContent === `LED ${numero}`) {
            actualizarTarjetaLed(tarjeta, encendido);
            return;
        }
    }
}

async function cambiarLed(numero, encender) {
    try {
        const datos = await enviarJSON(
            `/api/led/${numero}`,
            {
                accion: encender ? "encender" : "apagar"
            }
        );

        actualizarLed(numero, encender);
        resultadoVoz.textContent = datos.mensaje;

    } catch (error) {
        resultadoVoz.textContent = error.message;
    }
}


// ==========================================
// CARGAR ESTADO INICIAL
// ==========================================

async function cargarEstado() {
    try {
        const datos = await solicitar("/api/estado");

        listaLeds.replaceChildren();

        for (const [numero, encendido] of Object.entries(datos.leds)) {
            listaLeds.appendChild(
                crearTarjetaLed(
                    Number(numero),
                    encendido
                )
            );
        }

        controlServo.value = datos.servo;
        valorAngulo.textContent = `${datos.servo}°`;

        estadoServo.textContent =
            `Último ángulo solicitado: ${datos.servo}°`;

    } catch (error) {
        listaLeds.textContent =
            "No se pudo cargar el estado de los dispositivos.";

        resultadoVoz.textContent = error.message;
    }
}


// ==========================================
// SERVOMOTOR
// ==========================================

controlServo.addEventListener("input", () => {
    valorAngulo.textContent =
        `${controlServo.value}°`;
});

$("enviar-servo").addEventListener("click", async () => {
    const angulo = Number(controlServo.value);

    try {
        const datos = await enviarJSON("/api/servo", {
            angulo: angulo
        });

        estadoServo.textContent = datos.mensaje;

    } catch (error) {
        estadoServo.textContent = error.message;
    }
});


// ==========================================
// SENSOR ULTRASONICO
// ==========================================

async function actualizarDistancia() {
    if (consultandoDistancia) {
        return;
    }

    consultandoDistancia = true;

    try {
        const datos = await solicitar("/api/distancia");

        if (datos.ok && Number.isFinite(datos.distancia_cm)) {
            distanciaElemento.textContent =
                datos.distancia_cm.toFixed(1);

            estadoSensor.textContent = "Medición actualizada";
        } else {
            distanciaElemento.textContent = "--";

            estadoSensor.textContent =
                "No se obtuvo una medición válida.";
        }

    } catch (error) {
        distanciaElemento.textContent = "--";

        estadoSensor.textContent =
            "No se pudo consultar el sensor.";

    } finally {
        consultandoDistancia = false;
    }
}


// ==========================================
// RECONOCIMIENTO DE VOZ
// ==========================================

const APIReconocimiento =
    window.SpeechRecognition ||
    window.webkitSpeechRecognition;

function actualizarBotonesMicrofono() {
    botonActivar.disabled =
        escuchando || !APIReconocimiento;

    botonApagar.disabled = !escuchando;
}

function detenerMicrofono(mensaje) {
    escuchando = false;

    clearTimeout(temporizadorReconocimiento);

    actualizarBotonesMicrofono();

    estadoMicrofono.textContent = "Micrófono apagado";

    if (reconocimiento) {
        try {
            reconocimiento.stop();
        } catch (error) {
            // El reconocimiento podría estar detenido.
        }
    }

    if (mensaje) {
        resultadoVoz.textContent = mensaje;
    }
}

async function procesarComando(texto) {
    resultadoVoz.textContent = `Comando reconocido: ${texto}`;

    try {
        const datos = await enviarJSON("/api/comando", {
            comando: texto
        });

        resultadoVoz.textContent = datos.mensaje;

        // Sincronizar la interfaz después de un comando de voz.
        if (texto.toLowerCase().includes("led")) {
            const estado = await solicitar("/api/estado");

            for (const [numero, encendido] of Object.entries(estado.leds)) {
                actualizarLed(Number(numero), encendido);
            }
        }

        if (texto.toLowerCase().includes("servo")) {
            const estado = await solicitar("/api/estado");

            controlServo.value = estado.servo;
            valorAngulo.textContent = `${estado.servo}°`;

            estadoServo.textContent =
                `Último ángulo solicitado: ${estado.servo}°`;
        }

        if (
            texto.toLowerCase().includes("distancia") ||
            texto.toLowerCase().includes("cerca") ||
            texto.toLowerCase().includes("lejos")
        ) {
            await actualizarDistancia();
        }

    } catch (error) {
        resultadoVoz.textContent = error.message;
    }
}

function iniciarReconocimiento() {
    if (!APIReconocimiento) {
        resultadoVoz.textContent =
            "Este navegador no admite reconocimiento de voz.";

        return;
    }

    reconocimiento = new APIReconocimiento();

    reconocimiento.lang = "es-AR";
    reconocimiento.continuous = true;
    reconocimiento.interimResults = false;
    reconocimiento.maxAlternatives = 1;

    reconocimiento.onstart = () => {
        estadoMicrofono.textContent = "Micrófono encendido";
    };

    reconocimiento.onresult = (evento) => {
        for (
            let i = evento.resultIndex;
            i < evento.results.length;
            i++
        ) {
            if (!evento.results[i].isFinal) {
                continue;
            }

            const texto =
                evento.results[i][0].transcript.trim();

            if (texto) {
                procesarComando(texto);
            }
        }
    };

    reconocimiento.onerror = (evento) => {
        if (
            evento.error === "not-allowed" ||
            evento.error === "service-not-allowed" ||
            evento.error === "audio-capture"
        ) {
            detenerMicrofono(
                "No se pudo acceder al micrófono. " +
                "Comprobá los permisos y el dispositivo."
            );

            return;
        }

        if (evento.error === "network") {
            detenerMicrofono(
                "Falló el servicio de reconocimiento de voz. " +
                "Comprobá la conexión y la compatibilidad del navegador."
            );
        }
    };

    reconocimiento.onend = () => {
        if (!escuchando) {
            estadoMicrofono.textContent = "Micrófono apagado";
            return;
        }

        // Algunos navegadores finalizan cada sesión de escucha.
        temporizadorReconocimiento = setTimeout(() => {
            if (!escuchando) {
                return;
            }

            try {
                reconocimiento.start();
            } catch (error) {
                detenerMicrofono(
                    "No se pudo reiniciar el reconocimiento."
                );
            }
        }, 300);
    };
}

botonActivar.addEventListener("click", () => {
    if (!APIReconocimiento || escuchando) {
        return;
    }

    if (!reconocimiento) {
        iniciarReconocimiento();
    }

    escuchando = true;

    actualizarBotonesMicrofono();

    estadoMicrofono.textContent =
        "Solicitando acceso al micrófono...";

    try {
        reconocimiento.start();
    } catch (error) {
        detenerMicrofono(
            "No se pudo iniciar el reconocimiento."
        );
    }
});

botonApagar.addEventListener("click", () => {
    detenerMicrofono("Reconocimiento detenido.");
});


// ==========================================
// INICIALIZACION
// ==========================================

actualizarBotonesMicrofono();
cargarEstado();
actualizarDistancia();

// Consultar la distancia una vez por segundo.
setInterval(actualizarDistancia, 1000);
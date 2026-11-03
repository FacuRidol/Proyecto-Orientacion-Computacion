// static/js/voz.js
// Captura de audio compatible con Firefox y Chromium; Vosk reconoce localmente.

const $ = (id) => document.getElementById(id);

const listaLeds = $("lista-leds");
const estadoMicrofono = $("estado-microfono");
const estadoReconocimiento = $("estado-reconocimiento");
const resultadoVoz = $("resultado-voz");
const textoVosk = $("texto-vosk");

const botonActivar = $("activar-microfono");
const botonApagar = $("apagar-microfono");

const controlServo = $("control-servo");
const valorAngulo = $("valor-angulo");
const estadoServo = $("estado-servo");

// Indicador gráfico del servo (dial con aguja)
const indicadorServo = $("indicador-servo");
const agujaServo = $("aguja-servo");
const progresoServo = $("dial-progreso");
const anguloActual = $("angulo-actual");

const distanciaElemento = $("distancia");
const estadoSensor = $("estado-sensor");
const botonSensor = $("alternar-sensor");

let escuchando = false;
let iniciandoMicrofono = false;
let consultandoDistancia = false;
let sensorActivo = false;

let flujoMicrofono = null;
let contextoAudio = null;
let nodoMicrofono = null;
let procesadorAudio = null;
let gananciaSilencio = null;
let colaAudio = Promise.resolve();

// Se envían fragmentos de medio segundo de PCM mono, 16-bit, 16 kHz.
const FRECUENCIA_VOSK = 16000;
const DURACION_BLOQUE = 0.5;
let fragmentosAudio = [];
let muestrasDisponibles = 0;
let offsetPrimerFragmento = 0;


// ==========================================
// SOLICITUDES A FLASK
// ==========================================

async function solicitar(url, opciones = {}) {
    const respuesta = await fetch(url, opciones);
    let datos;

    try {
        datos = await respuesta.json();
    } catch (error) {
        throw new Error("El servidor devolvió una respuesta no válida.");
    }

    if (!respuesta.ok) {
        throw new Error(datos.mensaje || "Error del servidor.");
    }

    return datos;
}

function enviarJSON(url, datos) {
    return solicitar(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(datos),
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

    // Un solo botón: muestra la acción inversa al estado actual.
    const botonToggle = document.createElement("button");
    botonToggle.type = "button";
    botonToggle.className = "boton-led-toggle";
    botonToggle.addEventListener("click", () => alternarLed(numero));

    fila.append(titulo, indicador);
    botones.append(botonToggle);
    tarjeta.append(fila, estado, botones);
    actualizarTarjetaLed(tarjeta, encendido);

    return tarjeta;
}

function actualizarTarjetaLed(tarjeta, encendido) {
    const indicador = tarjeta.querySelector(".indicador-led");
    const estado = tarjeta.querySelector(".estado-led");
    const boton = tarjeta.querySelector(".boton-led-toggle");
    const titulo = tarjeta.querySelector("strong").textContent;
    const numero = titulo.replace("LED ", "");

    indicador.classList.toggle("encendido", Boolean(encendido));
    estado.textContent = encendido ? "Encendido" : "Apagado";
    boton.textContent = encendido ? "Apagar" : "Encender";
    boton.classList.toggle("boton-apagar", Boolean(encendido));
    boton.classList.toggle("boton-encender", !encendido);
    boton.setAttribute("aria-pressed", String(Boolean(encendido)));
    boton.setAttribute(
        "aria-label",
        `${encendido ? "Apagar" : "Encender"} ${titulo}`
    );
}

function actualizarLed(numero, encendido) {
    const tarjetas = listaLeds.querySelectorAll(".tarjeta-led");
    for (const tarjeta of tarjetas) {
        if (tarjeta.querySelector("strong").textContent === `LED ${numero}`) {
            actualizarTarjetaLed(tarjeta, encendido);
            return;
        }
    }
}

async function alternarLed(numero) {
    try {
        // El servidor lee el GPIO y alterna de forma atómica. Así no depende
        // del estado posiblemente desactualizado que tenga esta pestaña.
        const datos = await enviarJSON(`/api/led/${numero}/alternar`, {});
        actualizarLed(numero, datos.encendido);
        resultadoVoz.textContent = datos.mensaje;
        await sincronizarEstado();
    } catch (error) {
        resultadoVoz.textContent = error.message;
        await sincronizarEstado();
    }
}


// Botones «Encender todos» y «Apagar todos» (el servidor cambia los cuatro
// LED de una sola vez). Si se quitan del HTML, el resto sigue funcionando.
async function controlarTodosLeds(encender) {
    try {
        const datos = await enviarJSON("/api/leds/todos", {
            accion: encender ? "encender" : "apagar",
        });
        aplicarEstadoDispositivos({ leds: datos.leds });
        resultadoVoz.textContent = datos.mensaje;
    } catch (error) {
        resultadoVoz.textContent = error.message;
    }
    await sincronizarEstado();
}

$("encender-todos")?.addEventListener("click", () => controlarTodosLeds(true));
$("apagar-todos")?.addEventListener("click", () => controlarTodosLeds(false));


// ==========================================
// CARGAR ESTADO INICIAL
// ==========================================

function aplicarEstadoDispositivos(datos, crearTarjetas = false) {
    if (!datos || typeof datos !== "object") {
        return;
    }

    if (datos.leds && typeof datos.leds === "object") {
        for (const [numeroTexto, encendido] of Object.entries(datos.leds)) {
            const numero = Number(numeroTexto);
            if (!Number.isInteger(numero)) continue;

            let tarjeta = [...listaLeds.querySelectorAll(".tarjeta-led")].find(
                (elemento) => elemento.querySelector("strong")?.textContent === `LED ${numero}`
            );

            if (!tarjeta && crearTarjetas) {
                tarjeta = crearTarjetaLed(numero, Boolean(encendido));
                listaLeds.appendChild(tarjeta);
            } else if (!tarjeta) {
                // Si se añadió un LED en la configuración, también aparece
                // en las pestañas que ya estaban abiertas.
                tarjeta = crearTarjetaLed(numero, Boolean(encendido));
                listaLeds.appendChild(tarjeta);
            }

            actualizarTarjetaLed(tarjeta, Boolean(encendido));
        }
    }

    if (Number.isFinite(Number(datos.servo))) {
        const angulo = Number(datos.servo);
        // No mover el deslizador (ni su número) debajo del puntero mientras
        // el usuario lo edita. El dial, en cambio, siempre refleja al servo.
        if (document.activeElement !== controlServo) {
            controlServo.value = angulo;
            valorAngulo.textContent = `${angulo}°`;
        }
        actualizarIndicadorServo(angulo);
        estadoServo.textContent = `Última posición solicitada: ${angulo}°`;
    }

    if (typeof datos.sensor_activo === "boolean") {
        actualizarEstadoSensor(datos.sensor_activo);
    }
}

let sincronizandoEstado = false;

async function sincronizarEstado() {
    if (sincronizandoEstado) return;
    sincronizandoEstado = true;

    try {
        // Evitar respuestas cacheadas: cada pestaña consulta al mismo Flask.
        const datos = await solicitar("/api/estado", { cache: "no-store" });
        aplicarEstadoDispositivos(datos, true);
    } catch (error) {
        // No sobreescribir los controles si una consulta temporal falla.
        console.warn("No se pudo sincronizar el estado de los dispositivos:", error);
    } finally {
        sincronizandoEstado = false;
    }
}

async function cargarEstado() {
    listaLeds.replaceChildren();
    await sincronizarEstado();
    if (!listaLeds.querySelector(".tarjeta-led")) {
        listaLeds.textContent = "No se pudo cargar el estado de los dispositivos.";
    }
    if (sensorActivo) {
        await actualizarDistancia();
    }
}


// ==========================================
// SERVOMOTOR
// ==========================================

// Mueve la aguja del dial (el cuerno del servo) y rellena el arco de progreso.
// El dial va de 0° (izquierda) a 180° (derecha). Las transiciones suaves las
// define estilos.css, así que acá solo se cambian los valores.
function actualizarIndicadorServo(angulo) {
    const valor = Number(angulo);
    if (!Number.isFinite(valor)) {
        return;
    }

    const limitado = Math.max(0, Math.min(180, valor));
    agujaServo.style.transform = `rotate(${limitado}deg)`;
    // El arco mide 180 unidades (pathLength), una por grado.
    progresoServo.style.strokeDashoffset = String(180 - limitado);
    anguloActual.textContent = `${limitado}°`;
    indicadorServo.setAttribute("aria-label", `Posición actual del servo: ${limitado} grados`);
}

controlServo.addEventListener("input", () => {
    valorAngulo.textContent = `${controlServo.value}°`;
});

$("enviar-servo").addEventListener("click", async () => {
    const angulo = Number(controlServo.value);
    try {
        const datos = await enviarJSON("/api/servo", { angulo });
        valorAngulo.textContent = `${angulo}°`;
        actualizarIndicadorServo(angulo);
        estadoServo.textContent = datos.mensaje;
    } catch (error) {
        estadoServo.textContent = error.message;
    }
});


// ==========================================
// SENSOR ULTRASONICO
// ==========================================

function actualizarEstadoSensor(activo) {
    const nuevoEstado = Boolean(activo);
    const cambio = nuevoEstado !== sensorActivo;
    sensorActivo = nuevoEstado;

    botonSensor.textContent = sensorActivo ? "Desactivar medición" : "Activar medición";
    botonSensor.classList.toggle("boton-apagar", sensorActivo);

    if (!sensorActivo) {
        distanciaElemento.textContent = "--";
        if (cambio) estadoSensor.textContent = "Medición desactivada.";
    } else if (cambio) {
        estadoSensor.textContent = "Medición activa; buscando distancia...";
    }
}

async function cambiarEstadoSensor(activo, desdeVoz = false) {
    try {
        const datos = await enviarJSON("/api/sensor", {
            accion: activo ? "activar" : "desactivar",
        });
        actualizarEstadoSensor(datos.sensor_activo);
        resultadoVoz.textContent = datos.mensaje;
        if (sensorActivo) {
            await actualizarDistancia();
        }
    } catch (error) {
        const destino = desdeVoz ? resultadoVoz : estadoSensor;
        destino.textContent = error.message;
    }
}

botonSensor.addEventListener("click", () => {
    cambiarEstadoSensor(!sensorActivo);
});

async function actualizarDistancia() {
    if (!sensorActivo || consultandoDistancia) {
        return;
    }

    consultandoDistancia = true;
    try {
        const datos = await solicitar("/api/distancia");
        if (!sensorActivo) {
            return;
        }
        if (datos.sensor_activo === false) {
            actualizarEstadoSensor(false);
            return;
        }

        if (datos.ok && Number.isFinite(datos.distancia_cm)) {
            distanciaElemento.textContent = datos.distancia_cm.toFixed(1);
            estadoSensor.textContent = "Medición en vivo activa.";
        } else {
            distanciaElemento.textContent = "--";
            estadoSensor.textContent = datos.mensaje || "No se obtuvo una medición válida.";
        }
    } catch (error) {
        distanciaElemento.textContent = "--";
        estadoSensor.textContent = "No se pudo consultar el sensor.";
    } finally {
        consultandoDistancia = false;
    }
}


// ==========================================
// ESTADO DEL RECONOCIMIENTO OFFLINE
// ==========================================

async function comprobarReconocimientoOffline() {
    try {
        const datos = await solicitar("/api/voz/estado");
        estadoReconocimiento.textContent = datos.mensaje;
        estadoReconocimiento.classList.toggle("estado-correcto", datos.listo);
        estadoReconocimiento.classList.toggle("estado-advertencia", !datos.listo);
    } catch (error) {
        estadoReconocimiento.textContent = "No se pudo comprobar el servicio de voz.";
        estadoReconocimiento.classList.add("estado-advertencia");
    }
}


// ==========================================
// AUDIO: COLA, RESAMPLEO Y PCM 16-BIT
// ==========================================

function reiniciarBufferAudio() {
    fragmentosAudio = [];
    muestrasDisponibles = 0;
    offsetPrimerFragmento = 0;
}

function extraerMuestras(cantidad) {
    const salida = new Float32Array(cantidad);
    let escritas = 0;

    while (escritas < cantidad && fragmentosAudio.length > 0) {
        const actual = fragmentosAudio[0];
        const restantes = actual.length - offsetPrimerFragmento;
        const copiar = Math.min(restantes, cantidad - escritas);

        salida.set(
            actual.subarray(offsetPrimerFragmento, offsetPrimerFragmento + copiar),
            escritas,
        );

        escritas += copiar;
        offsetPrimerFragmento += copiar;

        if (offsetPrimerFragmento >= actual.length) {
            fragmentosAudio.shift();
            offsetPrimerFragmento = 0;
        }
    }

    muestrasDisponibles -= escritas;
    return salida.subarray(0, escritas);
}

function convertirPCM16k(muestras, frecuenciaOrigen) {
    const longitudSalida = Math.floor(muestras.length * FRECUENCIA_VOSK / frecuenciaOrigen);
    const buffer = new ArrayBuffer(longitudSalida * 2);
    const vista = new DataView(buffer);
    const proporcion = frecuenciaOrigen / FRECUENCIA_VOSK;

    for (let i = 0; i < longitudSalida; i++) {
        const posicion = i * proporcion;
        const indice = Math.floor(posicion);
        const fraccion = posicion - indice;
        const muestraA = muestras[indice] || 0;
        const muestraB = muestras[Math.min(indice + 1, muestras.length - 1)] || 0;
        const muestra = Math.max(-1, Math.min(1, muestraA + (muestraB - muestraA) * fraccion));
        const entero = muestra < 0 ? muestra * 32768 : muestra * 32767;
        vista.setInt16(i * 2, Math.round(entero), true);
    }

    return buffer;
}

function procesarCapturaAudio(evento) {
    if (!escuchando || !contextoAudio) {
        return;
    }

    const entrada = evento.inputBuffer.getChannelData(0);
    fragmentosAudio.push(new Float32Array(entrada));
    muestrasDisponibles += entrada.length;

    const muestrasPorBloque = Math.floor(contextoAudio.sampleRate * DURACION_BLOQUE);
    while (muestrasDisponibles >= muestrasPorBloque) {
        const bloque = extraerMuestras(muestrasPorBloque);
        const pcm = convertirPCM16k(bloque, contextoAudio.sampleRate);

        // Se serializan los POST para que Vosk reciba los bloques en orden.
        colaAudio = colaAudio
            .then(() => enviarBloqueAudio(pcm))
            .catch((error) => {
                if (escuchando) {
                    resultadoVoz.textContent = error.message;
                }
            });
    }
}

async function enviarBloqueAudio(pcm) {
    if (!escuchando) {
        return;
    }

    const datos = await solicitar("/api/voz/audio", {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: pcm,
    });

    // Mostrar el resultado parcial mientras el usuario sigue hablando.
    // Los resultados parciales son solo informativos: nunca ejecutan comandos.
    if (textoVosk && datos.parcial) {
        textoVosk.textContent = datos.parcial;
    }

    // Solo el resultado final se envía al intérprete de comandos.
    if (datos.final && datos.texto) {
        if (textoVosk) {
            textoVosk.textContent = datos.texto;
        }
        await procesarComando(datos.texto);
    }
}


// ==========================================
// ENCENDER Y APAGAR EL MICROFONO
// ==========================================

function actualizarBotonesMicrofono() {
    botonActivar.disabled = escuchando || iniciandoMicrofono;
    botonApagar.disabled = !escuchando;
}

async function iniciarMicrofono() {
    if (escuchando || iniciandoMicrofono) {
        return;
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        resultadoVoz.textContent = "El navegador no permite acceder al micrófono. Abrí la página mediante HTTPS y revisá los permisos.";
        return;
    }

    iniciandoMicrofono = true;
    actualizarBotonesMicrofono();
    estadoMicrofono.textContent = "Solicitando acceso al micrófono...";

    try {
        flujoMicrofono = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            },
        });

        contextoAudio = new (window.AudioContext || window.webkitAudioContext)();
        await contextoAudio.resume();

        // Carga Vosk en el servidor y crea un reconocedor nuevo para esta sesión.
        const datosInicio = await enviarJSON("/api/voz/iniciar", {});
        resultadoVoz.textContent = datosInicio.mensaje;
        if (textoVosk) {
            textoVosk.textContent = "Micrófono activo; esperando voz...";
        }

        reiniciarBufferAudio();
        colaAudio = Promise.resolve();
        nodoMicrofono = contextoAudio.createMediaStreamSource(flujoMicrofono);
        procesadorAudio = contextoAudio.createScriptProcessor(4096, 1, 1);
        gananciaSilencio = contextoAudio.createGain();
        gananciaSilencio.gain.value = 0;

        procesadorAudio.onaudioprocess = procesarCapturaAudio;
        nodoMicrofono.connect(procesadorAudio);
        procesadorAudio.connect(gananciaSilencio);
        gananciaSilencio.connect(contextoAudio.destination);

        escuchando = true;
        estadoMicrofono.textContent = "Micrófono encendido · Reconocimiento offline activo";
        resultadoVoz.textContent = "Te escucho. Decí un comando.";
    } catch (error) {
        resultadoVoz.textContent = error.message || "No se pudo iniciar el reconocimiento de voz.";
        await liberarAudioLocal();
        try {
            await enviarJSON("/api/voz/detener", {});
        } catch (errorDetencion) {
            // Es posible que la sesión del servidor todavía no se haya iniciado.
        }
    } finally {
        iniciandoMicrofono = false;
        actualizarBotonesMicrofono();
        if (!escuchando) {
            estadoMicrofono.textContent = "Micrófono apagado";
        }
    }
}

async function liberarAudioLocal() {
    if (procesadorAudio) {
        procesadorAudio.onaudioprocess = null;
        try { procesadorAudio.disconnect(); } catch (error) { /* Ya desconectado. */ }
    }
    if (nodoMicrofono) {
        try { nodoMicrofono.disconnect(); } catch (error) { /* Ya desconectado. */ }
    }
    if (gananciaSilencio) {
        try { gananciaSilencio.disconnect(); } catch (error) { /* Ya desconectado. */ }
    }
    if (flujoMicrofono) {
        flujoMicrofono.getTracks().forEach((pista) => pista.stop());
    }
    if (contextoAudio && contextoAudio.state !== "closed") {
        try { await contextoAudio.close(); } catch (error) { /* Contexto cerrado. */ }
    }

    flujoMicrofono = null;
    contextoAudio = null;
    nodoMicrofono = null;
    procesadorAudio = null;
    gananciaSilencio = null;
    reiniciarBufferAudio();
}

async function detenerMicrofono(mensaje) {
    escuchando = false;
    actualizarBotonesMicrofono();
    estadoMicrofono.textContent = "Micrófono apagado";

    await liberarAudioLocal();

    // Espera los últimos fragmentos ya encolados antes de cerrar la sesión de Vosk.
    try {
        await colaAudio;
    } catch (error) {
        // Los errores de audio ya se informan en la interfaz.
    }
    try {
        await enviarJSON("/api/voz/detener", {});
    } catch (error) {
        // Si Flask se reinició, no hay nada más que cerrar.
    }

    if (mensaje) {
        resultadoVoz.textContent = mensaje;
    }
}

botonActivar.addEventListener("click", iniciarMicrofono);
botonApagar.addEventListener("click", () => detenerMicrofono("Reconocimiento detenido."));


// ==========================================
// PROCESAR COMANDO RECONOCIDO
// ==========================================

async function procesarComando(texto) {
    resultadoVoz.textContent = `Comando reconocido: ${texto}`;

    try {
        const datos = await enviarJSON("/api/comando", { comando: texto });
        resultadoVoz.textContent = datos.mensaje;

        if (Number.isInteger(datos.led) && typeof datos.encendido === "boolean") {
            actualizarLed(datos.led, datos.encendido);
        } else if (texto.toLowerCase().includes("led")) {
            const estado = await solicitar("/api/estado");
            for (const [numero, encendido] of Object.entries(estado.leds)) {
                actualizarLed(Number(numero), encendido);
            }
        }

        // «Todas las leds» y «apagar todo» devuelven el estado de todos los LED.
        if (datos.leds && typeof datos.leds === "object") {
            aplicarEstadoDispositivos({ leds: datos.leds });
        }

        // «Estado» devuelve el estado completo de los dispositivos.
        if (datos.estado && typeof datos.estado === "object") {
            aplicarEstadoDispositivos(datos.estado);
        }

        if (Number.isInteger(datos.angulo)) {
            controlServo.value = datos.angulo;
            valorAngulo.textContent = `${datos.angulo}°`;
            actualizarIndicadorServo(datos.angulo);
            estadoServo.textContent = `Último ángulo solicitado: ${datos.angulo}°`;
        }

        if (typeof datos.sensor_activo === "boolean") {
            actualizarEstadoSensor(datos.sensor_activo);
            if (sensorActivo) {
                await actualizarDistancia();
            }
        } else if (/distancia|cerca|lejos|medir|medime/i.test(texto)) {
            await actualizarDistancia();
        }

        // Órdenes que cambian la propia página en lugar del hardware: el
        // servidor solo las reconoce y es esta página la que las ejecuta.
        if (datos.tema && window.temaInterfaz) {
            const temaNuevo = datos.tema === "alternar"
                ? window.temaInterfaz.alternar()
                : window.temaInterfaz.aplicar(datos.tema);
            if (temaNuevo) {
                resultadoVoz.textContent = `Tema ${temaNuevo} activado.`;
            }
        }

        if (datos.ayuda && window.ayudaComandos) {
            if (datos.ayuda === "cerrar") {
                window.ayudaComandos.cerrar();
            } else {
                window.ayudaComandos.abrir(datos.ayuda);
            }
        }
    } catch (error) {
        // Mostrar qué texto devolvió Vosk para poder distinguir entre
        // un error de reconocimiento y un comando que no coincide con las reglas.
        resultadoVoz.textContent = `Escuché: “${texto}”. ${error.message}`;
        if (/sensor|distancia|medicion|ultrasonico/i.test(texto)) {
            // Mantener el estado del control alineado con el hardware.
            try {
                const estado = await solicitar("/api/estado");
                actualizarEstadoSensor(Boolean(estado.sensor_activo));
            } catch (errorEstado) {
                // Se conserva el último estado visible.
            }
        }
    }
}


// ==========================================
// INICIALIZACION
// ==========================================

actualizarBotonesMicrofono();
cargarEstado();
comprobarReconocimientoOffline();

// Sincronización compartida: cada pestaña/navegador consulta el estado
// central de Flask. Una acción hecha en cualquier otra pestaña aparece aquí.
setInterval(() => {
    sincronizarEstado();
    if (sensorActivo) {
        actualizarDistancia();
    }
}, 1000);

document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
        sincronizarEstado();
        if (sensorActivo) actualizarDistancia();
    }
});

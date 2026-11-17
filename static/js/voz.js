// static/js/voz.js
// Captura de audio compatible con Firefox y Chromium; Vosk reconoce localmente.

// ┌─────────────────────────────────────────────────────────────────────────┐
// │ static/js/voz.js: EL SCRIPT PRINCIPAL DE LA PÁGINA                      │
// │                                                                         │
// │ QUÉ HACE                                                                │
// │  1. Dibuja y actualiza las tarjetas de los LED, con su nombre propio    │
// │     (lápiz para renombrar) y los botones de encender/apagar.            │
// │  2. Captura el micrófono, envía el audio a app.py y muestra lo que      │
// │     entiende Vosk.                                                      │
// │  3. Envía cada frase reconocida a app.py (POST /api/comando) y muestra  │
// │     el resultado en pantalla.                                           │
// │  4. Controla el servo (dial), el sensor ultrasónico y la sincronización │
// │     del estado entre pestañas (consulta /api/estado cada segundo).      │
// │                                                                         │
// │ DE QUIÉN DEPENDE                                                        │
// │  - templates/index.html: aporta todos los elementos con id que se       │
// │    buscan abajo (lista-leds, activar-microfono, control-servo...).      │
// │  - app.py: todas las rutas /api/... (estado, led, leds/todos, servo,    │
// │    sensor, distancia, voz/*, comando, led/<n>/nombre).                  │
// │  - Scripts que se cargan ANTES y publican funciones en «window»:        │
// │      tema.js -> window.temaInterfaz       ayuda.js -> window.ayudaComandos│
// │      registro.js -> window.registroComandos                             │
// │      automatizaciones.js -> window.automatizaciones                     │
// │    (voz.js los usa con «?.», así que no falla si alguno falta).         │
// │  - static/css/estilos.css: las clases que se asignan acá le dan aspecto.│
// └─────────────────────────────────────────────────────────────────────────┘
// Atajo: $("id") busca un elemento de la página por su id.
const $ = (id) => document.getElementById(id);

// Referencias a los elementos de la página que este script usa (todos están en templates/index.html): contenedor de LED, estado del micrófono, resultado de la orden, texto en vivo de Vosk, botones del micrófono...
const listaLeds = $("lista-leds");
const estadoMicrofono = $("estado-microfono");
const estadoReconocimiento = $("estado-reconocimiento");
const resultadoVoz = $("resultado-voz");
const textoVosk = $("texto-vosk");

const botonActivar = $("activar-microfono");
const botonApagar = $("apagar-microfono");

// Elementos del servo: control deslizante, valor, dial dibujado (aguja y arco de progreso) y ángulo actual.
const controlServo = $("control-servo");
const valorAngulo = $("valor-angulo");
const estadoServo = $("estado-servo");

// Indicador gráfico del servo (dial con aguja)
const indicadorServo = $("indicador-servo");
const agujaServo = $("aguja-servo");
const progresoServo = $("dial-progreso");
const anguloActual = $("angulo-actual");

// Elementos del sensor: valor de distancia, texto de estado y botón de activar/desactivar.
const distanciaElemento = $("distancia");
const estadoSensor = $("estado-sensor");
const botonSensor = $("alternar-sensor");

// Estado del micrófono y del sensor: si se está escuchando, si el micrófono se está iniciando, si hay una consulta de distancia en curso y si el sensor está activo.
let escuchando = false;
let iniciandoMicrofono = false;
let consultandoDistancia = false;
let sensorActivo = false;

// Piezas de la captura de audio del navegador (Web Audio): flujo del micrófono, contexto de audio, nodos de procesamiento y una cola para enviar el audio en orden.
let flujoMicrofono = null;
let contextoAudio = null;
let nodoMicrofono = null;
let procesadorAudio = null;
let gananciaSilencio = null;

// Cola acotada: una solicitud en curso y hasta tres bloques esperando.
// Así el navegador no acumula promesas indefinidamente si Flask/Vosk se atrasan.
let colaBloquesAudio = [];
let procesandoColaAudio = false;
let promesaDrenajeAudio = Promise.resolve();
let audioDiscontinuoPendiente = false;
const MAX_BLOQUES_PENDIENTES = 3;
const metricasAudio = {
    solicitudes: 0,
    bloquesDescartados: 0,
    ultimaLatenciaMs: 0,
    ultimaEsperaServidorMs: 0,
    ultimoProcesamientoMs: 0,
    ultimaEsperaColaMs: 0,
};

// Se envían fragmentos de medio segundo de PCM mono, 16-bit, 16 kHz.
// Vosk necesita audio a 16.000 muestras por segundo (igual que reconocimiento_voz.py). Se envían bloques de 0,5 segundos.
const FRECUENCIA_VOSK = 16000;
const DURACION_BLOQUE = 0.5;
// Memoria temporal donde se acumulan los trocitos de audio hasta completar un bloque de 0,5 s.
let fragmentosAudio = [];
let muestrasDisponibles = 0;
let offsetPrimerFragmento = 0;


// ==========================================
// SOLICITUDES A FLASK
// ==========================================

// FUNCIÓN BASE DE COMUNICACIÓN con app.py: hace la petición (fetch), convierte la respuesta a objeto y, si el servidor respondió con error, lanza una excepción con el mensaje que mandó app.py.
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

// Atajo para enviar datos como JSON (por defecto con POST; el renombrado de LED usa PUT).
function enviarJSON(url, datos, metodo = "POST") {
    return solicitar(url, {
        method: metodo,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(datos),
    });
}


// ==========================================
// LEDS DINAMICOS
// ==========================================

// Nombre y estado de cada LED según el servidor: {numero: {nombre, personalizado}}.
// Llega en /api/estado y se renueva cada segundo, así que un cambio de nombre
// hecho en otra pestaña (o en otro navegador) también aparece acá.
// Nombre y estado de cada LED según el servidor: {numero: {nombre, personalizado}}. Llega en /api/estado (que arma app.py con nombres_leds.py) y se renueva cada segundo.
let nombresLeds = {};
// Huellas (texto JSON) de los últimos nombres aplicados: sirven para no tocar la página si nada cambió.
let firmaNombres = "";
let firmaAyudaLeds = "";

// Lista de la ayuda de comandos donde se escriben los nombres actuales de los LED (el contenedor lo define index.html).
const listaAyudaLeds = $("ayuda-leds-actuales");
// Palabra de activación principal («comando», «robot»...). Ya NO es una constante: la persona puede cambiar
// las palabras desde el panel «Asistente de voz» (asistente.js las deja en <html data-palabra-inicio>), así que
// se lee en el momento de usarla.
function palabraInicio() {
    return document.documentElement.getAttribute("data-palabra-inicio") || "comando";
}
// Largo máximo del nombre de un LED (igual que LARGO_MAXIMO en nombres_leds.py).
const LARGO_MAXIMO_NOMBRE = 24;

// Dibujo (SVG) del lápiz del botón «Cambiar nombre».
const ICONO_LAPIZ =
    '<svg class="icono" viewBox="0 0 24 24" aria-hidden="true"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>';

// Devuelve el nombre y el estado «propio o de fábrica» de un LED (o «LED n» si todavía no llegaron los datos).
function infoLed(numero) {
    return nombresLeds[numero] || { nombre: `LED ${numero}`, personalizado: false };
}

// Las tarjetas se buscan por su número (data-led), no por el texto del título:
// el título ahora es el nombre que eligió la persona.
// Encuentra la tarjeta de un LED por su número (atributo data-led), no por el texto del título, porque el título ahora es el nombre elegido.
function buscarTarjeta(numero) {
    return listaLeds.querySelector(`.tarjeta-led[data-led="${Number(numero)}"]`);
}

// Construye la tarjeta de un LED: título con lápiz, indicador luminoso, estado, formulario de nombre (oculto), cartel «Por voz: …» y botón Encender/Apagar. Se crea una sola vez; después solo se actualiza.
function crearTarjetaLed(numero, encendido) {
    // Elemento principal; data-led guarda el número del LED para poder encontrarla después.
    const tarjeta = document.createElement("article");
    tarjeta.className = "tarjeta-led";
    tarjeta.dataset.led = String(numero);

    // Fila superior: bloque con el nombre y el lápiz, más el indicador luminoso.
    const fila = document.createElement("div");
    fila.className = "fila-led";

    const bloqueTitulo = document.createElement("div");
    bloqueTitulo.className = "led-titulo";

    const titulo = document.createElement("strong");
    titulo.className = "nombre-led";

    // Botón del lápiz: abre o cierra el formulario para cambiar el nombre.
    const botonNombre = document.createElement("button");
    botonNombre.type = "button";
    botonNombre.className = "boton-renombrar";
    botonNombre.innerHTML = ICONO_LAPIZ;
    botonNombre.setAttribute("aria-expanded", "false");
    botonNombre.addEventListener("click", () => {
        if (tarjeta.dataset.editando === "true") {
            cerrarEdicionNombre(tarjeta);
        } else {
            abrirEdicionNombre(tarjeta);
        }
    });

    bloqueTitulo.append(titulo, botonNombre);

    // Indicador luminoso (se ilumina con la clase «encendido» definida en estilos.css) y texto del estado.
    const indicador = document.createElement("span");
    indicador.className = "indicador-led";
    indicador.setAttribute("aria-hidden", "true");

    const estado = document.createElement("span");
    estado.className = "estado-led";

    // Cómo se nombra este LED por voz (se completa en aplicarNombreTarjeta).
    // Cartel con cómo se nombra este LED por voz («Por voz: «comando encender cocina»»).
    const vozLed = document.createElement("p");
    vozLed.className = "voz-led";

    const botones = document.createElement("div");
    botones.className = "botones-led";

    // Un solo botón: muestra la acción inversa al estado actual.
    // Botón único: muestra la acción contraria al estado actual. Al hacer clic llama a alternarLed().
    const botonToggle = document.createElement("button");
    botonToggle.type = "button";
    botonToggle.className = "boton-led-toggle";
    botonToggle.addEventListener("click", () => alternarLed(numero));

    fila.append(bloqueTitulo, indicador);
    botones.append(botonToggle);
    // Arma la tarjeta con todas sus partes y aplica el nombre y el estado iniciales.
    tarjeta.append(fila, estado, crearFormularioNombre(tarjeta, numero), vozLed, botones);
    aplicarNombreTarjeta(tarjeta, infoLed(numero));
    actualizarTarjetaLed(tarjeta, encendido);

    return tarjeta;
}

// Refleja en una tarjeta si el LED está encendido o apagado: indicador, texto, texto y colores del botón y su etiqueta de accesibilidad (que incluye el nombre del LED).
function actualizarTarjetaLed(tarjeta, encendido) {
    const indicador = tarjeta.querySelector(".indicador-led");
    const estado = tarjeta.querySelector(".estado-led");
    const boton = tarjeta.querySelector(".boton-led-toggle");
    const titulo = tarjeta.dataset.nombre || `LED ${tarjeta.dataset.led}`;

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

// Busca la tarjeta del LED y la actualiza (si existe).
function actualizarLed(numero, encendido) {
    const tarjeta = buscarTarjeta(numero);
    if (tarjeta) {
        actualizarTarjetaLed(tarjeta, encendido);
    }
}


// ==========================================
// NOMBRES DE LOS LED (renombrar desde la página)
// ==========================================

// Muestra en la tarjeta el nombre vigente y cómo se dice por voz.
// Muestra en la tarjeta el nombre vigente, el cartel de voz y la etiqueta accesible del lápiz. Solo escribe en la página si el texto cambió.
function aplicarNombreTarjeta(tarjeta, info) {
    const numero = tarjeta.dataset.led;
    tarjeta.dataset.nombre = info.nombre;

    const titulo = tarjeta.querySelector(".nombre-led");
    if (titulo.textContent !== info.nombre) {
        titulo.textContent = info.nombre;
    }
    titulo.title = info.personalizado ? `LED ${numero}` : "";

    tarjeta
        .querySelector(".boton-renombrar")
        .setAttribute("aria-label", `Cambiar el nombre de ${info.nombre}`);
    tarjeta.querySelector(".boton-renombrar").title = "Cambiar nombre";

    // Texto del cartel: muestra exactamente qué decir para encender este LED.
    const textoVoz = `Por voz: «${palabraInicio()} encender ${info.nombre}»`;
    const vozLed = tarjeta.querySelector(".voz-led");
    if (vozLed.textContent !== textoVoz) {
        vozLed.textContent = textoVoz;
    }

    // El botón de encender/apagar nombra al LED en su etiqueta de accesibilidad.
    const encendido = tarjeta.querySelector(".indicador-led").classList.contains("encendido");
    actualizarTarjetaLed(tarjeta, encendido);
}

// Guarda lo que informa el servidor y lo refleja en tarjetas y ayuda. Si nada
// cambió no toca la página: esta función se ejecuta cada segundo.
// Recibe los nombres del servidor, los guarda y los refleja en tarjetas y ayuda. Se ejecuta cada segundo, por eso no hace nada si no cambió nada.
function aplicarNombres(nombres) {
    if (!nombres || typeof nombres !== "object") {
        return;
    }

    const nuevos = {};
    for (const [clave, info] of Object.entries(nombres)) {
        const numero = Number(clave);
        if (!Number.isInteger(numero) || !info || typeof info.nombre !== "string") continue;
        nuevos[numero] = { nombre: info.nombre, personalizado: Boolean(info.personalizado) };
    }

    // Compara con la versión anterior; si es igual, termina. Si cambió, actualiza cada tarjeta (solo el título: si alguien escribe un nombre en esta pestaña, su campo no se toca) y la ayuda.
    const firma = JSON.stringify(nuevos);
    if (firma === firmaNombres) {
        return;
    }
    firmaNombres = firma;
    nombresLeds = nuevos;

    // Solo se cambia el título: si alguien está escribiendo un nombre en esta
    // pestaña, su campo de texto no se toca aunque el nombre cambie en otra.
    for (const tarjeta of listaLeds.querySelectorAll(".tarjeta-led")) {
        aplicarNombreTarjeta(tarjeta, infoLed(Number(tarjeta.dataset.led)));
    }
    dibujarAyudaLeds();
}

// Construye el formulario de cambio de nombre: etiqueta, campo de texto, pista, zona de error y botones Guardar/Cancelar.
function crearFormularioNombre(tarjeta, numero) {
    const formulario = document.createElement("form");
    formulario.className = "formulario-nombre-led";
    formulario.hidden = true;
    formulario.noValidate = true;

    const idCampo = `nombre-led-${numero}`;

    const etiqueta = document.createElement("label");
    etiqueta.className = "etiqueta";
    etiqueta.htmlFor = idCampo;
    etiqueta.textContent = `Nombre del LED ${numero}`;

    const campo = document.createElement("input");
    campo.type = "text";
    campo.id = idCampo;
    campo.className = "campo-nombre-led";
    campo.maxLength = LARGO_MAXIMO_NOMBRE;
    campo.autocomplete = "off";
    campo.spellcheck = false;
    campo.placeholder = `LED ${numero}`;

    const pista = document.createElement("p");
    pista.className = "texto-secundario";
    pista.textContent = `Dejalo vacío para volver a «LED ${numero}».`;

    const error = document.createElement("p");
    error.className = "aviso estado-error aviso-nombre";
    error.setAttribute("role", "alert");
    error.hidden = true;

    const acciones = document.createElement("div");
    acciones.className = "acciones-nombre-led";

    const guardar = document.createElement("button");
    guardar.type = "submit";
    guardar.className = "boton-guardar-nombre";
    guardar.textContent = "Guardar";

    const cancelar = document.createElement("button");
    cancelar.type = "button";
    cancelar.className = "boton-secundario";
    cancelar.textContent = "Cancelar";
    cancelar.addEventListener("click", () => cerrarEdicionNombre(tarjeta));

    acciones.append(guardar, cancelar);
    formulario.append(etiqueta, campo, pista, error, acciones);

    // Al enviar (Enter o botón Guardar) evita recargar la página y guarda el nombre. Esc cancela y devuelve el foco al lápiz.
    formulario.addEventListener("submit", (evento) => {
        evento.preventDefault();
        guardarNombre(tarjeta, numero, campo.value);
    });
    // Esc cancela y devuelve el foco al lápiz.
    formulario.addEventListener("keydown", (evento) => {
        if (evento.key === "Escape") {
            evento.stopPropagation();
            cerrarEdicionNombre(tarjeta);
        }
    });

    return formulario;
}

// Muestra el formulario con el nombre actual (o vacío si el LED no fue renombrado) y pone el cursor en el campo.
function abrirEdicionNombre(tarjeta) {
    const info = infoLed(Number(tarjeta.dataset.led));
    const formulario = tarjeta.querySelector(".formulario-nombre-led");
    const campo = formulario.querySelector(".campo-nombre-led");

    tarjeta.dataset.editando = "true";
    formulario.hidden = false;
    formulario.querySelector(".aviso-nombre").hidden = true;
    campo.value = info.personalizado ? info.nombre : "";
    tarjeta.querySelector(".boton-renombrar").setAttribute("aria-expanded", "true");
    campo.focus();
    campo.select();
}

// Oculta el formulario y, por accesibilidad, devuelve el foco del teclado al lápiz.
function cerrarEdicionNombre(tarjeta, devolverFoco = true) {
    delete tarjeta.dataset.editando;
    tarjeta.querySelector(".formulario-nombre-led").hidden = true;
    const lapiz = tarjeta.querySelector(".boton-renombrar");
    lapiz.setAttribute("aria-expanded", "false");
    if (devolverFoco) {
        lapiz.focus();
    }
}

// Envía el nombre a app.py y refleja el resultado. Si el servidor lo rechaza (repetido, palabra reservada...), muestra el motivo bajo el campo y lo deja abierto.
async function guardarNombre(tarjeta, numero, texto) {
    const formulario = tarjeta.querySelector(".formulario-nombre-led");
    const campo = formulario.querySelector(".campo-nombre-led");
    const error = formulario.querySelector(".aviso-nombre");
    const botonGuardar = formulario.querySelector(".boton-guardar-nombre");

    botonGuardar.disabled = true;
    error.hidden = true;
    try {
        // PUT /api/led/<n>/nombre: app.py llama a nombres_leds.establecer(), que valida y guarda en datos/nombres_leds.json.
        const datos = await enviarJSON(`/api/led/${numero}/nombre`, { nombre: texto }, "PUT");
        aplicarNombres(datos.nombres);
        resultadoVoz.textContent = datos.mensaje;
        cerrarEdicionNombre(tarjeta);
        // El formulario de reglas y sus descripciones usan el nombre nuevo.
        // Avisa al panel de automatizaciones (automatizaciones.js) para que actualice sus menús y descripciones con el nombre nuevo.
        window.automatizaciones?.refrescar();
    } catch (fallo) {
        error.textContent = fallo.message || "No se pudo cambiar el nombre.";
        error.hidden = false;
        campo.focus();
    } finally {
        botonGuardar.disabled = false;
    }
}

// Lista de la ayuda con una orden de encender y otra de apagar por cada LED,
// con el nombre que tiene en este momento.
// Dibuja en la Ayuda de comandos una orden de encender y otra de apagar por cada LED, con el nombre que tiene en este momento. Solo redibuja si los nombres cambiaron.
function dibujarAyudaLeds() {
    if (!listaAyudaLeds) {
        return;
    }

    // Ordena los LED por número y compara con la última versión dibujada.
    const numeros = Object.keys(nombresLeds).map(Number).sort((a, b) => a - b);
    const firma = JSON.stringify([palabraInicio(), numeros.map((numero) => nombresLeds[numero])]);
    if (firma === firmaAyudaLeds) {
        return;
    }
    firmaAyudaLeds = firma;

    const palabra = palabraInicio();
    listaAyudaLeds.replaceChildren(
        ...numeros.map((numero) => {
            const info = nombresLeds[numero];

            const item = document.createElement("li");
            const frases = document.createElement("span");
            frases.className = "comando-frases";
            for (const accion of ["encender", "apagar"]) {
                const codigo = document.createElement("code");
                const clave = document.createElement("span");
                clave.className = "palabra-clave";
                clave.textContent = palabra;
                codigo.append(clave, ` ${accion} ${info.nombre}`);
                frases.append(codigo);
            }

            const detalle = document.createElement("span");
            detalle.className = "comando-detalle";
            detalle.textContent = info.personalizado
                ? `Enciende o apaga «${info.nombre}» (el LED ${numero}).`
                : `El LED ${numero} conserva su nombre original. Podés cambiarlo con el lápiz de su tarjeta.`;

            item.append(frases, detalle);
            return item;
        })
    );
}

// Botón Encender/Apagar de una tarjeta: pide a app.py invertir el LED y actualiza la tarjeta. En caso de error muestra el mensaje y vuelve a sincronizar.
async function alternarLed(numero) {
    try {
        // El servidor lee el GPIO y alterna de forma atómica. Así no depende
        // del estado posiblemente desactualizado que tenga esta pestaña.
        // POST /api/led/<n>/alternar (app.py -> dispositivos.alternar_led).
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
// Botones «Encender todos» y «Apagar todos»: una sola petición para los cuatro LED.
async function controlarTodosLeds(encender) {
    try {
        // POST /api/leds/todos (app.py -> dispositivos.controlar_todos_leds).
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

// Conecta los dos botones generales a la función anterior.
$("encender-todos")?.addEventListener("click", () => controlarTodosLeds(true));
$("apagar-todos")?.addEventListener("click", () => controlarTodosLeds(false));


// ==========================================
// CARGAR ESTADO INICIAL
// ==========================================

// Aplica a la página un estado recibido del servidor: nombres, LED (crea las tarjetas que falten), servo y sensor. Lo usan sincronizarEstado() y las órdenes de voz.
function aplicarEstadoDispositivos(datos, crearTarjetas = false) {
    if (!datos || typeof datos !== "object") {
        return;
    }

    // Estado del asistente (modo, palabras de activación, despierto/dormido): lo muestra asistente.js.
    if (datos.asistente) {
        window.asistenteVoz?.aplicar(datos.asistente);
    }

    // Primero los nombres: así las tarjetas nuevas ya nacen con el nombre correcto.
    if (datos.nombres) {
        aplicarNombres(datos.nombres);
    }

    if (datos.leds && typeof datos.leds === "object") {
        for (const [numeroTexto, encendido] of Object.entries(datos.leds)) {
            const numero = Number(numeroTexto);
            if (!Number.isInteger(numero)) continue;

            // Busca la tarjeta del LED; si no existe (por ejemplo, se agregó un LED en dispositivos.py) la crea.
            let tarjeta = buscarTarjeta(numero);

            if (!tarjeta) {
                // Si se añadió un LED en la configuración, también aparece
                // en las pestañas que ya estaban abiertas.
                tarjeta = crearTarjetaLed(numero, Boolean(encendido));
                listaLeds.appendChild(tarjeta);
            }

            actualizarTarjetaLed(tarjeta, Boolean(encendido));
        }
    }

    // Servo: mueve el deslizador (salvo que la persona lo esté usando), el dial y el texto de última posición.
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

    // Sensor: actualiza el botón y el texto de estado.
    if (typeof datos.sensor_activo === "boolean") {
        actualizarEstadoSensor(datos.sensor_activo);
    }
}

// Bandera para no lanzar dos sincronizaciones a la vez.
let sincronizandoEstado = false;

// SINCRONIZACIÓN ENTRE PESTAÑAS: pide el estado completo a app.py y lo aplica. Se ejecuta cada segundo y tras cada acción, así todos los navegadores abiertos ven lo mismo.
async function sincronizarEstado() {
    if (sincronizandoEstado) return;
    sincronizandoEstado = true;

    try {
        // Evitar respuestas cacheadas: cada pestaña consulta al mismo Flask.
        // GET /api/estado (app.py: dispositivos.obtener_estado() + nombres de nombres_leds.py).
        const datos = await solicitar("/api/estado", { cache: "no-store" });
        aplicarEstadoDispositivos(datos, true);
    } catch (error) {
        // No sobreescribir los controles si una consulta temporal falla.
        console.warn("No se pudo sincronizar el estado de los dispositivos:", error);
    } finally {
        sincronizandoEstado = false;
    }
}

// Carga inicial al abrir la página: borra el texto «Cargando LED...», dibuja las tarjetas y, si el sensor ya estaba activo, consulta la distancia.
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
// Mueve el dial del servo: gira la aguja, rellena el arco de progreso y actualiza el texto accesible. Limita el valor a 0–180.
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

// Mientras se arrastra el deslizador, se muestra el valor elegido (todavía sin enviarlo).
controlServo.addEventListener("input", () => {
    valorAngulo.textContent = `${controlServo.value}°`;
});

// Botón «Aplicar posición»: envía el ángulo a app.py.
$("enviar-servo").addEventListener("click", async () => {
    const angulo = Number(controlServo.value);
    try {
        // POST /api/servo (app.py -> dispositivos.mover_servo).
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

// Refleja si el sensor está activo: texto y color del botón y mensajes de estado.
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

// Activa o desactiva el sensor (botón o comando de voz).
async function cambiarEstadoSensor(activo, desdeVoz = false) {
    try {
        // POST /api/sensor (app.py -> dispositivos.configurar_sensor).
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

// Clic en el botón del sensor: invierte el estado actual.
botonSensor.addEventListener("click", () => {
    cambiarEstadoSensor(!sensorActivo);
});

// Consulta la distancia actual y la muestra. Se evita solapar consultas con la bandera «consultandoDistancia».
async function actualizarDistancia() {
    if (!sensorActivo || consultandoDistancia) {
        return;
    }

    consultandoDistancia = true;
    try {
        // GET /api/distancia (app.py -> última medición de sensor_monitor.py).
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

// Al cargar, pregunta a app.py si Vosk y el modelo están disponibles y muestra el aviso verde o naranja.
async function comprobarReconocimientoOffline() {
    try {
        // GET /api/voz/estado (app.py -> reconocimiento_voz.servicio_voz.estado()).
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

// ═══ CAPTURA DE AUDIO ═══
// Vacía la memoria temporal del audio (se usa al activar el micrófono).
function reiniciarBufferAudio() {
    fragmentosAudio = [];
    muestrasDisponibles = 0;
    offsetPrimerFragmento = 0;
}

// Toma «cantidad» muestras de audio de la memoria temporal (que está guardada en trozos) y las junta en un solo bloque.
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

// Convierte el audio del navegador (decimales, normalmente a 44,1 o 48 kHz) al formato que pide Vosk: números enteros de 16 bits a 16 kHz (PCM). Es lo que recibe reconocimiento_voz.procesar_audio.
function convertirPCM16k(muestras, frecuenciaOrigen) {
    const longitudSalida = Math.floor(muestras.length * FRECUENCIA_VOSK / frecuenciaOrigen);
    const buffer = new ArrayBuffer(longitudSalida * 2);
    const vista = new DataView(buffer);
    // Para cada muestra de salida se interpola entre dos de entrada (remuestreo lineal) y se la recorta a -1..1 antes de pasarla a entero.
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

// Se ejecuta cada vez que el micrófono entrega un trocito de audio: lo guarda y, cuando hay medio segundo acumulado, lo convierte en PCM.
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
        encolarBloqueAudio(pcm);
    }
}

// Mantiene acotada la espera: ante una sobrecarga excepcional se descarta
// el bloque más antiguo que todavía no fue enviado, conservando los recientes.
// El servidor reinicia el contexto de Vosk antes del siguiente bloque para no
// unir palabras separadas por el audio que se perdió.
function encolarBloqueAudio(pcm) {
    if (colaBloquesAudio.length >= MAX_BLOQUES_PENDIENTES) {
        colaBloquesAudio.shift();
        metricasAudio.bloquesDescartados += 1;
        audioDiscontinuoPendiente = true;
    }

    colaBloquesAudio.push({ pcm, capturadoEn: performance.now() });
    void drenarColaAudio();
}

// Solo puede haber una petición de audio simultánea. El drenaje conserva el
// orden temporal de los bloques que siguen dentro de la cola.
function drenarColaAudio() {
    if (procesandoColaAudio) {
        return promesaDrenajeAudio;
    }

    procesandoColaAudio = true;
    promesaDrenajeAudio = (async () => {
        try {
            while (escuchando && colaBloquesAudio.length > 0) {
                const bloque = colaBloquesAudio.shift();
                const discontinuidad = audioDiscontinuoPendiente;
                audioDiscontinuoPendiente = false;

                try {
                    await enviarBloqueAudio(bloque, discontinuidad);
                } catch (error) {
                    // Si una petición falla, el bloque pudo no llegar al servidor:
                    // el próximo envío debe empezar un contexto acústico nuevo.
                    audioDiscontinuoPendiente = true;
                    if (escuchando) {
                        resultadoVoz.textContent = error.message;
                    }
                }
            }
        } finally {
            procesandoColaAudio = false;
        }
    })();

    return promesaDrenajeAudio;
}

// Expone diagnóstico sin modificar el diseño: detalle en el atributo title y
// una línea periódica en la consola del navegador (F12 -> Consola).
function registrarMetricasAudio(datos, latenciaMs, esperaColaMs, discontinuidad) {
    const servidor = datos.metricas || {};
    metricasAudio.solicitudes += 1;
    metricasAudio.ultimaLatenciaMs = latenciaMs;
    metricasAudio.ultimaEsperaServidorMs = Number(servidor.espera_bloqueo_ms) || 0;
    metricasAudio.ultimoProcesamientoMs = Number(servidor.procesamiento_ms) || 0;
    metricasAudio.ultimaEsperaColaMs = esperaColaMs;

    const diagnostico = [
        `Audio ida/vuelta: ${latenciaMs.toFixed(0)} ms`,
        `espera en Flask: ${metricasAudio.ultimaEsperaServidorMs.toFixed(1)} ms`,
        `Vosk: ${metricasAudio.ultimoProcesamientoMs.toFixed(1)} ms`,
        `espera local: ${esperaColaMs.toFixed(0)} ms`,
        `cola: ${colaBloquesAudio.length}/${MAX_BLOQUES_PENDIENTES}`,
        `descartados: ${metricasAudio.bloquesDescartados}`,
    ].join(" · ");

    if (estadoMicrofono) {
        estadoMicrofono.title = diagnostico;
    }

    if (metricasAudio.solicitudes % 10 === 0 || discontinuidad) {
        console.debug("Diagnóstico de voz:", {
            latenciaIdaVueltaMs: Math.round(latenciaMs),
            esperaBloqueoServidorMs: Number(metricasAudio.ultimaEsperaServidorMs.toFixed(1)),
            procesamientoVoskMs: Number(metricasAudio.ultimoProcesamientoMs.toFixed(1)),
            esperaColaMs: Math.round(esperaColaMs),
            bloquesEnCola: colaBloquesAudio.length,
            bloquesDescartados: metricasAudio.bloquesDescartados,
            contextoReiniciado: Boolean(discontinuidad),
        });
    }
}

// Envía un bloque de audio a app.py y procesa lo que responde Vosk: texto parcial (en vivo) o frase final (comando).
async function enviarBloqueAudio(bloque, discontinuidad = false) {
    if (!escuchando) {
        return;
    }

    const inicioSolicitud = performance.now();
    const esperaColaMs = Math.max(0, inicioSolicitud - bloque.capturadoEn);
    const headers = { "Content-Type": "application/octet-stream" };
    if (discontinuidad) {
        headers["X-Audio-Discontinuity"] = "1";
    }

    // POST /api/voz/audio (app.py -> reconocimiento_voz.servicio_voz.procesar_audio).
    const datos = await solicitar("/api/voz/audio", {
        method: "POST",
        headers,
        body: bloque.pcm,
    });
    const latenciaMs = performance.now() - inicioSolicitud;
    registrarMetricasAudio(datos, latenciaMs, esperaColaMs, discontinuidad);

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
        // Frase terminada: se envía a procesarComando(), que la manda a app.py (POST /api/comando).
        await procesarComando(datos.texto);
    }
}


// ==========================================
// ENCENDER Y APAGAR EL MICROFONO
// ==========================================

// Habilita «Activar micrófono» o «Apagar micrófono» según corresponda.
function actualizarBotonesMicrofono() {
    botonActivar.disabled = escuchando || iniciandoMicrofono;
    botonApagar.disabled = !escuchando;
}

// Botón «Activar micrófono»: pide permiso al navegador, abre el audio, inicia la sesión en app.py (POST /api/voz/iniciar) y empieza a enviar bloques. Requiere HTTPS (por eso app.py usa certificados).
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
        // Solicita el micrófono con cancelación de eco, supresión de ruido y control automático de ganancia.
        flujoMicrofono = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            },
        });

        // Crea el contexto de audio del navegador (Web Audio).
        contextoAudio = new (window.AudioContext || window.webkitAudioContext)();
        await contextoAudio.resume();

        // Carga Vosk en el servidor y crea un reconocedor nuevo para esta sesión.
        // POST /api/voz/iniciar (app.py -> reconocimiento_voz.servicio_voz.iniciar(), que carga el modelo de Vosk).
        const datosInicio = await enviarJSON("/api/voz/iniciar", {});
        resultadoVoz.textContent = datosInicio.mensaje;
        if (textoVosk) {
            textoVosk.textContent = "Micrófono activo; esperando voz...";
        }

        reiniciarBufferAudio();
        colaBloquesAudio = [];
        procesandoColaAudio = false;
        promesaDrenajeAudio = Promise.resolve();
        audioDiscontinuoPendiente = false;
        Object.assign(metricasAudio, {
            solicitudes: 0,
            bloquesDescartados: 0,
            ultimaLatenciaMs: 0,
            ultimaEsperaServidorMs: 0,
            ultimoProcesamientoMs: 0,
            ultimaEsperaColaMs: 0,
        });
        if (estadoMicrofono) estadoMicrofono.title = "";
        // Cadena de audio: micrófono -> procesador (que llama a procesarCapturaAudio cada 4096 muestras) -> volumen en cero -> salida. El volumen cero evita oír el propio micrófono pero mantiene el procesador funcionando.
        nodoMicrofono = contextoAudio.createMediaStreamSource(flujoMicrofono);
        procesadorAudio = contextoAudio.createScriptProcessor(4096, 1, 1);
        gananciaSilencio = contextoAudio.createGain();
        gananciaSilencio.gain.value = 0;

        procesadorAudio.onaudioprocess = procesarCapturaAudio;
        // Conecta la cadena de audio y marca que ya se está escuchando.
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

// Libera todo lo del audio local: desconecta los nodos, apaga el micrófono (las pistas) y cierra el contexto, para que el navegador deje de mostrar «grabando».
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

// Botón «Apagar micrófono»: deja de escuchar, libera el audio, espera a que terminen de enviarse los bloques pendientes y cierra la sesión en app.py (POST /api/voz/detener -> servicio_voz.detener()).
async function detenerMicrofono(mensaje) {
    escuchando = false;
    // No se envían bloques que quedaron esperando cuando el usuario apagó el micrófono.
    // La petición que ya estaba en curso termina antes de cerrar la sesión del servidor.
    colaBloquesAudio = [];
    audioDiscontinuoPendiente = false;
    actualizarBotonesMicrofono();
    estadoMicrofono.textContent = "Micrófono apagado";

    await liberarAudioLocal();

    try {
        await promesaDrenajeAudio;
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

// Conecta los botones del micrófono a sus funciones.
botonActivar.addEventListener("click", iniciarMicrofono);
botonApagar.addEventListener("click", () => detenerMicrofono("Reconocimiento detenido."));


// ==========================================
// PROCESAR COMANDO RECONOCIDO
// ==========================================

// ═══ EJECUCIÓN DE UNA ORDEN DE VOZ ═══
// Recibe la frase que Vosk reconoció, se la manda a app.py y refleja en la página lo que respondió. Lo llama enviarBloqueAudio() cada vez que Vosk termina una frase.
async function procesarComando(texto) {
    resultadoVoz.textContent = `Comando reconocido: ${texto}`;

    try {
        // POST /api/comando: app.py interpreta la frase (función comando()) y ejecuta la acción. Si falla (frase no reconocida, LED inexistente...) lanza una excepción con el mensaje del servidor.
        const datos = await enviarJSON("/api/comando", { comando: texto });
        resultadoVoz.textContent = datos.mensaje;

        // Estado del asistente (despierto o dormido, palabras): el servidor lo informa con cada respuesta.
        // En una despedida explícita se suprime el aviso automático de inactividad:
        // la respuesta «Hasta luego» se reproduce una sola vez más abajo.
        const contieneDespedida = Boolean(datos.despedida) || (
            Array.isArray(datos.resultados) && datos.resultados.some(function (resultado) {
                return Boolean(resultado && resultado.despedida);
            })
        );
        window.asistenteVoz?.aplicar(datos.asistente, {
            suprimirAvisoCierre: contieneDespedida,
        });

        // Con el asistente despierto, lo que no es una orden (charla) se informa pero sin tratarlo como un error.
        if (datos.ignorado) {
            resultadoVoz.textContent = `Escuché: “${texto}”. ${datos.mensaje}`;
            return;
        }

        // Una frase puede traer VARIAS órdenes («encender led uno y activar sensor»): el servidor responde con
        // «resultados» (uno por orden). Con una sola orden la respuesta es el propio «datos».
        const resultados = Array.isArray(datos.resultados) ? datos.resultados : [datos];
        for (const resultado of resultados) {
            // Una orden que falló no cambió nada: no hay nada que reflejar (su mensaje ya está en el resumen).
            if (resultado.ok) {
                await aplicarResultadoOrden(resultado, texto, resultados.length === 1);
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
    } finally {
        // Cada orden queda anotada en el registro del servidor y puede haber
        // creado, borrado o pausado reglas: se actualizan esos paneles ya, sin
        // esperar al ciclo de un segundo.
        // Siempre, al terminar: actualiza el panel «Registro de comandos» (registro.js) y el de reglas (automatizaciones.js) para ver al instante la orden y sus efectos.
        window.registroComandos?.refrescar();
        window.automatizaciones?.refrescar();
    }
}


// Refleja en la página el resultado de UNA orden que salió bien. procesarComando() la llama una vez por cada
// orden de la frase. «esUnica» indica si la frase tenía una sola orden (solo entonces ciertos mensajes
// reemplazan al resumen).
async function aplicarResultadoOrden(datos, texto, esUnica) {
    // FUNCIÓN 1 — Saludo: se dijo solo la palabra de activación. El saludo (únicamente texto) va en la burbuja
    // «Respuesta del asistente».
    if (datos.bienvenida) {
        window.asistenteVoz?.respuesta(datos.mensaje);
        resultadoVoz.textContent = "Asistente llamado.";
        return;
    }
    // Despedida («adiós»): termina la conversación. «cierra» evita agregar el aviso de «terminó por inactividad».
    if (datos.despedida) {
        window.asistenteVoz?.respuesta(datos.mensaje, { cierra: true });
        if (esUnica) {
            resultadoVoz.textContent = "Conversación terminada.";
        }
        return;
    }

    // Según lo que respondió el servidor, se actualiza la parte correspondiente de la página: LED individual (el número y el estado vienen en la respuesta, así que sirve cualquier nombre que se haya dicho)...
    if (Number.isInteger(datos.led) && typeof datos.encendido === "boolean") {
        actualizarLed(datos.led, datos.encendido);
    } else if (texto.toLowerCase().includes("led")) {
        const estado = await solicitar("/api/estado");
        for (const [numero, encendido] of Object.entries(estado.leds)) {
            actualizarLed(Number(numero), encendido);
        }
    }

    // «Todas las leds» y «apagar todo» devuelven el estado de todos los LED.
    // ...todos los LED...
    if (datos.leds && typeof datos.leds === "object") {
        aplicarEstadoDispositivos({ leds: datos.leds });
    }

    // «Estado» devuelve el estado completo de los dispositivos.
    // ...resumen del comando «estado»...
    if (datos.estado && typeof datos.estado === "object") {
        aplicarEstadoDispositivos(datos.estado);
    }

    // ...servo (mueve el deslizador y el dial)...
    if (Number.isInteger(datos.angulo)) {
        controlServo.value = datos.angulo;
        valorAngulo.textContent = `${datos.angulo}°`;
        actualizarIndicadorServo(datos.angulo);
        estadoServo.textContent = `Último ángulo solicitado: ${datos.angulo}°`;
    }

    // ...sensor (activado/desactivado) o consulta de distancia...
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
    // ...tema: cambia claro/oscuro con window.temaInterfaz (tema.js)...
    if (datos.tema && window.temaInterfaz) {
        const temaNuevo = datos.tema === "alternar"
            ? window.temaInterfaz.alternar()
            : window.temaInterfaz.aplicar(datos.tema);
        if (temaNuevo && esUnica) {
            resultadoVoz.textContent = `Tema ${temaNuevo} activado.`;
        }
    }

    // ...ayuda: abre o cierra el menú con window.ayudaComandos (ayuda.js).
    if (datos.ayuda && window.ayudaComandos) {
        if (datos.ayuda === "cerrar") {
            window.ayudaComandos.cerrar();
        } else {
            window.ayudaComandos.abrir(datos.ayuda);
        }
    }
}


// Cuando la persona cambia las palabras de activación (asistente.js avisa con este evento), se actualizan los
// carteles «Por voz: …» de cada LED y la lista de la ayuda, que usan la palabra principal.
document.addEventListener("palabras-inicio-cambiadas", () => {
    for (const tarjeta of listaLeds.querySelectorAll(".tarjeta-led")) {
        aplicarNombreTarjeta(tarjeta, infoLed(Number(tarjeta.dataset.led)));
    }
    dibujarAyudaLeds();
});


// ==========================================
// INICIALIZACION
// ==========================================

actualizarBotonesMicrofono();
// ═══ ARRANQUE ═══
// Al cargar la página: deja los botones del micrófono en su estado inicial, carga las tarjetas de LED y el estado de los dispositivos...
cargarEstado();
// ...y comprueba que Vosk esté disponible.
comprobarReconocimientoOffline();

// Sincronización compartida: cada pestaña/navegador consulta el estado
// central de Flask. Una acción hecha en cualquier otra pestaña aparece aquí.
// Cada segundo: sincroniza el estado (así se ven los cambios hechos desde otra pestaña, incluidos los nombres de los LED) y, si el sensor está activo, actualiza la distancia.
setInterval(() => {
    sincronizarEstado();
    if (sensorActivo) {
        actualizarDistancia();
    }
}, 1000);

// Al volver a mostrar la pestaña, sincroniza de inmediato.
document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
        sincronizarEstado();
        if (sensorActivo) actualizarDistancia();
    }
});

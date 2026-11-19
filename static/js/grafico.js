// static/js/grafico.js
// Gráfico de la distancia medida en los últimos 60 segundos.
//
// Está dibujado con SVG propio, sin librerías externas, para que siga
// funcionando sin internet. Los colores salen de las variables de estilos.css
// (clases grafico-*), así que acompaña al tema claro, al oscuro y a cualquiera
// que se agregue.
//
// Los datos los guarda el servidor (sensor_monitor.py) y se piden a
// /api/distancia/historial: por eso el gráfico se ve completo aunque se recargue
// la página o se abra desde otro dispositivo. Cada consulta trae solo las
// muestras nuevas (?desde=).
//
// automatizaciones.js le avisa las reglas vigentes con graficoDistancia.fijarReglas()
// para dibujar el umbral de cada una como una línea punteada.

// ┌─────────────────────────────────────────────────────────────────────────┐
// │ DE QUIÉN DEPENDE / QUIÉN LO USA                                         │
// │  - templates/index.html: contiene el <svg id="grafico-svg"> y demás     │
// │    elementos #grafico-* sobre los que se dibuja.                        │
// │  - app.py: GET /api/distancia/historial entrega las muestras (que       │
// │    guarda sensor_monitor.py).                                           │
// │  - static/js/automatizaciones.js llama a                                │
// │    window.graficoDistancia.fijarReglas() (definido al final) para       │
// │    dibujar el umbral de cada regla.                                     │
// │  - static/css/estilos.css da color a las clases grafico-*.              │
// └─────────────────────────────────────────────────────────────────────────┘
// Función autoejecutable: mantiene sus variables privadas.
(function () {
    // Busca el contenedor y el SVG; si no existen, no hace nada.
    const lienzo = document.getElementById("grafico-lienzo");
    const svg = document.getElementById("grafico-svg");
    if (!lienzo || !svg) {
        return;
    }

    // Otros elementos: mensaje de «sin datos», globo con el valor bajo el puntero, estadísticas y título del gráfico.
    const textoVacio = document.getElementById("grafico-vacio");
    const globo = document.getElementById("grafico-globo");
    const estadisticas = document.getElementById("grafico-estadisticas");
    const titulo = document.querySelector("#grafico-distancia figcaption");

    // Espacio de nombres necesario para crear elementos SVG desde JavaScript.
    const NS = "http://www.w3.org/2000/svg";
    // El gráfico muestra los últimos 60 segundos (igual a VENTANA_GRAFICO_S de app.py).
    const VENTANA_S = 60;
    // Si dos muestras seguidas están más separadas que esto, hay un hueco en la
    // línea (el sensor estuvo apagado o sin eco).
    // Si dos muestras están separadas por más de 1,5 s, la línea se corta (el sensor estuvo apagado o sin eco).
    const SALTO_MAXIMO_S = 1.5;
    // Márgenes (en píxeles) alrededor del área de dibujo, para los números de los ejes.
    const MARGEN = { izquierda: 54, derecha: 14, arriba: 14, abajo: 26 };
    // Techos posibles del eje vertical, en cm; se elige el más chico que alcance.
    // Alturas posibles del eje vertical (cm); se usa la más chica que alcance para los datos.
    const ESCALAS = [50, 100, 150, 200, 300, 400];
    // Posiciones de las marcas del eje del tiempo (segundos respecto de «ahora»).
    const MARCAS_TIEMPO = [-60, -45, -30, -15, 0];
    const SEPARACION_ETIQUETAS = 13;  // píxeles mínimos entre los nombres de dos umbrales

    // Estado del gráfico: muestras recibidas, hora del servidor, si el sensor está activo, reglas para los umbrales, tamaño actual y posición del puntero.
    let muestras = [];       // [momento, centímetros | null], de la más vieja a la más nueva
    let ultimoMomento = 0;   // momento de la última muestra recibida
    let ahoraServidor = null;
    let recibidoEn = 0;      // performance.now() cuando llegó ahoraServidor
    let activo = false;
    let consultando = false;
    let reglas = [];
    let reglasPausadas = false;
    let ancho = 0;
    let alto = 0;
    let punteroX = null;
    let escala = null;       // datos del último dibujo, para el globo del puntero
    let temporizador = null;

    // Crea un elemento SVG con sus atributos (línea, texto, círculo...).
    function crear(etiqueta, atributos = {}) {
        const nodo = document.createElementNS(NS, etiqueta);
        for (const [nombre, valor] of Object.entries(atributos)) {
            nodo.setAttribute(nombre, valor);
        }
        return nodo;
    }

    // Muestra un número con un decimal.
    function formatear(valor) {
        return valor.toFixed(1);
    }

    // Instante que corresponde al borde derecho del gráfico.
    // Instante que corresponde al borde derecho. Con el sensor activo avanza fluido (se extrapola entre consultas); detenido, se congela en la última medición.
    function momentoActual() {
        if (ahoraServidor === null) {
            return null;
        }
        if (activo) {
            // Entre consulta y consulta se extrapola, para que el eje avance fluido.
            return ahoraServidor + (performance.now() - recibidoEn) / 1000;
        }
        // Con el sensor detenido el gráfico se congela en la última medición,
        // así se pueden revisar los datos con calma.
        return muestras.length ? muestras[muestras.length - 1][0] : ahoraServidor;
    }

    // Todo lo que dibuja el gráfico.
    // ---------- dibujo ----------

    // Redibuja el gráfico completo: ejes, cuadrículas, umbrales de reglas, línea, área y último punto.
    function dibujar() {
        if (!ancho || !alto) {
            return;
        }

        // Calcula la ventana de tiempo (últimos 60 s) y qué muestras entran, y el valor máximo.
        const fin = momentoActual();
        if (fin === null) {
            return;
        }
        const inicio = fin - VENTANA_S;
        const visibles = muestras.filter(([momento]) => momento >= inicio && momento <= fin + 0.5);
        const validas = visibles.filter(([, cm]) => cm !== null);

        const maximo = validas.reduce((acumulado, [, cm]) => Math.max(acumulado, cm), 0);
        // Elige el techo del eje vertical según el máximo medido (con 10 % de margen).
        const techo = ESCALAS.find((valor) => valor >= maximo * 1.1) ?? ESCALAS[ESCALAS.length - 1];

        const izquierda = MARGEN.izquierda;
        const derecha = ancho - MARGEN.derecha;
        const arriba = MARGEN.arriba;
        const abajo = alto - MARGEN.abajo;
        // Funciones x() e y(): convierten un tiempo y una distancia en coordenadas de la pantalla.
        const x = (momento) => izquierda + ((momento - inicio) / VENTANA_S) * (derecha - izquierda);
        const y = (cm) => arriba + (1 - Math.min(cm, techo) / techo) * (abajo - arriba);

        // Guarda los datos de este dibujo para que el globo del puntero sepa dónde está cada punto.
        escala = { inicio, fin, techo, validas, x, y };
        lienzo.dataset.estado = activo ? "activo" : "detenido";
        // Borra el dibujo anterior y define un recorte para que nada se salga del área del gráfico.
        svg.replaceChildren();

        const recorte = crear("clipPath", { id: "grafico-recorte" });
        recorte.appendChild(crear("rect", {
            x: izquierda, y: arriba - 2, width: derecha - izquierda + 4, height: abajo - arriba + 4,
        }));
        const definiciones = crear("defs");
        definiciones.appendChild(recorte);
        svg.appendChild(definiciones);

        // Cuadrícula horizontal y números del eje vertical (cm)
        // Cuadrícula horizontal y números del eje vertical (cm).
        for (let paso = 0; paso <= 4; paso++) {
            const valor = (techo / 4) * paso;
            const posicion = y(valor);
            svg.appendChild(crear("line", {
                class: paso === 0 ? "grafico-eje" : "grafico-cuadricula",
                x1: izquierda, x2: derecha, y1: posicion, y2: posicion,
            }));
            if (paso % 2 === 0) {
                const etiqueta = crear("text", {
                    class: "grafico-texto", x: izquierda - 8, y: posicion, dy: "0.35em", "text-anchor": "end",
                });
                etiqueta.textContent = paso === 4 ? `${valor} cm` : String(valor);
                svg.appendChild(etiqueta);
            }
        }

        // Cuadrícula vertical y tiempos del eje horizontal
        // Cuadrícula vertical y rótulos del eje horizontal (-60 s ... ahora).
        for (const marca of MARCAS_TIEMPO) {
            const posicion = x(fin + marca);
            if (marca !== 0) {
                svg.appendChild(crear("line", {
                    class: "grafico-cuadricula", x1: posicion, x2: posicion, y1: arriba, y2: abajo,
                }));
            }
            const etiqueta = crear("text", {
                class: "grafico-texto", x: posicion, y: abajo + 17,
                "text-anchor": marca === 0 ? "end" : marca === MARCAS_TIEMPO[0] ? "start" : "middle",
            });
            etiqueta.textContent = marca === 0 ? (activo ? "ahora" : "detenido") : `${marca} s`;
            svg.appendChild(etiqueta);
        }

        // Todo lo que sigue se recorta al área del gráfico.
        // Grupo recortado: todo lo que se agregue a él no se sale del área de dibujo.
        const grupo = crear("g", { "clip-path": "url(#grafico-recorte)" });
        svg.appendChild(grupo);

        // Umbrales de las reglas (línea punteada). Los nombres van a la izquierda
        // (lo más nuevo, y con más datos, está a la derecha) y se apilan con una
        // separación mínima para que no se pisen cuando dos umbrales están cerca.
        // Umbrales de las reglas como líneas punteadas, ordenados de arriba a abajo (las reglas vienen de automatizaciones.js).
        const umbrales = reglas
            .filter((regla) => regla.umbral_cm <= techo)
            .map((regla) => ({ regla, posicion: y(regla.umbral_cm) }))
            .sort((a, b) => a.posicion - b.posicion);
        // Una regla desactivada o pausada se dibuja atenuada.
        const esApagada = (regla) => reglasPausadas || !regla.activa;
        for (const { regla, posicion } of umbrales) {
            grupo.appendChild(crear("line", {
                class: esApagada(regla) ? "grafico-umbral grafico-umbral-apagado" : "grafico-umbral",
                x1: izquierda, x2: derecha, y1: posicion, y2: posicion,
            }));
        }
        // Los nombres se dibujan después de todas las líneas, así ninguna los tapa.
        // Los nombres («Regla 1 < 20 cm») se dibujan después de las líneas y se apilan con una separación mínima para no pisarse.
        let ultimaEtiqueta = -Infinity;
        for (const { regla, posicion } of umbrales) {
            const sobreLaLinea = posicion - 5 > arriba + 8;
            const lugar = Math.max(sobreLaLinea ? posicion - 5 : posicion + 13, ultimaEtiqueta + SEPARACION_ETIQUETAS);
            ultimaEtiqueta = lugar;
            const nombre = crear("text", {
                class: esApagada(regla) ? "grafico-texto-umbral grafico-umbral-apagado" : "grafico-texto-umbral",
                x: izquierda + 6, y: lugar, "text-anchor": "start",
            });
            nombre.textContent = `Regla ${regla.id} ${regla.condicion === "menor" ? "<" : ">"} ${regla.umbral_cm} cm`;
            grupo.appendChild(nombre);
        }

        // Línea y área: se cortan donde hay huecos o lecturas sin eco
        // Divide las muestras en tramos continuos: se corta donde hay huecos o lecturas sin eco.
        const segmentos = [];
        let actual = [];
        let previo = null;
        const cerrar = () => {
            if (actual.length) {
                segmentos.push(actual);
            }
            actual = [];
            previo = null;
        };
        for (const [momento, cm] of visibles) {
            if (cm === null) {
                cerrar();
                continue;
            }
            if (previo !== null && momento - previo > SALTO_MAXIMO_S) {
                cerrar();
            }
            actual.push([x(momento), y(cm)]);
            previo = momento;
        }
        cerrar();

        // Dibuja cada tramo como un área sombreada y una línea (o un punto suelto si tiene una sola muestra).
        const base = y(0);
        for (const puntos of segmentos) {
            if (puntos.length === 1) {
                grupo.appendChild(crear("circle", { class: "grafico-punto-suelto", cx: puntos[0][0], cy: puntos[0][1], r: 2.5 }));
                continue;
            }
            const recorrido = puntos.map(([px, py], i) => `${i === 0 ? "M" : "L"}${px.toFixed(1)} ${py.toFixed(1)}`).join(" ");
            const [primeroX] = puntos[0];
            const [ultimoX] = puntos[puntos.length - 1];
            grupo.appendChild(crear("path", {
                class: "grafico-area",
                d: `${recorrido} L${ultimoX.toFixed(1)} ${base.toFixed(1)} L${primeroX.toFixed(1)} ${base.toFixed(1)} Z`,
            }));
            grupo.appendChild(crear("path", { class: "grafico-linea", d: recorrido }));
        }

        // Marca de la lectura más reciente
        // Marca con un punto la lectura más reciente (si tiene menos de 2 s).
        if (activo && validas.length) {
            const [momento, cm] = validas[validas.length - 1];
            if (fin - momento <= 2) {
                grupo.appendChild(crear("circle", { class: "grafico-punto", cx: x(momento), cy: y(cm), r: 4.5 }));
            }
        }

        // Actualiza las estadísticas y el texto accesible, y la guía bajo el puntero.
        actualizarResumen(validas, fin);
        actualizarGuia();
    }

    // Muestra mínimo, promedio y máximo, o el mensaje de «sin datos»; también escribe la descripción para lectores de pantalla.
    function actualizarResumen(validas, fin) {
        if (titulo) {
            titulo.textContent = activo ? "Últimos 60 segundos" : "Últimos 60 segundos · medición detenida";
        }

        if (!validas.length) {
            estadisticas.textContent = "Sin datos";
            textoVacio.hidden = false;
            textoVacio.textContent = activo
                ? "Esperando mediciones válidas…"
                : "Activá el sensor para ver el historial de distancia.";
            svg.setAttribute("aria-label", "Historial de distancia: sin datos en los últimos 60 segundos");
            return;
        }

        textoVacio.hidden = true;
        const valores = validas.map(([, cm]) => cm);
        const minimo = Math.min(...valores);
        const maximo = Math.max(...valores);
        const promedio = valores.reduce((suma, valor) => suma + valor, 0) / valores.length;
        estadisticas.textContent =
            `Mín ${formatear(minimo)} · Prom ${formatear(promedio)} · Máx ${formatear(maximo)} cm`;
        svg.setAttribute(
            "aria-label",
            `Historial de distancia de los últimos 60 segundos. Última lectura ${formatear(valores[valores.length - 1])} cm; `
            + `mínimo ${formatear(minimo)}, promedio ${formatear(promedio)}, máximo ${formatear(maximo)} centímetros.`
        );
    }

    // Línea vertical y globo con el valor exacto bajo el puntero
    // Línea vertical y globo con el valor exacto de la muestra más cercana al puntero (mouse o dedo).
    function actualizarGuia() {
        globo.hidden = true;
        if (punteroX === null || !escala || !escala.validas.length) {
            return;
        }

        let cercana = null;
        let distancia = Infinity;
        for (const muestra of escala.validas) {
            const separacion = Math.abs(escala.x(muestra[0]) - punteroX);
            if (separacion < distancia) {
                distancia = separacion;
                cercana = muestra;
            }
        }
        if (!cercana || distancia > 40) {
            return;
        }

        const [momento, cm] = cercana;
        const px = escala.x(momento);
        const py = escala.y(cm);
        svg.appendChild(crear("line", { class: "grafico-guia", x1: px, x2: px, y1: MARGEN.arriba, y2: alto - MARGEN.abajo }));
        svg.appendChild(crear("circle", { class: "grafico-punto", cx: px, cy: py, r: 4.5 }));

        const hace = Math.max(0, Math.round(escala.fin - momento));
        globo.textContent = `${formatear(cm)} cm · ${activo ? (hace <= 1 ? "ahora" : `hace ${hace} s`) : `${hace} s antes del final`}`;
        globo.hidden = false;
        const anchoGlobo = globo.offsetWidth;
        globo.style.left = `${Math.min(Math.max(px - anchoGlobo / 2, 0), ancho - anchoGlobo)}px`;
        globo.style.top = `${Math.max(py - 38, 0)}px`;
    }

    // Comunicación con app.py.
    // ---------- datos del servidor ----------

    // Pide a app.py las muestras nuevas y vuelve a dibujar.
    async function consultar() {
        if (consultando) {
            return;
        }
        consultando = true;
        try {
            // GET /api/distancia/historial?desde=<momento>: app.py responde con monitor.muestras_desde(...) (sensor_monitor.py). Se pide solo lo nuevo.
            const respuesta = await fetch(`/api/distancia/historial?desde=${ultimoMomento}`, { cache: "no-store" });
            if (!respuesta.ok) {
                throw new Error("respuesta no válida");
            }
            const datos = await respuesta.json();

            // Si el reloj del servidor retrocedió, se reinició: se empieza de cero.
            // Si el reloj del servidor retrocedió, se reinició: se empieza de cero.
            if (datos.ahora < ultimoMomento) {
                muestras = [];
                ultimoMomento = 0;
            }

            activo = Boolean(datos.sensor_activo);
            ahoraServidor = datos.ahora;
            // Guarda la hora del servidor y cuándo llegó, para poder avanzar el eje entre consultas.
            recibidoEn = performance.now();

            for (const muestra of datos.muestras) {
                muestras.push(muestra);
                ultimoMomento = Math.max(ultimoMomento, muestra[0]);
            }
            // Descarta las muestras demasiado viejas para no acumular memoria.
            const limite = ahoraServidor - VENTANA_S - 10;
            if (activo) {
                muestras = muestras.filter(([momento]) => momento >= limite);
            }
            dibujar();
        } catch (error) {
            // Si una consulta falla, se conserva lo que ya estaba dibujado.
        } finally {
            consultando = false;
            programar();
        }
    }

    // Programa la próxima consulta: cada 0,5 s con el sensor activo, cada 2 s si está detenido, y ninguna si la pestaña está oculta.
    function programar() {
        clearTimeout(temporizador);
        if (!document.hidden) {
            temporizador = setTimeout(consultar, activo ? 500 : 2000);
        }
    }

    // Reacciones al tamaño de la pantalla, al puntero y a la visibilidad de la pestaña.
    // ---------- eventos ----------

    // Cuando cambia el tamaño del contenedor, ajusta el SVG y redibuja.
    new ResizeObserver(([entrada]) => {
        ancho = Math.floor(entrada.contentRect.width);
        alto = Math.floor(entrada.contentRect.height);
        svg.setAttribute("viewBox", `0 0 ${ancho} ${alto}`);
        svg.setAttribute("width", ancho);
        svg.setAttribute("height", alto);
        dibujar();
    }).observe(lienzo);

    // Guarda la posición del puntero para mostrar el globo con el valor.
    svg.addEventListener("pointermove", (evento) => {
        punteroX = evento.clientX - svg.getBoundingClientRect().left;
        dibujar();
    });
    // Al salir el puntero del gráfico, se quita el globo.
    svg.addEventListener("pointerleave", () => {
        punteroX = null;
        dibujar();
    });

    // Pausa las consultas con la pestaña oculta; al volver, consulta de inmediato.
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            clearTimeout(temporizador);
        } else {
            consultar();
        }
    });

    // El eje avanza solo mientras se mide, aunque no lleguen datos nuevos.
    // Cada 250 ms redibuja mientras se mide, para que el eje avance fluido aunque no lleguen datos nuevos.
    setInterval(() => {
        if (!document.hidden && activo) {
            dibujar();
        }
    }, 250);

    // Función pública: fijarReglas(lista, pausadas). La llama automatizaciones.js cada vez que cambian las reglas.
    window.graficoDistancia = {
        fijarReglas(lista, pausadas) {
            reglas = Array.isArray(lista) ? lista : [];
            reglasPausadas = Boolean(pausadas);
            dibujar();
        },
    };

    // Primera consulta al cargar la página.
    consultar();
})();

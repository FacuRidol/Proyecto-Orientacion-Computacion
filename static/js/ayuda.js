// static/js/ayuda.js
// Menú «Ayuda de comandos»: un botón despliega cuatro categorías (LED, Servo,
// Sensor y Generales) y cada una despliega su lista de comandos de voz.
//
// El contenido de las listas lo genera Flask a partir de comandos_ayuda.py;
// este archivo solo muestra y oculta las partes. Se puede usar con el mouse,
// con el teclado (Tab, Enter, Esc) o por voz: voz.js llama a
//     ayudaComandos.abrir("menu" | "leds" | "servo" | "sensor" | "generales")
//     ayudaComandos.cerrar()

(function () {
    const botonAyuda = document.getElementById("boton-ayuda");
    const menu = document.getElementById("menu-ayuda");
    if (!botonAyuda || !menu) {
        return;
    }

    const botonesCategoria = [...menu.querySelectorAll(".boton-categoria")];
    const listas = [...menu.querySelectorAll(".lista-ayuda")];
    const prefiereMenosMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)");

    function buscarLista(categoria) {
        return listas.find((lista) => lista.dataset.categoria === categoria);
    }

    function ocultarListas() {
        for (const lista of listas) {
            lista.hidden = true;
        }
        for (const boton of botonesCategoria) {
            boton.setAttribute("aria-expanded", "false");
        }
    }

    function mostrarMenu(visible) {
        menu.hidden = !visible;
        botonAyuda.setAttribute("aria-expanded", String(visible));
        if (!visible) {
            ocultarListas();
        }
    }

    // Muestra una sola lista a la vez. Devuelve la lista, o null si no existe.
    function mostrarCategoria(categoria) {
        const lista = buscarLista(categoria);
        if (!lista) {
            return null;
        }

        ocultarListas();
        lista.hidden = false;
        const boton = botonesCategoria.find((b) => b.dataset.categoria === categoria);
        if (boton) {
            boton.setAttribute("aria-expanded", "true");
        }
        return lista;
    }

    function alternarCategoria(categoria) {
        const lista = buscarLista(categoria);
        if (lista && !lista.hidden) {
            ocultarListas();
        } else {
            mostrarCategoria(categoria);
        }
    }

    // Si el menú quedó fuera de pantalla (por ejemplo, al abrirlo por voz),
    // lo acerca lo mínimo necesario para que se vea.
    function acercarALaVista(elemento) {
        elemento.scrollIntoView({
            block: "nearest",
            behavior: prefiereMenosMovimiento.matches ? "auto" : "smooth",
        });
    }

    function abrir(categoria = "menu") {
        mostrarMenu(true);
        const lista = categoria === "menu" ? null : mostrarCategoria(categoria);
        acercarALaVista(lista || menu);
    }

    function cerrar() {
        mostrarMenu(false);
    }

    botonAyuda.addEventListener("click", () => mostrarMenu(menu.hidden));

    for (const boton of botonesCategoria) {
        boton.addEventListener("click", () => alternarCategoria(boton.dataset.categoria));
    }

    // Esc cierra la ayuda y devuelve el foco al botón que la abrió.
    menu.addEventListener("keydown", (evento) => {
        if (evento.key === "Escape") {
            cerrar();
            botonAyuda.focus();
        }
    });

    window.ayudaComandos = { abrir, cerrar };
})();

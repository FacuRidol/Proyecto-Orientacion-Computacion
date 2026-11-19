// static/js/ayuda.js
// Menú «Ayuda de comandos»: un botón despliega cuatro categorías (LED, Servo,
// Sensor y Generales) y cada una despliega su lista de comandos de voz.
//
// El contenido de las listas lo genera Flask a partir de comandos_ayuda.py;
// este archivo solo muestra y oculta las partes. Se puede usar con el mouse,
// con el teclado (Tab, Enter, Esc) o por voz: voz.js llama a
//     ayudaComandos.abrir("menu" | "leds" | "servo" | "sensor" | "generales")
//     ayudaComandos.cerrar()

// ┌─────────────────────────────────────────────────────────────────────────┐
// │ DE QUIÉN DEPENDE / QUIÉN LO USA                                         │
// │  - templates/index.html contiene los elementos que este archivo         │
// │    controla: #boton-ayuda, #menu-ayuda, .boton-categoria y .lista-ayuda │
// │    (el contenido de las listas viene de comandos_ayuda.py vía app.py).  │
// │  - static/js/voz.js llama a window.ayudaComandos.abrir()/cerrar() (se   │
// │    definen al final de este archivo) cuando se dice «ayuda».            │
// │  - static/css/estilos.css da el aspecto (el atributo «hidden» oculta).  │
// └─────────────────────────────────────────────────────────────────────────┘
// Función autoejecutable: mantiene las variables privadas.
(function () {
    // Busca en la página el botón que abre la ayuda y el panel del menú.
    const botonAyuda = document.getElementById("boton-ayuda");
    const menu = document.getElementById("menu-ayuda");
    // Si la página no tiene esos elementos, el script no hace nada.
    if (!botonAyuda || !menu) {
        return;
    }

    // Botones de las cuatro categorías (LED, Servo, Sensor, Generales) y sus listas de comandos. La última línea consulta si el usuario pidió «menos movimiento» en su sistema.
    const botonesCategoria = [...menu.querySelectorAll(".boton-categoria")];
    const listas = [...menu.querySelectorAll(".lista-ayuda")];
    const prefiereMenosMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)");

    // Devuelve la lista de comandos de una categoría («leds», «servo»...).
    function buscarLista(categoria) {
        return listas.find((lista) => lista.dataset.categoria === categoria);
    }

    // Oculta todas las listas y marca todos los botones de categoría como «cerrados» (accesibilidad).
    function ocultarListas() {
        for (const lista of listas) {
            lista.hidden = true;
        }
        for (const boton of botonesCategoria) {
            boton.setAttribute("aria-expanded", "false");
        }
    }

    // Muestra u oculta el menú completo. Al cerrarlo también oculta las listas.
    function mostrarMenu(visible) {
        menu.hidden = !visible;
        botonAyuda.setAttribute("aria-expanded", String(visible));
        if (!visible) {
            ocultarListas();
        }
    }

    // Muestra una sola lista a la vez. Devuelve la lista, o null si no existe.
    // Muestra UNA lista (cierra las demás) y marca su botón como abierto. Devuelve la lista, o null si no existe.
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

    // Si la lista está abierta la cierra; si no, la abre (comportamiento del clic en un botón de categoría).
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
    // Si el menú quedó fuera de pantalla (por ejemplo, al abrirlo por voz) hace scroll lo mínimo necesario; sin animación si el usuario prefiere menos movimiento.
    function acercarALaVista(elemento) {
        elemento.scrollIntoView({
            block: "nearest",
            behavior: prefiereMenosMovimiento.matches ? "auto" : "smooth",
        });
    }

    // Función pública: abre el menú y, si se indica, una categoría concreta. La usa voz.js.
    function abrir(categoria = "menu") {
        mostrarMenu(true);
        const lista = categoria === "menu" ? null : mostrarCategoria(categoria);
        acercarALaVista(lista || menu);
    }

    // Función pública: cierra el menú. La usa voz.js con «cerrar ayuda».
    function cerrar() {
        mostrarMenu(false);
    }

    // Clic en «Ayuda de comandos»: muestra el menú si estaba oculto y lo oculta si estaba visible.
    botonAyuda.addEventListener("click", () => mostrarMenu(menu.hidden));

    // Clic en una categoría: alterna su lista.
    for (const boton of botonesCategoria) {
        boton.addEventListener("click", () => alternarCategoria(boton.dataset.categoria));
    }

    // Esc cierra la ayuda y devuelve el foco al botón que la abrió.
    // Teclado: Esc cierra la ayuda y devuelve el foco al botón que la abrió.
    menu.addEventListener("keydown", (evento) => {
        if (evento.key === "Escape") {
            cerrar();
            botonAyuda.focus();
        }
    });

    // Publica las dos funciones para que otros scripts (voz.js) puedan abrir y cerrar la ayuda.
    window.ayudaComandos = { abrir, cerrar };
})();

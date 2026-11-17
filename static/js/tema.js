// static/js/tema.js
// Alterna entre el tema claro y el oscuro y recuerda la elección en el navegador.
//
// Se carga en el <head>, sin "defer", para aplicar el tema antes de dibujar la
// página y evitar un parpadeo. Los nombres de los temas ("claro", "oscuro")
// son los valores de data-tema que se usan en static/css/estilos.css.
//
// Si todavía no se eligió un tema, se usa el del sistema operativo.
//
// Además del botón del encabezado, expone window.temaInterfaz para que otros
// scripts (por ejemplo, los comandos de voz de voz.js) puedan cambiar el tema:
//     temaInterfaz.actual()          -> "claro" | "oscuro"
//     temaInterfaz.aplicar("oscuro") -> aplica ese tema y lo recuerda
//     temaInterfaz.alternar()        -> pasa al otro tema y devuelve el nuevo

// ┌─────────────────────────────────────────────────────────────────────────┐
// │ DE QUIÉN DEPENDE / QUIÉN LO USA                                         │
// │  - templates/index.html lo carga en el <head> y contiene el botón       │
// │    #alternar-tema que este archivo controla.                            │
// │  - static/css/estilos.css define los colores de cada tema según el      │
// │    atributo data-tema que este archivo escribe en <html>.               │
// │  - static/js/voz.js usa window.temaInterfaz (definido acá) para cambiar │
// │    el tema con comandos de voz («tema oscuro»).                         │
// └─────────────────────────────────────────────────────────────────────────┘
// Todo el archivo va dentro de una función que se ejecuta sola (IIFE): así sus variables no se mezclan con las de otros scripts.
(function () {
    // Nombre bajo el cual se guarda el tema elegido en el navegador (localStorage).
    const CLAVE_GUARDADO = "tema-interfaz";
    // Temas válidos; coinciden con los valores de data-tema en estilos.css.
    const TEMAS = ["claro", "oscuro"];
    // Elemento <html>: ahí se escribe el atributo data-tema.
    const raiz = document.documentElement;

    // Lee el tema que la persona eligió en una visita anterior (o null si no hay ninguno válido).
    function leerTemaGuardado() {
        try {
            // localStorage es una memoria pequeña del navegador. Si no se puede leer (modo privado, bloqueado) se ignora el error.
            const tema = localStorage.getItem(CLAVE_GUARDADO);
            return TEMAS.includes(tema) ? tema : null;
        } catch (error) {
            return null;
        }
    }

    // Guarda el tema elegido para recordarlo la próxima vez.
    function guardarTema(tema) {
        try {
            localStorage.setItem(CLAVE_GUARDADO, tema);
        } catch (error) {
            // Si el navegador bloquea el almacenamiento, el tema solo dura esta visita.
        }
    }

    // Si nunca se eligió un tema, se usa el del sistema operativo (modo oscuro o claro).
    function temaDelSistema() {
        const prefiereOscuro = window.matchMedia
            && window.matchMedia("(prefers-color-scheme: dark)").matches;
        return prefiereOscuro ? "oscuro" : "claro";
    }

    // Aplica un tema: escribe data-tema en <html> (el CSS hace el resto) y actualiza la etiqueta de accesibilidad del botón.
    function aplicarTema(tema) {
        raiz.setAttribute("data-tema", tema);

        const boton = document.getElementById("alternar-tema");
        if (boton) {
            boton.setAttribute(
                "aria-label",
                tema === "oscuro" ? "Cambiar a tema claro" : "Cambiar a tema oscuro"
            );
        }
    }

    // Devuelve el tema que está aplicado ahora.
    function temaActual() {
        return raiz.getAttribute("data-tema") === "oscuro" ? "oscuro" : "claro";
    }

    // API pública: aplica un tema válido y lo recuerda; devuelve null si no existe.
    // Cambia al tema indicado y lo guarda; si el nombre no es válido no hace nada.
    function elegirTema(tema) {
        if (!TEMAS.includes(tema)) {
            return null;
        }
        aplicarTema(tema);
        guardarTema(tema);
        return tema;
    }

    // Expone funciones al resto de scripts: temaInterfaz.actual(), .aplicar("oscuro") y .alternar() (las usa voz.js).
    window.temaInterfaz = {
        actual: temaActual,
        aplicar: elegirTema,
        alternar: () => elegirTema(temaActual() === "oscuro" ? "claro" : "oscuro"),
    };

    // Al cargar el script: aplica el tema guardado o el del sistema, antes de dibujar la página (evita un parpadeo).
    aplicarTema(leerTemaGuardado() || temaDelSistema());

    // Cuando la página ya está dibujada, conecta el botón del encabezado.
    document.addEventListener("DOMContentLoaded", () => {
        const boton = document.getElementById("alternar-tema");
        if (!boton) return;

        aplicarTema(temaActual());
        // Al hacer clic en el botón, alterna entre claro y oscuro.
        boton.addEventListener("click", () => window.temaInterfaz.alternar());
    });
})();

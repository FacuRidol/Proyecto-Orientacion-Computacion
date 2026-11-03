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

(function () {
    const CLAVE_GUARDADO = "tema-interfaz";
    const TEMAS = ["claro", "oscuro"];
    const raiz = document.documentElement;

    function leerTemaGuardado() {
        try {
            const tema = localStorage.getItem(CLAVE_GUARDADO);
            return TEMAS.includes(tema) ? tema : null;
        } catch (error) {
            return null;
        }
    }

    function guardarTema(tema) {
        try {
            localStorage.setItem(CLAVE_GUARDADO, tema);
        } catch (error) {
            // Si el navegador bloquea el almacenamiento, el tema solo dura esta visita.
        }
    }

    function temaDelSistema() {
        const prefiereOscuro = window.matchMedia
            && window.matchMedia("(prefers-color-scheme: dark)").matches;
        return prefiereOscuro ? "oscuro" : "claro";
    }

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

    function temaActual() {
        return raiz.getAttribute("data-tema") === "oscuro" ? "oscuro" : "claro";
    }

    // API pública: aplica un tema válido y lo recuerda; devuelve null si no existe.
    function elegirTema(tema) {
        if (!TEMAS.includes(tema)) {
            return null;
        }
        aplicarTema(tema);
        guardarTema(tema);
        return tema;
    }

    window.temaInterfaz = {
        actual: temaActual,
        aplicar: elegirTema,
        alternar: () => elegirTema(temaActual() === "oscuro" ? "claro" : "oscuro"),
    };

    aplicarTema(leerTemaGuardado() || temaDelSistema());

    document.addEventListener("DOMContentLoaded", () => {
        const boton = document.getElementById("alternar-tema");
        if (!boton) return;

        aplicarTema(temaActual());
        boton.addEventListener("click", () => window.temaInterfaz.alternar());
    });
})();

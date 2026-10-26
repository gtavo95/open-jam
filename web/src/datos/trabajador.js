// @ts-check
// Cliente del worker de decodificación: una promesa por ventana pedida.

import { ErrorDatos } from "./errores.js";

/** @typedef {import("../tipos.js").Ventana} Ventana */
/** @typedef {import("../tipos.js").Trayectoria} Trayectoria */

/**
 * @param {{ verificar?: boolean }} [opciones]  verificar: comprobar sha256 cuando el meta lo trae
 */
export function crearDecodificador({ verificar = true } = {}) {
  const worker = new Worker(new URL("./decodificador.worker.js", import.meta.url), { type: "module" });
  /** @type {Map<number, { ok: (t: Trayectoria) => void, mal: (e: Error) => void }>} */
  const pendientes = new Map();
  let siguiente = 0;

  worker.onmessage = ({ data }) => {
    const p = pendientes.get(data.id);
    if (!p) return;
    pendientes.delete(data.id);
    if (data.error) p.mal(ErrorDatos.desde(data.error));
    else p.ok(data.tray);
  };
  worker.onerror = (e) => {
    const err = new ErrorDatos("formato", `falló el worker de decodificación: ${e.message || "error desconocido"}`);
    for (const p of pendientes.values()) p.mal(err);
    pendientes.clear();
  };

  return {
    /**
     * @param {Ventana} ventana
     * @param {string} url  URL absoluta del .bin
     * @returns {Promise<Trayectoria>}
     */
    decodificar(ventana, url) {
      const id = siguiente++;
      return new Promise((ok, mal) => {
        pendientes.set(id, { ok, mal });
        worker.postMessage({
          id,
          url,
          binario: ventana.binario,
          bytes: ventana.bytes,
          sha256: ventana.sha256,
          verificar,
        });
      });
    },
    destruir() {
      worker.terminate();
      pendientes.clear();
    },
  };
}

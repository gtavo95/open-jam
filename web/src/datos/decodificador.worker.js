// @ts-check
// Baja y decodifica una ventana de trayectorias fuera del hilo principal.
// Mensaje de entrada: { id, url, binario, bytes?, sha256?, verificar }.
// Respuesta: { id, tray } (con los buffers transferidos) o { id, error }.

import { decodificar } from "./columnas.js";
import { ErrorDatos, pedir } from "./errores.js";

/** @param {ArrayBuffer} buf */
async function sha256(buf) {
  const h = new Uint8Array(await crypto.subtle.digest("SHA-256", buf));
  return Array.from(h, (b) => b.toString(16).padStart(2, "0")).join("");
}

self.onmessage = async ({ data: { id, url, binario, bytes, sha256: esperado, verificar } }) => {
  try {
    const buf = /** @type {ArrayBuffer} */ (await pedir(url, "binario"));
    if (bytes != null && buf.byteLength !== bytes)
      throw new ErrorDatos("integridad", `${url}: ${buf.byteLength} bytes, el meta dice ${bytes}`, url);
    if (verificar && esperado) {
      if (!crypto?.subtle) console.warn("sin crypto.subtle (contexto no seguro): no se verifica sha256 de", url);
      else if ((await sha256(buf)) !== esperado.toLowerCase())
        throw new ErrorDatos("integridad", `${url}: el sha256 no coincide con el del meta`, url);
    }
    const tray = decodificar(buf, binario);
    // inicio, tipo y v son vistas sobre `buf`; xy y t son buffers nuevos
    self.postMessage({ id, tray }, { transfer: [buf, tray.xy.buffer, tray.t.buffer] });
  } catch (e) {
    const err =
      e instanceof ErrorDatos ? e : new ErrorDatos("formato", `${url}: ${e instanceof Error ? e.message : e}`, url);
    self.postMessage({ id, error: err.plano() });
  }
};

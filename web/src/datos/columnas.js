// @ts-check
// Decodificación del binario de trayectorias. Lógica pura: la usan el worker y los tests.
//
// El primer punto de cada vehículo viene absoluto y los demás como diferencia
// (decímetros para xy, segundos para t). Acá se reconstruyen.

import { ErrorDatos } from "./errores.js";

/** @typedef {import("../tipos.js").IndiceColumnas} IndiceColumnas */
/** @typedef {import("../tipos.js").Trayectoria} Trayectoria */

const TIPOS = { uint32: Uint32Array, uint8: Uint8Array, int32: Int32Array, uint16: Uint16Array, float32: Float32Array };
const NECESARIAS = ["inicio", "tipo", "xy", "t", "v"];

/**
 * Vistas tipadas sobre el buffer según el índice de columnas.
 * @param {ArrayBuffer} buf
 * @param {IndiceColumnas} indice
 * @returns {Record<string, ArrayLike<number> & { length: number }>}
 */
export function columnas(buf, indice) {
  /** @type {Record<string, any>} */
  const col = {};
  for (const k of NECESARIAS)
    if (!indice?.[k]) throw new ErrorDatos("formato", `falta la columna "${k}" en el índice binario`);
  for (const [k, i] of Object.entries(indice)) {
    const Tipo = TIPOS[i.dtype];
    if (!Tipo) throw new ErrorDatos("formato", `columna "${k}": dtype desconocido "${i.dtype}"`);
    if (i.offset % Tipo.BYTES_PER_ELEMENT || i.offset + i.len * Tipo.BYTES_PER_ELEMENT > buf.byteLength)
      throw new ErrorDatos(
        "formato",
        `columna "${k}" fuera del binario (offset ${i.offset}, ${i.len} × ${i.dtype}, ${buf.byteLength} bytes)`,
      );
    col[k] = new Tipo(buf, i.offset, i.len);
  }
  return col;
}

/**
 * @param {ArrayBuffer} buf
 * @param {IndiceColumnas} indice
 * @returns {Trayectoria}
 */
export function decodificar(buf, indice) {
  const col = columnas(buf, indice);
  const inicio = /** @type {Uint32Array} */ (col.inicio);
  const tipo = /** @type {Uint8Array} */ (col.tipo);
  const n = inicio.length - 1;
  const p = col.t.length;
  if (n < 0 || tipo.length !== n || col.xy.length !== 2 * p || col.v.length !== p || inicio[n] !== p)
    throw new ErrorDatos(
      "formato",
      `columnas inconsistentes: ${n} vehículos, ${p} puntos, xy ${col.xy.length}, v ${col.v.length}`,
    );
  const dxy = col.xy,
    dt = col.t;
  const xy = new Float32Array(2 * p);
  const t = new Float32Array(p);
  for (let k = 0; k < n; k++) {
    let x = 0,
      y = 0,
      s = 0;
    const a = inicio[k],
      b = inicio[k + 1];
    if (b < a) throw new ErrorDatos("formato", `inicio decreciente en el vehículo ${k}`);
    for (let j = a; j < b; j++) {
      if (j === a) {
        x = dxy[2 * j];
        y = dxy[2 * j + 1];
        s = dt[j];
      } else {
        x += dxy[2 * j];
        y += dxy[2 * j + 1];
        s += dt[j];
      }
      xy[2 * j] = x / 10;
      xy[2 * j + 1] = y / 10;
      t[j] = s;
    }
  }
  return { n, inicio, tipo, xy, t, v: col.v };
}

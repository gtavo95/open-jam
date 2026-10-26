// @ts-check
// Codificador del binario de trayectorias, espejo de open_jam/export.py. Lo usan el
// generador del fixture y los tests (ida y vuelta con src/datos/columnas.js).

/** @typedef {[number, number, number, number]} Punto  x (m), y (m), t (s), v (km/h) */
/** @typedef {{ tipo: number, puntos: Punto[] }} Vehiculo */

/**
 * Tramo de un vehículo para la ventana [t0, t1]: los puntos dentro, más el último
 * anterior a t0 y el primero posterior a t1, para que la interpolación sea continua.
 * Null si el vehículo no está en la red durante la ventana.
 * @param {Punto[]} puntos  ordenados por t
 * @param {number} t0
 * @param {number} t1
 * @returns {Punto[] | null}
 */
export function recortar(puntos, t0, t1) {
  if (!puntos.length || puntos[puntos.length - 1][2] < t0 || puntos[0][2] > t1) return null;
  let a = 0;
  while (a + 1 < puntos.length && puntos[a + 1][2] <= t0) a++;
  let b = puntos.length - 1;
  while (b - 1 >= 0 && puntos[b - 1][2] >= t1) b--;
  return puntos.slice(a, b + 1);
}

const alinear = (n) => Math.ceil(n / 4) * 4;

/**
 * @param {Vehiculo[]} vehiculos
 * @returns {{ buf: Uint8Array, binario: Record<string, { dtype: string, len: number, offset: number }> }}
 */
export function codificar(vehiculos) {
  const n = vehiculos.length;
  const p = vehiculos.reduce((s, v) => s + v.puntos.length, 0);
  const binario = {};
  let off = 0;
  for (const [k, dtype, len, bytes] of [
    ["inicio", "uint32", n + 1, 4],
    ["tipo", "uint8", n, 1],
    ["xy", "int32", 2 * p, 4],
    ["t", "uint16", p, 2],
    ["v", "uint8", p, 1],
  ]) {
    off = alinear(off);
    binario[k] = { dtype, len, offset: off };
    off += len * bytes;
  }
  const ab = new ArrayBuffer(alinear(off));
  const inicio = new Uint32Array(ab, binario.inicio.offset, n + 1);
  const tipo = new Uint8Array(ab, binario.tipo.offset, n);
  const xy = new Int32Array(ab, binario.xy.offset, 2 * p);
  const t = new Uint16Array(ab, binario.t.offset, p);
  const v = new Uint8Array(ab, binario.v.offset, p);
  let j = 0;
  vehiculos.forEach((veh, k) => {
    inicio[k] = j;
    tipo[k] = veh.tipo;
    let px = 0,
      py = 0,
      pt = 0;
    veh.puntos.forEach(([x, y, s, kmh], q) => {
      // decímetros y segundos enteros; las diferencias se toman sobre los valores ya redondeados
      const dx = Math.round(x * 10),
        dy = Math.round(y * 10),
        ds = Math.round(s);
      xy[2 * j] = q ? dx - px : dx;
      xy[2 * j + 1] = q ? dy - py : dy;
      t[j] = q ? ds - pt : ds;
      v[j] = Math.max(0, Math.min(255, Math.round(kmh)));
      px = dx;
      py = dy;
      pt = ds;
      j++;
    });
  });
  inicio[n] = j;
  return { buf: new Uint8Array(ab), binario };
}

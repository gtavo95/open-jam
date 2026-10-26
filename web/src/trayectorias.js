// @ts-check
// Interpolación de trayectorias: en cada instante, la posición de cada vehículo activo
// entre sus dos puntos vecinos de la trayectoria simplificada. Lógica pura, sin Three.js.

/** @typedef {import("./tipos.js").Trayectoria} Trayectoria */

/**
 * @callback Visita
 * @param {number} k  vehículo
 * @param {number} x
 * @param {number} y
 * @param {number} kmh
 * @param {number} hx  rumbo (sin normalizar)
 * @param {number} hy
 */

/**
 * Recorre los vehículos activos en orden creciente de T con un cursor por vehículo
 * (avanzar es O(1) amortizado; retroceder reinicia los cursores).
 * @param {Trayectoria} tray
 */
export function crearMuestreador(tray) {
  const { n, inicio, xy, t, v } = tray;
  const t0 = new Float32Array(n),
    t1 = new Float32Array(n);
  for (let k = 0; k < n; k++) {
    t0[k] = t[inicio[k]];
    t1[k] = t[inicio[k + 1] - 1];
  }
  const cursor = new Uint32Array(n);
  cursor.set(inicio.subarray(0, n));
  let antes = -Infinity;

  /**
   * @param {number} T
   * @param {Visita} visita
   * @returns {number}  cantidad de vehículos activos
   */
  function recorrer(T, visita) {
    if (T < antes) cursor.set(inicio.subarray(0, n)); // retroceso: se reinician
    antes = T;
    let activos = 0;
    for (let k = 0; k < n; k++) {
      if (T < t0[k] || T > t1[k]) continue;
      let j = cursor[k];
      const fin = inicio[k + 1] - 1;
      while (j < fin - 1 && t[j + 1] <= T) j++;
      cursor[k] = j;
      const a = j,
        b = Math.min(j + 1, fin);
      const dt = t[b] - t[a];
      const f = dt > 0 ? (T - t[a]) / dt : 0;
      const x = xy[2 * a] + (xy[2 * b] - xy[2 * a]) * f;
      const y = xy[2 * a + 1] + (xy[2 * b + 1] - xy[2 * a + 1]) * f;
      const kmh = v[a] + (v[b] - v[a]) * f;
      let hx = xy[2 * b] - xy[2 * a],
        hy = xy[2 * b + 1] - xy[2 * a + 1];
      if (hx === 0 && hy === 0 && j > inicio[k]) {
        hx = xy[2 * a] - xy[2 * a - 2];
        hy = xy[2 * a + 1] - xy[2 * a - 1];
      }
      visita(k, x, y, kmh, hx, hy);
      activos++;
    }
    return activos;
  }

  return { recorrer };
}

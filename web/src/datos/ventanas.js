// @ts-check
// Ventanas de 900 s: cuál corresponde a un instante, cuáles precargar y un cargador que
// las baja bajo demanda (la actual y la siguiente) y suelta las que ya no hacen falta.

/** @typedef {import("../tipos.js").Ventana} Ventana */
/** @typedef {import("../tipos.js").Trayectoria} Trayectoria */

/**
 * Índice de la ventana que contiene T. En el borde exacto (T = t1 de una y t0 de la
 * siguiente) gana la siguiente; antes de la primera o después de la última, la extrema.
 * @param {{ t0: number, t1: number }[]} ventanas  ordenadas por t0
 * @param {number} T
 */
export function indiceVentana(ventanas, T) {
  let lo = 0,
    hi = ventanas.length - 1;
  if (hi < 0) return -1;
  while (lo < hi) {
    const m = (lo + hi + 1) >> 1;
    if (ventanas[m].t0 <= T) lo = m;
    else hi = m - 1;
  }
  return lo;
}

/**
 * Ventanas que conviene tener en memoria en T: la actual y la siguiente (al terminar,
 * la reproducción vuelve al principio, así que después de la última viene la primera).
 * @param {{ t0: number, t1: number }[]} ventanas
 * @param {number} T
 * @returns {number[]}
 */
export function necesarias(ventanas, T) {
  const i = indiceVentana(ventanas, T);
  if (i < 0) return [];
  const sig = (i + 1) % ventanas.length;
  return sig === i ? [i] : [i, sig];
}

/**
 * @param {Ventana[]} ventanas
 * @param {(v: Ventana) => Promise<Trayectoria>} bajar
 * @param {{ retener?: number }} [opciones]  retener: cuántas ventanas guardar como máximo
 */
export function crearCargador(ventanas, bajar, { retener = 3 } = {}) {
  /** @type {Map<number, { tray: Trayectoria | null, error: Error | null, uso: number }>} */
  const cache = new Map();
  let reloj = 0;

  /** @param {number} i */
  function pedirVentana(i) {
    const e = cache.get(i);
    if (e) return e;
    const nueva = {
      tray: /** @type {Trayectoria | null} */ (null),
      error: /** @type {Error | null} */ (null),
      uso: reloj,
    };
    cache.set(i, nueva);
    bajar(ventanas[i]).then(
      (t) => (nueva.tray = t),
      (err) => (nueva.error = err),
    );
    return nueva;
  }

  /** @param {number[]} protegidas */
  function podar(protegidas) {
    if (cache.size <= retener) return;
    const viejas = [...cache.entries()]
      .filter(([i, e]) => !protegidas.includes(i) && (e.tray || e.error))
      .sort((a, b) => a[1].uso - b[1].uso);
    for (const [i] of viejas) {
      if (cache.size <= retener) break;
      cache.delete(i);
    }
  }

  return {
    ventanas,
    /**
     * Lo disponible para T; dispara la carga de la ventana actual y la siguiente.
     * @param {number} T
     * @returns {{ i: number, tray: Trayectoria | null, error: Error | null }}
     */
    en(T) {
      reloj++;
      const ks = necesarias(ventanas, T);
      if (!ks.length) return { i: -1, tray: null, error: null };
      const actual = pedirVentana(ks[0]);
      actual.uso = reloj;
      // la siguiente se pide recién cuando la actual ya está (prioridad a lo que se ve)
      if (actual.tray && ks[1] != null) pedirVentana(ks[1]).uso = reloj;
      podar(ks);
      return { i: ks[0], tray: actual.tray, error: actual.error };
    },
    /** @param {number} T */
    listo(T) {
      return !!cache.get(indiceVentana(ventanas, T))?.tray;
    },
    /** índices en memoria (para depurar y tests) */
    enMemoria() {
      return [...cache.keys()].sort((a, b) => a - b);
    },
    /** olvida un error para reintentar */
    reintentar() {
      for (const [i, e] of cache) if (e.error) cache.delete(i);
    },
  };
}

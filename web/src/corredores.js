// @ts-check
// Estado de los semáforos según las decisiones del agente por corredor y periodo.
// Misma regla que politicas.aplicar_corredores: un semáforo compartido entre corredores
// está encendido si cualquiera de sus corredores (con decisión en el periodo) lo está;
// los que no pertenecen a ningún corredor decidido quedan en `resto`.

/** @typedef {import("./tipos.js").Corredor} Corredor */
/** @typedef {import("./tipos.js").Periodo} Periodo */
/** @typedef {import("./tipos.js").Semaforo} Semaforo */

/**
 * Periodo vigente en T (el último con t0 <= T; antes del primero, el primero).
 * @param {Periodo[]} periodos  ordenados por t0
 * @param {number} T
 * @returns {number}  índice, -1 si no hay periodos
 */
export function indicePeriodo(periodos, T) {
  let k = -1;
  for (let i = 0; i < periodos.length && periodos[i].t0 <= T; i++) k = i;
  return periodos.length ? Math.max(0, k) : -1;
}

/**
 * Para la regla de `resto` cuando el periodo no la trae: con la política fija "off"
 * se apagan todos los semáforos; en cualquier otra los que no se tocan siguen encendidos.
 * @param {Periodo | undefined} periodo
 * @param {string | undefined} politica
 */
export function restoDe(periodo, politica) {
  return periodo?.resto ?? politica !== "off";
}

/**
 * @param {Semaforo[]} semaforos  red.semaforos (el índice es el de la instancia en la escena)
 * @param {Corredor[]} corredores
 * @param {Record<string, boolean>} decisiones  corredor id -> encendido
 * @param {boolean} [resto]  estado de los semáforos sin corredor decidido
 * @returns {Uint8Array}  1 encendido, 0 apagado, por semáforo
 */
export function estadoSemaforos(semaforos, corredores, decisiones, resto = true) {
  const indice = new Map(semaforos.map((s, k) => [s.id, k]));
  const tocado = new Uint8Array(semaforos.length);
  const estado = new Uint8Array(semaforos.length);
  for (const c of corredores) {
    const d = decisiones[c.id];
    if (d === undefined) continue;
    for (const id of c.semaforos) {
      const k = indice.get(id);
      if (k === undefined) continue;
      tocado[k] = 1;
      if (d) estado[k] = 1;
    }
  }
  if (resto) for (let k = 0; k < estado.length; k++) if (!tocado[k]) estado[k] = 1;
  return estado;
}

/**
 * Corredores apagados en un periodo, en el orden de la red.
 * @param {Corredor[]} corredores
 * @param {Record<string, boolean>} decisiones
 * @returns {Corredor[]}
 */
export function apagados(corredores, decisiones) {
  return corredores.filter((c) => decisiones[c.id] === false);
}

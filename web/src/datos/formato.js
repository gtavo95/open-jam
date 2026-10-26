// @ts-check
// Validación y normalización de lo que exporta Python (manifest, red y meta.json de
// cada escenario) al formato que usa el visor.

import { ErrorDatos } from "./errores.js";

/** @typedef {import("../tipos.js").Manifest} Manifest */
/** @typedef {import("../tipos.js").Escenario} Escenario */
/** @typedef {import("../tipos.js").Corredor} Corredor */
/** @typedef {import("../tipos.js").Red} Red */
/** @typedef {import("../tipos.js").Periodo} Periodo */

export const PERIODO_S = 900;

/**
 * @param {any} m
 * @param {string} url
 * @returns {Manifest}
 */
export function validarManifest(m, url) {
  const mal = (/** @type {string} */ que) => new ErrorDatos("formato", `${url}: ${que}`, url);
  if (!m || typeof m !== "object") throw mal("no es un objeto");
  if (m.version !== 1) throw mal(`versión ${m.version} no soportada (se espera 1)`);
  for (const k of ["red", "escena", "terreno"]) if (typeof m[k] !== "string") throw mal(`falta "${k}"`);
  if (!Array.isArray(m.escenarios) || !m.escenarios.length) throw mal("no lista escenarios");
  for (const e of m.escenarios)
    if (typeof e?.id !== "string" || typeof e?.meta !== "string") throw mal("escenario sin id o meta");
  return { ...m, escenarios: m.escenarios.map((/** @type {any} */ e) => ({ ...e, titulo: e.titulo ?? e.id })) };
}

/**
 * corredores: lista {id, nombre, calles, semaforos}.
 * @param {any} red
 * @returns {Red}
 */
export function normalizarRed(red) {
  if (!red || !Array.isArray(red.calles) || !Array.isArray(red.semaforos))
    throw new ErrorDatos("formato", "red.json: faltan calles o semaforos");
  if (red.corredores !== undefined && !Array.isArray(red.corredores))
    throw new ErrorDatos("formato", "red.json: corredores no es una lista");
  /** @type {Corredor[]} */
  const corredores = (red.corredores ?? []).map((/** @type {any} */ x) => ({
    id: String(x.id),
    nombre: x.nombre ?? String(x.id),
    calles: x.calles ?? [],
    semaforos: x.semaforos ?? [],
  }));
  return { ...red, corredores };
}

/**
 * Todos los corredores en el mismo estado durante toda la corrida (políticas fijas).
 * @param {Corredor[]} corredores
 * @param {boolean} encendido
 * @param {number} fin
 * @returns {Periodo[]}
 */
export function periodosFijos(corredores, encendido, fin) {
  const decisiones = Object.fromEntries(corredores.map((c) => [c.id, encendido]));
  const r = [];
  for (let t0 = 0; t0 < fin; t0 += PERIODO_S)
    r.push({ t0, t1: Math.min(fin, t0 + PERIODO_S), decisiones, resto: encendido });
  return r.length ? r : [{ t0: 0, t1: fin, decisiones, resto: encendido }];
}

/**
 * @param {{ id: string, titulo: string }} esc  entrada del manifest
 * @param {any} meta  contenido de <id>/meta.json
 * @param {Corredor[]} corredores
 * @param {string} url
 * @returns {Escenario}
 */
export function normalizarEscenario(esc, meta, corredores, url) {
  const mal = (/** @type {string} */ que) => new ErrorDatos("formato", `${url}: ${que}`, url);
  if (!meta?.metricas) throw mal("faltan las métricas");
  const fin = meta.metricas.fin_s ?? 5400;
  const politica = meta.politica ?? esc.id;
  let ventanas = meta.ventanas;
  if (!Array.isArray(ventanas) || !ventanas.length) throw mal("no hay ventanas de trayectorias");
  for (const v of ventanas)
    if (typeof v.t0 !== "number" || typeof v.t1 !== "number" || typeof v.archivo !== "string" || !v.binario)
      throw mal("ventana sin t0, t1, archivo o binario");
  ventanas = [...ventanas].sort((a, b) => a.t0 - b.t0);

  /** @type {Periodo[]} */
  let periodos = meta.periodos;
  if (!Array.isArray(periodos) || !periodos.length) {
    if (politica !== "on" && politica !== "off") throw mal("faltan los periodos con decisiones del agente");
    periodos = periodosFijos(corredores, politica !== "off", fin);
  } else {
    for (const p of periodos) if (typeof p.t0 !== "number" || !p.decisiones) throw mal("periodo sin t0 o decisiones");
    periodos = [...periodos].sort((a, b) => a.t0 - b.t0);
  }
  return {
    id: esc.id,
    titulo: esc.titulo,
    politica,
    metricas: meta.metricas,
    curva: meta.curva ?? [],
    ventanas,
    periodos,
    fin,
  };
}

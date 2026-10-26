// @ts-check
// Carga lo que exporta Python (open_jam/export.py y open_jam/escena.py) desde la base de
// datos: VITE_DATA_URL (por defecto data/, relativo a la página). En desarrollo se puede
// cambiar con ?datos=<url>, p. ej. ?datos=fixtures/mini/.

import { ErrorDatos, pedir } from "./errores.js";
import { normalizarEscenario, normalizarRed, validarManifest } from "./formato.js";
import { crearCargador } from "./ventanas.js";
import { crearDecodificador } from "./trabajador.js";

/** @typedef {import("../tipos.js").Manifest} Manifest */
/** @typedef {import("../tipos.js").Escenario} Escenario */
/** @typedef {import("../tipos.js").Red} Red */

/** @param {string} b */
const conBarra = (b) => (b.endsWith("/") ? b : `${b}/`);

/** URL absoluta de la base de datos. */
export function baseDatos() {
  const env = import.meta.env;
  const consulta = env.DEV ? new URLSearchParams(location.search).get("datos") : null;
  return new URL(conBarra(consulta || env.VITE_DATA_URL || "data/"), location.href).href;
}

/**
 * @param {string} [base]
 */
export function crearFuente(base = baseDatos()) {
  const url = (/** @type {string} */ rel) => new URL(rel, base).href;
  const decodificador = crearDecodificador({ verificar: import.meta.env.VITE_VERIFICAR_SHA256 !== "0" });
  /** @type {Manifest | null} */
  let manifest = null;
  /** @type {Red | null} */
  let red = null;

  /** manifest.json */
  async function cargarManifest() {
    const u = url("manifest.json");
    manifest = validarManifest(await pedir(u, "json"), u);
    return manifest;
  }

  /** relieve, edificios, zonas y red de calles */
  async function cargarEscena() {
    const m = manifest ?? (await cargarManifest());
    const [meta, terreno, r] = await Promise.all([
      pedir(url(m.escena), "json"),
      pedir(url(m.terreno), "binario"),
      pedir(url(m.red), "json"),
    ]);
    const t = meta.terreno;
    const crudo = new Uint16Array(/** @type {ArrayBuffer} */ (terreno));
    if (!t || crudo.length !== t.filas * t.cols)
      throw new ErrorDatos(
        "formato",
        `${url(m.terreno)}: ${crudo.length} celdas, escena.json dice ${t?.filas}×${t?.cols}`,
      );
    const alto = new Float32Array(crudo.length);
    for (let i = 0; i < crudo.length; i++) alto[i] = crudo[i] / 10;
    red = normalizarRed(r);
    return { ...meta, terreno: { ...t, alto }, red };
  }

  /**
   * Meta de un escenario y su cargador de ventanas.
   * @param {string} id
   */
  async function cargarEscenario(id) {
    const m = manifest ?? (await cargarManifest());
    const esc = m.escenarios.find((e) => e.id === id);
    if (!esc) throw new ErrorDatos("formato", `el manifest no tiene el escenario "${id}"`);
    const u = url(esc.meta);
    const meta = normalizarEscenario(esc, await pedir(u, "json"), red?.corredores ?? [], u);
    const cargador = crearCargador(meta.ventanas, (v) => decodificador.decodificar(v, url(v.archivo)));
    return { meta, cargador };
  }

  return {
    base,
    cargarManifest,
    cargarEscena,
    cargarEscenario,
    /** comando para regenerar lo que falte */
    pista: (/** @type {string} */ id) => `Corré: uv run python -m open_jam.export ${id}`,
    destruir: () => decodificador.destruir(),
  };
}

// El fixture en formato nuevo (pnpm fixture) se decodifica, verifica y es continuo
// en los bordes de ventana: el mismo vehículo está en el mismo lugar visto desde las dos.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { estadoSemaforos } from "../src/corredores.js";
import { decodificar } from "../src/datos/columnas.js";
import { normalizarEscenario, normalizarRed, validarManifest } from "../src/datos/formato.js";
import { crearMuestreador } from "../src/trayectorias.js";

const RAIZ = join(import.meta.dirname, "..", "fixtures", "mini");
const leer = (rel) => readFileSync(join(RAIZ, rel));
const json = (rel) => JSON.parse(leer(rel).toString());

const manifest = validarManifest(json("manifest.json"), "manifest.json");
const red = normalizarRed(json("red.json"));
const escenario = (id) => {
  const e = manifest.escenarios.find((x) => x.id === id);
  return normalizarEscenario(e, json(e.meta), red.corredores, e.meta);
};
const ventana = (v) => {
  const b = leer(v.archivo);
  const buf = b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
  return { buf, tray: decodificar(buf, v.binario) };
};
const posiciones = (tray, T) => {
  const r = [];
  crearMuestreador(tray).recorrer(T, (_k, x, y) => r.push([Math.round(x * 10), Math.round(y * 10)].join(",")));
  return r.sort();
};

describe("fixture mini", () => {
  it("los escenarios salen del manifest", () => {
    expect(manifest.escenarios.map((e) => e.id)).toEqual(["on", "off", "agente"]);
  });

  it("cada ventana coincide en bytes y sha256 con el meta", () => {
    for (const v of escenario("agente").ventanas) {
      const { buf } = ventana(v);
      expect(buf.byteLength).toBe(v.bytes);
      expect(createHash("sha256").update(new Uint8Array(buf)).digest("hex")).toBe(v.sha256);
    }
  });

  it("es continuo en el borde entre ventanas", () => {
    const vs = escenario("on").ventanas;
    for (let i = 0; i + 1 < vs.length; i++) {
      const T = vs[i].t1;
      const a = posiciones(ventana(vs[i]).tray, T),
        b = posiciones(ventana(vs[i + 1]).tray, T);
      expect(a.length).toBeGreaterThan(0);
      expect(b).toEqual(a);
    }
  });

  it("el agente apaga Reforma en el segundo periodo y el cruce compartido sigue encendido", () => {
    const p = escenario("agente").periodos[1];
    expect(p.decisiones).toEqual({ reforma: false, bolivar: true });
    const e = estadoSemaforos(red.semaforos, red.corredores, p.decisiones, true);
    expect(Object.fromEntries(red.semaforos.map((s, k) => [s.id, e[k]]))).toEqual({
      cruce: 1,
      ref_oeste: 0,
      bol_sur: 1,
      suelto: 1,
    });
  });
});

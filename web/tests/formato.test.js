import { describe, expect, it } from "vitest";
import { normalizarEscenario, normalizarRed, periodosFijos, validarManifest } from "../src/datos/formato.js";

const metricas = { fin_s: 1800, periodos: [] };

describe("normalizarRed", () => {
  it("respeta la lista de corredores", () => {
    const c = [{ id: "reforma", nombre: "Avenida La Reforma", calles: [0], semaforos: ["a"] }];
    expect(normalizarRed({ calles: [], semaforos: [], corredores: c }).corredores).toEqual(c);
  });
  it("rechaza corredores que no son una lista", () => {
    expect(() => normalizarRed({ calles: [], semaforos: [], corredores: { a: [1] } })).toThrow(/lista/);
  });
});

describe("validarManifest", () => {
  it("rechaza versiones desconocidas y escenarios incompletos", () => {
    const m = { version: 1, red: "r", escena: "e", terreno: "t", escenarios: [{ id: "on", meta: "on/meta.json" }] };
    expect(validarManifest(m, "m").escenarios[0].titulo).toBe("on");
    expect(() => validarManifest({ ...m, version: 3 }, "m")).toThrow(/versión 3/);
    expect(() => validarManifest({ ...m, escenarios: [{ id: "x" }] }, "m")).toThrow(/meta/);
  });
});

describe("normalizarEscenario", () => {
  const corr = [{ id: "a", nombre: "A", calles: [], semaforos: [] }];
  const meta = {
    metricas,
    ventanas: [
      { t0: 900, t1: 1800, archivo: "b", binario: {} },
      { t0: 0, t1: 900, archivo: "a", binario: {} },
    ],
  };
  it("ordena las ventanas y, sin periodos, usa periodos fijos según la política", () => {
    const e = normalizarEscenario({ id: "off", titulo: "Off" }, { ...meta, politica: "off" }, corr, "u");
    expect(e.ventanas.map((v) => v.archivo)).toEqual(["a", "b"]);
    expect(e.periodos).toHaveLength(2);
    expect(e.periodos[1]).toMatchObject({ t0: 900, decisiones: { a: false }, resto: false });
  });
  it("exige ventanas y, para un agente, periodos", () => {
    expect(() => normalizarEscenario({ id: "agente", titulo: "" }, meta, corr, "u")).toThrow(/periodos/);
    expect(() => normalizarEscenario({ id: "on", titulo: "" }, { metricas }, corr, "u")).toThrow(/ventanas/);
  });
  it("periodosFijos cubre toda la corrida", () => {
    expect(periodosFijos(corr, true, 2000).map((p) => [p.t0, p.t1])).toEqual([
      [0, 900],
      [900, 1800],
      [1800, 2000],
    ]);
  });
});

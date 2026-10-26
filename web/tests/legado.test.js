import { describe, expect, it } from "vitest";
import { normalizarEscenario, normalizarRed, periodosFijos, validarManifest } from "../src/datos/legado.js";

const metricas = { fin_s: 1800, periodos: [] };

describe("normalizarRed", () => {
  it("convierte el diccionario viejo de corredores a la lista nueva", () => {
    const r = normalizarRed({ calles: [], semaforos: [], corredores: { "Avenida Reforma": [1, 2] } });
    expect(r.corredores).toEqual([{ id: "Avenida Reforma", nombre: "Avenida Reforma", calles: [1, 2], semaforos: [] }]);
  });
  it("respeta la lista nueva", () => {
    const c = [{ id: "reforma", nombre: "Avenida La Reforma", calles: [0], semaforos: ["a"] }];
    expect(normalizarRed({ calles: [], semaforos: [], corredores: c }).corredores).toEqual(c);
  });
});

describe("validarManifest", () => {
  it("rechaza versiones desconocidas y escenarios incompletos", () => {
    const m = { version: 2, red: "r", escena: "e", terreno: "t", escenarios: [{ id: "on", meta: "on/meta.json" }] };
    expect(validarManifest(m, "m").escenarios[0].titulo).toBe("on");
    expect(() => validarManifest({ ...m, version: 3 }, "m")).toThrow(/versión 3/);
    expect(() => validarManifest({ ...m, escenarios: [{ id: "x" }] }, "m")).toThrow(/meta/);
  });
});

describe("normalizarEscenario", () => {
  const corr = [{ id: "a", nombre: "A", calles: [], semaforos: [] }];
  it("formato viejo: una sola ventana y periodos fijos según la política", () => {
    const e = normalizarEscenario(
      { id: "off", titulo: "Off" },
      { politica: "off", metricas, binario: { x: 1 } },
      corr,
      {
        legado: true,
        url: "off.json",
      },
    );
    expect(e.ventanas).toEqual([{ t0: 0, t1: 1800, archivo: "off.bin", binario: { x: 1 } }]);
    expect(e.periodos).toHaveLength(2);
    expect(e.periodos[1]).toMatchObject({ t0: 900, decisiones: { a: false }, resto: false });
  });
  it("formato nuevo: exige ventanas y, para un agente, periodos", () => {
    const meta = {
      metricas,
      ventanas: [
        { t0: 900, t1: 1800, archivo: "b", binario: {} },
        { t0: 0, t1: 900, archivo: "a", binario: {} },
      ],
    };
    const e = normalizarEscenario({ id: "on", titulo: "On" }, meta, corr, { legado: false, url: "u" });
    expect(e.ventanas.map((v) => v.archivo)).toEqual(["a", "b"]);
    expect(() => normalizarEscenario({ id: "agente", titulo: "" }, meta, corr, { legado: false, url: "u" })).toThrow(
      /periodos/,
    );
    expect(() =>
      normalizarEscenario({ id: "on", titulo: "" }, { metricas }, corr, { legado: false, url: "u" }),
    ).toThrow(/ventanas/);
  });
  it("periodosFijos cubre toda la corrida", () => {
    expect(periodosFijos(corr, true, 2000).map((p) => [p.t0, p.t1])).toEqual([
      [0, 900],
      [900, 1800],
      [1800, 2000],
    ]);
  });
});

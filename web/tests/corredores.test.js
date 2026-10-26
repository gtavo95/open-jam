import { describe, expect, it } from "vitest";
import { apagados, estadoSemaforos, indicePeriodo, restoDe } from "../src/corredores.js";

const semaforos = ["cruce", "ref", "bol", "suelto"].map((id) => ({ id, x: 0, y: 0, n: id }));
const corredores = [
  { id: "reforma", nombre: "Avenida La Reforma", calles: [], semaforos: ["cruce", "ref"] },
  { id: "bolivar", nombre: "Avenida Bolívar", calles: [], semaforos: ["cruce", "bol", "no-existe"] },
];
const estado = (d, resto) => Array.from(estadoSemaforos(semaforos, corredores, d, resto));

describe("estadoSemaforos", () => {
  it("un semáforo compartido sigue encendido si cualquiera de sus corredores lo está", () => {
    expect(estado({ reforma: false, bolivar: true })).toEqual([1, 0, 1, 1]);
    expect(estado({ reforma: true, bolivar: false })).toEqual([1, 1, 0, 1]);
  });
  it("se apaga solo si todos sus corredores lo apagan", () => {
    expect(estado({ reforma: false, bolivar: false })).toEqual([0, 0, 0, 1]);
  });
  it("los semáforos sin corredor decidido quedan en `resto`", () => {
    expect(estado({ reforma: false, bolivar: false }, false)).toEqual([0, 0, 0, 0]);
    expect(estado({ reforma: false }, true)).toEqual([0, 0, 1, 1]); // bolívar sin decisión: no lo toca
    expect(estado({}, true)).toEqual([1, 1, 1, 1]);
  });
});

describe("periodos", () => {
  const P = [0, 900, 1800].map((t0) => ({ t0, t1: t0 + 900, decisiones: {} }));
  it("indicePeriodo", () => {
    expect(indicePeriodo(P, 0)).toBe(0);
    expect(indicePeriodo(P, 1799)).toBe(1);
    expect(indicePeriodo(P, 5000)).toBe(2);
    expect(indicePeriodo(P, -1)).toBe(0);
    expect(indicePeriodo([], 10)).toBe(-1);
  });
  it("restoDe: explícito o según la política", () => {
    expect(restoDe({ ...P[0], resto: false }, "agente")).toBe(false);
    expect(restoDe(P[0], "off")).toBe(false);
    expect(restoDe(P[0], "agente")).toBe(true);
  });
  it("apagados", () => {
    expect(apagados(corredores, { reforma: false, bolivar: true }).map((c) => c.id)).toEqual(["reforma"]);
  });
});

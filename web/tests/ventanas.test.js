import { describe, expect, it } from "vitest";
import { crearCargador, indiceVentana, necesarias } from "../src/datos/ventanas.js";

const V = [0, 900, 1800, 2700].map((t0) => ({ t0, t1: t0 + 900, archivo: `on/${t0}.bin`, binario: {} }));
const esperar = () => new Promise((r) => setTimeout(r, 0));

describe("indiceVentana", () => {
  it("elige la ventana que contiene T; en el borde, la siguiente", () => {
    expect(indiceVentana(V, 0)).toBe(0);
    expect(indiceVentana(V, 899.9)).toBe(0);
    expect(indiceVentana(V, 900)).toBe(1);
    expect(indiceVentana(V, 3599)).toBe(3);
  });
  it("fuera de rango usa la extrema", () => {
    expect(indiceVentana(V, -5)).toBe(0);
    expect(indiceVentana(V, 99999)).toBe(3);
    expect(indiceVentana([], 10)).toBe(-1);
  });
});

describe("necesarias", () => {
  it("la actual y la siguiente; después de la última, la primera", () => {
    expect(necesarias(V, 100)).toEqual([0, 1]);
    expect(necesarias(V, 3000)).toEqual([3, 0]);
    expect(necesarias(V.slice(0, 1), 100)).toEqual([0]);
  });
});

describe("crearCargador", () => {
  it("baja la actual, después precarga la siguiente y retiene a lo sumo `retener`", async () => {
    const pedidas = [];
    const c = crearCargador(V, async (v) => (pedidas.push(v.t0), { n: 0, desde: v.t0 }), { retener: 2 });
    expect(c.en(100).tray).toBeNull();
    expect(pedidas).toEqual([0]);
    await esperar();
    expect(c.en(100).tray).toEqual({ n: 0, desde: 0 });
    expect(pedidas).toEqual([0, 900]);
    await esperar();
    expect(c.listo(950)).toBe(true);
    c.en(1000);
    await esperar();
    c.en(1000);
    expect(pedidas).toEqual([0, 900, 1800]);
    expect(c.enMemoria()).toEqual([1, 2]);
  });

  it("guarda el error de una ventana y permite reintentar", async () => {
    let falla = true;
    const c = crearCargador(V, async () => {
      if (falla) throw new Error("404");
      return { n: 1 };
    });
    c.en(0);
    await esperar();
    expect(c.en(0).error?.message).toBe("404");
    falla = false;
    c.reintentar();
    c.en(0);
    await esperar();
    expect(c.en(0).tray).toEqual({ n: 1 });
  });
});

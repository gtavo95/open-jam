import { describe, expect, it } from "vitest";
import { codificar } from "../scripts/codificar.js";
import { decodificar } from "../src/datos/columnas.js";
import { crearMuestreador } from "../src/trayectorias.js";

const tray = (vehiculos) => {
  const { buf, binario } = codificar(vehiculos);
  return decodificar(buf.buffer, binario);
};
const foto = (m, T) => {
  const r = {};
  m.recorrer(T, (k, x, y, kmh, hx, hy) => (r[k] = { x, y, kmh, rumbo: Math.atan2(hy, hx) }));
  return r;
};

describe("crearMuestreador", () => {
  const t = tray([
    {
      tipo: 0,
      puntos: [
        [0, 0, 10, 0],
        [100, 0, 20, 40],
        [100, 50, 30, 20],
      ],
    },
    {
      tipo: 1,
      puntos: [
        [500, 500, 25, 10],
        [500, 500, 35, 0],
      ],
    },
  ]);

  it("interpola posición y velocidad entre los puntos vecinos", () => {
    const m = crearMuestreador(t);
    expect(foto(m, 15)[0]).toMatchObject({ x: 50, y: 0, kmh: 20 });
    expect(foto(m, 25)[0]).toMatchObject({ x: 100, y: 25, kmh: 30 });
    expect(foto(m, 30)[0]).toMatchObject({ x: 100, y: 50, kmh: 20 });
  });

  it("solo recorre los vehículos activos", () => {
    const m = crearMuestreador(t);
    expect(Object.keys(foto(m, 5))).toEqual([]);
    expect(Object.keys(foto(m, 27)).map(Number)).toEqual([0, 1]);
    expect(Object.keys(foto(m, 31)).map(Number)).toEqual([1]);
    expect(m.recorrer(40, () => {})).toBe(0);
  });

  it("da el mismo resultado al retroceder que al ir hacia adelante", () => {
    const m = crearMuestreador(t);
    const adelante = foto(m, 12);
    foto(m, 29);
    expect(foto(m, 12)).toEqual(adelante);
    expect(foto(crearMuestreador(t), 12)).toEqual(adelante);
  });

  it("detenido: conserva el rumbo del tramo anterior", () => {
    const m = crearMuestreador(
      tray([
        {
          tipo: 0,
          puntos: [
            [0, 0, 0, 30],
            [0, 10, 10, 0],
            [0, 10, 20, 0],
          ],
        },
      ]),
    );
    expect(foto(m, 15)[0].rumbo).toBeCloseTo(Math.PI / 2);
  });
});

import { describe, expect, it } from "vitest";
import { codificar } from "../scripts/codificar.js";
import { columnas, decodificar } from "../src/datos/columnas.js";
import { ErrorDatos } from "../src/datos/errores.js";

const vehiculos = [
  {
    tipo: 0,
    puntos: [
      [100.25, 200.5, 10, 30],
      [101.5, 199.9, 12, 32],
      [103, 198, 15, 0],
    ],
  },
  { tipo: 2, puntos: [[5000, 7000.1, 600, 50]] },
  {
    tipo: 1,
    puntos: [
      [0, 0, 0, 0],
      [-3.3, 4.4, 2, 10],
    ],
  },
];

describe("decodificar", () => {
  it("reconstruye posiciones absolutas desde las diferencias por vehículo", () => {
    const { buf, binario } = codificar(vehiculos);
    const d = decodificar(buf.buffer, binario);
    expect(d.n).toBe(3);
    expect(Array.from(d.inicio)).toEqual([0, 3, 4, 6]);
    expect(Array.from(d.tipo)).toEqual([0, 2, 1]);
    const puntos = vehiculos.flatMap((v) => v.puntos);
    puntos.forEach(([x, y, t, v], j) => {
      expect(d.xy[2 * j]).toBeCloseTo(Math.round(x * 10) / 10, 3);
      expect(d.xy[2 * j + 1]).toBeCloseTo(Math.round(y * 10) / 10, 3);
      expect(d.t[j]).toBe(t);
      expect(d.v[j]).toBe(v);
    });
  });

  it("no arrastra la diferencia de un vehículo al siguiente", () => {
    const { buf, binario } = codificar(vehiculos);
    const d = decodificar(buf.buffer, binario);
    expect(d.xy[2 * 3]).toBeCloseTo(5000, 4); // primer punto del vehículo 1: absoluto
    expect(d.t[4]).toBe(0);
  });

  it("acepta una ventana sin vehículos", () => {
    const { buf, binario } = codificar([]);
    const d = decodificar(buf.buffer, binario);
    expect(d.n).toBe(0);
    expect(d.t.length).toBe(0);
  });

  it("rechaza índices que no cierran con el binario", () => {
    const { buf, binario } = codificar(vehiculos);
    expect(() => decodificar(buf.buffer, { ...binario, v: { ...binario.v, len: 2 } })).toThrow(ErrorDatos);
    expect(() => columnas(buf.buffer, { ...binario, xy: { ...binario.xy, dtype: "int64" } })).toThrow(/dtype/);
    expect(() => columnas(buf.buffer, { ...binario, t: { ...binario.t, offset: buf.byteLength } })).toThrow(/fuera/);
    const { t: _t, ...sinT } = binario;
    expect(() => columnas(buf.buffer, sinT)).toThrow(/"t"/);
  });
});

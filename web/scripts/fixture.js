// Genera fixtures/mini/: un juego de datos chico en el formato nuevo (manifest v2,
// ventanas de 900 s, decisiones por corredor) para los tests y para probar el visor sin
// correr la simulación:  pnpm fixture  y después  http://localhost:5180/?datos=fixtures/mini/
//
// Red: 800 × 600 m con dos corredores que se cruzan (Reforma, horizontal; Bolívar,
// vertical), cuatro semáforos (uno compartido, uno sin corredor) y tres escenarios:
// on, off y un agente que apaga Reforma en el segundo periodo y todo en el tercero.

import { createHash } from "node:crypto";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { codificar, recortar } from "./codificar.js";
import { crearMuestreador } from "../src/trayectorias.js";
import { decodificar } from "../src/datos/columnas.js";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..", "fixtures", "mini");
const FIN = 2700,
  PERIODO = 900;
const FILAS = 31,
  COLS = 41,
  PASO = 20;

const escribir = (rel, datos) => {
  const p = join(RAIZ, rel);
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, typeof datos === "string" || datos instanceof Uint8Array ? datos : JSON.stringify(datos));
};

// relieve: una loma suave al noreste (decímetros sobre el nivel del mar)
const alto = new Uint16Array(FILAS * COLS);
for (let i = 0; i < FILAS; i++)
  for (let j = 0; j < COLS; j++)
    alto[i * COLS + j] = 15000 + Math.round(120 * Math.exp(-((i - 22) ** 2 + (j - 30) ** 2) / 60));

const caja = (x, y, w, h) => [x, y, x + w, y, x + w, y + h, x, y + h, x, y];
const escena = {
  terreno: { filas: FILAS, cols: COLS, paso_m: PASO, base_m: 1500, x0: 0, y0: 0 },
  edificios: [
    [caja(100, 330, 60, 40), 12],
    [caja(440, 330, 50, 50), 45],
    [caja(250, 200, 40, 70), 8],
    [caja(500, 180, 70, 60), 20],
  ],
  zonas: [
    { n: "Zona 10", centro: [600, 300], anillos: [[400, 0, 800, 0, 800, 600, 400, 600]] },
    { n: "Zona 9", centro: [200, 300], anillos: [[0, 0, 400, 0, 400, 600, 0, 600]] },
  ],
  atribucion: "fixture sintético",
};

const linea = (x0, y0, x1, y1, pasos = 8) =>
  Array.from({ length: pasos + 1 }, (_, k) => [x0 + ((x1 - x0) * k) / pasos, y0 + ((y1 - y0) * k) / pasos]).flat();
const red = {
  origen: [-90.5, 14.6],
  bbox: [0, 0, 800, 600],
  calles: [
    { id: "r1", p: linea(0, 300, 400, 300), l: 3, n: "Avenida La Reforma", w: 10, k: 0 },
    { id: "r2", p: linea(400, 300, 800, 300), l: 3, n: "Avenida La Reforma", w: 10, k: 0 },
    { id: "b1", p: linea(400, 0, 400, 300), l: 2, n: "Avenida Bolívar", w: 7, k: 1 },
    { id: "b2", p: linea(400, 300, 400, 600), l: 2, n: "Avenida Bolívar", w: 7, k: 1 },
    { id: "c1", p: linea(600, 300, 600, 600, 4), l: 1, n: "6a Calle", w: 3.2, k: 3 },
  ],
  semaforos: [
    { id: "cruce", x: 400, y: 300, n: "Reforma y Bolívar" },
    { id: "ref_oeste", x: 200, y: 300, n: "Reforma y 2a Calle" },
    { id: "bol_sur", x: 400, y: 150, n: "Bolívar y 8a Calle" },
    { id: "suelto", x: 600, y: 450, n: "6a Calle" },
  ],
  corredores: [
    { id: "reforma", nombre: "Avenida La Reforma", calles: [0, 1], semaforos: ["cruce", "ref_oeste"] },
    { id: "bolivar", nombre: "Avenida Bolívar", calles: [2, 3], semaforos: ["cruce", "bol_sur"] },
  ],
};

// vehículos de ida y vuelta por un corredor, con una parada en el cruce; deterministas
let semilla = 11;
const azar = () => (semilla = (semilla * 16807) % 2147483647) / 2147483647;
const vehiculos = Array.from({ length: 60 }, (_, k) => {
  const horizontal = k % 2 === 0;
  const sale = Math.round(azar() * (FIN - 200));
  const dura = 300 + Math.round(azar() * 900);
  const puntos = [];
  for (let s = 0; s <= dura; s += 10) {
    const fase = ((s / 200) % 2) - 1; // -1..1: ida y vuelta
    const u = Math.abs(fase) * 800;
    const parado = Math.abs(u - 400) < 30 && azar() < 0.6;
    const pos = horizontal ? [u, 300 - 2] : [400 + 2, u * 0.75];
    puntos.push([pos[0], pos[1], Math.min(FIN, sale + s), parado ? 0 : 20 + Math.round(azar() * 30)]);
  }
  return { tipo: [0, 0, 0, 1, 2, 3][k % 6], puntos: puntos.filter((p, q) => q === 0 || p[2] > puntos[q - 1][2]) };
});

// curva por minuto calculada sobre los vehículos completos
const todo = codificar(vehiculos);
const tray = decodificar(todo.buf.buffer, todo.binario);
const m = crearMuestreador(tray);
const curva = [];
for (let t = 0; t <= FIN; t += 60) {
  let n = 0,
    kmh = 0,
    parados = 0;
  m.recorrer(t, (_k, _x, _y, v) => {
    n++;
    kmh += v;
    if (v < 5) parados++;
  });
  curva.push({
    t,
    n,
    kmh: n ? Math.round((kmh / n) * 10) / 10 : 0,
    parados: n ? Math.round((parados / n) * 1000) / 1000 : 0,
  });
}

const ventanas = (id) =>
  Array.from({ length: FIN / PERIODO }, (_, w) => {
    const t0 = w * PERIODO,
      t1 = t0 + PERIODO;
    const tramos = vehiculos.map((v) => ({ tipo: v.tipo, puntos: recortar(v.puntos, t0, t1) })).filter((v) => v.puntos);
    const { buf, binario } = codificar(tramos);
    const archivo = `${id}/${String(w).padStart(4, "0")}.bin`;
    escribir(archivo, buf);
    return { t0, t1, archivo, bytes: buf.byteLength, sha256: createHash("sha256").update(buf).digest("hex"), binario };
  });

const ESCENARIOS = {
  on: { titulo: "Semáforos encendidos", decide: () => ({ reforma: true, bolivar: true }) },
  off: { titulo: "Semáforos apagados", decide: () => ({ reforma: false, bolivar: false }) },
  agente: { titulo: "Agente", decide: (w) => ({ reforma: w === 0, bolivar: w < 2 }) },
};

rmSync(RAIZ, { recursive: true, force: true });
escribir("escena.json", escena);
escribir("terreno.bin", new Uint8Array(alto.buffer));
escribir("red.json", red);
escribir("manifest.json", {
  version: 2,
  red: "red.json",
  escena: "escena.json",
  terreno: "terreno.bin",
  escenarios: Object.entries(ESCENARIOS).map(([id, e]) => ({ id, titulo: e.titulo, meta: `${id}/meta.json` })),
});
for (const [id, e] of Object.entries(ESCENARIOS)) {
  const periodos = Array.from({ length: FIN / PERIODO }, (_, w) => ({
    t0: w * PERIODO,
    t1: (w + 1) * PERIODO,
    decisiones: e.decide(w),
  }));
  const fl = (w, c) => Math.round((0.4 + 0.5 * Math.abs(Math.sin(w * 1.7 + c + id.length))) * 1000) / 1000;
  escribir(`${id}/meta.json`, {
    escenario: id,
    politica: id,
    muestreo_s: 10,
    tolerancia_m: 1.5,
    metricas: {
      escenario: id,
      fin_s: FIN,
      insertados: vehiculos.length,
      llegaron: 40,
      teleports: 0,
      demora_prom_s: 240,
      fluidez: 0.7,
      parado_h: 3.2,
      periodos: periodos.map((p, w) => ({
        t: p.t0,
        red: { parado_h: 1.1, fluidez: fl(w, 0) },
        corredores: {
          "Avenida La Reforma": { parado_h: 0.4, fluidez: fl(w, 1) },
          "Avenida Bolívar": { parado_h: 0.3, fluidez: fl(w, 2) },
        },
      })),
    },
    curva,
    vehiculos: vehiculos.length,
    ventanas: ventanas(id),
    periodos,
  });
}
console.log(`fixture en ${RAIZ}`);

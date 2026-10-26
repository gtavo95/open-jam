// Relieve: altura interpolada, pendiente, densidad urbana, la malla del suelo coloreada
// y el bosque de los barrancos.

import * as THREE from "three";
import { colorZona } from "./zonas.js";

/**
 * @typedef {object} Grilla
 * @property {number} filas
 * @property {number} cols
 * @property {number} paso_m
 * @property {number} x0
 * @property {number} y0
 * @property {Float32Array} alto  metros, fila 0 = sur
 */

const EXAGERA = 1.4; // relieve un poco exagerado: los barrancos se leen mejor

/**
 * Altura del suelo (m, ya exagerada) en coordenadas de la red, bilineal.
 * @param {Grilla} tr
 * @returns {(x: number, y: number) => number}
 */
export function crearAltura(tr) {
  return (x, y) => {
    const fx = (x - tr.x0) / tr.paso_m,
      fy = (y - tr.y0) / tr.paso_m;
    const j = Math.max(0, Math.min(tr.cols - 2, Math.floor(fx)));
    const i = Math.max(0, Math.min(tr.filas - 2, Math.floor(fy)));
    const u = Math.min(1, Math.max(0, fx - j)),
      v = Math.min(1, Math.max(0, fy - i));
    const a = tr.alto,
      c = tr.cols;
    return (
      EXAGERA *
      (a[i * c + j] * (1 - u) * (1 - v) +
        a[i * c + j + 1] * u * (1 - v) +
        a[(i + 1) * c + j] * (1 - u) * v +
        a[(i + 1) * c + j + 1] * u * v)
    );
  };
}

/**
 * Pendiente (m/m) por celda, para colorear y para poner bosque en los barrancos.
 * @param {Grilla} tr
 */
export function pendientes(tr) {
  const { filas, cols, paso_m, alto } = tr;
  const p = new Float32Array(filas * cols);
  for (let i = 1; i < filas - 1; i++)
    for (let j = 1; j < cols - 1; j++) {
      const dx = (alto[i * cols + j + 1] - alto[i * cols + j - 1]) / (2 * paso_m);
      const dy = (alto[(i + 1) * cols + j] - alto[(i - 1) * cols + j]) / (2 * paso_m);
      p[i * cols + j] = Math.hypot(dx, dy);
    }
  return p;
}

/**
 * 0..1: qué tan construida está cada celda (edificios cerca), suavizado.
 * @param {Grilla} tr
 * @param {[number[], number][]} lista  edificios: [polígono, altura]
 */
export function densidadUrbana(tr, lista) {
  const { filas, cols, paso_m, x0, y0 } = tr;
  let d = new Float32Array(filas * cols);
  for (const [p] of lista)
    for (let k = 0; k < p.length; k += 2) {
      const j = Math.round((p[k] - x0) / paso_m),
        i = Math.round((p[k + 1] - y0) / paso_m);
      if (i >= 0 && i < filas && j >= 0 && j < cols) d[i * cols + j] = 1;
    }
  // dos pasadas de caja (radio 4 celdas = 80 m) por filas y por columnas
  const r = 4;
  for (let pasada = 0; pasada < 2; pasada++) {
    const o = new Float32Array(d.length);
    for (let i = 0; i < filas; i++) {
      let s = 0;
      for (let j = -r; j < cols + r; j++) {
        if (j + r < cols) s += d[i * cols + j + r];
        if (j - r - 1 >= 0) s -= d[i * cols + j - r - 1];
        if (j >= 0 && j < cols) o[i * cols + j] = s / (2 * r + 1);
      }
    }
    const q = new Float32Array(d.length);
    for (let j = 0; j < cols; j++) {
      let s = 0;
      for (let i = -r; i < filas + r; i++) {
        if (i + r < filas) s += o[(i + r) * cols + j];
        if (i - r - 1 >= 0) s -= o[(i - r - 1) * cols + j];
        if (i >= 0 && i < filas) q[i * cols + j] = s / (2 * r + 1);
      }
    }
    d = q;
  }
  for (let k = 0; k < d.length; k++) d[k] = Math.min(1, d[k] * 6);
  return d;
}

function muestra(a) {
  const r = [];
  for (let i = 0; i < a.length; i += 97) r.push(a[i]);
  return r;
}

/**
 * Malla del suelo con color por altura, pendiente y ciudad; `marcar` tiñe las zonas elegidas.
 * @param {Grilla} tr
 * @param {(x: number, y: number) => number} altura
 * @param {Float32Array} pendiente
 * @param {Float32Array} urbano
 * @param {Uint8Array} malla  zona (+1) de cada celda
 * @param {number} nz
 */
export function terreno(tr, altura, pendiente, urbano, malla, nz) {
  const { filas, cols, paso_m, x0, y0 } = tr;
  const g = new THREE.PlaneGeometry((cols - 1) * paso_m, (filas - 1) * paso_m, cols - 1, filas - 1);
  g.rotateX(-Math.PI / 2);
  const pos = g.attributes.position;
  const color = new Float32Array(pos.count * 3);
  const zona = new Float32Array(pos.count);
  const m0 = muestra(tr.alto);
  const min = Math.min(...m0),
    max = Math.max(...m0);
  const bajo = new THREE.Color("#a7a77c"),
    alto = new THREE.Color("#d8ccad"),
    ciudad = new THREE.Color("#ddd6c8"),
    bosque = new THREE.Color("#5f7a45"),
    cumbre = new THREE.Color("#7f8b5c");
  const c = new THREE.Color();
  for (let k = 0; k < pos.count; k++) {
    // PlaneGeometry va de arriba (norte) hacia abajo; la fila 0 del terreno es el sur
    const j = k % cols,
      i = filas - 1 - Math.floor(k / cols);
    const x = x0 + j * paso_m,
      y = y0 + i * paso_m;
    pos.setXYZ(k, x, altura(x, y), -y);
    const q = i * cols + j;
    const h = (tr.alto[q] - min) / (max - min || 1);
    // campo: más verde abajo, más seco arriba; montaña alta con bosque ralo
    c.copy(bajo)
      .lerp(alto, Math.min(1, h * 2.4))
      .lerp(cumbre, Math.max(0, Math.min(1, h * 2.5 - 1.2)));
    c.lerp(ciudad, urbano[q] * 0.9);
    c.lerp(bosque, Math.max(0, Math.min(1, (pendiente[q] - 0.12) / 0.2)) * 0.9);
    // fondos de barranco más oscuros (curvatura): da profundidad sin otra pasada de render
    if (i > 0 && j > 0 && i < filas - 1 && j < cols - 1) {
      const a = tr.alto;
      const lap = (a[q - 1] + a[q + 1] + a[q - cols] + a[q + cols]) / 4 - a[q];
      c.multiplyScalar(1 - Math.max(-0.08, Math.min(0.18, lap * 0.05)));
    }
    c.multiplyScalar(0.95 + 0.05 * Math.sin(x * 0.013) * Math.cos(y * 0.011));
    color.set([c.r, c.g, c.b], 3 * k);
    zona[k] = malla[q];
  }
  g.setAttribute("color", new THREE.BufferAttribute(color, 3));
  g.setAttribute("zona", new THREE.BufferAttribute(zona, 1));
  g.computeVertexNormals();

  const base = color.slice();
  const attr = g.attributes.color;
  const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95, metalness: 0 }));
  m.receiveShadow = true;
  const tintes = Array.from({ length: nz }, (_, k) => new THREE.Color(colorZona(k)));
  return {
    malla: m,
    /**
     * Zonas elegidas: se tiñen con su color; el resto se apaga (gris y más oscuro).
     * @param {Set<number>} conjunto
     */
    marcar(conjunto) {
      const a = attr.array;
      if (!conjunto.size) a.set(base);
      else
        for (let k = 0; k < zona.length; k++) {
          const r = base[3 * k],
            g_ = base[3 * k + 1],
            b = base[3 * k + 2],
            z = zona[k] - 1;
          if (z >= 0 && conjunto.has(z)) {
            const t = tintes[z];
            a[3 * k] = r * 0.45 + t.r * 0.55;
            a[3 * k + 1] = g_ * 0.45 + t.g * 0.55;
            a[3 * k + 2] = b * 0.45 + t.b * 0.55;
          } else {
            const y = (r * 0.3 + g_ * 0.59 + b * 0.11) * 0.62;
            a[3 * k] = r * 0.25 + y * 0.75 - 0.03;
            a[3 * k + 1] = g_ * 0.25 + y * 0.75 - 0.03;
            a[3 * k + 2] = b * 0.25 + y * 0.75 - 0.03;
          }
        }
      attr.needsUpdate = true;
    },
  };
}

/**
 * Bosque de hoja ancha en las laderas empinadas (los barrancos), lejos de calles y edificios.
 * @param {Grilla} tr
 * @param {(x: number, y: number) => number} altura
 * @param {Float32Array} pendiente
 * @param {{ red: { calles: { p: number[] }[] }, edificios: [number[], number][] }} datos
 */
export function arboles(tr, altura, pendiente, datos) {
  const ocupado = new Uint8Array(tr.filas * tr.cols);
  const marca = (x, y) => {
    const j = Math.round((x - tr.x0) / tr.paso_m),
      i = Math.round((y - tr.y0) / tr.paso_m);
    if (i >= 0 && i < tr.filas && j >= 0 && j < tr.cols) ocupado[i * tr.cols + j] = 1;
  };
  for (const c of datos.red.calles) for (let k = 0; k < c.p.length; k += 2) marca(c.p[k], c.p[k + 1]);
  for (const [p] of datos.edificios) for (let k = 0; k < p.length; k += 2) marca(p[k], p[k + 1]);

  const puntos = [];
  let semilla = 7;
  const azar = () => (semilla = (semilla * 16807) % 2147483647) / 2147483647;
  for (let i = 1; i < tr.filas - 1; i++)
    for (let j = 1; j < tr.cols - 1; j++) {
      const s = pendiente[i * tr.cols + j];
      if (ocupado[i * tr.cols + j] || s < 0.16) continue;
      const k = s > 0.35 ? 3 : s > 0.24 ? 2 : 1;
      for (let r = 0; r < k; r++) {
        if (azar() > 0.85) continue;
        const x = tr.x0 + (j + azar() - 0.5) * tr.paso_m,
          y = tr.y0 + (i + azar() - 0.5) * tr.paso_m;
        puntos.push(x, y, 0.7 + azar() * 0.9);
      }
    }
  const n = puntos.length / 3;
  const copa = new THREE.IcosahedronGeometry(6, 0);
  copa.scale(1, 0.85, 1).translate(0, 8, 0);
  const m = new THREE.InstancedMesh(
    copa,
    new THREE.MeshStandardMaterial({ color: "#ffffff", roughness: 0.95, flatShading: true }),
    n,
  );
  const o = new THREE.Object3D(),
    c = new THREE.Color();
  for (let k = 0; k < n; k++) {
    const [x, y, s] = [puntos[3 * k], puntos[3 * k + 1], puntos[3 * k + 2]];
    o.position.set(x, altura(x, y) - 1, -y);
    o.scale.set(s, s * (0.8 + (0.5 * ((k * 31) % 7)) / 7), s);
    o.rotation.set(0, k, 0);
    o.updateMatrix();
    m.setMatrixAt(k, o.matrix);
    m.setColorAt(k, c.setHSL(0.2 + (0.09 * ((k * 13) % 10)) / 10, 0.42, 0.24 + (0.12 * ((k * 7) % 10)) / 10));
  }
  m.castShadow = true;
  m.receiveShadow = true;
  return m;
}

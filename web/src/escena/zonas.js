// Zonas de la ciudad: color de cada una, raster sobre la grilla del terreno y la cinta
// brillante que marca el límite de las zonas elegidas.

import * as THREE from "three";

/** @typedef {{ n: string, centro: [number, number], anillos: number[][] }} Zona */

// un color por zona, repartidos por el círculo cromático para que vecinas no se confundan
/** @param {number} k */
export const colorZona = (k) => `hsl(${(k * 137.5) % 360}, 70%, 55%)`;

/**
 * Zona (índice + 1, 0 = ninguna) de cada celda del terreno, por barrido de filas.
 * @param {{ filas: number, cols: number, paso_m: number, x0: number, y0: number }} tr
 * @param {Zona[]} zonas
 */
export function rasterZonas(tr, zonas) {
  const { filas, cols, paso_m, x0, y0 } = tr;
  const m = new Uint8Array(filas * cols);
  zonas.forEach((z, k) => {
    for (const a of z.anillos) {
      const n = a.length / 2;
      for (let i = 0; i < filas; i++) {
        const y = y0 + i * paso_m;
        const xs = [];
        for (let e = 0; e < n; e++) {
          const ax = a[2 * e],
            ay = a[2 * e + 1],
            bx = a[2 * ((e + 1) % n)],
            by = a[2 * ((e + 1) % n) + 1];
          if (ay <= y !== by <= y) xs.push(ax + ((y - ay) / (by - ay)) * (bx - ax));
        }
        xs.sort((p, q) => p - q);
        for (let s = 0; s + 1 < xs.length; s += 2) {
          const j0 = Math.max(0, Math.ceil((xs[s] - x0) / paso_m)),
            j1 = Math.min(cols - 1, Math.floor((xs[s + 1] - x0) / paso_m));
          for (let j = j0; j <= j1; j++) m[i * cols + j] = k + 1;
        }
      }
    }
  });
  return m;
}

/**
 * Límite de cada zona: una cinta brillante que sigue el relieve.
 * @param {Zona[]} zonas
 * @param {(x: number, y: number) => number} altura
 */
export function bordes(zonas, altura) {
  const grupo = new THREE.Group();
  const lineas = zonas.map((z, k) => {
    const pos = [],
      idx = [];
    for (const a of z.anillos) {
      // densifica cada lado cada 15 m para que la cinta no atraviese lomas
      const p = [];
      const n = a.length / 2;
      for (let e = 0; e < n; e++) {
        const ax = a[2 * e],
          ay = a[2 * e + 1],
          bx = a[2 * ((e + 1) % n)],
          by = a[2 * ((e + 1) % n) + 1];
        const pasos = Math.max(1, Math.ceil(Math.hypot(bx - ax, by - ay) / 15));
        for (let s = 0; s < pasos; s++) p.push(ax + ((bx - ax) * s) / pasos, ay + ((by - ay) * s) / pasos);
      }
      p.push(p[0], p[1]);
      const m = p.length / 2,
        base = pos.length / 3,
        w = 7;
      for (let q = 0; q < m; q++) {
        const i0 = Math.max(0, q - 1),
          i1 = Math.min(m - 1, q + 1);
        let dx = p[2 * i1] - p[2 * i0],
          dy = p[2 * i1 + 1] - p[2 * i0 + 1];
        const l = Math.hypot(dx, dy) || 1;
        dx /= l;
        dy /= l;
        for (const s of [-1, 1]) {
          const x = p[2 * q] - dy * w * s,
            y = p[2 * q + 1] + dx * w * s;
          pos.push(x, altura(x, y) + 3, -y);
        }
        if (q < m - 1) {
          const v = base + 2 * q;
          idx.push(v, v + 1, v + 2, v + 1, v + 3, v + 2);
        }
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setIndex(idx);
    const color = new THREE.Color(colorZona(k));
    const mat = new THREE.MeshBasicMaterial({ color, toneMapped: false, side: THREE.DoubleSide, fog: false });
    const malla = new THREE.Mesh(g, mat);
    malla.visible = false;
    malla.renderOrder = 2;
    grupo.add(malla);
    return { malla, color };
  });
  return {
    grupo,
    /** @param {Set<number>} sel */
    mostrar(sel) {
      lineas.forEach((l, k) => (l.malla.visible = sel.has(k)));
    },
    /** @param {number} t */
    pulso(t) {
      const f = 0.75 + 0.12 * Math.sin(t * 2.2); // bajo el umbral del bloom: conserva el color
      for (const l of lineas) if (l.malla.visible) l.malla.material.color.copy(l.color).multiplyScalar(f);
    },
  };
}

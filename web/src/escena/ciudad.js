// Ciudad: calles como cintas sobre el relieve y edificios extruidos.

import * as THREE from "three";

/**
 * Calles; las grandes más oscuras y anchas, con borde claro.
 * @param {{ calles: { p: number[], w: number, k?: number }[] }} red
 * @param {(x: number, y: number) => number} altura
 */
export function calles(red, altura) {
  const pos = [],
    col = [],
    idx = [];
  const tono = [
    new THREE.Color("#4a4c50"),
    new THREE.Color("#55575a"),
    new THREE.Color("#6a6b6c"),
    new THREE.Color("#858481"),
  ];
  const cinta = (p, w, h, c) => {
    const base = pos.length / 3;
    const n = p.length / 2;
    for (let k = 0; k < n; k++) {
      const a = Math.max(0, k - 1),
        b = Math.min(n - 1, k + 1);
      let dx = p[2 * b] - p[2 * a],
        dy = p[2 * b + 1] - p[2 * a + 1];
      const l = Math.hypot(dx, dy) || 1;
      dx /= l;
      dy /= l;
      const x = p[2 * k],
        y = p[2 * k + 1];
      for (const s of [-1, 1]) {
        const px = x - dy * w * s,
          py = y + dx * w * s;
        pos.push(px, altura(px, py) + h, -py);
        col.push(c.r, c.g, c.b);
      }
      if (k < n - 1) {
        const v = base + 2 * k;
        idx.push(v, v + 1, v + 2, v + 1, v + 3, v + 2);
      }
    }
  };
  const borde = new THREE.Color("#e9e4da");
  // primero los bordes (debajo), después las calzadas
  for (const c of red.calles)
    if (c.p.length >= 4 && (c.k ?? 3) <= 1) cinta(c.p, Math.max(3, c.w) / 2 + 1.6, 0.5, borde);
  for (const c of red.calles) if (c.p.length >= 4) cinta(c.p, Math.max(3, c.w) / 2, 0.7, tono[c.k ?? 3]);
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
  g.setIndex(idx);
  g.computeVertexNormals();
  const m = new THREE.Mesh(
    g,
    new THREE.MeshStandardMaterial({
      vertexColors: true,
      roughness: 0.9,
      polygonOffset: true,
      polygonOffsetFactor: -2,
      side: THREE.DoubleSide,
    }),
  );
  m.receiveShadow = true;
  return m;
}

/**
 * Edificios: prismas extruidos, todos en una sola geometría.
 * @param {[number[], number][]} lista  [polígono cerrado xy, altura m]
 * @param {(x: number, y: number) => number} altura
 */
export function edificios(lista, altura) {
  const pos = [],
    nor = [],
    col = [];
  const c = new THREE.Color(),
    pie = new THREE.Color();
  // agrega un triángulo con la normal dada, ordenando los vértices para que esa sea
  // la cara de frente (si no, three la ilumina como cara trasera y queda negra)
  const tri = (a, b, d, n, ka, kb, kd) => {
    const ux = b[0] - a[0],
      uy = b[1] - a[1],
      uz = b[2] - a[2];
    const vx = d[0] - a[0],
      vy = d[1] - a[1],
      vz = d[2] - a[2];
    const dot = (uy * vz - uz * vy) * n[0] + (uz * vx - ux * vz) * n[1] + (ux * vy - uy * vx) * n[2];
    const vs =
      dot >= 0
        ? [
            [a, ka],
            [b, kb],
            [d, kd],
          ]
        : [
            [a, ka],
            [d, kd],
            [b, kb],
          ];
    for (const [q, k] of vs) {
      pos.push(...q);
      nor.push(...n);
      col.push(k.r, k.g, k.b);
    }
  };
  for (const [p, h] of lista) {
    const n = p.length / 2 - 1; // el último punto repite el primero
    if (n < 3) continue;
    let cx = 0,
      cy = 0;
    for (let k = 0; k < n; k++) {
      cx += p[2 * k];
      cy += p[2 * k + 1];
    }
    cx /= n;
    cy /= n;
    let z0 = Infinity;
    for (let k = 0; k < n; k++) z0 = Math.min(z0, altura(p[2 * k], p[2 * k + 1]));
    const z1 = z0 + h + 1.5;
    const t = (Math.abs(Math.round(cx * 3 + cy * 7)) % 100) / 100;
    // casas en tonos tierra claros; torres en gris azulado (vidrio y concreto)
    if (h > 25) c.setHSL(0.58, 0.1 + 0.08 * t, 0.74 + 0.08 * t);
    else c.setHSL(0.07 + 0.05 * t, 0.18 + 0.14 * t, 0.78 + 0.1 * t);
    // oclusión al pie de la pared: más oscuro abajo, en los primeros ~12 m
    pie.copy(c).multiplyScalar(Math.max(0.55, 1 - 0.45 * Math.min(1, 12 / (h + 4))));
    // paredes; la normal apunta hacia afuera según el sentido de giro del polígono
    let area2 = 0;
    for (let k = 0; k < n; k++) area2 += p[2 * k] * p[2 * k + 3] - p[2 * k + 2] * p[2 * k + 1];
    const giro = area2 > 0 ? 1 : -1;
    for (let k = 0; k < n; k++) {
      const ax = p[2 * k],
        ay = p[2 * k + 1],
        bx = p[2 * k + 2],
        by = p[2 * k + 3];
      let nx = (by - ay) * giro,
        ny = -(bx - ax) * giro;
      const l = Math.hypot(nx, ny) || 1;
      nx /= l;
      ny /= l;
      const n3 = [nx, 0, -ny];
      const a0 = [ax, z0 - 3, -ay],
        b0 = [bx, z0 - 3, -by],
        b1 = [bx, z1, -by],
        a1 = [ax, z1, -ay];
      tri(a0, b0, b1, n3, pie, pie, c);
      tri(a0, b1, a1, n3, pie, c, c);
    }
    // techo: triangulación en abanico desde el centroide (sirve para casi todos los polígonos de OSM)
    const techo = c.clone().multiplyScalar(1.06);
    for (let k = 0; k < n; k++)
      tri(
        [cx, z1, -cy],
        [p[2 * k], z1, -p[2 * k + 1]],
        [p[2 * k + 2], z1, -p[2 * k + 3]],
        [0, 1, 0],
        techo,
        techo,
        techo,
      );
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3));
  g.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
  const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.75 }));
  m.castShadow = true;
  m.receiveShadow = true;
  return m;
}

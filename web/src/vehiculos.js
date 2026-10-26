// Vehículos: un InstancedMesh por tipo. La flota dibuja la ventana de trayectorias que
// se le pase con `usar`; la interpolación está en trayectorias.js.

import * as THREE from "three";
import { crearMuestreador } from "./trayectorias.js";

/** @typedef {import("./tipos.js").Trayectoria} Trayectoria */
/** @typedef {{ n: Uint32Array, parados: Uint32Array, kmh: Float32Array }} PorZona */
/** @typedef {{ enRed: number, parados: number, kmh: number, porZona: PorZona }} Resumen */

// largo, ancho, alto (m); el tipo viene del export: 0 carro, 1 moto, 2 bus, 3 camión
const FORMAS = [
  [4.4, 1.9, 1.5],
  [2.1, 0.8, 1.4],
  [12, 2.6, 3.2],
  [8, 2.5, 3.4],
];
const ESCALA = 3; // a escala real un carro es un pixel visto desde 3 km

function caja([l, w, h]) {
  // carrocería + cabina, con el frente hacia +x
  const cuerpo = new THREE.BoxGeometry(l, h * 0.55, w).translate(0, h * 0.28, 0);
  const cabina = new THREE.BoxGeometry(l * 0.5, h * 0.45, w * 0.86).translate(-l * 0.05, h * 0.77, 0);
  const g = new THREE.BufferGeometry();
  const pos = [...cuerpo.attributes.position.array, ...cabina.attributes.position.array];
  const nor = [...cuerpo.attributes.normal.array, ...cabina.attributes.normal.array];
  const off = cuerpo.attributes.position.count;
  const idx = [...cuerpo.index.array, ...Array.from(cabina.index.array, (i) => i + off)];
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3));
  g.setIndex(idx);
  cuerpo.dispose();
  cabina.dispose();
  return g;
}

// velocidad -> color: rojo detenido, ámbar lento, verde-azulado fluido
const PARADO = new THREE.Color(3.2, 0.25, 0.12),
  LENTO = new THREE.Color(2.2, 1.2, 0.15),
  FLUIDO = new THREE.Color(0.35, 1.1, 1.0);

/**
 * @param {THREE.Scene} scene
 * @param {(x: number, y: number) => number} altura
 * @param {(x: number, y: number) => number} [zonaDe]  índice de zona + 1 (0 = fuera de toda zona)
 * @param {number} [nz]  cantidad de zonas
 */
export function crear(scene, altura, zonaDe = () => 0, nz = 0) {
  const geometrias = FORMAS.map(caja);
  const materiales = FORMAS.map(() => new THREE.MeshStandardMaterial({ roughness: 0.45, metalness: 0.2 }));
  /** @type {THREE.InstancedMesh[]} */
  const mallas = [];

  /** malla del tipo i con lugar para al menos `cap` instancias (se agranda, nunca se achica) */
  function asegurar(i, cap) {
    const vieja = mallas[i];
    if (vieja && vieja.instanceMatrix.count >= cap) return;
    if (vieja) {
      scene.remove(vieja);
      vieja.dispose();
    }
    const m = new THREE.InstancedMesh(geometrias[i], materiales[i], Math.max(1, Math.ceil(cap * 1.25)));
    m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    m.setColorAt(0, new THREE.Color());
    m.instanceColor.setUsage(THREE.DynamicDrawUsage);
    m.castShadow = true;
    m.frustumCulled = false;
    m.count = 0;
    scene.add(m);
    mallas[i] = m;
  }
  FORMAS.forEach((_, i) => asegurar(i, 1));

  /** @type {Trayectoria | null} */
  let tray = null;
  let muestreador = null;
  const o = new THREE.Object3D(),
    c = new THREE.Color();
  const porZona = { n: new Uint32Array(nz + 1), parados: new Uint32Array(nz + 1), kmh: new Float32Array(nz + 1) };
  let escala = ESCALA;
  const usados = [0, 0, 0, 0];
  let enRed = 0,
    parados = 0,
    suma = 0;

  function visita(k, x, y, kmh, hx, hy) {
    const tp = tray.tipo[k];
    const m = mallas[tp];
    const i = usados[tp]++;
    o.position.set(x, altura(x, y) + 0.8, -y);
    o.rotation.set(0, Math.atan2(hy, hx), 0);
    o.scale.setScalar(escala);
    o.updateMatrix();
    m.setMatrixAt(i, o.matrix);
    if (kmh < 5) c.copy(PARADO);
    else if (kmh < 25) c.copy(PARADO).lerp(LENTO, (kmh - 5) / 20);
    else c.copy(LENTO).lerp(FLUIDO, Math.min(1, (kmh - 25) / 25));
    m.setColorAt(i, c);
    enRed++;
    suma += kmh;
    if (kmh < 5) parados++;
    const z = zonaDe(x, y);
    porZona.n[z]++;
    porZona.kmh[z] += kmh;
    if (kmh < 5) porZona.parados[z]++;
  }

  function vaciar() {
    for (const m of mallas) m.count = 0;
    porZona.n.fill(0);
    porZona.parados.fill(0);
    porZona.kmh.fill(0);
    return { enRed: 0, parados: 0, kmh: 0, porZona };
  }

  return {
    /**
     * Cambia la ventana de trayectorias que se dibuja.
     * @param {Trayectoria | null} t
     */
    usar(t) {
      if (t === tray) return;
      tray = t;
      muestreador = t ? crearMuestreador(t) : null;
      if (!t) return;
      const cuenta = [0, 0, 0, 0];
      for (let k = 0; k < t.n; k++) cuenta[t.tipo[k]]++;
      cuenta.forEach((n, i) => asegurar(i, n));
    },
    /**
     * @param {number} T
     * @returns {Resumen}
     */
    actualizar(T) {
      if (!muestreador) return vaciar();
      usados.fill(0);
      enRed = parados = suma = 0;
      porZona.n.fill(0);
      porZona.parados.fill(0);
      porZona.kmh.fill(0);
      muestreador.recorrer(T, visita);
      mallas.forEach((m, i) => {
        m.count = usados[i];
        m.instanceMatrix.needsUpdate = true;
        m.instanceColor.needsUpdate = true;
      });
      return { enRed, parados, kmh: enRed ? suma / enRed : 0, porZona };
    },
    vaciar,
    /** @param {number} e */
    set escala(e) {
      escala = e;
    },
    destruir() {
      for (const m of mallas) {
        scene.remove(m);
        m.dispose();
      }
      for (const g of geometrias) g.dispose();
      for (const m of materiales) m.dispose();
    },
  };
}

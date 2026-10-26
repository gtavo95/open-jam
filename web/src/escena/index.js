// La escena 3D en Three.js: arma relieve, ciudad, zonas, semáforos, cámara y postproceso.
// Coordenadas: x este, y arriba, z = -norte (metros de la red SUMO).

import * as THREE from "three";
import { iluminar, ajustarNiebla } from "./ambiente.js";
import { crearCamara } from "./camara.js";
import { calles, edificios } from "./ciudad.js";
import { crearComposer } from "./postproceso.js";
import { semaforos as crearSemaforos } from "./semaforos.js";
import { arboles, crearAltura, densidadUrbana, pendientes, terreno } from "./terreno.js";
import { bordes, rasterZonas } from "./zonas.js";

export { colorZona } from "./zonas.js";

/**
 * Libera geometrías, materiales, texturas y sombras de todo lo que cuelga de `raiz`.
 * @param {THREE.Object3D} raiz
 */
export function liberar(raiz) {
  raiz.traverse((o) => {
    const m = /** @type {any} */ (o);
    m.geometry?.dispose?.();
    for (const mat of [m.material].flat()) {
      if (!mat) continue;
      for (const v of Object.values(mat)) if (v instanceof THREE.Texture) v.dispose();
      mat.dispose();
    }
    if (m.isInstancedMesh) m.dispose();
    if (m.isLight) m.dispose?.();
  });
}

/**
 * @param {HTMLCanvasElement} lienzo
 * @param {{ terreno: any, edificios: [number[], number][], zonas?: any[], red: import("../tipos.js").Red }} datos
 */
export function crear(lienzo, datos) {
  const renderer = new THREE.WebGLRenderer({ canvas: lienzo, antialias: false, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  const tr = datos.terreno;
  const ancho = (tr.cols - 1) * tr.paso_m,
    largo = (tr.filas - 1) * tr.paso_m;
  const centro = new THREE.Vector3(tr.x0 + ancho / 2, 0, -(tr.y0 + largo / 2));
  const altura = crearAltura(tr);

  const zonas = datos.zonas ?? [];
  const malla = rasterZonas(tr, zonas);
  /** índice de zona + 1 en (x, y); 0 = fuera de toda zona */
  const zonaDe = (x, y) => {
    const j = Math.round((x - tr.x0) / tr.paso_m),
      i = Math.round((y - tr.y0) / tr.paso_m);
    return i >= 0 && i < tr.filas && j >= 0 && j < tr.cols ? malla[i * tr.cols + j] : 0;
  };

  // arranca mirando Zona 10 (Reforma y La Pradera)
  const z10 = zonas.find((z) => z.n === "Zona 10");
  const foco = z10 ? new THREE.Vector3(z10.centro[0], 0, -z10.centro[1]) : centro.clone();
  foco.y = altura(foco.x, -foco.z);
  const camara = crearCamara(lienzo, foco, altura);
  const { camera, controls } = camara;

  iluminar(scene, centro);
  const pendiente = pendientes(tr);
  const urbano = densidadUrbana(tr, datos.edificios);
  const suelo = terreno(tr, altura, pendiente, urbano, malla, zonas.length);
  scene.add(suelo.malla);
  scene.add(calles(datos.red, altura));
  scene.add(edificios(datos.edificios, altura));
  scene.add(arboles(tr, altura, pendiente, datos));
  const limites = bordes(zonas, altura);
  scene.add(limites.grupo);
  const semaforos = crearSemaforos(datos.red.semaforos, altura);
  scene.add(semaforos.grupo);

  const composer = crearComposer(renderer, scene, camera);

  function tamaño() {
    const { clientWidth: w, clientHeight: h } = lienzo.parentElement;
    renderer.setSize(w, h, false);
    composer.setSize(w, h);
    camara.aspecto(w, h);
  }
  tamaño();
  addEventListener("resize", tamaño);

  /**
   * @param {number} dt  segundos desde el cuadro anterior
   * @param {number} t  segundos de reloj
   */
  function cuadro(dt, t) {
    ajustarNiebla(/** @type {THREE.Fog} */ (scene.fog), camara.actualizar(dt));
    limites.pulso(t);
    composer.render(dt);
  }

  /**
   * Zonas visibles: índices en `zonas` (vacío = mapa limpio).
   * @param {Set<number>} sel
   */
  function mostrarZonas(sel) {
    suelo.marcar(sel);
    limites.mostrar(sel);
  }

  if (import.meta.env.DEV) window.mundo = { camera, controls, altura, zonaDe, scene, renderer };
  return {
    scene,
    camera,
    altura,
    semaforos,
    centro,
    zonas,
    zonaDe,
    volar: camara.volar,
    pantalla: camara.pantalla,
    cuadro,
    mostrarZonas,
    destruir() {
      removeEventListener("resize", tamaño);
      camara.destruir();
      composer.dispose();
      liberar(scene);
      scene.clear();
      renderer.dispose();
      if (import.meta.env.DEV) delete window.mundo;
    },
  };
}

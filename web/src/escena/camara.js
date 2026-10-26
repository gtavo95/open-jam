// Cámara: órbita con el mouse, teclado (flechas mueven el mapa, Shift + flechas giran e
// inclinan, + / − acercan), vuelo suave hacia un punto y proyección a pantalla.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const MOVIL = ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "+", "=", "-", "_"];

/**
 * @param {HTMLCanvasElement} lienzo
 * @param {THREE.Vector3} foco  punto inicial que se mira
 * @param {(x: number, y: number) => number} altura
 */
export function crearCamara(lienzo, foco, altura) {
  const camera = new THREE.PerspectiveCamera(40, 1, 5, 60000);
  // arranca mirando el foco desde el suroeste
  camera.position.set(foco.x - 900, foco.y + 900, foco.z + 1500);
  const controls = new OrbitControls(camera, lienzo);
  controls.target.copy(foco);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI * 0.47;
  controls.minDistance = 60;
  controls.maxDistance = 26000;

  // vuelo suave de la cámara hacia un punto (al elegir una zona)
  let vuelo = null;
  /**
   * @param {number} x
   * @param {number} y
   * @param {number} distancia
   */
  function volar(x, y, distancia) {
    const destino = new THREE.Vector3(x, altura(x, y), -y);
    const dir = camera.position.clone().sub(controls.target).normalize();
    dir.y = Math.max(dir.y, 0.55);
    dir.normalize();
    vuelo = {
      t: 0,
      de: [camera.position.clone(), controls.target.clone()],
      a: [destino.clone().addScaledVector(dir, distancia), destino],
    };
  }

  const teclas = new Map(); // tecla -> hasta cuándo sigue activa aunque se haya soltado
  let girar = false;
  /** @param {KeyboardEvent} e */
  const abajo = (e) => {
    girar = e.shiftKey;
    if (/** @type {Element} */ (e.target).closest?.("input, select, textarea") || !MOVIL.includes(e.key)) return;
    e.preventDefault();
    teclas.set(e.key, { hasta: performance.now() + 200, suelta: false });
    vuelo = null;
  };
  /** @param {KeyboardEvent} e */
  const arriba = (e) => {
    girar = e.shiftKey;
    const k = teclas.get(e.key);
    if (k) k.suelta = true;
  };
  const soltar = () => teclas.clear();
  addEventListener("keydown", abajo);
  addEventListener("keyup", arriba);
  addEventListener("blur", soltar);

  const adelante = new THREE.Vector3(),
    lado = new THREE.Vector3(),
    paso = new THREE.Vector3();
  /** @param {number} dt */
  function teclado(dt) {
    const ahora = performance.now();
    for (const [k, e] of teclas) if (e.suelta && ahora > e.hasta) teclas.delete(k);
    if (!teclas.size) return;
    const d = camera.position.distanceTo(controls.target);
    const f = (k) => (teclas.has(k) ? 1 : 0);
    const dx = f("ArrowRight") - f("ArrowLeft"),
      dy = f("ArrowUp") - f("ArrowDown");
    const dz = f("-") + f("_") - f("+") - f("=");
    if (girar) {
      // giro alrededor del punto que se mira, y cambio de inclinación
      const o = camera.position.clone().sub(controls.target);
      const s = new THREE.Spherical().setFromVector3(o);
      s.theta -= dx * dt * 1.2;
      s.phi = Math.min(controls.maxPolarAngle, Math.max(0.15, s.phi - dy * dt * 0.8));
      camera.position.copy(controls.target).add(o.setFromSpherical(s));
    } else if (dx || dy) {
      // desplazamiento sobre el plano, relativo a hacia dónde mira la cámara
      camera.getWorldDirection(adelante);
      adelante.y = 0;
      adelante.normalize();
      lado.crossVectors(adelante, camera.up).normalize();
      paso
        .set(0, 0, 0)
        .addScaledVector(adelante, dy)
        .addScaledVector(lado, dx)
        .multiplyScalar(d * 0.9 * dt);
      camera.position.add(paso);
      controls.target.add(paso);
      // el punto mirado sigue al relieve para no hundirse en las lomas
      const h = altura(controls.target.x, -controls.target.z) - controls.target.y;
      controls.target.y += h;
      camera.position.y += h;
    }
    if (dz) {
      const o = camera.position.clone().sub(controls.target);
      const l = Math.min(controls.maxDistance, Math.max(controls.minDistance, o.length() * (1 + dz * dt * 1.5)));
      camera.position.copy(controls.target).add(o.setLength(l));
    }
  }

  /**
   * Avanza vuelo, teclado y amortiguación; devuelve la distancia al objetivo.
   * @param {number} dt
   */
  function actualizar(dt) {
    if (vuelo) {
      vuelo.t = Math.min(1, vuelo.t + dt / 1.4);
      const e = vuelo.t < 0.5 ? 4 * vuelo.t ** 3 : 1 - (-2 * vuelo.t + 2) ** 3 / 2;
      camera.position.lerpVectors(vuelo.de[0], vuelo.a[0], e);
      controls.target.lerpVectors(vuelo.de[1], vuelo.a[1], e);
      if (vuelo.t === 1) vuelo = null;
    }
    teclado(dt);
    controls.update();
    return camera.position.distanceTo(controls.target);
  }

  const v = new THREE.Vector3();
  /**
   * Píxeles en el lienzo del punto (x, y) a 40 m sobre el suelo; null si queda detrás.
   * @param {number} x
   * @param {number} y
   * @returns {[number, number] | null}
   */
  function pantalla(x, y) {
    v.set(x, altura(x, y) + 40, -y).project(camera);
    if (v.z > 1) return null;
    return [((v.x + 1) / 2) * lienzo.clientWidth, ((1 - v.y) / 2) * lienzo.clientHeight];
  }

  /** @param {number} w @param {number} h */
  function aspecto(w, h) {
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }

  return {
    camera,
    controls,
    volar,
    actualizar,
    pantalla,
    aspecto,
    destruir() {
      removeEventListener("keydown", abajo);
      removeEventListener("keyup", arriba);
      removeEventListener("blur", soltar);
      controls.dispose();
    },
  };
}

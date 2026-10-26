// Ambiente: cielo, niebla y luz de la mañana.

import * as THREE from "three";

export const HORIZONTE = new THREE.Color("#eadfca");
const CENIT = new THREE.Color("#8fb0cc");

/** cúpula con degradé del horizonte al cenit, que sigue a la cámara */
export function cielo() {
  const g = new THREE.SphereGeometry(45000, 32, 16);
  const m = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    fog: false,
    uniforms: { horizonte: { value: HORIZONTE }, cenit: { value: CENIT } },
    vertexShader:
      "varying vec3 p; void main(){ p = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
    fragmentShader:
      "uniform vec3 horizonte, cenit; varying vec3 p; void main(){ float h = smoothstep(-0.02, 0.45, p.y); gl_FragColor = vec4(mix(horizonte, cenit, h), 1.0); }",
  });
  const s = new THREE.Mesh(g, m);
  s.onBeforeRender = (r, sc, cam) => s.position.copy(cam.position);
  s.renderOrder = -1;
  return s;
}

/**
 * Luz de la mañana: sol bajo desde el este con sombras sobre toda el área, cielo cálido.
 * @param {THREE.Scene} scene
 * @param {THREE.Vector3} centro
 */
export function iluminar(scene, centro) {
  scene.background = HORIZONTE;
  scene.fog = new THREE.Fog(HORIZONTE, 7000, 22000);
  scene.add(cielo());
  scene.add(new THREE.HemisphereLight("#f4f1ea", "#6b5a44", 1.25));
  const sol = new THREE.DirectionalLight("#ffdcb0", 2.4);
  sol.position.set(centro.x + 7000, 4200, centro.z - 2500);
  sol.target.position.copy(centro);
  sol.castShadow = true;
  sol.shadow.mapSize.set(4096, 4096);
  const sc = sol.shadow.camera;
  sc.left = -11000;
  sc.right = 11000;
  sc.top = 11000;
  sc.bottom = -11000;
  sc.near = 100;
  sc.far = 24000;
  sol.shadow.bias = -0.0004;
  sol.shadow.normalBias = 2;
  scene.add(sol, sol.target);
}

/**
 * Niebla relativa a la distancia de la cámara: lejos se ve la ciudad entera, cerca hay profundidad.
 * @param {THREE.Fog} fog
 * @param {number} d  distancia cámara-objetivo
 */
export function ajustarNiebla(fog, d) {
  fog.near = d * 1.1 + 1500;
  fog.far = d * 4 + 9000;
}

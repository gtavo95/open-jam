// Semáforos: un poste con una luz que brilla, una instancia por semáforo. Encendido:
// verde fijo; apagado (amarillo intermitente en la vida real): ámbar que parpadea.

import * as THREE from "three";

const VERDE = new THREE.Color(0.2, 3, 0.8);
const AMBAR_ALTO = new THREE.Color(3.2, 3.2 * 0.55, 0);
const AMBAR_BAJO = new THREE.Color(0.25, 0.25 * 0.55, 0);

/**
 * @param {{ x: number, y: number }[]} lista  red.semaforos
 * @param {(x: number, y: number) => number} altura
 */
export function semaforos(lista, altura) {
  const grupo = new THREE.Group();
  const n = Math.max(1, lista.length);
  const poste = new THREE.InstancedMesh(
    new THREE.CylinderGeometry(0.6, 0.6, 9, 6).translate(0, 4.5, 0),
    new THREE.MeshStandardMaterial({ color: "#2b2b2b" }),
    n,
  );
  // el color de cada luz va por instancia (HDR, > 1 para que el bloom la haga brillar)
  const mat = new THREE.MeshBasicMaterial({ color: "#ffffff", toneMapped: false });
  const luz = new THREE.InstancedMesh(new THREE.SphereGeometry(2.4, 12, 8).translate(0, 10, 0), mat, n);
  const o = new THREE.Object3D();
  lista.forEach((s, k) => {
    o.position.set(s.x, altura(s.x, s.y), -s.y);
    o.updateMatrix();
    poste.setMatrixAt(k, o.matrix);
    luz.setMatrixAt(k, o.matrix);
    luz.setColorAt(k, VERDE);
  });
  poste.count = luz.count = lista.length;
  grupo.add(poste, luz);

  /** @type {Uint8Array | null} */
  let previo = null;
  let fase = -1;
  // con movimiento reducido el ámbar queda fijo
  const quieto = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)");
  return {
    grupo,
    /**
     * @param {Uint8Array} encendidos  1/0 por semáforo, en el orden de `lista`
     * @param {number} t  segundos de reloj (para el parpadeo)
     */
    estado(encendidos, t) {
      const f = quieto?.matches || Math.sin(t * Math.PI) > 0 ? 1 : 0;
      if (encendidos === previo && f === fase) return; // solo se escribe cuando algo cambia
      previo = encendidos;
      fase = f;
      const ambar = f ? AMBAR_ALTO : AMBAR_BAJO;
      for (let k = 0; k < lista.length; k++) luz.setColorAt(k, encendidos[k] ? VERDE : ambar);
      if (luz.instanceColor) luz.instanceColor.needsUpdate = true;
    },
  };
}

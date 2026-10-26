// Postproceso: bloom para las luces HDR, tone mapping AgX, viñeta y SMAA.

import * as THREE from "three";
import {
  EffectComposer,
  RenderPass,
  EffectPass,
  BloomEffect,
  SMAAEffect,
  VignetteEffect,
  ToneMappingEffect,
  ToneMappingMode,
} from "postprocessing";

/**
 * @param {THREE.WebGLRenderer} renderer
 * @param {THREE.Scene} scene
 * @param {THREE.Camera} camera
 */
export function crearComposer(renderer, scene, camera) {
  const composer = new EffectComposer(renderer, { frameBufferType: THREE.HalfFloatType });
  composer.addPass(new RenderPass(scene, camera));
  composer.addPass(
    new EffectPass(
      camera,
      new BloomEffect({ intensity: 0.9, luminanceThreshold: 0.9, luminanceSmoothing: 0.2, mipmapBlur: true }),
      new ToneMappingEffect({ mode: ToneMappingMode.AGX }),
      new VignetteEffect({ darkness: 0.3, offset: 0.35 }),
      new SMAAEffect(),
    ),
  );
  return composer; // composer.dispose() libera pases, efectos y render targets
}

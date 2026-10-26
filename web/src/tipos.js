// Tipos compartidos del visor (solo JSDoc; no exporta código).
// El contrato con Python está en open_jam/export.py y open_jam/escena.py.

/**
 * @typedef {"uint32" | "uint8" | "int32" | "uint16" | "float32"} Dtype
 * @typedef {{ dtype: Dtype, len: number, offset: number }} Columna
 * @typedef {Record<string, Columna>} IndiceColumnas  columnas del .bin: inicio, tipo, xy, t, v
 */

/**
 * Trayectorias ya decodificadas de una ventana: el vehículo k ocupa los puntos
 * inicio[k] .. inicio[k+1]-1; xy en metros, t en segundos, v en km/h.
 * @typedef {object} Trayectoria
 * @property {number} n  cantidad de vehículos
 * @property {Uint32Array} inicio  n + 1 elementos
 * @property {Uint8Array} tipo  0 carro, 1 moto, 2 bus, 3 camión
 * @property {Float32Array} xy
 * @property {Float32Array} t
 * @property {ArrayLike<number>} v
 */

/**
 * @typedef {object} Ventana
 * @property {number} t0
 * @property {number} t1
 * @property {string} archivo  relativo a la base de datos
 * @property {number} [bytes]
 * @property {string} [sha256]
 * @property {IndiceColumnas} binario
 */

/**
 * @typedef {object} Periodo
 * @property {number} t0
 * @property {number} t1
 * @property {Record<string, boolean>} decisiones  corredor -> semáforos encendidos
 * @property {boolean} [resto]  estado de los semáforos que no son de ningún corredor
 */

/**
 * @typedef {object} Corredor
 * @property {string} id
 * @property {string} nombre
 * @property {number[]} calles  índices en red.calles
 * @property {string[]} semaforos  ids de TLS
 */

/**
 * @typedef {{ id: string, x: number, y: number, n: string }} Semaforo
 * @typedef {{ id: string, p: number[], l: number, n: string, w: number, k?: number }} Calle
 * @typedef {{ origen: number[], bbox: number[], calles: Calle[], semaforos: Semaforo[], corredores: Corredor[] }} Red
 */

/**
 * @typedef {object} EscenarioManifest
 * @property {string} id
 * @property {string} titulo
 * @property {string} meta  ruta del meta.json
 */

/**
 * @typedef {object} Manifest
 * @property {number} version  versión del formato (1)
 * @property {string} red
 * @property {string} escena
 * @property {string} terreno
 * @property {EscenarioManifest[]} escenarios
 */

/**
 * Lo que el visor usa de un <id>/meta.json, ya normalizado.
 * @typedef {object} Escenario
 * @property {string} id
 * @property {string} titulo
 * @property {string} [politica]
 * @property {any} metricas  métricas de la corrida (open_jam/metricas.py)
 * @property {{ t: number, n: number, kmh: number, parados: number }[]} curva
 * @property {Ventana[]} ventanas
 * @property {Periodo[]} periodos
 * @property {number} fin  segundos simulados
 */

export {};

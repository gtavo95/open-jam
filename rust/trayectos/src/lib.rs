//! Simplificación de trayectorias en espacio-tiempo (ver open_jam/trayectos.py).
//! Cada vehículo es independiente, así que se reparten entre hilos con rayon.

use numpy::PyReadonlyArray1;
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use rayon::prelude::*;

const MAX_VENTANA: usize = 64; // igual que en open_jam/trayectos.py

fn un_vehiculo(t: &[f32], x: &[f32], y: &[f32], tol2: f32, keep: &mut [u8]) {
    let n = t.len();
    if n == 0 {
        return;
    }
    keep[0] = 1;
    keep[n - 1] = 1;
    let mut ancla = 0;
    let mut j = 2;
    while j < n {
        let dt = t[j] - t[ancla];
        let (ax, ay) = (x[ancla], y[ancla]);
        let (vx, vy) = (x[j] - ax, y[j] - ay);
        let fuera = (ancla + 1..j).any(|k| {
            let f = if dt > 0.0 { (t[k] - t[ancla]) / dt } else { 0.0 }; // igual que la referencia en Python
            let dx = ax + f * vx - x[k];
            let dy = ay + f * vy - y[k];
            dx * dx + dy * dy > tol2
        });
        // Ventana máxima: acota el costo (cuadrático) en vehículos parados mucho tiempo.
        if fuera || j - ancla > MAX_VENTANA {
            ancla = j - 1;
            keep[ancla] = 1;
        }
        j += 1;
    }
}

/// Devuelve un byte por punto: 1 si se conserva.
#[pyfunction]
fn simplificar<'py>(
    py: Python<'py>,
    t: PyReadonlyArray1<'py, f32>,
    x: PyReadonlyArray1<'py, f32>,
    y: PyReadonlyArray1<'py, f32>,
    inicio: PyReadonlyArray1<'py, u32>,
    tol: f64,
) -> PyResult<Bound<'py, PyBytes>> {
    let (t, x, y, inicio) = (t.as_slice()?, x.as_slice()?, y.as_slice()?, inicio.as_slice()?);
    let tol2 = (tol * tol) as f32;
    let mut keep = vec![0u8; t.len()];
    py.allow_threads(|| {
        // Partir `keep` en un trozo por vehículo para escribir en paralelo sin locks.
        let mut trozos = Vec::with_capacity(inicio.len().saturating_sub(1));
        let mut resto: &mut [u8] = &mut keep;
        for w in inicio.windows(2) {
            let (a, b) = (w[0] as usize, w[1] as usize);
            let (cab, cola) = resto.split_at_mut(b - a);
            trozos.push((a, b, cab));
            resto = cola;
        }
        trozos.into_par_iter().for_each(|(a, b, k)| un_vehiculo(&t[a..b], &x[a..b], &y[a..b], tol2, k));
    });
    Ok(PyBytes::new(py, &keep))
}

#[pymodule]
fn trayectos_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(simplificar, m)?)
}

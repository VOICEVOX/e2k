use pyo3::prelude::*;
use pyo3::types::PyDict;

fn extract_strategy(strategy: &str, kwargs: Option<&Bound<'_, PyDict>>) -> PyResult<e2k::Strategy> {
    return Ok(match strategy {
        "greedy" => {
            error_on_extra_args(kwargs, &[])?;

            e2k::Strategy::Greedy
        }
        "top_k" => {
            error_on_extra_args(kwargs, &["k"])?;

            let k = kwargs
                .map(|kwargs| kwargs.get_item("k"))
                .transpose()?
                .flatten()
                .map(|k| k.extract::<usize>())
                .transpose()?;

            let mut strategy = e2k::StrategyTopK::default();
            if let Some(k) = k {
                strategy.k = k;
            }

            e2k::Strategy::TopK(strategy)
        }
        "top_p" => {
            error_on_extra_args(kwargs, &["p", "t"])?;

            let top_p = kwargs
                .map(|kwargs| kwargs.get_item("p"))
                .transpose()?
                .flatten()
                .map(|top_p| top_p.extract::<f32>())
                .transpose()?;

            let temperature = kwargs
                .map(|kwargs| kwargs.get_item("t"))
                .transpose()?
                .flatten()
                .map(|temperature| temperature.extract::<f32>())
                .transpose()?;

            let mut strategy = e2k::StrategyTopP::default();
            if let Some(top_p) = top_p {
                strategy.top_p = top_p;
            }
            if let Some(temperature) = temperature {
                strategy.temperature = temperature;
            }

            e2k::Strategy::TopP(strategy)
        }
        _ => {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "strategy must be one of 'greedy', 'top_k', 'top_p'",
            ));
        }
    });

    fn error_on_extra_args(kwargs: Option<&Bound<'_, PyDict>>, expected: &[&str]) -> PyResult<()> {
        if let Some(kwargs) = kwargs {
            let keys = kwargs.iter().map(|item| item.0).collect::<Vec<_>>();
            let keys = keys
                .iter()
                .map(|key| key.extract::<String>())
                .collect::<Result<Vec<_>, _>>()?;

            let extra_keys = keys
                .iter()
                .map(|key| key.as_str())
                .filter(|&key| !expected.contains(&key))
                .collect::<Vec<_>>();

            if !extra_keys.is_empty() {
                return Err(pyo3::exceptions::PyTypeError::new_err(format!(
                    "unexpected keyword argument(s): {}",
                    extra_keys.join(", ")
                )));
            }
        }
        Ok(())
    }
}

#[pyclass(frozen)]
struct C2k {
    inner: std::sync::RwLock<e2k::C2k>,
}

#[pymethods]
impl C2k {
    #[new]
    #[pyo3(signature = (max_length = 32, strategy = "greedy", **kwargs))]
    fn new(
        max_length: usize,
        strategy: &str,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Self> {
        let strategy = extract_strategy(strategy, kwargs)?;
        Ok(Self {
            inner: std::sync::RwLock::new(
                e2k::C2k::new()
                    .with_max_length(max_length)
                    .with_strategy(strategy),
            ),
        })
    }

    fn __call__(&self, src: &str) -> String {
        self.inner.read().unwrap().infer(src)
    }
}

#[pymodule(name = "voicevox_e2k")]
fn voicevox_e2k(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<C2k>()?;

    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("KANAS", e2k::KANAS)?;
    m.add("ASCII_ENTRIES", e2k::ASCII_ENTRIES)?;

    Ok(())
}

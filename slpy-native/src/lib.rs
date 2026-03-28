/// slpy-native — Rust masking engine for slpy
///
/// Exposes a single Python class: `NativeMaskingEngine`
/// Same interface as slpy's Python MaskingEngine — drop-in replacement.
///
///     engine = NativeMaskingEngine(enable_default_rules=True)
///     engine.add_rule(pattern, strategy, mask_char='*')
///     result = engine.process(data)   # data: dict|list
///
/// Strategies: "email", "credit_card", "ssn", "phone", "password", "token", "full"

use once_cell::sync::Lazy;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use regex::Regex;
use std::collections::HashMap;

// ---------------------------------------------------------------------------
// Default patterns — compiled once at module load
// ---------------------------------------------------------------------------
static DEFAULT_RULES: Lazy<Vec<(Regex, Strategy)>> = Lazy::new(|| {
    vec![
        (re(r"(?i)(?:credit|card|cc|payment).*?(?:number|num|id)"), Strategy::CreditCard),
        (re(r"(?i)(?:ssn|social|security).*?(?:number|num)"),       Strategy::Ssn),
        (re(r"(?i)(?:email|mail|e-mail)"),                           Strategy::Email),
        (re(r"(?i)(?:phone|tel|mobile|cell).*?(?:number|num)"),      Strategy::Phone),
        (re(r"(?i)(?:password|pass|pwd|secret)"),                    Strategy::Full),
        (re(r"(?i)(?:token|key|auth|jwt|bearer)"),                   Strategy::Full),
    ]
});

fn re(pat: &str) -> Regex {
    Regex::new(pat).expect("invalid default pattern")
}

// ---------------------------------------------------------------------------
// Strategy
// ---------------------------------------------------------------------------
#[derive(Clone, Debug)]
enum Strategy {
    Email,
    CreditCard,
    Ssn,
    Phone,
    Full,
}

impl Strategy {
    fn from_str(s: &str) -> Self {
        match s {
            "email"       => Strategy::Email,
            "credit_card" => Strategy::CreditCard,
            "ssn"         => Strategy::Ssn,
            "phone"       => Strategy::Phone,
            _             => Strategy::Full,
        }
    }
}

fn apply(value: &str, strategy: &Strategy, mask_char: char) -> String {
    match strategy {
        Strategy::Full => mask_char.to_string().repeat(value.len()),

        Strategy::Email => {
            if let Some(at) = value.find('@') {
                let user = &value[..at];
                let domain = &value[at..];
                let masked = if user.len() > 2 {
                    format!(
                        "{}{}{}",
                        &user[..1],
                        mask_char.to_string().repeat(user.len() - 2),
                        &user[user.len() - 1..]
                    )
                } else {
                    mask_char.to_string().repeat(user.len())
                };
                format!("{}{}", masked, domain)
            } else {
                mask_char.to_string().repeat(value.len())
            }
        }

        Strategy::CreditCard | Strategy::Ssn | Strategy::Phone => {
            let digits: String = value.chars().filter(|c| c.is_ascii_digit()).collect();
            if digits.len() >= 4 {
                let last4 = &digits[digits.len() - 4..];
                format!("{}{}", mask_char.to_string().repeat(digits.len() - 4), last4)
            } else {
                mask_char.to_string().repeat(value.len())
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Flat value — either a string (maskable) or an opaque Python object
// ---------------------------------------------------------------------------
enum Flat {
    Str(String),
    Obj(PyObject),
}

// ---------------------------------------------------------------------------
// Flatten any dict/list into a dotted-key → Flat map
// ---------------------------------------------------------------------------
fn flatten(obj: &Bound<'_, PyAny>, prefix: &str, out: &mut HashMap<String, Flat>) -> PyResult<()> {
    if let Ok(dict) = obj.downcast::<PyDict>() {
        for (k, v) in dict.iter() {
            let key = k.str()?.to_string();
            let path = if prefix.is_empty() { key } else { format!("{}.{}", prefix, key) };
            flatten(&v, &path, out)?;
        }
    } else if let Ok(list) = obj.downcast::<PyList>() {
        for (i, v) in list.iter().enumerate() {
            let path = if prefix.is_empty() { i.to_string() } else { format!("{}.{}", prefix, i) };
            flatten(&v, &path, out)?;
        }
    } else if let Ok(s) = obj.extract::<String>() {
        out.insert(prefix.to_string(), Flat::Str(s));
    } else {
        out.insert(prefix.to_string(), Flat::Obj(obj.clone().unbind()));
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Unflatten dotted-key map back into a nested PyDict
// ---------------------------------------------------------------------------
fn unflatten<'py>(py: Python<'py>, flat: &HashMap<String, Flat>) -> PyResult<Bound<'py, PyDict>> {
    let mut keys: Vec<&String> = flat.keys().collect();
    keys.sort();

    let root = PyDict::new(py);
    for key in keys {
        let parts: Vec<&str> = key.split('.').collect();
        let mut node = root.clone().into_any();
        for part in &parts[..parts.len() - 1] {
            let next = if let Ok(d) = node.downcast::<PyDict>() {
                match d.get_item(part)? {
                    Some(existing) => existing,
                    None => {
                        let new_d = PyDict::new(py);
                        d.set_item(part, &new_d)?;
                        new_d.into_any()
                    }
                }
            } else {
                break;
            };
            node = next;
        }
        let last = parts[parts.len() - 1];
        if let Ok(d) = node.downcast::<PyDict>() {
            match &flat[key] {
                Flat::Str(s) => d.set_item(last, s)?,
                Flat::Obj(o) => d.set_item(last, o.bind(py))?,
            }
        }
    }
    Ok(root)
}

// ---------------------------------------------------------------------------
// NativeMaskingEngine — exposed to Python
// ---------------------------------------------------------------------------
struct Rule {
    pattern: Regex,
    strategy: Strategy,
    mask_char: char,
}

#[pyclass]
struct NativeMaskingEngine {
    rules: Vec<Rule>,
}

#[pymethods]
impl NativeMaskingEngine {
    #[new]
    #[pyo3(signature = (enable_default_rules = true))]
    fn new(enable_default_rules: bool) -> Self {
        let mut rules = Vec::new();
        if enable_default_rules {
            for (re, strategy) in DEFAULT_RULES.iter() {
                rules.push(Rule {
                    pattern: re.clone(),
                    strategy: strategy.clone(),
                    mask_char: '*',
                });
            }
        }
        NativeMaskingEngine { rules }
    }

    #[pyo3(signature = (pattern, strategy, mask_char = '*', preserve_length = true))]
    fn add_rule(
        &mut self,
        pattern: &str,
        strategy: &str,
        mask_char: char,
        preserve_length: bool,
    ) -> PyResult<()> {
        let _ = preserve_length; // API parity with Python engine
        let re = Regex::new(pattern)
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
        self.rules.push(Rule {
            pattern: re,
            strategy: Strategy::from_str(strategy),
            mask_char,
        });
        Ok(())
    }

    fn process<'py>(&self, py: Python<'py>, data: &Bound<'py, PyAny>) -> PyResult<PyObject> {
        if !data.is_instance_of::<PyDict>() && !data.is_instance_of::<PyList>() {
            return Ok(data.clone().unbind());
        }

        let mut flat: HashMap<String, Flat> = HashMap::new();
        flatten(data, "", &mut flat)?;

        for (key, value) in flat.iter_mut() {
            if let Flat::Str(s) = value {
                let leaf = key.rsplit('.').next().unwrap_or(key.as_str());
                for rule in &self.rules {
                    if rule.pattern.is_match(leaf) {
                        *value = Flat::Str(apply(s, &rule.strategy, rule.mask_char));
                        break;
                    }
                }
            }
        }

        Ok(unflatten(py, &flat)?.into_any().unbind())
    }
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------
#[pymodule]
fn slpy_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<NativeMaskingEngine>()?;
    Ok(())
}

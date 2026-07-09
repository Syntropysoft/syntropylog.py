/// slpy-native — Rust masking engine for slpy
///
/// Exposes a single Python class: `NativeMaskingEngine`
/// Same interface AND same semantics as slpy's Python MaskingEngine — a
/// drop-in twin. The two engines must never diverge: masking is BY FIELD
/// NAME, matched on each dict key on the way down; once a key matches,
/// everything beneath it is masked (nested dicts, lists, and non-string
/// scalars included).
///
///     engine = NativeMaskingEngine(enable_default_rules=True, max_depth=10)
///     engine.add_rule(pattern, strategy, mask_char='*')
///     result = engine.process(data)   # data: dict|list
///
/// Strategies: "email", "credit_card", "ssn", "phone", "password", "token", "full"

use once_cell::sync::Lazy;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};
use regex::Regex;

// ---------------------------------------------------------------------------
// Default patterns — compiled once at module load
// ---------------------------------------------------------------------------
// Kept in lockstep with slpy/masking.py _DEFAULT_RULES — loose suffix patterns
// for derived names + anchored alternates for the bare aliases.
static DEFAULT_RULES: Lazy<Vec<(Regex, Strategy)>> = Lazy::new(|| {
    vec![
        (re(r"(?i)(?:credit|card|cc|payment).*?(?:number|num|id)|^(?i)(?:credit_?card|card_?number)$"), Strategy::CreditCard),
        (re(r"(?i)(?:ssn|social|security).*?(?:number|num)|^(?i)(?:ssn|social_?security)$"),            Strategy::Ssn),
        (re(r"(?i)(?:email|mail|e-mail)"),                                                               Strategy::Email),
        (re(r"(?i)(?:phone|tel|mobile|cell).*?(?:number|num)|^(?i)(?:phone|mobile|tel|cell)$"),          Strategy::Phone),
        (re(r"(?i)(?:password|pass|pwd|secret)"),                                                        Strategy::Full),
        (re(r"(?i)(?:token|key|auth|jwt|bearer)"),                                                       Strategy::Full),
    ]
});

fn re(pat: &str) -> Regex {
    Regex::new(pat).expect("invalid default pattern")
}

// ReDoS guard — rules only ever run against field NAMES; cap the input.
const MAX_KEY_LEN: usize = 256;

// Fixed-width replacement when the depth budget runs out under a sensitive key.
const EXHAUSTED_MASK_LEN: usize = 6;

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
        Strategy::Full => mask_char.to_string().repeat(value.chars().count()),

        Strategy::Email => {
            if let Some(at) = value.find('@') {
                let user = &value[..at];
                let domain = &value[at..];
                let user_len = user.chars().count();
                let masked = if user_len > 2 {
                    let chars: Vec<char> = user.chars().collect();
                    format!(
                        "{}{}{}",
                        chars[0],
                        mask_char.to_string().repeat(user_len - 2),
                        chars[user_len - 1]
                    )
                } else {
                    mask_char.to_string().repeat(user_len)
                };
                format!("{}{}", masked, domain)
            } else {
                mask_char.to_string().repeat(value.chars().count())
            }
        }

        Strategy::CreditCard | Strategy::Ssn | Strategy::Phone => {
            let digits: String = value.chars().filter(|c| c.is_ascii_digit()).collect();
            if digits.len() >= 4 {
                let last4 = &digits[digits.len() - 4..];
                format!("{}{}", mask_char.to_string().repeat(digits.len() - 4), last4)
            } else {
                mask_char.to_string().repeat(value.chars().count())
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Rules
// ---------------------------------------------------------------------------
struct Rule {
    pattern: Regex,
    strategy: Strategy,
    mask_char: char,
}

/// First rule whose pattern matches the (length-capped) field name.
fn find_rule<'a>(rules: &'a [Rule], key: &str) -> Option<&'a Rule> {
    let name: String = key.chars().take(MAX_KEY_LEN).collect();
    rules.iter().find(|r| r.pattern.is_match(&name))
}

/// Mask a scalar. Non-strings are stringified first; None passes through.
fn mask_leaf(py: Python<'_>, value: &Bound<'_, PyAny>, rule: &Rule) -> PyResult<Py<PyAny>> {
    if value.is_none() {
        return Ok(py.None());
    }
    let text = match value.extract::<String>() {
        Ok(s) => s,
        Err(_) => value.str()?.to_string(),
    };
    Ok(apply(&text, &rule.strategy, rule.mask_char).into_pyobject(py)?.into_any().unbind())
}

/// Recursively mask a structure. `active` is the rule inherited from the
/// closest matching ancestor key; a deeper key matching its own rule
/// overrides it. Mirrors slpy.masking._mask_tree exactly.
fn mask_tree(
    py: Python<'_>,
    value: &Bound<'_, PyAny>,
    rules: &[Rule],
    active: Option<&Rule>,
    depth: u32,
) -> PyResult<Py<PyAny>> {
    if depth == 0 {
        return match active {
            None => Ok(value.clone().unbind()),
            Some(rule) => Ok(rule
                .mask_char
                .to_string()
                .repeat(EXHAUSTED_MASK_LEN)
                .into_pyobject(py)?
                .into_any()
                .unbind()),
        };
    }
    if let Ok(dict) = value.cast::<PyDict>() {
        let out = PyDict::new(py);
        for (k, v) in dict.iter() {
            let key = k.str()?.to_string();
            let rule = find_rule(rules, &key).or(active);
            out.set_item(k, mask_tree(py, &v, rules, rule, depth - 1)?)?;
        }
        return Ok(out.into_any().unbind());
    }
    if let Ok(list) = value.cast::<PyList>() {
        let items = list
            .iter()
            .map(|v| mask_tree(py, &v, rules, active, depth - 1))
            .collect::<PyResult<Vec<_>>>()?;
        return Ok(PyList::new(py, items)?.into_any().unbind());
    }
    if let Ok(tuple) = value.cast::<PyTuple>() {
        let items = tuple
            .iter()
            .map(|v| mask_tree(py, &v, rules, active, depth - 1))
            .collect::<PyResult<Vec<_>>>()?;
        return Ok(PyList::new(py, items)?.into_any().unbind());
    }
    match active {
        None => Ok(value.clone().unbind()),
        Some(rule) => mask_leaf(py, value, rule),
    }
}

// ---------------------------------------------------------------------------
// NativeMaskingEngine — exposed to Python
// ---------------------------------------------------------------------------
#[pyclass]
struct NativeMaskingEngine {
    rules: Vec<Rule>,
    max_depth: u32,
}

#[pymethods]
impl NativeMaskingEngine {
    #[new]
    #[pyo3(signature = (enable_default_rules = true, max_depth = 10))]
    fn new(enable_default_rules: bool, max_depth: u32) -> Self {
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
        NativeMaskingEngine { rules, max_depth }
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
        let re = Regex::new(&format!("(?i){}", pattern))
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
        self.rules.push(Rule {
            pattern: re,
            strategy: Strategy::from_str(strategy),
            mask_char,
        });
        Ok(())
    }

    fn process<'py>(&self, py: Python<'py>, data: &Bound<'py, PyAny>) -> PyResult<Py<PyAny>> {
        if !data.is_instance_of::<PyDict>() && !data.is_instance_of::<PyList>() {
            return Ok(data.clone().unbind());
        }
        mask_tree(py, data, &self.rules, None, self.max_depth)
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

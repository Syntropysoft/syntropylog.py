/// slpy-native — Rust masking engine for slpy
///
/// Exposes a single Python class: `NativeMaskingEngine`
/// Same interface AND same semantics as slpy's Python MaskingEngine — a
/// drop-in twin. The two engines must never diverge: masking is BY FIELD
/// NAME, matched on each dict key on the way down; once a key matches,
/// everything beneath it is masked (nested dicts, lists, and non-string
/// scalars included).
///
///     engine = NativeMaskingEngine(max_depth=10)
///     engine.add_rule(pattern, redact=False, unmask_start=1, keep_after='@', ...)
///     result = engine.process(data)   # data: dict|list
///
/// This engine does NOT know what a strategy is and does NOT carry a rule
/// table of its own. Python owns both — it resolves every strategy into a
/// MaskSpec and pushes every rule, defaults included. There is one rule list
/// and one strategy→spec mapping in the project, so neither can drift; what
/// crosses the boundary is already data. `ENGINE_API` is the contract version:
/// slpy refuses an addon that does not match rather than run weaker semantics.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};
use regex::Regex;
use std::collections::HashSet;

/// Bumped whenever the boundary changes shape. slpy checks it at import and
/// falls back to the Python engine on a mismatch — an addon from an older
/// wheel must never silently apply different semantics.
const ENGINE_API: u32 = 2;

// ReDoS guard — rules only ever run against field NAMES; cap the input.
const MAX_KEY_LEN: usize = 256;

// Fixed-width replacement when the depth budget runs out under a sensitive key.
const EXHAUSTED_MASK_LEN: usize = 6;

// ---------------------------------------------------------------------------
// Declarative masking primitive
// ---------------------------------------------------------------------------
// ONE parameterized masker, mirrored by apply_mask() in slpy/mask_spec.py and
// by the family's canonical pair (SyntropyLog's maskSpec.ts and its Rust
// addon). The shared fixture tests/mask-parity-cases.json is asserted against
// both slpy engines, so adding a strategy is data, never code.

/// Replacement for fully redacted values; must equal REDACTED in slpy/mask_spec.py.
const REDACTED: &str = "[REDACTED]";

/// Cap for the masked run when preserve_length is false (does not reveal the length).
const MASK_DEFAULT_CAP_LENGTH: usize = 8;

/// A masking instruction expressed as data. Built-in strategies (email, card, …)
/// are presets that Python expands into one of these before it crosses.
#[derive(Clone, Debug)]
struct MaskSpec {
    /// Replace the whole value with [REDACTED] (credentials). Wins over everything else.
    redact: bool,
    /// Keep the first N units (chars, or digits when scope = "digits").
    unmask_start: usize,
    /// Keep the last N units.
    unmask_end: usize,
    /// "digits" → only mask digit characters (separators kept); otherwise mask all chars.
    scope: Option<String>,
    /// Keep everything from the first occurrence of this delimiter onward (an email domain).
    keep_after: Option<String>,
    mask_char: String,
    preserve_length: bool,
}

/// Mask all characters of `s` except the first `start` and last `end`.
/// When `preserve_length` is false the masked run is capped (does not reveal exact length).
fn mask_chars(s: &str, start: usize, end: usize, mask_char: &str, preserve_length: bool) -> String {
    let chars: Vec<char> = s.chars().collect();
    let n = chars.len();
    let keep_start = start.min(n);
    let keep_end = end.min(n - keep_start);
    let masked_count = n - keep_start - keep_end;
    let body_len = if preserve_length {
        masked_count
    } else {
        masked_count.min(MASK_DEFAULT_CAP_LENGTH)
    };
    let prefix: String = chars[..keep_start].iter().collect();
    let suffix: String = chars[n - keep_end..].iter().collect();
    format!("{}{}{}", prefix, mask_char.repeat(body_len), suffix)
}

/// Mask only the digit characters of `s` except the first `start` and last `end` digits,
/// preserving every non-digit (separators, '+', spaces). Always length-preserving.
fn mask_digits(s: &str, start: usize, end: usize, mask_char: &str) -> String {
    let chars: Vec<char> = s.chars().collect();
    let digit_positions: Vec<usize> = chars
        .iter()
        .enumerate()
        .filter(|(_, c)| c.is_ascii_digit())
        .map(|(i, _)| i)
        .collect();
    let d = digit_positions.len();
    let keep_start = start.min(d);
    let keep_end = end.min(d - keep_start);
    let masked: HashSet<usize> = digit_positions[keep_start..d - keep_end]
        .iter()
        .copied()
        .collect();
    chars
        .iter()
        .enumerate()
        .map(|(i, c)| {
            if masked.contains(&i) {
                mask_char.to_string()
            } else {
                c.to_string()
            }
        })
        .collect()
}

/// Split `value` into the head to mask and the verbatim tail kept from `delim` onward.
fn split_kept_tail<'a>(value: &'a str, delim: Option<&str>) -> (&'a str, &'a str) {
    let Some(delim) = delim else {
        return (value, "");
    };
    if delim.is_empty() {
        return (value, "");
    }
    match value.find(delim) {
        None => (value, ""),
        Some(idx) => (&value[..idx], &value[idx..]),
    }
}

/// Apply a declarative mask spec to a string. Guard clauses, pure.
fn apply_mask(value: &str, spec: &MaskSpec) -> String {
    if spec.redact {
        return REDACTED.to_string();
    }

    let (head, tail) = split_kept_tail(value, spec.keep_after.as_deref());

    let masked = if spec.scope.as_deref() == Some("digits") {
        mask_digits(head, spec.unmask_start, spec.unmask_end, &spec.mask_char)
    } else {
        mask_chars(
            head,
            spec.unmask_start,
            spec.unmask_end,
            &spec.mask_char,
            spec.preserve_length,
        )
    };

    format!("{}{}", masked, tail)
}

// ---------------------------------------------------------------------------
// Rules
// ---------------------------------------------------------------------------
struct Rule {
    pattern: Regex,
    spec: MaskSpec,
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
    Ok(apply_mask(&text, &rule.spec)
        .into_pyobject(py)?
        .into_any()
        .unbind())
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
                .spec
                .mask_char
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
    /// Starts empty on purpose: Python pushes every rule, defaults included.
    #[new]
    #[pyo3(signature = (max_depth = 10))]
    fn new(max_depth: u32) -> Self {
        NativeMaskingEngine {
            rules: Vec::new(),
            max_depth,
        }
    }

    /// Append a rule: a key pattern (matched case-insensitively, as in Python's
    /// `re.IGNORECASE`) plus the resolved spec. A pattern the Rust `regex` crate
    /// cannot compile raises, and slpy answers by dropping to the Python engine —
    /// never by running with one rule missing.
    #[pyo3(signature = (
        pattern,
        redact = false,
        unmask_start = 0,
        unmask_end = 0,
        scope = None,
        keep_after = None,
        mask_char = "*".to_string(),
        preserve_length = true,
    ))]
    #[allow(clippy::too_many_arguments)]
    fn add_rule(
        &mut self,
        pattern: &str,
        redact: bool,
        unmask_start: usize,
        unmask_end: usize,
        scope: Option<String>,
        keep_after: Option<String>,
        mask_char: String,
        preserve_length: bool,
    ) -> PyResult<()> {
        let re = Regex::new(&format!("(?i){}", pattern))
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
        self.rules.push(Rule {
            pattern: re,
            spec: MaskSpec {
                redact,
                unmask_start,
                unmask_end,
                scope,
                keep_after,
                mask_char,
                preserve_length,
            },
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
    m.add("ENGINE_API", ENGINE_API)?;
    m.add_class::<NativeMaskingEngine>()?;
    Ok(())
}

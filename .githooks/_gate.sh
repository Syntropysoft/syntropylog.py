#!/usr/bin/env sh
# Shared gate for slpy's git hooks. Sourced by pre-commit and pre-push.
#
# Enable:   git config core.hooksPath .githooks
# Disable:  git config --unset core.hooksPath
#
# `core.hooksPath` is per-repo and OVERRIDES a global hooksPath, so whatever a global
# hook was enforcing here stops running the moment this is enabled. That is why
# refuse_on_main lives in this file instead of being assumed from the outside.

REPO_ROOT=$(git rev-parse --show-toplevel)

say() { printf '%s\n' "$*" >&2; }
die() { printf '\n  ✖ %s\n\n' "$*" >&2; exit 1; }

# The published branch is promoted by PR. Escape hatch: SLPY_ALLOW_MAIN=1.
refuse_on_main() {
    branch=$(git symbolic-ref --short -q HEAD || echo "")
    case "$branch" in
        main|master)
            if [ "${SLPY_ALLOW_MAIN:-}" = "1" ]; then
                say "  ! SLPY_ALLOW_MAIN=1 — commit en '$branch' permitido a mano"
                return 0
            fi
            die "estás en '$branch'. Se trabaja en develop y main se promueve por PR.
    Si de verdad va acá: SLPY_ALLOW_MAIN=1 git commit ..."
            ;;
    esac
}

# First interpreter that actually has pytest: SLPY_PYTHON, then the repo's own
# .venv (what `pip install -e '.[dev,fastapi]'` creates), then the PATH.
python_bin() {
    for candidate in "${SLPY_PYTHON:-}" "$REPO_ROOT/.venv/bin/python" python3 python; do
        [ -n "$candidate" ] || continue
        command -v "$candidate" >/dev/null 2>&1 || continue
        "$candidate" -c "import pytest" >/dev/null 2>&1 || continue
        printf '%s' "$candidate"
        return 0
    done
    return 1
}

require_python() {
    python_bin || die "no hay un Python con pytest.
    Armá el entorno del repo (es lo que el hook busca primero):
        python3 -m venv .venv && .venv/bin/pip install -e '.[dev,fastapi]' httpx maturin
    O apuntá al que tengas:  export SLPY_PYTHON=/ruta/al/python"
}

# The turtle this catches: editing slpy-native/src and not rebuilding. The suite
# still passes — against the PREVIOUS wheel — so the parity tests silently assert
# the old binary and the change looks verified when nothing verified it.
gate_native_is_current() {
    staged=$(git diff --cached --name-only --diff-filter=ACMR -- slpy-native/src slpy-native/Cargo.toml)
    [ -n "$staged" ] || return 0

    say "  → slpy-native tocado: cargo check"
    ( cd "$REPO_ROOT/slpy-native" && cargo check --release --quiet ) \
        || die "el gemelo Rust no compila."

    py=$(python_bin) || return 0
    installed=$("$py" -c "import slpy_native, inspect; print(slpy_native.__file__)" 2>/dev/null) || {
        say "  ! slpy-native no está instalado en este entorno: los tests de paridad van a skipear."
        return 0
    }
    newest_source=$(find "$REPO_ROOT/slpy-native/src" "$REPO_ROOT/slpy-native/Cargo.toml" -newer "$installed" 2>/dev/null | head -n 1)
    [ -z "$newest_source" ] && return 0

    die "el wheel instalado es más viejo que slpy-native/src.
    La suite pasaría contra el binario ANTERIOR y los tests de paridad no probarían tu cambio.
    Recompilá:
        .venv/bin/maturin build --release -m slpy-native/Cargo.toml -i .venv/bin/python
        .venv/bin/pip install --force-reinstall slpy-native/target/wheels/*.whl"
}

# $1 = "strict" → un test skipeado también es error (todas las opcionales instaladas).
gate_tests() {
    py=$(require_python)

    say "  → pytest ($py)"
    if ! out=$("$py" -m pytest -q -rs 2>&1); then
        printf '%s\n' "$out" >&2
        die "la suite está en rojo."
    fi
    printf '%s\n' "$out" | tail -n 1 >&2

    case "$out" in
        *skipped*)
            if [ "${1:-}" = "strict" ]; then
                die "la suite skipeó tests. Con todo instalado no debería skipear nada."
            fi
            say "  ! hay tests skipeados: falta alguna opcional (slpy-native / fastapi).
    El lock de deriva entre motores NO corrió acá — lo corre el job parity-native de CI.
    Para correrlo local:  .venv/bin/pip install -e '.[dev,fastapi]' httpx maturin
                          .venv/bin/maturin build --release -m slpy-native/Cargo.toml -i .venv/bin/python
                          .venv/bin/pip install --force-reinstall slpy-native/target/wheels/*.whl"
            ;;
    esac
}

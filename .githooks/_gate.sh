#!/usr/bin/env sh
# Shared gate for slpy's git hooks. Sourced by pre-commit and pre-push.
#
# Enable:   git config core.hooksPath .githooks
# Disable:  git config --unset core.hooksPath
#
# `core.hooksPath` is per-repo and OVERRIDES a global hooksPath, so whatever a global
# hook was enforcing here stops running the moment this is enabled. That is why
# refuse_on_main lives in this file instead of being assumed from the outside.

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

# First interpreter that actually has pytest. SLPY_PYTHON gana si está seteada.
python_bin() {
    for candidate in "${SLPY_PYTHON:-}" python3 python; do
        [ -n "$candidate" ] || continue
        command -v "$candidate" >/dev/null 2>&1 || continue
        "$candidate" -c "import pytest" >/dev/null 2>&1 || continue
        printf '%s' "$candidate"
        return 0
    done
    return 1
}

# $1 = "strict" → un test skipeado también es error (todas las opcionales instaladas).
gate_tests() {
    py=$(python_bin) || die "no hay un Python con pytest en el PATH.
    Instalá el entorno de dev:  pip install -e '.[dev,fastapi]' httpx
    O apuntá al que tengas:     export SLPY_PYTHON=/ruta/al/python"

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
    Para correrlo local:  pip install maturin && maturin build --release -m slpy-native/Cargo.toml
                          pip install --force-reinstall slpy-native/target/wheels/*.whl"
            ;;
    esac
}

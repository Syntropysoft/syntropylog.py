# syntropylog.py (slpy-log) — gate e invariantes del repo

> Ficha que consumen las skills `/sl-*` (nivel usuario). El método vive en la skill; los hechos de
> este repo, acá. Sin esta ficha, la skill se detiene.

## Cómo se trabaja acá (aplica antes que cualquier otra cosa)

- **La frontera es tuya, el código es mío.** Alcance, límites y fronteras — qué entra y qué no, qué
  se niega a hacer la librería, dónde termina su responsabilidad, qué se borra, qué promete el
  contrato — son decisiones del usuario y **se preguntan**. La implementación, los nombres, la
  estructura, los tests y la verificación son del agente: se hacen, no se consultan.
- **El tell, porque una decisión de frontera casi nunca parece una.** Si la respuesta a *"¿por qué
  así?"* es un **principio**, saliste del código y estás moviendo un límite → preguntá. Si es una
  **técnica**, decidí y seguí.
  *"Uso un Map porque el lookup es O(1)"* → técnica, mío.
  *"Devuelvo `null` porque no adivinamos"* → principio, tuyo.
- ❌ NEVER meter código sin análisis previo. Si algo no queda claro, **se pregunta** — no se elige
  la interpretación más razonable y se sigue.
- ✅ ALWAYS **el contexto que aporta el usuario se convierte en test**, no en doc. Un hecho de
  comportamiento — *"esto ya está en producción"*, *"siempre funcionó así"*, *"no cambies esto"* —
  se fija con un test cuyo **nombre** lo enuncia. Un doc se lee si alguien lo busca; un test falla
  cuando alguien lo contradice, sin que nadie recuerde la conversación.
- ❌ NEVER afirmar una negación ("no existe X") sin decir **dónde** se buscó.
- ❌ NEVER borrar porque el archivo destino existe. ✅ ALWAYS comparar **contenido**.
- ❌ NEVER una sonda manual como evidencia: o se vuelve test, o se dice "verificado a mano, sin test".

## Qué es

Puerto Python de SyntropyLog, publicado en PyPI como **`slpy-log`** (paquete importable: `slpy`),
versión `1.0.0`, `requires-python >=3.7`. Propagación sobre `contextvars`/asyncio, middleware
FastAPI opcional, motor de masking en Rust opcional propio.

## Gate

```
pytest                 # asyncio_mode=auto, testpaths=tests (config única: pytest.ini)
python -m build        # solo en publish
```

**Un `pytest` a secas no es el gate completo.** Sin las opcionales da `174 passed, 15 skipped`, y
esos 15 son justamente los que importan: 14 comparan el motor Rust contra el Python (el lock contra
deriva entre motores) y 1 es el middleware FastAPI. Con todo instalado: **197 passed, 0 skipped**.

```
pip install -e '.[dev,fastapi]' httpx
pip install maturin && maturin build --release -m slpy-native/Cargo.toml
pip install --force-reinstall slpy-native/target/wheels/*.whl
```

Desde 2026-08-23 hay `ci.yml` (push + PR): `test` en 3.9/3.11/3.12/3.13, `floor` en 3.7
(`ubuntu-22.04`, el último runner que lo tiene), y `parity-native` con el addon compilado donde
**un skip es un job rojo**. Los mismos chequeos como hooks en `.githooks/`
(`git config core.hooksPath .githooks`).

⚠️ `core.hooksPath` a nivel repo **pisa el global**. Por eso el guard de "no commitear en main" está
replicado dentro del hook del repo y no se asume de afuera.

## Invariantes

- ❌ NEVER tocar `slpy/` sin correr `pytest` local: no hay red.
- ❌ NEVER divergir del modelo de la referencia Node sin registrarlo en `PARITY-ROADMAP.md`.
- ❌ NEVER que un fallo de logging escape al caller.
- ❌ NEVER romper `>=3.7`: es el piso declarado y es viejo a propósito.
- ✅ ALWAYS mantener `py.typed` (declarado en `package-data`) — el paquete promete tipos.

## Gotchas conocidos

**El masking de slpy NO es canónico** (hasta que aterrice 2.0.0). El motor es tabla de estrategias,
no `MaskSpec`, y la salida difiere de JS/Rust/JVM en las cinco estrategias built-in: email
`j**n@` vs `j***@`, tarjeta `************1234` vs `****-****-****-1234`, password `*******` vs
`[REDACTED]`. El fixture compartido `mask-parity-cases.json` **no existe en este repo**. ❌ NEVER
afirmar paridad de masking citando el roadmap viejo: lo afirmaba y era falso. Estado real y
decisión en `PARITY-ROADMAP.md` § *Audit 2026-08-23*.

**`preserve_length` es config muerta** en los dos motores: se acepta en `core.py`, se guarda en
`masking.py` y no la lee nadie (`slpy-native/src/lib.rs`: `let _ = preserve_length;`). Cobra
sentido recién con el spec canónico.

**`docs/` describe una librería que no existe.** `data_masking.md`, `lifecycle.md` y
`logger_matrix.md` son anteriores al refactor y documentan 11 métodos de fachada que nunca se
publicaron. Llevan banner desde 2026-08-23. Fuente correcta hoy: `README.md` y el código.
`slpy-refactor-plan.md` es histórico y se queda.

**Config de pytest desduplicada** (2026-08-23): `pytest.ini` es la única fuente; el bloque
`[tool.pytest.ini_options]` de `pyproject.toml` era config muerta y se borró.

## Fuente de verdad del estado

`PARITY-ROADMAP.md` → `CHANGELOG.md` → `pyproject.toml`.

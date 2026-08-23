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
- ❌ NEVER mezclar cálculo y efecto cuando se pueden separar. ✅ ALWAYS la **decisión** en una
  función pura a nivel módulo (`apply_mask`, `strategy_to_spec`, `_mask_tree`, `RetentionRegistry.stamp`)
  y el **efecto** — escribir al transport, tocar un contador — en el borde que la llama. Guard
  clauses primero: el fail-path sale arriba, sin `else`. SOLID sobre `Transport`: se extiende
  agregando un sink, no tocando el logger; y una estrategia de masking nueva es **un spec**, no una
  función en dos lenguajes.
  **El límite, explícito:** el estado mutable que queda es deliberado y chico — la caché de
  decisiones del masking, que se pasa como **parámetro explícito** a las funciones puras en vez de
  vivir en el módulo, y los contadores de `SlpyStats`. La regla no es "nada muta": es que lo que se
  *calcula* salga de funciones puras, y lo que *muta* sea un borde nombrado y justificado.

## Gotchas conocidos

**El masking es canónico desde 2026-08-23 y hay UNA sola fuente de cada cosa.** El mapeo
estrategia→spec vive en `strategy_to_spec()` (`slpy/masking.py`) y en ningún otro lado; el motor
Rust **no sabe qué es una estrategia** y tampoco tiene tabla de reglas propia — Python le empuja
todas, defaults incluidos, ya resueltas a `MaskSpec`. ❌ NEVER agregar una estrategia tocando los
dos lenguajes: es un spec nuevo y nada más. El contrato lo fija `tests/mask-parity-cases.json`,
copia byte a byte de la familia — ❌ NEVER editarlo acá: se edita en la familia y se copia.

**El borde con el addon está versionado.** `ENGINE_API` (hoy `2`) tiene que coincidir con
`_REQUIRED_ENGINE_API` en `slpy/masking.py`; si no, slpy cae al motor Python en vez de correr uno
cuyas semánticas no puede garantizar. Cambió la forma del borde → se bumpea el número.

**Trampa de la transliteración:** `str.isdigit()` NO es `is_ascii_digit()` (`'²'`, `'٣'` son
digit). `_is_ascii_digit` en `slpy/mask_spec.py` es explícito por eso, y los 17 casos del fixture
son todos ASCII, así que **el fixture no atrapa esta deriva** — la atrapa
`test_non_ascii_digits_do_not_diverge`.

**`preserve_length` dejó de ser config muerta** (2026-08-23): la interpreta `apply_mask` y capa el
tramo enmascarado en `MASK_DEFAULT_CAP_LENGTH = 8`. No aplica a `password`/`token`, que redactan
entero — y ahí `mask_char` **también** se ignora, a propósito.

**`docs/` describe una librería que no existe.** `data_masking.md`, `lifecycle.md` y
`logger_matrix.md` son anteriores al refactor y documentan 11 métodos de fachada que nunca se
publicaron. Llevan banner desde 2026-08-23. Fuente correcta hoy: `README.md` y el código.
`slpy-refactor-plan.md` es histórico y se queda.

**Config de pytest desduplicada** (2026-08-23): `pytest.ini` es la única fuente; el bloque
`[tool.pytest.ini_options]` de `pyproject.toml` era config muerta y se borró.

## Fuente de verdad del estado

`PARITY-ROADMAP.md` → `CHANGELOG.md` → `pyproject.toml`.

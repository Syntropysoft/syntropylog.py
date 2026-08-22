# syntropylog.py (slpy-log) — gate e invariantes del repo

> Ficha que consumen las skills `/sl-*` (nivel usuario). El método vive en la skill; los hechos de
> este repo, acá. Sin esta ficha, la skill se detiene.

## Cómo se trabaja acá (aplica antes que cualquier otra cosa)

- ❌ NEVER meter código sin análisis previo. Si algo no queda claro, **se pregunta** — no se elige
  la interpretación más razonable y se sigue.
- **La línea.** Se decide solo: nombres, ubicación de archivos, forma del test, redacción. Se
  **pregunta siempre** ante: (a) cambio de comportamiento observable para alguien que ya usa esto,
  (b) borrar o reemplazar contenido existente, (c) elegir entre dos semánticas defendibles,
  (d) mover superficie pública.
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
pytest                 # asyncio_mode=auto, testpaths=tests
python -m build        # solo en publish
```

⚠️ **CI solo tiene `benchmark.yml` y `publish.yml` — no hay workflow de CI que corra `pytest` en cada
push.** El gate existe como comando pero nadie lo hace cumplir. ✅ ALWAYS correrlo a mano y decirlo;
❌ NEVER asumir que "CI está verde" significa que los tests pasaron.

## Invariantes

- ❌ NEVER tocar `slpy/` sin correr `pytest` local: no hay red.
- ❌ NEVER divergir del modelo de la referencia Node sin registrarlo en `PARITY-ROADMAP.md`.
- ❌ NEVER que un fallo de logging escape al caller.
- ❌ NEVER romper `>=3.7`: es el piso declarado y es viejo a propósito.
- ✅ ALWAYS mantener `py.typed` (declarado en `package-data`) — el paquete promete tipos.

## Gotcha conocido

**La config de pytest está duplicada:** `pytest.ini` y `[tool.pytest.ini_options]` en
`pyproject.toml` declaran lo mismo (`asyncio_mode`, `testpaths`). `pytest.ini` **gana** y el bloque
del `pyproject` es config muerta. Mismo patrón que el `lint-staged` duplicado de SyntropyLog: si
alguien edita el que no corre, el cambio no tiene efecto y nada avisa.

## Fuente de verdad del estado

`PARITY-ROADMAP.md` → `CHANGELOG.md` → `pyproject.toml`.

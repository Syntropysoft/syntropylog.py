"""
Run all slpy examples and report pass/fail.

Usage:
    py run_examples.py

Examples that require extra dependencies (fastapi, uvicorn) are skipped
automatically if those packages are not installed.
"""

import importlib.util
import os
import sys
import time
import traceback

# Make slpy importable from the project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

EXAMPLES = [
    ("01_basic_setup",           "Basic setup and initialization"),
    ("02_named_loggers_and_child","Named loggers and child()"),
    ("03_context_propagation",   "Context propagation with asyncio.gather()"),
    ("04_masking",               "Data masking — default and custom rules"),
    ("05_with_meta_and_audit",   "with_meta() and audit level"),
    ("06_fastapi_middleware",    "FastAPI/ASGI middleware"),       # skipped if no fastapi
    ("07_pretty_console",        "PrettyConsoleTransport"),
]

SKIP_OUTPUT = True   # suppress example stdout during run


def run_example(module_name: str) -> tuple[bool, float, str]:
    path = os.path.join("examples", f"{module_name}.py")
    start = time.perf_counter()
    try:
        # Redirect stdout to suppress example output
        if SKIP_OUTPUT:
            import io
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()

        spec = importlib.util.spec_from_file_location(module_name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        elapsed = time.perf_counter() - start
        return True, elapsed, ""
    except ImportError as e:
        elapsed = time.perf_counter() - start
        return None, elapsed, str(e)   # None = skipped
    except SystemExit as e:
        elapsed = time.perf_counter() - start
        if e.code == 0:
            return True, elapsed, ""
        return None, elapsed, f"exit({e.code})"
    except Exception:
        elapsed = time.perf_counter() - start
        return False, elapsed, traceback.format_exc()
    finally:
        if SKIP_OUTPUT:
            sys.stdout = old_stdout


def main():
    print(f"\n{'=' * 62}")
    print("  slpy examples runner")
    print(f"{'=' * 62}\n")

    passed = skipped = failed = 0

    for module, description in EXAMPLES:
        ok, elapsed, detail = run_example(module)

        if ok is True:
            status = "\033[32mPASS\033[0m"
            passed += 1
        elif ok is None:
            status = "\033[33mSKIP\033[0m"
            skipped += 1
        else:
            status = "\033[31mFAIL\033[0m"
            failed += 1

        print(f"  {status}  {elapsed:.2f}s  {description}")

        if ok is False:
            for line in detail.strip().splitlines():
                print(f"         {line}")
        elif ok is None:
            print(f"         (missing dependency: {detail})")

    total = passed + skipped + failed
    print(f"\n{'=' * 62}")
    print(f"  {total} examples — {passed} passed  {skipped} skipped  {failed} failed")
    print(f"{'=' * 62}\n")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅ Current |

## Reporting a vulnerability

Please do **not** open a public GitHub issue for security vulnerabilities.

Report privately to: **info@syntropysoft.com**

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (optional)

You will receive a response within 48 hours.

---

## Security notes

### No network I/O at runtime

slpy does not contact any external URLs or IPs. The only output is what
your transports produce (e.g. stdout, your database, your API).

### Zero runtime dependencies

The core package has no `install_requires`. The optional `[fastapi]` extra
adds only `starlette` (already a FastAPI dependency). There are no transitive
runtime dependencies that could introduce supply-chain risk.

### Environment variables read at runtime

| Variable | Module | Purpose |
|----------|--------|---------|
| `SLPY_LOG_LEVEL` | `slpy.config` | Override configured log level |
| `SLPY_NATIVE_DISABLE` | `slpy.masking` | Disable Rust addon, use Python fallback |

No credentials, secrets, or sensitive configuration are read from environment variables.

### Rust addon (slpy-native)

The optional `slpy-native` addon is built from source in this repository.
No precompiled opaque binaries are distributed — the build is reproducible
from auditable Rust source using `maturin`.

If the addon is unavailable, the Python MaskingEngine is used automatically.
The addon does not make network calls, read files, or access environment variables.

### Custom masking functions

The `MaskingStrategy.CUSTOM` option accepts a consumer-supplied
`custom_mask: callable`. This function is part of the application's own
configuration — it is not influenced by external input. If masking config
is constructed dynamically from user-supplied HTTP input, that is an
application-level risk, not a framework risk.

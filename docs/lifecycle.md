# SyntropyLog Python - Lifecycle Management

> ⚠️ **Stale — this document predates the slpy refactor and does not describe the shipped library.**
>
> It documents a facade that does not exist (`syntropy_log.add_shutdown_handler`,
> `syntropy_log.get_status`, module-level `syntropy_log.info`). The real lifecycle is
> `await slpy.init(config)` → `slpy.get_logger(name)` → `await slpy.shutdown()`, with
> `slpy.is_initialized` as the only status accessor (`slpy/core.py`).
>
> Rewrite tracked in `PARITY-ROADMAP.md`.


## 🎯 Overview

El ciclo de vida del framework SyntropyLog Python está diseñado para manejar **singletons de recursos pesados** de manera segura, asegurando que todos los recursos se liberen correctamente durante el shutdown graceful.

## 🏗️ Arquitectura del Ciclo de Vida

### 1. Singleton Pattern

```python
# El framework expone un singleton global
from syntropylog import syntropy_log

# Todas las instancias creadas por init() son singletons:
# - Logger instance
# - Redis client  
# - HTTP clients
# - Broker clients
# - Serializers
# - Transports
# - Context manager
```

### 2. Inicialización (init)

```python
await syntropy_log.init({
    'logger': {'level': 'info'},
    'redis': {'url': 'redis://localhost:6379'},
    'http': {'correlation': True},
    'brokers': {'kafka': {'bootstrap_servers': 'localhost:9092'}}
})
```

**Orden de inicialización:**
1. Configuration management
2. Context management  
3. Logger system
4. HTTP instrumentation
5. Redis integration
6. Message brokers
7. Serialization pipeline

### 3. Shutdown Graceful

```python
# Shutdown manual
result = await syntropy_log.shutdown()

# O automático via signal handlers
# SIGINT (Ctrl+C) y SIGTERM (Kubernetes)
```

## 🚨 Manejo de Señales

### Signal Handlers Automáticos

El framework registra automáticamente handlers para:

- **SIGINT** (Ctrl+C) - Desarrollo
- **SIGTERM** (Kubernetes) - Producción

```python
# En __init__.py se registran automáticamente
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)
```

### Shutdown con Timeout

```python
async def _graceful_shutdown_with_timeout(timeout: int = 30):
    """Shutdown con timeout de 30 segundos por defecto."""
    try:
        shutdown_task = asyncio.create_task(syntropy_log.shutdown())
        result = await asyncio.wait_for(shutdown_task, timeout=timeout)
        return result
    except asyncio.TimeoutError:
        print(f"⚠️  Shutdown timeout after {timeout}s. Forcing exit...")
        return {"success": False, "error": "shutdown_timeout"}
```

## 🔄 Proceso de Shutdown

### Orden de Shutdown (Reverse Order)

```python
components_to_shutdown = [
    ("serialization", self._serialization, 10.0),  # 10s timeout
    ("brokers", self._brokers, 15.0),              # 15s timeout  
    ("redis", self._redis, 10.0),                  # 10s timeout
    ("http", self._http, 10.0),                    # 10s timeout
    ("logger", self._logger, 5.0),                 # 5s timeout
    ("context", self._context, 5.0),               # 5s timeout
]
```

### Timeouts Individuales

Cada componente tiene su propio timeout para evitar que un componente lento bloquee todo el shutdown:

- **Serialization**: 10 segundos
- **Brokers**: 15 segundos (más tiempo para cerrar conexiones)
- **Redis**: 10 segundos
- **HTTP**: 10 segundos
- **Logger**: 5 segundos
- **Context**: 5 segundos

### Shutdown Handlers Personalizados

```python
async def my_custom_cleanup():
    """Cleanup personalizado."""
    await close_database_connections()
    await flush_cache()
    await notify_monitoring()

# Registrar handler
syntropy_log.add_shutdown_handler(my_custom_cleanup)
```

## 📊 Monitoreo del Estado

### Status Information

```python
status = syntropy_log.get_status()

# Retorna:
{
    "initialized": True,
    "components": {
        "config": {"available": True, "type": "ConfigManager"},
        "context": {"available": True, "type": "ContextManager"},
        "logger": {"available": True, "type": "Logger"},
        "http": {"available": True, "type": "HttpManager"},
        "redis": {"available": True, "type": "BeaconRedis"},
        "brokers": {"available": False, "type": None},
        "serialization": {"available": True, "type": "SerializationManager"}
    },
    "shutdown_handlers": 2
}
```

### Shutdown Result

```python
result = await syntropy_log.shutdown()

# Retorna:
{
    "success": True,
    "errors": [],
    "components_shutdown": ["serialization", "redis", "http", "logger", "context"],
    "start_time": 1640995200.123,
    "end_time": 1640995200.456,
    "duration": 0.333
}
```

## 🐳 Kubernetes Integration

### Graceful Shutdown en Kubernetes

El framework está optimizado para Kubernetes:

1. **SIGTERM**: Kubernetes envía SIGTERM
2. **Grace Period**: Framework tiene 30 segundos para shutdown
3. **SIGKILL**: Si no termina, Kubernetes envía SIGKILL

```python
# El signal handler maneja esto automáticamente
def _signal_handler(signum: int, frame: Any) -> None:
    if _shutdown_in_progress:
        print("Forcing exit...")
        sys.exit(1)  # Exit inmediato si ya está shutdown
    
    _shutdown_in_progress = True
    # Inicia shutdown graceful
```

### Health Checks

```python
# Verificar si el framework está saludable
if syntropy_log.is_initialized:
    status = syntropy_log.get_status()
    if status["initialized"] and all(c["available"] for c in status["components"].values()):
        return {"status": "healthy"}
    else:
        return {"status": "unhealthy", "details": status}
```

## 🧪 Testing del Ciclo de Vida

### Ejemplo Completo

```python
#!/usr/bin/env python3
import asyncio
from syntropylog import syntropy_log

async def main():
    # Initialize
    await syntropy_log.init({
        'logger': {'level': 'info'},
        'context': {'correlation_enabled': True}
    })
    
    # Use framework
    syntropy_log.info("Application started")
    
    # Add custom shutdown handler
    async def cleanup():
        print("Cleaning up...")
    
    syntropy_log.add_shutdown_handler(cleanup)
    
    # Graceful shutdown
    result = await syntropy_log.shutdown()
    print(f"Shutdown result: {result}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Testing Signal Handling

```python
# En desarrollo, presionar Ctrl+C
# En producción, Kubernetes envía SIGTERM automáticamente

# Para testing manual:
import os
import signal
os.kill(os.getpid(), signal.SIGTERM)
```

## 🚀 Best Practices

### 1. Siempre Usar Shutdown Graceful

```python
try:
    await syntropy_log.init(config)
    # ... tu aplicación ...
finally:
    await syntropy_log.shutdown()
```

### 2. Registrar Shutdown Handlers

```python
# Para recursos externos
async def cleanup_database():
    await db.close()

syntropy_log.add_shutdown_handler(cleanup_database)
```

### 3. Monitorear Estado

```python
# En health checks
status = syntropy_log.get_status()
if not status["initialized"]:
    # Framework no está listo
    pass
```

### 4. Manejar Timeouts

```python
# Si el shutdown tarda mucho, puede ser un problema
result = await syntropy_log.shutdown()
if result.get("duration", 0) > 10:
    # Investigar por qué tarda tanto
    pass
```

## 🔧 Troubleshooting

### Shutdown Timeout

Si el shutdown tarda más de 30 segundos:

1. **Revisar logs**: Ver qué componente está tardando
2. **Verificar conexiones**: Redis, HTTP, brokers
3. **Shutdown handlers**: Verificar que no se cuelguen
4. **Timeouts**: Ajustar timeouts si es necesario

### Memory Leaks

Si hay memory leaks:

1. **Verificar cleanup**: Todos los componentes deben implementar `shutdown()`
2. **Shutdown handlers**: Asegurar que liberen recursos
3. **Context cleanup**: Verificar que el context se limpie

### Kubernetes Issues

Si Kubernetes mata el pod:

1. **Grace period**: Aumentar si es necesario
2. **Health checks**: Verificar que respondan correctamente
3. **Signal handling**: Verificar que SIGTERM se maneje

---

**SyntropyLog Python** - Lifecycle Management optimizado para producción 🚀
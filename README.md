# SyntropyLog Python

<p align="center">
  <img src="./assets/syntropysoft-logo.png" alt="SyntropySoft Logo" width="170"/>
</p>

<h1 align="center">SyntropyLog Python</h1>

<p align="center">
  <strong>From Chaos to Clarity</strong>
  <br />
  The Observability Framework for High-Performance Python Applications
</p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/status-alpha-orange.svg" alt="Alpha"></a>
  <a href="https://github.com/Syntropysoft/SyntropyLog/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.7+-blue.svg" alt="Python 3.7+"></a>
  <a href="#"><img src="https://img.shields.io/badge/async-await-green.svg" alt="Async/Await"></a>
</p>

---

🚀 **Ultra-fast observability framework with automatic correlation - Just 1 line of code!**

SyntropyLog Python provides comprehensive observability for your Python applications with automatic context propagation, correlation IDs, and ultra-fast logging performance.

## 🎯 Propósito

SyntropyLog Python es la implementación en Python del framework de observabilidad SyntropyLog, manteniendo la misma filosofía y patrones del framework Node.js.

## 🏗️ Arquitectura Base

### Componentes Principales

**1. Lifecycle Management**
- `init()` - Inicialización del framework
- `shutdown()` - Cierre graceful con limpieza de recursos
- Manejo de señales SIGINT/SIGTERM

**2. Context Management**
- Propagación automática de contexto
- Correlation IDs automáticos
- Context threading para operaciones asíncronas

**3. Logger System**
- Niveles de logging configurables
- Transports múltiples (console, file, HTTP)
- Formatters personalizables
- Filosofía "Silent Observer"

**4. HTTP Instrumentation**
- Wrappers para clientes HTTP
- Correlation automática de requests
- Interceptores para frameworks web

**5. Redis Integration**
- BeaconRedis para correlación
- Context storage automático
- Operaciones asíncronas

**6. Message Brokers**
- Kafka, RabbitMQ, NATS
- Correlation automática de mensajes
- Producers y consumers instrumentados

**7. Serialization Pipeline**
- Custom serializers
- Pipeline configurable
- Timeout handling

**8. Configuration System**
- Schema validation
- Environment-based config
- Type hints completos

**9. Testing Framework**
- Mocks agnósticos
- Framework compatible (pytest, unittest)
- Spy injection pattern

## 🎯 Filosofía "Silent Observer"

### Principios Fundamentales

**1. No interrumpir el flujo principal**
```python
# ✅ Correcto - La aplicación continúa
try:
    result = database.query('SELECT * FROM users')
    logger.info('Query successful', count=len(result))
except Exception as error:
    # La aplicación maneja el error normalmente
    logger.error('Database error', error=str(error))
    # Lógica de negocio continúa...
```

**2. Reportar sin lanzar excepciones**
- Los errores del logging se reportan via metadata
- No se lanzan excepciones que interrumpan la aplicación
- Graceful degradation cuando algo falla

**3. Observador silencioso**
- El framework observa y reporta
- No toma decisiones por la aplicación
- No modifica el comportamiento del código

### 🏗️ Arquitectura de Singletons

**Todas las instancias creadas por `init()` son singletons:**
```python
# Al inicializar
await syntropy_log.init(config)

# Se crean singletons de:
- Logger instance
- Redis client
- HTTP clients
- Broker clients
- Serializers
- Transports
- Context manager
```

**Reglas de singleton:**
- **Clientes complejos** (HTTP, Redis, Brokers) **NO se pueden redefinir**
- Una vez creados, permanecen hasta `shutdown()`
- Evita conflictos y comportamientos inesperados

### 🔧 Configuración en Caliente

**1. Reglas de enmascaramiento - Solo agregar:**
```python
# ✅ Se puede agregar en caliente
syntropy_log.add_masking_rule('password', r'password:\s*\w+')

# ❌ NO se puede modificar/eliminar reglas existentes
# (workaround por diseño)
```

**2. Nivel de log - Cambio en caliente:**
```python
# Se puede cambiar en cualquier momento
syntropy_log.set_log_level('debug')
syntropy_log.set_log_level('info')
syntropy_log.set_log_level('warn')
```

**3. Matrix de contexto - Modificación libre:**
```python
# Se puede modificar a placer
syntropy_log.add_context('user_id', '123')
syntropy_log.remove_context('temp_data')
syntropy_log.update_context('session_id', 'new_session')
```

### 🔄 Pipeline de Logger

**El logger hace su trabajo sin preocuparse por nada más:**

**1. Pipeline no puede interferir:**
```python
# El logger procesa y continúa
logger.info('User action', user_id='123')
# Si el pipeline falla, el logger no se entera
# La aplicación continúa normalmente
```

**2. Fallo de pipeline:**
```python
# Si una pieza del pipeline falla:
# 1. La pieza informa del error (via metadata)
# 2. Se pone en estado "error"
# 3. El resto del pipeline NO se ejecuta
# 4. El logger continúa sin problemas
# 5. La aplicación no se entera
```

**3. Estados del pipeline:**
```python
class PipelineStep:
    def process(self, data):
        try:
            # Procesar datos
            return processed_data
        except Exception as error:
            # 1. Informar error (no lanzar)
            self.report_error(error)
            # 2. Poner en estado error
            self.set_error_state()
            # 3. Retornar None (pipeline se detiene)
            return None
```

## 🔄 Compatibilidad Cross-Platform

### Estrategia de Compatibilidad

**Serializers Compatibles**
```python
# Python - Mismo serializer que Node.js
class UserSerializer:
    def process(self, data):
        return {
            'id': data.get('id'),
            'name': data.get('name'),
            'email': data.get('email')
        }
```

```javascript
// Node.js - MISMO serializer
class UserSerializer {
    process(data) {
        return {
            id: data.id,
            name: data.name,
            email: data.email
        };
    }
}
```

**Transports Compatibles**
- Console transport - Mismo formato en ambos
- File transport - Mismo formato de archivo
- HTTP transport - Misma estructura de payload
- Custom transports - Misma interfaz

**Configuración Unificada**
```yaml
# Misma config para ambos frameworks
serializers:
  user: UserSerializer
  order: OrderSerializer

transports:
  console: true
  file: logs/app.log
```

## 🚀 Patrones de Uso

### 1. Boilerplate Patterns
```python
# Inicialización
async def initialize_syntropy_log():
    await syntropy_log.init(config)
    return syntropy_log

# Shutdown graceful
async def graceful_shutdown():
    await syntropy_log.shutdown()
    return {"success": True}
```

### 2. Context Patterns
```python
# Propagación automática
async def create_user(user_data):
    with syntropy_log.context(user_id=user_data['id']):
        # Todo el código aquí hereda el contexto
        result = await user_service.create(user_data)
        logger.info('User created', user_id=result.id)
        return result
```

### 3. Testing Patterns
```python
# Framework agnóstico
def test_user_creation():
    test_helper = create_test_helper(pytest.fn)  # o unittest.mock
    test_helper.before_each()
    
    result = user_service.create_user(user_data)
    assert result.user_id is not None
```

### 4. Production Patterns
```python
# Configuración production
config = {
    'logger': {
        'level': 'info',
        'transports': ['console', 'file']
    },
    'redis': {
        'url': os.getenv('REDIS_URL')
    },
    'http': {
        'correlation': True
    }
}
```

## 🛠️ Herramientas y Conceptos

### Type Hints
```python
from typing import Dict, Any, Optional

class Serializer:
    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        pass

class Transport:
    def send(self, entry: Dict[str, Any]) -> None:
        pass
```

### Async/Await
```python
import asyncio

class BeaconRedis:
    async def set(self, key: str, value: Any) -> None:
        pass
    
    async def get(self, key: str) -> Optional[Any]:
        pass
```

### Configuration Management
```python
from pydantic import BaseModel

class LoggerConfig(BaseModel):
    level: str = "info"
    transports: List[str] = ["console"]
    formatters: Dict[str, Any] = {}
```

### Error Handling
```python
# Silent Observer approach
def safe_serialize(data):
    try:
        return serializer.process(data)
    except Exception as error:
        # Reportar pero no lanzar
        logger.error('Serialization failed', error=str(error))
        return None  # Fallback graceful
```

## 📊 Performance Optimization

### Objetivos de Performance
- **45,000+ ops/sec** - Mismo target que Node.js
- **< 1ms latency** - Overhead mínimo
- **Memory efficient** - Footprint reducido
- **Async operations** - No blocking

### Bundle Size
- **Main bundle** - Solo código de producción
- **Testing bundle** - Mocks separados
- **Optional features** - Imports condicionales

## 🧪 Testing Strategy

### Framework Agnostic
```python
# Funciona con pytest, unittest, nose
def create_test_helper(spy_fn):
    return TestHelper(spy_fn)

# Spy injection
mock_redis = BeaconRedisMock(pytest.fn)
mock_http = MockHttpClient(pytest.fn)
```

### Coverage Goals
- **90%+ test coverage** - Mismo target que Node.js
- **Unit tests** - Cada componente
- **Integration tests** - Flujos completos
- **Performance tests** - Benchmarks

## 🎯 Decisiones Técnicas

### Python vs Go

**Python elegido porque:**
- **Ecosistema inmenso** - Requests, FastAPI, Django, Flask
- **Adopción masiva** - Más desarrolladores Python que Go
- **DX superior** - Más fácil de usar y entender
- **Testing ecosystem** - pytest, unittest, coverage
- **Serialización** - JSON, YAML, Pickle (muy potente)

**Analogía:**
- **Go = Ferrari/McLaren** - Velocidad extrema, precisión de ingeniería
- **Python = Camioneta 4x4 anfibia** - Va a todos lados, carga de todo, sobrevive en cualquier ambiente

### Compatibilidad Strategy

**"Backward compatibility + New interfaces"**
- Crear interfaces nuevas cuando hay problemas
- Mantener las viejas funcionando
- Migración gradual sin romper nada
- Deprecación suve con warnings

## 📚 Estructura del Proyecto

```
syntropylog.py/
├── syntropylog/
│   ├── __init__.py
│   ├── core.py              # Lifecycle management
│   ├── context.py           # Context propagation
│   ├── logger.py            # Logger system
│   ├── http/                # HTTP instrumentation
│   ├── redis/               # Redis integration
│   ├── brokers/             # Message brokers
│   ├── serialization/       # Serialization pipeline
│   ├── config.py            # Configuration system
│   └── testing/             # Testing framework
├── tests/                   # Test suite
├── examples/                # Usage examples
├── docs/                    # Documentation
├── setup.py                 # Package setup
├── pyproject.toml           # Project configuration
└── README.md               # This file
```

## 🚀 Roadmap

### Fase 1: Core Framework
- [ ] Lifecycle management
- [ ] Context propagation
- [ ] Logger system básico
- [ ] Configuration system

### Fase 2: Integrations
- [ ] HTTP instrumentation
- [ ] Redis integration
- [ ] Serialization pipeline
- [ ] Testing framework

### Fase 3: Advanced Features
- [ ] Message brokers
- [ ] Advanced transports
- [ ] Performance optimization
- [ ] Production patterns

### Fase 4: Ecosystem
- [ ] Compatibilidad con Node.js
- [ ] Shared serializers/transports
- [ ] Unified configuration
- [ ] Cross-platform examples

## 🎯 Objetivos Finales

1. **Framework completo** - Misma funcionalidad que Node.js
2. **Compatibilidad total** - Serializers y transports compartidos
3. **Performance equivalente** - Mismos targets de performance
4. **DX superior** - Fácil de usar y adoptar
5. **Ecosistema unificado** - Node.js + Python working together

---

**SyntropyLog Python** - From Chaos to Clarity, ahora en Python 🐍 
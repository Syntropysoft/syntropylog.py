# SyntropyLog Python - Logger Matrix

> ⚠️ **Stale — this document predates the slpy refactor and does not describe the shipped library.**
>
> It documents a facade that does not exist (`syntropy_log.add_context`,
> `add_context_with_matrix`, `configure_logger_matrix`, module-level `syntropy_log.debug/info/error`).
> The real API is the `logging_matrix` key in `init()`, the async scope
> `async with slpy.context(**fields)`, and `slpy.reconfigure_logging_matrix()` for runtime changes
> (`slpy/core.py`, `slpy/matrix.py`).
>
> Rewrite tracked in `PARITY-ROADMAP.md`.


## 🎯 Overview

La **Logger Matrix** es un sistema inteligente de filtrado de contexto que permite controlar exactamente qué campos se incluyen en los logs, evitando la contaminación con objetos kilométricos y campos innecesarios.

## 🚨 El Problema

### Sin Logger Matrix (Problema Actual)
```python
# ❌ PROBLEMA: Todo se imprime
syntropy_log.add_context('user_id', '12345')
syntropy_log.add_context('http_headers', {
    'User-Agent': 'Mozilla/5.0...',
    'Accept': 'text/html,application/xhtml+xml...',
    'Accept-Language': 'en-US,en;q=0.9...',
    # ... 50 headers más
})
syntropy_log.add_context('request_body', {
    'data': '...',  # Objeto de 10MB
    'metadata': {...}  # Objeto anidado infinito
})

syntropy_log.info('User action')
# Output: Log con 50 headers + objeto de 10MB = INUTILIZABLE
```

### Con Logger Matrix (Solución)
```python
# ✅ SOLUCIÓN: Solo lo importante se imprime
syntropy_log.configure_logger_matrix(
    include_fields=['user_id', 'action'],
    exclude_fields=['http_headers', 'request_body']
)

syntropy_log.add_context('user_id', '12345')
syntropy_log.add_context('http_headers', {...})  # Se excluye automáticamente
syntropy_log.add_context('request_body', {...})  # Se excluye automáticamente

syntropy_log.info('User action')
# Output: Solo user_id y action = LIMPIO Y ÚTIL
```

## 🏗️ Arquitectura de la Logger Matrix

### Componentes Principales

1. **Include Fields** - Campos que SIEMPRE se incluyen
2. **Exclude Fields** - Campos que NUNCA se incluyen
3. **Level Matrices** - Reglas por nivel de log
4. **Sanitización** - Limpieza automática de objetos grandes

### Configuración Básica

```python
syntropy_log.configure_logger_matrix(
    include_fields=['user_id', 'session_id', 'correlation_id'],
    exclude_fields=['internal_data', 'temp_vars', 'debug_info'],
    max_object_depth=3,
    max_field_length=1000
)
```

## 🎛️ Métodos de Control

### 1. Configuración Estática

```python
# Configurar matrix al inicializar
config = {
    'context': {
        'logger_matrix': {
            'include_fields': ['user_id', 'correlation_id'],
            'exclude_fields': ['internal_debug'],
            'max_object_depth': 2,
            'max_field_length': 500
        }
    }
}

await syntropy_log.init(config)
```

### 2. Configuración Dinámica

```python
# Cambiar matrix en tiempo de ejecución
syntropy_log.configure_logger_matrix(
    include_fields=['user_id', 'new_field'],
    exclude_fields=['old_field']
)
```

### 3. Control Granular

```python
# Agregar contexto con control específico
syntropy_log.add_context_with_matrix(
    'public_data', 
    'visible in logs', 
    include_in_logs=True
)

syntropy_log.add_context_with_matrix(
    'private_data', 
    'hidden from logs', 
    include_in_logs=False
)
```

## 📊 Filtrado por Nivel de Log

### Matrices por Nivel

```python
syntropy_log.configure_logger_matrix(
    level_matrices={
        'debug': ['user_id', 'session_id', 'debug_info', 'all_fields'],
        'info': ['user_id', 'action', 'status'],
        'warn': ['user_id', 'warning_code'],
        'error': ['user_id', 'error_code', 'error_message']
    }
)
```

### Comportamiento por Nivel

- **DEBUG**: Máximo detalle (todos los campos)
- **INFO**: Información esencial (campos principales)
- **WARN**: Información de advertencia (mínimo)
- **ERROR**: Información de error (crítico)

## 🧹 Sanitización Automática

### Objetos Grandes

```python
# Objeto grande se convierte en:
large_dict = {f'key_{i}': f'value_{i}' for i in range(50)}
# Output: "<large_object:50_fields>"
```

### Arrays Grandes

```python
# Array grande se convierte en:
large_array = [f'item_{i}' for i in range(100)]
# Output: "<large_array:100_items>"
```

### Objetos Anidados

```python
# Objeto anidado profundo:
complex_object = {
    'level1': {
        'level2': {
            'level3': {
                'level4': 'data'  # Se trunca en level3
            }
        }
    }
}
# Output: "<max_depth_reached:dict>"
```

### Strings Largos

```python
# String largo se trunca:
long_string = "x" * 2000
# Output: "xxxxx... (truncado a 1000 caracteres)"
```

## 🎯 Casos de Uso

### 1. API REST

```python
# Configuración para APIs
syntropy_log.configure_logger_matrix(
    include_fields=['user_id', 'endpoint', 'method', 'status_code'],
    exclude_fields=['request_body', 'response_body', 'headers'],
    level_matrices={
        'info': ['user_id', 'endpoint', 'method', 'status_code'],
        'error': ['user_id', 'endpoint', 'error_code', 'error_message']
    }
)

# Uso
syntropy_log.add_context('user_id', '12345')
syntropy_log.add_context('endpoint', '/api/users')
syntropy_log.add_context('method', 'POST')
syntropy_log.add_context('request_body', large_json)  # Se excluye automáticamente

syntropy_log.info('API request')
# Output: Solo user_id, endpoint, method, status_code
```

### 2. Base de Datos

```python
# Configuración para DB
syntropy_log.configure_logger_matrix(
    include_fields=['user_id', 'table', 'operation'],
    exclude_fields=['query_params', 'result_set'],
    level_matrices={
        'info': ['user_id', 'table', 'operation'],
        'warn': ['user_id', 'table', 'query_time'],
        'error': ['user_id', 'table', 'error_code', 'error_message']
    }
)
```

### 3. Microservicios

```python
# Configuración para microservicios
syntropy_log.configure_logger_matrix(
    include_fields=['service_name', 'correlation_id', 'user_id'],
    exclude_fields=['internal_state', 'temp_data'],
    level_matrices={
        'debug': ['service_name', 'correlation_id', 'user_id', 'debug_info'],
        'info': ['service_name', 'correlation_id', 'action'],
        'error': ['service_name', 'correlation_id', 'error_code']
    }
)
```

## 🔧 Configuración Avanzada

### Límites Personalizables

```python
syntropy_log.configure_logger_matrix(
    max_object_depth=5,      # Profundidad máxima de objetos
    max_field_length=2000    # Longitud máxima de campos
)
```

### Matrices Dinámicas

```python
# Cambiar matrix según el contexto
async def process_request(request_data):
    # Matrix para requests
    syntropy_log.configure_logger_matrix(
        include_fields=['request_id', 'user_id'],
        exclude_fields=['request_body']
    )
    
    # Procesar request...
    
    # Matrix para responses
    syntropy_log.configure_logger_matrix(
        include_fields=['request_id', 'user_id', 'status'],
        exclude_fields=['response_body']
    )
```

## 📈 Performance

### Optimizaciones

1. **Filtrado en Memoria** - No hay I/O durante el filtrado
2. **Caché de Reglas** - Las reglas se compilan una vez
3. **Sanitización Lazy** - Solo se sanitiza cuando se necesita
4. **Thread-Safe** - Operaciones concurrentes seguras

### Benchmarks

```python
# Sin Logger Matrix: ~1000 ops/sec
# Con Logger Matrix: ~950 ops/sec (5% overhead)
# Beneficio: Logs 90% más pequeños y útiles
```

## 🚀 Best Practices

### 1. Configurar al Inicializar

```python
# ✅ Correcto
config = {
    'context': {
        'logger_matrix': {
            'include_fields': ['user_id', 'correlation_id'],
            'exclude_fields': ['internal_data']
        }
    }
}
await syntropy_log.init(config)
```

### 2. Usar Niveles Apropiados

```python
# ✅ Correcto
syntropy_log.debug('Debug info', debug_data=large_object)
syntropy_log.info('User action', user_id='123', action='login')
syntropy_log.error('Error occurred', error_code='E001')
```

### 3. Excluir Datos Sensibles

```python
# ✅ Correcto
syntropy_log.configure_logger_matrix(
    exclude_fields=['password', 'token', 'secret_key', 'private_data']
)
```

### 4. Revisar Periódicamente

```python
# ✅ Correcto
# Revisar logs y ajustar matrix según necesidades
syntropy_log.configure_logger_matrix(
    include_fields=['new_important_field'],
    exclude_fields=['no_longer_needed_field']
)
```

## 🔍 Troubleshooting

### Logs Muy Grandes

```python
# Problema: Logs con objetos kilométricos
# Solución: Configurar exclude_fields
syntropy_log.configure_logger_matrix(
    exclude_fields=['large_object', 'debug_data', 'temp_vars']
)
```

### Información Faltante

```python
# Problema: Falta información importante
# Solución: Agregar a include_fields
syntropy_log.configure_logger_matrix(
    include_fields=['user_id', 'correlation_id', 'missing_field']
)
```

### Performance Degradada

```python
# Problema: Matrix muy compleja
# Solución: Simplificar reglas
syntropy_log.configure_logger_matrix(
    include_fields=['essential_field'],
    exclude_fields=['unnecessary_field']
)
```

---

**SyntropyLog Python** - Logger Matrix para logs limpios y útiles 🧹✨
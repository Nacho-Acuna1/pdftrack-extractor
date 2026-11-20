# pdftrack-extractor

Microservicio independiente y autónomo de extracción de texto de documentos PDF a Markdown estructurado por páginas.

Forma parte del ecosistema **PDFtrack** compuesto por cuatro repositorios desacoplados (`pdftrack-extractor`, `pdftrack-documents`, `pdftrack-proxy`, `pdftrack-deploy`). Este microservicio es completamente **stateless**, no tiene persistencia en disco ni conexión a bases de datos, y no conoce ni depende de ningún otro servicio.

---

## Características y Arquitectura Interna

- **Zero-Copy IPC con SharedMemory**: El payload PDF recibido en memoria nunca se serializa via `pickle` para transferirlo al proceso worker. Se aloja en un segmento `multiprocessing.shared_memory.SharedMemory` y al worker solo se le comunica el nombre del segmento y su tamaño en bytes. PyMuPDF abre directamente el stream en memoria (`shm.buf[:size]`). La liberación del segmento (`close()` y `unlink()`) se realiza en un bloque `finally` protegido contra cancelaciones mediante `asyncio.shield`.
- **Aislamiento en ProcessPoolExecutor**: Las operaciones de parsing y extracción de PyMuPDF se ejecutan en un pool de procesos dedicado para no bloquear el event loop asíncrono de Uvicorn. El pool se inicializa en el arranque y se apaga de forma limpia en el shutdown (`lifespan`).
- **Backpressure determinista**: Control de admisión basado en `asyncio.Semaphore(EXTRACTION_WORKERS + EXTRACTION_QUEUE_SIZE)`. Si no hay slots libres, el semáforo rechaza la petición inmediatamente con HTTP `503 Service Unavailable` y cabecera `Retry-After: 1`. La adquisición se intenta **antes** de leer el body de la petición para evitar consumo innecesario de memoria.
- **Timeout de extracción**: Si la extracción supera `EXTRACTION_TIMEOUT_SECONDS`, la tarea se cancela y se responde HTTP `504 Gateway Timeout`.
- **Validaciones estrictas**: Valida magic bytes `%PDF` (HTTP 415), archivo vacío (HTTP 400), tamaño máximo (HTTP 413) y errores de parsing (HTTP 422).
- **Structured JSON Logging**: Logs estructurados en formato JSON emitidos directamente a `stdout` con campos `timestamp`, `level`, `service`, `method`, `path`, `status_code` y `duration_ms`.
- **Cumplimiento Twelve-Factor App**:
  - **Factor I (Codebase)**: Repositorio único para este servicio.
  - **Factor II (Dependencies)**: Dependencias declaradas estrictamente en `pyproject.toml`, bloqueadas con `uv.lock` y exportadas a `requirements.txt`.
  - **Factor III (Config)**: Configuración estricta vía variables de entorno mediante `pydantic-settings`.
  - **Factor V (Build, release, run)**: Dockerfile multi-stage (builder con `uv`, runtime minimalista sin herramientas de build).
  - **Factor VI (Processes)**: Completamente stateless; sin archivos temporales en disco.
  - **Factor VII (Port binding)**: `entrypoint.py` enlaza dinámicamente al puerto definido por la variable `PORT`. Dockerfile utiliza `ARG PORT_ARG=8000` y `EXPOSE ${PORT_ARG}`.
  - **Factor VIII (Concurrency)**: Escalabilidad horizontal mediante réplicas externas de contenedores.
  - **Factor IX (Disposability)**: Cierre limpio de procesos (`SIGTERM`) y liberación garantizada de memoria compartida con `stop_grace_period` recomendado de 35s.
  - **Factor XI (Logs)**: Logs como flujo de eventos JSON a `stdout`.

---

## Endpoints

### 1. `POST /extract`
Extrae el texto de un PDF y lo formatea a Markdown página por página.

- **Entrada soportada**:
  - `multipart/form-data`: archivo en el campo `file`.
  - Binario directo: `Content-Type: application/pdf` o `application/octet-stream` con los bytes del PDF en el body.
- **Respuesta exitosa** (`200 OK`):
  ```json
  {
    "content": "## Página 1\n\nTexto de la primera página...\n\n## Página 2\n\nTexto de la segunda página...",
    "page_count": 2
  }
  ```
- **Errores posibles**:
  - `400 Bad Request`: Archivo vacío o campo `file` ausente en multipart.
  - `413 Payload Too Large`: Archivo excede `MAX_PDF_SIZE_MB`.
  - `415 Unsupported Media Type`: El archivo no inicia con magic bytes `%PDF`.
  - `422 Unprocessable Entity`: Error al procesar o parsear el documento PDF.
  - `503 Service Unavailable`: Servicio saturado por backpressure (incluye header `Retry-After: 1`).
  - `504 Gateway Timeout`: La extracción superó el tiempo límite configurado.

### 2. `GET /health/live`
Liveness probe para orquestadores (Kubernetes/Docker).
- **Respuesta** (`200 OK`): `{"status": "alive"}`

### 3. `GET /health/ready`
Readiness probe. Verifica que el `ProcessPoolExecutor` esté inicializado y operativo.
- **Respuesta** (`200 OK`): `{"status": "ready"}`
- **Respuesta** (`503 Service Unavailable`): `{"status": "not ready"}`

### 4. `GET /docs`
Documentación interactiva Swagger UI generada automáticamente por FastAPI.

---

## Variables de Entorno

| Variable | Tipo | Default | Descripción |
| :--- | :---: | :---: | :--- |
| `PORT` | `int` | `8000` | Puerto TCP en el que escucha el servicio |
| `EXTRACTION_WORKERS` | `int` | `1` | Cantidad de procesos en el `ProcessPoolExecutor` |
| `EXTRACTION_QUEUE_SIZE` | `int` | `1` | Capacidad de cola concurrente antes de activar backpressure (503) |
| `QUEUE_WAIT_TIMEOUT_SECONDS` | `float` | `0` | Tiempo de espera por un slot en el semáforo (0 = no bloqueante) |
| `EXTRACTION_TIMEOUT_SECONDS` | `float` | `30` | Timeout máximo para la extracción de un PDF antes de cancelar (504) |
| `MAX_PDF_SIZE_MB` | `int` | `50` | Tamaño máximo permitido del PDF en megabytes |
| `LOG_LEVEL` | `str` | `INFO` | Nivel de logging (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## Desarrollo Local

### Prerrequisitos
- Python `>= 3.12`
- [uv](https://astral.sh/uv) como gestor de paquetes y entornos virtuales.

### 1. Inicializar e instalar dependencias
```bash
uv sync --all-extras
```

### 2. Ejecutar la suite de tests
```bash
uv run pytest -v
```

### 3. Ejecutar el microservicio localmente
```bash
uv run python -m extractor.entrypoint
```

O asignando un puerto personalizado:
```bash
PORT=8080 uv run python -m extractor.entrypoint
```

---

## Docker

### Build de la imagen
```bash
docker build -t pdftrack-extractor:latest .
```

Con puerto alternativo en build:
```bash
docker build --build-arg PORT_ARG=8080 -t pdftrack-extractor:latest .
```

### Ejecutar contenedor
```bash
docker run --rm -p 8000:8000 \
  -e PORT=8000 \
  -e EXTRACTION_WORKERS=2 \
  -e EXTRACTION_QUEUE_SIZE=4 \
  --stop-timeout 35 \
  pdftrack-extractor:latest
```

---

## Ejemplos de Uso con cURL

### Extracción vía Multipart (campo `file`)
```bash
curl -X POST "http://localhost:8000/extract" \
  -F "file=@documento.pdf"
```

### Extracción vía Binario Directo
```bash
curl -X POST "http://localhost:8000/extract" \
  -H "Content-Type: application/pdf" \
  --data-binary "@documento.pdf"
```

### Verificación de Health Checks
```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

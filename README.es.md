# Agente de inventario para cafeterías

Una API de inventario con FastAPI y un bucle manual de llamadas a herramientas de un LLM. Los productos persisten en `products.csv` y los eventos del agente se añaden a `conversation_log.csv`.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Crea un fichero `.env` en la raíz con tu clave de Groq:

```dotenv
GROQ_API_KEY=tu_clave_de_groq
GROQ_MODEL=llama-3.3-70b-versatile
INVENTORY_API_URL=http://127.0.0.1:8000
```

Git ignora `.env`; nunca subas claves de API al repositorio.

## Ejecución

Inicia primero la API:

```bash
uvicorn api.app:app --reload
```

En otra terminal, inicia el agente:

```bash
python agent.py
```

Escribe solicitudes en lenguaje natural y usa `salir` para terminar. El historial de conversación se mantiene en memoria hasta salir. Los dos CSV conservan sus datos y el registro de conversación no se sobrescribe al reiniciar el agente. La API también está disponible en `http://127.0.0.1:8000/docs`.

## API

- `GET /inventory`
- `POST /inventory` con `{"name": "Leche de avena", "quantity": 30, "unit": "litros"}`
- `PATCH /inventory/{product_id}` con `{"delta": 12}` o `{"delta": -12}`
- `GET /inventory/alerts?threshold=10`

Las alertas devuelven productos cuya cantidad es estrictamente inferior al umbral (10 por defecto). No se permite reducir el stock por debajo de cero.

# Coffee Shop Inventory Agent

A FastAPI inventory API and a manually implemented LLM tool-calling loop for a small coffee-supply shop. Products persist in `products.csv`, and agent events are appended to `conversation_log.csv`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a root `.env` file containing your Groq key:

```dotenv
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile
INVENTORY_API_URL=http://127.0.0.1:8000
```

The `.env` file is ignored by Git; never commit API keys.

## Run

Start the API first:

```bash
uvicorn api.app:app --reload
```

In another terminal, start the agent:

```bash
python agent.py
```

Enter requests in natural language and type `salir` to end the session. The agent keeps its conversation history in memory until it exits. Both CSV files are persistent data and are not overwritten on agent restarts. The API can also be explored at `http://127.0.0.1:8000/docs`.

## API

- `GET /inventory`
- `POST /inventory` with `{"name": "Oat milk", "quantity": 30, "unit": "liters"}`
- `PATCH /inventory/{product_id}` with `{"delta": 12}` or `{"delta": -12}`
- `GET /inventory/alerts?threshold=10`

The alerts endpoint returns products whose quantity is strictly below the threshold (10 by default). Stock cannot be adjusted below zero.

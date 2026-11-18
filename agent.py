import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
LOG_FILE = ROOT / "conversation_log.csv"
API_BASE_URL = os.getenv("INVENTORY_API_URL", "http://127.0.0.1:8000").rstrip("/")
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_TOOL_ROUNDS = 10
LOG_FIELDS = ("actor", "message", "tool_call", "timestamp")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_inventory",
            "description": "List every inventory product with its id, quantity, and unit.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_product",
            "description": "Register a product that is not already in the inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Product name"},
                    "quantity": {"type": "number", "description": "Initial stock"},
                    "unit": {"type": "string", "description": "Unit, such as bags, kg, or liters"},
                },
                "required": ["name", "quantity", "unit"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "adjust_stock",
            "description": (
                "Change stock for an existing product. Use a positive delta for a delivery "
                "and a negative delta for a sale. Get the product id from list_inventory first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Inventory product id"},
                    "delta": {"type": "number", "description": "Signed stock change"},
                },
                "required": ["product_id", "delta"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_low_stock_alerts",
            "description": "List products below the requested stock threshold (default 10).",
            "parameters": {
                "type": "object",
                "properties": {
                    "threshold": {
                        "type": "number",
                        "description": "Alert for products with quantity strictly below this value",
                    }
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
]

SYSTEM_MESSAGE = (
    "Eres un asistente amable de inventario para una tienda de suministros de cafetería. "
    "Responde en el idioma del usuario. Usa las herramientas para consultar o cambiar el "
    "inventario; nunca afirmes que un cambio se realizó si la herramienta devolvió un error. "
    "Para registrar una entrega o venta de un producto existente, consulta primero el "
    "inventario para obtener su id y luego aplica el delta correcto. Si el producto no existe, "
    "pide los datos que falten antes de registrarlo."
)


def log_event(actor: str, message: str, tool_call: str = "") -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_header = not LOG_FILE.exists() or LOG_FILE.stat().st_size == 0
    with LOG_FILE.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=LOG_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "actor": actor,
                "message": message,
                "tool_call": tool_call,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


def api_request(
    path: str, method: str = "GET", payload: dict[str, Any] | None = None
) -> dict[str, Any] | list[Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{API_BASE_URL}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        try:
            details = json.loads(error_body).get("detail", error_body)
        except json.JSONDecodeError:
            details = error_body
        return {"error": f"API returned HTTP {exc.code}: {details}"}
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"error": f"Could not communicate with the inventory API: {exc}"}


def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any] | list[Any]:
    if name == "list_inventory":
        return api_request("/inventory")
    if name == "add_product":
        return api_request("/inventory", "POST", arguments)
    if name == "adjust_stock":
        product_id = arguments["product_id"]
        return api_request(f"/inventory/{product_id}", "PATCH", {"delta": arguments["delta"]})
    if name == "get_low_stock_alerts":
        threshold = arguments.get("threshold", 10)
        return api_request(f"/inventory/alerts?threshold={threshold}")
    return {"error": f"Unknown tool: {name}"}


def run_turn(client: OpenAI, history: list[dict[str, Any]], user_text: str) -> str:
    history.append({"role": "user", "content": user_text})
    log_event("user", user_text)

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=MODEL,
            messages=history,
            tools=TOOLS,
            tool_choice="auto",
        )
        assistant_message = response.choices[0].message
        history.append(assistant_message.model_dump(exclude_none=True))

        if not assistant_message.tool_calls:
            answer = assistant_message.content or ""
            log_event("agent", answer)
            return answer

        for call in assistant_message.tool_calls:
            name = call.function.name
            raw_arguments = call.function.arguments
            try:
                arguments = json.loads(raw_arguments)
                if not isinstance(arguments, dict):
                    raise ValueError("Tool arguments must be a JSON object.")
                result = execute_tool(name, arguments)
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                result = {"error": f"Invalid arguments for {name}: {exc}"}
            log_event("tool", raw_arguments, name)
            result_text = json.dumps(result, ensure_ascii=False)
            log_event("tool", result_text, name)
            history.append(
                {"role": "tool", "tool_call_id": call.id, "content": result_text}
            )

    raise RuntimeError(f"Agent exceeded the limit of {MAX_TOOL_ROUNDS} tool rounds.")


def main() -> None:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise SystemExit("GROQ_API_KEY is missing. Set it in the root .env file.")

    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
    history: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_MESSAGE}]
    print("Asistente de inventario listo. Escribe 'salir' para terminar.")

    while True:
        try:
            user_text = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nHasta luego.")
            return
        if user_text.lower() in {"salir", "exit", "quit"}:
            print("Hasta luego.")
            return
        if not user_text:
            continue
        try:
            print(f"Agente: {run_turn(client, history, user_text)}")
        except Exception as exc:
            print(f"Error al procesar el mensaje: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()

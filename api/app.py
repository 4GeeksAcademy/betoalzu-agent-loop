import csv
import math
import os
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

PRODUCTS_FILE = Path(
    os.getenv("INVENTORY_CSV_PATH", Path(__file__).resolve().parent.parent / "products.csv")
)
CSV_FIELDS = ("id", "name", "quantity", "unit")

app = FastAPI(title="Coffee Shop Inventory API")


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: float = Field(ge=0, allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(str_strip_whitespace=True)


class StockAdjustment(BaseModel):
    delta: float = Field(allow_inf_nan=False)


class Product(BaseModel):
    id: str
    name: str
    quantity: float
    unit: str


def read_products() -> list[dict[str, str]]:
    try:
        if not PRODUCTS_FILE.exists():
            return []
        with PRODUCTS_FILE.open("r", newline="", encoding="utf-8") as file:
            return list(csv.DictReader(file))
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not read inventory file: {exc}",
        ) from exc


def write_products(products: list[dict[str, str]]) -> None:
    try:
        PRODUCTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with PRODUCTS_FILE.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(products)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save inventory file: {exc}",
        ) from exc


@app.get("/inventory", response_model=list[Product])
def list_inventory() -> list[dict[str, str]]:
    return read_products()


@app.post("/inventory", response_model=Product, status_code=status.HTTP_201_CREATED)
def create_product(product: ProductCreate) -> dict[str, str]:
    products = read_products()
    created = {
        "id": str(uuid4()),
        "name": product.name,
        "quantity": str(product.quantity),
        "unit": product.unit,
    }
    products.append(created)
    write_products(products)
    return created


@app.patch("/inventory/{product_id}", response_model=Product)
def adjust_stock(product_id: str, adjustment: StockAdjustment) -> dict[str, str]:
    products = read_products()
    for product in products:
        if product["id"] == product_id:
            updated_quantity = float(product["quantity"]) + adjustment.delta
            if not math.isfinite(updated_quantity):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Stock adjustment exceeds the supported quantity range.",
                )
            if updated_quantity < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Stock adjustment would make {product['name']} negative "
                        f"({updated_quantity:g} {product['unit']})."
                    ),
                )
            product["quantity"] = str(updated_quantity)
            write_products(products)
            return product
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Product with id '{product_id}' was not found.",
    )


@app.get("/inventory/alerts", response_model=list[Product])
def low_stock_alerts(
    threshold: Annotated[float, Query(ge=0, allow_inf_nan=False)] = 10,
) -> list[dict[str, str]]:
    return [
        product
        for product in read_products()
        if float(product["quantity"]) < threshold
    ]

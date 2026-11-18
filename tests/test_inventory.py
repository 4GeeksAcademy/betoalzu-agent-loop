import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import app as inventory


class InventoryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.products_file = Path(self.temp_dir.name) / "products.csv"
        self.file_patch = patch.object(inventory, "PRODUCTS_FILE", self.products_file)
        self.file_patch.start()
        self.client = TestClient(inventory.app)

    def tearDown(self) -> None:
        self.file_patch.stop()
        self.temp_dir.cleanup()

    def test_create_adjust_alerts_and_persist_products(self) -> None:
        self.assertEqual(self.client.get("/inventory").json(), [])

        created = self.client.post(
            "/inventory", json={"name": "Oat milk", "quantity": 12, "unit": "liters"}
        )
        self.assertEqual(created.status_code, 201)
        product = created.json()

        adjusted = self.client.patch(
            f"/inventory/{product['id']}", json={"delta": -3}
        )
        self.assertEqual(adjusted.status_code, 200)
        self.assertEqual(adjusted.json()["quantity"], 9)

        alerts = self.client.get("/inventory/alerts").json()
        self.assertEqual([item["id"] for item in alerts], [product["id"]])
        self.assertEqual(self.client.get("/inventory/alerts?threshold=9").json(), [])

        with self.products_file.open(newline="", encoding="utf-8") as file:
            persisted = list(csv.DictReader(file))
        self.assertEqual(persisted[0]["quantity"], "9.0")

    def test_rejects_negative_stock_and_reports_missing_product(self) -> None:
        response = self.client.post(
            "/inventory", json={"name": "Coffee", "quantity": 2, "unit": "bags"}
        )
        product_id = response.json()["id"]

        self.assertEqual(
            self.client.patch(f"/inventory/{product_id}", json={"delta": -3}).status_code,
            400,
        )
        self.assertEqual(
            self.client.patch("/inventory/missing", json={"delta": 1}).status_code,
            404,
        )
        self.assertEqual(self.client.get("/inventory").json()[0]["quantity"], 2)


if __name__ == "__main__":
    unittest.main()

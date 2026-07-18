"""Read-only access to XituERP and the read-only Ozon product endpoints.

This module deliberately contains no INSERT/UPDATE/DELETE statements.  The ERP
project is imported only to reuse its existing database connection and Ozon API
client.  Bytecode generation is disabled before the ERP path is imported so no
__pycache__ files are created in the ERP tree.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProductCandidate:
    source_type: str
    source_key: str
    shop_id: int | None
    shop_name: str
    seller_sku: str
    product_id: str
    product_title: str
    image_url: str
    sold_units: int
    last_order_at: str


class ErpReader:
    def __init__(self, erp_root: Path) -> None:
        sys.dont_write_bytecode = True
        root = str(erp_root.resolve())
        if root not in sys.path:
            sys.path.insert(0, root)
        from app.infra import db  # type: ignore
        from app.infra.ozon.client import OzonClient  # type: ignore

        self._db = db
        self._ozon_client_class = OzonClient

    def ordered_products(self) -> list[ProductCandidate]:
        sql = """
            SELECT StoreName, StoreSKU, ProductId, ProductName,
                   MAX(ProductImageUrl) AS ProductImageUrl,
                   SUM(COALESCE(Quantity, 1)) AS SoldUnits,
                   MAX(BuyerOrderTime) AS LastOrderAt
            FROM order_center
            WHERE ProductId IS NOT NULL
              AND ProductName IS NOT NULL
              AND ProductImageUrl IS NOT NULL
            GROUP BY StoreName, StoreSKU, ProductId, ProductName
            ORDER BY SoldUnits DESC, LastOrderAt DESC
        """
        rows = self._db.query(sql)
        result: list[ProductCandidate] = []
        for store, sku, product_id, title, image, sold, last_order in rows:
            pid = str(product_id or "").strip()
            if not pid.isdigit():
                continue
            result.append(
                ProductCandidate(
                    source_type="order",
                    source_key=f"order:{store}:{pid}",
                    shop_id=None,
                    shop_name=str(store or "").strip(),
                    seller_sku=str(sku or "").strip(),
                    product_id=pid,
                    product_title=str(title or "").strip(),
                    image_url=str(image or "").strip(),
                    sold_units=max(0, int(sold or 0)),
                    last_order_at=str(last_order or ""),
                )
            )
        return result

    def successfully_published_products(self) -> list[ProductCandidate]:
        """Return only products that still resolve in their matching Ozon shop.

        A historical ``发布成功`` row is not enough: copied or removed offers can
        remain in the ERP table.  The read-only Ozon product-list endpoint is used
        to confirm the real product id and product pictures before a page is made.
        """
        sql = """
            SELECT Id, ShopId, ShopName, ProductSKU, ProductTitle, Status, DetailJson,
                   COALESCE(OperatedAt, CreatedAt)
            FROM product_publish
            ORDER BY Id DESC
        """
        rows = self._db.query(sql)
        result: list[ProductCandidate] = []
        for row_id, shop_id, shop_name, offer_id, title, status, detail_json, operated_at in rows:
            if str(status or "").strip() != "发布成功":
                continue
            auth = self._db.query(
                "SELECT ClientId, ApiKey FROM sys_shop_auth WHERE Id=%s",
                int(shop_id),
            )
            if not auth:
                continue
            client_id, api_key = auth[0]
            client = self._ozon_client_class(client_id, api_key)
            try:
                response = client.get_products(
                    filters={"offer_id": [str(offer_id)], "visibility": "ALL"},
                    limit=10,
                )
                items = ((response or {}).get("result") or {}).get("items") or []
                item = next(
                    (item for item in items if str(item.get("offer_id")) == str(offer_id)),
                    None,
                )
                if not item or not str(item.get("product_id") or "").isdigit():
                    continue
                product_id = str(item["product_id"])
                picture_response = client.get_product_pictures([int(product_id)])
                image_url = self._first_http_url(picture_response)
                if not image_url:
                    detail = json.loads(detail_json) if isinstance(detail_json, str) else (detail_json or {})
                    images = detail.get("images") if isinstance(detail, dict) else []
                    image_url = next((str(x) for x in (images or []) if str(x).startswith("http")), "")
            except Exception:
                # API/auth/network failures are intentionally non-fatal.  They are
                # retried on the next scheduled run and no uncertain page is made.
                continue
            if not image_url:
                continue
            result.append(
                ProductCandidate(
                    source_type="published",
                    source_key=f"published:{shop_id}:{offer_id}",
                    shop_id=int(shop_id),
                    shop_name=str(shop_name or "").strip(),
                    seller_sku=str(offer_id or "").strip(),
                    product_id=product_id,
                    product_title=str(title or "").strip(),
                    image_url=image_url,
                    sold_units=0,
                    last_order_at=str(operated_at or ""),
                )
            )
        return result

    @classmethod
    def _first_http_url(cls, value: Any) -> str:
        if isinstance(value, str):
            return value if value.startswith("http") else ""
        if isinstance(value, list):
            for child in value:
                found = cls._first_http_url(child)
                if found:
                    return found
        if isinstance(value, dict):
            for child in value.values():
                found = cls._first_http_url(child)
                if found:
                    return found
        return ""

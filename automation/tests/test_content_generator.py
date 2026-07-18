from __future__ import annotations

import sys
import unittest
from pathlib import Path

AUTOMATION_ROOT = Path(__file__).resolve().parents[1]
if str(AUTOMATION_ROOT) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_ROOT))

from content_generator import extract_keyword, generate, normalize_keyword, slugify
from erp_reader import ProductCandidate


class ContentGeneratorTests(unittest.TestCase):
    def test_extracts_straight_and_guillemet_quotes(self) -> None:
        self.assertEqual(extract_keyword('Флаг "AC/DC" 90x140 см'), "AC/DC")
        self.assertEqual(extract_keyword("Картина «VALHALLA» 30x40 см"), "VALHALLA")

    def test_missing_quote_requires_review(self) -> None:
        self.assertIsNone(extract_keyword("Флаг Север 90x140 см"))

    def test_slug_transliterates_and_is_stable(self) -> None:
        self.assertEqual(slugify("Спартак Москва", "123"), "spartak-moskva")
        self.assertEqual(slugify("AC/DC", "123"), "ac-dc")

    def test_keyword_normalization_deduplicates_case(self) -> None:
        self.assertEqual(normalize_keyword("  AC/DC "), normalize_keyword("ac dc"))

    def test_generated_page_contains_confirmed_ozon_link(self) -> None:
        candidate = ProductCandidate(
            source_type="order",
            source_key="order:test:123456",
            shop_id=None,
            shop_name="test",
            seller_sku="seller-1",
            product_id="123456",
            product_title='Флаг "AC/DC" 90x140 см',
            image_url="https://example.test/image.jpg",
            sold_units=2,
            last_order_at="2026-07-18 10:00:00",
        )
        page = generate(candidate)
        self.assertIsNotNone(page)
        assert page is not None
        self.assertIn("https://www.ozon.ru/product/123456/", page.markdown)
        self.assertIn("updatedAt: 2026-07-18", page.markdown)


if __name__ == "__main__":
    unittest.main()

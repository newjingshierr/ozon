from __future__ import annotations

import sys
import unittest
from pathlib import Path

AUTOMATION_ROOT = Path(__file__).resolve().parents[1]
if str(AUTOMATION_ROOT) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_ROOT))

from content_generator import normalize_keyword, slugify, validate_model_page
from erp_reader import ProductCandidate
from run import candidate_fingerprint, skip_decision_is_active


class ContentGeneratorTests(unittest.TestCase):
    def test_persistent_skip_decisions(self) -> None:
        candidate = ProductCandidate(
            source_type="order", source_key="order:test:123", shop_id=None,
            shop_name="test", seller_sku="sku", product_id="123",
            product_title="Флаг Хаски", image_url="https://example.com/a.jpg",
            sold_units=1, last_order_at="2026-01-01",
        )
        fingerprint = candidate_fingerprint(candidate)
        self.assertTrue(skip_decision_is_active(candidate, {
            candidate.source_key: {"disposition": "ignore", "fingerprint": "old"}
        }))
        self.assertTrue(skip_decision_is_active(candidate, {
            candidate.source_key: {"disposition": "review", "fingerprint": fingerprint}
        }))
        self.assertFalse(skip_decision_is_active(candidate, {
            candidate.source_key: {"disposition": "review", "fingerprint": "old"}
        }))

    def test_slug_transliterates_and_is_stable(self) -> None:
        self.assertEqual(slugify("Спартак Москва", "123"), "spartak-moskva")
        self.assertEqual(slugify("AC/DC", "123"), "ac-dc")

    def test_keyword_normalization_deduplicates_case(self) -> None:
        self.assertEqual(normalize_keyword("  AC/DC "), normalize_keyword("ac dc"))

    def test_valid_model_page(self) -> None:
        body = "## Выбор темы\n\n" + ("Русский полезный текст о товаре и оформлении пространства. " * 15)
        body += "\n\n## Размещение\n\n" + ("Практические рекомендации без выдуманных характеристик. " * 12)
        body += "\n\n## Проверка на Ozon\n\n" + ("Проверьте цену, наличие и доставку в карточке товара. " * 10)
        page = validate_model_page(
            {
                "source_key": "order:test:123",
                "primary_keyword": "флаг AC/DC",
                "title": "Флаг AC/DC для тематического оформления комнаты",
                "description": "Флаг AC/DC для интерьера: идеи размещения и важные детали перед заказом. Цена и наличие указаны в карточке товара на Ozon.",
                "category": "rock",
                "image_alt": "Флаг AC/DC с изображением товара на светлом фоне",
                "keywords": ["флаг AC/DC", "AC/DC декор", "рок флаг", "флаг на стену", "AC/DC Ozon"],
                "body_markdown": body,
            },
            "order:test:123",
        )
        self.assertEqual(page.category, "rock")

    def test_rejects_short_template_copy(self) -> None:
        with self.assertRaises(ValueError):
            validate_model_page(
                {
                    "source_key": "order:test:123",
                    "primary_keyword": "AC/DC",
                    "title": "Слишком короткий текст о товаре",
                    "description": "Короткое описание, которое всё же пытается выглядеть как нормальное описание товара для страницы.",
                    "category": "rock",
                    "image_alt": "Флаг AC/DC на изображении товара",
                    "keywords": ["AC/DC", "рок", "флаг", "декор", "Ozon"],
                    "body_markdown": "## Один раздел\nОчень коротко.",
                },
                "order:test:123",
            )


if __name__ == "__main__":
    unittest.main()

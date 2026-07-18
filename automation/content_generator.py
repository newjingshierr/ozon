"""Deterministic Russian SEO page generation without an AI API."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from erp_reader import ProductCandidate


QUOTE_PATTERN = re.compile(r'["“”«»]([^"“”«»]{2,120})["“”«»]')
DIMENSION_PATTERN = re.compile(r"\b(\d{2,3})\s*[xх×*]\s*(\d{2,3})\s*(?:см|cm)?\b", re.IGNORECASE)

TRANSLIT = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
        "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
        "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
        "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
        "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
        "э": "e", "ю": "yu", "я": "ya",
    }
)


@dataclass(frozen=True)
class GeneratedPage:
    slug: str
    keyword: str
    category: str
    image_filename: str
    markdown: str
    content_hash: str


def extract_keyword(title: str) -> str | None:
    match = QUOTE_PATTERN.search(title or "")
    if not match:
        return None
    keyword = re.sub(r"\s+", " ", match.group(1)).strip(" ,.;:")
    return keyword if len(keyword) >= 2 else None


def normalize_keyword(keyword: str) -> str:
    return re.sub(r"[^\w]+", " ", unicodedata.normalize("NFKC", keyword).casefold()).strip()


def slugify(keyword: str, product_id: str) -> str:
    value = unicodedata.normalize("NFKC", keyword).casefold().translate(TRANSLIT)
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    if not value:
        value = f"product-{product_id}"
    return value[:72].rstrip("-")


def classify(title: str, keyword: str) -> tuple[str, str]:
    text = f"{title} {keyword}".casefold()
    kind = "art" if any(x in text for x in ("картина", "постер", "холст")) else "flag"
    if any(x in text for x in ("фк ", "хк ", "спартак", "цска", "локомотив", "краснодар", "футбол", "хоккей")):
        return "sport", kind
    if any(x in text for x in ("valhalla", "odin", "вальхалл", "один", "викинг", "мифолог")):
        return "mythology", kind
    if any(x in text for x in ("ac/dc", "deep purple", "the prodigy", "metallica", "nirvana", "rammstein", "король и шут", "группа")):
        return "rock", kind
    return "art", kind


def generate(candidate: ProductCandidate) -> GeneratedPage | None:
    keyword = extract_keyword(candidate.product_title)
    if not keyword:
        return None
    category, kind = classify(candidate.product_title, keyword)
    slug = slugify(keyword, candidate.product_id)
    image_filename = f"{slug}-{candidate.product_id}.jpg"
    dimensions_match = DIMENSION_PATTERN.search(candidate.product_title)
    dimensions = (
        f"{dimensions_match.group(1)}×{dimensions_match.group(2)} см"
        if dimensions_match
        else "указанный в карточке размер"
    )
    is_flag = kind == "flag"
    noun = "флаг" if is_flag else "картина"
    title = (
        f"Флаг «{keyword}» — посмотреть на Ozon"
        if is_flag
        else f"Картина «{keyword}» — посмотреть на Ozon"
    )
    description = (
        f"{noun.capitalize()} «{keyword}»: фото, особенности и идеи размещения. "
        "Актуальная цена, наличие и доставка — в карточке товара на Ozon."
    )[:180]
    image_alt = f"{noun.capitalize()} «{keyword}», изображение товара с Ozon"
    sold_note = (
        f"По данным магазина, этот товар уже встречался в {candidate.sold_units} заказах. "
        if candidate.sold_units > 0
        else ""
    )
    type_paragraph = (
        "Двусторонний формат удобно использовать как заметный настенный баннер: изображение "
        "остаётся частью оформления комнаты, домашней студии, тематической зоны или пространства для встреч."
        if is_flag
        else
        "Настенная картина помогает добавить тематический акцент в комнату, кабинет, домашнюю студию "
        "или зону отдыха без сложной перестройки интерьера."
    )
    keywords = [
        keyword,
        f"{noun} {keyword}",
        f"{keyword} купить",
        f"{keyword} Ozon",
        "настенный декор",
    ]
    frontmatter_keywords = ", ".join(json_quote(x) for x in keywords)
    markdown = f'''---
title: {json_quote(title)}
description: {json_quote(description)}
category: {category}
image: "/images/products/{image_filename}"
imageAlt: {json_quote(image_alt)}
ozonUrl: "https://www.ozon.ru/product/{candidate.product_id}/"
shopName: {json_quote(candidate.shop_name)}
ozonSku: {json_quote(candidate.product_id)}
sellerSku: {json_quote(candidate.seller_sku)}
sourceKey: {json_quote(candidate.source_key)}
sourceType: {json_quote(candidate.source_type)}
soldUnits: {candidate.sold_units}
keywords: [{frontmatter_keywords}]
updatedAt: {date_only(candidate.last_order_at)}
draft: false
---

## {noun.capitalize()} «{keyword}» для тематического интерьера

{noun.capitalize()} «{keyword}» — готовый визуальный акцент для поклонников этой темы. {type_paragraph}

Размер, указанный продавцом: **{dimensions}**. Перед заказом рекомендуем ещё раз проверить фотографии, комплектацию, материал и доступный вариант непосредственно на Ozon: карточка товара может обновляться продавцом.

## Почему эту модель стоит посмотреть

- выразительная тема «{keyword}»;
- формат, подходящий для настенного оформления;
- одна крупная композиция вместо набора небольших украшений;
- заказ, оплата и доставка оформляются на Ozon.

{sold_note}Это не означает гарантированное наличие сейчас: актуальный статус всегда показывается в карточке Ozon.

## Где разместить

Такой {noun} можно использовать в комнате, рабочей зоне, домашней студии или тематическом уголке. Перед креплением измерьте свободное место и выберите способ монтажа, подходящий поверхности стены и весу изделия.

## Проверка перед покупкой

Откройте карточку товара на Ozon и проверьте текущую цену, сроки доставки, отзывы, фактические фотографии и характеристики. ArtBox World публикует независимые тематические подборки и не является официальным сайтом правообладателя или Ozon.
'''
    digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    return GeneratedPage(slug, keyword, category, image_filename, markdown, digest)


def json_quote(value: str) -> str:
    import json
    return json.dumps(str(value), ensure_ascii=False)


def date_only(value: str) -> str:
    match = re.match(r"(\d{4}-\d{2}-\d{2})", value or "")
    if match:
        return match.group(1)
    from datetime import date
    return date.today().isoformat()

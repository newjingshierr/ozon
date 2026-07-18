"""Helpers for model-written Russian SEO pages.

This module does not write prose.  It validates and renders prose supplied by
the Codex language model during a scheduled task.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass

from erp_reader import ProductCandidate


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
class ModelPage:
    source_key: str
    primary_keyword: str
    title: str
    description: str
    category: str
    image_alt: str
    keywords: list[str]
    body_markdown: str


def normalize_keyword(keyword: str) -> str:
    return re.sub(r"[^\w]+", " ", unicodedata.normalize("NFKC", keyword).casefold()).strip()


def slugify(keyword: str, product_id: str) -> str:
    value = unicodedata.normalize("NFKC", keyword).casefold().translate(TRANSLIT)
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return (value or f"product-{product_id}")[:72].rstrip("-")


def validate_model_page(raw: dict, expected_source_key: str) -> ModelPage:
    if str(raw.get("source_key") or "") != expected_source_key:
        raise ValueError("模型输出的 source_key 与输入不一致")
    primary_keyword = clean_text(raw.get("primary_keyword"))
    title = clean_text(raw.get("title"))
    description = clean_text(raw.get("description"))
    category = clean_text(raw.get("category"))
    image_alt = clean_text(raw.get("image_alt"))
    keywords = [clean_text(x) for x in (raw.get("keywords") or []) if clean_text(x)]
    body = str(raw.get("body_markdown") or "").strip()
    if not 2 <= len(primary_keyword) <= 120:
        raise ValueError("primary_keyword 长度不合格")
    if not 15 <= len(title) <= 100:
        raise ValueError("title 长度必须为 15–100 字符")
    if not 70 <= len(description) <= 180:
        raise ValueError("description 长度必须为 70–180 字符")
    if category not in {"rock", "sport", "mythology", "art"}:
        raise ValueError("category 不在允许范围")
    if not 10 <= len(image_alt) <= 180:
        raise ValueError("image_alt 长度不合格")
    if not 5 <= len(keywords) <= 12:
        raise ValueError("keywords 必须有 5–12 个")
    if len({normalize_keyword(x) for x in keywords}) != len(keywords):
        raise ValueError("keywords 内部存在重复")
    if not 1200 <= len(body) <= 8000:
        raise ValueError("body_markdown 必须为 1200–8000 字符")
    if body.count("## ") < 3:
        raise ValueError("body_markdown 至少需要 3 个二级标题")
    if len(re.findall(r"[А-Яа-яЁё]", body)) < 500:
        raise ValueError("正文俄文内容不足")
    if "---" == body.splitlines()[0].strip() if body.splitlines() else False:
        raise ValueError("body_markdown 不应包含 frontmatter")
    return ModelPage(
        source_key=expected_source_key,
        primary_keyword=primary_keyword,
        title=title,
        description=description,
        category=category,
        image_alt=image_alt,
        keywords=keywords,
        body_markdown=body,
    )


def render_markdown(
    candidate: ProductCandidate,
    page: ModelPage,
    slug: str,
    image_path: str,
    batch_id: str,
) -> tuple[str, str]:
    keyword_json = ", ".join(json.dumps(x, ensure_ascii=False) for x in page.keywords)
    markdown = f'''---
title: {json.dumps(page.title, ensure_ascii=False)}
description: {json.dumps(page.description, ensure_ascii=False)}
category: {page.category}
image: {json.dumps(image_path, ensure_ascii=False)}
imageAlt: {json.dumps(page.image_alt, ensure_ascii=False)}
ozonUrl: "https://www.ozon.ru/product/{candidate.product_id}/"
shopName: {json.dumps(candidate.shop_name, ensure_ascii=False)}
ozonSku: {json.dumps(candidate.product_id, ensure_ascii=False)}
sellerSku: {json.dumps(candidate.seller_sku, ensure_ascii=False)}
sourceKey: {json.dumps(candidate.source_key, ensure_ascii=False)}
sourceType: {json.dumps(candidate.source_type, ensure_ascii=False)}
contentMode: model
modelBatch: {json.dumps(batch_id, ensure_ascii=False)}
soldUnits: {candidate.sold_units}
keywords: [{keyword_json}]
updatedAt: {date_only(candidate.last_order_at)}
draft: false
---

{page.body_markdown.rstrip()}
'''
    return markdown, hashlib.sha256(markdown.encode("utf-8")).hexdigest()


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def date_only(value: str) -> str:
    match = re.match(r"(\d{4}-\d{2}-\d{2})", value or "")
    if match:
        return match.group(1)
    from datetime import date
    return date.today().isoformat()

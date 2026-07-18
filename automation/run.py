"""Two-phase SEO pipeline orchestrated by a Codex scheduled task.

Python performs deterministic work only:

1. ``prepare`` reads ERP data and writes a model-input batch.
2. Codex writes keywords and original Russian copy to model_output.json.
3. ``finalize`` validates the model output, processes images, builds and publishes.

No AI API key is required because the scheduled Codex task supplies the model step.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from PIL import Image, UnidentifiedImageError

from content_generator import ModelPage, normalize_keyword, render_markdown, slugify, validate_model_page
from erp_reader import ErpReader, ProductCandidate


AUTOMATION_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = AUTOMATION_ROOT / "config.json"
DATA_ROOT = AUTOMATION_ROOT / "data"
INPUT_PATH = DATA_ROOT / "model_input.json"
OUTPUT_PATH = DATA_ROOT / "model_output.json"
REVIEW_PATH = DATA_ROOT / "review_queue.json"
PENDING_PATH = DATA_ROOT / "pending_publish.json"


def load_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


class RunLock:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> "RunLock":
        if self.path.exists() and time.time() - self.path.stat().st_mtime > 3 * 60 * 60:
            self.path.unlink(missing_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError("另一个 SEO 自动化任务仍在运行") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()} started={datetime.now().isoformat()}\n")
        return self

    def __exit__(self, *_: object) -> None:
        self.path.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="create model_input.json")
    prepare.add_argument("--limit", type=int)
    finalize = sub.add_parser("finalize", help="validate model_output.json and generate pages")
    finalize.add_argument("--publish", action="store_true")
    sub.add_parser("status", help="show current batch state")
    return parser.parse_args()


def read_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    block = text.split("---", 2)[1]
    result: dict[str, Any] = {"_text": text}
    for key in (
        "image", "ozonUrl", "shopName", "ozonSku", "sellerSku", "sourceKey",
        "sourceType", "contentMode", "modelBatch",
    ):
        match = re.search(rf"^{key}:\s*(.+?)\s*$", block, re.MULTILINE)
        if match:
            raw = match.group(1).strip()
            try:
                result[key] = json.loads(raw)
            except Exception:
                result[key] = raw.strip("\"'")
    sold = re.search(r"^soldUnits:\s*(\d+)", block, re.MULTILINE)
    result["soldUnits"] = int(sold.group(1)) if sold else 0
    kw = re.search(r'^keywords:\s*\[\s*["\']([^"\']+)', block, re.MULTILINE)
    result["primaryKeyword"] = kw.group(1) if kw else ""
    return result


def existing_pages(site_root: Path) -> tuple[dict[str, dict[str, Any]], set[str], set[str]]:
    by_product: dict[str, dict[str, Any]] = {}
    source_keys: set[str] = set()
    model_keywords: set[str] = set()
    for path in (site_root / "src/content/products").glob("*.md"):
        meta = read_frontmatter(path)
        url = str(meta.get("ozonUrl") or "")
        match = re.search(r"ozon\.ru/product/(\d+)", url)
        if not match:
            continue
        meta["path"] = str(path)
        meta["slug"] = path.stem
        by_product[match.group(1)] = meta
        if meta.get("sourceKey"):
            source_keys.add(str(meta["sourceKey"]))
        if meta.get("contentMode") == "model" and meta.get("primaryKeyword"):
            model_keywords.add(normalize_keyword(str(meta["primaryKeyword"])))
    return by_product, source_keys, model_keywords


def candidate_dict(candidate: ProductCandidate, action: str, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "action": action,
        "source_type": candidate.source_type,
        "source_key": candidate.source_key,
        "shop_id": candidate.shop_id,
        "shop_name": candidate.shop_name,
        "seller_sku": candidate.seller_sku,
        "product_id": candidate.product_id,
        "original_product_title": candidate.product_title,
        "image_url": candidate.image_url,
        "sold_units": candidate.sold_units,
        "last_order_at": candidate.last_order_at,
        "existing_slug": (existing or {}).get("slug"),
        "existing_image": (existing or {}).get("image"),
    }


def prepare_batch(config: dict[str, Any], limit: int) -> int:
    site_root = Path(config["site_root"]).resolve()
    reader = ErpReader(Path(config["erp_root"]).resolve())
    candidates = reader.ordered_products() + reader.successfully_published_products()
    by_product, source_keys, _ = existing_pages(site_root)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    # First rewrite pages previously created by the retired fixed template.
    for candidate in candidates:
        existing = by_product.get(candidate.product_id)
        if existing and existing.get("sourceKey") and existing.get("contentMode") != "model":
            items.append(candidate_dict(candidate, "rewrite", existing))
            seen.add(candidate.product_id)
            if len(items) >= limit:
                break

    # Then add genuinely new products.
    if len(items) < limit:
        for candidate in candidates:
            if candidate.product_id in by_product or candidate.source_key in source_keys or candidate.product_id in seen:
                continue
            items.append(candidate_dict(candidate, "new"))
            seen.add(candidate.product_id)
            if len(items) >= limit:
                break

    signature = "\n".join(item["source_key"] + ":" + item["action"] for item in items)
    batch_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + hashlib.sha256(signature.encode()).hexdigest()[:8]
    payload = {
        "version": 1,
        "batch_id": batch_id,
        "created_at": datetime.now().isoformat(),
        "items": items,
        "model_requirements": {
            "language": "Russian",
            "task": "Identify the true primary search keyword and write original, useful SEO copy for each product.",
            "title_chars": "15-100",
            "description_chars": "70-180",
            "body_chars": "1200-8000",
            "body_min_h2": 3,
            "keywords_count": "5-12",
            "categories": ["rock", "sport", "mythology", "art"],
            "facts": "Use only facts present in the input. Do not invent official affiliation, materials, availability, reviews or history.",
            "uniqueness": "Every page must be substantively rewritten for its exact search intent; do not reuse a fixed paragraph template.",
        },
        "output_schema": {
            "batch_id": "copy from input",
            "items": [
                {
                    "source_key": "copy exactly",
                    "status": "publish or skip",
                    "skip_reason": "required only when status=skip",
                    "primary_keyword": "one natural Russian search phrase",
                    "title": "unique SEO title",
                    "description": "unique meta description",
                    "category": "rock|sport|mythology|art",
                    "image_alt": "descriptive Russian alt text",
                    "keywords": ["5-12 unique related phrases"],
                    "body_markdown": "original Russian Markdown body with at least three ## headings",
                }
            ],
        },
    }
    atomic_json(INPUT_PATH, payload)
    OUTPUT_PATH.unlink(missing_ok=True)
    print(json.dumps({"batch_id": batch_id, "items": len(items), "input": str(INPUT_PATH)}, ensure_ascii=False))
    return 0


def download_image(url: str, target: Path, config: dict[str, Any]) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "ArtBoxWorldBot/2.0"})
    with urllib.request.urlopen(request, timeout=int(config.get("request_timeout_seconds", 30))) as response:
        if not response.headers.get("Content-Type", "").startswith("image/"):
            raise ValueError("下载内容不是图片")
        data = response.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024:
        raise ValueError("图片超过 20MB")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".image", delete=False) as handle:
        handle.write(data)
        temporary = Path(handle.name)
    try:
        with Image.open(temporary) as image:
            image.load()
            max_width = int(config.get("image_max_width", 1600))
            if image.width > max_width:
                image.thumbnail((max_width, 10000), Image.Resampling.LANCZOS)
            if image.mode != "RGB":
                background = Image.new("RGB", image.size, "white")
                if "A" in image.getbands():
                    background.paste(image, mask=image.getchannel("A"))
                else:
                    background.paste(image.convert("RGB"))
                image = background
            image.save(target, "JPEG", quality=int(config.get("image_quality", 86)), optimize=True, progressive=True)
    except UnidentifiedImageError as exc:
        raise ValueError("无法识别下载图片") from exc
    finally:
        temporary.unlink(missing_ok=True)


def run_command(command: list[str], cwd: Path) -> None:
    completed = subprocess.run(command, cwd=cwd, text=True, encoding="utf-8", errors="replace")
    if completed.returncode:
        raise RuntimeError(f"命令失败（{completed.returncode}）：{' '.join(command)}")


def finalize_batch(config: dict[str, Any], publish: bool) -> int:
    input_data = load_json(INPUT_PATH, None)
    output_data = load_json(OUTPUT_PATH, None)
    if not input_data or not output_data:
        raise ValueError("缺少 model_input.json 或 model_output.json")
    if output_data.get("batch_id") != input_data.get("batch_id"):
        raise ValueError("模型输出 batch_id 与输入不一致")
    raw_outputs = {str(x.get("source_key")): x for x in output_data.get("items", [])}
    site_root = Path(config["site_root"]).resolve()
    by_product, _, existing_model_keywords = existing_pages(site_root)
    batch_keywords: set[str] = set()
    review: list[dict[str, str]] = []
    changes: list[str] = []

    for item in input_data.get("items", []):
        source_key = str(item["source_key"])
        raw = raw_outputs.get(source_key)
        if not raw:
            raise ValueError(f"模型漏掉了 {source_key}")
        if raw.get("status") == "skip":
            review.append({"source_key": source_key, "reason": str(raw.get("skip_reason") or "模型跳过")})
            continue
        page: ModelPage = validate_model_page(raw, source_key)
        keyword_key = normalize_keyword(page.primary_keyword)
        if keyword_key in batch_keywords:
            raise ValueError(f"本批次主关键词重复：{page.primary_keyword}")
        existing = by_product.get(str(item["product_id"]))
        old_keyword = normalize_keyword(str((existing or {}).get("primaryKeyword") or ""))
        if keyword_key in existing_model_keywords and keyword_key != old_keyword:
            raise ValueError(f"主关键词与已有模型页面重复：{page.primary_keyword}")
        batch_keywords.add(keyword_key)

        candidate = ProductCandidate(
            source_type=str(item["source_type"]), source_key=source_key,
            shop_id=item.get("shop_id"), shop_name=str(item["shop_name"]),
            seller_sku=str(item["seller_sku"]), product_id=str(item["product_id"]),
            product_title=str(item["original_product_title"]), image_url=str(item["image_url"]),
            sold_units=int(item.get("sold_units") or 0), last_order_at=str(item.get("last_order_at") or ""),
        )
        if item.get("action") == "rewrite":
            slug = str(item["existing_slug"])
            image_path = str(item["existing_image"])
        else:
            base_slug = slugify(page.primary_keyword, candidate.product_id)
            slug = base_slug
            content_target = site_root / "src/content/products" / f"{slug}.md"
            if content_target.exists():
                slug = f"{base_slug}-{candidate.product_id[-6:]}"
            image_name = f"{slug}-{candidate.product_id}.jpg"
            image_path = f"/images/products/{image_name}"
            image_target = site_root / "public" / image_path.lstrip("/")
            download_image(candidate.image_url, image_target, config)
            changes.append(str(image_target.relative_to(site_root)).replace("\\", "/"))
        markdown, _ = render_markdown(candidate, page, slug, image_path, str(input_data["batch_id"]))
        content_target = site_root / "src/content/products" / f"{slug}.md"
        content_target.write_text(markdown, encoding="utf-8", newline="\n")
        changes.append(str(content_target.relative_to(site_root)).replace("\\", "/"))

    atomic_json(REVIEW_PATH, {"updated_at": datetime.now().isoformat(), "items": review})
    changes = list(dict.fromkeys(changes))
    atomic_json(PENDING_PATH, {"batch_id": input_data["batch_id"], "paths": changes})
    if changes:
        run_command(["npm.cmd", "run", "build"], site_root)
    if publish and changes:
        run_command(["git", "add", "--", *changes], site_root)
        run_command(["git", "commit", "-m", f"Publish {len(input_data['items'])} model-written SEO pages"], site_root)
        run_command(["git", "push", config.get("git_remote", "origin"), config.get("git_branch", "main")], site_root)
        PENDING_PATH.unlink(missing_ok=True)
    print(json.dumps({"batch_id": input_data["batch_id"], "changed_files": len(changes), "skipped": len(review), "published": bool(publish and changes)}, ensure_ascii=False))
    return 0


def show_status() -> int:
    input_data = load_json(INPUT_PATH, {})
    output_data = load_json(OUTPUT_PATH, {})
    pending = load_json(PENDING_PATH, {})
    print(json.dumps({
        "batch_id": input_data.get("batch_id"),
        "input_items": len(input_data.get("items", [])),
        "model_output_ready": output_data.get("batch_id") == input_data.get("batch_id") and bool(output_data),
        "pending_publish_paths": len(pending.get("paths", [])),
    }, ensure_ascii=False))
    return 0


def main() -> int:
    args = parse_args()
    config = load_json(CONFIG_PATH, {})
    with RunLock(AUTOMATION_ROOT / ".run.lock"):
        if args.command == "prepare":
            return prepare_batch(config, max(1, int(args.limit or config.get("max_new_pages_per_run", 20))))
        if args.command == "finalize":
            return finalize_batch(config, bool(args.publish))
        return show_status()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)

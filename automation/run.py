"""Generate, validate and optionally publish Ozon SEO pages.

Usage:
  python automation/run.py --dry-run
  python automation/run.py
  python automation/run.py --publish
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
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

from content_generator import GeneratedPage, generate, normalize_keyword
from erp_reader import ErpReader, ProductCandidate


AUTOMATION_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = AUTOMATION_ROOT / "config.json"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


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
            raise RuntimeError("另一个自动化任务仍在运行，当前任务已安全退出。") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()} started={datetime.now().isoformat()}\n")
        return self

    def __exit__(self, *_: object) -> None:
        self.path.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate ArtBox World pages from XituERP")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="read and report only; write no pages")
    mode.add_argument("--publish", action="store_true", help="generate, build, commit and push")
    parser.add_argument("--limit", type=int, help="override maximum new pages")
    return parser.parse_args()


def existing_identity(site_root: Path) -> tuple[set[str], set[str], set[str]]:
    product_ids: set[str] = set()
    source_keys: set[str] = set()
    keywords: set[str] = set()
    for path in (site_root / "src/content/products").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        product_ids.update(re.findall(r"ozon\.ru/product/(\d+)", text))
        match = re.search(r'^sourceKey:\s*["\']?(.+?)["\']?\s*$', text, re.MULTILINE)
        if match:
            source_keys.add(match.group(1).strip())
        keyword_match = re.search(r"^keywords:\s*\[\s*[\"']([^\"']+)", text, re.MULTILINE)
        if keyword_match:
            keywords.add(normalize_keyword(keyword_match.group(1)))
    return product_ids, source_keys, keywords


def select_candidates(
    candidates: list[ProductCandidate],
    product_ids: set[str],
    source_keys: set[str],
    keywords: set[str],
    limit: int,
) -> tuple[list[tuple[ProductCandidate, GeneratedPage]], list[dict[str, str]]]:
    selected: list[tuple[ProductCandidate, GeneratedPage]] = []
    review: list[dict[str, str]] = []
    seen_products = set(product_ids)
    seen_sources = set(source_keys)
    seen_keywords = set(keywords)
    for candidate in candidates:
        if candidate.product_id in seen_products or candidate.source_key in seen_sources:
            continue
        page = generate(candidate)
        if page is None:
            review.append(
                {
                    "source_key": candidate.source_key,
                    "product_id": candidate.product_id,
                    "title": candidate.product_title,
                    "reason": "标题中没有可明确提取的引号关键词，需要模型或人工确认",
                }
            )
            continue
        keyword_key = normalize_keyword(page.keyword)
        if keyword_key in seen_keywords:
            review.append(
                {
                    "source_key": candidate.source_key,
                    "product_id": candidate.product_id,
                    "title": candidate.product_title,
                    "reason": f"关键词重复：{page.keyword}",
                }
            )
            continue
        selected.append((candidate, page))
        seen_products.add(candidate.product_id)
        seen_sources.add(candidate.source_key)
        seen_keywords.add(keyword_key)
        if len(selected) >= limit:
            break
    return selected, review


def download_image(url: str, target: Path, max_width: int, quality: int, timeout: int) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "ArtBoxWorldBot/1.0"})
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        if not content_type.startswith("image/"):
            raise ValueError(f"返回内容不是图片：{content_type}")
        data = response.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024:
        raise ValueError("图片超过 20MB 安全上限")
    with tempfile.NamedTemporaryFile(suffix=".image", delete=False) as handle:
        handle.write(data)
        temporary = Path(handle.name)
    try:
        with Image.open(temporary) as image:
            image.load()
            if image.width > max_width:
                height = round(image.height * max_width / image.width)
                image = image.resize((max_width, height), Image.Resampling.LANCZOS)
            if image.mode != "RGB":
                background = Image.new("RGB", image.size, "white")
                if "A" in image.getbands():
                    background.paste(image, mask=image.getchannel("A"))
                else:
                    background.paste(image.convert("RGB"))
                image = background
            image.save(target, "JPEG", quality=quality, optimize=True, progressive=True)
    except UnidentifiedImageError as exc:
        raise ValueError("下载文件无法识别为图片") from exc
    finally:
        temporary.unlink(missing_ok=True)


def run_command(command: list[str], cwd: Path) -> None:
    completed = subprocess.run(command, cwd=cwd, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise RuntimeError(f"命令失败（{completed.returncode}）：{' '.join(command)}")


def publish_pending(site_root: Path, state: dict[str, Any], config: dict[str, Any]) -> None:
    pending = [site_root / value for value in state.get("pending_paths", [])]
    pending = [path for path in pending if path.exists()]
    if not pending:
        return
    run_command(["npm.cmd", "run", "build"], site_root)
    relative_paths = [str(path.relative_to(site_root)) for path in pending]
    run_command(["git", "add", "--", *relative_paths], site_root)
    count = len([path for path in pending if path.suffix == ".md"])
    run_command(["git", "commit", "-m", f"Add {count} automated Ozon SEO pages"], site_root)
    run_command(
        ["git", "push", config.get("git_remote", "origin"), config.get("git_branch", "main")],
        site_root,
    )
    state["pending_paths"] = []


def main() -> int:
    args = parse_args()
    config = load_json(CONFIG_PATH, {})
    site_root = Path(config["site_root"]).resolve()
    erp_root = Path(config["erp_root"]).resolve()
    limit = max(1, int(args.limit or config.get("max_new_pages_per_run", 5)))
    data_root = AUTOMATION_ROOT / "data"
    state_path = data_root / "state.json"
    review_path = data_root / "review_queue.json"
    state = load_json(state_path, {"version": 1, "records": {}, "pending_paths": []})

    with RunLock(AUTOMATION_ROOT / ".run.lock"):
        reader = ErpReader(erp_root)
        ordered = reader.ordered_products()
        published = reader.successfully_published_products()
        product_ids, source_keys, keywords = existing_identity(site_root)
        selected, review = select_candidates(
            ordered + published,
            product_ids,
            source_keys,
            keywords,
            limit,
        )
        print(
            f"读取：订单商品 {len(ordered)}，可确认的成功发布商品 {len(published)}；"
            f"本次可新增 {len(selected)}，待检查 {len(review)}。"
        )
        for candidate, page in selected:
            print(f"  + {page.slug}: {page.keyword} -> Ozon {candidate.product_id}")
        if args.dry_run:
            return 0

        review_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(review_path, {"updated_at": datetime.now().isoformat(), "items": review})
        content_dir = site_root / "src/content/products"
        image_dir = site_root / "public/images/products"
        created_paths: list[str] = []
        for candidate, page in selected:
            content_path = content_dir / f"{page.slug}.md"
            image_path = image_dir / page.image_filename
            try:
                download_image(
                    candidate.image_url,
                    image_path,
                    int(config.get("image_max_width", 1600)),
                    int(config.get("image_quality", 86)),
                    int(config.get("request_timeout_seconds", 30)),
                )
                content_path.write_text(page.markdown, encoding="utf-8", newline="\n")
            except Exception as exc:
                image_path.unlink(missing_ok=True)
                content_path.unlink(missing_ok=True)
                review.append(
                    {
                        "source_key": candidate.source_key,
                        "product_id": candidate.product_id,
                        "title": candidate.product_title,
                        "reason": f"生成失败：{type(exc).__name__}: {exc}",
                    }
                )
                continue
            relative_content = str(content_path.relative_to(site_root)).replace("\\", "/")
            relative_image = str(image_path.relative_to(site_root)).replace("\\", "/")
            created_paths.extend([relative_content, relative_image])
            state["records"][candidate.source_key] = {
                "product_id": candidate.product_id,
                "keyword": page.keyword,
                "slug": page.slug,
                "content_hash": page.content_hash,
                "created_at": datetime.now().isoformat(),
            }
        atomic_json(review_path, {"updated_at": datetime.now().isoformat(), "items": review})
        state["pending_paths"] = list(dict.fromkeys(state.get("pending_paths", []) + created_paths))
        atomic_json(state_path, state)

        if created_paths:
            run_command(["npm.cmd", "run", "build"], site_root)
        if args.publish:
            publish_pending(site_root, state, config)
            atomic_json(state_path, state)
            print("构建、提交并推送完成。Cloudflare Pages 将自动部署。")
        else:
            print("页面已在本地生成并通过构建；尚未提交或推送。")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)

"""Extract legal page body HTML from Nuxt Vue templates for SitePage seed fixtures."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def extract_body(vue_path: Path) -> str:
    text = vue_path.read_text(encoding="utf-8")
    match = re.search(r"<template>(.*?)</template>", text, re.S)
    if not match:
        return ""
    tpl = match.group(1)
    tpl = re.sub(r'^\s*<div class="container[^"]*">', "", tpl)
    tpl = re.sub(r"</div>\s*$", "", tpl.strip())
    tpl = re.sub(r"<h1[^>]*>.*?</h1>", "", tpl, flags=re.S)
    tpl = re.sub(
        r'<p class="text-gray-600 mb-8"><i>Last updated:.*?</i></p>',
        "",
        tpl,
        flags=re.S,
    )
    return tpl.strip()


def main() -> None:
    out = ROOT / "robotaigeek-server" / "content" / "fixtures" / "site_pages"
    out.mkdir(parents=True, exist_ok=True)
    pages_dir = ROOT / "robotaigeek-web" / "app" / "pages"
    for slug, vue in [("privacy", "privacy.vue"), ("terms", "terms.vue")]:
        body = extract_body(pages_dir / vue)
        path = out / f"{slug}.body.html"
        path.write_text(body, encoding="utf-8")
        print(f"{slug}: {len(body)} chars -> {path}")


if __name__ == "__main__":
    main()

"""阶段 ③：payload.json → 单文件 HTML，并做静态自检。

自检直接 raise / 非零退出，拦的是“看起来生成了、其实不合规”的产物：
占位符没替换、有外链、命中 CDN、样式或脚本没内联、DOM 锚点缺失、正文带 emoji。
动态行为另由 validate.js（Node DOM 桩）与无头 Chrome 复核。

用法：
    python render.py                    # 读 out/payload.json，写 _preview.html
    python render.py --out 交付.html
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# GBK 控制台里中文/符号会抛 UnicodeEncodeError，统一改用 UTF-8 输出
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent
TPL = ROOT / "template.html"
PAYLOAD = ROOT / "out" / "payload.json"
PLACEHOLDER = "/*__PAYLOAD__*/null"

CDN_WORDS = ("cdn.", "unpkg", "jsdelivr", "googleapis", "fontawesome", "bootstrap",
             "cdnjs", "esm.sh", "skypack", "highlightjs")
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]")
ANCHORS = ("search", "panels", "tabs", "meta-source", "meta-built", "doc-title")


def build(out: Path) -> str:
    tpl = TPL.read_text(encoding="utf-8")
    if tpl.count(PLACEHOLDER) != 1:
        raise SystemExit(f"模板占位符数量异常: {tpl.count(PLACEHOLDER)}（应为 1 行独立占位）")
    data = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # `</` 必须转义，否则数据里的 `</script>` 会提前结束脚本块
    blob = blob.replace("</", "<\\/")
    html = tpl.replace(PLACEHOLDER, blob)
    out.write_text(html, encoding="utf-8")
    return html


def check(html: str) -> list[str]:
    problems: list[str] = []
    low = html.lower()
    if PLACEHOLDER in html:
        problems.append("占位符未被替换")
    for m in re.finditer(r"https?://[^\s\"'<>)]+", html):
        problems.append(f"存在外链: {m.group(0)[:80]}")
    for word in CDN_WORDS:
        if word in low:
            problems.append(f"命中 CDN 关键字: {word}")
    if EMOJI.search(html):
        problems.append("产物含 emoji")
    for anchor in ANCHORS:
        if f'id="{anchor}"' not in html:
            problems.append(f"缺少 DOM 锚点 id={anchor}")
    if re.search(r"<link[^>]+rel=[\"']stylesheet", low):
        problems.append("存在 <link rel=stylesheet>（样式未内联）")
    if re.search(r"<script[^>]+src=", low):
        problems.append("存在 <script src=（脚本未内联）")
    if "<style>" not in low:
        problems.append("未找到内联 <style>")
    if "<script>" not in low:
        problems.append("未找到内联 <script>")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="payload.json → 单文件 HTML（含静态自检）")
    ap.add_argument("--out", default=str(ROOT / "_preview.html"))
    args = ap.parse_args()
    out = Path(args.out)
    html = build(out)
    problems = check(html)
    print(f"产物: {out}  {len(html)} 字符 / {out.stat().st_size} 字节（单文件）")
    print(f"占位符已替换: {PLACEHOLDER not in html}")
    print(f"内联 <style>/<script>: {'<style>' in html} / {'<script>' in html}")
    print(f"静态问题: {len(problems)}")
    for p in problems:
        print("  x", p)
    if problems:
        return 1
    print("静态自检通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

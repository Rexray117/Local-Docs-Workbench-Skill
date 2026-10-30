"""阶段 ②：把本地 md/docx 抽成 payload.json（+ data/*.md 人读副本 + 自检报告）。

复制本文件到项目根后，只改三处即可用：
  1. SRC / OUT 常量（源目录、产物目录）；
  2. 每个 extract_xxx() 里的字段映射（列名 → key）；
  3. EXPECT（每个板块至少应解析出的行数，自检用）。

约束（与 SKILL.md 一致）：只读源文件，绝不写回 SRC；单个抽取器失败不能拖垮整轮，
错误进 ERRORS 并在 SELFTEST.md 里显形。
"""
from __future__ import annotations

import html as _html
import json
import re
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

# GBK 控制台里中文/符号会抛 UnicodeEncodeError，统一改用 UTF-8 输出
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
OUT = ROOT / "out"
DATA = OUT / "data"

# 每个板块至少应有几行；达不到就在自检里报“不达标”（退出码 1）
EXPECT = {"plan": 1, "docx": 1}

ERRORS: list[str] = []
SOURCES: list[str] = []


# ------------------------------------------------------------------ helpers
def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def write(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]+"
)


def clip(s: object, limit: int = 200) -> str:
    """单行化 + 去 emoji + 截断。工作台正文不出现 emoji（静态自检会拦）。"""
    text = re.sub(r"^[\s>*\-•·]+", "", str(s or ""))
    text = EMOJI.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def cjk_count(s: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", s or ""))


def docx_text(p: Path) -> str:
    """只用标准库读 docx 正文（不装 python-docx 也能跑）。

    两个必须做的修正（否则 payload 里是脏数据）：
      * `</w:tc>` → " | "：不映射的话同一行的表格单元格会粘成一个词；
      * html.unescape()：docx 里 `&amp;` 是转义写法，不解码会把 `&amp;` 当正文。
    """
    with zipfile.ZipFile(p) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    xml = xml.replace("</w:tc>", " | ").replace("</w:p>", "\n")
    text = _html.unescape(re.sub(r"<[^>]+>", "", xml))
    return "\n".join(line.strip(" |") for line in text.splitlines() if line.strip(" |"))


def md_tables(text: str) -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    cur: list[list[str]] = []
    for line in text.splitlines():
        if line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            cur.append(cells)
        elif cur:
            tables.append(cur)
            cur = []
    if cur:
        tables.append(cur)
    return tables


def rows_as_dicts(table: list[list[str]]) -> list[dict[str, str]]:
    if not table:
        return []
    head = table[0]
    return [{head[i]: (row[i] if i < len(row) else "") for i in range(len(head))}
            for row in table[1:]]


# ------------------------------------------------------------------ extractors
def extract_plan() -> dict:
    """md 表格 → 表格式板块。列名换成你自己的表头即可。"""
    try:
        text = read(SRC / "plan.md")
        SOURCES.append("plan.md")
        tables = md_tables(text)
        if not tables:
            raise ValueError("plan.md 里没找到 Markdown 表格")
        rows = [{"id": clip(r.get("编号", "")), "title": clip(r.get("阶段", "")),
                 "owner": clip(r.get("负责人", "")), "status": clip(r.get("状态", ""))}
                for r in rows_as_dicts(tables[0])]
        return {
            "id": "plan",
            "title": "计划",
            "kind": "table",
            "columns": [{"key": "id", "label": "编号"}, {"key": "title", "label": "阶段"},
                        {"key": "owner", "label": "负责人"}, {"key": "status", "label": "状态"}],
            "rows_count": len(rows),
            "rows": rows,
        }
    except Exception as exc:  # noqa: BLE001 - 单个抽取器失败不能中断整轮
        ERRORS.append(f"extract_plan: {type(exc).__name__}: {exc}")
        return {"id": "plan", "title": "计划", "kind": "table", "columns": [],
                "rows_count": 0, "rows": []}


def extract_docx() -> dict:
    """docx → 列表式板块（示例：按段落抽前 30 行，正文预览）。"""
    try:
        p = SRC / "weekly.docx"
        text = docx_text(p)
        SOURCES.append("weekly.docx")
        lines = [clip(x, 120) for x in text.splitlines() if clip(x)]
        return {
            "id": "docx",
            "title": "周报正文",
            "kind": "list",
            "rows_count": len(lines),
            "rows": [{"label": x} for x in lines[:30]],
            "_extra": {"chars": len(text), "cjk": cjk_count(text), "lines": len(lines)},
        }
    except Exception as exc:  # noqa: BLE001
        ERRORS.append(f"extract_docx: {type(exc).__name__}: {exc}")
        return {"id": "docx", "title": "周报正文", "kind": "list", "rows_count": 0, "rows": []}


# ------------------------------------------------------------------ main
def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    sections = [extract_plan(), extract_docx()]

    payload = {
        "meta": {
            "title": "本地资料工作台",
            "sources": SOURCES or ["(无)"],
            "built_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "today": date.today().isoformat(),
        },
        "sections": [{k: v for k, v in sec.items() if not k.startswith("_")} for sec in sections],
    }
    write(OUT / "payload.json", json.dumps(payload, ensure_ascii=False, indent=1))

    for sec in sections:
        lines = [f"# {sec['title']}（来源: {', '.join(SOURCES)}）", ""]
        for row in sec["rows"]:
            lines.append("- " + " | ".join(f"{k}={v}" for k, v in row.items()))
        write(DATA / f"{sec['id']}.md", "\n".join(lines) + "\n")

    checks = []
    for sec in sections:
        need = EXPECT.get(sec["id"], 0)
        checks.append((sec["id"], sec["rows_count"], need, sec["rows_count"] >= need))

    report = ["# 自检报告", "", f"- 来源: {', '.join(SOURCES)}",
              f"- 抽取器错误: {len(ERRORS)}", ""]
    report += [f"- {sid}: 解析 {got} 行 / 预期 ≥{need} → {'达标' if ok else '不达标'}"
               for sid, got, need, ok in checks]
    if ERRORS:
        report += ["", "## 错误明细", ""] + [f"- {e}" for e in ERRORS]
    write(DATA / "SELFTEST.md", "\n".join(report) + "\n")

    print("\n".join(report))
    size = len(json.dumps(payload, ensure_ascii=False))
    ok = all(item[3] for item in checks) and not ERRORS
    print(f"\npayload.json: {size} 字符 | 全部达标: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

---
name: local-docs-workbench
description: >-
  从本地既有文档（md/docx）抽取真实数据，构建"单文件、全内联、零外链"的本地工作台 HTML，
  并用 Node DOM 桩 + 无头 Chrome 双重验证。适用于把散落的项目资料变成可检索、可校验、
  可归档的只读索引页，且要求不部署、不上传、不改动源文件的场景。
  触发词：搭建工作台、生成单文件HTML工作台、本地资料索引页、把md转成工作台、
  抽取文档生成看板、workbench from local docs。
agent_created: true
version: 1.1.0
---

# 从本地文档构建单文件工作台

适用前提：数据源是本地 md/docx；要求单文件 HTML、可离线打开、不改动源文件。
若用户要求"在线链接/多设备同步"，改走 WorkBuddy 资料库方案，本技能不适用。

## 四段式流程

```
① 探查结构  →  ② 抽取脚本  →  ③ 模板注入  →  ④ 双重验证
   (grep/head)   (build.py)    (render.py)    (node + chrome)
```

### ① 探查结构（决定解析正则）

不要凭文件名猜格式。逐类文件抽样看真实的标题层级与字段标签：

```bash
# 标题结构
grep -n "^#\{1,4\} " 文件.md | head -40
# 字段标签频次（用于确认 spec 解析键名）
grep -o "\*\*[^*]*\*\*：" 文件.md | sort | uniq -c | sort -rn
# 目录全貌与重复目录
find . -type d -empty
diff <(ls -1 A/) <(ls -1 B/)
```

### ② 抽取脚本（build.py）

结构固定为：`ROOT/PROJ/OUT/DATA` 常量 → `read/write/clip/docx_text/cjk_count` 工具函数
→ 每个数据源一个 `extract_xxx()` → `main()` 落盘 `data/*.md` 与 `payload.json`。

要点：
- 每个 `extract_xxx()` 独立 try/except，错误收集到 `ERRORS`，不因单点失败整体崩。
- `clip()` 里统一清洗源文档中的 emoji 与行首符号（源文档常带 `🌱` `🚀` 类装饰符）。
- docx 只读提取用标准库即可，无需 python-docx：
  ```python
  import html, re, zipfile
  with zipfile.ZipFile(p) as z:
      xml = z.read("word/document.xml").decode("utf-8", "ignore")
  xml = xml.replace("</w:tc>", " | ").replace("</w:p>", "\n")   # 单元格→竖线，否则整表粘连
  txt = html.unescape(re.sub(r"<[^>]+>", "", xml))               # 必须反转义，否则 &amp; 原样进 payload
  txt = "\n".join(line.strip(" |") for line in txt.splitlines() if line.strip(" |"))
  ```
- **必须加"自检报告"**：解析条数 + 来源 + 是否达标，写进产物。这是发现解析失灵的唯一手段。

### ③ 模板注入（render.py + template.html）

`template.html` 里放占位符 `const PAYLOAD = /*__PAYLOAD__*/null;`，
render.py 用 `json.dumps(..., ensure_ascii=False, separators=(",",":"))` 替换。

注入前必须转义，否则 JSON 里的 `</script>` 会提前闭合脚本块：
```python
blob = blob.replace("</", "<\\/")
```

render.py 末尾做**静态自检**并 raise：占位符已替换、无 http(s) 外链、无 CDN 关键字、
无 emoji、DOM 锚点齐全（`id="xxx"` 全部存在）、样式与脚本皆内联。

### ④ 双重验证（关键，不能省）

静态检查抓不到运行时错误。两层都要做：

**第一层：Node DOM 桩，跑真实脚本（抓逻辑错误）**

```javascript
const vm = require("node:vm");
const els = {};                                   // code 里 `els[id] ||= …` 依赖它，漏了直接 ReferenceError
const mkEl = () => ({ innerHTML:"", textContent:"", value:"", style:{}, dataset:{},
                      classList:{ add(){}, remove(){}, toggle(){}, contains(){ return false; } },
                      appendChild(){}, addEventListener(){}, querySelector(){ return null; },
                      querySelectorAll(){ return []; } });
const ctx = {
  document: { getElementById(id){ return els[id] ||= {innerHTML:"",textContent:"",style:{},
                scrollIntoView(){},value:""}; },
              addEventListener(ev,fn){ ctx.__ready = fn; },
              createElement(){return mkEl();}, body:{appendChild(){},removeChild(){}} },
  localStorage:{ _d:{}, getItem(k){return this._d[k]??null;}, setItem(k,v){this._d[k]=String(v);} },
  window:{scrollTo(){}}, Date, JSON, Math, Blob:function(){},
  URL:{createObjectURL(){return"blob:";},revokeObjectURL(){}},
  setTimeout, alert(){}, confirm(){return false;}, FileReader:function(){}
};
vm.createContext(ctx);
vm.runInContext(code + "\n;globalThis.__P = PAYLOAD;", ctx);  // 见下方坑 1
ctx.__ready();                                                // 触发初始化
```

断言清单：
- 所有计算函数与卡片构建函数逐个调用不抛错
- 每个 `id` 容器渲染后 `innerHTML.length > 20`
- 交互路径：切 Tab / 切筛选 / 编辑入队 / 一键处理 / 跳转定位
- **空数据集不崩**：把各数组置空 + progress 归零后 `renderAll()`，再恢复
- 日期函数跨月跨年非负且单调

**第二层：无头 Chrome，真实渲染（抓视觉与布局问题）**

```bash
CHROME=$(ls -d "$LOCALAPPDATA/ms-playwright"/chromium-*/chrome-win64/chrome.exe 2>/dev/null | sort -V | tail -1)
[ -x "$CHROME" ] || CHROME="/c/Program Files/Google/Chrome/Application/chrome.exe"   # 回退系统 Chrome
"$CHROME" --headless=new --disable-gpu --no-sandbox --virtual-time-budget=4000 \
  --dump-dom "file:///D:/path/_preview.html" > _dom.html      # 执行JS后转储DOM
"$CHROME" --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
  --virtual-time-budget=5000 --window-size=1440,1200 \
  --screenshot="D:/abs/path/shot.png" "file:///D:/path/_preview.html"
```

- `file://` 可直接打开中文路径（实测可用）；真正会静默失败的是 `--screenshot` 给的相对路径，
  以及 `--user-data-dir` 指向含空格的临时目录。仍做成 ASCII 副本只是为了 `--dump-dom` 重定向好写。
- `--screenshot` **必须给绝对路径**，相对路径不写文件。
- 要单独看某张卡：用 Python 在副本上把 `renderXxx()` 的拼接改成只调那一张，
  再注入 `#todo,.cps,.tabs{display:none}` 置顶显示。
- 要验证非默认 Tab：在副本上把默认值 `s.tab || "anchor"` 改成目标 Tab。
- 验证完**删掉所有临时副本与截图**。

## 可运行基线（`assets/`，别从零手写）

本技能自带一套跑通过的骨架，四段式里 ②③④ 直接复用，只改 `extract_xxx()` 与 payload 里的 `sections`：

| 文件 | 作用 |
| --- | --- |
| `assets/build.py` | 常量 + `read/write/clip/cjk_count/docx_text` + `md_tables` + 抽取器范例 + `main()` 落盘 `payload.json`、`data/*.md`、强制写 `SELFTEST.md` |
| `assets/template.html` | 通用单文件壳：`#meta-source`/`#meta-built`/`#search`/`#tabs`/`#panels` 锚点齐全，样式脚本全内联，占位符 `const PAYLOAD = /*__PAYLOAD__*/null;` |
| `assets/render.py` | 注入 + 静态自检（占位符/外链/CDN/emoji/锚点/内联），不通过直接非零退出 |
| `assets/validate.js` | Node DOM 桩，`vm`/`els`/`mkEl` 已定义，跑真实脚本并断言每个面板 `innerHTML.length > 20`、空数据集不崩 |

最短闭环（复制到工作目录、改掉常量与 `extract_*` 即可）：

```bash
cp -r <skill>/assets ./wb && cd wb
python build.py                   # → out/payload.json + out/data/*.md + out/data/SELFTEST.md
python render.py                  # → _preview.html
node validate.js _preview.html    # DOM 桩断言，全绿再进无头 Chrome 截图
```

约定：`payload` 顶层是 `meta` + `sections[]`（每项 `{id, title, rows[]}`），
`build.py` 只负责把本地文档抽成这个形状，`template.html` 与 `render.py` 不必改。
`SKILL.md` 里引用的脚本一律写成 `assets/xxx`，保证从 skills 根目录直接可跑。

## 七个必踩的坑

1. **`const`/`let` 不会挂到 vm context 上**。测试里想访问 `PAYLOAD`／`state`，
   必须在同一脚本内追加 `globalThis.__P = PAYLOAD;` 再导出。`function` 声明则自动成为全局。
2. **层级分支必须先落盘再切换**。解析"幕→章"这类嵌套结构时，
   遇到上层标题的分支里若忘了 `chapters.append(cur)` 就直接 `cur = None`，
   会静默吞掉上层标题之前的最后一章。症状是章数少 1—2 且编号有缺口 → 用
   `[n for n in range(lo,hi) if n not in nos]` 查缺口定位。
3. **天数差用 `Math.floor` 而非 `Math.round`**。否则当天下午就会被判成"已过 1 天"，
   "昨日滚入"类逻辑全部误报。
4. **JS 字符串参数不能走 HTML 转义**。形如
   `onchange="f('{{x}}')"` 的写法，若 x 用 `esc()` 转义，`'` 会变成 `&#39;`，
   浏览器解码成裸 `'` 后 JS 语法错误。要另写 `arg()`：只删 `\` 和引号、限长，不转义成实体。
5. **SVG viewBox 高度要贴合内容**。`width:100%` 的 SVG 按 viewBox 比例撑高，
   viewBox 底部留白会被等比放大成一大片空白。算准最底元素 + 20px 再定 H，
   并给 svg 加 `style="max-width:880px"` 防止超宽拉伸。
6. **多参数 `append` 是静默杀手**。`L.append(a, b)` 只在运行到那一行时才报
   `TypeError: list.append() takes exactly one argument`，长脚本里靠肉眼很难找全。
   用 AST 一次扫干净：
   ```python
   import ast
   for n in ast.walk(ast.parse(src)):
       if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "append" and len(n.args) > 1:
           print("行", n.lineno, "参数个数", len(n.args))
   ```
7. **行内元素上的进度条高度失效**。`<span class="bar" style="height:8px">` 里的
   `height` 对 `display:inline` 无效，`<i style="height:100%">` 于是塌成 0——条形图整体不可见。
   在 CSS 里写 `.bar{display:block;width:100%;height:8px}`，别只依赖父级 flex 布局碰运气。
   **这类问题 Node DOM 桩测不出来，只能靠截图发现**。

## 数据模型建议

产物 `data/*.md` 优先用 Markdown 表格（可直接被其他工具消费），并保证：
- 每份表**首行注明抽取来源**，让使用者能回溯到原始文件
- 派生结论（如口径冲突、系统性偏差）单独成节，不要混在原始数据里
- 冲突检测很有价值：同一指标出现多个值就单列一节，这是人工最难发现的错误类型

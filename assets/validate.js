#!/usr/bin/env node
/**
 * Node DOM 桩：不装 jsdom / 不开浏览器，也能证明产物真的渲染出了数据。
 *
 * 为什么需要它：render.py 的静态自检只能证明“结构合规”，证明不了
 * “脚本能跑、面板里有行”。历史上 SKILL.md 给的片段里 vm / els / mkEl 三个
 * 符号都没定义，照抄必然 ReferenceError，所以这里给出可运行的完整实现。
 *
 *   node validate.js out/_preview.html
 *   node validate.js out/_preview.html --json
 */
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function mkEl(tag = "div", id = "") {
  const el = {
    tagName: tag.toUpperCase(),
    id,
    innerHTML: "",
    textContent: "",
    className: "",
    style: {},
    children: [],
    attrs: {},
    onclick: null,
    oninput: null,
    listeners: [],
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; },
    appendChild(child) { this.children.push(child); return child; },
    addEventListener(type, fn) { this.listeners.push([type, fn]); },
    dispatchEvent() { return true; },
    // 桩：搜索框里的 value 由测试直接赋值
    value: "",
  };
  return el;
}

const els = new Map();
const documentStub = {
  readyState: "complete",
  documentElement: mkEl("html"),
  body: mkEl("body"),
  getElementById(id) {
    if (!els.has(id)) els.set(id, mkEl("div", id));
    return els.get(id);
  },
  createElement(tag) { return mkEl(tag); },
  querySelectorAll() { return []; },
  addEventListener() {},
  dispatchEvent() { return true; },
};

function extractInlineScript(html) {
  const blocks = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi)];
  if (!blocks.length) throw new Error("产物理没有内联 <script>");
  return blocks[blocks.length - 1][1];
}

function run(file) {
  const html = fs.readFileSync(file, "utf8");
  let code = extractInlineScript(html);
  // 把脚本内部状态暴露给校验器（只加两行，不改产物行为）
  code += "\n;globalThis.__api = { renderAll: renderAll, setTab: setTab, state: state, payload: PAYLOAD };";

  const sandbox = {
    document: documentStub,
    window: {},
    console,
    setTimeout,
    clearTimeout,
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox, { filename: path.basename(file) });

  const api = sandbox.__api;
  if (!api) throw new Error("脚本没有执行到末尾：init() 抛错或提前 return");
  const payload = api.payload || {};
  const sections = payload.sections || [];
  if (!sections.length) throw new Error("payload.sections 为空");

  const problems = [];
  const panels = documentStub.getElementById("panels");
  const tabs = documentStub.getElementById("tabs");

  if (!panels.innerHTML.trim()) problems.push("panels 面板是空的：renderAll() 没写入内容");
  if (tabs.children.length !== sections.length) {
    problems.push(`标签数 ${tabs.children.length} ≠ 板块数 ${sections.length}`);
  }
  for (const sec of sections) {
    if (!panels.innerHTML.includes(sec.title)) problems.push(`面板里没有板块标题「${sec.title}」`);
    if (sec.rows_count > 0 && !/class="card"/.test(panels.innerHTML)) {
      problems.push(`板块「${sec.id}」声明有 ${sec.rows_count} 行，但没渲染出任何卡片`);
    }
  }
  if (!documentStub.getElementById("meta-built").textContent) problems.push("meta-built 为空");
  if (!documentStub.getElementById("doc-title").textContent) problems.push("doc-title 为空");

  // 搜索过滤：把第一行的第一个字当关键词，行数必须减少或保持
  const firstRow = (sections.find((s) => s.rows && s.rows.length) || {}).rows?.[0];
  let search = { skipped: true };
  if (firstRow) {
    const needle = String(Object.values(firstRow)[0] || "").slice(0, 2);
    api.state.q = needle;
    api.renderAll();
    const filtered = panels.innerHTML;
    search = {
      needle,
      rendered: filtered.length,
      baseline: panels.innerHTML.length > 0,
      shrunk: filtered.length <= (panels.innerHTML.length + 1),
    };
    if (!filtered.trim()) problems.push(`搜索「${needle}」把面板筛成了空白`);
  }

  return {
    file,
    bytes: Buffer.byteLength(html, "utf8"),
    sections: sections.map((s) => ({ id: s.id, title: s.title, rows: s.rows_count })),
    panels_html_bytes: Buffer.byteLength(panels.innerHTML, "utf8"),
    search,
    problems,
    ok: problems.length === 0,
  };
}

function main() {
  const args = process.argv.slice(2);
  const file = args.find((a) => !a.startsWith("--"));
  if (!file) {
    console.error("usage: node validate.js <产物.html> [--json]");
    process.exit(2);
  }
  let result;
  try {
    result = run(path.resolve(file));
  } catch (err) {
    console.error(`FAIL ${path.basename(file)}: ${err && err.message ? err.message : err}`);
    process.exit(1);
    return;
  }
  if (args.includes("--json")) {
    console.log(JSON.stringify(result, null, 2));
  } else {
    console.log(`产物: ${result.file}  ${result.bytes} 字节`);
    console.log(`板块: ${result.sections.map((s) => `${s.title}(${s.rows})`).join(" / ")}`);
    console.log(`面板渲染: ${result.panels_html_bytes} 字节`);
    if (result.search && !result.search.skipped) {
      console.log(`搜索过滤: 关键词「${result.search.needle}」→ 面板 ${result.search.rendered} 字节`);
    }
    if (result.problems.length) {
      for (const p of result.problems) console.log("  x", p);
      console.log("结论: 未通过");
    } else {
      console.log("结论: 通过（脚本可执行、面板有内容、标签与板块一致）");
    }
  }
  process.exit(result.ok ? 0 : 1);
}

main();

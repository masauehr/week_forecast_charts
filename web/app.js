// 週間〜長期予報用 天気図ビューア（Vanilla JS）。manifest.json を読んで、初期値・図種・期間・領域を切り替える。
"use strict";

const CHARTS = {
  c1: { label: "500hPa 平均と偏差", kind: "period",
    help: "500hPa高度（約5.5km上空の偏西風の流れ）のアンサンブル平均を等値線、平年からの差を色で示します。" +
          "青は平年より低い（トラフ・寒気が入りやすい）、赤は平年より高い（高気圧の尾根）。期間平均なので先の期間ほど偏差は弱まります。" },
  c2: { label: "500hPa スパゲッティ", kind: "step",
    help: "500hPa高度の特定の等値線（5400・5700gpm）を50メンバー全部重ねた図です。線が束ねられている場所は予報の確実性が高く、" +
          "ばらける場所は低い（流れの蛇行が不確か）ことを表します。太い黒線がアンサンブル平均です。" },
  c3high: { label: "850hPa気温 高温の確率", kind: "period",
    help: "左: 850hPa気温（約1.5km上空）の平年偏差のアンサンブル平均。右: 期間平均の偏差が+1℃以上になるメンバーの割合です。" +
          "割合は気象庁の「高い／平年並／低い」の階級確率とは定義が異なります。温暖化の傾向や平年値との系統差で高温側に偏って見えやすい点に注意。" },
  c3low: { label: "850hPa気温 低温の確率", kind: "period",
    help: "左: 850hPa気温の平年偏差のアンサンブル平均。右: 期間平均の偏差が−1℃以下になるメンバーの割合です。" +
          "気象庁の階級確率とは定義が異なります。" },
};
const CHART_ORDER = ["c1", "c2", "c3high", "c3low"];
const PERIOD_LABEL = { 1: "予報1〜7日目", 2: "予報8〜14日目" };
const REGION_LABEL = { asia: "東アジア", nh: "北半球" };

let M = null;                // manifest
const S = { init: null, chart: "c1", sel: null, region: "asia" };

const $ = (id) => document.getElementById(id);

function fmtInit(i) {
  return `${i.slice(0, 4)}/${i.slice(4, 6)}/${i.slice(6, 8)} ${i.slice(8, 10)}UTC`;
}
function validText(init, h) {
  const d = new Date(Date.UTC(+init.slice(0, 4), +init.slice(4, 6) - 1, +init.slice(6, 8), +init.slice(8, 10)) + h * 3600e3);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()} ${p(d.getUTCHours())}UTC`;
}
function selLabel(chart, v) {
  if (CHARTS[chart].kind === "period") return PERIOD_LABEL[v] || `期間${v}`;
  return `${v}時間後（${validText(S.init, v)}）`;
}

function initFiles() {
  const it = M.inits.find((x) => x.init === S.init);
  return it ? it.files : [];
}
function selsFor(chart) {
  return [...new Set(initFiles().filter((f) => f.chart === chart).map((f) => f.value))].sort((a, b) => a - b);
}
function regionsFor(chart, sel) {
  return [...new Set(initFiles().filter((f) => f.chart === chart && f.value === sel).map((f) => f.region))];
}

function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  if (p.get("init")) S.init = p.get("init");
  if (p.get("chart") in CHARTS) S.chart = p.get("chart");
  if (p.get("sel")) S.sel = +p.get("sel");
  if (p.get("region")) S.region = p.get("region");
}
function writeHash() {
  history.replaceState(null, "", "#" + new URLSearchParams(
    { init: S.init, chart: S.chart, sel: S.sel, region: S.region }).toString());
}

// 選択が今の初期値・図種に存在しなければ、近い有効な値へ直す
function normalize() {
  if (!M.inits.some((x) => x.init === S.init)) S.init = M.inits[0].init;
  const sels = selsFor(S.chart);
  if (!sels.includes(S.sel)) S.sel = sels[0];
  const regs = regionsFor(S.chart, S.sel);
  if (!regs.includes(S.region)) S.region = regs[0];
}

function seg(el, items, current, onPick) {
  el.replaceChildren();
  for (const [val, text] of items) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = text;
    b.setAttribute("aria-pressed", String(val === current));
    b.addEventListener("click", () => onPick(val));
    el.appendChild(b);
  }
}

function render() {
  normalize();
  writeHash();
  $("init").value = S.init;
  seg($("charts"), CHART_ORDER.filter((c) => selsFor(c).length).map((c) => [c, CHARTS[c].label]), S.chart,
    (c) => { S.chart = c; render(); });
  $("sel-lab").textContent = CHARTS[S.chart].kind === "period" ? "期間" : "時刻";
  seg($("sels"), selsFor(S.chart).map((v) => [v, selLabel(S.chart, v)]), S.sel, (v) => { S.sel = v; render(); });
  seg($("regions"), regionsFor(S.chart, S.sel).map((r) => [r, REGION_LABEL[r] || r]), S.region,
    (r) => { S.region = r; render(); });

  const f = initFiles().find((x) => x.chart === S.chart && x.value === S.sel && x.region === S.region);
  const img = $("img");
  if (f) {
    const title = `${CHARTS[S.chart].label} ${selLabel(S.chart, S.sel)} ${REGION_LABEL[S.region] || S.region}`;
    img.src = `charts/${S.init}/${f.name}`;
    img.alt = `${title}（初期値 ${fmtInit(S.init)}）`;
    $("caption").textContent = `${title} ／ 初期値 ${fmtInit(S.init)}`;
    $("status").textContent = "";
  } else {
    img.removeAttribute("src");
    $("status").textContent = "該当する図がありません。";
  }
  $("help").textContent = CHARTS[S.chart].help;
}

function move(dir, list, cur) {
  const i = list.indexOf(cur);
  return list[Math.min(list.length - 1, Math.max(0, i + dir))];
}

document.addEventListener("keydown", (e) => {
  if (!M || e.target.tagName === "SELECT") return;
  if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
    S.sel = move(e.key === "ArrowRight" ? 1 : -1, selsFor(S.chart), S.sel);
  } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
    const avail = CHART_ORDER.filter((c) => selsFor(c).length);
    S.chart = move(e.key === "ArrowDown" ? 1 : -1, avail, S.chart);
  } else return;
  e.preventDefault();
  render();
});

async function main() {
  try {
    const r = await fetch("manifest.json", { cache: "no-cache" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    M = await r.json();
  } catch (e) {
    $("status").textContent = "図の一覧(manifest.json)を読み込めませんでした: " + e.message;
    return;
  }
  const sel = $("init");
  for (const it of M.inits) {
    const o = document.createElement("option");
    o.value = it.init;
    o.textContent = fmtInit(it.init);
    sel.appendChild(o);
  }
  sel.addEventListener("change", () => { S.init = sel.value; render(); });
  $("updated").textContent = `更新: ${M.updated.replace("T", " ")}`;
  $("legal-source").textContent = M.legal.source;
  $("legal-clim").textContent = `平年値: ${M.legal.climatology}`;
  $("legal-disclaimer").textContent = M.legal.disclaimer;
  S.init = M.inits[0].init;
  readHash();
  render();
}
window.addEventListener("hashchange", () => { if (M) { readHash(); render(); } });
main();

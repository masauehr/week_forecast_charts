// 週間〜2週間予報用 統計図ビューア（Vanilla JS）。manifest.json を読んで、初期値・図種・期間・領域を切り替える。
// 天気図の標準版（maps/）と同様に、「並べて表示」（別の図を並べる／別の初期値と比較）と「画像の大きさ」を選べる。
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
const SIZES = [["fit", "画面に収める"], ["wide", "幅いっぱい"], ["80", "80%"], ["60", "60%"], ["40", "40%"]];
const SIDE_MODES = [["chart", "別の図を並べる"], ["init", "別の初期値と比較"]];

let M = null;                // manifest
// 左の図 = S 自身（init/chart/sel/region）。右の図 = S.p2（side=chart: 自由に選ぶ／side=init: 初期値だけ選び、他は左に揃える）
const S = { init: null, chart: "c1", sel: null, region: "asia", size: "fit", side: "off", mode: "chart",
            p2: { init: null, chart: null, sel: null, region: null } };

const $ = (id) => document.getElementById(id);

function fmtInit(i) {
  return `${i.slice(0, 4)}/${i.slice(4, 6)}/${i.slice(6, 8)} ${i.slice(8, 10)}UTC`;
}
function validText(init, h) {
  const d = new Date(Date.UTC(+init.slice(0, 4), +init.slice(4, 6) - 1, +init.slice(6, 8), +init.slice(8, 10)) + h * 3600e3);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()} ${p(d.getUTCHours())}UTC`;
}
function selLabel(init, chart, v) {
  if (CHARTS[chart].kind === "period") return PERIOD_LABEL[v] || `期間${v}`;
  return `${v}時間後（${validText(init, v)}）`;
}

// ---------------------------------------------------------------- 選べる値（初期値ごと）
const filesOf = (init) => { const it = M.inits.find((x) => x.init === init); return it ? it.files : []; };
const chartsFor = (init) => CHART_ORDER.filter((c) => filesOf(init).some((f) => f.chart === c));
const selsFor = (init, chart) => [...new Set(filesOf(init).filter((f) => f.chart === chart).map((f) => f.value))].sort((a, b) => a - b);
const regionsFor = (init, chart, sel) => [...new Set(filesOf(init).filter((f) => f.chart === chart && f.value === sel).map((f) => f.region))];
const findFile = (P) => filesOf(P.init).find((x) => x.chart === P.chart && x.value === P.sel && x.region === P.region);

// 選択が存在しなければ、近い有効な値へ直す（パネル P = {init, chart, sel, region}）
function fixPanel(P) {
  if (!M.inits.some((x) => x.init === P.init)) P.init = M.inits[0].init;
  const cs = chartsFor(P.init);
  if (!cs.includes(P.chart)) P.chart = cs[0];
  const ss = selsFor(P.init, P.chart);
  if (!ss.includes(P.sel)) P.sel = ss[0];
  const rs = regionsFor(P.init, P.chart, P.sel);
  if (!rs.includes(P.region)) P.region = rs[0];
}
const olderInit = (init) => { const l = M.inits.map((x) => x.init); const i = l.indexOf(init); return l[i + 1] || l[i - 1] || init; };

// 右の図を決める（side=init は左に揃えて初期値だけ変える／side=chart は p2 の選択をそのまま使う）
function rightPanel() {
  if (S.side === "off") return null;
  if (!S.p2.init || !M.inits.some((x) => x.init === S.p2.init)) S.p2.init = S.side === "init" ? olderInit(S.init) : S.init;
  if (S.side === "init") return { init: S.p2.init, chart: S.chart, sel: S.sel, region: S.region };
  if (!S.p2.chart) {                      // 初めて開くときは、左と違う図種を選んでおく
    const cs = chartsFor(S.p2.init);
    S.p2.chart = cs[(cs.indexOf(S.chart) + 1) % cs.length];
    S.p2.region = S.region;
  }
  fixPanel(S.p2);
  return S.p2;
}

// ---------------------------------------------------------------- URL
function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  if (p.get("init")) S.init = p.get("init");
  if (p.get("chart") in CHARTS) S.chart = p.get("chart");
  if (p.get("sel")) S.sel = +p.get("sel");
  if (p.get("region")) S.region = p.get("region");
  if (SIZES.some(([v]) => v === p.get("size"))) S.size = p.get("size");
  if (p.get("side") === "chart" || p.get("side") === "init") { S.side = p.get("side"); S.mode = S.side; } else if (p.has("init")) S.side = "off";
  if (p.get("init2")) S.p2.init = p.get("init2");
  if (p.get("chart2") in CHARTS) S.p2.chart = p.get("chart2");
  if (p.get("sel2")) S.p2.sel = +p.get("sel2");
  if (p.get("region2")) S.p2.region = p.get("region2");
}
function writeHash() {
  const q = { init: S.init, chart: S.chart, sel: S.sel, region: S.region, size: S.size };
  if (S.side !== "off") {
    q.side = S.side;
    q.init2 = S.p2.init;
    if (S.side === "chart") Object.assign(q, { chart2: S.p2.chart, sel2: S.p2.sel, region2: S.p2.region });
  }
  history.replaceState(null, "", "#" + new URLSearchParams(q).toString());
}

// ---------------------------------------------------------------- 部品
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
function fillSelect(el, items, current) {
  el.replaceChildren();
  for (const [val, text] of items) {
    const o = document.createElement("option");
    o.value = String(val);
    o.textContent = text;
    el.appendChild(o);
  }
  el.value = String(current);
}

// 画像1枚を表示する（n=1: 左、n=2: 右）
function showPanel(n, P) {
  const img = $("img" + n), cap = $("caption" + n), dl = $("dl" + n);
  const f = findFile(P);
  if (f) {
    const title = `${CHARTS[P.chart].label} ${selLabel(P.init, P.chart, P.sel)} ${REGION_LABEL[P.region] || P.region}`;
    const url = `charts/${P.init}/${f.name}`;
    img.src = url;
    img.alt = `${title}（初期値 ${fmtInit(P.init)}）`;
    cap.textContent = `${title} ／ 初期値 ${fmtInit(P.init)}`;
    dl.href = url;
    dl.download = f.name;
    dl.hidden = false;
  } else {
    img.removeAttribute("src");
    img.alt = "";
    cap.textContent = "この組み合わせの図はありません。";
    dl.hidden = true;
  }
}

function render() {
  fixPanel(S);
  const R = rightPanel();
  writeHash();
  $("init").value = S.init;

  // 左の選択
  seg($("charts"), chartsFor(S.init).map((c) => [c, CHARTS[c].label]), S.chart, (c) => { S.chart = c; render(); });
  $("sel-lab").textContent = CHARTS[S.chart].kind === "period" ? "期間" : "時刻";
  seg($("sels"), selsFor(S.init, S.chart).map((v) => [v, selLabel(S.init, S.chart, v)]), S.sel, (v) => { S.sel = v; render(); });
  seg($("regions"), regionsFor(S.init, S.chart, S.sel).map((r) => [r, REGION_LABEL[r] || r]), S.region, (r) => { S.region = r; render(); });

  // 表示（並べ方・大きさ）
  $("sideChk").checked = S.side !== "off";
  fillSelect($("sideMode"), SIDE_MODES, S.side === "off" ? S.mode : S.side);
  $("sideMode").hidden = S.side === "off";
  fillSelect($("sizeSel"), SIZES, S.size);

  // 右の選択
  $("sideRow").hidden = S.side === "off";
  const isInit = S.side === "init";
  for (const id of ["chart2", "sel2", "region2"]) $(id).hidden = isInit;
  if (R) {
    fillSelect($("init2"), M.inits.map((x) => [x.init, fmtInit(x.init)]), R.init);
    if (!isInit) {
      fillSelect($("chart2"), chartsFor(R.init).map((c) => [c, CHARTS[c].label]), R.chart);
      fillSelect($("sel2"), selsFor(R.init, R.chart).map((v) => [v, selLabel(R.init, R.chart, v)]), R.sel);
      fillSelect($("region2"), regionsFor(R.init, R.chart, R.sel).map((r) => [r, REGION_LABEL[r] || r]), R.region);
    }
  }

  // 画像
  $("views").className = `views size-${S.size}${R ? " two" : ""}`;
  $("view2").hidden = !R;
  showPanel(1, S);
  if (R) showPanel(2, R);
  $("help").textContent = CHARTS[S.chart].help + (R && S.side === "chart" && R.chart !== S.chart ? "（右の図: " + CHARTS[R.chart].help + "）" : "");
}

function move(dir, list, cur) {
  const i = list.indexOf(cur);
  return list[Math.min(list.length - 1, Math.max(0, i + dir))];
}

document.addEventListener("keydown", (e) => {
  if (!M || !M.inits || !M.inits.length) return;
  if (["SELECT", "INPUT", "TEXTAREA"].includes(e.target.tagName)) return;
  if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
    S.sel = move(e.key === "ArrowRight" ? 1 : -1, selsFor(S.init, S.chart), S.sel);
  } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
    S.chart = move(e.key === "ArrowDown" ? 1 : -1, chartsFor(S.init), S.chart);
  } else if (e.key === "c" || e.key === "C") {            // 並べて表示の切替
    S.side = S.side === "off" ? S.mode : "off";
  } else return;
  e.preventDefault();
  render();
});

function bindControls() {
  $("init").addEventListener("change", () => { S.init = $("init").value; render(); });
  $("sizeSel").addEventListener("change", () => {
    S.size = $("sizeSel").value;
    try { localStorage.setItem("wsc_stats_size", S.size); } catch (e) { /* 保存できない環境は無視 */ }
    render();
  });
  $("sideChk").addEventListener("change", () => { S.side = $("sideChk").checked ? S.mode : "off"; render(); });
  $("sideMode").addEventListener("change", () => { S.mode = S.side = $("sideMode").value; render(); });
  $("init2").addEventListener("change", () => { S.p2.init = $("init2").value; render(); });
  $("chart2").addEventListener("change", () => { S.p2.chart = $("chart2").value; render(); });
  $("sel2").addEventListener("change", () => { S.p2.sel = +$("sel2").value; render(); });
  $("region2").addEventListener("change", () => { S.p2.region = $("region2").value; render(); });
}

async function main() {
  try {
    const r = await fetch("manifest.json", { cache: "no-cache" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    M = await r.json();
  } catch (e) {
    $("status").textContent = "図の一覧(manifest.json)を読み込めませんでした: " + e.message;
    return;
  }
  if (!M.inits || !M.inits.length) {          // 図がまだ無い（手元でまだ作っていない等）: エラーにせず案内を出す
    $("status").textContent = "統計図がまだありません。ローカルで見るときは python pipeline.py で作ってから serve_local.py を起動してください（天気図は上のリンクから見られます）。";
    return;
  }
  fillSelect($("init"), M.inits.map((x) => [x.init, fmtInit(x.init)]), M.inits[0].init);
  $("updated").textContent = `更新: ${M.updated.replace("T", " ")}`;
  $("legal-source").textContent = M.legal.source;
  $("legal-clim").textContent = `平年値: ${M.legal.climatology}`;
  $("legal-disclaimer").textContent = M.legal.disclaimer;
  try {                                       // 画像の大きさは前回の選択を覚える
    const sv = localStorage.getItem("wsc_stats_size");
    if (sv && SIZES.some(([v]) => v === sv)) S.size = sv;
  } catch (e) { /* 既定のまま */ }
  S.init = M.inits[0].init;
  bindControls();
  readHash();
  render();
}
window.addEventListener("hashchange", () => { if (M && M.inits && M.inits.length) { readHash(); render(); } });
main();

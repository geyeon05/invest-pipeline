// 기업분석 진행 화면: 공책을 읽어 시안 모양으로 보여주고, 판단을 공책에 적는다 (server.py 경유).
// 계산·판단 규칙은 파이썬(엔진·공책)에 있다. 이 화면은 보여주기와 입력만 한다.
"use strict";

const PROFILE = [
  { key: "증명", short: "말보다 지킨 기록을 믿는다",
    more: ["경영진은 의심부터. 약속을 지킨 몇 년의 기록으로 믿는다", "판단은 공시로. 뉴스는 시야를 넓히는 데만"], steps: ["1 약속 이행", "7 정성 자료"] },
  { key: "버는 회사", short: "이미 돈을 버는 회사가 먼저",
    more: ["성장 회사는 영업CF가 꾸준히 늘면 인정 (5번 중 3번 증가)", "남는 돈은 재투자하는 회사를 더 믿는다"], steps: ["2 현금 창출", "3 자본 배분"] },
  { key: "적정 가격", short: "비싸면 사지 않고 기다린다",
    more: ["좋은 회사라도 비싸면 적정 가격까지 기다린다", "금리·환율은 사는 시점을 정할 때만 본다"], steps: ["8 가격 판단"] },
  { key: "오래 보유", short: "회사가 그대로면 몇 년",
    more: ["주가가 떨어져도 회사가 그대로면 기다린다", "회사가 바뀌거나 너무 비싸지면 나눠서 판다"], steps: ["9 최종 판단"] },
];
const STEP_Q = { 1: "경영진이 말한 대로 했나?", 2: "본업 현금이 꾸준히 늘었나?", 3: "번 돈을 어디에 썼나? 빚으로 높인 ROE인가?",
  4: "이익이 진짜인가?", 5: "빚이 위험한가?", 6: "대주주 쪽 회사와 거래가 많나?", 7: "해자·사건·뉴스는?", 8: "지금 비싼가?" };
const STEP_PROFILE = {
  2: "성장 회사는 영업CF가 꾸준히 늘면 인정한다 (5번 중 3번 이상 증가 + 연평균 0% 초과). 영업CF가 마이너스인 해는 경고: 탈락이 아니라 원인을 확인한다.",
  4: "이익조정 신호는 탈락이 아니라 경고다: 의심의 출발점이지 결론이 아니다. 신호가 여러 개 겹칠 때는 분석할 때 판단한다. 판단은 공시로 한다.",
  5: "재무 안전성에는 통과선이 없다: 같은 업종끼리 비교해서 본다. 자본잠식·이자보상비율 1 미만·스프레드 마이너스는 경고: 탈락이 아니라 원인을 확인한다. 빚으로 높인 ROE는 스프레드가 플러스일 때만 인정한다.",
};
const KIND_LABEL = { draft: "초안", feedback: "Claude의 냉정한 피드백", revise: "고친 판단 (한 번 더 피드백)", confirm: "확정한 판단",
  checked: "확인함", reopen: "다시 열기" };
const METHOD_CLASS = { "기존 부품": "k1", "자료 받기": "k2", "새 도구": "k3" };
const METHOD_WAIT = { "기존 부품": "확인 중", "자료 받기": "승인 필요", "새 도구": "의논 필요" };

const S = { cid: "", view: null, price: null, range: "y1", hov: null, sel: null, item: 1, infoOpen: null, profileOpen: false, drafts: {}, lastUpdated: null };
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const when = (iso) => (iso || "").slice(0, 16).replace("T", " ");

async function api(path, body) {
  const opt = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
  const r = await fetch(path, opt);
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
function say(text, ok) {
  const m = $("msg");
  m.hidden = !text; m.textContent = text || ""; m.className = "msg " + (ok ? "ok" : "err");
  if (ok) setTimeout(() => { if (m.textContent === text) m.hidden = true; }, 3000);
}

// ---------- 그리기 ----------
function render() {
  renderProfile();
  const v = S.view;
  const book = v && v.book;
  const has = !!(book && book.rounds && book.rounds.length);
  $("empty").hidden = has;
  ["progress", "info", "discuss", "final", "roles"].forEach((id) => ($(id).hidden = !has));
  $("hold").hidden = !(has && (v.holding || v.sold || (v.book.rounds[v.book.current.round - 1].final || {}).conclusion === "산다"));
  renderPrice();
  if (!v) { $("empty").textContent = "회사를 고르고 '분석 시작'을 누르세요."; return; }
  if (!has) { $("empty").textContent = `${v.company.name}의 공책이 아직 없습니다. '분석 시작'을 누르면 받아 둔 자료로 계산합니다 (외부 요청 없음).`; return; }
  const round = book.rounds[book.current.round - 1];
  const pages = Object.keys(round.steps).filter((k) => k !== "9" && !k.startsWith("h")).sort((a, b) => a - b).map((k) => round.steps[k]);   // 9 최종 판단은 아래 칸에서 따로
  const st = (p) => v.status[String(p.no)];
  renderProgress(v, round, pages, st);
  renderInfo(pages.filter((p) => p.lane === "info"), st);
  renderDiscuss(pages.filter((p) => p.lane === "discuss"), st, v);
  renderFinal(pages, st, v);
  renderHold(v);
  $("roles").querySelector("div").innerHTML = book.roles.map((r) =>
    `<span>${esc(when(r.at))} · ${r.by === "user" ? "나" : "AI"} · ${esc(r.what)}</span>`).join("");
}

function renderProfile() {
  $("profile").innerHTML = `
    <div class="head"><h2 style="color:var(--navy)">내 투자 성향</h2>
      <button type="button" class="ghost" id="ptoggle">${S.profileOpen ? "간단히" : "자세히"}</button></div>
    <div class="pgrid ${S.profileOpen ? "open" : ""}">${PROFILE.map((c) => `
      <div class="pcard"><div><b>${esc(c.key)}</b><div class="s">${esc(c.short)}</div></div>
        ${S.profileOpen ? `<div class="more">${c.more.map((d) => `<span>· ${esc(d)}</span>`).join("")}
          <span class="tagrow">${c.steps.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</span></div>` : ""}
      </div>`).join("")}</div>
    <p class="rule"><b>탈락은 딱 하나</b>: 약속을 2번 이상 안 지킨 경영진. 나머지 경고는 원인을 확인한다</p>
    ${S.profileOpen ? `<span class="muted">전체 문답: investor_profile.md</span>` : ""}`;
  $("ptoggle").onclick = () => { S.profileOpen = !S.profileOpen; renderProfile(); };
}

function renderProgress(v, round, pages, st) {
  const doneN = pages.filter((p) => ["확인함", "확정"].includes(st(p))).length;
  const discN = pages.filter((p) => p.lane === "discuss" && st(p) !== "확정").length;
  const infoN = pages.filter((p) => p.lane === "info" && st(p) !== "확인함").length;
  const missing = [1, 2, 3, 4, 5, 6, 7, 8].filter((n) => !v.implemented.includes(n));
  const w = (n) => `${(n / 9) * 100}%`;
  $("progress").innerHTML = `
    <div class="head"><h2>${esc(v.company.name)} · ${round.no}회차 (${esc(round.mode)}) · 진행 상황</h2></div>
    <div class="bar" aria-hidden="true">
      <div style="width:${w(doneN)};background:var(--green)"></div><div style="width:${w(discN)};background:var(--orange)"></div>
      <div style="width:${w(infoN)};background:#7FB89A"></div><div style="width:${w(missing.length)};background:var(--gray)"></div>
      <div style="width:${w(1)};background:var(--navy)"></div></div>
    <div class="legend">
      <span><i class="dot" style="background:var(--green)"></i>끝 ${doneN}</span>
      <span><i class="dot" style="background:var(--orange)"></i>논의 필요 ${discN}</span>
      <span><i class="dot" style="background:#7FB89A"></i>확인 전 ${infoN}</span>
      ${missing.length ? `<span><i class="dot" style="background:var(--gray)"></i>아직 엔진에 없음 ${missing.length} (${missing.join(", ")})</span>` : ""}
      <span><i class="dot" style="background:var(--navy)"></i>최종 판단 ${round.final ? `확정: ${esc(round.final.conclusion)}` : v.final_lock && v.final_lock.length ? "잠김" : "열 수 있음"}</span></div>`;
}

function srcText(p) {
  const s = [...new Map((p.sources || []).map((x) => [`${x.year} ${x.filing}`, x])).keys()].sort();
  return s.length ? s.map((x) => x.replace(" ", " 접수번호 ")).join(", ") : "-";
}

function checksHtml(cs, title) {
  if (!cs.length) return "";
  const open = cs.filter((c) => c.status === "open");
  return `<div class="checks">
      <div class="head"><b style="font-size:13px">${title}</b>
        <span class="muted">${open.length ? `${open.length}건 남음 · 모두 확인해야 확정할 수 있음` : "모두 확인함"}</span></div>
      ${cs.map((c) => `<div class="ck"><span class="box ${c.status === "done" ? "done" : ""}" aria-hidden="true">${c.status === "done" ? "✓" : ""}</span>
        <span class="txt"><span>#${c.id} ${esc(c.text)}</span>
          ${c.status === "done" ? `<span class="res">→ ${esc(c.result)}${c.source ? ` [${esc(c.source)}]` : ""}</span>` : ""}</span>
        <span class="kind ${METHOD_CLASS[c.method]}">${esc(c.method)}</span>
        ${c.status === "open" ? `<span class="wait">${METHOD_WAIT[c.method]}</span>` : ""}</div>`).join("")}</div>`;
}

function renderInfo(info, st) {
  const sel = info.find((p) => p.no === S.infoOpen);
  const pageOpen = sel ? sel.checks.filter((c) => c.status === "open").length : 0;
  $("info").innerHTML = `
    <div class="head" style="justify-content:flex-start;gap:8px 16px"><h2>단순 정보</h2>
      <span class="muted" style="color:var(--green-ink)">${info.length ? `${info.length}단계` : "없음"}</span></div>
    <div class="chips">${info.map((p) => `
      <button type="button" class="chip ${S.infoOpen === p.no ? "on" : ""}" data-info="${p.no}" aria-expanded="${S.infoOpen === p.no}">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#2F855A" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5L20 7"></path></svg>
        <b>${p.no} ${esc(p.name)}</b><span class="s">${esc(st(p))}</span></button>`).join("")}</div>
    ${sel ? `<div class="infobox"><b>${sel.no}. ${esc(sel.name)} <span class="muted">· ${esc(STEP_Q[sel.no] || "")}</span></b>
      <ul class="facts">${sel.summary.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>
      <span class="muted">출처: ${esc(srcText(sel))}</span>
      ${checksHtml(sel.checks, "확인할 것 (단계 전체)")}
      ${st(sel) === "확인 전" ? `<div><button type="button" class="primary" data-act="checked" data-step="${sel.no}" ${pageOpen ? "disabled" : ""}>${pageOpen ? `확인함 불가 · 확인할 것 ${pageOpen}건 남음` : "확인함"}</button></div>`
        : `<span class="muted">확인함 · ${esc(when((sel.log.find((e) => e.kind === "checked") || {}).at))}</span>`}</div>` : ""}`;
  $("info").querySelectorAll("[data-info]").forEach((b) => (b.onclick = () => {
    const n = Number(b.dataset.info); S.infoOpen = S.infoOpen === n ? null : n; render(); }));
}

function liveItems(p) { return p.items.filter((it) => !it.gone); }

function renderDiscuss(list, st, v) {
  const box = $("discuss");
  if (!list.length) {
    box.innerHTML = `<div class="head" style="justify-content:flex-start;gap:8px 16px"><h2>논의할 부분</h2><span class="muted">지금은 없음</span></div>`;
    return;
  }
  if (!list.some((p) => p.no === S.sel)) { S.sel = list[0].no; S.item = 1; }
  const p = list.find((x) => x.no === S.sel);
  const items = liveItems(p);
  const info = v.items[String(p.no)];
  if (!(S.item >= 1 && S.item <= items.length)) S.item = 1;
  const it = items[S.item - 1], meta = info[S.item - 1];
  const s = meta.status;
  const order = { "초안 전": 1, "피드백 기다림": 1, "피드백 도착": 2, "확정": 3 }[s];
  const stage = (i, t) => `<span class="${order === i ? "cur" : order > i ? "past" : ""}">${t}</span>`;
  const key = (k) => `${v.company.company_id}|${p.no}|${S.item}|${k}`;
  const log = it.log.map((e) => {
    const cls = e.kind === "feedback" ? "fb" : e.kind === "confirm" ? "ok" : "";
    return `<div class="entry ${cls}"><span class="k">${KIND_LABEL[e.kind]} · ${e.by === "user" ? "나" : "Claude"} · ${esc(when(e.at))}</span>${esc(e.text)}</div>`;
  }).join("");
  const blocked = meta.open;
  let input = "";
  if (s === "초안 전") {
    input = `<label class="label" for="ta">내 판단 (초안)</label><textarea id="ta" rows="3" data-key="${esc(key("draft"))}">${esc(S.drafts[key("draft")] || "")}</textarea>
      <div><button type="button" class="primary" data-act="draft" data-step="${p.no}" data-item="${S.item}">피드백 받기</button></div>`;
  } else if (s === "피드백 기다림") {
    input = `<p class="note">대화창: <b>"${esc(v.company.name)} ${p.no}번 ${S.item}항목 피드백해줘"</b></p>`;
  } else if (s === "피드백 도착") {
    input = `<label class="label" for="ta">고친 판단</label>
      <textarea id="ta" rows="3" data-key="${esc(key("revise"))}" placeholder="피드백을 보고 다시 생각한 판단을 쓴다. 바꾸지 않아도 되고, 그 이유를 적는다">${esc(S.drafts[key("revise")] || "")}</textarea>
      <div class="btns">
        <button type="button" class="primary" data-act="confirm" data-step="${p.no}" data-item="${S.item}" ${blocked ? "disabled" : ""}>${blocked ? `확정 불가 · 확인할 것 ${blocked}건 남음` : "확정"}</button>
        <button type="button" class="ghost" data-act="revise" data-step="${p.no}" data-item="${S.item}">한 번 더 피드백 받기</button></div>`;
  } else if (s === "확정") {
    input = `<div><button type="button" class="ghost" data-act="reopen" data-step="${p.no}" data-item="${S.item}">다시 열기</button></div>`;
  }
  const gone = p.items.filter((x) => x.gone);

  box.innerHTML = `
    <div class="head" style="justify-content:flex-start;gap:8px 16px"><h2>논의할 부분</h2></div>
    <div class="split">
      <div class="list">${list.map((x) => `
        <button type="button" class="item ${x.no === S.sel ? "on" : ""}" data-sel="${x.no}">
          <span class="t"><span>${x.no}. ${esc(x.name)}</span><span class="badge ${st(x) === "확정" ? "done" : ""}">${esc(st(x))}</span></span>
          <span class="s">${liveItems(x).map((i) => esc(i.title)).join(" · ")}</span></button>`).join("")}</div>
      <div class="detail">
        <div><h3>${p.no}. ${esc(p.name)}</h3><span class="muted">${esc(STEP_Q[p.no] || "")}</span></div>
        <div><div class="label">핵심 사실</div><ul class="facts">${p.summary.map((l) => `<li>${esc(l)}</li>`).join("")}</ul></div>
        <div class="src">출처: ${esc(srcText(p))}</div>
        ${STEP_PROFILE[p.no] ? `<div class="mine"><div class="k">관련된 내 성향</div>${esc(STEP_PROFILE[p.no])}</div>` : ""}
        ${checksHtml(p.checks, "확인할 것 (단계 전체 · 끝나야 이 단계의 항목을 확정할 수 있음)")}
        <div class="label">논의 항목 (켜진 신호)</div>
        <div class="chips">${items.map((x, i) => `<button type="button" class="chip ${i + 1 === S.item ? "on" : ""}" data-it="${i + 1}">
          <b>(${i + 1}) ${esc(x.title)}</b><span class="s">${esc(info[i].status)}</span></button>`).join("")}</div>
        <div class="entry"><span class="k">(${S.item}) ${esc(it.title)}</span>${esc(it.detail)}</div>
        <div class="stages" aria-label="판단 단계">${stage(1, "① 초안")}${stage(2, "② 피드백")}${stage(3, "③ 확정")}</div>
        ${log}${checksHtml(it.checks, "확인할 것 (이 항목)")}${input}
        ${gone.length ? `<span class="muted">다시 계산하니 사라진 신호: ${gone.map((x) => esc(x.title)).join(", ")}</span>` : ""}
      </div></div>`;
  box.querySelectorAll("[data-sel]").forEach((b) => (b.onclick = () => { S.sel = Number(b.dataset.sel); S.item = 1; render(); }));
  box.querySelectorAll("[data-it]").forEach((b) => (b.onclick = () => { S.item = Number(b.dataset.it); render(); }));
}

function renderPrice() {
  const v = S.view, P = S.price;
  const name = v ? v.company.name : "";
  const head = `<div class="head"><h2 style="color:var(--navy)">주가 ${name ? `<span class="muted">· ${esc(name)}</span>` : ""}</h2>
    ${P && P.have ? `<div class="btns" role="group" aria-label="기간">
      <button type="button" class="${S.range === "y1" ? "primary" : "ghost"}" data-range="y1">1년</button>
      <button type="button" class="${S.range === "y5" ? "primary" : "ghost"}" data-range="y5">5년</button></div>` : ""}</div>`;
  if (!v) { $("price").innerHTML = head + `<p class="muted">-</p>`; return; }
  if (!P || !P.have) {
    $("price").innerHTML = head + `<p class="muted">주가를 아직 받지 않음 · 대화창에서 승인 후 받으면 여기에 나옴</p>`;
    return;
  }
  const ser = P[S.range], vals = ser.map((x) => x.value), n = vals.length;
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const cur = P.currency === "KRW" ? "원" : ` ${P.currency}`;
  const fmt = (x) => x.toLocaleString("ko-KR", { maximumFractionDigits: P.currency === "KRW" ? 0 : 2 });
  const xs = vals.map((_, i) => (n > 1 ? (i / (n - 1)) * 100 : 50));
  const ys = vals.map((x) => (hi > lo ? (1 - (x - lo) / (hi - lo)) * 100 : 50));
  const path = xs.map((x, i) => `${i ? "L" : "M"}${x.toFixed(2)} ${ys[i].toFixed(2)}`).join(" ");
  const chg = vals[n - 1] / vals[0] - 1;
  const day = P.prev ? P.last / P.prev - 1 : null;
  const sign = (r) => (r >= 0 ? "▲ +" : "▼ ") + (r * 100).toFixed(1) + "%";
  const h = S.hov;
  const tip = h != null && h < n ? `
    <div style="position:absolute;top:0;bottom:0;width:1px;background:#9AA5B1;left:${xs[h]}%"></div>
    <div style="position:absolute;width:10px;height:10px;border-radius:5px;background:var(--navy);border:2px solid #fff;transform:translate(-7px,-7px);left:${xs[h]}%;top:${ys[h]}%"></div>
    <div style="position:absolute;top:-6px;transform:translate(${xs[h] > 70 ? "-100%" : "8px"},-100%);left:${xs[h]}%;background:#1F2933;color:#fff;font-size:12px;border-radius:6px;padding:3px 8px;white-space:nowrap;pointer-events:none"><b>${fmt(vals[h])}${cur}</b> · ${esc(ser[h].label)}</div>` : "";
  $("price").innerHTML = head + `
    <div style="display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 20px">
      <span style="font-size:28px;font-weight:800">${fmt(P.last)}${cur}</span>
      ${day != null ? `<span style="font-size:14px">전일 대비 <b>${sign(day)}</b></span>` : ""}
      <span style="font-size:14px">${S.range === "y1" ? "1년" : "5년"} 변화 <b>${sign(chg)}</b></span>
      <span class="muted">${esc(P.date)} 종가</span></div>
    <div id="chart" style="position:relative;height:170px;margin-left:64px">
      <div class="muted" style="position:absolute;left:-64px;top:0">${fmt(hi)}</div>
      <div class="muted" style="position:absolute;left:-64px;bottom:0">${fmt(lo)}</div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" style="position:absolute;inset:0;width:100%;height:100%;overflow:visible"
        role="img" aria-label="${esc(name)} 주가 추이 ${fmt(vals[0])}에서 ${fmt(vals[n - 1])}">
        <line x1="0" y1="0" x2="100" y2="0" stroke="#E4E9EF" vector-effect="non-scaling-stroke"></line>
        <line x1="0" y1="50" x2="100" y2="50" stroke="#E4E9EF" vector-effect="non-scaling-stroke"></line>
        <line x1="0" y1="100" x2="100" y2="100" stroke="#C9D4DF" vector-effect="non-scaling-stroke"></line>
        <path d="${path}" fill="none" stroke="#0B3D63" stroke-width="2" stroke-linejoin="round" vector-effect="non-scaling-stroke"></path>
      </svg>${tip}
      <div style="position:absolute;inset:0;display:flex">${vals.map((_, i) => `<span data-hov="${i}" style="flex:1 1 0;height:100%"></span>`).join("")}</div>
    </div>
    <div class="muted" style="display:flex;justify-content:space-between;margin-left:64px"><span>${esc(ser[0].label)}</span><span>${esc(ser[n - 1].label)}</span></div>
    <div class="muted" style="border-top:1px solid #E4E9EF;padding-top:8px">${S.range === "y1" ? "1년(월말 종가)" : "5년(분기말 종가)"} 최고 <b>${fmt(hi)}</b> · 최저 <b>${fmt(lo)}</b> · 출처: Yahoo Finance (받아 둔 자료)</div>`;
  $("price").querySelectorAll("[data-range]").forEach((b) => (b.onclick = () => { S.range = b.dataset.range; S.hov = null; renderPrice(); }));
  $("price").querySelectorAll("[data-hov]").forEach((s) => (s.onmouseenter = () => { S.hov = Number(s.dataset.hov); renderPrice(); }));
  $("chart").onmouseleave = () => { S.hov = null; renderPrice(); };
}

function renderFinal(pages, st, v) {
  const box = $("final");
  const lock = v.final_lock || [];
  const fp = v.book.rounds[v.book.current.round - 1].steps["9"];
  let body;
  if (lock.length) {
    body = `<div class="locked"><b>아직 잠김 · 남은 것 ${lock.length}개</b>
      <ul class="facts" style="font-size:13px">${lock.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>`;
  } else if (!fp) {
    body = `<p class="note">1~8단계 끝 · 최종 판단을 열 수 있음</p>
      <div><button type="button" class="primary" data-act="open-final" data-step="9">최종 판단 열기</button></div>`;
  } else {
    const it = fp.items[0], meta = (v.items["9"] || [])[0] || { status: "초안 전", open: 0 };
    const s = meta.status;
    const order = { "초안 전": 1, "피드백 기다림": 1, "피드백 도착": 2, "확정": 3 }[s];
    const stage = (i, t) => `<span class="${order === i ? "cur" : order > i ? "past" : ""}">${t}</span>`;
    const key = (k) => `${v.company.company_id}|9|${k}`;
    const log = it.log.map((e) => {
      const cls = e.kind === "feedback" ? "fb" : e.kind === "confirm" ? "ok" : "";
      const extra = e.kind === "confirm" ? `<b>결론: ${esc(e.conclusion)}</b>${e.recheck && e.recheck.length ? ` · 다시 볼 조건: ${e.recheck.map(esc).join(" / ")}` : ""}\n` : "";
      return `<div class="entry ${cls}"><span class="k">${KIND_LABEL[e.kind]} · ${e.by === "user" ? "나" : "Claude"} · ${esc(when(e.at))}</span>${extra}${esc(e.text)}</div>`;
    }).join("");
    let input = "";
    if (s === "초안 전") {
      input = `<label class="label" for="ta">결론 초안 (산다 / 기다린다 / 사지 않는다와 그 이유)</label>
        <textarea id="ta" rows="4" data-key="${esc(key("draft"))}">${esc(S.drafts[key("draft")] || "")}</textarea>
        <div><button type="button" class="primary" data-act="draft" data-step="9" data-item="1">피드백 받기</button></div>`;
    } else if (s === "피드백 기다림") {
      input = `<p class="note">대화창: <b>"${esc(v.company.name)} 최종 판단 피드백해줘"</b></p>`;
    } else if (s === "피드백 도착") {
      const ch = S.drafts[key("choice")] || "";
      input = `<fieldset style="border:0;padding:0;margin:0;display:flex;flex-wrap:wrap;gap:8px"><legend class="label">결론</legend>
          ${v.final_choices.map((c) => `<label class="chip ${ch === c ? "on" : ""}"><input type="radio" name="concl" value="${c}" ${ch === c ? "checked" : ""} data-key="${esc(key("choice"))}"> ${c}</label>`).join("")}</fieldset>
        <label class="label" for="ta">고친 결론과 이유</label>
        <textarea id="ta" rows="4" data-key="${esc(key("revise"))}">${esc(S.drafts[key("revise")] || "")}</textarea>
        <label class="label" for="rc">다시 볼 조건 ('기다린다'면 꼭, 한 줄에 하나)</label>
        <textarea id="rc" rows="2" data-key="${esc(key("recheck"))}" placeholder="예: PER이 10배 아래로 오면&#10;다음 사업보고서에서 이자보상비율이 1을 넘으면">${esc(S.drafts[key("recheck")] || "")}</textarea>
        <div class="btns">
          <button type="button" class="primary" data-act="confirm" data-step="9" data-item="1" ${meta.open ? "disabled" : ""}>${meta.open ? `확정 불가 · 확인할 것 ${meta.open}건 남음` : "확정"}</button>
          <button type="button" class="ghost" data-act="revise" data-step="9" data-item="1">한 번 더 피드백 받기</button></div>`;
    } else if (s === "확정") {
      const outs = v.book.rounds[v.book.current.round - 1].outputs;
      const link = (f) => `<a href="/out?cid=${encodeURIComponent(v.company.company_id)}&name=${encodeURIComponent(f)}" target="_blank" rel="noopener">${esc(f)}</a>`;
      input = `<div class="checks"><b style="font-size:13px">결과물 3종 (분석 보고서 · 검증표 · 역할구분, md + PDF)</b>
          ${outs ? `<span class="muted">만든 때 ${esc(when(outs.at))} · 검증표: ${Object.entries(outs.verify).map(([k, n]) => `${esc(k)} ${n}건`).join(", ")}</span>
            <ul class="facts" style="font-size:14px">${Object.entries(outs.files).map(([k, f]) => `<li>${esc(k)}: ${f.pdf ? link(f.pdf) : "PDF 못 만듦"} · ${link(f.md)}</li>`).join("")}</ul>`
          : `<span class="muted">공책에 적힌 것만으로 만든다</span>`}
          <div class="btns"><button type="button" class="primary" data-act="outputs" data-step="9">${outs ? "다시 만들기" : "결과물 만들기"}</button>
          <button type="button" class="ghost" data-act="reopen" data-step="9" data-item="1">다시 열기</button></div></div>`;
    }
    body = `<div><div class="label">한 장에 모아 본 것</div><ul class="facts" style="font-size:14px">${fp.summary.map((l) => `<li>${esc(l)}</li>`).join("")}</ul></div>
      <div class="stages" aria-label="판단 단계">${stage(1, "① 초안")}${stage(2, "② 피드백")}${stage(3, "③ 확정")}</div>
      ${log}${checksHtml(it.checks, "확인할 것")}${input}`;
  }
  box.innerHTML = `<h2>9. 최종 판단</h2>${body}`;
}

function renderHold(v) {
  const box = $("hold");
  if (box.hidden) return;
  const r = v.book.rounds[v.book.current.round - 1];
  const checks = Object.keys(r.steps).filter((k) => k.startsWith("h")).sort((a, b) => b.slice(1) - a.slice(1));   // 최근 점검이 위
  let html = `<div class="head"><h2>보유 중 점검</h2>${v.holding ? `<span class="badge done">보유 중 · ${esc(v.holding.since)}부터</span>`
    : v.sold ? `<span class="badge">판 기록 · ${esc(v.sold.sold)}</span>` : ""}</div>`;
  if (!v.holding && !v.sold) {
    html += `<p class="muted"><b>실제로 샀을 때만</b> 누른다</p>
      <div class="btns" style="align-items:center"><label class="label" for="bday">산 날짜</label>
      <input id="bday" type="date" value="${new Date().toISOString().slice(0, 10)}" style="min-height:44px;border:1px solid #C9D4DF;border-radius:10px;padding:0 10px;font-family:inherit">
      <input id="bnote" placeholder="메모 (선택)" aria-label="메모" style="min-height:44px;border:1px solid #C9D4DF;border-radius:10px;padding:0 10px;font-family:inherit">
      <button type="button" class="primary" data-act="bought" data-step="9">샀다</button></div>`;
  } else if (v.holding) {
    html += `<p class="muted"><b>산 이유:</b> ${esc(v.holding.reason)}</p>
      <div class="btns" style="align-items:center"><label class="label" for="hreason">점검 이유</label>
      <select id="hreason" style="min-height:44px;border:1px solid #C9D4DF;border-radius:10px;padding:0 10px;font-family:inherit"><option>정기</option><option>바로</option></select>
      <button type="button" class="primary" data-act="start-check" data-step="9">보유 점검 시작</button></div>`;
  }
  for (const k of checks) {
    const p = r.steps[k], metas = v.items[k] || [], items = p.items.filter((x) => !x.gone);
    const sk = `h|${k}`;
    const n = (S.hItem && S.hItem[sk]) || 1;
    const it = items[n - 1], meta = metas[n - 1] || { status: "초안 전", open: 0 };
    const order = { "초안 전": 1, "피드백 기다림": 1, "피드백 도착": 2, "확정": 3 }[meta.status];
    const stage = (i, t) => `<span class="${order === i ? "cur" : order > i ? "past" : ""}">${t}</span>`;
    const key = (x) => `${v.company.company_id}|${k}|${n}|${x}`;
    const isDec = it.key === "decision";
    const log = it.log.map((e) => `<div class="entry ${e.kind === "feedback" ? "fb" : e.kind === "confirm" ? "ok" : ""}"><span class="k">${KIND_LABEL[e.kind]} · ${e.by === "user" ? "나" : "Claude"} · ${esc(when(e.at))}</span>${e.conclusion ? `<b>결론: ${esc(e.conclusion)}</b> · ` : ""}${esc(e.text)}</div>`).join("");
    const attrs = `data-step="${k}" data-item="${n}"`;
    let input = "";
    if (meta.status === "초안 전") {
      input = `<label class="label" for="ta">내 판단 (초안)</label><textarea id="ta" rows="3" data-key="${esc(key("draft"))}">${esc(S.drafts[key("draft")] || "")}</textarea>
        <div><button type="button" class="primary" data-act="draft" ${attrs}>피드백 받기</button></div>`;
    } else if (meta.status === "피드백 기다림") {
      input = `<p class="note">대화창: <b>"${esc(v.company.name)} ${esc(p.name.split(" (")[0])} ${n}항목 피드백해줘"</b></p>`;
    } else if (meta.status === "피드백 도착") {
      const ch = S.drafts[key("choice")] || "";
      input = (isDec ? `<fieldset style="border:0;padding:0;margin:0;display:flex;flex-wrap:wrap;gap:8px"><legend class="label">결론</legend>${v.hold_choices.map((c) =>
          `<label class="chip ${ch === c ? "on" : ""}"><input type="radio" name="hconcl" value="${c}" ${ch === c ? "checked" : ""} data-key="${esc(key("choice"))}"> ${c}</label>`).join("")}</fieldset>` : "")
        + `<label class="label" for="ta">고친 판단</label><textarea id="ta" rows="3" data-key="${esc(key("revise"))}">${esc(S.drafts[key("revise")] || "")}</textarea>
        <div class="btns"><button type="button" class="primary" data-act="confirm" ${attrs} ${meta.open ? "disabled" : ""}>${meta.open ? `확정 불가 · 확인할 것 ${meta.open}건 남음` : "확정"}</button>
        <button type="button" class="ghost" data-act="revise" ${attrs}>한 번 더 피드백 받기</button></div>`;
    }
    html += `<div class="detail" style="margin-top:6px"><div class="head"><h3>${esc(p.name)}</h3><span class="badge ${v.status[k] === "확정" ? "done" : ""}">${esc(v.status[k])}</span></div>
      <ul class="facts" style="font-size:14px">${p.summary.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>
      ${checksHtml(p.checks, "확인할 것 (이 점검 전체)")}
      <div class="chips">${items.map((x, i) => `<button type="button" class="chip ${i + 1 === n ? "on" : ""}" data-hit="${esc(sk)}|${i + 1}"><b>(${i + 1}) ${esc(x.title)}</b><span class="s">${esc(metas[i].status)}</span></button>`).join("")}</div>
      <div class="entry"><span class="k">(${n}) ${esc(it.title)}</span>${esc(it.detail)}</div>
      ${isDec ? `<span class="muted">앞 항목을 모두 확정한 뒤 확정</span>` : ""}
      <div class="stages">${stage(1, "① 초안")}${stage(2, "② 피드백")}${stage(3, "③ 확정")}</div>${log}${checksHtml(it.checks, "확인할 것 (이 항목)")}${input}</div>`;
  }
  box.innerHTML = html;
  box.querySelectorAll("[data-hit]").forEach((b) => (b.onclick = () => {
    const parts = b.dataset.hit.split("|");
    S.hItem = { ...(S.hItem || {}), [`${parts[0]}|${parts[1]}`]: Number(parts[2]) };
    render();
  }));
}

// ---------- 입력 ----------
document.addEventListener("input", (e) => { if (e.target.dataset && e.target.dataset.key) S.drafts[e.target.dataset.key] = e.target.value; });
document.addEventListener("change", (e) => { if ((e.target.name === "concl" || e.target.name === "hconcl") && e.target.dataset.key) { S.drafts[e.target.dataset.key] = e.target.value; render(); } });
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-act]");
  if (!b || b.disabled) return;
  const step = /^\d+$/.test(b.dataset.step || "") ? Number(b.dataset.step) : b.dataset.step;
  const kind = b.dataset.act, item = b.dataset.item ? Number(b.dataset.item) : null;
  const ta = $("ta");
  const text = ["draft", "revise", "confirm"].includes(kind) && ta ? ta.value.trim() : "";
  const pick = document.querySelector('input[name="concl"]:checked');
  const hpick = document.querySelector('input[name="hconcl"]:checked');
  const isHold = typeof step === "string" && step.startsWith("h");
  const conclusion = kind !== "confirm" ? undefined : step === 9 ? (pick ? pick.value : "") : isHold ? (hpick ? hpick.value : "") : undefined;
  const extra = kind === "bought" ? { day: ($("bday") || {}).value, text: ($("bnote") || {}).value || "" }
    : kind === "start-check" ? { reason: ($("hreason") || {}).value } : {};
  const recheck = step === 9 && kind === "confirm" && $("rc") ? $("rc").value.split("\n").map((x) => x.trim()).filter(Boolean) : undefined;
  try {
    if (kind === "outputs") say("결과물을 만드는 중입니다 (PDF 3개, 30초쯤 걸림)…", true);
    S.view = kind === "outputs" ? await api("/api/outputs", { cid: S.cid })
      : await api("/api/note", { cid: S.cid, step, kind, text, item, conclusion, recheck, ...extra });
    if (ta && ta.dataset.key) delete S.drafts[ta.dataset.key];
    S.lastUpdated = S.view.book.updated;
    say("공책에 적었습니다.", true);
  } catch (err) { say("공책에 적지 않았습니다: " + err.message, false); }
  render();
});

async function load(cid) {
  S.cid = cid; S.sel = null; S.infoOpen = null;
  S.view = cid ? await api("/api/book?cid=" + encodeURIComponent(cid)) : null;
  S.price = cid ? await api("/api/price?cid=" + encodeURIComponent(cid)) : null;
  S.lastUpdated = S.view && S.view.book ? S.view.book.updated : null;
  render();
}

// Claude가 대화창에서 공책에 적으면 저절로 보이게: 몇 초마다 공책을 다시 읽고, 바뀌었을 때만 다시 그린다
setInterval(async () => {
  if (!S.cid || document.hidden) return;
  try {
    const v = await api("/api/book?cid=" + encodeURIComponent(S.cid));
    const u = v.book ? v.book.updated : null;
    if (u !== S.lastUpdated) { S.view = v; S.lastUpdated = u; render(); }
    if (!S.price || !S.price.have) {          // 대화창에서 주가를 받으면 저절로 나오게
      const pr = await api("/api/price?cid=" + encodeURIComponent(S.cid));
      if (pr.have) { S.price = pr; renderPrice(); }
    }
  } catch (_) { /* 서버가 꺼져 있으면 조용히 넘어감 */ }
}, 4000);

document.querySelectorAll(".tab").forEach((t) => (t.onclick = () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("on", x === t));
  $("basic").hidden = t.dataset.tab !== "basic"; $("case").hidden = t.dataset.tab !== "case";
}));
// ---------- 회사 검색 (받아 둔 회사만, 외부 요청 없음) ----------
const Q = { list: [], filter: "all", hits: [], act: 0 };
const norm = (t) => String(t || "").toLowerCase().replace(/\(주\)|주식회사|inc\.?|corp\.?|co\.?|ltd\.?|[\s,.()&-]/g, "");

function searchHits(text) {
  const q = norm(text);
  let xs = Q.list.filter((c) => Q.filter === "all" || (Q.filter === "book" ? c.has_book : c.holding));
  if (q) {
    xs = xs.map((c) => {
      const name = norm(c.name), keys = c.keys.split(" ").map(norm);
      const score = name === q || keys.includes(q) ? 0 : name.startsWith(q) || keys.some((k) => k.startsWith(q)) ? 1
        : name.includes(q) || keys.some((k) => k.includes(q)) ? 2 : 9;
      return { c, score };
    }).filter((x) => x.score < 9).sort((a, b) => a.score - b.score || (b.c.has_book - a.c.has_book) || a.c.name.localeCompare(b.c.name, "ko")).map((x) => x.c);
  } else {
    xs = xs.slice().sort((a, b) => (b.holding - a.holding) || (b.has_book - a.has_book) || a.name.localeCompare(b.name, "ko"));
  }
  return xs.slice(0, 30);
}

function showHits() {
  const ul = $("colist"), inp = $("co");
  Q.hits = searchHits(inp.value);
  Q.act = Math.min(Q.act, Math.max(Q.hits.length - 1, 0));
  ul.innerHTML = Q.hits.length ? Q.hits.map((c, i) => `<li role="option" id="co-${i}" class="${i === Q.act ? "act" : ""}" data-pick="${esc(c.company_id)}" aria-selected="${i === Q.act}">
      <span>${esc(c.name)} <span class="meta">${esc(c.ticker || "")}</span></span>
      <span class="meta">${c.holding ? "보유 중" : c.has_book ? "분석 중" : ""}</span></li>`).join("")
    : `<li class="none">받아 둔 회사 중에 없음 · 새 회사는 대화창에서 "투자 분석 시작 ${esc(inp.value)}" (수집은 승인 후)</li>`;
  ul.hidden = false;
  inp.setAttribute("aria-expanded", "true");
  inp.setAttribute("aria-activedescendant", Q.hits.length ? `co-${Q.act}` : "");
}

function hideHits() { $("colist").hidden = true; $("co").setAttribute("aria-expanded", "false"); }

async function pick(cid) {
  const c = Q.list.find((x) => x.company_id === cid);
  if (!c) return;
  $("co").value = c.name;
  hideHits();
  await load(cid);
}

$("co").addEventListener("input", () => { Q.act = 0; showHits(); });
$("co").addEventListener("focus", showHits);
$("co").addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    if ($("colist").hidden) return showHits();
    Q.act = (Q.act + (e.key === "ArrowDown" ? 1 : -1) + Q.hits.length) % Math.max(Q.hits.length, 1);
    showHits();
  } else if (e.key === "Enter") {
    e.preventDefault();
    if (Q.hits[Q.act]) pick(Q.hits[Q.act].company_id).catch((err) => say(err.message, false));
  } else if (e.key === "Escape") hideHits();
});
$("colist").addEventListener("mousedown", (e) => {        // blur 전에 고르게 mousedown
  const li = e.target.closest("[data-pick]");
  if (li) { e.preventDefault(); pick(li.dataset.pick).catch((err) => say(err.message, false)); }
});
$("co").addEventListener("blur", () => setTimeout(hideHits, 100));
document.querySelectorAll(".fchip").forEach((b) => (b.onclick = () => {
  Q.filter = b.dataset.f;
  document.querySelectorAll(".fchip").forEach((x) => x.classList.toggle("on", x === b));
  $("co").focus(); showHits();
}));
async function refreshIndex() { Q.list = await api("/api/companies"); }

$("start").onclick = async () => {
  if (!S.cid) return say("회사를 먼저 고르세요.", false);
  if (S.view && S.view.book) return say("이미 공책이 있습니다. 다시 분석(새 회차)은 대화창에서 정합니다.", false);
  try { S.view = await api("/api/run", { cid: S.cid }); S.lastUpdated = S.view.book.updated; say("공책을 만들었습니다.", true); await refreshIndex(); }
  catch (err) { say(err.message, false); }
  render();
};

(async () => {
  await refreshIndex();
  const pre = new URLSearchParams(location.search).get("cid");   // 주소에 ?cid=KR:00126380 을 붙이면 그 회사로 바로 열기
  if (pre && Q.list.some((c) => c.company_id === pre)) { await pick(pre); return; }
  render();
})().catch((err) => say("서버에 연결하지 못했습니다: " + err.message, false));

// 과제 방: cases/<과제>/ 를 보여주고, 과제 공책(질문·주장)과 과제용 회사 공책에 판단을 적는다 (server.py 경유).
// app.js 의 도우미(esc, api, say, when, checksHtml, KIND_LABEL, STEP_Q)를 함께 쓴다.
"use strict";

const C = { list: [], id: "", view: null, mode: "step", cell: null, cbook: null, q: null, item: 1, drafts: {}, last: null };

function flowHtml(scope, page, itNo, meta, ask) {
  // scope: {cid?} — 회사 공책이면 cid, 과제 공책이면 없음. ask: 피드백 요청 말
  const items = page.items.filter((x) => !x.gone);
  const it = items[itNo - 1];
  const s = meta.status;
  const order = { "초안 전": 1, "피드백 기다림": 1, "피드백 도착": 2, "확정": 3 }[s];
  const stage = (i, t) => `<span class="${order === i ? "cur" : order > i ? "past" : ""}">${t}</span>`;
  const key = (k) => `${C.id}|${scope.cid || "book"}|${page.no}|${itNo}|${k}`;
  const attrs = `data-cact data-step="${esc(page.no)}" data-item="${itNo}" ${scope.cid ? `data-cid="${esc(scope.cid)}"` : ""}`;
  const log = it.log.map((e) => {
    const cls = e.kind === "feedback" ? "fb" : e.kind === "confirm" ? "ok" : "";
    return `<div class="entry ${cls}"><span class="k">${KIND_LABEL[e.kind]} · ${e.by === "user" ? "나" : "Claude"} · ${esc(when(e.at))}</span>${esc(e.text)}</div>`;
  }).join("");
  let input = "";
  if (s === "초안 전") {
    input = `<label class="label" for="cta">내 판단 (초안)</label><textarea id="cta" rows="3" data-ckey="${esc(key("draft"))}">${esc(C.drafts[key("draft")] || "")}</textarea>
      <div><button type="button" class="primary" ${attrs} data-kind="draft">피드백 받기</button></div>`;
  } else if (s === "피드백 기다림") {
    input = `<p class="note">Claude Code 대화창에서 <b>"${esc(ask)}"</b>라고 하면 피드백이 여기에 저절로 나타난다.</p>`;
  } else if (s === "피드백 도착") {
    input = `<label class="label" for="cta">고친 판단</label><textarea id="cta" rows="3" data-ckey="${esc(key("revise"))}">${esc(C.drafts[key("revise")] || "")}</textarea>
      <div class="btns"><button type="button" class="primary" ${attrs} data-kind="confirm" ${meta.open ? "disabled" : ""}>${meta.open ? `확정 불가 · 확인할 것 ${meta.open}건 남음` : "확정"}</button>
      <button type="button" class="ghost" ${attrs} data-kind="revise">한 번 더 피드백 받기</button></div>`;
  } else if (s === "확정") {
    input = `<div><button type="button" class="ghost" ${attrs} data-kind="reopen">다시 열기</button></div>`;
  }
  return `<div class="entry"><span class="k">(${itNo}) ${esc(it.title)}</span>${esc(it.detail)}</div>
    <div class="stages">${stage(1, "① 초안")}${stage(2, "② 피드백")}${stage(3, "③ 확정")}</div>
    ${log}${checksHtml(it.checks, "확인할 것 (이 항목)")}${input}`;
}

function caseRender() {
  const root = $("case");
  const v = C.view;
  const chips = C.list.map((x) => `<button type="button" class="chip ${x.id === C.id ? "on" : ""}" data-case="${esc(x.id)}">
      <b>${esc(x.title)}</b><span class="s">${x.stage}/7 · ${esc(x.id)}</span></button>`).join("");
  let html = `<section class="card"><div class="head"><h2>과제 목록</h2>
      <span class="muted">cases/ 에 과제가 생기면 저절로 나타남</span></div>
    <div class="chips">${chips || `<span class="muted">아직 과제가 없음</span>`}</div>
    <p class="muted"><b>새 과제 시작:</b> 대화창에서 "기자본 과제 시작 N주차" → 1단계 과제 읽기 → 2단계 대응표 (승인) → 여기서 3~7단계</p></section>`;
  if (!v) { root.innerHTML = html; return; }
  const cs = v.case, st = v.stages;
  html += `<section class="card">
      <div class="head"><h2>${esc(cs.title)}</h2><span class="muted">${esc(cs.id)} · IN ${esc(cs.in_file || "-")} · PRE ${esc(cs.pre_file || "-")}</span></div>
      ${cs.summary ? `<p style="margin:0">${esc(cs.summary)}</p>` : ""}
      <div class="chips">${(cs.alternatives || []).map((a) => `<span class="tag" style="font-size:13px">${esc(a)}</span>`).join("")}
        ${cs.deliver ? `<span class="muted">제출: ${esc(cs.deliver)}</span>` : ""}</div>
      <div class="stages" aria-label="과제 단계">${Object.entries(st).map(([n, name]) =>
        `<span class="${Number(n) === cs.stage ? "cur" : Number(n) < cs.stage ? "past" : ""}">${n} ${esc(name)}</span>`).join("")}</div>
      ${(cs.pre_concepts || []).length ? `<div class="mine"><div class="k">이번 주 PRE 관점</div>${cs.pre_concepts.map((p) => `<b>${esc(p.name)}</b>: ${esc(p.desc)}`).join(" · ")}</div>` : ""}
    </section>`;
  html += `<section class="card"><div class="head"><h2>대응표: 질문 → 부품</h2>
      <span class="badge ${cs.approved ? "done" : ""}">${cs.approved ? `승인 ${esc(cs.approved.slice(0, 10))}` : "승인 전"}</span></div>
    ${cs.questions.length ? `<div style="overflow-x:auto"><table style="border-collapse:collapse;width:100%;font-size:14px">
      <tr>${["#", "과제 질문", "PRE 관점", "필요한 재료", "쓸 부품", "없으면"].map((h) => `<th style="text-align:left;border-bottom:2px solid var(--line);padding:6px">${h}</th>`).join("")}</tr>
      ${cs.questions.map((q) => `<tr>${[q.no, q.q, q.pre, q.need, q.parts, q.missing || "−"].map((c) => `<td style="border-bottom:1px solid var(--line);padding:6px;vertical-align:top">${esc(c)}</td>`).join("")}</tr>`).join("")}
    </table></div>` : `<p class="muted">2단계에서 대화창으로 정한다.</p>`}</section>`;

  // 3단계: 회사 × 단계
  const steps = ["1", "2", "3", "4", "5", "6", "7", "8"];
  const cell = (row, k) => {
    const x = row.steps[k];
    if (!x) return `<td class="muted" style="padding:6px">-</td>`;
    const on = C.cell && C.cell.cid === row.company_id && C.cell.step === k;
    const bg = x.status === "확인함" || x.status === "확정" ? "var(--green-bg)" : x.lane === "info" ? "#F4FAF6" : "var(--orange-bg)";
    return `<td style="padding:4px"><button type="button" data-cell="${esc(row.company_id)}|${k}" title="${esc(x.titles.join(", ") || x.first)}"
      style="width:100%;min-height:44px;border-radius:8px;border:${on ? "2px solid var(--navy)" : "1px solid var(--line)"};background:${bg};font-family:inherit;font-size:13px;cursor:pointer">${esc(x.status)}</button></td>`;
  };
  let table;
  if (C.mode === "step") {
    table = `<tr><th></th>${v.grid.map((r) => `<th style="padding:6px;text-align:left">${esc(r.name)}</th>`).join("")}</tr>` +
      steps.map((k) => `<tr><th style="padding:6px;text-align:left;white-space:nowrap">${k} ${esc(STEP_NAMES[k])}</th>${v.grid.map((r) => cell(r, k)).join("")}</tr>`).join("");
  } else {
    table = `<tr><th></th>${steps.map((k) => `<th style="padding:6px;text-align:left;white-space:nowrap">${k} ${esc(STEP_NAMES[k])}</th>`).join("")}</tr>` +
      v.grid.map((r) => `<tr><th style="padding:6px;text-align:left">${esc(r.name)}</th>${steps.map((k) => cell(r, k)).join("")}</tr>`).join("");
  }
  html += `<section class="card lane-discuss"><div class="head"><h2>3단계 · 내 9단계로 회사 분석</h2>
      <div class="btns"><button type="button" class="${C.mode === "step" ? "primary" : "ghost"}" data-mode="step">단계별 보기</button>
      <button type="button" class="${C.mode === "company" ? "primary" : "ghost"}" data-mode="company">회사별 보기</button></div></div>
    <span class="muted">논의는 단계별로 회사끼리 비교하며 한다 · 약속 이행에서 탈락해도 끝까지 본다 · 9번 최종 판단은 5단계 주장으로 대신</span>
    ${v.grid.length ? `<div style="overflow-x:auto"><table style="border-collapse:collapse;width:100%">${table}</table></div>` : `<p class="muted">분석할 회사가 아직 없다 (2단계 대응표에서 정함).</p>`}
    <div id="ccell"></div></section>`;

  // 4단계 질문 · 5단계 주장
  const bv = v.book, r = bv.book.rounds[bv.book.current.round - 1];
  const qkeys = Object.keys(r.steps).filter((k) => k.startsWith("q")).sort((a, b) => a.slice(1) - b.slice(1));
  if (!C.q || !r.steps[C.q]) C.q = qkeys[0] || "claim";
  html += `<section class="card lane-discuss"><div class="head"><h2>4단계 · 과제 질문에 답하기</h2></div>
    ${qkeys.length ? `<div class="chips">${qkeys.map((k) => `<button type="button" class="chip ${C.q === k ? "on" : ""}" data-q="${k}"><b>${esc(r.steps[k].name)}</b><span class="s">${esc(bv.status[k])}</span></button>`).join("")}</div>` : `<p class="muted">대응표의 질문이 생기면 여기에 나온다.</p>`}
    ${C.q && C.q !== "claim" && r.steps[C.q] ? pageHtml({}, r.steps[C.q], bv, `${cs.id} 질문 ${C.q.slice(1)} 피드백해줘`) : ""}</section>
    <section class="card lane-final"><div class="head"><h2>5단계 · 주장 정하기</h2><span class="badge">${esc(bv.status.claim || "")}</span></div>
    ${r.steps.claim ? pageHtml({}, r.steps.claim, bv, `${cs.id} 주장 피드백해줘`) : ""}</section>
    <section class="card"><h2>6단계 · 결과물 / 7단계 · 마무리</h2>
      <p class="muted">보고서는 대화창에서 사용자가 준 뼈대대로 Claude가 쓴다 (확정한 판단·검증한 수치만). 검증표·역할구분은 공책에서 저절로 만든다. 모두 reports/ 에 md + PDF (PDF는 GitHub에 올리지 않음).</p>
      ${(cs.outputs || []).length ? `<ul class="facts">${cs.outputs.map((o) => `<li><b>${esc(o.name)}</b>: ${outLink(cs.id, o.pdf)} · ${outLink(cs.id, o.path)}</li>`).join("")}</ul>` : ""}
      ${cs.verify ? `<span class="muted">검증표: ${Object.entries(cs.verify).map(([k, n]) => `${esc(k)} ${n}건`).join(", ")}</span>` : ""}
      <div><button type="button" class="primary" data-outputs>${(cs.outputs || []).some((o) => o.kind === "검증표") ? "검증표·역할구분 다시 만들기" : "검증표·역할구분 만들기"}</button></div>
      ${(cs.wrapup || []).length ? `<ul class="facts">${cs.wrapup.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}</section>`;
  root.innerHTML = html;
  if (C.cell && C.cbook) $("ccell").innerHTML = cellHtml();
}

function outLink(id, f) {
  return f ? `<a href="/out-case?id=${encodeURIComponent(id)}&name=${encodeURIComponent(f)}" target="_blank" rel="noopener">${esc(f.split("/").pop())}</a>` : "PDF 없음";
}

const STEP_NAMES = { 1: "약속 이행", 2: "현금 창출", 3: "자본 배분", 4: "이익의 질", 5: "재무 안전성", 6: "특수관계자", 7: "정성 자료", 8: "가격 판단" };

function pageHtml(scope, page, bv, ask) {
  const items = page.items.filter((x) => !x.gone);
  const metas = bv.items[String(page.no)] || [];
  const k = `${scope.cid || "book"}|${page.no}`;
  const n = C.itemSel?.[k] || 1;
  return `<ul class="facts">${page.summary.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>
    ${checksHtml(page.checks, "확인할 것 (이 쪽 전체)")}
    ${items.length > 1 ? `<div class="chips">${items.map((x, i) => `<button type="button" class="chip ${i + 1 === n ? "on" : ""}" data-it="${esc(k)}|${i + 1}"><b>(${i + 1}) ${esc(x.title)}</b><span class="s">${esc(metas[i].status)}</span></button>`).join("")}</div>` : ""}
    ${items.length ? flowHtml(scope, page, n, metas[n - 1], ask) : ""}`;
}

function cellHtml() {
  const bv = C.cbook, r = bv.book.rounds[bv.book.current.round - 1];
  const p = r.steps[C.cell.step];
  if (!p) return "";
  const head = `<div class="detail" style="margin-top:10px"><div><h3>${esc(bv.company.name)} · ${p.no}. ${esc(p.name)}</h3>
    <span class="muted">${esc(STEP_Q[p.no] || "")} · ${esc(bv.status[String(p.no)])}</span></div>`;
  if (p.lane === "info") {
    const open = p.checks.filter((c) => c.status === "open").length;
    return head + `<ul class="facts">${p.summary.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>${checksHtml(p.checks, "확인할 것")}
      ${bv.status[String(p.no)] === "확인 전" ? `<div><button type="button" class="primary" data-cact data-kind="checked" data-step="${p.no}" data-cid="${esc(C.cell.cid)}" ${open ? "disabled" : ""}>확인함</button></div>` : ""}</div>`;
  }
  return head + pageHtml({ cid: C.cell.cid }, p, bv, `${C.id} ${bv.company.name} ${p.no}번 피드백해줘`) + `</div>`;
}

async function caseLoad(id) {
  C.id = id; C.cell = null; C.cbook = null;
  C.view = id ? await api("/api/case?id=" + encodeURIComponent(id)) : null;
  C.last = C.view ? JSON.stringify(C.view.case.updated) + C.view.book.book.updated : null;
  caseRender();
}

document.addEventListener("click", async (e) => {
  const root = $("case");
  if (!root.contains(e.target)) return;
  const t = e.target.closest("[data-case],[data-mode],[data-cell],[data-q],[data-it],[data-cact],[data-outputs]");
  if (!t || t.disabled) return;
  try {
    if (t.dataset.case !== undefined) return caseLoad(t.dataset.case);
    if (t.dataset.mode) { C.mode = t.dataset.mode; return caseRender(); }
    if (t.dataset.outputs !== undefined) {
      say("검증표·역할구분을 만드는 중입니다 (PDF, 30초쯤)…", true);
      C.view = await api("/api/case/outputs", { id: C.id });
      say("만들었습니다.", true);
      return caseRender();
    }
    if (t.dataset.q) { C.q = t.dataset.q; return caseRender(); }
    if (t.dataset.it) { const [a, b, n] = t.dataset.it.split("|"); C.itemSel = { ...(C.itemSel || {}), [`${a}|${b}`]: Number(n) }; return caseRender(); }
    if (t.dataset.cell) {
      const [cid, step] = t.dataset.cell.split("|");
      C.cell = { cid, step };
      C.cbook = await api(`/api/case/company?id=${encodeURIComponent(C.id)}&cid=${encodeURIComponent(cid)}`);
      return caseRender();
    }
    if (t.dataset.cact !== undefined) {
      const ta = $("cta");
      const kind = t.dataset.kind;
      const text = ["draft", "revise", "confirm"].includes(kind) && ta ? ta.value.trim() : "";
      C.view = await api("/api/case/note", { id: C.id, cid: t.dataset.cid || null, step: t.dataset.step, item: Number(t.dataset.item) || null, kind, text });
      if (ta && ta.dataset.ckey) delete C.drafts[ta.dataset.ckey];
      if (C.cell) C.cbook = await api(`/api/case/company?id=${encodeURIComponent(C.id)}&cid=${encodeURIComponent(C.cell.cid)}`);
      say("공책에 적었습니다.", true);
      caseRender();
    }
  } catch (err) { say("적지 않았습니다: " + err.message, false); }
});
document.addEventListener("input", (e) => { if (e.target.dataset && e.target.dataset.ckey) C.drafts[e.target.dataset.ckey] = e.target.value; });

// Claude가 대화창에서 과제 공책에 적으면 저절로 보이게
setInterval(async () => {
  if (!C.id || $("case").hidden || document.hidden) return;
  try {
    const v = await api("/api/case?id=" + encodeURIComponent(C.id));
    let changed = JSON.stringify(v.case.updated) + v.book.book.updated !== C.last;
    if (C.cell) {
      const cb = await api(`/api/case/company?id=${encodeURIComponent(C.id)}&cid=${encodeURIComponent(C.cell.cid)}`);
      if (!C.cbook || cb.book.updated !== C.cbook.book.updated) { C.cbook = cb; changed = true; }
    }
    if (changed) { C.view = v; C.last = JSON.stringify(v.case.updated) + v.book.book.updated; caseRender(); }
  } catch (_) { /* 조용히 */ }
}, 4000);

(async () => {
  try {
    C.list = await api("/api/cases");
    const pre = new URLSearchParams(location.search).get("case");   // 주소에 ?case=과제ID 를 붙이면 바로 열기
    if (pre && C.list.some((x) => x.id === pre)) {
      document.querySelector('.tab[data-tab="case"]').click();
      await caseLoad(pre);
      return;
    }
    caseRender();
  } catch (err) { say("과제 목록을 읽지 못했습니다: " + err.message, false); }
})();

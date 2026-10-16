import {api, routes} from "./ads-api.mjs";
import {localInput, inputDate, dateText} from "./time.mjs";
"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const state = {rows: [], editing: null, editingTimes: null, cursor: null, nextCursor: null, previous: [], filters: {placement: "", status: ""}, listBusy: false, listRequest: 0, delivery: null, pendingDeliveryRequest: null, publicBusy: false, publicGeneration: 0, publicOperation: 0, activePublicOperation: null, expiryTimer: null, visibleSince: null, imageLoaded: false, intersecting: false};
  const numberFormat = new Intl.NumberFormat("ko-KR");
  const statusText = {ACTIVE: "진행 중", RESERVED: "게시 대기", ENDED: "종료", STOPPED: "수동 중단"};
  const metricText = {READY: "집계 완료", PARTIAL: "일부 집계", PENDING: "집계 대기"};
  const resultText = {COUNTED: "인정", DELIVERY_DUPLICATE: "같은 배달의 중복 이벤트", REPEAT_SUPPRESSED: "반복 제한으로 제외", LATE_EVENT: "지연 허용 시간 초과", DELIVERY_INVALID: "유효하지 않은 배달", MEASUREMENT_UNAVAILABLE: "측정 불가"};
  const fmt = value => value === null || value === undefined ? "—" : (Number.isSafeInteger(value) ? numberFormat.format(value) : "정밀도 범위 초과");
  const message = (id, text, error = false) => {$(id).textContent = text; $(id).classList.toggle("error", error);};
  function integer(id, positive = false) {
    const value = $(id).value.trim();
    if (!(positive ? /^[1-9]\d*$/ : /^-?\d+$/).test(value) || !Number.isSafeInteger(Number(value))) throw new Error((positive ? "예산" : "우선순위") + "은 이 화면에서 정확히 표현할 수 있는 정수로 입력해 주세요.");
    return Number(value);
  }
  function formData() {
    const startValue = $("starts-at").value, endValue = $("ends-at").value;
    const start = new Date(state.editing && startValue === state.editingTimes.start ? state.editing.starts_at : inputDate(startValue)), end = new Date(state.editing && endValue === state.editingTimes.end ? state.editing.ends_at : inputDate(endValue));
    if (!$("ad-form").reportValidity()) throw new Error("필수 입력을 확인해 주세요.");
    if (!$("asset-id").value) throw new Error("먼저 광고 이미지를 업로드해 주세요.");
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end <= start) throw new Error("게시 종료 시각은 시작 시각보다 늦어야 합니다.");
    const body = {title: $("title").value, asset_id: $("asset-id").value, link_url: $("link-url").value, placement: $("placement").value, starts_at: start.toISOString(), ends_at: end.toISOString(), priority: integer("priority")};
    if ($("daily-budget").value.trim() || $("total-budget").value.trim()) {body.daily_budget_tokens = integer("daily-budget", true); body.total_budget_tokens = integer("total-budget", true);}
    return body;
  }
  function clearForm() {
    state.editing = null; state.editingTimes = null; $("ad-form").reset(); $("asset-id").value = "";
    $("starts-at").value = localInput(new Date()); $("ends-at").value = localInput(new Date(Date.now() + 86400000));
    $("editor-title").textContent = "새 광고 등록"; $("editor-context").textContent = "새로운 시험 광고를 작성합니다."; $("save-ad").textContent = "광고 등록";
    $("asset-image").hidden = true; $("asset-image").removeAttribute("src"); $("preview-section").hidden = true; $("preview-empty").hidden = false;
    $("asset-info").textContent = "이미지를 업로드하면 MongoDB에 원본을 저장합니다."; message("form-message", "");
  }
  function edit(row) {
    if (![row.version, row.priority, row.daily_budget_tokens, row.total_budget_tokens].filter(value => value !== null && value !== undefined).every(Number.isSafeInteger)) {message("global-message", "이 광고에는 브라우저 정밀도 범위를 넘는 정수가 있습니다. 정확한 값을 보존하기 위해 이 화면에서 수정할 수 없습니다.", true); return;}
    state.editing = row; $("title").value = row.title; $("placement").value = row.placement; $("priority").value = String(row.priority); $("link-url").value = row.link_url;
    $("starts-at").value = localInput(row.starts_at); $("ends-at").value = localInput(row.ends_at); $("asset-id").value = row.asset_id;
    state.editingTimes = {start: $("starts-at").value, end: $("ends-at").value};
    $("daily-budget").value = row.daily_budget_tokens == null ? "" : String(row.daily_budget_tokens); $("total-budget").value = row.total_budget_tokens == null ? "" : String(row.total_budget_tokens);
    $("image-file").value = ""; $("asset-image").src = routes.asset(row.asset_id); $("asset-image").hidden = false;
    $("asset-info").textContent = "기존 이미지입니다. 교체하려면 새 파일을 업로드하세요."; $("preview-section").hidden = true; $("preview-empty").hidden = false;
    $("editor-title").textContent = "광고 수정"; $("editor-context").textContent = "버전 " + row.version + " · " + statusText[row.status]; $("save-ad").textContent = "수정 저장";
    message("form-message", row.paused ? "수동 중단 상태를 유지한 채 내용을 수정합니다. 재개 기능은 제공하지 않습니다." : "기존 예산을 바꾸면 다음 예산 검증 후 공개 제공이 가능합니다.");
    $("editor-title").scrollIntoView({block: "start", behavior: "auto"}); $("title").focus({preventScroll: true});
  }
  function textNode(tag, text, className) {const element = document.createElement(tag); element.textContent = text; if (className) element.className = className; return element;}
  function drawRows() {
    $("ad-rows").replaceChildren(); $("list-empty").hidden = state.rows.length > 0;
    for (const row of state.rows) {
      const tr = document.createElement("tr"), title = document.createElement("td"), status = document.createElement("td"), budget = document.createElement("td"), metrics = document.createElement("td"), controls = document.createElement("td");
      const thumbnail = document.createElement("img"); thumbnail.src = routes.asset(row.asset_id); thumbnail.alt = ""; thumbnail.className = "row-thumbnail"; thumbnail.loading = "lazy"; title.append(thumbnail);
      title.append(textNode("div", row.title, "ad-title"), textNode("div", (row.placement === "top" ? "상단" : "하단") + " · 우선순위 " + fmt(row.priority), "subline"), textNode("div", dateText(row.starts_at) + " ~", "subline"), textNode("div", dateText(row.ends_at), "subline"));
      status.append(textNode("span", statusText[row.status] || row.status, "tag" + (row.status === "STOPPED" ? " stopped" : row.status === "ENDED" ? " warning" : "")));
      if (row.end_reason) status.append(textNode("span", row.end_reason === "BUDGET_EXHAUSTED" ? "토큰 소진" : "게시 기간 종료", "end-reason"));
      if (!row.budget_version) status.append(textNode("div", "예산 미설정 · 공개 부적격", "subline"));
      budget.append(textNode("div", "일일 " + fmt(row.daily_budget_tokens)), textNode("div", "총 " + fmt(row.total_budget_tokens), "subline"));
      const m = row.measurement || {}; metrics.append(textNode("div", "노출 " + fmt(m.impressions) + " · 클릭 " + fmt(m.clicks)), textNode("div", fmt(m.estimated_tokens) + " 토큰", "subline"), textNode("div", (metricText[m.status] || "집계 대기") + (m.is_stale ? " · 오래됨" : ""), "subline"));
      const buttons = document.createElement("div"); buttons.className = "row-actions";
      const modify = textNode("button", "수정"); modify.type = "button"; modify.addEventListener("click", () => edit(row));
      const stop = textNode("button", row.paused ? "중단됨" : "수동 중단", "danger"); stop.type = "button"; stop.disabled = row.paused; stop.addEventListener("click", () => stopAd(row, stop)); buttons.append(modify, stop); controls.append(buttons);
      tr.append(title, status, budget, metrics, controls); $("ad-rows").append(tr);
    }
    syncPagination();
  }
  function syncPagination() {$("page-prev").disabled = state.listBusy || state.previous.length === 0; $("page-next").disabled = state.listBusy || !state.nextCursor; $("page-label").textContent = (state.previous.length + 1) + "페이지 · " + state.rows.length + "건";}
  async function loadList() {
    const request = ++state.listRequest; state.listBusy = true; syncPagination();
    const query = new URLSearchParams({page_size: "10"});
    if (state.filters.placement) query.set("placement", state.filters.placement); if (state.filters.status) query.set("status", state.filters.status); if (state.cursor) query.set("cursor", state.cursor);
    try {const body = await api(routes.ads + "?" + query); if (request !== state.listRequest) return; state.rows = body.items; state.nextCursor = body.next_cursor; drawRows();}
    catch (error) {if (request === state.listRequest) throw error;}
    finally {if (request === state.listRequest) {state.listBusy = false; syncPagination();}}
  }
  async function loadSummary() {
    const body = await api(routes.summary), counts = body.counts || {}, m = body.measurement || {};
    $("count-active").textContent = fmt(counts.ACTIVE); $("count-reserved").textContent = fmt(counts.RESERVED); $("count-ended").textContent = fmt(counts.ENDED); $("count-stopped").textContent = "수동 중단 " + fmt(counts.STOPPED) + "건";
    $("today-impressions").textContent = fmt(m.impressions); $("today-clicks").textContent = fmt(m.clicks); $("today-tokens").textContent = fmt(m.estimated_tokens); $("summary-status").textContent = (metricText[m.status] || "집계 대기") + (m.is_stale ? " · 오래된 집계" : "");
    $("metrics-note").textContent = "KST 집계일 " + (m.metric_date_kst || "—") + " · 마지막 집계 " + dateText(m.as_of) + " · 5분 주기. 진행 중 상태만으로 공개 제공을 보장하지 않습니다. 예산 설정·최근 검증도 필요합니다.";
  }
  async function loadStatus() {
    const body = await api(routes.status), worker = body.budget_worker || {};
    $("worker-dot").classList.toggle("running", worker.running === true); $("worker-status").textContent = (worker.running ? "5분 예산 검증 작업 실행 중" : "예산 검증 작업 정지") + " · " + body.database + " · TEST";
    $("worker-detail").textContent = "마지막 성공 " + dateText(worker.last_succeeded_at) + " · 광고 로그 MongoDB 저장" + (worker.last_error ? " · 최근 집계 실패: " + worker.last_error : "");
  }
  async function reload(reset = false) {if (reset) {state.cursor = null; state.previous = [];} const results = await Promise.allSettled([loadList(), loadSummary(), loadStatus()]); const failed = results.find(result => result.status === "rejected"); if (failed) throw failed.reason;}
  async function stopAd(row, button) {
    if (!Number.isSafeInteger(row.version)) {message("global-message", "버전 값이 브라우저 정밀도 범위를 넘어서 이 화면에서 중단할 수 없습니다.", true); return;}
    button.disabled = true;
    try {await api(routes.ad(row.ad_id) + "/stop", {method: "POST", json: {version: row.version}, mutation: true}); message("global-message", "광고를 수동 중단했습니다. 기존 배달의 새 표시도 차단됩니다."); await reload(true); if (state.editing && state.editing.ad_id === row.ad_id) clearForm();}
    catch (error) {message("global-message", error.message + " 버전 충돌이면 목록을 새로고침한 뒤 다시 확인해 주세요.", true); button.disabled = row.paused;}
  }
  async function action(button, id, operation) {if (button.disabled) return; button.disabled = true; try {await operation();} catch (error) {message(id, error.message, true);} finally {button.disabled = false;}}
  $("ad-form").addEventListener("submit", event => {event.preventDefault(); action($("save-ad"), "form-message", async () => {
    const body = formData(), editing = state.editing; if (editing) body.version = editing.version;
    const result = await api((editing ? routes.ad(editing.ad_id) : routes.ads), {method: editing ? "PUT" : "POST", json: body, mutation: true});
    clearForm(); message("form-message", (editing ? "수정했습니다." : "등록했습니다.") + " 공개 확인 전 [지금 예산 검증·집계]를 실행하세요."); message("global-message", "광고 저장 완료 · 현재 상태 " + (statusText[result.status] || result.status)); await reload(true);
  });});
  $("upload-image").addEventListener("click", () => action($("upload-image"), "form-message", async () => {
    const file = $("image-file").files[0]; if (!file) throw new Error("업로드할 이미지 파일을 선택해 주세요."); if (file.size > 2000000) throw new Error("이미지 원본은 최대 2,000,000바이트입니다.");
    const data = new FormData(); data.append("image", file);
    const asset = await api(routes.assets, {method: "POST", body: data, mutation: true, fingerprint: [file.name, file.size, file.lastModified].join(":")});
    $("asset-id").value = asset.asset_id; $("asset-info").textContent = asset.width + " × " + asset.height + " · " + asset.mime_type + " · " + numberFormat.format(asset.byte_size) + "바이트";
    $("asset-image").src = routes.asset(asset.asset_id); $("asset-image").hidden = false; $("preview-section").hidden = true; $("preview-empty").hidden = false; message("form-message", "이미지 원본을 MongoDB에 저장했습니다. 광고를 저장하면 연결됩니다.");
  }));
  $("preview-ad").addEventListener("click", () => action($("preview-ad"), "form-message", async () => {
    const preview = await api(routes.preview, {method: "POST", json: formData()});
    const image = routes.asset(preview.asset_id); $("preview-desktop-image").src = image; $("preview-mobile-image").src = image;
    $("preview-desktop").classList.toggle("bottom", preview.placement === "bottom"); $("preview-mobile").classList.toggle("bottom", preview.placement === "bottom");
    $("preview-description").textContent = preview.title + " · " + (preview.placement === "top" ? "상단 120px" : "하단 104px") + " · 공개 배달·측정 없음"; $("preview-section").hidden = false; $("preview-empty").hidden = true; $("preview-heading").textContent = preview.title; $("preview-mobile-heading").textContent = preview.title; message("form-message", "서버에서 입력·이미지 원본을 확인했습니다.");
  }));
  $("new-ad").addEventListener("click", clearForm);
  $("reload").addEventListener("click", () => action($("reload"), "global-message", async () => {await reload(true); message("global-message", "목록과 집계 상태를 새로 불러왔습니다.");}));
  $("refresh-policy").addEventListener("click", () => action($("refresh-policy"), "global-message", async () => {
    const counts = await api(routes.refresh, {method: "POST", json: {}}); await reload(true); message("global-message", "예산 검증·집계 완료 · 확인 광고 " + fmt(counts.ads_checked) + "건 · 신규 소진 판정 " + fmt(counts.blocked) + "건 · 집계 행 " + fmt(counts.metrics_rows) + "개");
  }));
  $("filter-form").addEventListener("submit", event => {event.preventDefault(); state.filters = {placement: $("filter-placement").value, status: $("filter-status").value}; reload(true).catch(error => message("global-message", error.message, true));});
  $("page-next").addEventListener("click", () => {if (state.listBusy || !state.nextCursor) return; const before = state.cursor; state.previous.push(before); state.cursor = state.nextCursor; loadList().catch(error => {state.cursor = state.previous.pop(); syncPagination(); message("global-message", error.message, true);});});
  $("page-prev").addEventListener("click", () => {if (state.listBusy || !state.previous.length) return; const before = state.cursor; state.cursor = state.previous.pop(); loadList().catch(error => {state.previous.push(state.cursor); state.cursor = before; syncPagination(); message("global-message", error.message, true);});});
  $("logout").addEventListener("click", () => action($("logout"), "global-message", async () => {await api(routes.logout, {method: "POST", json: {}}); window.location.assign(routes.login);}));
  function hideBanner() {$("test-banner").hidden = true; $("test-image").removeAttribute("src"); state.imageLoaded = false; state.visibleSince = null; updateTestButtons();}
  function invalidatePublicRequest() {state.publicGeneration += 1; state.publicBusy = false; state.activePublicOperation = null; if (state.pendingDeliveryRequest) $("provide-ad").textContent = "배달 요청 재시도";}
  function clearDelivery() {invalidatePublicRequest(); clearTimeout(state.expiryTimer); hideBanner(); state.delivery = null; state.pendingDeliveryRequest = null; $("provide-ad").textContent = "새 배달 받기"; $("reconfirm-ad").disabled = true; $("test-state").textContent = "시험 배너를 비웠습니다."; message("test-message", "");}
  function updateTestButtons() {
    const showing = !!state.delivery && !$("test-banner").hidden && state.imageLoaded && document.visibilityState === "visible" && Date.now() < Date.parse(state.delivery.valid_until);
    if (showing && state.intersecting) {if (state.visibleSince === null) state.visibleSince = performance.now();} else state.visibleSince = null;
    $("test-impression").disabled = !showing || state.publicBusy || !state.delivery.measurement_available || state.visibleSince === null || performance.now() - state.visibleSince < 1000;
    $("test-click").disabled = !showing || state.publicBusy || !state.delivery.measurement_available;
  }
  function localImagePath(urlValue, deliveryId) {
    const url = new URL(urlValue), expected = "/api/ad-deliveries/" + encodeURIComponent(deliveryId) + "/image";
    if (url.protocol !== "https:" || !["127.0.0.1", "localhost", "[::1]"].includes(url.hostname) || url.hostname !== window.location.hostname || url.port !== window.location.port || url.pathname !== expected || url.username || url.password || url.hash || Array.from(url.searchParams.keys()).some(key => key !== "delivery_token") || url.searchParams.getAll("delivery_token").length !== 1) throw new Error("시험 이미지의 서버 주소 또는 경로가 로컬 환경과 일치하지 않습니다.");
    return url.pathname + url.search;
  }
  function acceptDelivery(body) {
    clearTimeout(state.expiryTimer);
    if (!body.ad) {clearDelivery(); $("test-state").textContent = "제공 가능한 광고가 없습니다. 예산·게시 기간·최근 검증 상태를 확인하세요."; return;}
    const until = Date.parse(body.valid_until); if (!Number.isFinite(until) || until <= Date.now()) {hideBanner(); $("test-state").textContent = "표시 유효 시각이 지났습니다. 다시 확인해 주세요."; return;}
    const imagePath = localImagePath(body.ad.image_url, body.ad.delivery_id);
    const same = state.delivery && state.delivery.ad.delivery_id === body.ad.delivery_id && $("test-image").getAttribute("src") === imagePath;
    state.delivery = body; $("reconfirm-ad").disabled = false; $("test-banner").classList.toggle("bottom", body.ad.placement === "bottom"); $("test-title").textContent = body.ad.title; $("test-banner").hidden = false;
    if (!same) {state.imageLoaded = false; state.visibleSince = null; $("test-image").src = imagePath;}
    $("test-state").textContent = (body.ad.placement === "top" ? "상단" : "하단") + " 시험 배달 · 표시 확인 " + dateText(body.evaluated_at) + " · " + (body.measurement_available ? "시험 측정 가능" : "측정 불가");
    state.expiryTimer = setTimeout(() => {hideBanner(); $("test-state").textContent = "표시 유효 시각이 지나 배너를 숨겼습니다. 현재 배달을 재확인할 수 있습니다.";}, Math.max(0, until - Date.now())); updateTestButtons();
  }
  async function provide(reconfirm = false, quiet = false) {
    if (state.publicBusy || !$("public-panel").open || (reconfirm && !state.delivery)) return;
    const generation = state.publicGeneration, operation = ++state.publicOperation;
    let pending = null;
    state.activePublicOperation = operation; state.publicBusy = true; updateTestButtons();
    try {
      const query = new URLSearchParams({placement: reconfirm ? state.delivery.ad.placement : $("test-placement").value}), headers = {};
      if (reconfirm) {query.set("delivery_id", state.delivery.ad.delivery_id); headers["X-Ad-Delivery-Token"] = state.delivery.ad.delivery_token;}
      else {if (!state.pendingDeliveryRequest || state.pendingDeliveryRequest.placement !== query.get("placement")) state.pendingDeliveryRequest = {placement: query.get("placement"), key: crypto.randomUUID()}; pending = state.pendingDeliveryRequest; headers["Idempotency-Key"] = pending.key;}
      const body = await api(routes.publicAds + "?" + query, {headers});
      if (generation !== state.publicGeneration || !$("public-panel").open || document.visibilityState !== "visible") return;
      if (pending === state.pendingDeliveryRequest) {state.pendingDeliveryRequest = null; $("provide-ad").textContent = "새 배달 받기";}
      acceptDelivery(body); if (!quiet) message("test-message", body.ad ? "시험 배달을 확인했습니다. 아직 이벤트는 전송하지 않았습니다." : "광고가 제공되지 않았습니다.");
    } catch (error) {
      if (generation !== state.publicGeneration || !$("public-panel").open || document.visibilityState !== "visible") return;
      if (pending && pending === state.pendingDeliveryRequest && error.status >= 400 && error.status < 500) state.pendingDeliveryRequest = null;
      $("provide-ad").textContent = state.pendingDeliveryRequest ? "배달 요청 재시도" : "새 배달 받기"; hideBanner(); message("test-message", error.message, true);
    } finally {if (state.activePublicOperation === operation) {state.publicBusy = false; state.activePublicOperation = null; updateTestButtons();}}
  }
  async function sendEvent(type) {
    if (state.publicBusy || !state.delivery) return;
    const button = $(type === "CLICK" ? "test-click" : "test-impression"); if (button.disabled) return;
    const delivery = state.delivery, generation = state.publicGeneration, operation = ++state.publicOperation; state.activePublicOperation = operation; state.publicBusy = true; updateTestButtons();
    try {
      const body = await api(routes.events, {method: "POST", headers: {"X-Ad-Delivery-Token": delivery.ad.delivery_token}, json: {event_id: crypto.randomUUID(), delivery_id: delivery.ad.delivery_id, event_type: type, occurred_at: new Date().toISOString()}});
      if (generation === state.publicGeneration && $("public-panel").open && document.visibilityState === "visible") message("test-message", (type === "CLICK" ? "클릭" : "노출") + " 시험 결과: " + (resultText[body.result] || body.result) + " · 인정 " + (body.counted ? "예" : "아니요") + ". 시험 배달은 집계·토큰 합계에서 제외됩니다.");
    } catch (error) {if (generation === state.publicGeneration && $("public-panel").open && document.visibilityState === "visible") message("test-message", error.message, true);} finally {if (state.activePublicOperation === operation) {state.publicBusy = false; state.activePublicOperation = null; updateTestButtons();}}
  }
  $("provide-ad").addEventListener("click", () => provide()); $("reconfirm-ad").addEventListener("click", () => provide(true)); $("clear-delivery").addEventListener("click", clearDelivery);
  $("test-impression").addEventListener("click", () => sendEvent("VIEWABLE_IMPRESSION")); $("test-click").addEventListener("click", () => sendEvent("CLICK"));
  $("test-image").addEventListener("load", () => {state.imageLoaded = true; updateTestButtons();}); $("test-image").addEventListener("error", () => {hideBanner(); message("test-message", "공개 시험 이미지를 읽을 수 없습니다. 배달을 다시 확인해 주세요.", true);});
  $("public-panel").addEventListener("toggle", () => {if (!$("public-panel").open) clearDelivery();});
  $("test-placement").addEventListener("change", clearDelivery);
  document.addEventListener("visibilitychange", () => {state.visibleSince = null; if (document.visibilityState !== "visible") {invalidatePublicRequest(); hideBanner();} else if (state.delivery && $("public-panel").open) provide(true, true); updateTestButtons();});
  const observer = new IntersectionObserver(entries => {state.intersecting = entries[0].intersectionRatio >= .5; updateTestButtons();}, {threshold: [0,.5,1]}); observer.observe($("test-image"));
  setInterval(updateTestButtons, 150); setInterval(() => {if (state.delivery && $("public-panel").open && document.visibilityState === "visible") provide(true, true);}, 1000);
  setInterval(() => loadStatus().catch(error => {$("worker-dot").classList.remove("running"); $("worker-status").textContent = "서버 상태 확인 실패"; $("worker-detail").textContent = error.message;}), 15000);
  $("timezone-note").textContent = "게시 시각은 한국 표준시(KST)로 입력·표시하고 서버에는 UTC로 저장합니다.";
  clearForm(); reload(true).catch(error => message("global-message", error.message, true));
})();

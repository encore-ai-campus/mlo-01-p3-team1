// 광고 API 경로와 전송 계약을 한곳에서 관리합니다. 인증 값은 저장하지 않습니다.
export const routes = Object.freeze({
  ads: "/api/admin/ads",
  assets: "/api/admin/ad-assets",
  summary: "/api/admin/ads/summary",
  preview: "/api/admin/ads/preview",
  publicAds: "/api/ads",
  events: "/api/ad-events",
  status: "/dev/ads/status",
  refresh: "/dev/ads/refresh",
  logout: "/dev/ads/logout",
  login: "/dev/ads/login",
  ad: id => "/api/admin/ads/" + encodeURIComponent(id),
  asset: id => "/api/admin/ad-assets/" + encodeURIComponent(id),
});
const pendingKeys = new Map();
  const csrf = () => {const item = document.cookie.split(";").map(value => value.trim()).find(value => value.startsWith("ads_sandbox_csrf=")); return item ? decodeURIComponent(item.slice("ads_sandbox_csrf=".length)) : "";};
  const keyFor = fingerprint => {if (!pendingKeys.has(fingerprint)) pendingKeys.set(fingerprint, crypto.randomUUID()); return pendingKeys.get(fingerprint);};
  export async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    const method = options.method || "GET";
    if (!["GET", "HEAD"].includes(method)) headers.set("X-CSRFToken", csrf());
    if (options.json !== undefined) {headers.set("Content-Type", "application/json"); options.body = JSON.stringify(options.json);}
    const fingerprint = options.mutation ? method + path + (options.fingerprint || options.body || "") : null;
    if (fingerprint) headers.set("Idempotency-Key", keyFor(fingerprint));
    let response;
    try {response = await fetch(path, {method, headers, body: options.body, credentials: "same-origin", cache: "no-store", redirect: "error"});}
    catch {throw new Error("서버에 연결할 수 없습니다. 입력을 유지한 채 같은 작업을 다시 시도할 수 있습니다.");}
    let body;
    try {body = await response.json();} catch {throw new Error("서버 응답을 확인할 수 없습니다. 로그인 또는 서버 상태를 확인해 주세요.");}
    if (!response.ok) {const fields = body.details && Array.isArray(body.details.fields) ? " · 필드: " + body.details.fields.join(", ") : ""; const error = new Error((body.message || "요청을 처리할 수 없습니다.") + (body.code ? " [" + body.code + "]" : "") + fields); error.status = response.status; throw error;}
    if (fingerprint) pendingKeys.delete(fingerprint);
    return body;
  }

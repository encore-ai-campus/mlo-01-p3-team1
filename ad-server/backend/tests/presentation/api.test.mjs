import {test} from "node:test";
import assert from "node:assert/strict";
import {webcrypto} from "node:crypto";
import {api, routes} from "../../presentation/ads/ads-api.mjs";

test("a failed mutation retries with the same key and sends CSRF on the same origin", async () => {
  const oldFetch = globalThis.fetch;
  const oldDocument = globalThis.document;
  const oldCrypto = globalThis.crypto;
  const calls = [];
  globalThis.document = {cookie: "ads_sandbox_csrf=local-fixture-csrf"};
  if (!globalThis.crypto) globalThis.crypto = webcrypto;
  globalThis.fetch = async (path, options) => {
    calls.push({path, ...options});
    if (calls.length === 1) throw new TypeError("simulated disconnect");
    return {ok: true, json: async () => ({saved: true})};
  };
  try {
    const options = {method: "POST", json: {version: 2}, mutation: true};
    await assert.rejects(api(routes.ad("local-id") + "/stop", options));
    assert.deepEqual(await api(routes.ad("local-id") + "/stop", options), {saved:true});
    assert.equal(calls[0].headers.get("Idempotency-Key"), calls[1].headers.get("Idempotency-Key"));
    assert.equal(calls[1].headers.get("X-CSRFToken"), "local-fixture-csrf");
    assert.equal(calls[1].credentials, "same-origin");
    assert.equal(calls[1].redirect, "error");
    await api(routes.ad("local-id") + "/stop", options);
    assert.notEqual(calls[1].headers.get("Idempotency-Key"), calls[2].headers.get("Idempotency-Key"));
  } finally {
    globalThis.fetch = oldFetch;
    globalThis.document = oldDocument;
    if (!oldCrypto) delete globalThis.crypto;
  }
});

test("version conflicts preserve the status and field diagnostics for the page", async () => {
  const oldFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ok:false, status:409, json:async()=>({
    code:"VERSION_CONFLICT", message:"새로고침해 주세요.", details:{fields:["version"]},
  })});
  try {
    await assert.rejects(api(routes.ads), error => error.status === 409 && error.message.includes("version"));
  } finally { globalThis.fetch = oldFetch; }
});

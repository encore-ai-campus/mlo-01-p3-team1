import {test} from "node:test";
import assert from "node:assert/strict";
import {inputDate, localInput, dateText} from "../../presentation/ads/time.mjs";

test("KST midnight and milliseconds survive a browser-independent round trip", () => {
  const instant = "2026-10-15T15:00:00.123Z";
  assert.equal(localInput(instant), "2026-10-16T00:00:00.123");
  assert.equal(inputDate(localInput(instant)).toISOString(), instant);
  assert.equal(inputDate("2026-10-16T09:30").toISOString(), "2026-10-16T00:30:00.000Z");
});

test("invalid and timezone-bearing inputs are rejected", () => {
  for (const value of ["", "not-a-date", "2026-10-16T09:30Z", "2026-10-16T09:30+00:00"]) {
    assert.ok(Number.isNaN(inputDate(value).getTime()));
  }
  assert.equal(dateText(null), "—");
  assert.equal(dateText("bad-date"), "—");
});

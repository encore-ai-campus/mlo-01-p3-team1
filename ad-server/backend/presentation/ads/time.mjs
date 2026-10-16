// datetime-local의 의미를 브라우저 설정과 관계없이 한국 표준시로 고정합니다.
const KST_OFFSET = 9 * 60 * 60 * 1000;
export function localInput(value) {
  const date = new Date(value);
  return new Date(date.getTime() + KST_OFFSET).toISOString().slice(0, 23);
}
export function inputDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,3})?)?$/.test(value)) return new Date(NaN);
  return new Date(value + "+09:00");
}
export function dateText(value) {
  const date = new Date(value);
  return value && !Number.isNaN(date.getTime())
    ? date.toLocaleString("ko-KR", {timeZone: "Asia/Seoul", hour12: false}) : "—";
}

// ES5.1 Filebeat processor: allowlisted structured fields and bounded, redacted text.
var secrets = [];
function register(params) { secrets = params.secrets || []; }
function clean(value) {
    var text = String(value || "");
    if (/STATEMENT:|DETAIL:.*(?:INSERT|UPDATE)|-----BEGIN .*PRIVATE KEY-----/i.test(text)) {
        return "[database statement or private material omitted]";
    }
    for (var i = 0; i < secrets.length; i++) {
        if (secrets[i].length >= 6) text = text.split(secrets[i]).join("[REDACTED]");
    }
    text = text.replace(/(https?:\/\/)([^\s\/]+@)/gi, "$1[REDACTED]@");
    text = text.replace(/([?&][^\s"']*)/g, "?[REDACTED]");
    text = text.replace(/((?:authorization|cookie|password|passwd|token|secret|api[_-]?key|authKey)["']?\s*[=:]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)/gi, "$1[REDACTED]");
    text = text.replace(/\b(?:Bearer|Basic)\s+[A-Za-z0-9+\/_=.-]+/gi, "[REDACTED AUTH]");
    text = text.replace(/\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g, "[REDACTED JWT]");
    return text.slice(0, 4096);
}
function process(event) {
    var payload = event.Get("payload");
    var message = event.Get("message") || "";
    if (!payload && /^\s*\{/.test(message)) {
        try { payload = JSON.parse(message); } catch (ignored) {}
    }
    var dataset = event.Get("event.dataset") || "service";
    var unit = event.Get("systemd.unit") || event.Get("service.name") || dataset;
    var ops = {};
    var allow = "log_id event_id request_id attempt stage ok source category http_status bytes elapsed_seconds error_type events source_hash batch_id grids normalized_rows api_received parsed kafka_published status method job_id latency_seconds pipeline_latency_seconds count pending stream_records projected_events queued_events acked_events failed_events rss_bytes age_seconds active service state timestamp_basis collection event_type placement result ad_id is_test counted".split(" ");
    if (payload && typeof payload === "object") {
        for (var i = 0; i < allow.length; i++) {
            var key = allow[i]; var val = payload[key];
            if (val !== undefined && val !== null && typeof val !== "object") {
                ops[key] = typeof val === "string" ? clean(val).slice(0, 256) : val;
            }
        }
        if (payload.dataset) dataset = clean(payload.dataset);
        var time = payload["@timestamp"] || payload.requested_at || payload.received_at || (payload.t && payload.t.$date);
        if (time) event.Put("ops_timestamp", String(time));
        message = payload.message || payload.msg || (payload.stage ? "weather " + payload.stage : dataset);
        var level = payload["log.level"] || payload.level || payload.s;
        if (level) {
            level = String(level).toLowerCase();
            var levels = {e:"error",f:"fatal",w:"warn",i:"info",d1:"debug",d2:"debug",d3:"debug"};
            event.Put("log.level", levels[level] || level);
        }
        if (payload.ok === true) event.Put("event.outcome", "success");
        if (payload.ok === false || payload.status === "FAILED" || payload.status === "EXPIRED") event.Put("event.outcome", "failure");
        if (payload.status === "SUCCEEDED") event.Put("event.outcome", "success");
    }
    // Nginx combined logs contain client identifiers and query strings: retain only the request and status.
    if (dataset === "nginx_access") {
        var request = /"(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) ([^ ?"]+)(?:[^\"]*)" (\d{3})/.exec(String(message));
        if (request) {
            ops.method = request[1]; ops.http_status = Number(request[3]);
            message = request[1] + " " + request[2] + " " + request[3];
            if (Number(request[3]) >= 500) event.Put("event.outcome", "failure");
        } else { message = "[unparsed access log omitted]"; }
    }
    message = clean(message);
    if (!event.Get("log.level")) {
        var priority = event.Get("log.syslog.priority");
        var levelText = /\b(error|fatal|exception|traceback|panic)\b/i.test(message) ? "error" : (/\bwarn(?:ing)?\b/i.test(message) ? "warn" : "info");
        if (priority !== null && Number(priority) <= 3) levelText = "error";
        event.Put("log.level", levelText);
    }
    event.Put("event.dataset", dataset);
    event.Put("service.name", clean(unit));
    event.Put("ops", ops);
    event.Put("ops_fingerprint", JSON.stringify(ops));
    event.Put("message", message);
    if (ops.event_id || ops.log_id) event.Put("event.id", ops.event_id || ops.log_id);
    event.Delete("payload");
    return event;
}
function test() {
    if (clean("password=hiddenvalue https://user:pass@example.org/a?authKey=hidden") .indexOf("hidden") >= 0) throw "redaction failed";
    if (clean('{"password":"hiddenvalue"}').indexOf('hiddenvalue') >= 0) throw "JSON redaction failed";
    var e = process(new Event({payload: {stage:"collection",ok:false,password:"never",http_status:503},event:{dataset:"weather"}}));
    if (e.Get("ops.password") !== null || e.Get("event.outcome") !== "failure") throw "whitelist failed";
}

"""Route Burnwatch alerts into PagerDuty (or any on-call tool with an events API).

Burnwatch sends a generic JSON webhook in its own shape; PagerDuty's Events API v2 expects its own.
This tiny stdlib-only relay sits in between: it verifies the Burnwatch webhook, maps it to a
PagerDuty event, and triggers an incident. The same pattern works for Opsgenie and similar tools,
just change the target URL and the field mapping.

Setup:
  1. In PagerDuty, add an "Events API v2" integration to a service and copy its Integration Key.
  2. Run this with PD_ROUTING_KEY set (and BURNWATCH_WEBHOOK_SECRET set if webhook signing is on).
  3. In Burnwatch: Settings -> Alert delivery -> add a JSON webhook pointing at this server.
"""
import hashlib
import hmac
import json
import os
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

PD_ROUTING_KEY = os.environ.get("PD_ROUTING_KEY")    # PagerDuty Events API v2 integration key
SECRET = os.environ.get("BURNWATCH_WEBHOOK_SECRET")  # per-org signing secret from the dashboard (optional)
PD_URL = "https://events.pagerduty.com/v2/enqueue"
MAX_AGE = 300

# Burnwatch severity -> PagerDuty severity
SEVERITY = {"critical": "critical", "high": "error", "medium": "warning", "low": "info"}


def _verified(body: bytes, headers) -> bool:
    if not SECRET:
        return True
    ts = headers.get("X-Burnwatch-Timestamp", "")
    sig = headers.get("X-Burnwatch-Signature", "").removeprefix("sha256=")
    if not ts or not sig:
        return False
    try:
        if abs(time.time() - int(ts)) > MAX_AGE:
            return False
    except ValueError:
        return False
    expected = hmac.new(SECRET.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def trigger_pagerduty(alert: dict) -> None:
    sev = alert.get("severity", "")
    event = {
        "routing_key": PD_ROUTING_KEY,
        "event_action": "trigger",
        # dedup_key collapses repeated deliveries of the same detection into one PD incident
        "dedup_key": alert.get("detection_id", ""),
        "payload": {
            "summary": (f"[Burnwatch] {sev} {alert.get('agent_name', '')}: "
                        f"{alert.get('summary', alert.get('type', 'anomaly'))}")[:1024],
            "severity": SEVERITY.get(sev, "warning"),
            "source": alert.get("agent_name") or alert.get("agent_id") or "burnwatch",
            "component": "burnwatch",
            "custom_details": alert.get("evidence", {}),
        },
        "links": [{"href": alert.get("dashboard_url", ""), "text": "Open in Burnwatch"}],
    }
    req = urllib.request.Request(
        PD_URL, data=json.dumps(event).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"PagerDuty returned {resp.status}")


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        if not _verified(body, self.headers):
            self.send_response(403)
            self.end_headers()
            return
        try:
            alert = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        self.send_response(200)
        self.end_headers()

        if alert.get("event") == "detection.created":
            try:
                trigger_pagerduty(alert)
            except Exception as exc:  # never crash the listener on a downstream hiccup
                print(f"[pagerduty] failed to relay: {exc}")

    def log_message(self, *args) -> None:
        return


if __name__ == "__main__":
    if not PD_ROUTING_KEY:
        raise SystemExit("Set PD_ROUTING_KEY to your PagerDuty Events API v2 integration key.")
    port = int(os.environ.get("PORT", "8089"))
    print(f"Burnwatch -> PagerDuty relay listening on :{port}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()

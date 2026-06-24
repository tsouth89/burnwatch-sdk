"""Turn Burnwatch alerts into an automatic kill-switch.

Burnwatch is observe-only by design: it never sits in your payment path (so it can't slow or
break your agent) and it never holds your keys. This example is the other half of the loop -
wiring its webhook alerts to an automatic response, so a drain is stopped without a human
watching Slack.

How to use:
  1. Run this server and expose it on a URL Burnwatch can reach (a tunnel, a small box, a lambda).
  2. In the dashboard: Settings -> Alert delivery -> add a webhook pointing at that URL.
  3. Replace pause_agent() below with whatever actually halts your agent.

Webhooks are not signed yet, so protect this endpoint with a shared secret: register the webhook
URL as https://your-host/hook?secret=YOUR_SECRET and set BURNWATCH_WEBHOOK_SECRET to the same
value. Stdlib-only, like the SDK - no dependencies.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

SECRET = os.environ.get("BURNWATCH_WEBHOOK_SECRET")  # shared secret in the webhook URL's ?secret=
ACT_ON = {"high", "critical"}                         # only kill on serious alerts, not every nudge


def pause_agent(agent_id: str, agent_name: str, reason: str) -> None:
    """YOUR kill-switch. Burnwatch can't do this for you - it never holds your keys.

    Replace this with whatever stops the agent: revoke its spending allowance, flip a feature
    flag, kill the process, rotate the funding wallet, or page a human. Keep it fast and
    idempotent (the same alert can arrive more than once).
    """
    print(f"[KILL] pausing {agent_name} ({agent_id}): {reason}")
    # e.g. requests.post(f"https://your-control-plane/agents/{agent_id}/pause", timeout=5)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if SECRET and parse_qs(urlparse(self.path).query).get("secret", [None])[0] != SECRET:
            self.send_response(403)
            self.end_headers()
            return

        body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        try:
            alert = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        # Acknowledge immediately so Burnwatch's delivery doesn't retry; in production, hand the
        # actual work to a queue/thread instead of doing it inline here.
        self.send_response(200)
        self.end_headers()

        if alert.get("event") == "detection.created" and alert.get("severity") in ACT_ON:
            pause_agent(
                alert.get("agent_id", ""),
                alert.get("agent_name", "unknown"),
                alert.get("summary", alert.get("type", "anomaly")),
            )

    def log_message(self, *args) -> None:  # keep the console quiet
        return


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8088"))
    print(f"Burnwatch kill-switch listening on :{port} (acting on {sorted(ACT_ON)} alerts)")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()

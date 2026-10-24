#!/usr/bin/env python3
"""Answers a phone's internet probe, so Android offers the portal page.

When a phone joins a Wi-Fi network it asks for a known URL to find out
whether the network reaches the internet. Android asks
`connectivitycheck.gstatic.com/generate_204` and expects `204 No
Content`. Anything else tells Android the network is captive, and the
phone then shows its "sign in to network" notification. Tapping that
opens a webview on the URL this server redirects to.

Without that, Android treats the access point as broken and leaves it
for mobile data, which is what happened at the bench on 2026-10-08.

This serves one small page and nothing else. It must not be able to
take the DEQ link down: it runs as its own service, it holds no state,
and it never touches the gadget, the backend or the radio. The DEQ link
is the thing this project exists for, and a convenience for joining the
network is not allowed to risk it.

The captive webview is a poor place for the web app: it has no browser
menu, and Android closes it when the phone leaves the sign-in screen.
So the page's one job is to hand the phone to a real browser with an
`intent://` link, which the webview cannot handle itself and so passes
to Android.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN_ADDRESS = "192.168.4.1"
LISTEN_PORT = 80
APP_PORT = 8420

# The app's own address, as a phone on the access point reaches it.
APP_URL = f"http://{LISTEN_ADDRESS}:{APP_PORT}/"

# An `intent://` URL leaves the captive webview. A plain link does not:
# the webview opens it itself, where the app cannot be installed. Android
# cannot handle this scheme inside the webview, so it hands it to the
# system, which opens the real browser.
APP_INTENT_URL = (
    f"intent://{LISTEN_ADDRESS}:{APP_PORT}/#Intent"
    ";scheme=http"
    ";action=android.intent.action.VIEW"
    ";end"
)

PORTAL_PAGE = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DEQ Tune</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{
    margin: 0;
    min-height: 100vh;
    display: grid;
    place-items: center;
    background: #0e011a;
    color: #f4f0f8;
    font: 16px/1.5 system-ui, sans-serif;
    text-align: center;
    padding: 24px;
    box-sizing: border-box;
  }}
  h1 {{ font-size: 1.4rem; margin: 0 0 8px; }}
  p {{ margin: 0 0 24px; color: #bdb2c9; }}
  a.open {{
    display: inline-block;
    padding: 14px 28px;
    border-radius: 999px;
    background: #8d4ddb;
    color: #fff;
    font-weight: 600;
    text-decoration: none;
  }}
  .address {{
    margin-top: 28px;
    font-size: 0.85rem;
    color: #8a7f96;
  }}
  code {{ color: #bdb2c9; }}
</style>
</head>
<body>
  <main>
    <h1>DEQ Tune</h1>
    <p>You are connected to the bridge.</p>
    <a class="open" href="{APP_INTENT_URL}">Open the app</a>
    <p class="address">
      If that does nothing, open a browser and go to<br>
      <code>{LISTEN_ADDRESS}:{APP_PORT}</code>
    </p>
  </main>
</body>
</html>
"""

PORTAL_PAGE_BYTES = PORTAL_PAGE.encode("utf-8")

# The paths each platform probes. A phone asking one of these wants to
# know whether the network reaches the internet.
PROBE_PATHS = frozenset(
    {
        "/generate_204",
        "/gen_204",
        "/generate204",
        "/hotspot-detect.html",
        "/library/test/success.html",
        "/ncsi.txt",
        "/connecttest.txt",
        "/canonical.html",
        "/success.txt",
    }
)


class PortalRequestHandler(BaseHTTPRequestHandler):
    """Sends every request either a redirect to the portal page, or the
    page itself."""

    # Keep the protocol at HTTP/1.0 so each answer closes its connection.
    # A phone that holds a keep-alive socket open against a one-thread
    # server would block the next phone.
    protocol_version = "HTTP/1.0"
    server_version = "deq-portal"

    def do_GET(self) -> None:
        requested_path = self.path.split("?", 1)[0]

        if requested_path == "/portal":
            self.send_portal_page()
            return

        # Every other path, the probe paths included, gets a redirect.
        # The redirect is what tells the phone the network is captive.
        self.send_redirect_to_portal()

    def do_HEAD(self) -> None:
        self.send_redirect_to_portal()

    def send_portal_page(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PORTAL_PAGE_BYTES)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(PORTAL_PAGE_BYTES)

    def send_redirect_to_portal(self) -> None:
        self.send_response(302)
        self.send_header("Location", f"http://{LISTEN_ADDRESS}/portal")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, message_format: str, *arguments: object) -> None:
        """Writes one line per request to the journal, through systemd's
        stdout. The default writes to stderr with a timestamp that
        duplicates the journal's own."""
        print(f"deq-portal: {self.address_string()} {message_format % arguments}")


def main() -> None:
    server = ThreadingHTTPServer((LISTEN_ADDRESS, LISTEN_PORT), PortalRequestHandler)
    print(f"deq-portal: listening on {LISTEN_ADDRESS}:{LISTEN_PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()

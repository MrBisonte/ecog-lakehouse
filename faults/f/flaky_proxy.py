"""Fault F, spec 6: an HTTP proxy that forwards to a base URL and answers 503 to a fraction of
range requests, the way a busy object store or a tired CDN edge does.

    python faults/f/flaky_proxy.py <base_url> [port] [fraction]

Defaults: port 8766, fraction 0.1. Deterministic per run: a counter, not a random draw, so
every tenth range request fails at 0.1 and the two benchmark settings see the same failures.
"""

import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_URL, PORT, FRACTION = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 8766, float(sys.argv[3]) if len(sys.argv) > 3 else 0.1
FORWARDED = ("Range", "If-Match", "If-None-Match")
RETURNED = ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges", "Last-Modified", "ETag")


class Flaky(BaseHTTPRequestHandler):
    ranges = 0

    def do_HEAD(self):
        self.forward()

    def do_GET(self):
        self.forward()

    def forward(self):
        if "Range" in self.headers:
            Flaky.ranges += 1
            if FRACTION > 0 and int(Flaky.ranges * FRACTION) != int((Flaky.ranges - 1) * FRACTION):
                self.send_response(503)
                self.end_headers()
                return
        request = Request(BASE_URL + self.path, method=self.command,
                          headers={h: self.headers[h] for h in FORWARDED if h in self.headers})
        try:
            with urlopen(request, timeout=60) as upstream:
                self.send_response(upstream.status)
                for h in RETURNED:
                    if upstream.headers.get(h):
                        self.send_header(h, upstream.headers[h])
                self.end_headers()
                if self.command == "GET":
                    self.wfile.write(upstream.read())
        except HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
        except BrokenPipeError:  # the client gave up on this request, nothing to answer
            pass

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Flaky).serve_forever()

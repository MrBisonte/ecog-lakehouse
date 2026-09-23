"""A static file server for the benches that honours HTTP Range requests, as GitHub Pages and
every object store do. The standard http.server answers a Range request with the whole file,
which makes DuckDB fall back to full downloads and hides faults A and F.

    python faults/serve.py <directory> [port]
"""

import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class Ranged(SimpleHTTPRequestHandler):
    chunk = -1

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def send_head(self):
        header = self.headers.get("Range", "")
        if not header.startswith("bytes="):
            return super().send_head()
        try:
            f = open(self.translate_path(self.path), "rb")  # noqa: SIM115
        except OSError:
            self.send_error(404)
            return None
        size = os.fstat(f.fileno()).st_size
        first, _, last = header[6:].partition("-")
        if first:
            lo, hi = int(first), min(int(last), size - 1) if last else size - 1
        else:  # a suffix range, the last N bytes, how Parquet readers find the footer
            lo, hi = max(size - int(last), 0), size - 1
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(self.translate_path(self.path)))
        self.send_header("Content-Range", f"bytes {lo}-{hi}/{size}")
        self.send_header("Content-Length", str(hi - lo + 1))
        self.end_headers()
        f.seek(lo)
        self.chunk = hi - lo + 1
        return f

    def copyfile(self, source, outputfile):
        outputfile.write(source.read(self.chunk))

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
    ThreadingHTTPServer(("127.0.0.1", port), partial(Ranged, directory=sys.argv[1])).serve_forever()

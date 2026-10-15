#!/usr/bin/env python3
"""Local review: serves <project>/storyboard/ (or any folder, like the style board) on this computer and saves notes.

For hosts without Claude artifacts (Codex, any terminal agent), or when the creator prefers to review locally.
Open the printed address, leave a note on any beat, press "Looks good: render it" when done. Every note lands in
<project>/storyboard/notes.json as {"beat": "p06" | "all", "text": ..., "at": ISO time}; the agent reads that file.
It serves the approval stops too (<project>/approvals/<stop>/), answering byte ranges so their videos can seek.
Run: python3 storyboard/serve.py <project or folder> [--port 8765]    (standard library only; Ctrl+C to stop)
"""
import datetime
import http.server
import json
import os
import re
import sys
import threading


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    root = os.path.abspath(os.path.expanduser(sys.argv[1]))
    sb = os.path.join(root, "storyboard") if os.path.isdir(os.path.join(root, "storyboard")) else root
    if not os.path.exists(os.path.join(sb, "index.html")):
        sys.exit(f"nothing to review yet: {sb}/index.html doesn't exist (build the storyboard or the style board first)")
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8765
    notes_path = os.path.join(sb, "notes.json")
    lock = threading.Lock()

    def read_notes():
        try:
            return json.load(open(notes_path))
        except (OSError, ValueError):
            return []

    class Handler(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                          ".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8",
                          ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}

        def __init__(self, *a, **kw):
            super().__init__(*a, directory=sb, **kw)

        def log_message(self, *a):
            pass

        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.split("?")[0].endswith("/api/notes"):
                return self._json(200, read_notes())
            if self.headers.get("Range"):
                return self._range(self.headers["Range"])
            return super().do_GET()

        def _range(self, rng):
            """one byte range (206): a browser seeks a video this way, and iOS Safari won't play one without it"""
            path = self.translate_path(self.path)
            m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
            if not m or not os.path.isfile(path) or not (m.group(1) or m.group(2)):
                return super().do_GET()
            size = os.path.getsize(path)
            if m.group(1):
                start, end = int(m.group(1)), min(int(m.group(2)) if m.group(2) else size - 1, size - 1)
            else:                                               # a suffix: the last N bytes
                start, end = max(0, size - int(m.group(2))), size - 1
            if start >= size or start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            try:
                with open(path, "rb") as fh:
                    fh.seek(start)
                    left = end - start + 1
                    while left > 0:
                        chunk = fh.read(min(1 << 16, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):        # the player moved on mid-range: normal
                pass

        def do_POST(self):
            if not self.path.split("?")[0].endswith("/api/notes"):
                return self._json(404, {"error": "not found"})
            try:
                n = int(self.headers.get("Content-Length", 0))
                note = json.loads(self.rfile.read(min(n, 16384)))
                beat, text = str(note["beat"])[:16], str(note["text"]).strip()[:4000]
            except (ValueError, KeyError):
                return self._json(400, {"error": "send {beat, text}"})
            if not text:
                return self._json(400, {"error": "empty note"})
            with lock:
                notes = read_notes()
                notes.append({"beat": beat, "text": text, "at": datetime.datetime.now().isoformat(timespec="seconds")})
                json.dump(notes, open(notes_path, "w"), indent=1)
            print(f"note on {beat}: {text}", flush=True)
            return self._json(200, {"ok": True})

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Storyboard: http://127.0.0.1:{port}/   (notes -> {notes_path})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

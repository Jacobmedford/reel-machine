"""storyboard/serve.py answers byte ranges, so an approval page's video can seek (and plays at all on iOS Safari)."""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

SERVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "storyboard", "serve.py")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Range(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.data = bytes(range(256)) * 400                    # 102400 bytes
        with open(os.path.join(cls.tmp, "clip.mp4"), "wb") as fh:
            fh.write(cls.data)
        with open(os.path.join(cls.tmp, "index.html"), "w") as fh:
            fh.write("<p>page</p>")
        cls.port = free_port()
        cls.proc = subprocess.Popen([sys.executable, SERVE, cls.tmp, "--port", str(cls.port)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{cls.port}/index.html", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(5)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def get(self, rng=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/clip.mp4", headers={"Range": rng} if rng else {})
        try:
            r = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as err:
            return err.code, dict(err.headers), b""
        return r.status, dict(r.headers), r.read()

    def test_a_range_comes_back_partial(self):
        code, head, body = self.get("bytes=1000-1999")
        self.assertEqual(code, 206)
        self.assertEqual(head["Content-Range"], f"bytes 1000-1999/{len(self.data)}")
        self.assertEqual(body, self.data[1000:2000])

    def test_open_and_suffix_ranges(self):
        code, _, body = self.get("bytes=100000-")
        self.assertEqual((code, body), (206, self.data[100000:]))
        code, _, body = self.get("bytes=-500")
        self.assertEqual((code, body), (206, self.data[-500:]))

    def test_out_of_range_is_416(self):
        code, head, _ = self.get(f"bytes={len(self.data)}-")
        self.assertEqual(code, 416)

    def test_no_range_is_the_whole_file(self):
        code, _, body = self.get()
        self.assertEqual((code, body), (200, self.data))


if __name__ == "__main__":
    unittest.main()

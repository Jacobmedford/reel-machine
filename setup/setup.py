#!/usr/bin/env python3
"""Setup: checks what reel-machine needs on this computer and installs its own pieces. Safe to run again any time.

Run with any Python 3.10+:  python3 setup/setup.py [--check] [--matte]
  --check  report only, change nothing
  --matte  also install PyTorch for pipeline/matte.py (smoother cutouts for lo-fi, about 1 GB)

Prints one STATUS line per piece. A MISSING line ends with the exact fix for this computer. Ends with READY or
NOT READY. Standard library only, so it runs before anything else is installed. What it makes goes in
$REEL_MACHINE_HOME (default ~/reel-machine: .venv/, vendor/, and models/ for the optional matte model), next to the
style pack and projects, never inside the skill folder. The speech model, the render browser and HyperFrames itself
live in the user's own caches (Hugging Face's, the browser's, npm's), shared with anything else that uses them; on a
Linux where no browser build starts, setup installs Chromium in $REEL_MACHINE_HOME/browsers instead.
"""
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import urllib.request

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_home(env=os.environ, expand=os.path.expanduser, exists=os.path.exists):
    """the creator's home folder: the rule in pipeline/common.py, copied because setup runs before anything is
    installed and imports nothing of the kit's (tests/test_home.py holds this copy to that one)"""
    for k in ("REEL_MACHINE_HOME", "REEL_KIT_HOME"):
        if env.get(k):
            return expand(env[k])
    new, old = expand("~/reel-machine"), expand("~/reel-kit")
    if exists(new):
        return new
    if exists(os.path.join(old, "style", "style.json")):
        return old
    return new


HOME = resolve_home()
WIN = os.name == "nt"
VENV = os.path.join(HOME, ".venv")                     # everything setup makes lives in HOME: the skill folder may be read-only
VENV_PY = os.path.join(VENV, "Scripts", "python.exe") if WIN else os.path.join(VENV, "bin", "python")
HF = ["npx.cmd" if WIN else "npx", "-y", "hyperframes@0.8.139"]
GSAP_VERSION = "3.15.0"
GSAP_URL = f"https://cdn.jsdelivr.net/npm/gsap@{GSAP_VERSION}/dist/gsap.min.js"
GSAP_PATH = os.path.join(HOME, "vendor", "gsap.min.js")
CHECK = "--check" in sys.argv
HF_RUN = HF[:1] + ["--yes=false"] + HF[2:] if CHECK else HF   # --check runs only what is installed, never fetches
GSAP_SHA256 = "92bb9a96476f983d212a2bc4f54c889039c1696dd4461d40a736860938570fbb"   # gsap.min.js 3.15.0
OS = "macos" if sys.platform == "darwin" else "windows" if WIN else "linux"
FIX = {
    "ffmpeg": {"macos": "brew install ffmpeg", "linux": "sudo apt install ffmpeg",
               "windows": "winget install --id Gyan.FFmpeg -e   (then reopen the terminal)"},
    "node": {"macos": "brew install node",
             "linux": "Node 22+ (the render engine needs it; apt's is usually older): "
                      "curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs",
             "windows": "winget install --id OpenJS.NodeJS.LTS -e   (then reopen the terminal)"},
    "python": {"macos": "brew install python@3.12", "linux": "sudo apt install python3 python3-venv",
               "windows": "winget install --id Python.Python.3.12 -e"},
    "venv": {"macos": "brew install python@3.12, then run setup again",
             "linux": "sudo apt install python3-venv (python3.X-venv for the Python above), then run setup again",
             "windows": "winget install --id Python.Python.3.12 -e, then run setup again"},
}
ok = True
SANDBOX = os.environ.get("CODEX_SANDBOX")   # Codex marks its sandboxed commands; the render browser can't start in it
FULL_ACCESS = ("give this session full access (Codex: Full access in the permissions menu, or start it with "
               "`codex --sandbox danger-full-access`), then run setup again")


def status(name, good, detail="", fix=""):
    global ok
    ok = ok and good
    line = f"STATUS {name:<10} {'OK     ' if good else 'MISSING'} {detail}"
    if not good and fix:
        line += f"\n           fix: {fix}"
    print(line, flush=True)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def make_venv(base):
    """the kit's own Python environment. False when this Python can't make one (a Linux without python3-venv): what
    it printed is shown, and the half-made folder this run created is cleared so the next run starts clean."""
    print(f"creating .venv with {base} ...", flush=True)
    os.makedirs(HOME, exist_ok=True)
    r = run([base, "-m", "venv", VENV])
    if r.returncode:
        print((r.stdout + r.stderr).strip()[-800:], flush=True)
        shutil.rmtree(VENV, ignore_errors=True)
        return False
    return True


def sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_gsap():
    """GSAP from its pinned URL, kept only when its bytes match the pinned checksum"""
    os.makedirs(os.path.dirname(GSAP_PATH), exist_ok=True)
    part = GSAP_PATH + ".part"
    try:
        urllib.request.urlretrieve(GSAP_URL, part)
        if sha256(part) == GSAP_SHA256:
            os.replace(part, GSAP_PATH)
        else:
            print(f"GSAP download did not match its checksum ({GSAP_URL}): not installed", flush=True)
    except OSError as e:
        print(f"GSAP download failed: {e}", flush=True)
    finally:
        if os.path.exists(part):
            os.remove(part)


def home_in_kit(home=None, kit=KIT):
    """the home folder is the kit itself, or inside it: a clone made in the home folder (~/reel-machine is the default
    home), or REEL_MACHINE_HOME pointed at the clone. The creator's style, packs and projects would then be written
    into the kit, and pack install would recolor the kit's own packs."""
    h, k = os.path.realpath(home or HOME), os.path.realpath(kit)
    return h == k or h.startswith(k + os.sep)


def home_fix():
    """the exact fix for home_in_kit(), for this computer"""
    if os.environ.get("REEL_MACHINE_HOME") or os.environ.get("REEL_KIT_HOME"):
        return ("point REEL_MACHINE_HOME at a folder outside the kit (or unset it: the default ~/reel-machine is fine "
                "once the kit lives in your agent's skills folder), then run setup again")
    move = "mkdir -p {0} && mv {1} {0}/reel-machine && python3 {0}/reel-machine/setup/setup.py"
    return ("move the kit into your agent's skills folder and run setup from there. Claude Code: "
            + move.format("~/.claude/skills", shlex.quote(KIT)) + "   Codex: "
            + move.format("~/.agents/skills", shlex.quote(KIT)))


def version_of(cmd):
    try:
        out = run(cmd)
        return (out.stdout + out.stderr).strip()
    except OSError:
        return ""


FRAME = """<!doctype html><html><head><meta charset="utf-8"><title>render test</title></head><body>
<div id="root" data-composition-id="main" data-start="0" data-duration="1.000" data-fps="30" data-width="1080" data-height="1920"
 style="width:1080px;height:1920px;background:#222"></div>
<script src="vendor/gsap.min.js"></script>
<script>window.__timelines = window.__timelines || {}; window.__timelines["main"] = gsap.timeline({ paused: true }).to({}, { duration: 1 });</script>
</body></html>"""


BROWSER_FILE = os.path.join(HOME, "vendor", "browser-path.txt")     # a browser setup picked; the pipeline uses it
PLAYWRIGHT = "playwright@1.56.1"


def frame_test(browser=None):
    """one frame of a one-second composition with the render browser; returns (ok, output)"""
    import glob
    import tempfile
    d = tempfile.mkdtemp(prefix="reel-machine-render-test-")
    os.makedirs(os.path.join(d, "vendor"))
    shutil.copy(GSAP_PATH, os.path.join(d, "vendor", "gsap.min.js"))
    shutil.copy(os.path.join(KIT, "kit", "hyperframes.json"), d)
    with open(os.path.join(d, "index.html"), "w") as fh:
        fh.write(FRAME)
    env = dict(os.environ, **({"HYPERFRAMES_BROWSER_PATH": browser} if browser else {}))
    r = subprocess.run(HF_RUN + ["snapshot", "--at", "0.5", "--no-end", "--describe", "false"], cwd=d,
                       capture_output=True, text=True, env=env)
    good = r.returncode == 0 and bool(glob.glob(os.path.join(d, "snapshots", "frame-*.png")))
    shutil.rmtree(d, ignore_errors=True)
    return good, r.stdout + r.stderr


def linux_browser():
    """Linux on ARM (Claude Cowork's VM, Raspberry Pi, ARM servers) has no headless Chrome build, and Ubuntu's
    chromium-browser is a snap wrapper that won't start in a VM or container: install Playwright's Chromium into
    HOME/browsers instead and remember it. Returns the path that renders, or None."""
    dest = os.path.join(HOME, "browsers")
    env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=dest)
    print("installing a render browser that works on this Linux (Chromium, about 200 MB, once) ...", flush=True)
    root = hasattr(os, "geteuid") and os.geteuid() == 0
    cmd = ["npx", "-y", PLAYWRIGHT, "install"] + (["--with-deps"] if root else []) + ["chromium"]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode and not root:
        print("note: if it still can't start, its system libraries are missing: "
              f"sudo npx -y {PLAYWRIGHT} install-deps chromium", flush=True)
    import glob
    found = sorted(glob.glob(os.path.join(dest, "chromium_headless_shell-*", "*", "headless_shell"))) + \
        sorted(glob.glob(os.path.join(dest, "chromium-*", "*", "chrome")))
    for b in found:
        if frame_test(b)[0]:
            os.makedirs(os.path.dirname(BROWSER_FILE), exist_ok=True)
            with open(BROWSER_FILE, "w") as fh:
                fh.write(b)
            return b
    return None


def render_test():
    """launch the render browser for real: one frame of a one-second composition. READY has to mean it can render"""
    saved = open(BROWSER_FILE).read().strip() if os.path.exists(BROWSER_FILE) else None
    good, out = frame_test(saved if saved and os.path.exists(saved) else None)
    if not good and OS == "linux" and not SANDBOX and not CHECK:
        b = linux_browser()
        if b:
            good, out = True, ""
            print(f"render browser: {b}", flush=True)
    if good:
        status("render", True, "the render browser launched and drew a frame")
    elif SANDBOX or "MachPortRendezvousServer" in out:
        status("render", False, "BLOCKED: this agent's sandbox stops the render browser from starting", FULL_ACCESS)
    else:
        status("render", False, "the test frame failed:\n" + out[-1200:],
               f"{' '.join(HF)} browser ensure, or point HYPERFRAMES_BROWSER_PATH at any Chrome or Chromium")


def find_python():
    """this Python if it is 3.10+, else the newest python3.1x on PATH (or Homebrew's), else None"""
    if sys.version_info >= (3, 10):
        return sys.executable
    names = ["python3.13", "python3.12", "python3.11", "python3.10"] + (["py"] if WIN else [])
    extra = ["/opt/homebrew/bin/python3", "/usr/local/bin/python3"]
    for c in [shutil.which(n) for n in names] + [p for p in extra if os.path.exists(p)]:
        if not c:
            continue
        m = re.search(r"Python 3\.(\d+)", version_of([c, "--version"]))
        if m and int(m.group(1)) >= 10:
            return c
    return None


def main():
    print(f"reel-machine setup on {OS} ({platform.machine()}), kit at {KIT}", flush=True)
    if SANDBOX:
        net = " with the network off" if os.environ.get("CODEX_SANDBOX_NETWORK_DISABLED") else ""
        print(f"note: running inside Codex's sandbox ({SANDBOX}){net}. Rendering launches a headless browser, which "
              f"this sandbox blocks: {FULL_ACCESS}", flush=True)
    if home_in_kit():
        status("home", False, f"{HOME} is where your style and videos go, and the kit itself is there", home_fix())
        print("NOT READY: apply the fix above, then run setup again", flush=True)
        sys.exit(1)
    if OS == "macos" and not shutil.which("brew"):
        print("note: the macOS fixes below use Homebrew (https://brew.sh)", flush=True)

    # Python 3.10+ for the kit's environment (a stock Mac's python3 is 3.9: look for a newer one first)
    base = find_python()
    status("python", bool(base), (version_of([base, "--version"]) + f" ({base})") if base else platform.python_version(),
           FIX["python"][OS])

    # ffmpeg / ffprobe, with the VP9 encoder the cutout needs
    have = shutil.which("ffmpeg") and shutil.which("ffprobe")
    detail = version_of(["ffmpeg", "-version"]).split("\n")[0][:60] if have else ""
    status("ffmpeg", bool(have), detail, FIX["ffmpeg"][OS])
    if have and "libvpx-vp9" not in version_of(["ffmpeg", "-hide_banner", "-encoders"]):
        print("note: this ffmpeg has no VP9 encoder (libvpx); cutouts behind the speaker need it", flush=True)

    # Node 22+ (HyperFrames refuses older)
    v = version_of(["node", "--version"]) if shutil.which("node") else ""
    m = re.match(r"v(\d+)", v)
    status("node", bool(m and int(m.group(1)) >= 22), v + ("" if m and int(m.group(1)) >= 22 else " (needs 22+)"), FIX["node"][OS])

    # the kit's own Python environment
    reqs = os.path.join(KIT, "setup", "requirements.txt")
    venv_failed = not os.path.exists(VENV_PY) and not CHECK and base and not make_venv(base)
    if os.path.exists(VENV_PY) and not CHECK:
        print("installing Python packages (numpy, scipy, pillow, faster-whisper, yt-dlp) ...", flush=True)
        r = subprocess.run([VENV_PY, "-m", "pip", "install", "-q", "--upgrade", "pip"], capture_output=True)
        r = subprocess.run([VENV_PY, "-m", "pip", "install", "-q", "-r", reqs], capture_output=True, text=True)
        if r.returncode:
            print(r.stderr[-1500:], flush=True)
    probe = run([VENV_PY, "-c", "import numpy, scipy, PIL, faster_whisper"]) if os.path.exists(VENV_PY) else None
    status("venv", bool(probe and probe.returncode == 0), VENV_PY,
           FIX["venv"][OS] if venv_failed else f"python3 {os.path.join(KIT, 'setup', 'setup.py')}")

    # GSAP (standard license, downloaded here rather than committed)
    if not os.path.exists(GSAP_PATH) and not CHECK:
        fetch_gsap()
    good = os.path.exists(GSAP_PATH) and sha256(GSAP_PATH) == GSAP_SHA256
    status("gsap", good, GSAP_VERSION, f"move {GSAP_PATH} aside if it is there, then run setup again (it fetches "
                                       f"{GSAP_URL} and checks it)" if os.path.exists(GSAP_PATH) else
           "check your internet connection, then run setup again")

    # HyperFrames (renders the video in headless Chrome) and its Chrome
    if shutil.which("npx" if not WIN else "npx.cmd"):
        hv = version_of(HF_RUN + ["--version"])
        status("hyperfrm", "0.8.139" in hv, "hyperframes 0.8.139",
               FULL_ACCESS if SANDBOX else "check your internet connection, then run setup again")
        if not CHECK:
            print("making sure the render browser is installed ...", flush=True)
            r = run(HF + ["browser", "ensure"])
            if r.returncode:
                print((r.stdout + r.stderr)[-800:], flush=True)
        chrome = run(HF_RUN + ["browser", "path"])
        found = chrome.returncode == 0 and bool(chrome.stdout.strip())
        if OS != "linux" or found:                  # on Linux the render step installs a browser that works
            status("chrome", found, "found" if found else "", FULL_ACCESS if SANDBOX else f"{' '.join(HF)} browser ensure")
        if os.path.exists(GSAP_PATH) and (found or OS == "linux"):
            render_test()
    else:
        status("hyperfrm", False, "needs Node first", FIX["node"][OS])

    # the transcription model (downloaded once, about 1.5 GB, into the Hugging Face cache)
    if os.path.exists(VENV_PY):
        have = run([VENV_PY, "-c", "from faster_whisper.utils import download_model; download_model('medium', local_files_only=True)"])
        if have.returncode and not CHECK:
            print("downloading the transcription model (Whisper medium, about 1.5 GB, once) ...", flush=True)
            subprocess.run([VENV_PY, "-c", "from faster_whisper.utils import download_model; download_model('medium')"])
            have = run([VENV_PY, "-c", "from faster_whisper.utils import download_model; download_model('medium', local_files_only=True)"])
        status("whisper", have.returncode == 0, "medium", "check your internet connection, then run setup again")

    # optional: smoother cutouts
    if "--matte" in sys.argv and os.path.exists(VENV_PY):
        if not CHECK:
            cmd = [VENV_PY, "-m", "pip", "install", "-q", "torch"]
            if OS == "linux" and not shutil.which("nvidia-smi"):
                cmd += ["--index-url", "https://download.pytorch.org/whl/cpu"]
            print("installing PyTorch (about 1 GB) ...", flush=True)
            subprocess.run(cmd)
        t = run([VENV_PY, "-c", "import torch; print(torch.__version__)"])
        status("matte", t.returncode == 0, t.stdout.strip(), "python3 setup/setup.py --matte")

    # the creator's style (installed on the first run, not by setup)
    pack = os.path.join(HOME, "style", "style.json")
    print(f"STATUS style      {'OK     ' if os.path.exists(pack) else 'NONE YET'} "
          f"{pack if os.path.exists(pack) else 'the first run asks: Harbor or your own colors (SKILL.md step 0)'}",
          flush=True)
    print("READY" if ok else "NOT READY: apply the fixes above, then run setup again", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

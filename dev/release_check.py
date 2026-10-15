#!/usr/bin/env python3
"""Dev only: the release scan. Walks every file git tracks and fails on anything a public repo must not carry.

  names      every term in the deny list (people, creators, clients, private project names and paths), whole words,
             any case; the LICENSE copyright lines are the one place a name may be
  paths      /Users/<anyone>, C:\\Users\\<anyone>, /home/<anyone>
  secrets    API keys and tokens (sk-, gh*_, AKIA, xox*-, AIza), private key blocks, a quoted api_key or token value,
             a .env file
  licenses   a font file with no OFL.txt (or LICENSE.txt) beside it; the private pack's two trial-license faces; a
             private sound (a fav-* file, or the private sound pack by name)
  size       any file over 10 MB; a symlink (it would carry whatever it points at)
  dashes     an em dash in any text file
Binary files are searched too, for paths and the deny list's names (as bytes: metadata, EXIF and tags carry them).

The deny list is one term per line (# starts a comment) and lives outside the repo, so the names it holds are never
published: HOME/release/denylist.txt by default (HOME as pipeline/common.py finds it), or --deny <file>.
Run: python3 dev/release_check.py [--deny <file>] [<repo>]      prints every hit with its file and line, exits 1 on any
"""
import os
import re
import subprocess
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KIT, "pipeline"))

MAX_BYTES = 10 * 1024 * 1024
FONT_EXTS = (".ttf", ".otf", ".woff", ".woff2")
FONT_LICENSES = ("OFL.txt", "LICENSE.txt")
SECRETS = [
    ("an OpenAI-style key", re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}")),
    ("a GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("an AWS key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("a Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("a Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("a private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("a quoted secret value", re.compile(r"""(?i)\b(?:api_?key|secret|token|password)\s*[:=]\s*["'][^"'\s]{8,}["']""")),
]
PATHS = re.compile(r"/Users/[A-Za-z0-9._-]+|[A-Za-z]:\\+Users\\+[A-Za-z0-9._-]+|/home/[a-z][a-z0-9._-]*")
PATH_OK = {"/home/user", "/home/runner"}                      # generic names in examples and CI, not a person
# the private pack's trial-license faces and its sound pack, spelled in pieces so this file passes its own scan
PRIVATE = re.compile(r"\b(" + "|".join(("Exten" + "da", "Young" + "est", "Sound " + "Kit")) + r")\b", re.I)
EM_DASH = "\u2014"
BINARY_NEEDLES = (b"/users/",)


def read_deny(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        terms = [ln.split("#", 1)[0].strip() for ln in fh]
    return [t for t in terms if t]


def deny_regex(terms):
    """whole words, any case; a term that starts or ends with a non-word character matches at that edge as written"""
    if not terms:
        return None
    parts = []
    for t in sorted(set(terms), key=len, reverse=True):
        a = r"\b" if re.match(r"\w", t) else ""
        b = r"\b" if re.search(r"\w$", t) else ""
        parts.append(a + re.escape(t) + b)
    return re.compile("|".join(parts), re.I)


def tracked(repo):
    r = subprocess.run(["git", "-C", repo, "ls-files", "-z"], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"{repo} is not a git checkout: {r.stderr.strip()}")
    return sorted(f for f in r.stdout.split("\0") if f and (os.path.isfile(os.path.join(repo, f))
                                                             or os.path.islink(os.path.join(repo, f))))


def is_binary(data):
    return b"\0" in data[:8192]


def license_line(rel, line):
    """the LICENSE copyright lines: the one place a person's name belongs"""
    return os.path.basename(rel).upper().startswith("LICENSE") and line.lstrip().lower().startswith("copyright")


def scan(repo, terms):
    names = deny_regex(terms)
    needles = BINARY_NEEDLES + tuple(t.lower().encode() for t in terms if len(t) >= 5)
    hits = []
    files = tracked(repo)
    have = set(files)
    for rel in files:
        p = os.path.join(repo, rel)
        base = os.path.basename(rel)
        if os.path.islink(p):
            hits.append((rel, 0, "a symlink (the release zip leaves it out: ship the file itself)"))
            continue
        size = os.path.getsize(p)
        if size > MAX_BYTES:
            hits.append((rel, 0, f"over 10 MB ({size / 1e6:.1f} MB)"))
        if base.lower().startswith("fav-"):
            hits.append((rel, 0, "a private sound (fav-*)"))
        if base == ".env" or (base.startswith(".env.") and not base.endswith((".example", ".sample"))):
            hits.append((rel, 0, "an env file"))
        if base.lower().endswith(FONT_EXTS):
            d = os.path.dirname(rel)
            if not any(os.path.join(d, f) in have for f in FONT_LICENSES):
                hits.append((rel, 0, "a font with no OFL.txt beside it"))
        with open(p, "rb") as fh:
            data = fh.read()
        if is_binary(data):
            low = data.lower()
            for n in needles:
                if n in low:
                    hits.append((rel, 0, f"binary holds {n.decode(errors='replace')!r}"))
            continue
        text = data.decode("utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if EM_DASH in line:
                hits.append((rel, i, "an em dash"))
            for m in PATHS.finditer(line):
                if m.group(0) not in PATH_OK:
                    hits.append((rel, i, f"a home path: {m.group(0)}"))
            for what, rx in SECRETS:
                if rx.search(line):
                    hits.append((rel, i, what))
            m = PRIVATE.search(line)
            if m:
                hits.append((rel, i, f"a private asset: {m.group(0)}"))
            if names and not license_line(rel, line):
                for m in names.finditer(line):
                    hits.append((rel, i, f"a name on the deny list: {m.group(0)}"))
    return hits


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    deny = None
    if "--deny" in args:
        k = args.index("--deny")
        deny = args[k + 1]
        del args[k:k + 2]
    repo = os.path.abspath(args[0]) if args else KIT
    if deny is None:
        from common import HOME
        deny = os.path.join(HOME, "release", "denylist.txt")
    terms = read_deny(deny)
    if not terms:
        print(f"note: no deny list at {deny}: names are not checked (paths, secrets, licenses, sizes and dashes are)")
    hits = scan(repo, terms)
    for rel, line, what in hits:
        print(f"{rel}:{line}: {what}" if line else f"{rel}: {what}")
    n = len(tracked(repo))
    print(f"release check: {n} files, {len(terms)} deny-list terms, {len(hits)} hits")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())

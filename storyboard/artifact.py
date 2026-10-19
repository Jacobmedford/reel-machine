#!/usr/bin/env python3
"""Artifact: a review page (the start page, an approval stop, the storyboard, a style board) packed for a Claude artifact.

The Artifact tool publishes one HTML file and nothing beside it, so a page's relative refs (fonts/, frames/,
poster.jpg, first-cut.mp4) 404 in the viewer: no fonts, no frames, an empty player. This writes a copy that carries
its media:
  - fonts and images become data: URIs (each under 1.4 MB, so no URI nears Chrome's 2 MiB URL cap), local scripts
    and stylesheets go inline, and @font-face rules for families the page never names are dropped;
  - videos, and anything too big to inline, never become data: URIs: they go to the artifact's asset store
    (the Artifact tool's upload_asset, 20 MiB a file; a bigger or non-mp4 video gets a phone copy first) and their
    src becomes the "/_blob/<id>" url the upload returns.

pack:  python3 storyboard/artifact.py <folder or project> [--out DIR] [--all-fonts]
       DIR/index.html is the page to publish, DIR/readable.html the same page with each inlined payload shown as the
       file it came from (read that one before publishing), DIR/artifact.json the record. Prints each file to upload
       and where its url goes.
fill:  python3 storyboard/artifact.py <folder or project> [--out DIR] --fill <file>=<url> [<file>=<url> ...]
       packs again with the uploaded urls written in, and fails unless no relative media is left. A run that finds
       an error writes nothing, so the last good copy stays.
The publish (SKILL.md, step 6): pack, read readable.html, publish DIR/index.html with capabilities
{"comments": {"composer_only": true}, "assets": {}}, upload_asset each listed file to that artifact, fill with the
urls it returns, republish DIR/index.html from the same path.
<folder> holds a page writer's index.html and files.json (approvals/<stop>, storyboard, board); a project folder
means its storyboard. DIR defaults to <folder>/artifact. Standard library only (ffmpeg only for a phone copy).
Exit 0: publishable (pack: once the files it lists are uploaded and filled). Exit 1: not.
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from urllib.parse import unquote

PAGE_CAP = 16_000_000            # the viewer's limit for the rendered page, data: URIs included (decimal: the safe side)
PAGE_WARN = 12_000_000
INLINE_MAX = 1_400_000           # bytes; as base64 that is 1.87 MB, under Chrome's 2 MiB URL cap
ASSET_CAP = 20 * 1024 * 1024     # upload_asset's limit for a video, image, PDF or font
SVG_CAP = 2 * 1024 * 1024        # for an SVG (which it also sanitizes)
CODE_CAP = 16 * 1024 * 1024      # for a script or stylesheet
TITLE_SCAN = 7000                # the tool reads the title from the first 8 KB, its own skeleton included
INLINE = {".ttf": "font/ttf", ".otf": "font/otf", ".woff": "font/woff", ".woff2": "font/woff2",
          ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif",
          ".webp": "image/webp", ".avif": "image/avif", ".svg": "image/svg+xml", ".vtt": "text/vtt"}
STORE = {".mp4", ".webm", ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
         ".ttf", ".otf", ".woff", ".woff2", ".js", ".css"}          # what the asset store takes as it is
VIDEO = {".mp4", ".webm", ".mov", ".m4v", ".mkv"}
AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".aif", ".aiff"}
KNOWN = set(INLINE) | STORE | VIDEO | AUDIO
NOT_LOCAL = ("data:", "blob:", "/_blob/", "http:", "https:", "//", "#", "mailto:", "tel:", "sms:", "javascript:",
             "about:")
CAPS = '{"comments": {"composer_only": true}, "assets": {}}'

ATTR = re.compile(r"""(?P<pre>\s(?P<name>src|poster|href|srcset|data-src|data-poster)\s*=\s*)(?P<q>["'])"""
                  r"""(?P<val>.*?)(?P=q)""", re.I | re.S)
CSS_URL = re.compile(r"""url\(\s*(?P<q>['"]?)(?P<val>[^'")]*?)(?P=q)\s*\)""", re.I)
FACE = re.compile(r"@font-face\s*\{[^}]*\}[ \t]*\n?", re.I)
FAMILY = re.compile(r"""font-family\s*:\s*(['"]?)([^;'"}]+?)\1\s*[;}]""", re.I)
SCRIPT = re.compile(r"""<script\b(?P<a>[^>]*?)\ssrc\s*=\s*(?P<q>["'])(?P<val>[^"']+)(?P=q)(?P<b>[^>]*)>\s*</script\s*>""",
                    re.I)
LINK_CSS = re.compile(r"""<link\b[^>]*\brel\s*=\s*["']?stylesheet\b[^>]*>""", re.I)
SKELETON = re.compile(r"<!doctype[^>]*>[ \t]*\n?|</?html\b[^>]*>[ \t]*\n?|</?head\b[^>]*>[ \t]*\n?|</?body\b[^>]*>[ \t]*\n?",
                      re.I)
PAYLOAD = re.compile(r"data:[\w.+-]+/[\w.+-]+;base64,[A-Za-z0-9+/=]+")
STYLE = re.compile(r"(<style\b[^>]*>)(.*?)(</style\s*>)", re.I | re.S)
COMMENT = re.compile(r"/\*.*?\*/", re.S)


def mb(n):
    return f"{n / 1e6:.2f} MB" if n >= 100_000 else f"{n / 1000:.0f} KB"


def mib(n):
    return f"{n / 1048576:.2f} MiB" if n >= 104_858 else f"{n / 1024:.0f} KiB"


def srcset(val):
    """a srcset's candidates as (url, descriptor), split the way browsers split them (a data: url keeps its commas)"""
    out, i, n = [], 0, len(val)
    while i < n:
        while i < n and (val[i].isspace() or val[i] == ","):
            i += 1
        j = i
        while j < n and not val[j].isspace():
            j += 1
        url, desc = val[i:j], ""
        if not url:
            break
        if url.endswith(","):
            url = url.rstrip(",")
        else:
            k = val.find(",", j)
            k = n if k < 0 else k
            desc, j = val[j:k].strip(), k
        out.append((url, desc))
        i = j
    return out


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def local(value):
    """the file a ref names, or None for anything that is not a local file (data:, /_blob/, http, an anchor)"""
    v = value.strip()
    if not v or v.lower().startswith(NOT_LOCAL):
        return None
    return unquote(v.split("#", 1)[0].split("?", 1)[0])


def where_at(doc, pos, attr):
    """'<video id="v"> src': the tag a ref sits in"""
    lt = doc.rfind("<", 0, pos)
    m = re.match(r"<([a-zA-Z][\w-]*)", doc[lt:pos]) if lt >= 0 and doc.find(">", lt, pos) < 0 else None
    if not m:
        return attr
    i = re.search(r"""\bid\s*=\s*["']([^"']+)""", doc[lt:pos])
    return f"<{m.group(1).lower()}{' id=' + chr(34) + i.group(1) + chr(34) if i else ''}> {attr}"


def listed(folder):
    p = os.path.join(folder, "files.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    return sorted(data) if isinstance(data, dict) else [x for x in data if isinstance(x, str)]


class Pack:
    def __init__(self, folder, out, fills, all_fonts):
        self.folder, self.out, self.fills, self.all_fonts = folder, out, fills, all_fonts
        self.uris, self.marks, self.inlined = {}, {}, {}     # file -> data: uri, uri -> readable stand-in, rel -> bytes
        self.uploads = {}                                    # rel -> what to upload and where its url goes
        self.missing, self.external, self.notes, self.dropped, self.dropped_files, self.scripts = [], [], [], [], [], []

    def rel(self, full):
        return os.path.relpath(full, self.folder)

    def data_uri(self, full, rel, mime):
        if full not in self.uris:
            with open(full, "rb") as fh:
                raw = fh.read()
            uri = f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")
            self.uris[full] = uri
            self.marks[uri] = f"data:{mime};base64,[{rel}, {len(raw):,} bytes, sha256 {hashlib.sha256(raw).hexdigest()[:12]}]"
            self.inlined[rel] = len(raw)
        return self.uris[full]

    def ref(self, value, where, link=False):
        """a ref's new value: a data: uri, the uploaded url once filled, or the value as it was"""
        path = local(value)
        if path is None:
            if value.strip().lower().startswith(("http:", "https:", "//")):
                self.external.append((value.strip(), where))
            return value
        ext = os.path.splitext(path)[1].lower()
        if ext not in KNOWN:
            return value                                     # not a file we carry (an api route, a page link)
        full = os.path.normpath(os.path.join(self.folder, path))
        rel = self.rel(full)
        if not os.path.isfile(full):
            self.missing.append((rel, where))
            return value
        size = os.path.getsize(full)
        if ext in INLINE and size <= INLINE_MAX and not link:  # a link opens the file: data: urls never navigate
            return self.data_uri(full, rel, INLINE[ext])
        up = self.uploads.setdefault(rel, {"file": rel, "source": full, "bytes": size, "where": []})
        if where not in up["where"]:
            up["where"].append(where)
        return self.fills.get(rel, value)

    def attr(self, m):
        name, val = m.group("name").lower(), m.group("val")
        where = where_at(m.string, m.start(), name)
        if name == "srcset":
            return ", ".join(f"{self.ref(u, where)} {d}".rstrip() for u, d in srcset(val))
        return self.ref(val, where, link=name == "href" and where.startswith("<a"))

    def css_url(self, m):
        new = self.ref(m.group("val"), "CSS url()")
        return m.group(0) if new == m.group("val") else f"url('{new}')"

    def script(self, m):
        """a local <script src> goes inline (the asset store would need an upload per file)"""
        path = local(m.group("val"))
        if path is None:
            if m.group("val").strip().lower().startswith(("http:", "https:", "//")):
                self.external.append((m.group("val").strip(), "<script> src"))
            return m.group(0)
        full = os.path.normpath(os.path.join(self.folder, path))
        rel = self.rel(full)
        if not os.path.isfile(full):
            self.missing.append((rel, "<script> src"))
            return m.group(0)
        with open(full, encoding="utf-8") as fh:
            js = re.sub(r"</(script)", r"<\\/\1", fh.read(), flags=re.I)
        attrs = (m.group("a") + m.group("b")).rstrip().rstrip("/")
        if re.search(r"\s(defer|async)\b", attrs, re.I):
            self.notes.append(f"{rel} was a deferred script: inline, it runs where it stands")
            attrs = re.sub(r"""\s(?:defer|async)\b(?:\s*=\s*(?:"[^"]*"|'[^']*'|\S+))?""", "", attrs, flags=re.I)
        size = os.path.getsize(full)
        token = f"\x00script{len(self.scripts)}\x00"
        self.scripts.append((token, f"<script{attrs}>/* {rel} */\n{js}\n</script>",
                             f"<script{attrs}>/* inlined: {rel}, {size / 1000:.0f} KB, sha256 {sha(full)[:12]} */</script>"))
        self.inlined[rel] = size
        return token

    def stylesheet(self, m):
        """a local <link rel=stylesheet> goes inline as <style>, its own url()s re-based onto the page folder"""
        tag = m.group(0)
        h = re.search(r"""\bhref\s*=\s*(["'])(.*?)\1""", tag, re.I | re.S)
        path = local(h.group(2)) if h else None
        if path is None:
            if h and h.group(2).strip().lower().startswith(("http:", "https:", "//")):
                self.external.append((h.group(2).strip(), "<link> stylesheet"))
            return tag
        full = os.path.normpath(os.path.join(self.folder, path))
        rel = self.rel(full)
        if not os.path.isfile(full):
            self.missing.append((rel, "<link> stylesheet"))
            return tag
        base = os.path.dirname(full)
        with open(full, encoding="utf-8") as fh:
            css = fh.read()

        def rebase(u):
            p = local(u.group("val"))
            return u.group(0) if p is None else f"url('{self.rel(os.path.normpath(os.path.join(base, p)))}')"
        media = re.search(r"""\bmedia\s*=\s*(["'])(.*?)\1""", tag, re.I)
        self.inlined[rel] = os.path.getsize(full)
        self.notes.append(f"inlined the stylesheet {rel}")        # (no comment naming it: the leftover check reads names)
        return f"<style{' media=' + chr(34) + media.group(2) + chr(34) if media else ''}>\n{CSS_URL.sub(rebase, css)}\n</style>"

    def uncomment(self, doc):
        """CSS comments go: they never render, and a url() inside one would carry its file for nothing (a template that
        names its __THEME__ placeholder in a comment gets the whole theme pasted there, every font a second time)"""
        dead = []

        def drop(c):
            dead.extend(CSS_URL.findall(c.group(0)))
            return ""
        doc = STYLE.sub(lambda m: m.group(1) + COMMENT.sub(drop, m.group(2)) + m.group(3), doc)
        if dead:
            self.notes.append(f"dropped CSS comments holding {len(dead)} url() refs (a browser never loads those)")
        return doc

    def prune(self, doc):
        """drop @font-face rules whose family nothing else on the page names (they would ride along as dead weight)"""
        rest = FACE.sub(" ", doc) + "".join(js for _, js, _ in self.scripts)

        def keep(m):
            f = FAMILY.search(m.group(0))
            name = f.group(2).strip() if f else None
            if name and not re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", rest, re.I):
                self.dropped.append(name)
                self.dropped_files += [self.rel(os.path.normpath(os.path.join(self.folder, p)))
                                       for p in (local(u.group("val")) for u in CSS_URL.finditer(m.group(0))) if p]
                return ""
            return m.group(0)
        return FACE.sub(keep, doc)

    def leftovers(self, doc, files):
        """local media refs still on the page, beyond the uploads still waiting for their url"""
        waiting = {r for r in self.uploads if r not in self.fills}
        left = []

        def check(value, where):
            p = local(value)
            if p is not None and os.path.splitext(p)[1].lower() in KNOWN:
                r = self.rel(os.path.normpath(os.path.join(self.folder, p)))
                if r not in waiting:
                    left.append((r, where))
        for m in CSS_URL.finditer(doc):
            check(m.group("val"), "CSS url()")
        for m in ATTR.finditer(doc):
            name = m.group("name").lower()
            for url in ([u for u, _ in srcset(m.group("val"))] if name == "srcset" else [m.group("val")]):
                check(url, where_at(doc, m.start(), name))
        named = {r for r, _ in left}
        for f in files:                                      # a listed file named anywhere else (a script string)
            if f not in waiting and f not in named and f not in ("index.html", "files.json") and f in doc:
                left.append((f, "named in the page text or a script"))
        return left


def phone_copy(src, dst):
    """an mp4 the asset store takes: 720 on the short side, H.264 (the Mac's encoder when there is one) + AAC"""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.splitext(src)[1].lower() in AUDIO:
        codec = ["-vn", "-c:a", "aac", "-b:a", "160k"]
    else:
        enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        v = (["-c:v", "h264_videotoolbox", "-b:v", "2500k"] if "h264_videotoolbox" in enc else
             ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-maxrate", "3M", "-bufsize", "6M"])
        codec = ["-map", "0:v:0", "-map", "0:a:0?", "-vf",
                 "scale='if(gt(iw,ih),-2,min(720,iw))':'if(gt(iw,ih),min(720,ih),-2)'", *v, "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "160k"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, *codec, "-movflags", "+faststart", dst], check=True)


def prepare_uploads(P):
    """the file each upload sends: the page's own file, or a phone copy when the store would refuse it"""
    errors = []
    for up in P.uploads.values():
        ext = os.path.splitext(up["source"])[1].lower()
        cap = SVG_CAP if ext == ".svg" else CODE_CAP if ext in (".js", ".css") else ASSET_CAP
        path = up["source"]
        if ext in VIDEO | AUDIO and (ext not in STORE or up["bytes"] > cap):
            copy = os.path.join(P.out, "upload", os.path.splitext(up["file"])[0].replace(os.sep, "-") + ".mp4")
            if not os.path.exists(copy) or os.path.getmtime(copy) < os.path.getmtime(path):
                phone_copy(path, copy)
            why = "not a type the store takes" if ext not in STORE else f"{mib(up['bytes'])}, over the 20 MiB cap"
            P.notes.append(f"{up['file']}: uploading a phone copy ({why}): {copy}")
            path = copy
        elif ext not in STORE:
            errors.append(f"{up['file']}: the asset store does not take {ext} files")
        size = os.path.getsize(path)
        if size > cap:
            errors.append(f"{up['file']}: {mib(size)} is over the asset store's {mib(cap)} cap")
        up.update(upload=path, upload_bytes=size, sha256=sha(path))
    return errors


def run(folder, out, fills, all_fonts):
    P = Pack(folder, out, fills, all_fonts)
    with open(os.path.join(folder, "index.html"), encoding="utf-8") as fh:
        doc = fh.read()
    doc = SCRIPT.sub(P.script, doc)
    doc = LINK_CSS.sub(P.stylesheet, doc)
    doc = P.uncomment(doc)
    if not all_fonts:
        doc = P.prune(doc)
    doc = CSS_URL.sub(P.css_url, doc)
    doc = ATTR.sub(lambda m: m.group("pre") + m.group("q") + P.attr(m) + m.group("q"), doc)
    if SKELETON.search(doc):                                 # the Artifact tool adds its own doctype, head and body
        body = re.search(r"<body\b([^>]*)>", doc, re.I)
        if body and body.group(1).strip():
            P.notes.append(f"the <body{body.group(1)}> attributes are dropped with the document skeleton")
        doc = SKELETON.sub("", doc)
        P.notes.append("stripped the doctype, html, head and body tags: the Artifact tool adds its own")
    return P, doc


def resolve_fills(items, uploads):
    """FILE=URL pairs (FILE as printed, its base name or its full path) into {rel: url}; a lone URL when one file waits"""
    out, errors = {}, []
    for item in items:
        lone = item.startswith(("/_blob/", "http://", "https://")) or "=" not in item
        key, _, url = ("", "", item) if lone else item.partition("=")
        url = url.strip()
        if not url or url.lower().startswith("data:") or (local(url) is not None) or \
                (url.startswith("/") and not url.startswith("/_blob/")):
            errors.append(f"--fill {item}: not an uploaded url (upload_asset returns /_blob/<id>)")
            continue
        if not key:
            if len(uploads) != 1:
                errors.append(f"--fill {item}: {len(uploads)} files wait for a url, so name each one as <file>=<url>")
                continue
            key = next(iter(uploads))
        hits = [r for r, u in uploads.items() if key in (r, u["source"], u.get("upload"))] or \
               [r for r in uploads if os.path.basename(r) == os.path.basename(key)]
        if len(hits) != 1:
            errors.append(f"--fill {item}: {'no file' if not hits else 'more than one file'} on the page matches "
                          f"{key!r} (waiting: {', '.join(uploads) or 'none'})")
            continue
        out[hits[0]] = url
    return out, errors


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", help="the page's folder (approvals/<stop>, storyboard, board), or a project: its storyboard")
    ap.add_argument("--out", help="the scratch folder to write the publishable copy to (default <folder>/artifact)")
    ap.add_argument("--fill", nargs="+", action="extend", metavar="FILE=URL",
                    help="the url upload_asset returned for each listed file")
    ap.add_argument("--all-fonts", action="store_true", help="keep every @font-face rule, used or not")
    a = ap.parse_args()
    folder = os.path.abspath(os.path.expanduser(a.folder))
    if not os.path.isfile(os.path.join(folder, "index.html")) and os.path.isdir(os.path.join(folder, "storyboard")):
        folder = os.path.join(folder, "storyboard")
    if not os.path.isfile(os.path.join(folder, "index.html")):
        sys.exit(f"{folder}/index.html is missing: run its page writer first (preview.py, render.py --hook, "
                 "storyboard.py, board.py)")
    out = os.path.abspath(os.path.expanduser(a.out)) if a.out else os.path.join(folder, "artifact")
    if os.path.realpath(out) == os.path.realpath(folder):
        sys.exit("--out is the page's own folder: pick a scratch folder, the page writer's index.html stays as it is")
    page, record = os.path.join(out, "index.html"), os.path.join(out, "artifact.json")
    if os.path.exists(page) and not os.path.exists(record):
        sys.exit(f"{page} exists and artifact.py did not write it: pick another --out, or rename that file")
    prev = {}
    if os.path.exists(record):
        with open(record, encoding="utf-8") as fh:
            prev = json.load(fh)
    os.makedirs(out, exist_ok=True)

    errors, fills = [], {}
    if a.fill:                                               # a first pass learns which files wait for a url
        P0, _ = run(folder, out, {}, a.all_fonts)
        prepare_uploads(P0)
        fills, errors = resolve_fills(a.fill, P0.uploads)
    P, doc = run(folder, out, fills, a.all_fonts)
    errors += prepare_uploads(P)
    history = dict(prev.get("filled") or {})
    for rel, url in fills.items():                           # a url that holds an older version of this file
        old = history.get(url)
        if old and old.get("sha256") != P.uploads[rel]["sha256"]:
            errors.append(f"{rel} changed since {url} was uploaded ({old.get('at', '?')}): upload it again and fill "
                          "with the new url")
    files = listed(folder)
    left = P.leftovers(doc, files)
    waiting = [u for r, u in P.uploads.items() if r not in fills]
    if a.fill:
        errors += [f"{u['file']} has no url yet: add {u['file']}=<url> to --fill" for u in waiting]

    final = readable = doc
    readable = PAYLOAD.sub(lambda m: P.marks.get(m.group(0), m.group(0)), readable)
    for token, js, stand in P.scripts:
        final, readable = final.replace(token, js), readable.replace(token, stand)
    size = len(final.encode("utf-8"))
    for rel, where in P.missing:
        errors.append(f"{rel} is missing ({where})")
    for rel, where in left:
        errors.append(f"{rel} is still a relative ref ({where})")
    if size > PAGE_CAP:
        big = sorted(P.inlined.items(), key=lambda kv: -kv[1])[:5]
        errors.append(f"the page is {mb(size)}, over the viewer's 16 MB cap; the biggest inlined files: "
                      + ", ".join(f"{r} {mb(n)}" for r, n in big))
    title = final.lower().find("<title")
    if title < 0 or title > TITLE_SCAN:
        P.notes.append("no <title> near the top of the page: the artifact would take its name from the file")

    if not errors:                                           # a run with errors writes nothing: the last good copy stays
        with open(page, "w", encoding="utf-8") as fh:
            fh.write(final)
        with open(os.path.join(out, "readable.html"), "w", encoding="utf-8") as fh:
            fh.write(readable)
        now = datetime.datetime.now().isoformat(timespec="seconds")
        for rel, url in fills.items():
            history[url] = {"file": rel, "sha256": P.uploads[rel]["sha256"], "at": now}
        with open(record, "w", encoding="utf-8") as fh:
            json.dump({"source": folder, "page": page, "bytes": size, "packed_at": now,
                       "inlined": P.inlined, "dropped_fonts": sorted(set(P.dropped)),
                       "uploads": [dict(u, url=fills.get(r)) for r, u in P.uploads.items()],
                       "filled": history}, fh, indent=1)

    groups = {}
    for r, n in P.inlined.items():
        ext = os.path.splitext(r)[1].lower()
        kind = ("font", "fonts") if ext in (".ttf", ".otf", ".woff", ".woff2") else ("image", "images") \
            if ext in INLINE else ("script or stylesheet", "scripts and stylesheets")
        groups.setdefault(kind, []).append(n)
    print((f"NOT WRITTEN {page} (any earlier copy stays as it was): it would be {mb(size)}" if errors else
           f"packed {page}: {mb(size)} of the 16 MB cap") + ("  (WARNING: near the cap)" if size > PAGE_WARN else ""))
    print("  inlined " + (", ".join(f"{len(v)} {k[len(v) != 1]} ({mb(sum(v))})" for k, v in groups.items()) or "nothing")
          + (f"; dropped the @font-face rules for {', '.join(sorted(set(P.dropped)))} (nothing on the page names them)"
             if P.dropped else ""))
    unused = [f for f in files if f not in P.inlined and f not in P.uploads and f not in P.dropped_files
              and f not in {r for r, _ in left}]
    if unused:
        print(f"  files.json lists {len(unused)} file{'s' * (len(unused) != 1)} the page never references, left out: "
              + ", ".join(unused[:6]) + (" ..." if len(unused) > 6 else ""))
    if not errors:
        print(f"  read {os.path.join(out, 'readable.html')} before publishing: the same page, each inlined payload "
              "shown as the file it came from")
    for rel, url in fills.items():
        print(f"  filled {rel} -> {url}")
    for v, where in sorted(set(P.external)):
        print(f"  NOTE external ref {v} ({where}): the viewer blocks most other hosts")
    for n in P.notes:
        print(f"  NOTE {n}")
    if errors:
        for e in errors:
            print(f"ERROR {e}")
        print("NOT READY: fix the errors above and run it again")
        sys.exit(1)
    me = f"python3 {shlex.quote(os.path.abspath(__file__))} {shlex.quote(folder)} --out {shlex.quote(out)}"
    if waiting:
        print(f"UPLOAD {len(waiting)} file{'s' * (len(waiting) != 1)} (Artifact action upload_asset with the "
              "artifact's url, one call per file), then fill in the urls it returns:")
        for u in waiting:
            print(f"  {u['file']}  {mib(u['upload_bytes'])}  {u['upload']}")
            print(f"      its url goes in: {', '.join(u['where'])}")
        print(f"NEXT publish {page} (first time: capabilities {CAPS}), upload the file"
              f"{'s' * (len(waiting) != 1)} above to that artifact, then")
        print(f"  {me} --fill " + " ".join(f"{u['file']}=<url>" for u in waiting))
        print(f"  and republish {page} from the same path")
        return
    print(f"READY no relative media left: publish {page} (first time: capabilities {CAPS}; "
          "a republish from the same path keeps them)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Inline vendor: every <script src="vendor/<file>.js"></script> in a composition carries that file inside the page,
so the renderer has nothing to fetch before the page can animate.

Why: a render runs several browser workers, and each one loads the page and its scripts from the renderer's local
HTTP server. A network change on the Mac (Wi-Fi churn, net::ERR_NETWORK_CHANGED) can abort one of those loads. A
worker that loses vendor/gsap.min.js has no GSAP: the composition's script stops at its first gsap call, no timeline
registers, and that worker's whole share of the frames renders the static page, with no error.

How: the tag keeps its place (so the library still runs before the composition's script) and its src becomes the
file itself, base64 in a data: URL: <script data-inlined="vendor/gsap.min.js" src="data:text/javascript;
name=gsap.min.js;base64,...">. The browser decodes a data: URL in memory; no request reaches the network stack, so a
network change cannot drop it. The bytes are the library's own, exactly (nothing to escape: base64 has no < or ").
Not inline script text, on purpose: `hyperframes check` reads inline script text as composition code, and GSAP's
own Math.random() and Date.now() then fail it (non_deterministic_code), which stops every render.

  inline(html, public_dir)  the document with each vendor script carried inside it (files from public_dir/vendor/).
                            Idempotent: a page carrying its vendor files has none left to fetch.
  fetched(html)             vendor scripts the page still loads by URL (an async, defer or module tag is left alone:
                            it would run at another moment)
  inlined(html)             the vendor files the page carries, in page order

Run: PY pipeline/inline_vendor.py <html file> [<public dir>]
  rewrites the file in place and keeps what it replaced as <file>.pre-inline. The vendor files resolve from
  <public dir>, by default the file's own folder. A second run changes nothing. Exits non-zero, writing nothing,
  when a vendor file is missing or a vendor script cannot be inlined.
"""
import base64
import os
import re
import shutil
import sys

# a comment, or a whole script element: a tag written inside either is text, never a tag
SCAN = re.compile(r"<!--.*?-->|<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script\s*>", re.I | re.S)
ATTR = re.compile(r"""([^\s"'>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?""")
INLINABLE = re.compile(r"(?:\./)?vendor/[^?#\s]+\.js")


def attrs_of(text):
    """{name: (value, start, end)} of a tag's attribute text, names lowercased, the first of a repeated name"""
    out = {}
    for m in ATTR.finditer(text):
        val = next((g for g in m.groups()[1:] if g is not None), "")
        out.setdefault(m.group(1).lower(), (val, m.start(), m.end()))
    return out


def _external(m):
    """(attributes, src) of a script element that loads a file, else None"""
    if m.group("attrs") is None or m.group("body").strip():
        return None
    a = attrs_of(m.group("attrs"))
    return (a, a["src"][0]) if "src" in a else None


def _vendor_path(src):
    """vendor/<file> for a src that points into the page's vendor folder, else None"""
    path = re.split(r"[?#]", src, 1)[0]
    path = path[2:] if path.startswith("./") else path.lstrip("/")
    return path if path.startswith("vendor/") else None


def data_url(code, name):
    """a classic script's data: URL; name (a MIME parameter) keeps the file's name visible to a reader and to the
    HyperFrames lint, which looks for "gsap" in a script's src"""
    token = re.sub(r"[^A-Za-z0-9._-]", "_", name) or "script"
    return f"data:text/javascript;name={token};base64,{base64.b64encode(code).decode('ascii')}"


def inline(html, public_dir):
    """html with every plain <script src="vendor/<file>.js"></script> carrying its file as a data: URL"""
    def one(m):
        ext = _external(m)
        if not ext:
            return m.group(0)
        a, src = ext
        if not INLINABLE.fullmatch(src) or "async" in a or "defer" in a or a.get("type", ("",))[0].strip().lower() == "module":
            return m.group(0)
        rel = os.path.normpath(src[2:] if src.startswith("./") else src)
        if rel.startswith("..") or not rel.startswith("vendor" + os.sep):
            raise ValueError(f"{src} points out of the vendor folder")
        path = os.path.join(public_dir, rel)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"{src} is not in {public_dir} (new.py copies the kit's vendor folder into "
                                    "public/vendor; setup downloads it)")
        with open(path, "rb") as fh:
            code = fh.read()
        _, s, e = a["src"]
        rest = (m.group("attrs")[:s] + m.group("attrs")[e:]).strip()
        name = rel.replace(os.sep, "/")
        return (f'<script{" " + rest if rest else ""} data-inlined="{name}" '
                f'src="{data_url(code, os.path.basename(rel))}"></script>')
    return SCAN.sub(one, html)


def fetched(html):
    """vendor scripts this page still loads by URL"""
    out = []
    for m in SCAN.finditer(html):
        ext = _external(m)
        if ext and _vendor_path(ext[1]):
            out.append(_vendor_path(ext[1]))
    return out


def inlined(html):
    """vendor files this page carries, in page order"""
    return [attrs_of(m.group("attrs"))["data-inlined"][0] for m in SCAN.finditer(html)
            if m.group("attrs") is not None and "data-inlined" in attrs_of(m.group("attrs"))]


def main(argv=None):
    a = sys.argv[1:] if argv is None else argv
    if not a or len(a) > 2 or a[0].startswith("-"):
        sys.exit("usage: inline_vendor.py <html file> [<public dir>]")
    path = os.path.abspath(os.path.expanduser(a[0]))
    pub = os.path.abspath(os.path.expanduser(a[1])) if len(a) > 1 else os.path.dirname(path)
    with open(path, encoding="utf-8") as fh:
        doc = fh.read()
    try:
        out = inline(doc, pub)
    except (OSError, ValueError) as e:
        sys.exit(f"inline_vendor: {e}. {os.path.basename(path)} was not changed.")
    name = os.path.basename(path)
    left = fetched(out)
    if left:
        sys.exit(f"inline_vendor: {name} still loads {', '.join(left)} by URL (an async, defer or module tag): make it "
                 f"a plain <script src=\"...\"></script> so it can be inlined. {name} was not changed.")
    if out == doc:
        have = inlined(doc)
        print(f"{name}: nothing to inline" + (f" ({', '.join(have)} already inside)" if have else ""))
        return
    shutil.copy2(path, path + ".pre-inline")              # the page as it was, before this inline
    tmp = path + ".inline-tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(out)
    os.replace(tmp, path)                                  # a new file: a hard-linked twin keeps the original
    new = [n for n in inlined(out) if n not in inlined(doc)]
    print(f"{name}: inlined {', '.join(new)}; the page as it was is {name}.pre-inline")


if __name__ == "__main__":
    main()

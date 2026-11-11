#!/usr/bin/env python3
"""A small graph of your own ERPForAll addons, for agents and people. Python 3.10+, standard library only (a subset TOML reader replaces tomllib on 3.10).

It reads the addons under one or more addons paths (no build, no network, no model) and answers, with a
`path:line` for every fact, what models, fields, RPC methods, views, menus, actions and access rows your project
defines, how addons depend on and extend each other, and what a change to a file can affect. Use it before you
write a field name, a `ref=`, a model name in a view or an access row: if it prints "not found", it is not in
your addons (it may come from the framework or from an addon outside --addons-path).

  addon-graph.py [--addons-path DIR]... [--json] summary
  addon-graph.py [--addons-path DIR]... [--json] model <name>
  addon-graph.py [--addons-path DIR]... [--json] field <model> <field>
  addon-graph.py [--addons-path DIR]... [--json] impact <path>...
  addon-graph.py [--addons-path DIR]... [--json] context "<what you are about to do>"

`--addons-path` defaults to ./addons. Exit status: 0 found, 1 not found (model, field), 2 usage error.

What it reads: manifest.toml (depends), models/*.toml (data-only models and fields), native Rust sources in src/
(`#[model]`, `#[extend]`, `#[field]`, `#[methods]` with `#[rpc]`), XML data files (views, view inheritance, menus,
actions, other records), access CSV files. What it cannot read is listed by `summary` under "not understood" with
the reason; an absence is only meaningful when that list does not cover the file you care about. It does not know
the framework's own models: a reference to `res.partner` is accepted as external when no addon of yours defines it.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import io
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# ----------------------------------------------------------------------------------------------- toml
# tomllib exists from Python 3.11; build hosts may run 3.10. `toml_loads` uses tomllib when importable and
# otherwise `_mini_toml`, a reader for the subset the repository's Cargo.toml, manifest.toml and models/*.toml
# use: tables, arrays of tables, dotted keys, strings (basic, literal, multi-line), integers, floats, booleans,
# arrays and inline tables. Anything else (dates, hex, bare syntax it does not know) raises TomlError.

try:
    import tomllib as _tomllib
except ImportError:  # Python 3.10
    _tomllib = None


class TomlError(ValueError):
    pass


_ESC = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r", '"': '"', "\\": "\\"}
_KEY = re.compile(r'\s*(?:([A-Za-z0-9_-]+)|"((?:\\.|[^"\\])*)"|\'([^\']*)\')\s*')
_NUM = re.compile(r"[+-]?(?:0|[1-9](?:_?\d)*)(?:\.\d(?:_?\d)*)?(?:[eE][+-]?\d(?:_?\d)*)?(?![\w.:-])")


class _Reader:
    def __init__(self, text: str) -> None:
        self.s, self.i = text, 0

    def err(self, msg: str) -> TomlError:
        return TomlError(f"{msg} (line {self.s.count(chr(10), 0, self.i) + 1})")

    def ws(self, newlines: bool = False) -> None:
        while self.i < len(self.s):
            c = self.s[self.i]
            if c in " \t" or (newlines and c in "\r\n"):
                self.i += 1
            elif c == "#" and (newlines or True):
                while self.i < len(self.s) and self.s[self.i] != "\n":
                    self.i += 1
            else:
                break

    def key(self) -> list[str]:
        parts = []
        while True:
            m = _KEY.match(self.s, self.i)
            if not m:
                raise self.err("unsupported key")
            if m.group(1) is not None:
                parts.append(m.group(1))
            elif m.group(2) is not None:
                parts.append(self.unescape(m.group(2)))
            else:
                parts.append(m.group(3))
            self.i = m.end()
            if self.s.startswith(".", self.i):
                self.i += 1
                continue
            return parts

    def unescape(self, raw: str) -> str:
        out, i = [], 0
        while i < len(raw):
            c = raw[i]
            if c != "\\":
                out.append(c); i += 1
                continue
            n = raw[i + 1:i + 2]
            if n in _ESC:
                out.append(_ESC[n]); i += 2
            elif n in ("u", "U"):
                w = 4 if n == "u" else 8
                out.append(chr(int(raw[i + 2:i + 2 + w], 16))); i += 2 + w
            else:
                raise self.err(f"unsupported escape \\{n}")
        return "".join(out)

    def value(self):
        s, i = self.s, self.i
        if s.startswith('"""', i):
            j = s.find('"""', i + 3)
            while j >= 0 and s[j - 1] == "\\":
                j = s.find('"""', j + 1)
            if j < 0:
                raise self.err("unterminated string")
            body = s[i + 3:j]
            self.i = j + 3
            if body.startswith("\r\n"):
                body = body[2:]
            elif body.startswith("\n"):
                body = body[1:]
            if re.search(r"\\\s*\n", body):
                body = re.sub(r"\\[ \t]*\r?\n\s*", "", body)
            return self.unescape(body)
        if s.startswith("'''", i):
            j = s.find("'''", i + 3)
            if j < 0:
                raise self.err("unterminated string")
            body = s[i + 3:j]
            self.i = j + 3
            return body[1:] if body.startswith("\n") else body
        if s.startswith('"', i):
            m = re.compile(r'"((?:\\.|[^"\\\n])*)"').match(s, i)
            if not m:
                raise self.err("unterminated string")
            self.i = m.end()
            return self.unescape(m.group(1))
        if s.startswith("'", i):
            m = re.compile(r"'([^'\n]*)'").match(s, i)
            if not m:
                raise self.err("unterminated string")
            self.i = m.end()
            return m.group(1)
        if s.startswith("[", i):
            self.i += 1
            out: list = []
            while True:
                self.ws(True)
                if s.startswith("]", self.i):
                    self.i += 1
                    return out
                out.append(self.value())
                self.ws(True)
                if s.startswith(",", self.i):
                    self.i += 1
                elif not s.startswith("]", self.i):
                    raise self.err("expected , or ] in array")
        if s.startswith("{", i):
            self.i += 1
            tbl: dict = {}
            while True:
                self.ws()
                if s.startswith("}", self.i):
                    self.i += 1
                    return tbl
                k = self.key()
                self.ws()
                if not s.startswith("=", self.i):
                    raise self.err("expected = in inline table")
                self.i += 1
                self.ws()
                _set(tbl, k, self.value(), self)
                self.ws()
                if s.startswith(",", self.i):
                    self.i += 1
                elif not s.startswith("}", self.i):
                    raise self.err("expected , or } in inline table")
        for word, val in (("true", True), ("false", False)):
            if s.startswith(word, i) and not re.match(r"[\w-]", s[i + len(word):i + len(word) + 1] or " "):
                self.i += len(word)
                return val
        m = _NUM.match(s, i)
        if m and not re.match(r"\d{4}-\d\d", s[i:i + 7]):
            self.i = m.end()
            t = m.group().replace("_", "")
            return float(t) if re.search(r"[.eE]", t) else int(t)
        raise self.err(f"unsupported value `{s[i:i + 20].splitlines()[0] if s[i:i + 20] else ''}`")


def _set(tbl: dict, key: list[str], value, rd: _Reader) -> None:
    for k in key[:-1]:
        tbl = tbl.setdefault(k, {})
        if not isinstance(tbl, dict):
            raise rd.err("key path crosses a non-table")
    if key[-1] in tbl:
        raise rd.err(f"duplicate key {key[-1]}")
    tbl[key[-1]] = value


def _mini_toml(text: str) -> dict:
    rd = _Reader(text)
    root: dict = {}
    cur = root
    while True:
        rd.ws(True)
        if rd.i >= len(text):
            return root
        if text.startswith("[[", rd.i):
            rd.i += 2
            k = rd.key()
            if not text.startswith("]]", rd.i):
                raise rd.err("expected ]]")
            rd.i += 2
            tbl = root
            for p in k[:-1]:
                tbl = tbl.setdefault(p, {})
                if isinstance(tbl, list):
                    tbl = tbl[-1]
            arr = tbl.setdefault(k[-1], [])
            if not isinstance(arr, list):
                raise rd.err("array of tables clashes with a table")
            cur = {}
            arr.append(cur)
        elif text.startswith("[", rd.i):
            rd.i += 1
            k = rd.key()
            if not text.startswith("]", rd.i):
                raise rd.err("expected ]")
            rd.i += 1
            tbl = root
            for p in k:
                tbl = tbl.setdefault(p, {})
                if isinstance(tbl, list):
                    tbl = tbl[-1]
                if not isinstance(tbl, dict):
                    raise rd.err("table clashes with a value")
            cur = tbl
        else:
            k = rd.key()
            rd.ws()
            if not text.startswith("=", rd.i):
                raise rd.err("expected =")
            rd.i += 1
            rd.ws()
            _set(cur, k, rd.value(), rd)
        rd.ws()
        if rd.i < len(text) and text[rd.i] not in "\r\n":
            raise rd.err("unexpected text after a value")


def toml_loads(text: str) -> dict:
    """tomllib when available, else the subset reader; both raise TomlError on bad or unsupported input."""
    if _tomllib is not None:
        try:
            return _tomllib.loads(text)
        except _tomllib.TOMLDecodeError as e:
            raise TomlError(str(e)) from e
    try:
        return _mini_toml(text)
    except (IndexError, KeyError, ValueError) as e:
        raise TomlError(str(e)) from e


CONTEXT_LINES = 80
IMPLICIT_FIELDS = ("id", "display_name", "create_uid", "create_date", "write_uid", "write_date")
STOP = set("a an and the to of in on for with from by is are be it this that as at or how do does can i we you add "
           "make new use using when what which should into not no per via has have get set show".split())

# ------------------------------------------------------------------------------------------------ rust lexing
# (a trimmed copy of the lexer of the framework repository's knowledge-graph builder)

_RUST_TOKENS = re.compile(
    r"""(?P<line>//[^\n]*)|(?P<block>/\*)|(?P<raw>b?r(?P<h>\#*)"(?:.|\n)*?"(?P=h))|(?P<str>b?"(?:\\.|[^"\\])*")"""
    r"""|(?P<chr>b?'(?:\\.|[^\\'\n])')""", re.S)
_BRACKETS = re.compile(r"[()\[\]{}]")


def _blank(s: str) -> str:
    return re.sub(r"[^\n]", " ", s)


def lex_rust(text: str) -> tuple[str, str]:
    """(clean, skel): comments blanked; and also string contents blanked. Same length, same newlines."""
    clean: list[str] = []
    skel: list[str] = []
    pos, n = 0, len(text)
    while pos < n:
        m = _RUST_TOKENS.search(text, pos)
        if not m:
            clean.append(text[pos:]); skel.append(text[pos:])
            break
        clean.append(text[pos:m.start()]); skel.append(text[pos:m.start()])
        if m.group("line"):
            b = _blank(m.group(0)); clean.append(b); skel.append(b); pos = m.end()
        elif m.group("block"):
            depth, i = 1, m.end()
            while i < n and depth:
                if text.startswith("/*", i):
                    depth += 1; i += 2
                elif text.startswith("*/", i):
                    depth -= 1; i += 2
                else:
                    i += 1
            b = _blank(text[m.start():i]); clean.append(b); skel.append(b); pos = i
        else:
            token = m.group(0)
            clean.append(token)
            q = token.index("'") if m.group("chr") else token.index('"')
            skel.append(token[:q + 1] + _blank(token[q + 1:-1]) + token[-1:])
            pos = m.end()
    return "".join(clean), "".join(skel)


def close_of(skel: str, i: int) -> int:
    depth = 0
    for m in _BRACKETS.finditer(skel, i):
        if m.group() in "([{":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return m.start()
    return -1


def split_top(clean: str, start: int, end: int) -> list[str]:
    parts, depth, i, begin = [], 0, start, start
    while i < end:
        c = clean[i]
        if c == '"':
            i += 1
            while i < end and clean[i] != '"':
                i += 2 if clean[i] == "\\" else 1
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(clean[begin:i]); begin = i + 1
        i += 1
    if clean[begin:end].strip():
        parts.append(clean[begin:end])
    return parts


def parse_args(clean: str, start: int, end: int) -> tuple[list[str], dict[str, str]]:
    pos, kw = [], {}
    for part in split_top(clean, start, end):
        part = part.strip()
        m = re.match(r"^([A-Za-z_]\w*)\s*=\s*(.*)$", part, re.S)
        if m:
            kw[m.group(1)] = m.group(2).strip()
        elif part:
            pos.append(part)
    return pos, kw


def lit(value: str | None) -> str | None:
    m = re.fullmatch(r'"((?:\\.|[^"\\])*)"', (value or "").strip())
    return m.group(1) if m else None


def lineno(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def skip_attrs(skel: str, p: int) -> int:
    while p < len(skel):
        while p < len(skel) and skel[p].isspace():
            p += 1
        if skel.startswith("#[", p):
            c = close_of(skel, p + 1)
            if c < 0:
                return p
            p = c + 1
        else:
            return p
    return p


# ------------------------------------------------------------------------------------------------ the graph


class Graph:
    def __init__(self) -> None:
        self.addons: dict[str, dict] = {}
        self.models: dict[str, dict] = {}   # name -> {decls: [(addon, how, path, line)], fields: {}, methods: {}}
        self.views: dict[str, dict] = {}
        self.menus: dict[str, dict] = {}
        self.actions: dict[str, dict] = {}
        self.access: list[dict] = []
        self.records: list[dict] = []
        self.unparsed: list[tuple[str, int, str]] = []
        self.owner_dirs: list[tuple[str, str]] = []  # (dir with trailing /, addon)

    def bad(self, path: str, line: int, reason: str) -> None:
        self.unparsed.append((path, line, reason))

    def model(self, name: str) -> dict:
        return self.models.setdefault(name, {"decls": [], "fields": {}, "methods": {}, "inherits": []})

    def owner(self, path: str) -> str | None:
        for d, a in self.owner_dirs:
            if path.startswith(d):
                return a
        return None

    def chain(self, model: str) -> list[str]:
        out, todo = [], [model]
        while todo:
            m = todo.pop(0)
            if m not in out:
                out.append(m)
                todo += self.models.get(m, {}).get("inherits", [])
        return out

    def fields_of(self, model: str) -> dict[str, dict]:
        found: dict[str, dict] = {}
        for m in self.chain(model):
            for k, v in self.models.get(m, {}).get("fields", {}).items():
                found.setdefault(k, v)
        return found


def build(paths: list[Path]) -> Graph:
    g = Graph()
    for base in paths:
        if not base.is_dir():
            continue
        for manifest in sorted(base.glob("*/manifest.toml")):
            d = manifest.parent
            rel = lambda p: p.as_posix()  # noqa: E731
            try:
                data = toml_loads(manifest.read_text(encoding="utf-8"))
            except (TomlError, OSError) as e:
                g.bad(rel(manifest), 1, f"manifest does not parse: {e}")
                continue
            g.addons[d.name] = {"path": rel(manifest), "dir": rel(d), "depends": list(data.get("depends") or []),
                                "summary": data.get("summary") or data.get("name") or "", "native": (d / "Cargo.toml").is_file()}
            g.owner_dirs.append((rel(d) + "/", d.name))
    g.owner_dirs.sort(key=lambda t: -len(t[0]))
    for name, a in sorted(g.addons.items()):
        d = Path(a["dir"])
        for f in sorted((d / "models").glob("*.toml")) if (d / "models").is_dir() else []:
            read_model_toml(g, name, f)
        for f in sorted((d / "src").rglob("*.rs")) if (d / "src").is_dir() else []:
            read_rust(g, name, f)
    # Rust types resolve to models once every addon was read
    for name, a in sorted(g.addons.items()):
        d = Path(a["dir"])
        for f in sorted(d.rglob("*.xml")):
            read_xml(g, name, f)
        for f in sorted(d.rglob("*.csv")):
            read_access(g, name, f)
    return g


# ------------------------------------------------------------------------------------------------ readers


def read_model_toml(g: Graph, addon: str, f: Path) -> None:
    text = f.read_text(encoding="utf-8", errors="replace")
    p = f.as_posix()
    try:
        data = toml_loads(text)
    except TomlError as e:
        g.bad(p, 1, f"model file does not parse: {e}")
        return
    mlines = [i for i, ln in enumerate(text.split("\n"), 1) if ln.strip() == "[[model]]"]
    flines = [i for i, ln in enumerate(text.split("\n"), 1) if ln.strip() == "[[model.field]]"]
    fi = 0
    for mi, m in enumerate(data.get("model", [])):
        ln = mlines[mi] if mi < len(mlines) else 1
        name = m.get("name") or m.get("extend")
        if not name:
            g.bad(p, ln, "[[model]] has neither name nor extend")
            fi += len(m.get("field", []))
            continue
        mod = g.model(name)
        mod["decls"].append((addon, "extends" if "name" not in m else "defines", p, ln))
        mod["summary"] = m.get("description") or mod.get("summary", "")
        mod["inherits"] += [x for x in (m.get("inherit") or []) if isinstance(x, str)]
        for fld in m.get("field", []):
            fl = flines[fi] if fi < len(flines) else ln
            fi += 1
            if fld.get("name"):
                mod["fields"].setdefault(fld["name"], {"kind": fld.get("type"), "comodel": fld.get("comodel"), "addon": addon,
                                                       "path": p, "line": fl, "string": fld.get("string")})


def read_rust(g: Graph, addon: str, f: Path) -> None:
    text = f.read_text(encoding="utf-8", errors="replace")
    if not any(k in text for k in ("#[model(", "#[extend(", "#[methods(")):
        return
    p = f.as_posix()
    clean, skel = lex_rust(text)
    types = g.__dict__.setdefault("_types", {})   # Rust struct name -> model name
    pending = g.__dict__.setdefault("_pending", [])
    for m in re.finditer(r"#\[(model|extend)\s*\(", skel):
        ln = lineno(clean, m.start())
        oc = close_of(skel, m.end() - 1)
        if oc < 0:
            g.bad(p, ln, "unbalanced attribute")
            continue
        pos, kw = parse_args(clean, m.end(), oc)
        sm = re.compile(r"(?:pub(?:\s*\([^)]*\))?\s+)?struct\s+(\w+)").match(skel, skip_attrs(skel, oc + 2))
        if not sm:
            g.bad(p, ln, "no struct after the attribute")
            continue
        if m.group(1) == "model":
            name = lit(kw.get("name"))
            if not name:
                g.bad(p, ln, "#[model] without a literal name")
                continue
            how = "defines"
        else:
            target = pos[0].strip() if pos else ""
            name = types.get(target)
            if not name:
                pending.append((addon, p, ln, m, clean, skel, oc, sm, kw, target))
                continue
            how = "extends"
        types[sm.group(1)] = name
        finish_model(g, addon, p, ln, name, how, clean, skel, oc, sm, kw)
    for it in list(pending):
        addon2, p2, ln2, m2, clean2, skel2, oc2, sm2, kw2, target = it
        name = types.get(target)
        if name:
            types[sm2.group(1)] = name
            finish_model(g, addon2, p2, ln2, name, "extends", clean2, skel2, oc2, sm2, kw2)
            pending.remove(it)
    for m in re.finditer(r"#\[methods\s*\(", skel):
        ln = lineno(clean, m.start())
        oc = close_of(skel, m.end() - 1)
        pos, _ = parse_args(clean, m.end(), oc)
        im = re.compile(r"impl\b[^{;]*\{").match(skel, skip_attrs(skel, oc + 2))
        if not pos or not im:
            g.bad(p, ln, "#[methods] without a target type or an impl block")
            continue
        model = types.get(pos[0].strip())
        if not model:
            g.bad(p, ln, f"#[methods] target type `{pos[0].strip()}` is not a model of these addons")
            continue
        bo = im.end() - 1
        bc = close_of(skel, bo)
        for fm in re.finditer(r"(?:#\[(rpc|method)\b[^\]]*\]\s*)+(?:pub(?:\s*\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)", skel[bo:bc]):
            attrs = fm.group(0)
            exposed = "#[rpc" in attrs and "hide" not in attrs.split("fn")[0]
            ef = re.search(r"effect\s*=\s*(\w+)", clean[bo + fm.start():bo + fm.end()])
            g.model(model)["methods"].setdefault(fm.group(2), {"rpc": exposed, "effect": ef.group(1) if ef else None,
                                                               "addon": addon, "path": p, "line": lineno(clean, bo + fm.start())})


def finish_model(g: Graph, addon: str, p: str, ln: int, name: str, how: str, clean: str, skel: str, oc: int,
                 sm: re.Match, kw: dict[str, str]) -> None:
    mod = g.model(name)
    mod["decls"].append((addon, how, p, ln))
    if kw.get("description") and lit(kw["description"]):
        mod["summary"] = lit(kw["description"])
    if "inherit" in kw:
        types = g.__dict__.get("_types", {})
        for t in [w.strip() for w in kw["inherit"].strip("[]").split(",") if w.strip()]:
            mod["inherits"].append(types.get(t, t))
    bo = skel.find("{", sm.end())
    semi = skel.find(";", sm.end())
    if bo < 0 or 0 <= semi < bo:
        return
    bc = close_of(skel, bo)
    pos = bo
    while True:
        fm = re.compile(r"#\[field\s*\(").search(skel, pos, bc)
        if not fm:
            break
        fc = close_of(skel, fm.end() - 1)
        args, fkw = parse_args(clean, fm.end(), fc)
        ident = re.compile(r"(?:pub(?:\s*\([^)]*\))?\s+)?(?:r#)?(\w+)\s*:").match(skel, skip_attrs(skel, fc + 2))
        pos = fc + 2
        if not ident:
            g.bad(p, lineno(clean, fm.start()), "no field identifier after #[field]")
            continue
        fname = lit(fkw.get("name")) or ident.group(1)
        mod["fields"].setdefault(fname, {"kind": args[0] if args else None, "comodel": lit(fkw.get("comodel")), "addon": addon,
                                         "path": p, "line": lineno(clean, fm.start()), "string": lit(fkw.get("string"))})


def read_xml(g: Graph, addon: str, f: Path) -> None:
    text = f.read_text(encoding="utf-8", errors="replace")
    p = f.as_posix()
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as e:
        g.bad(p, getattr(e, "position", (1, 0))[0], f"xml does not parse: {e}")
        return
    lines = {}
    for m in re.finditer(r"<(?:record|menuitem)\b[^>]*?\bid=\"([^\"]+)\"", text):
        lines.setdefault(m.group(1), lineno(text, m.start()))

    def q(ref: str) -> str:
        return ref if "." in ref else f"{addon}.{ref}"

    def visit(el: ET.Element, parent: str | None) -> None:
        rid = el.get("id")
        if el.tag == "menuitem" and rid:
            full = q(rid)
            g.menus[full] = {"name": el.get("name", ""), "action": q(el.get("action")) if el.get("action") else None,
                             "parent": q(el.get("parent")) if el.get("parent") else parent, "path": p, "line": lines.get(rid, 1)}
            for c in el.findall("menuitem"):
                visit(c, full)
        elif el.tag == "record" and rid:
            full, model, ln = q(rid), el.get("model", ""), lines.get(rid, 1)
            fields = {c.get("name"): c for c in el.findall("field") if c.get("name")}

            def val(n: str) -> str | None:
                c = fields.get(n)
                return None if c is None else (c.get("ref") or (c.text or "").strip() or None)
            if model == "ir.ui.view":
                inh = fields.get("inherit_id")
                used = []
                a0 = text.find('name="arch"', text.find(f'id="{rid}"'))
                if a0 >= 0:
                    e0 = text.find("</record>", a0)
                    used = sorted({m.group(1) for m in re.finditer(r'<field\s+name="(\w+)"', text[a0:e0])})
                g.views[full] = {"model": val("model"), "inherits": q(inh.get("ref")) if inh is not None and inh.get("ref") else None,
                                 "fields": used, "path": p, "line": ln}
            elif model.startswith("ir.actions."):
                g.actions[full] = {"model": val("res_model"), "name": val("name") or "", "path": p, "line": ln}
            else:
                g.records.append({"id": full, "model": model, "path": p, "line": ln})

    for el in root:
        if el.tag in ("record", "menuitem"):
            visit(el, None)
        elif el.tag in ("data", "erp", "odoo"):
            for c in el:
                visit(c, None)


def read_access(g: Graph, addon: str, f: Path) -> None:
    if "access" not in f.name:
        return
    p = f.as_posix()
    rows = list(csv.reader(io.StringIO(f.read_text(encoding="utf-8", errors="replace"))))
    if not rows:
        return
    head = [h.replace("/id", ":id") for h in rows[0]]
    if "model_id:id" not in head:
        g.bad(p, 1, f"access file without a model_id column ({head[:4]})")
        return
    idx = {h: i for i, h in enumerate(head)}
    for i, row in enumerate(rows[1:], 2):
        if not row or not any(c.strip() for c in row):
            continue
        ref = row[idx["model_id:id"]] if idx["model_id:id"] < len(row) else ""
        tail = ref.split(".", 1)[-1]
        g.access.append({"id": row[idx["id"]] if "id" in idx and idx["id"] < len(row) else "", "model_ref": ref,
                         "model_tail": tail[len("model_"):] if tail.startswith("model_") else tail,
                         "group": row[idx["group_id:id"]] if "group_id:id" in idx and idx["group_id:id"] < len(row) else "",
                         "op": row[idx["operation"]] if "operation" in idx and idx["operation"] < len(row) else "",
                         "path": p, "line": i})


def access_model(g: Graph, row: dict) -> str | None:
    tail = row["model_tail"]
    for m in g.models:
        if m.replace(".", "_") == tail:
            return m
    return None


# ------------------------------------------------------------------------------------------------ commands


def near(word: str, options) -> list[str]:
    return difflib.get_close_matches(word, sorted(options), n=4, cutoff=0.5)


def out(a, data, lines: list[str]) -> None:
    print(json.dumps(data, indent=1, sort_keys=True) if a.json else "\n".join(lines))


def cmd_summary(g: Graph, a) -> int:
    counts = {"addons": len(g.addons), "models": len(g.models), "fields": sum(len(m["fields"]) for m in g.models.values()),
              "rpc_methods": sum(1 for m in g.models.values() for x in m["methods"].values() if x["rpc"]),
              "views": len(g.views), "menus": len(g.menus), "actions": len(g.actions), "access_rows": len(g.access),
              "other_records": len(g.records), "not_understood": len(g.unparsed)}
    lines = ["addon graph: " + ", ".join(f"{v} {k}" for k, v in counts.items())]
    for p, ln, why in g.unparsed[:20]:
        lines.append(f"  not understood: {p}:{ln}: {why}")
    out(a, {"counts": counts, "not_understood": [{"at": f"{p}:{ln}", "reason": w} for p, ln, w in g.unparsed]}, lines)
    return 0


def cmd_model(g: Graph, a) -> int:
    m = g.models.get(a.name)
    if m is None:
        close = near(a.name, g.models)
        out(a, {"exists": False, "did_you_mean": close},
            [f"model {a.name}: not found in these addons (it may come from the framework or another addon path)"
             + (f"; did you mean: {', '.join(close)}" if close else "")])
        return 1
    d: dict = {"model": a.name, "declared": [{"addon": x, "how": h, "at": f"{p}:{l}"} for x, h, p, l in m["decls"]],
               "inherits": sorted(set(m["inherits"]))}
    lines = [f"model {a.name}" + (f" - {m.get('summary')}" if m.get("summary") else "")]
    lines += [f"  {h} by {x}  {p}:{l}" for x, h, p, l in m["decls"]]
    if m["inherits"]:
        lines.append("  inherits: " + ", ".join(sorted(set(m["inherits"]))))
    flds = g.fields_of(a.name)
    d["fields"] = {k: {kk: v[kk] for kk in ("kind", "comodel", "path", "line")} for k, v in sorted(flds.items())}
    lines.append(f"fields ({len(flds)}):")
    for k, v in sorted(flds.items()):
        lines.append(f"  {k}: {v['kind'] or '?'}" + (f" -> {v['comodel']}" if v["comodel"] else "") + f"  {v['path']}:{v['line']}")
    meths = {k: v for mm in g.chain(a.name) for k, v in g.models.get(mm, {}).get("methods", {}).items()}
    d["methods"] = {k: {"rpc": v["rpc"], "effect": v["effect"], "at": f"{v['path']}:{v['line']}"} for k, v in sorted(meths.items())}
    if meths:
        lines.append(f"methods ({len(meths)}; rpc = exposed):")
        lines += [f"  {k}{' [rpc ' + (v['effect'] or '-') + ']' if v['rpc'] else ''}  {v['path']}:{v['line']}" for k, v in sorted(meths.items())]
    views = [(k, v) for k, v in sorted(g.views.items()) if v["model"] == a.name]
    acts = [(k, v) for k, v in sorted(g.actions.items()) if v["model"] == a.name]
    menus = [(k, v) for k, v in sorted(g.menus.items()) if v["action"] in {x for x, _ in acts}]
    acc = [r for r in g.access if access_model(g, r) == a.name]
    d["views"] = [f"{k} {v['path']}:{v['line']}" for k, v in views]
    d["actions"] = [f"{k} {v['path']}:{v['line']}" for k, v in acts]
    d["menus"] = [f"{k} {v['path']}:{v['line']}" for k, v in menus]
    d["access"] = [f"{r['id']} {r['path']}:{r['line']}" for r in acc]
    for label, rows in (("views", d["views"]), ("actions", d["actions"]), ("menus", d["menus"]), ("access rows", d["access"])):
        if rows:
            lines.append(f"{label} ({len(rows)}):")
            lines += [f"  {r}" for r in rows]
    out(a, d, lines)
    return 0


def cmd_field(g: Graph, a) -> int:
    if a.model not in g.models:
        close = near(a.model, g.models)
        out(a, {"exists": False, "did_you_mean": close}, [f"field {a.model}.{a.field}: model {a.model} is not defined in these addons"
                                                            + (f"; did you mean: {', '.join(close)}" if close else "")])
        return 1
    flds = g.fields_of(a.model)
    if a.field in IMPLICIT_FIELDS:
        out(a, {"exists": True, "implicit": True}, [f"field {a.model}.{a.field}: exists (implicit)"])
        return 0
    if a.field not in flds:
        close = near(a.field, list(flds) + list(IMPLICIT_FIELDS))
        out(a, {"exists": False, "did_you_mean": close},
            [f"field {a.model}.{a.field}: NOT DECLARED in these addons" + (f"; did you mean: {', '.join(close)}" if close else "")
             + f" ({len(flds)} fields known; fields of a model from outside the addons path are not known here)"])
        return 1
    v = flds[a.field]
    used = [k for k, vw in sorted(g.views.items()) if vw["model"] == a.model and a.field in vw["fields"]]
    out(a, {"exists": True, "kind": v["kind"], "comodel": v["comodel"], "at": f"{v['path']}:{v['line']}", "views": used},
        [f"field {a.model}.{a.field}: {v['kind'] or '?'}" + (f" -> {v['comodel']}" if v["comodel"] else "") + f"  {v['path']}:{v['line']}",
         f"used in views: {', '.join(used) or 'none'}"])
    return 0


def cmd_impact(g: Graph, a) -> int:
    touched_models: dict[str, list[str]] = {}
    addons: set[str] = set()
    for raw in a.paths:
        p = Path(raw).as_posix().lstrip("./") if raw.startswith("./") else Path(raw).as_posix()
        own = g.owner(p)
        if own:
            addons.add(own)
        for name, m in g.models.items():
            if any(dp == p for _, _, dp, _ in m["decls"]) or any(v["path"] == p for v in m["fields"].values()):
                touched_models.setdefault(name, []).append(p)
        for vw in g.views.values():
            if vw["path"] == p and vw["model"]:
                touched_models.setdefault(vw["model"], []).append(p)
    deps: dict[str, list[str]] = {}
    todo = list(addons)
    seen = set(addons)
    while todo:
        cur = todo.pop()
        for name, ad in g.addons.items():
            if cur in ad["depends"] and name not in seen:
                seen.add(name)
                deps.setdefault(name, []).append(cur)
                todo.append(name)
    refs: list[str] = []
    for mname in sorted(touched_models):
        for k, v in sorted(g.views.items()):
            if v["model"] == mname and v["path"] not in a.paths:
                refs.append(f"view {k} ({v['path']}:{v['line']}) shows {mname}")
        for k, v in sorted(g.actions.items()):
            if v["model"] == mname:
                refs.append(f"action {k} ({v['path']}:{v['line']}) opens {mname}")
        for r in g.access:
            if access_model(g, r) == mname:
                refs.append(f"access row {r['id']} ({r['path']}:{r['line']}) grants {mname}")
        for other, m in sorted(g.models.items()):
            for fk, fv in m["fields"].items():
                if fv["comodel"] == mname and other != mname:
                    refs.append(f"field {other}.{fk} ({fv['path']}:{fv['line']}) points at {mname}")
    affected = sorted(addons | set(deps))
    d = {"addons": sorted(addons), "dependent_addons": sorted(deps), "models": sorted(touched_models), "references": refs,
         "lint": [f"addon-lint.py <addons path>/{x}" for x in affected]}
    lines = [f"impact of {len(a.paths)} file(s): addons {', '.join(sorted(addons)) or 'none found'}"
             + (f"; addons that depend on them: {', '.join(sorted(deps))}" if deps else "")]
    if touched_models:
        lines.append("models in these files: " + ", ".join(sorted(touched_models)))
    lines += [f"  {r}" for r in refs[:40]] + ([f"  ... +{len(refs) - 40} more"] if len(refs) > 40 else [])
    if affected:
        lines.append("check again: " + "; ".join(d["lint"]) + "   (the kit's lint tool; the framework's own loader is the authority)")
    out(a, d, lines)
    return 0


def words(text: str) -> list[str]:
    return [w for w in (t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*", text)) if w not in STOP and len(w) >= 3]


def cmd_context(g: Graph, a) -> int:
    ws = words(" ".join(a.text))
    scored: list[tuple[float, str, str, str]] = []   # score, at, label, why

    def hit(name: str, extra: str = "") -> int:
        parts = set(re.split(r"[^a-z0-9]+", (name + " " + extra).lower()))
        return sum(1 for w in ws if w in parts or any(p.startswith(w) for p in parts if len(w) >= 4))
    for name, m in g.models.items():
        n = hit(name, m.get("summary", ""))
        if n or name in " ".join(a.text):
            _, _, p, l = next((x for x in m["decls"] if x[1] == "defines"), m["decls"][0])
            scored.append((5.0 + 3 * n, f"{p}:{l}", f"model {name}", "name or description matches"))
            for fk, fv in m["fields"].items():
                if hit(fk, fv.get("string") or ""):
                    scored.append((3.0, f"{fv['path']}:{fv['line']}", f"field {name}.{fk}", f"field of {name} matching the text"))
            for v in (v for v in g.views.values() if v["model"] == name):
                scored.append((1.5, f"{v['path']}:{v['line']}", "view of " + name, "shows the model"))
            for k, v in g.actions.items():
                if v["model"] == name:
                    scored.append((1.5, f"{v['path']}:{v['line']}", f"action {k}", f"opens {name}"))
            for r in g.access:
                if access_model(g, r) == name:
                    scored.append((1.0, f"{r['path']}:{r['line']}", f"access row {r['id']}", f"grants {name}"))
            for mk, mv in m["methods"].items():
                if mv["rpc"]:
                    scored.append((2.0, f"{mv['path']}:{mv['line']}", f"rpc {name}.{mk}", f"exposed method of {name}"))
    for k, v in g.views.items():
        if hit(k, v["model"] or ""):
            scored.append((3.0, f"{v['path']}:{v['line']}", f"view {k}", "name matches"))
    for k, v in g.menus.items():
        if hit(k, v["name"]):
            scored.append((3.0, f"{v['path']}:{v['line']}", f"menu {k}", "name matches"))
    for k, v in g.addons.items():
        if hit(k, v["summary"]):
            scored.append((4.0, v["path"], f"addon {k}", "name or summary matches; depends on " + (", ".join(v["depends"]) or "nothing")))
    seen, rows = set(), []
    for s, at, label, why in sorted(scored, key=lambda t: -t[0]):
        if (at, label) not in seen:
            seen.add((at, label))
            rows.append((s, at, label, why))
    lines = [f"context for: {' '.join(a.text)[:90]}"] + [f"{at}  {label}  <- {why}" for _, at, label, why in rows[:CONTEXT_LINES - 2]]
    if not rows:
        lines.append("nothing in these addons matches; the framework's guide pages are the next place to read")
    out(a, {"results": [{"at": at, "item": label, "why": why} for _, at, label, why in rows[:CONTEXT_LINES - 2]]}, lines)
    return 0 if rows else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--addons-path", action="append", default=None, help="a directory of addons (repeatable; default ./addons)")
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("summary")
    p = sub.add_parser("model"); p.add_argument("name")
    p = sub.add_parser("field"); p.add_argument("model"); p.add_argument("field")
    p = sub.add_parser("impact"); p.add_argument("paths", nargs="+")
    p = sub.add_parser("context"); p.add_argument("text", nargs="+")
    for sp in sub.choices.values():
        sp.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    paths = [Path(x) for x in (a.addons_path or ["addons"])]
    if not any(p.is_dir() for p in paths):
        print("addon-graph: no addons directory found; pass --addons-path", file=sys.stderr)
        return 2
    g = build(paths)
    return {"summary": cmd_summary, "model": cmd_model, "field": cmd_field, "impact": cmd_impact, "context": cmd_context}[a.cmd](g, a)


if __name__ == "__main__":
    sys.exit(main())

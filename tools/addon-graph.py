#!/usr/bin/env python3
"""Index ERPForAll addon and framework declarations with source locations (Python 3.10+).

From the framework root run erpforall-addon-graph summary. In a separate addon project,
pass --framework-root DIR for core models, implicit fields and registered methods.
Use --help for the query commands and docs/addon-graph-format.md for the JSON export.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import io
from collections import defaultdict
from dataclasses import dataclass
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
        self.core_addons = {}
        self.core = False
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
        if self.core and "base" in out:
            out.remove("base")
            out.append("base")
        return out

    def method_sources(self, model):
        sources = defaultdict(list)
        for ancestor in self.chain(model):
            for key, method in self.models.get(ancestor, {}).get("methods", {}).items():
                sources[key].extend(method["sources"])
        return sources

    def fields_of(self, model: str) -> dict[str, dict]:
        found: dict[str, dict] = {}
        for m in self.chain(model):
            for k, v in self.models.get(m, {}).get("fields", {}).items():
                found.setdefault(k, v)
        return found


def build(paths: list[Path], framework: Path | None = None) -> Graph:
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
    rust = RustIndex(g)
    if framework is not None:
        read_framework(g, rust, framework)
    for name, a in sorted(g.addons.items()):
        d = Path(a["dir"])
        for f in sorted((d / "models").glob("*.toml")) if (d / "models").is_dir() else []:
            read_model_toml(g, name, f)
        for file, text in addon_rust_sources(d / "src"):
            rust.collect(name, file, text)
    rust.resolve()
    if framework is not None:
        apply_core_fields(g)
    for name, a in sorted(g.addons.items()):
        d = Path(a["dir"])
        for f in sorted(d.rglob("*.xml")):
            if not f.name.startswith("."):
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
        if "name" in m:
            mod["audit"] = m.get("kind") != "abstract" and m.get("log_access", True)
        if m.get("row_version"):
            mod["versioned"] = True
        mod["summary"] = m.get("description") or mod.get("summary", "")
        mod["inherits"] += [x for x in (m.get("inherit") or []) if isinstance(x, str)]
        for fld in m.get("field", []):
            fl = flines[fi] if fi < len(flines) else ln
            fi += 1
            if fld.get("name"):
                mod["fields"].setdefault(fld["name"], {"kind": fld.get("type"), "comodel": fld.get("comodel"), "addon": addon,
                                                       "path": p, "line": fl, "string": fld.get("string")})


@dataclass
class RustSource:
    addon: str
    path: str
    module: str
    clean: str
    skel: str
    imports: dict


def production_text(text: str) -> tuple[str, str]:
    clean, skel = lex_rust(text)
    for m in reversed(list(re.finditer(r"#\[\s*cfg\s*\(\s*test\s*\)\s*\]", skel))):
        start = skip_attrs(skel, m.end())
        bound = re.search(r"[{;]", skel[start:])
        if bound:
            end = start + bound.start()
            end = end if skel[end] == ";" else close_of(skel, end)
            if end >= start:
                blank = _blank(skel[m.start():end + 1])
                clean = clean[:m.start()] + blank + clean[end + 1:]
                skel = skel[:m.start()] + blank + skel[end + 1:]
    return clean, skel


def addon_rust_sources(root):
    files = {f: f.read_text(encoding="utf-8", errors="replace") for f in sorted(root.rglob("*.rs"))}
    excluded = set()
    for file, text in files.items():
        if "cfg" not in text or "mod " not in text:
            continue
        clean, skel = lex_rust(text)
        for cfg in re.finditer(r"#\[\s*cfg\s*\(\s*test\s*\)\s*\]", skel):
            end = skip_attrs(skel, cfg.end())
            external = re.compile(r"(?:pub(?:\s*\([^)]*\))?\s+)?mod\s+(\w+)\s*;").match(skel, end)
            if external:
                path = re.search(r'#\[\s*path\s*=\s*"([^"]+)"\s*\]', clean[cfg.end():end])
                if path:
                    excluded.add(file.parent / path[1])
                else:
                    parent = file.parent if file.stem in ("lib", "mod") else file.with_suffix("")
                    excluded.update((parent / (external[1] + ".rs"), parent / external[1] / "mod.rs"))
    for file, text in files.items():
        if file not in excluded and "tests" not in file.relative_to(root).parts:
            yield file, text


def import_paths(tree: str, prefix: str = ""):
    tree = tree.strip()
    if "{" in tree:
        head, children = tree.split("{", 1)
        for part in split_top(children, 0, children.rfind("}")):
            yield from import_paths(part, prefix + head.strip())
    else:
        source, *aliases = re.split(r"\s+as\s+", tree, maxsplit=1)
        alias = aliases[0] if aliases else ""
        path = prefix + source.strip()
        yield alias.strip() or path.split("::")[-1], path


def add_method(g, model, name, addon, path, line, exposure=None, effect=None, invocation=None):
    origin = {"addon": addon, "path": path, "line": line}
    if invocation:
        origin["invocation"] = invocation
    if exposure is not None:
        origin.update(rpc=exposure, effect=effect)
    methods = g.model(model)["methods"]
    method = methods.setdefault(name, {**origin, "rpc": False, "effect": None, "sources": []})
    method["sources"].append(origin)
    method["rpc"], method["effect"] = exposure_of(method["sources"])


def exposure_of(sources):
    visible = [s for s in sources if s.get("rpc")]
    if not visible or any(s.get("rpc") is False for s in sources):
        return False, None
    effects = [s["effect"] for s in visible if s.get("effect")]
    severity = {"read": 0, "write": 1, "destructive": 2, "external": 3}
    return True, max(effects, key=lambda e: severity.get(e, -1), default=None)


def method_targets(src, target, offset):
    """Expand the single-arm, identifier-only method templates used by native addons."""
    if not target.startswith("$"):
        return [(target, None)]
    for macro in re.finditer(r"macro_rules!\s*(\w+)\s*\{", src.skel[:offset]):
        end = close_of(src.skel, macro.end() - 1)
        if not macro.end() <= offset < end:
            continue
        arm = re.match(r"\s*\(([^()]*)\)\s*=>\s*\{", src.skel[macro.end():end])
        if not arm:
            break
        body_end = close_of(src.skel, macro.end() + arm.end() - 1)
        if src.skel[body_end + 1:end].strip().strip(";").strip():
            break
        params = [re.fullmatch(r"\s*(\$\w+)\s*:\s*ident\s*", arg) for arg in arm[1].split(",")]
        if not all(params):
            break
        names = [arg[1] for arg in params]
        if target not in names:
            break
        calls = []
        for call in re.finditer(r"\b" + macro[1] + r"!\s*\(([^()]*)\)", src.skel):
            args = [a.strip() for a in call[1].rstrip(", \n\t").split(",")]
            if len(args) != len(params) or not all(re.fullmatch(r"\w+", a) for a in args):
                return []
            calls.append((args[names.index(target)], lineno(src.clean, call.start())))
        return calls
    return []


class RustIndex:
    def __init__(self, g):
        self.g = g
        self.types = defaultdict(set)  # Rust identifier -> (addon, module, model) candidates
        self.extensions = []
        self.dependencies = {}
        self.imports = {}
        self.reexports = defaultdict(list)
        self.parents = []
        self.methods = []

    def qualified(self, addon, scope, parts, visited):
        prefix, *tail = parts
        module = list(filter(None, scope.split("::")))
        if prefix in ("erp_sdk", "erp_orm"):
            return {c[2] for c in self.types[parts[-1]] if c[0] == "erp_sdk"}
        if prefix.startswith("erp_addon_"):
            addon = prefix.removeprefix("erp_addon_")
            module = []
        elif prefix == "crate":
            module = []
        elif prefix == "super":
            module = module[:-1]
        elif prefix != "self":
            module.append(prefix)
        for segment in tail[:-1]:
            if segment == "super":
                module = module[:-1]
            else:
                module.append(segment)
        scope = "::".join(module)
        key = (addon, scope, tail[-1])
        if key in visited:
            return set()
        direct = {c[2] for c in self.types[key[2]] if c[:2] == key[:2]}
        alias = self.imports.get(key)
        if direct:
            return direct
        if alias and "::" in alias:
            return self.qualified(addon, scope, alias.split("::"), visited | {key})
        found = set()
        for glob in self.reexports[addon, scope]:
            found.update(self.qualified(addon, scope, [*glob, key[2]], visited | {key}))
        return found

    def lookup(self, src, target):
        target = re.sub(r"\s*::\s*", "::", target)
        explicit = target if "::" in target else src.imports.get(target)
        if explicit and "::" in explicit:
            return self.qualified(src.addon, src.module, explicit.split("::"), set())
        candidates = self.types[target]
        local = {c for c in candidates if c[:2] == (src.addon, src.module)}
        visible = {c for c in candidates if c[0] in self.dependencies[src.addon]}
        candidates = local or {c for c in candidates if c[0] == src.addon} or visible
        return {c[2] for c in candidates}

    def target(self, src, typ, line, attr):
        candidates = self.lookup(src, typ)
        if len(candidates) == 1:
            return next(iter(candidates))
        why = "ambiguous: " + ", ".join(sorted(candidates)) if candidates else "unresolved"
        self.g.bad(src.path, line, f"{attr} target type `{typ}` is {why}")
        return None

    def collect(self, addon, f, text):
        attr = r"#\s*\[\s*(model|extend|methods)\s*\("
        if "use " not in text and not re.search(attr, text):
            return
        clean, skel = production_text(text)
        parts = f.relative_to(Path(self.g.addons[addon]["dir"]) / "src").with_suffix("").parts
        module = "::".join(parts[:-1] if parts[-1] in ("mod", "lib") else parts)
        nested = [(m.end(), close_of(skel, m.end() - 1), m[1]) for m in re.finditer(r"\bmod\s+(\w+)\s*\{", skel)]

        def module_at(offset):
            return "::".join(filter(None, [module, *(name for start, stop, name in nested if start <= offset < stop)]))

        imports = defaultdict(dict)
        for clause in re.finditer(r"\b(pub(?:\s*\([^)]*\))?\s+)?use\s+([^;]+);", skel):
            scope = module_at(clause.start())
            for alias, path in import_paths(clause[2]):
                if alias == "*" and clause[1]:
                    self.reexports[addon, scope].append(path.split("::")[:-1])
                imports[scope][alias] = path
                self.imports[addon, scope, alias] = path
        for m in re.finditer(attr, skel):
            scope = module_at(m.start())
            src = RustSource(addon, f.as_posix(), scope, clean, skel, imports[scope])
            ln = lineno(clean, m.start())
            oc = close_of(skel, m.end() - 1)
            end = close_of(skel, skel.index("[", m.start(), m.end()))
            if oc < 0 or end < oc:
                self.g.bad(src.path, ln, "unbalanced Rust attribute")
                continue
            pos, kw = parse_args(clean, m.end(), oc)
            start = skip_attrs(skel, end + 1)
            if m[1] == "methods":
                impl = re.compile(r"impl\b[^{;]*\{").match(skel, start)
                if not pos or not impl:
                    self.g.bad(src.path, ln, "#[methods] needs a target type and impl block")
                else:
                    self.methods.append((src, ln, pos[0], impl.end() - 1, m.start()))
                continue
            sm = re.compile(r"(?:pub(?:\s*\([^)]*\))?\s+)?struct\s+(\w+)").match(skel, start)
            if not sm:
                self.g.bad(src.path, ln, "no struct after the attribute")
                continue
            decl = (src, ln, sm, kw)
            if m[1] == "extend" and pos:
                self.extensions.append((pos[0], decl))
                continue
            name = lit(kw.get("name"))
            if not name or m[1] == "extend":
                self.g.bad(src.path, ln, "missing literal model name or extension target")
                continue
            self.declare(name, "defines", decl)

    def declare(self, name, how, decl):
        src, ln, sm, kw = decl
        self.types[sm[1]].add((src.addon, src.module, name))
        finish_model(self.g, src.addon, src.path, ln, name, how, src.clean, src.skel, sm, kw)
        for parent in kw.get("inherit", "").strip("[]").split(","):
            if parent.strip():
                self.parents.append((name, src, ln, parent.strip()))

    def resolve(self):
        for addon in self.g.addons:
            visible = {"erp_sdk", "base"}
            todo = list(self.g.addons[addon]["depends"])
            while todo:
                dep = todo.pop()
                if dep not in visible:
                    visible.add(dep)
                    todo.extend(self.g.addons.get(dep, {}).get("depends", []))
            self.dependencies[addon] = visible
        remaining = self.extensions
        while remaining:
            unresolved = []
            for typ, decl in remaining:
                candidates = self.lookup(decl[0], typ)
                if len(candidates) == 1:
                    self.declare(next(iter(candidates)), "extends", decl)
                else:
                    unresolved.append((typ, decl))
            if len(unresolved) == len(remaining):
                for typ, (src, ln, _, _) in unresolved:
                    self.target(src, typ, ln, "#[extend]")
                break
            remaining = unresolved
        for name, src, ln, typ in self.parents:
            parent = self.target(src, typ, ln, "inherit")
            if parent:
                self.g.model(name)["inherits"].append(parent)
        for src, ln, typ, bo, offset in self.methods:
            targets = method_targets(src, typ, offset)
            if not targets:
                self.g.bad(src.path, ln, f"unsupported or uninstantiated method template {typ}")
            for target, call in targets:
                model = self.target(src, target, call or ln, "#[methods]")
                if model and model not in self.g.models:
                    self.g.bad(src.path, call or ln, f"model {model} is outside the indexed roots")
                elif model:
                    self.read_methods(src, bo, model, call)

    def read_methods(self, src, bo, model, call):
        end = close_of(src.skel, bo)
        pattern = re.compile(r"#\[\s*(rpc|method|constrains|onchange|compute)\b")
        pos = bo + 1
        while m := pattern.search(src.skel, pos, end):
            start = skip_attrs(src.skel, m.start())
            fn = re.compile(r"(?:pub(?:\s*\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)").match(src.skel, start)
            pos = max(start, m.end())
            if not fn:
                continue
            attrs = src.skel[m.start():start]
            rpc = re.search(r"#\[\s*rpc\b([^\]]*)", attrs)
            effect = re.search(r"\beffect\s*=\s*(\w+)", rpc[1]) if rpc else None
            add_method(self.g, model, fn[1], src.addon, src.path, lineno(src.clean, m.start()),
                       not re.search(r"\bhide\b", rpc[1]) if rpc else None, effect[1] if effect else None, call)


CORE_REGISTRY = "crates/erp-registry/src/compose.rs"
CORE_KEYS = "crates/erp-registry/src/keys.rs"
CORE_MODULES = "crates/erp-modules/src/base_models.rs"
CORE_DATA = "crates/erp-data/src/model_data.rs"
CORE_ORM = "crates/erp-orm/src"
CORE_INPUTS = (CORE_REGISTRY, CORE_KEYS, CORE_MODULES, CORE_DATA,
               CORE_ORM + "/records.rs", CORE_ORM + "/dispatch.rs", CORE_ORM + "/rpc/core.rs")


def string_constants(clean):
    return dict(re.findall(r'\bconst\s+(\w+)\s*:\s*&str\s*=\s*"([^"]+)"', clean))


def core_fields(g, path, clean, skel, constants, start, end):
    fields = {}
    for m in re.compile(r"\bFieldDecl::(\w+)\s*\(").finditer(skel, start, end):
        args = [arg.strip() for arg in split_top(clean, m.end(), close_of(skel, m.end() - 1))]
        kind = m[1]
        name = lit(args[0]) or constants.get(args[0])
        line = lineno(clean, m.start())
        if not name:
            g.bad(path, line, "unresolved core field name " + args[0])
            continue
        comodel = None
        if kind == "new":
            kind = re.sub(r"(?<!^)(?=[A-Z])", "_", args[1].removeprefix("KindDecl::")).lower()
        elif kind in ("one2many", "many2one", "many2many"):
            comodel = lit(args[1]) or constants.get(args[1])
            if not comodel:
                g.bad(path, line, "unresolved comodel " + args[1])
        fields[name] = {"kind": kind, "comodel": comodel, "path": path, "line": line, "string": None}
    return fields


def core_models(g, file):
    path = file.as_posix()
    clean, skel = production_text(file.read_text())
    constants = string_constants(clean)
    groups = {}
    for m in re.finditer(r"\bconst\s+(\w+)\s*:\s*&\[FieldDecl\]\s*=\s*&\[", skel):
        groups[m[1]] = core_fields(g, path, clean, skel, constants, m.end(), close_of(skel, m.end() - 1))
    for m in re.finditer(r"\bstatic\s+\w+\s*:\s*AddonDescriptor\s*=\s*AddonDescriptor\s*\{", skel):
        body = clean[m.end():close_of(skel, m.end() - 1)]
        name = re.search(r'\bname:\s*"([^"]+)"', body)
        deps = re.search(r"\bdepends:\s*&\[([^\]]*)\]", body)
        if name and deps:
            g.core_addons[name[1]] = (path, lineno(clean, m.start()), re.findall(r'"([^"]+)"', deps[1]))
    for m in re.finditer(r"\bModelDecl::(new|extension)\(", skel):
        end = close_of(skel, m.end() - 1)
        args = [arg.strip() for arg in split_top(clean, m.end(), end)]
        addon = lit(args[0])
        name = lit(args[1]) or constants.get(args[1])
        line = lineno(clean, m.start())
        if not name or not addon:
            g.bad(path, line, "unresolved core model declaration")
            continue
        mod = g.model(name)
        how = "defines" if m[1] == "new" else "extends"
        mod["decls"].append((addon, how, path, line))
        # Read chained builder calls, stopping at the end of this expression.
        pos = end + 1
        while attr := re.compile(r"\s*\.(\w+)\s*\(").match(skel, pos):
            pos = close_of(skel, attr.end() - 1) + 1
            if not pos:
                g.bad(path, line, "unbalanced core model builder call")
                break
            arg = clean[attr.end():pos - 1].strip()
            if attr[1] == "fields":
                fields = groups.get(arg)
                if fields is None:
                    fields = core_fields(g, path, clean, skel, constants, attr.end(), pos - 1)
                    if not fields:
                        g.bad(path, line, "unresolved core field group " + arg)
                mod["fields"].update({k: dict(v, addon=addon) for k, v in fields.items()})
            elif attr[1] == "description":
                mod["summary"] = lit(arg)
            elif how == "defines" and ((attr[1] == "kind" and arg == "ModelKind::Abstract")
                                       or (attr[1] == "log_access" and arg == "false")):
                mod["audit"] = False
        if how == "defines":
            mod.setdefault("audit", True)
    return groups


def core_methods(g, file, table=None):
    clean, skel = production_text(file.read_text())
    path = file.as_posix()
    constants = string_constants(clean)
    registered = None
    if table:
        items = re.search(r"\bstatic\s+" + table + r"\s*:[^=]+=\s*\[([^\]]*)\]", skel)
        if not items:
            g.bad(path, 1, f"missing core registration table {table}")
            return
        registered = set(re.findall(r"&\s*(\w+)", items[1]))
    seen = set()
    registrations = r"\bstatic\s+(\w+)\s*:\s*(?:\w+::)*(MethodImpl|RpcImpl)\s*=\s*(?:\w+::)*\2\s*\{"
    for m in re.finditer(registrations, skel):
        if registered is not None and m[1] not in registered:
            continue
        seen.add(m[1])
        body = clean[m.end():close_of(skel, m.end() - 1)]
        attrs = dict(re.findall(r'\b(addon|model|method):\s*("[^"]+"|\w+)', body))
        values = [lit(attrs.get(k)) or constants.get(attrs.get(k)) for k in ("model", "method", "addon")]
        effect = re.search(r"\beffect:\s*(?:\w+::)*Effect::(\w+)", body)
        exposure = "RpcDecl::Expose" in body if m[2] == "RpcImpl" else None
        if all(values):
            add_method(g, *values, path, lineno(clean, m.start()), exposure, effect[1].lower() if effect else None)
        else:
            g.bad(path, lineno(clean, m.start()), "unresolved core method registration")
    for m in re.finditer(r"\b(core_rpc|web_impl)!\s*\(", skel):
        args = [x.strip() for x in split_top(clean, m.end(), close_of(skel, m.end() - 1))]
        if registered is not None and args[0] not in registered:
            continue
        seen.add(args[0])
        rpc = m[1] == "core_rpc"
        name = lit(args[2 if rpc else 3])
        addon = lit(args[1]) if rpc else "web"
        line = lineno(clean, m.start())
        if name and addon:
            add_method(g, "base", name, addon, path, line, True if rpc else None, args[3].lower() if rpc else None)
        else:
            g.bad(path, line, "unresolved " + m[1] + " registration")

    if registered is not None:
        for symbol in sorted(registered - seen):
            g.bad(path, lineno(clean, items.start()), f"unresolved {table} entry {symbol}")


def read_framework(g, rust, root):
    g.core = True
    for rel in (CORE_REGISTRY, CORE_MODULES, CORE_DATA, CORE_KEYS):
        groups = core_models(g, root / rel)
        if rel == CORE_REGISTRY:
            g.audit_fields = groups.get("MAGIC_FIELDS", {})
        if rel == CORE_KEYS:
            g.version_fields = groups.get("ROW_VERSION_FIELDS", {})
    if not g.audit_fields:
        g.bad((root / CORE_REGISTRY).as_posix(), 1, "missing core audit field declarations")
    if not g.version_fields:
        g.bad((root / CORE_KEYS).as_posix(), 1, "missing core row-version field declaration")
    orm = root / CORE_ORM
    records, _ = production_text((orm / "records.rs").read_text())
    for m in re.finditer(r'impl\s+Model\s+for\s+(\w+)\s*\{\s*const\s+MODEL_NAME:[^=]+=\s*"([^"]+)"', records):
        rust.types[m[1]].add(("erp_sdk", "records", m[2]))
    dispatch, _ = production_text((orm / "dispatch.rs").read_text())
    for module in sorted(set(re.findall(r"crate::(\w+)::BUILTIN_IMPLS", dispatch))):
        file = orm / (module + ".rs")
        if not file.is_file():
            file = orm / module / "mod.rs"
        if file.is_file():
            core_methods(g, file, "BUILTIN_IMPLS")
        else:
            g.bad((orm / "dispatch.rs").as_posix(), lineno(dispatch, dispatch.index("crate::" + module + "::BUILTIN_IMPLS")),
                  "missing core method module " + module)
    core_methods(g, root / CORE_MODULES, "IMPLS")
    core_methods(g, orm / "rpc/core.rs", "CORE_RPC")
    for rel in ("crates/erp-data/src/impex/rpc.rs", "crates/erp-cli/src/human.rs", "crates/erp-cli/src/human/addon_detail.rs"):
        if (root / rel).is_file():
            core_methods(g, root / rel)


def apply_core_fields(g):
    for name, model in g.models.items():
        if name != "base" and "base" not in model["inherits"]:
            model["inherits"].append("base")
        for enabled, fields in ((model.get("audit"), g.audit_fields), (model.get("versioned"), g.version_fields)):
            if enabled:
                for k, field in fields.items():
                    model["fields"].setdefault(k, dict(field, addon="base"))


def finish_model(g: Graph, addon: str, p: str, ln: int, name: str, how: str, clean: str, skel: str,
                 sm: re.Match, kw: dict[str, str]) -> None:
    mod = g.model(name)
    mod["decls"].append((addon, how, p, ln))
    if kw.get("description") and lit(kw["description"]):
        mod["summary"] = lit(kw["description"])
    if how == "defines":
        mod["audit"] = lit(kw.get("kind")) != "abstract" and kw.get("log_access") != "false"
    if kw.get("row_version") == "true":
        mod["versioned"] = True
    bo = skel.find("{", sm.end())
    semi = skel.find(";", sm.end())
    if bo < 0 or 0 <= semi < bo:
        return
    bc = close_of(skel, bo)
    pos = bo
    while True:
        fm = re.compile(r"#\s*\[\s*field\s*\(").search(skel, pos, bc)
        if not fm:
            break
        fc = close_of(skel, fm.end() - 1)
        if fc < 0:
            g.bad(p, lineno(clean, fm.start()), "unbalanced field attribute")
            break
        args, fkw = parse_args(clean, fm.end(), fc)
        ident = re.compile(r"(?:pub(?:\s*\([^)]*\))?\s+)?(?:r#)?(\w+)\s*:").match(skel, skip_attrs(skel, skel.index("]", fc + 1) + 1))
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
    if "access" not in f.name or f.name.startswith("."):
        return
    p = f.as_posix()
    try:
        rows = list(csv.reader(io.StringIO(f.read_text(encoding="utf-8", errors="replace"))))
    except csv.Error as e:
        g.bad(p, 1, f"csv does not parse: {e}")
        return
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
    meths = g.method_sources(a.name)
    d["methods"] = {}
    if meths:
        lines.append(f"methods ({len(meths)}; rpc = exposed):")
    for key, sources in sorted(meths.items()):
        rpc, effect = exposure_of(sources)
        at = f"{sources[0]['path']}:{sources[0]['line']}"
        d["methods"][key] = {"rpc": rpc, "effect": effect, "at": at, "sources": sources}
        lines.append(f"  {key}" + (f" [rpc {effect or '-'}]" if rpc else "") + f"  {at}")
        for source in sources:
            if source is not sources[0] or "invocation" in source:
                call = f" (invoked at line {source['invocation']})" if "invocation" in source else ""
                lines.append(f"    {source['addon']}  {source['path']}:{source['line']}{call}")
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
    if (not g.core and a.field in IMPLICIT_FIELDS and a.field not in flds
            and (a.field in ("id", "display_name") or g.models[a.model].get("audit", True))):
        out(a, {"exists": True, "implicit": True}, [f"field {a.model}.{a.field}: exists (implicit)"])
        return 0
    if a.field not in flds:
        close = near(a.field, flds if g.core else list(flds) + list(IMPLICIT_FIELDS))
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
    known_paths = set()
    for m in g.models.values():
        for _, _, path, _ in m["decls"]:
            known_paths.add(path)
        for field in m["fields"].values():
            known_paths.add(field["path"])
        for method in m["methods"].values():
            for src in method["sources"]:
                known_paths.add(src["path"])
    known_paths.update(v["path"] for v in g.views.values())
    absolute_paths = {Path(p).resolve(): p for p in known_paths}
    for raw in a.paths:
        p = absolute_paths.get(Path(raw).resolve(), Path(raw).as_posix())
        own = g.owner(p)
        if own:
            addons.add(own)
        for name, m in g.models.items():
            if any(dp == p for _, _, dp, _ in m["decls"]) or any(v["path"] == p for v in m["fields"].values()) or any(
                src["path"] == p for method in m["methods"].values() for src in method["sources"]
            ):
                touched_models.setdefault(name, []).append(p)
                if not own:
                    addons.update(x for x, _, dp, _ in m["decls"] if dp == p and x in g.addons)
                    addons.update(src["addon"] for method in m["methods"].values() for src in method["sources"]
                                  if src["path"] == p and src["addon"] in g.addons)
        for vw in g.views.values():
            if vw["path"] == p and vw["model"]:
                touched_models.setdefault(vw["model"], []).append(p)
    # Core registrations on a parent model reach addons through model inheritance,
    # even in a standalone project that omits the base manifest.
    core_models = {name for name, paths in touched_models.items() if any(g.owner(p) is None for p in paths)}
    if core_models:
        for name, m in g.models.items():
            if core_models.intersection(g.chain(name)):
                touched_models.setdefault(name, [])
                addons.update(addon for addon, _, _, _ in m["decls"] if addon in g.addons)
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
    access_by_model = defaultdict(list)
    for row in g.access:
        access_by_model[access_model(g, row)].append(row)
    refs: list[str] = []
    for mname in sorted(touched_models):
        for k, v in sorted(g.views.items()):
            if v["model"] == mname and v["path"] not in a.paths:
                refs.append(f"view {k} ({v['path']}:{v['line']}) shows {mname}")
        for k, v in sorted(g.actions.items()):
            if v["model"] == mname:
                refs.append(f"action {k} ({v['path']}:{v['line']}) opens {mname}")
        for r in access_by_model[mname]:
            refs.append(f"access row {r['id']} ({r['path']}:{r['line']}) grants {mname}")
        for other, m in sorted(g.models.items()):
            for fk, fv in m["fields"].items():
                if fv["comodel"] == mname and other != mname:
                    refs.append(f"field {other}.{fk} ({fv['path']}:{fv['line']}) points at {mname}")
    affected = sorted(addons | set(deps))
    suggested_pkgs: list[str] = []
    for x in affected:
        ad = g.addons.get(x)
        if ad and ad.get("native"):
            suggested_pkgs.append(f"erp-addon-{x}")
            suite_dir = Path(ad["dir"]).resolve().parent.parent / "crates" / f"erp-suite-{x}"
            if (suite_dir / "Cargo.toml").is_file():
                suggested_pkgs.append(f"erp-suite-{x}")
    d = {"addons": sorted(addons), "dependent_addons": sorted(deps), "affected_addons": affected,
         "suggested_packages": suggested_pkgs, "models": sorted(touched_models), "references": refs,
         "lint": [f"addon-lint.py <addons path>/{x}" for x in affected]}
    lines = [f"impact of {len(a.paths)} file(s): addons {', '.join(sorted(addons)) or 'none found'}"
             + (f"; addons that depend on them: {', '.join(sorted(deps))}" if deps else "")]
    if touched_models:
        lines.append("models in these files: " + ", ".join(sorted(touched_models)))
    lines += [f"  {r}" for r in refs[:40]] + ([f"  ... +{len(refs) - 40} more"] if len(refs) > 40 else [])
    if affected:
        lines.append("check again: " + "; ".join(d["lint"]) + "   (the kit's lint tool; the framework's own loader is the authority)")
    if suggested_pkgs:
        pkg_flags = " ".join(f"-p {p}" for p in suggested_pkgs)
        lines.append(f"test packages: scripts/check.sh {pkg_flags} --tests")
    out(a, d, lines)
    return 0


def export_graph(g: Graph) -> dict:
    """Every node and edge as plain data, sorted, so two runs on the same files give the same bytes."""
    nodes: dict[tuple[str, str], dict] = {}
    edges: list[dict] = []

    def node(kind: str, name: str, file: str | None, line: int | None) -> None:
        nodes.setdefault((kind, name), {"kind": kind, "name": name, "file": file, "line": line})

    def edge(kind: str, a: tuple[str, str], b: tuple[str, str], file: str | None, line: int | None) -> None:
        edges.append({"kind": kind, "from": f"{a[0]}:{a[1]}", "to": f"{b[0]}:{b[1]}", "file": file, "line": line})
    for name, (path, line, deps) in g.core_addons.items():
        if name not in g.addons:
            node("addon", name, path, line)
            for dep in deps:
                edge("depends_on", ("addon", name), ("addon", dep), path, line)
    for name, a in g.addons.items():
        node("addon", name, a["path"], 1)
        for dep in a["depends"]:
            edge("depends_on", ("addon", name), ("addon", dep), a["path"], 1)
    for mname, m in g.models.items():
        for addon, how, p, ln in m["decls"]:
            if how == "defines":
                node("model", mname, p, ln)
            edge(how, ("addon", addon), ("model", mname), p, ln)
        for inh in sorted(set(m["inherits"])):
            edge("inherits", ("model", mname), ("model", inh), m["decls"][0][2], m["decls"][0][3])
        for fname, f in m["fields"].items():
            node("field", f"{mname}.{fname}", f["path"], f["line"])
            edge("has_field", ("model", mname), ("field", f"{mname}.{fname}"), f["path"], f["line"])
            if f["comodel"]:
                edge("relates_to", ("field", f"{mname}.{fname}"), ("model", f["comodel"]), f["path"], f["line"])
        for meth, x in m["methods"].items():
            node("rpc" if x["rpc"] else "method", f"{mname}.{meth}", x["path"], x["line"])
            target = ("rpc" if x["rpc"] else "method", f"{mname}.{meth}")
            for source in x["sources"]:
                edge("has_method", ("model", mname), target, source["path"], source["line"])
                if "invocation" in source:
                    edge("has_method", ("model", mname), target, source["path"], source["invocation"])
    for k, v in g.views.items():
        node("view", k, v["path"], v["line"])
        if v["model"]:
            edge("refers_to", ("view", k), ("model", v["model"]), v["path"], v["line"])
            for fld in v["fields"]:
                owner = next((m for m in g.chain(v["model"]) if fld in g.models.get(m, {}).get("fields", {})), v["model"])
                edge("uses_field", ("view", k), ("field", f"{owner}.{fld}"), v["path"], v["line"])
        if v["inherits"]:
            edge("inherits", ("view", k), ("view", v["inherits"]), v["path"], v["line"])
    for k, v in g.actions.items():
        node("action", k, v["path"], v["line"])
        if v["model"]:
            edge("refers_to", ("action", k), ("model", v["model"]), v["path"], v["line"])
    for k, v in g.menus.items():
        node("menu", k, v["path"], v["line"])
        if v["action"]:
            edge("opens", ("menu", k), ("action", v["action"]), v["path"], v["line"])
        if v["parent"]:
            edge("child_of", ("menu", k), ("menu", v["parent"]), v["path"], v["line"])
    for r in g.access:
        full = r["id"]
        node("access", full, r["path"], r["line"])
        model = access_model(g, r)
        if model:
            edge("refers_to", ("access", full), ("model", model), r["path"], r["line"])
    for r in g.records:
        node("record", r["id"], r["path"], r["line"])
        if r["model"]:
            edge("refers_to", ("record", r["id"]), ("model", r["model"]), r["path"], r["line"])
    known = {f"{k}:{n}" for k, n in nodes}
    edges = [e for e in edges if e["to"] in known and e["from"] in known]
    key = lambda e: (e["kind"], e["from"], e["to"], e["file"] or "", e["line"] or 0)  # noqa: E731
    uniq = {json.dumps(e, sort_keys=True): e for e in edges}
    return {"format": "addon-graph/1",
            "nodes": sorted(nodes.values(), key=lambda n: (n["kind"], n["name"])),
            "edges": sorted(uniq.values(), key=key),
            "not_understood": [{"file": p, "line": ln, "reason": w} for p, ln, w in sorted(g.unparsed)]}


def cmd_export(g: Graph, a) -> int:
    print(json.dumps(export_graph(g), indent=1, sort_keys=True))
    return 0


def words(text: str) -> list[str]:
    return [w for w in (t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*", text)) if w not in STOP and len(w) >= 3]


def cmd_context(g: Graph, a) -> int:
    ws = words(" ".join(a.text))
    scored: list[tuple[float, str, str, str]] = []   # score, at, label, why

    def hit(name: str, extra: str = "") -> int:
        parts = set(re.split(r"[^a-z0-9]+", (name + " " + extra).lower()))
        return sum(1 for w in ws if w in parts or any(p.startswith(w) for p in parts if len(w) >= 4))
    for term in ws:
        model, _, member = term.rpartition(".")
        if model in g.models:
            field = g.fields_of(model).get(member)
            if field:
                scored.append((12.0, f"{field['path']}:{field['line']}", f"field {term}", "field declaration"))
            sources = g.method_sources(model).get(member, [])
            rpc, _ = exposure_of(sources)
            for source in sources:
                scored.append((12.0, f"{source['path']}:{source['line']}",
                               ("rpc " if rpc else "method ") + term, "method declaration"))
    for name, m in g.models.items():
        for key, method in m["methods"].items():
            label = f"{name}.{key}"
            if key.lower() in ws:
                for source in method["sources"]:
                    scored.append((10.0, f"{source['path']}:{source['line']}",
                                   ("rpc " if method["rpc"] else "method ") + label, "method declaration"))
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
    ap.add_argument("--framework-root", type=Path, help="ERPForAll checkout for the core index (auto-detected in the framework root)")
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("summary")
    sub.add_parser("export")
    p = sub.add_parser("model"); p.add_argument("name")
    p = sub.add_parser("field"); p.add_argument("model"); p.add_argument("field")
    p = sub.add_parser("impact"); p.add_argument("paths", nargs="+")
    p = sub.add_parser("context"); p.add_argument("text", nargs="+")
    for sp in sub.choices.values():
        sp.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    default_addons = Path("addons")
    if a.framework_root is not None and not default_addons.is_dir():
        default_addons = a.framework_root / "addons"
    paths = [Path(x) for x in (a.addons_path or [default_addons])]
    if not any(p.is_dir() for p in paths):
        print("addon-graph: no addons directory found; pass --addons-path", file=sys.stderr)
        return 2
    framework = a.framework_root
    if framework is None and Path(CORE_REGISTRY).is_file():
        framework = Path(".")
    if framework is not None and not all((framework / rel).is_file() for rel in CORE_INPUTS):
        print(f"addon-graph: incomplete ERPForAll framework root: {framework}", file=sys.stderr)
        return 2
    g = build(paths, framework)
    return {"summary": cmd_summary, "model": cmd_model, "field": cmd_field, "impact": cmd_impact, "context": cmd_context, "export": cmd_export}[a.cmd](g, a)


if __name__ == "__main__":
    sys.exit(main())

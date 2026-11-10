#!/usr/bin/env python3
"""Static checks for an ERPForAll addon directory. Python 3.11+, standard library only.

It catches mistakes an AI coding agent (or a person) commonly makes before the addon is
installed. It does not replace installing the addon: the framework's loader is the authority.

Checks (E = error, W = warning):
  manifest   manifest.toml parses; unknown keys (E); data/demo entries exist, are inside the addon,
             are .xml/.csv, are not listed twice (W); shipped files in data/ security/ views/ demo/ that
             the manifest does not list (E); depends lacks "base" (W); non-data-only files in an addon
             without Cargo.toml (W).
  models     models/*.toml keys and types as documented for data-only addons (E).
  access     security/ir.access.csv header, column count per row, operation letters (E),
             duplicate ids (E), model references that the addon does not define (E).
  xml        well-formed, no DOCTYPE, root element <erp> (legacy <odoo>/<openerp>/<data> W), only the
             documented elements and <record> attributes (E).
  ids        ref="..." / ref('...') / menu action= used before the record is defined in this addon (E);
             references to other modules that are not in depends (W).
  views      view `model` / action `res_model` not defined by the addon or (when the dependencies can
             be found with --addons-path) by its dependencies (E, or W when unverifiable); list/form/
             search root tag; translated attributes used as inheritance selectors (E); fields used by a
             view of a locally declared model that the model does not declare (W).
  native     for an addon with Cargo.toml: erp_sdk::addon!(name, depends) matches the directory and the
             manifest (W).

Usage: addon-lint.py [--addons-path DIR]... [--strict] <addon-dir>
Exit status: 0 no errors, 1 errors (or warnings with --strict), 2 usage error.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from xml.parsers import expat
from dataclasses import dataclass
from pathlib import Path

MANIFEST_KEYS = {
    "name", "summary", "description", "version", "license", "author", "category", "application",
    "depends", "data", "demo", "auto_install", "countries", "excludes", "installable",
    "pre_init_hook", "post_init_hook", "uninstall_hook", "exact_only", "extra",
}
MODEL_KEYS = {"name", "extend", "inherit", "description", "order", "rec_name", "table", "transient",
              "abstract", "field", "company_access"}  # company_access: seen in sample_library
FIELD_TYPES = {"boolean", "integer", "float", "monetary", "char", "text", "html", "selection", "date",
               "datetime", "json", "many2one", "one2many", "many2many"}
FIELD_KEYS = {"name", "type", "string", "help", "required", "readonly", "store", "copy", "groups",
              "index", "default", "related", "size", "digits", "currency_field", "selection",
              "selection_add", "comodel", "inverse", "relation", "column1", "column2", "ondelete",
              "domain", "context", "check_company"}
RELATIONAL = {"many2one", "one2many", "many2many"}
ROOTS_OK = {"erp"}
ROOTS_LEGACY = {"odoo", "openerp", "data"}
CONTAINERS = {"erp", "odoo", "openerp", "data"}
TOP_ELEMENTS = {"record", "template", "asset", "menuitem", "delete", "function"}
RECORD_ATTRS = {"id", "model", "forcecreate", "uid", "context"}  # data-files.md error example
VIEW_ROOTS = {"list", "form", "search"}
TRANSLATED_ATTRS = ("string", "help", "placeholder", "confirm", "title")
POSITIONS = {"inside", "after", "before", "replace", "attributes", "move"}
BUILTIN_FIELDS = {"id", "display_name", "create_uid", "create_date", "write_uid", "write_date"}
REF_CALL = re.compile(r"""\bref\(\s*['"]([^'"]+)['"]\s*\)""")
MODEL_ATTR = re.compile(r"#\[\s*model\((.*?)\)\s*\]", re.S)
NAME_IN_ATTR = re.compile(r"""\bname\s*=\s*"([^"]+)\"""")
EXTEND_ATTR = re.compile(r"#\[\s*extend\(\s*([A-Za-z_][A-Za-z0-9_:]*)")
ADDON_MACRO = re.compile(r"erp_sdk::addon!\s*\((.*?)\)\s*;", re.S)


@dataclass
class Finding:
    level: str  # "E" or "W"
    path: str
    line: int | None
    msg: str

    def __str__(self) -> str:
        loc = self.path + (f":{self.line}" if self.line else "")
        return f"{loc}: {self.level}: {self.msg}"


class _El:
    """Minimal element with the line it starts on (ElementTree does not keep lines)."""

    def __init__(self, tag: str, attrib: dict, lineno: int):
        self.tag, self.attrib, self.lineno = tag, attrib, lineno
        self.children: list[_El] = []
        self.text = ""

    def get(self, key: str, default=None):
        return self.attrib.get(key, default)

    def __iter__(self):
        return iter(self.children)

    def __len__(self):
        return len(self.children)

    def __getitem__(self, i):
        return self.children[i]

    def iter(self):
        yield self
        for c in self.children:
            yield from c.iter()


def parse_xml(path: Path) -> _El:
    text = path.read_text(encoding="utf-8")
    if re.search(r"<!DOCTYPE", text):
        raise ET.ParseError("DOCTYPE is not allowed in data files")
    stack: list[_El] = []
    root: list[_El] = []
    parser = expat.ParserCreate()

    def start(tag, attrs):
        el = _El(tag, dict(attrs), parser.CurrentLineNumber)
        (stack[-1].children if stack else root).append(el)
        stack.append(el)

    parser.StartElementHandler = start
    parser.EndElementHandler = lambda tag: stack.pop()
    parser.CharacterDataHandler = lambda data: stack[-1].__setattr__("text", stack[-1].text + data) if stack else None
    try:
        parser.Parse(text.encode("utf-8"), True)
    except expat.ExpatError as e:
        err = ET.ParseError(str(e))
        err.position = (e.lineno, e.offset)
        raise err from e
    return root[0]


def tech(model: str) -> str:
    return model.replace(".", "_")


class Linter:
    def __init__(self, addon: Path, addons_paths: list[Path]):
        self.dir = addon.resolve()
        self.name = self.dir.name
        self.paths = addons_paths
        self.findings: list[Finding] = []
        self.manifest: dict = {}
        self.local_models: dict[str, dict] = {}  # model -> {"fields": set|None, "toml": bool, "extend": bool}
        self.defined: dict[str, tuple[str, int | None]] = {}  # local id -> (file, line)
        self.defined_order: list[str] = []
        self.model_refs: list[tuple[str, str, int | None]] = []  # (model, file, line)
        self.ext_modules_used: dict[str, tuple[str, int | None]] = {}

    # -- helpers --------------------------------------------------------------------------
    def add(self, level: str, path: Path | str, line: int | None, msg: str) -> None:
        rel = str(path)
        if isinstance(path, Path):
            try:
                rel = str(path.relative_to(self.dir.parent))
            except ValueError:
                rel = str(path)
        self.findings.append(Finding(level, rel, line, msg))

    @property
    def native(self) -> bool:
        return (self.dir / "Cargo.toml").is_file()

    # -- manifest -------------------------------------------------------------------------
    def check_manifest(self) -> None:
        mpath = self.dir / "manifest.toml"
        if not mpath.is_file():
            self.add("E", mpath, None, "manifest.toml is missing")
            return
        try:
            self.manifest = tomllib.loads(mpath.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
            self.add("E", mpath, None, f"manifest.toml does not parse: {e}")
            return
        for key in self.manifest:
            if key not in MANIFEST_KEYS:
                self.add("E", mpath, None, f"unknown manifest key {key!r} (unknown keys are refused unless under [extra])")
        for key in ("data", "demo", "depends"):
            val = self.manifest.get(key, [])
            if not isinstance(val, list) or not all(isinstance(v, str) for v in val):
                self.add("E", mpath, None, f"{key} must be a list of strings")
                self.manifest[key] = []
        if "name" not in self.manifest:
            self.add("W", mpath, None, "no name key")
        depends = self.manifest.get("depends", [])
        if self.name != "base" and "base" not in depends:
            self.add("W", mpath, None, 'depends does not list "base"')
        for key in ("data", "demo"):
            seen: set[str] = set()
            for rel in self.manifest.get(key, []):
                p = (self.dir / rel).resolve()
                if rel in seen:
                    self.add("W", mpath, None, f"{key} lists {rel} twice (it would load twice)")
                seen.add(rel)
                if self.dir not in p.parents:
                    self.add("E", mpath, None, f"{key} path {rel} is outside the addon")
                elif not p.is_file():
                    self.add("E", mpath, None, f"{key} lists {rel}, which does not exist")
                elif p.suffix.lower() not in (".xml", ".csv") and not self.native:
                    self.add("E", mpath, None, f"{key} file {rel} is not .xml or .csv (data-only addons allow only those)")
        listed = set(self.manifest.get("data", [])) | set(self.manifest.get("demo", []))
        for folder, key in (("data", "data"), ("security", "data"), ("views", "data"), ("demo", "demo")):
            d = self.dir / folder
            if not d.is_dir():
                continue
            for f in sorted(d.rglob("*")):
                if f.is_file() and f.suffix.lower() in (".xml", ".csv"):
                    rel = f.relative_to(self.dir).as_posix()
                    if rel not in listed:
                        self.add("E", f, None, f"{rel} is not listed in manifest {key} (it would never load)")
        if not self.native:
            allowed_dirs = {"models", "views", "data", "demo", "security"}
            for f in sorted(self.dir.rglob("*")):
                rel = f.relative_to(self.dir)
                if f.is_symlink():
                    self.add("W", f, None, "symlink: the addon would not be offered as a data-only addon")
                elif f.is_file() and len(rel.parts) > 1 and rel.parts[0] in allowed_dirs:
                    ok = f.suffix.lower() in (".xml", ".csv") or (rel.parts[0] == "models" and f.suffix == ".toml")
                    if not ok and not f.name.upper().startswith("README"):
                        self.add("W", f, None, "file kind not allowed in a data-only addon")
                elif f.is_file() and len(rel.parts) == 1 and f.name != "manifest.toml" and not f.name.upper().startswith("README"):
                    self.add("W", f, None, "file kind not allowed in a data-only addon")
                elif f.is_file() and len(rel.parts) > 1 and rel.parts[0] not in allowed_dirs:
                    self.add("W", f, None, f"{rel.parts[0]}/ is not a data-only addon folder (static/, migrations/, ... need a native addon)")

    # -- models ---------------------------------------------------------------------------
    def check_models(self) -> None:
        mdir = self.dir / "models"
        if mdir.is_dir():
            for f in sorted(mdir.iterdir()):
                if f.suffix != ".toml" or not f.is_file():
                    if f.name.upper().startswith("README"):
                        continue
                    self.add("W", f, None, "only regular *.toml files may sit in models/")
                    continue
                self._check_model_file(f)
        for f in sorted((self.dir / "src").rglob("*.rs")) if (self.dir / "src").is_dir() else []:
            text = f.read_text(encoding="utf-8", errors="replace")
            for m in MODEL_ATTR.finditer(text):
                nm = NAME_IN_ATTR.search(m.group(1))
                if nm:
                    self.local_models.setdefault(nm.group(1), {"fields": None, "toml": False, "extend": False})
            for m in EXTEND_ATTR.finditer(text):
                self.local_models.setdefault("?" + m.group(1), {"fields": None, "toml": False, "extend": True})

    def _check_model_file(self, f: Path) -> None:
        try:
            doc = tomllib.loads(f.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
            self.add("E", f, None, f"does not parse: {e}")
            return
        for key in doc:
            if key != "model":
                self.add("E", f, None, f"unknown top-level key {key!r} (use [[model]] tables)")
        for model in doc.get("model", []):
            for key in model:
                if key not in MODEL_KEYS:
                    self.add("E", f, None, f"unknown model key {key!r}")
            n, e = model.get("name"), model.get("extend")
            if (n is None) == (e is None):
                self.add("E", f, None, "a [[model]] needs exactly one of name / extend")
                continue
            mname = n or e
            fields = {fd.get("name") for fd in model.get("field", []) if isinstance(fd, dict)}
            info = self.local_models.setdefault(mname, {"fields": set(), "toml": True, "extend": e is not None})
            if info["fields"] is None:
                info["fields"] = set()
            info["fields"] |= fields
            info["toml"] = True
            if e is not None or model.get("inherit") or model.get("abstract") or model.get("transient"):
                info["partial"] = True  # fields may come from elsewhere: do not check view fields
            for fd in model.get("field", []):
                self._check_field(f, mname, fd)

    def _check_field(self, f: Path, mname: str, fd: dict) -> None:
        fname = fd.get("name", "?")
        where = f"{mname}.{fname}"
        for key in fd:
            if key in ("compute", "depends"):
                self.add("E", f, None, f"{where}: {key} is refused in model files (use related, or a native addon)")
            elif key not in FIELD_KEYS:
                self.add("E", f, None, f"{where}: unknown field key {key!r}")
        t = fd.get("type")
        if t not in FIELD_TYPES:
            self.add("E", f, None, f"{where}: type {t!r} is not one of {sorted(FIELD_TYPES)}")
            return
        if t in RELATIONAL and "comodel" not in fd:
            self.add("E", f, None, f"{where}: {t} needs comodel")
        if t == "one2many" and "inverse" not in fd:
            self.add("E", f, None, f"{where}: one2many needs inverse")
        if t != "one2many" and "inverse" in fd:
            self.add("E", f, None, f"{where}: inverse only applies to one2many")
        rel = [k for k in ("relation", "column1", "column2") if k in fd]
        if rel and (t != "many2many" or len(rel) != 3):
            self.add("E", f, None, f"{where}: relation, column1 and column2 go together and only on many2many")
        if t != "selection" and ("selection" in fd or "selection_add" in fd):
            self.add("E", f, None, f"{where}: selection keys only apply to selection fields")
        if t == "selection" and "selection" not in fd and "selection_add" not in fd:
            self.add("W", f, None, f"{where}: selection field without selection")
        if t != "char" and "size" in fd:
            self.add("E", f, None, f"{where}: size only applies to char")
        if t != "float" and "digits" in fd:
            self.add("E", f, None, f"{where}: digits only applies to float")
        if (t in RELATIONAL or t == "json") and "default" in fd:
            self.add("E", f, None, f"{where}: relational and json fields take no default")

    # -- access csv -----------------------------------------------------------------------
    def _check_csv(self, p: Path) -> None:
        text = p.read_text(encoding="utf-8")
        lines = text.splitlines()
        while lines and lines[0].lstrip().startswith("#"):
            lines.pop(0)  # "# noupdate: 1" first line
        if not lines:
            self.add("E", p, None, "empty CSV file")
            return
        rows = list(csv.reader(lines))
        header = rows[0]
        if len(set(header)) != len(header) or any(not h.strip() for h in header):
            self.add("E", p, 1, "empty or repeated header cell")
            return
        is_access = "ir.access" in p.name or "ir.model.access" in p.name
        model_col = next((i for i, h in enumerate(header) if re.fullmatch(r"model_id([/:]id)?", h)), None)
        op_col = header.index("operation") if "operation" in header else None
        id_col = header.index("id") if "id" in header else None
        if is_access:
            for need in ("id", "operation"):
                if need not in header:
                    self.add("E", p, 1, f"access CSV header lacks {need!r}")
            if model_col is None:
                self.add("E", p, 1, "access CSV header lacks model_id/id")
            if not any(re.fullmatch(r"group_id([/:]id)?", h) for h in header):
                self.add("W", p, 1, "access CSV header lacks group_id/id")
        seen: set[str] = set()
        for n, row in enumerate(rows[1:], start=2):
            if not any(c.strip() for c in row):
                continue
            if len(row) != len(header):
                self.add("E", p, n, f"{len(row)} cells but the header has {len(header)}")
                continue
            if id_col is not None and row[id_col]:
                rid = row[id_col]
                if rid in seen:
                    self.add("E", p, n, f"duplicate id {rid!r}")
                seen.add(rid)
                self._define(rid, p, n)
            if is_access and op_col is not None:
                op = row[op_col]
                if not re.fullmatch(r"c?r?u?d?", op) or not op:
                    hint = " ('w' is not accepted: write is 'u')" if "w" in op else ""
                    self.add("E", p, n, f"operation {op!r} must be a non-empty subset of 'crud' in that order{hint}")
            if is_access and model_col is not None and row[model_col]:
                self._check_model_xmlid(row[model_col], p, n)

    def _check_model_xmlid(self, ref: str, p: Path, n: int) -> None:
        mod, _, rest = ref.rpartition(".")
        if not rest.startswith("model_"):
            self.add("E", p, n, f"model reference {ref!r} should look like <addon>.model_<model_name_with_underscores>")
            return
        if mod in ("", self.name):
            want = rest[len("model_"):]
            local = {tech(m) for m, i in self.local_models.items() if not m.startswith("?")}
            if self.local_models and want not in local and not self.native:
                self.add("E", p, n, f"{ref!r}: this addon defines no model whose table name is {want!r}")
        else:
            self._external_module(mod, p, n)

    # -- xml ------------------------------------------------------------------------------
    def check_xml_file(self, rel: str) -> None:
        p = self.dir / rel
        try:
            root = parse_xml(p)
        except (ET.ParseError, UnicodeDecodeError) as e:
            self.add("E", p, getattr(e, "position", (None,))[0], f"XML is not well-formed: {e}")
            return
        if root.tag in ROOTS_LEGACY:
            self.add("W", p, root.lineno, f"root <{root.tag}> is a legacy alias; the canonical root is <erp>")
        elif root.tag not in ROOTS_OK:
            self.add("E", p, root.lineno, f"root element <{root.tag}>: use <erp>")
            return
        self._walk(root, p)

    def _define(self, rid: str, p: Path, line: int | None) -> None:
        mod, _, name = rid.rpartition(".")
        if mod and mod != self.name:
            return  # updates another module's record
        if name in self.defined:
            first = self.defined[name]
            self.add("W", p, line, f"id {name!r} defined again (first in {first[0]}:{first[1]})")
            return
        self.defined[name] = (p.name, line)
        self.defined_order.append(name)

    def _walk(self, parent: _El, p: Path) -> None:
        for el in parent:
            tag = el.tag
            if tag in CONTAINERS and tag != "erp":
                self._walk(el, p)
            elif tag == "record":
                self._record(el, p)
            elif tag == "menuitem":
                self._menuitem(el, p)
            elif tag in ("template", "asset"):
                if el.get("id"):
                    self._define(el.get("id"), p, el.lineno)
            elif tag in TOP_ELEMENTS:
                pass
            else:
                self.add("E", p, el.lineno, f"unknown element <{tag}> (allowed: {', '.join(sorted(TOP_ELEMENTS))}, <data>)")

    def _record(self, el: _El, p: Path) -> None:
        for a in el.attrib:
            if a not in RECORD_ATTRS:
                self.add("E", p, el.lineno, f"unknown attribute {a!r} on <record>; allowed: id, model, forcecreate, uid, context")
        model = el.get("model")
        if not model:
            self.add("E", p, el.lineno, "<record> without model")
            return
        # one value per field, children must be <field>
        for ch in el:
            if ch.tag != "field":
                self.add("E", p, ch.lineno, f"<{ch.tag}> inside <record>: only <field> is allowed")
        # references in field values are resolved before the record itself is created
        fields = {ch.get("name"): ch for ch in el if ch.tag == "field"}
        for ch in el:
            if ch.tag == "field":
                self._field_refs(ch, p)
        if el.get("id"):
            self._define(el.get("id"), p, el.lineno)
        if model == "ir.ui.view":
            self._view_record(el, fields, p)
        elif model == "ir.actions.act_window":
            rm = fields.get("res_model")
            if rm is not None and (rm.text or "").strip():
                self.model_refs.append(((rm.text or "").strip(), p.name, rm.lineno))
        elif not model.startswith("ir."):
            self.model_refs.append((model, p.name, el.lineno))

    def _field_refs(self, field: _El, p: Path) -> None:
        refs = []
        if field.get("ref"):
            refs.append(field.get("ref"))
        refs += REF_CALL.findall(field.get("eval") or "")
        for r in refs:
            self._use_ref(r, p, field.lineno, strict=True)
        for ch in field:
            if ch.tag == "record":
                self._record(ch, p)

    def _menuitem(self, el: _El, p: Path) -> None:
        for key in ("action", "parent"):
            if el.get(key):
                self._use_ref(el.get(key), p, el.lineno, strict=False)
        for g in (el.get("groups") or "").split(","):
            g = g.strip().lstrip("-")
            if "." in g:
                self._external_module(g.rpartition(".")[0], p, el.lineno)
        if el.get("id"):
            self._define(el.get("id"), p, el.lineno)
        for ch in el:
            if ch.tag == "menuitem":
                self._menuitem(ch, p)

    def _use_ref(self, ref: str, p: Path, line: int | None, strict: bool) -> None:
        ref = ref.strip()
        if not ref:
            return
        mod, _, name = ref.rpartition(".")
        if mod and mod != self.name:
            self._external_module(mod, p, line)
            return
        if name.startswith(("model_", "field_")):
            return  # generated by the framework for each model and field
        if name in self.defined:
            return
        self.pending_refs.append((name, p, line, strict))

    def _external_module(self, mod: str, p: Path | str, line: int | None) -> None:
        deps = set(self.manifest.get("depends", []))
        if mod != self.name and mod not in deps and mod not in self.ext_modules_used:
            self.ext_modules_used[mod] = (str(p), line)

    # -- views ----------------------------------------------------------------------------
    def _view_record(self, el: _El, fields: dict[str, _El], p: Path) -> None:
        mfield = fields.get("model")
        model = (mfield.text or "").strip() if mfield is not None else ""
        inherit = fields.get("inherit_id")
        if model:
            self.model_refs.append((model, p.name, el.lineno))
        arch = fields.get("arch")
        if arch is None or len(arch) == 0:
            self.add("E", p, el.lineno, "view record without <field name=\"arch\"> content")
            return
        if arch.get("type") != "xml":
            self.add("W", p, arch.lineno, 'arch should be type="xml"')
        root = arch[0]
        if inherit is None:
            if root.tag in ("tree",):
                self.add("W", p, root.lineno, "the guide's addons use <list>, not <tree>")
            elif root.tag not in VIEW_ROOTS:
                self.add("W", p, root.lineno, f"view root <{root.tag}>: only list, form and search are checked by this lint")
            self._check_view_fields(root, model, p)
        else:
            self._check_inherit(arch, p)

    def _check_inherit(self, arch: _El, p: Path) -> None:
        for el in arch.iter():
            pos = el.get("position")
            if pos is None:
                continue
            if pos not in POSITIONS:
                self.add("E", p, el.lineno, f"position={pos!r} is not one of {sorted(POSITIONS)}")
            if el.tag == "xpath":
                expr = el.get("expr") or ""
                if not expr:
                    self.add("E", p, el.lineno, "<xpath> without expr")
                for a in TRANSLATED_ATTRS:
                    if re.search(rf"@{a}\b", expr):
                        self.add("E", p, el.lineno, f"xpath selects on the translated attribute @{a}: select by @name or position instead")
            else:
                for a in TRANSLATED_ATTRS:
                    if a in el.attrib:
                        self.add("E", p, el.lineno, f"<{el.tag}> locator uses the translated attribute {a!r}: locate by name instead")

    def _check_view_fields(self, root: _El, model: str, p: Path) -> None:
        info = self.local_models.get(model)
        if not info or not info["toml"] or info.get("partial") or info["fields"] is None:
            return
        declared = info["fields"] | BUILTIN_FIELDS

        def visit(node: _El, in_subview: bool) -> None:
            for ch in node:
                if ch.tag == "field":
                    n = ch.get("name")
                    if not in_subview and n and n not in declared:
                        self.add("W", p, ch.lineno, f"view field {n!r} is not declared by model {model}")
                    visit(ch, True)  # a field's children are a sub-view of another model
                else:
                    visit(ch, in_subview)
        visit(root, False)

    # -- models used vs defined -----------------------------------------------------------
    def _dependency_models(self) -> tuple[set[str], list[str]]:
        found: set[str] = set()
        missing: list[str] = []
        queue = list(self.manifest.get("depends", []))
        seen: set[str] = set()
        while queue:
            d = queue.pop()
            if d in seen or d == self.name:
                continue
            seen.add(d)
            root = next((q / d for q in self.paths if (q / d / "manifest.toml").is_file()), None)
            if root is None:
                missing.append(d)
                continue
            try:
                queue += tomllib.loads((root / "manifest.toml").read_text(encoding="utf-8")).get("depends", [])
            except (tomllib.TOMLDecodeError, UnicodeDecodeError):
                pass
            for f in sorted((root / "models").glob("*.toml")) if (root / "models").is_dir() else []:
                try:
                    for m in tomllib.loads(f.read_text(encoding="utf-8")).get("model", []):
                        found.add(m.get("name") or m.get("extend") or "")
                except (tomllib.TOMLDecodeError, UnicodeDecodeError):
                    pass
            for f in sorted((root / "src").rglob("*.rs")) if (root / "src").is_dir() else []:
                for m in MODEL_ATTR.finditer(f.read_text(encoding="utf-8", errors="replace")):
                    nm = NAME_IN_ATTR.search(m.group(1))
                    if nm:
                        found.add(nm.group(1))
        return found, missing

    def check_models_used(self) -> None:
        local = {m for m in self.local_models if not m.startswith("?")}
        first: dict[str, tuple[str, int | None]] = {}
        for m, f, l in self.model_refs:
            if m not in local:
                first.setdefault(m, (f, l))
        if not first:
            return
        dep_models, missing = self._dependency_models()
        native_ext = any(m.startswith("?") for m in self.local_models)
        unverifiable = []
        for m, (f, l) in sorted(first.items()):
            if m in dep_models:
                continue
            if missing or native_ext:
                unverifiable.append(m)
            else:
                self.add("E", self.dir / f, l, f"model {m!r} is defined neither by this addon nor by its dependencies")
        if unverifiable:
            why = ("dependencies not found in --addons-path: " + ", ".join(sorted(missing))) if missing \
                else "the addon extends models from native code"
            self.add("W", self.dir / "manifest.toml", None,
                     f"cannot verify {len(unverifiable)} model(s) ({why}): {', '.join(unverifiable)}")

    # -- native ---------------------------------------------------------------------------
    def check_native(self) -> None:
        lib = self.dir / "src" / "lib.rs"
        if not self.native or not lib.is_file():
            return
        m = ADDON_MACRO.search(lib.read_text(encoding="utf-8", errors="replace"))
        if not m:
            self.add("W", lib, None, "no erp_sdk::addon!(...) declaration found in src/lib.rs")
            return
        body = m.group(1)
        nm = NAME_IN_ATTR.search(body)
        if nm and nm.group(1) != self.name:
            self.add("W", lib, None, f"addon! name {nm.group(1)!r} differs from the directory name {self.name!r}")
        dm = re.search(r"depends\s*=\s*\[(.*?)\]", body, re.S)
        declared = set(re.findall(r'"([^"]+)"', dm.group(1))) if dm else set()
        listed = set(self.manifest.get("depends", []))
        if declared - {"base"} != listed - {"base"}:
            self.add("W", lib, None, f"addon! depends {sorted(declared)} and manifest depends {sorted(listed)} differ")

    # -- driver ---------------------------------------------------------------------------
    def run(self) -> list[Finding]:
        self.pending_refs: list[tuple[str, Path, int | None, bool]] = []
        self.check_manifest()
        if not self.manifest:
            return self.findings
        self.check_models()
        # data files are processed in manifest order so that "defined earlier" means "loaded earlier"
        for rel in self.manifest.get("data", []) + self.manifest.get("demo", []):
            p = self.dir / rel
            if not p.is_file():
                continue
            if rel.endswith(".csv"):
                self._check_csv(p)
            elif rel.endswith(".xml"):
                self.check_xml_file(rel)
        self._resolve_refs()
        self.check_models_used()
        self.check_native()
        for mod, (f, l) in sorted(self.ext_modules_used.items()):
            self.add("W", f, l, f"refers to module {mod!r}, which is not in depends")
        return self.findings

    def _resolve_refs(self) -> None:
        for name, p, line, strict in self.pending_refs:
            if name in self.defined:
                f, l = self.defined[name]
                # defined, but only after this use (it was not defined when the use was seen)
                msg = f"{name!r} is used before it is defined (defined later in {f}:{l}); order the files or records so it loads first"
                self.add("E" if strict else "W", p, line, msg)
            else:
                msg = f"{name!r} is not defined in this addon (use <module>.<id> for another addon's record)"
                self.add("E" if strict else "W", p, line, msg)


def lint(addon: Path, addons_paths: list[Path] | None = None) -> list[Finding]:
    paths = addons_paths if addons_paths else [addon.resolve().parent]
    return Linter(addon, [p.resolve() for p in paths]).run()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Static checks for an ERPForAll addon directory.")
    ap.add_argument("addon", help="the addon directory (the one holding manifest.toml)")
    ap.add_argument("--addons-path", action="append", default=[], metavar="DIR",
                    help="directory holding dependency addons (repeatable; default: the addon's parent)")
    ap.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    a = ap.parse_args(argv)
    addon = Path(a.addon)
    if not addon.is_dir():
        print(f"error: {addon} is not a directory", file=sys.stderr)
        return 2
    findings = lint(addon, [Path(p) for p in a.addons_path])
    for f in findings:
        print(f)
    errors = sum(f.level == "E" for f in findings)
    warns = len(findings) - errors
    print(f"{addon}: {errors} error(s), {warns} warning(s)")
    return 1 if errors or (a.strict and warns) else 0


if __name__ == "__main__":
    sys.exit(main())

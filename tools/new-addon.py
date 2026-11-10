#!/usr/bin/env python3
"""Scaffold a minimal data-only ERPForAll addon.

The layout is the one of the `sample_library` example addon: manifest.toml,
models/*.toml, security/ir.access.csv and views/*.xml (list and form views, a window
action and a menu), with the `<erp>` root element. Nothing needs compiling.

For a native (Rust) addon use the framework's own `erp scaffold <name>` instead.

Usage: new-addon.py <name> [--dest DIR] [--summary TEXT] [--author TEXT]
                    [--license EXPR] [--model NAME] [--icon lucide:NAME]
Python 3.11+, standard library only.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

NAME_RE = re.compile(r"^[a-zA-Z0-9_]{1,256}$")  # cli.md: technical module name
MODEL_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


def toml_str(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render(name: str, model: str, summary: str, author: str, license_: str, icon: str) -> dict[str, str]:
    """Return {relative path: file text} for the new addon."""
    title = name.replace("_", " ").title()
    tech = model.replace(".", "_")  # access rows name the model as model_<model_with_underscores>
    short = model.rsplit(".", 1)[-1].replace("_", " ").title()
    manifest = f"""name = {toml_str(title)}
summary = {toml_str(summary)}
version = "1.0.0"
license = {toml_str(license_)}
author = {toml_str(author)}
category = "Productivity"
application = true
depends = ["base"]
data = [
    "security/ir.access.csv",
    "views/{name}_views.xml",
]
"""
    models = f"""# {short} records of the {title} addon.
[[model]]
name = {toml_str(model)}
description = {toml_str(short)}
order = "name, id"

[[model.field]]
name = "name"
type = "char"
string = "Name"
required = true
index = true

[[model.field]]
name = "description"
type = "text"
string = "Description"
"""
    access = (
        "id,name,model_id/id,group_id/id,operation,domain\n"
        f"access_{tech}_user,{short} for internal users,{name}.model_{tech},base.group_user,crud,\n"
    )
    aside = """                <aside>
                    <group string="Record information">
                        <field name="create_uid" readonly="1"/>
                        <field name="create_date" readonly="1"/>
                        <field name="write_uid" readonly="1"/>
                        <field name="write_date" readonly="1"/>
                    </group>
                </aside>
"""
    views = f"""<?xml version="1.0" encoding="utf-8"?>
<erp>
    <record id="{tech}_list" model="ir.ui.view">
        <field name="name">{escape(model)}.list</field>
        <field name="model">{escape(model)}</field>
        <field name="arch" type="xml">
            <list string={quoteattr(short)}>
                <field name="name"/>
            </list>
        </field>
    </record>
    <record id="{tech}_form" model="ir.ui.view">
        <field name="name">{escape(model)}.form</field>
        <field name="model">{escape(model)}</field>
        <field name="arch" type="xml">
            <form string={quoteattr(short)}>
                <sheet>
                    <div class="oe_title"><h1><field name="name"/></h1></div>
                    <group>
                        <field name="description"/>
                    </group>
                </sheet>
{aside}            </form>
        </field>
    </record>
    <record id="{tech}_action" model="ir.actions.act_window">
        <field name="name">{escape(short)}</field>
        <field name="res_model">{escape(model)}</field>
        <field name="view_mode">list,form</field>
    </record>
    <menuitem id="{name}_menu" name={quoteattr(title)} groups="base.group_user" sequence="70" web_icon={quoteattr(icon)}>
        <menuitem id="{tech}_menu" name={quoteattr(short)} action="{tech}_action" sequence="10"/>
    </menuitem>
</erp>
"""
    return {
        "manifest.toml": manifest,
        "models/10_" + model.rsplit(".", 1)[-1] + ".toml": models,
        "security/ir.access.csv": access,
        f"views/{name}_views.xml": views,
    }


def scaffold(dest: Path, name: str, model: str | None = None, summary: str | None = None,
             author: str = "Addon Author", license_: str = "MIT OR Apache-2.0",
             icon: str = "lucide:library") -> list[Path]:
    if not NAME_RE.match(name):
        raise ValueError(f"invalid addon name {name!r}: use letters, digits and underscores (1..256)")
    model = model or f"{name}.item"
    if not MODEL_RE.match(model):
        raise ValueError(f"invalid model name {model!r}: lowercase dotted name such as 'my_addon.item'")
    root = dest / name
    if root.is_symlink() or (root.exists() and (not root.is_dir() or any(root.iterdir()))):
        raise FileExistsError(f"{root} exists and is not an empty directory")
    files = render(name, model, summary or f"{name.replace('_', ' ').title()} addon", author, license_, icon)
    written = []
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("name", help="technical addon name (letters, digits, underscores)")
    p.add_argument("--dest", default="addons", help="directory that will hold the addon (default: ./addons)")
    p.add_argument("--model", help="model name (default: <name>.item)")
    p.add_argument("--summary")
    p.add_argument("--author", default="Addon Author")
    p.add_argument("--license", default="MIT OR Apache-2.0")
    p.add_argument("--icon", default="lucide:library", help="web_icon of the top menu (a lucide:<name> the client ships)")
    a = p.parse_args(argv)
    try:
        written = scaffold(Path(a.dest), a.name, a.model, a.summary, a.author, a.license, a.icon)
    except (ValueError, FileExistsError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    for path in written:
        print(f"created {path}")
    print(f"next: run addon-lint.py {Path(a.dest) / a.name}, then "
          f"`erp module install -d <db> {a.name} --addons-path {a.dest}`")
    return 0


if __name__ == "__main__":
    sys.exit(main())

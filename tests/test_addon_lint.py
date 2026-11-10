import contextlib
import io
import tempfile
import textwrap
import unittest
from pathlib import Path

from _load import load

new_addon = load("new-addon")
addon_lint = load("addon-lint")


def write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return p


class LintCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        new_addon.scaffold(self.root, "shop", model="shop.item")
        self.addon = self.root / "shop"

    def tearDown(self):
        self._tmp.cleanup()

    def lint(self, **kw):
        return addon_lint.lint(self.addon, **kw)

    def messages(self, level=None, **kw):
        return [f.msg for f in self.lint(**kw) if level in (None, f.level)]

    def assertHas(self, needle, level="E", **kw):
        msgs = self.messages(level, **kw)
        self.assertTrue(any(needle in m for m in msgs), f"{needle!r} not in {msgs}")


class ManifestTest(LintCase):
    def test_clean_scaffold(self):
        self.assertEqual(self.lint(), [])

    def test_listed_file_missing(self):
        (self.addon / "views/shop_views.xml").unlink()
        self.assertHas("does not exist")

    def test_file_present_but_not_listed(self):
        write(self.addon, "views/extra.xml", "<erp/>")
        self.assertHas("views/extra.xml is not listed")

    def test_unknown_key(self):
        m = self.addon / "manifest.toml"
        m.write_text(m.read_text() + 'colour = "red"\n')
        self.assertHas("unknown manifest key 'colour'")

    def test_extra_table_is_allowed(self):
        m = self.addon / "manifest.toml"
        m.write_text(m.read_text() + '[extra]\ncolour = "red"\n')
        self.assertEqual(self.messages(), [])

    def test_non_xml_data_file_and_duplicates(self):
        m = self.addon / "manifest.toml"
        write(self.addon, "data/x.sql", "select 1;")
        m.write_text(m.read_text().replace('data = [', 'data = [\n    "data/x.sql",\n    "security/ir.access.csv",'))
        self.assertHas("not .xml or .csv")
        self.assertHas("twice", level="W")

    def test_path_escape(self):
        m = self.addon / "manifest.toml"
        m.write_text(m.read_text().replace('data = [', 'data = [\n    "../outside.xml",'))
        self.assertHas("outside the addon")

    def test_missing_base_dependency_warns(self):
        m = self.addon / "manifest.toml"
        m.write_text(m.read_text().replace('depends = ["base"]', 'depends = []'))
        self.assertHas('does not list "base"', level="W")

    def test_broken_toml(self):
        (self.addon / "manifest.toml").write_text("name = ")
        self.assertHas("does not parse")

    def test_foreign_files_warn_for_data_only(self):
        write(self.addon, "static/app.js", "x")
        self.assertHas("static/", level="W")


class AccessTest(LintCase):
    def csv(self, text):
        write(self.addon, "security/ir.access.csv", text)

    def test_w_is_not_an_operation(self):
        self.csv("id,name,model_id/id,group_id/id,operation,domain\na,A,shop.model_shop_item,base.group_user,rw,\n")
        self.assertHas("'w' is not accepted")

    def test_operation_order(self):
        self.csv("id,name,model_id/id,group_id/id,operation,domain\na,A,shop.model_shop_item,base.group_user,rc,\n")
        self.assertHas("subset of 'crud'")

    def test_column_count(self):
        self.csv("id,name,model_id/id,group_id/id,operation,domain\na,A,shop.model_shop_item,base.group_user,r\n")
        self.assertHas("5 cells but the header has 6")

    def test_duplicate_id(self):
        row = "a,A,shop.model_shop_item,base.group_user,r,\n"
        self.csv("id,name,model_id/id,group_id/id,operation,domain\n" + row + row)
        self.assertHas("duplicate id")

    def test_model_not_defined_by_addon(self):
        self.csv("id,name,model_id/id,group_id/id,operation,domain\na,A,shop.model_shop_ghost,base.group_user,r,\n")
        self.assertHas("defines no model")

    def test_header_without_model_column(self):
        self.csv("id,name,group_id/id,operation,domain\na,A,base.group_user,r,\n")
        self.assertHas("lacks model_id/id")

    def test_noupdate_comment_line_and_colon_header_accepted(self):
        self.csv("# noupdate: 1\nid,name,model_id:id,group_id:id,operation,domain\na,A,shop.model_shop_item,base.group_user,ru,\n")
        self.assertEqual(self.messages(), [])


class XmlTest(LintCase):
    VIEWS = "views/shop_views.xml"

    def views(self, text):
        write(self.addon, self.VIEWS, text)

    def test_not_well_formed(self):
        self.views("<erp><record></erp>")
        self.assertHas("not well-formed")

    def test_root_element(self):
        self.views('<odoo><record id="a" model="ir.actions.act_window"><field name="res_model">shop.item</field></record></odoo>')
        self.assertHas("legacy alias", level="W")
        self.views("<foo/>")
        self.assertHas("use <erp>")

    def test_doctype_refused(self):
        self.views('<!DOCTYPE erp [<!ENTITY x "y">]><erp/>')
        self.assertHas("DOCTYPE")

    def test_typo_in_field_and_attribute(self):
        self.views('<erp><record id="a" modle="x" model="ir.ui.view"><feild name="n"/></record></erp>')
        self.assertHas("unknown attribute 'modle'")
        self.assertHas("only <field> is allowed")

    def test_unknown_top_level_element(self):
        self.views("<erp><rekord/></erp>")
        self.assertHas("unknown element <rekord>")

    def test_ref_used_before_defined(self):
        self.views("""
            <erp>
              <record id="inh" model="ir.ui.view">
                <field name="model">shop.item</field>
                <field name="inherit_id" ref="base_form"/>
                <field name="arch" type="xml"><xpath expr="//field[@name='name']" position="after"><field name="description"/></xpath></field>
              </record>
              <record id="base_form" model="ir.ui.view">
                <field name="model">shop.item</field>
                <field name="arch" type="xml"><form><field name="name"/></form></field>
              </record>
            </erp>""")
        self.assertHas("used before it is defined")

    def test_ref_never_defined(self):
        self.views("""
            <erp><record id="a" model="ir.ui.view">
              <field name="model">shop.item</field>
              <field name="inherit_id" ref="shop.nope"/>
              <field name="arch" type="xml"><xpath expr="//form" position="inside"/></field>
            </record></erp>""")
        self.assertHas("'nope' is not defined in this addon")

    def test_eval_ref_and_external_refs(self):
        self.views("""
            <erp><record id="g" model="res.groups">
              <field name="name">G</field>
              <field name="implied_ids" eval="[Command.link(ref('base.group_user')), Command.link(ref('other.thing'))]"/>
            </record></erp>""")
        self.assertHas("module 'other'", level="W")
        self.assertNotIn("module 'base'", " ".join(self.messages("W")))

    def test_menu_action_defined_later_is_only_a_warning(self):
        self.views("""
            <erp>
              <menuitem id="m" name="M" action="later"/>
              <record id="later" model="ir.actions.act_window"><field name="res_model">shop.item</field></record>
            </erp>""")
        self.assertEqual([m for m in self.messages("E")], [])
        self.assertHas("used before it is defined", level="W")

    def test_translated_attribute_selector(self):
        self.views("""
            <erp>
              <record id="v" model="ir.ui.view"><field name="model">shop.item</field>
                <field name="arch" type="xml"><form><field name="name"/></form></field></record>
              <record id="inh" model="ir.ui.view">
                <field name="model">shop.item</field><field name="inherit_id" ref="v"/>
                <field name="arch" type="xml">
                  <xpath expr="//button[@string='Save']" position="after"><field name="description"/></xpath>
                  <button string="Save" position="after"><field name="description"/></button>
                </field>
              </record>
            </erp>""")
        msgs = self.messages("E")
        self.assertEqual(sum("translated attribute" in m for m in msgs), 2, msgs)

    def test_bad_position(self):
        self.views("""
            <erp>
              <record id="v" model="ir.ui.view"><field name="model">shop.item</field>
                <field name="arch" type="xml"><form><field name="name"/></form></field></record>
              <record id="inh" model="ir.ui.view"><field name="model">shop.item</field><field name="inherit_id" ref="v"/>
                <field name="arch" type="xml"><field name="name" position="below"/></field></record>
            </erp>""")
        self.assertHas("position='below'")

    def test_view_field_not_declared_warns(self):
        self.views("""
            <erp><record id="v" model="ir.ui.view"><field name="model">shop.item</field>
              <field name="arch" type="xml"><form><sheet><field name="name"/><field name="colour"/></sheet></form></field>
            </record></erp>""")
        self.assertHas("'colour' is not declared", level="W")

    def test_tree_root_warns(self):
        self.views("""
            <erp><record id="v" model="ir.ui.view"><field name="model">shop.item</field>
              <field name="arch" type="xml"><tree><field name="name"/></tree></field></record></erp>""")
        self.assertHas("<list>", level="W")


class ModelsTest(LintCase):
    def models(self, text):
        write(self.addon, "models/10_item.toml", text)

    def test_unknown_keys_and_types(self):
        self.models("""
            [[model]]
            name = "shop.item"
            colour = 1
            [[model.field]]
            name = "a"
            type = "varchar"
            [[model.field]]
            name = "b"
            type = "char"
            widget = "x"
            """)
        self.assertHas("unknown model key 'colour'")
        self.assertHas("type 'varchar'")
        self.assertHas("unknown field key 'widget'")

    def test_compute_refused_and_relations(self):
        self.models("""
            [[model]]
            name = "shop.item"
            [[model.field]]
            name = "a"
            type = "integer"
            compute = "_c"
            [[model.field]]
            name = "o"
            type = "one2many"
            comodel = "shop.item"
            [[model.field]]
            name = "m"
            type = "many2many"
            comodel = "shop.item"
            relation = "r"
            [[model.field]]
            name = "x"
            type = "many2one"
            """)
        self.assertHas("compute is refused")
        self.assertHas("one2many needs inverse")
        self.assertHas("go together")
        self.assertHas("many2one needs comodel")

    def test_name_xor_extend(self):
        self.models('[[model]]\nname = "shop.item"\nextend = "res.partner"\n')
        self.assertHas("exactly one of name / extend")

    def test_model_used_by_view_but_not_defined(self):
        write(self.root, "base/manifest.toml", 'name = "Base"\nversion = "1.0.0"\n')
        write(self.addon, "models/10_item.toml", '[[model]]\nname = "shop.other"\n')
        self.assertHas("neither by this addon nor by its dependencies", addons_paths=[self.root])

    def test_dependency_models_are_found_with_addons_path(self):
        write(self.root, "base/manifest.toml", 'name = "Base"\nversion = "1.0.0"\n')
        write(self.root, "base/models/10_p.toml", '[[model]]\nname = "res.partner"\n')
        write(self.root, "shop/views/more.xml", """
            <erp><record id="pv" model="ir.ui.view"><field name="model">res.partner</field>
              <field name="arch" type="xml"><form><field name="name"/></form></field></record></erp>""")
        m = self.addon / "manifest.toml"
        m.write_text(m.read_text().replace('"views/shop_views.xml",', '"views/shop_views.xml",\n    "views/more.xml",'))
        self.assertEqual(self.messages(addons_paths=[self.root]), [])

    def test_unverifiable_without_dependencies_is_a_warning(self):
        write(self.addon, "views/more.xml", """
            <erp><record id="pv" model="ir.ui.view"><field name="model">res.partner</field>
              <field name="arch" type="xml"><form><field name="name"/></form></field></record></erp>""")
        m = self.addon / "manifest.toml"
        m.write_text(m.read_text().replace('"views/shop_views.xml",', '"views/shop_views.xml",\n    "views/more.xml",'))
        self.assertEqual(self.messages("E"), [])
        self.assertHas("cannot verify 1 model(s)", level="W")


class NativeTest(LintCase):
    def test_native_macro_mismatch(self):
        write(self.addon, "Cargo.toml", '[package]\nname = "addon-shop"\n')
        write(self.addon, "src/lib.rs", 'erp_sdk::addon!(name = "other", depends = ["base", "mail"]);\n#[model(name = "shop.item", description = "Item")]\npub struct Item {}\n')
        msgs = self.messages("W")
        self.assertTrue(any("differs from the directory name" in m for m in msgs), msgs)
        self.assertTrue(any("depends" in m and "differ" in m for m in msgs), msgs)
        self.assertEqual(self.messages("E"), [])  # native: the model comes from src, no TOML needed


class CliTest(LintCase):
    def setUp(self):
        super().setUp()
        out = contextlib.redirect_stdout(io.StringIO())
        err = contextlib.redirect_stderr(io.StringIO())
        out.__enter__(), err.__enter__()
        self.addCleanup(out.__exit__, None, None, None)
        self.addCleanup(err.__exit__, None, None, None)

    def test_exit_codes(self):
        self.assertEqual(addon_lint.main([str(self.addon)]), 0)
        (self.addon / "views/shop_views.xml").unlink()
        self.assertEqual(addon_lint.main([str(self.addon)]), 1)
        self.assertEqual(addon_lint.main([str(self.root / "nope")]), 2)

    def test_strict_fails_on_warnings(self):
        m = self.addon / "manifest.toml"
        m.write_text(m.read_text().replace('depends = ["base"]', 'depends = []'))
        self.assertEqual(addon_lint.main([str(self.addon)]), 0)
        self.assertEqual(addon_lint.main(["--strict", str(self.addon)]), 1)


if __name__ == "__main__":
    unittest.main()

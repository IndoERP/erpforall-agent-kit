"""addon-graph.py: fixture addons in a temp dir; every command, exit codes, and what is reported as not understood."""
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _load import load

graph = load("addon-graph")

FILES = {
    "ws/addons/shop/manifest.toml": 'name = "Shop"\nsummary = "A tiny shop"\ndepends = ["base"]\ndata = ["views/v.xml", "security/ir.access.csv"]\n',
    "ws/addons/shop/Cargo.toml": '[package]\nname = "erp-addon-shop"\n',
    "ws/addons/shop/src/lib.rs": '''//! a doc line with #[model(name = "fake.model")] that must be ignored
#[model(name = "shop.order", description = "Sale order", inherit = [Thread])]
pub struct Order {
    /// a comment with a } brace
    #[field(char, required, string = "Reference")]
    pub name: Option<Arc<str>>,
    #[field(many2one, comodel = "shop.customer")]
    pub customer_id: Option<RecId>,
    #[field(char)]
    pub r#type: Option<Arc<str>>,
}
#[model(name = "shop.customer", description = "Customer")]
pub struct Customer {
    #[field(char)]
    pub name: Option<Arc<str>>,
}
#[methods(Order)]
impl Order {
    #[rpc(effect = write)]
    async fn confirm(this: &RecordSet<Order>) -> Result<()> { let _x = "{"; Ok(()) }
    #[method]
    fn _helper() {}
}
#[methods(Elsewhere)]
impl Elsewhere {}
''',
    "ws/addons/shop/views/v.xml": '''<erp>
  <record id="order_form" model="ir.ui.view">
    <field name="model">shop.order</field>
    <field name="arch" type="xml"><form><field name="name"/><field name="customer_id"/></form></field>
  </record>
  <record id="order_form_x" model="ir.ui.view">
    <field name="model">shop.order</field>
    <field name="inherit_id" ref="order_form"/>
    <field name="arch" type="xml"><form/></field>
  </record>
  <record id="order_action" model="ir.actions.act_window">
    <field name="name">Orders</field>
    <field name="res_model">shop.order</field>
  </record>
  <menuitem id="order_menu" name="Orders" action="order_action"/>
</erp>
''',
    "ws/addons/shop/security/ir.access.csv": "id,name,model_id/id,group_id/id,operation\naccess_order,Order,shop.model_shop_order,base.group_user,crud\n",
    "ws/addons/loyalty/manifest.toml": 'name = "Loyalty"\ndepends = ["shop"]\n',
    "ws/addons/loyalty/models/10_card.toml": '''[[model]]
name = "loyalty.card"
description = "Card"

[[model.field]]
name = "order_id"
type = "many2one"
comodel = "shop.order"

[[model]]
extend = "shop.order"

[[model.field]]
name = "points"
type = "integer"
''',
}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = Path(tempfile.mkdtemp(prefix="agfix"))
        for p, t in FILES.items():
            f = cls.d / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(t)
        cls.ws = cls.d / "ws"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d, ignore_errors=True)

    def run_cli(self, *argv):
        import os
        old = os.getcwd()
        os.chdir(self.ws)
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                code = graph.main(list(argv))
        finally:
            os.chdir(old)
        return code, buf.getvalue()


class BuildTests(Base):
    def test_graph_contents(self):
        import os
        old = os.getcwd(); os.chdir(self.ws)
        try:
            g = graph.build([Path("addons")])
        finally:
            os.chdir(old)
        self.assertEqual(set(g.addons), {"shop", "loyalty"})
        self.assertEqual(g.addons["loyalty"]["depends"], ["shop"])
        self.assertNotIn("fake.model", g.models)
        self.assertEqual(set(g.models), {"shop.order", "shop.customer", "loyalty.card"})
        order = g.models["shop.order"]
        self.assertEqual({"name", "customer_id", "type", "points"}, set(order["fields"]))  # r#type, and a field from an extension
        self.assertEqual(order["fields"]["customer_id"]["comodel"], "shop.customer")
        self.assertEqual(order["fields"]["customer_id"]["line"], 7)
        self.assertTrue(order["methods"]["confirm"]["rpc"])
        self.assertFalse(order["methods"]["_helper"]["rpc"])
        self.assertIn("shop.customer", {c for c in [f["comodel"] for f in order["fields"].values()]})
        self.assertEqual({"shop.order_form", "shop.order_form_x"}, set(g.views))
        self.assertEqual(g.views["shop.order_form_x"]["inherits"], "shop.order_form")
        self.assertEqual(g.views["shop.order_form"]["fields"], ["customer_id", "name"])
        self.assertEqual(g.menus["shop.order_menu"]["action"], "shop.order_action")
        self.assertEqual(g.access[0]["model_tail"], "shop_order")
        self.assertEqual(graph.access_model(g, g.access[0]), "shop.order")
        self.assertTrue(any("`Elsewhere`" in why for _, _, why in g.unparsed))


class CommandTests(Base):
    def test_summary(self):
        code, out = self.run_cli("summary")
        self.assertEqual(code, 0)
        self.assertIn("2 addons", out)
        self.assertIn("not understood", out)

    def test_model(self):
        code, out = self.run_cli("model", "shop.order")
        self.assertEqual(code, 0)
        for want in ("customer_id: many2one -> shop.customer", "confirm [rpc write]", "order_form", "order_action", "order_menu",
                     "access_order", "extends by loyalty"):
            self.assertIn(want, out)
        code, out = self.run_cli("model", "shop.ordr")
        self.assertEqual(code, 1)
        self.assertIn("shop.order", out)
        self.assertEqual(json.loads(self.run_cli("--json", "model", "shop.order")[1])["model"], "shop.order")

    def test_field(self):
        self.assertEqual(self.run_cli("field", "shop.order", "customer_id")[0], 0)
        code, out = self.run_cli("field", "shop.order", "custmer_id")
        self.assertEqual(code, 1)
        self.assertIn("did you mean: customer_id", out)
        self.assertEqual(self.run_cli("field", "shop.order", "write_date")[0], 0)
        self.assertEqual(self.run_cli("field", "res.partner", "name")[0], 1)  # outside these addons: not asserted either way
        self.assertEqual(self.run_cli("field", "shop.order", "points")[0], 0)

    def test_impact(self):
        code, out = self.run_cli("--json", "impact", "addons/shop/src/lib.rs")
        data = json.loads(out)
        self.assertEqual(data["addons"], ["shop"])
        self.assertEqual(data["dependent_addons"], ["loyalty"])
        self.assertIn("shop.order", data["models"])
        self.assertTrue(any("access row access_order" in r for r in data["references"]))
        self.assertTrue(any("loyalty.card.order_id" in r for r in data["references"]))
        self.assertTrue(any(l.endswith("/loyalty") for l in data["lint"]))

    def test_context(self):
        code, out = self.run_cli("context", "add a confirm button to the order")
        self.assertEqual(code, 0)
        self.assertIn("addons/shop/src/lib.rs:2  model shop.order", out)
        self.assertIn("rpc shop.order.confirm", out)
        self.assertLessEqual(len(out.splitlines()), graph.CONTEXT_LINES)
        self.assertEqual(self.run_cli("context", "zzzqqq")[0], 1)
        code, out = self.run_cli("context", "list the items")  # `list` must not match a longer word
        self.assertNotIn("shop.order", out)

    def test_usage_error_without_addons(self):
        import os
        old = os.getcwd(); os.chdir(self.d)
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(graph.main(["summary"]), 2)
        finally:
            os.chdir(old)


class TomlTests(unittest.TestCase):
    def test_subset_reader_matches_tomllib_and_fails_loudly(self):
        doc = 'a = "x"\nn = [1, 2.5, true]\nt = { k = "v" }\n[[m]]\nname = "one"\n[m.s]\nz = 1\n'
        mini = graph._mini_toml(doc)
        self.assertEqual(mini, {"a": "x", "n": [1, 2.5, True], "t": {"k": "v"}, "m": [{"name": "one", "s": {"z": 1}}]})
        if graph._tomllib is None:
            self.skipTest("tomllib is not available on this Python (3.10): no reference reader to compare with")
        self.assertEqual(mini, graph._tomllib.loads(doc))
        for bad in ("d = 1979-05-27", "x = @", "x = [1"):
            with self.assertRaises(graph.TomlError):
                graph._mini_toml(bad)


class LexerTests(unittest.TestCase):
    def test_comments_and_strings(self):
        text = 'a // c {\nb "x}" /* y { */ c\'{\''
        clean, skel = graph.lex_rust(text)
        self.assertEqual((len(clean), len(skel)), (len(text), len(text)))
        self.assertNotIn("}", skel)
        self.assertIn('"x}"', clean)


if __name__ == "__main__":
    unittest.main()

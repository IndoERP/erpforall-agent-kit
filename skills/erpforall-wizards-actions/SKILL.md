---
name: erpforall-wizards-actions
description: Build transient wizard dialogs and custom full-screen client actions in an ERPForAll addon - transient models with <footer> confirm/cancel buttons, bounded act_window and display_notification action results, transient cleanup policy (transient_max_age_seconds), and ir.actions.client tags with ClientActionDecl and registerClientAction. Use when an object button opens a multi-field modal dialog or a menu opens a custom board or workspace.
---

# Wizards and client actions

Choose the simplest mechanism that fits the interaction:
- **One short input (text, date, selection) before an object method:** use a button `prompt="..."` attribute directly on the form (see `erpforall-views`), no wizard model needed.
- **Multi-field modal form before an action:** declare a **transient model** (`kind = "transient"`) with a `<footer>` form and return a bounded `act_window` action result.
- **Full-screen custom workspace (board, report viewer):** declare an `ir.actions.client` tag in Rust and register its screen in TypeScript.

## 1. Wizard model and form view

Declare a transient model (native Rust or WASM `kind = "transient"`, or TOML `transient = true`) and give it explicit `security/ir.access.csv` rows plus `company_access` if company-scoped (wizards grant no elevated access).

```rust
#[model(
    name = "sample_library.lend.wizard",
    kind = "transient",
    description = "Lend Book Wizard",
    transient_max_age_seconds = 7_200,
    transient_max_count = 500
)]
pub struct LendWizard {
    #[field(many2one, comodel = "sample_library.book", required, readonly = true)]
    pub book_id: Option<RecId>,
    #[field(many2one, comodel = "res.partner", required)]
    pub borrower_id: Option<RecId>,
    #[field(date, required)]
    pub due_date: Option<Date>,
}
```

Package a dialog `<form>` whose direct, last child is a `<footer>` with confirm and cancel buttons:

```xml
<form string="Lend Book">
    <group>
        <field name="book_id"/>
        <field name="borrower_id"/>
        <field name="due_date"/>
    </group>
    <footer>
        <button name="action_confirm" type="object" string="Lend" class="btn-primary"/>
        <button special="cancel" string="Cancel" class="btn-secondary"/>
    </footer>
</form>
```

- Clicking Confirm saves the transient record first, then calls `action_confirm`; Cancel and Escape discard edits.
- Set `transient_max_age_seconds` (default 3600, max 315,360,000, `0` disables) and `transient_max_count` (or `0`) to control cleanup policy; an operator runs `erp db vacuum-transient` to prune expired rows.

## 2. Returning bounded action results from methods

A button's `#[method(wire, rpc)]` / `#[rpc(effect = ...)]` method returns JSON matching the server's action-result contract (serialized <= 16 KiB, depth <= 6):

```json
{
  "type": "ir.actions.act_window",
  "name": "Lend Book",
  "res_model": "sample_library.lend.wizard",
  "target": "new",
  "views": [[false, "form"]],
  "context": {"default_book_id": 1, "default_due_date": "2026-11-11"}
}
```

- Pass only literal `default_<field>` keys for real fields of `res_model` (never `active_*`, company, or session keys). Supply either `views` or `view_id`/`view_mode`, never both.
- A dialog (`target` `"new"`) opens one form only (`views` `[[false, "form"]]`, or `view_mode` `form`) and takes **no `domain`**. A window result without `target` is refused.

### Opening records in the page (`target: "current"`)

A stat button or a drill that opens related records stays in the page. Two shapes are admitted (members: `type`, `name`, `res_model`, `target`, `views`, `domain`, `context`, `res_id`):

```json
{"type": "ir.actions.act_window", "name": "Contract History", "res_model": "hr.employee.version",
 "target": "current", "views": [[false, "list"], [false, "form"]],
 "domain": [["employee_id", "=", 7]], "context": {"default_employee_id": 7}}
```

```json
{"type": "ir.actions.act_window", "name": "Sales Order", "res_model": "sale.order",
 "res_id": 42, "target": "current", "views": [[false, "form"]]}
```

- **A list:** `views` is `list`, optionally followed by `form`, and nothing else (no kanban, hierarchy or `view_mode`); `domain` is a required literal array.
- **One record:** `res_id` with exactly one `[id|false, "form"]` view and no `domain`.
- `context` takes `default_<field>` literals, `search_default_<name>` (a boolean, safe integer or text up to 256 bytes), and booleans `active_test` and `create`.
- Integers in `domain` must fit the browser's safe range (2^53 - 1). The caller's read access on the records is checked when the result is shown.

A record method returns the dictionary as a `Value::Map`; `addons/hr/src/employee.rs` (`action_open_versions`) is the model to copy.
- After completing the work in `action_confirm`, show a toast and close the modal:

```json
{
  "type": "ir.actions.client",
  "tag": "display_notification",
  "params": {
    "title": "Lent",
    "message": "Book checked out.",
    "type": "success",
    "next": {"type": "ir.actions.act_window_close"}
  }
}
```

`params.type` accepts `info`, `success`, `warning`, or `danger` (plain text, max 4096 bytes). Returning scalar JSON means no action; arrays and arbitrary action chains are refused.

## 3. Full-screen client actions (`ir.actions.client`)

1. **Declare and validate the tag in Rust:**
   ```rust
   use erp_sdk::client_actions::ClientActionDecl;
   use erp_sdk::prelude::*;
   use erp_sdk::serde_json::{Map, Value as Json};

   fn check_params<'a>(_env: &'a Env, _tx: &'a mut Transaction, params: &'a Map<String, Json>)
       -> erp_sdk::BoxFuture<'a, Result<Map<String, Json>>> {
       Box::pin(async move { Ok(params.clone()) })
   }
   fn tags() -> Result<Vec<ClientActionDecl>> {
       Ok(vec![ClientActionDecl::new("my_addon.board", "My board", check_params)?])
   }
   erp_sdk::client_action_declarations!(tags);
   ```
   Tags must be `<addon>.<name>` (lowercase ASCII/digits/underscores, <= 64 bytes).
2. **Add XML record and menu:** `<record id="board_action" model="ir.actions.client"><field name="name">My board</field><field name="tag">my_addon.board</field><field name="params">{"board": 1}</field></record>`. Only `target="current"` with empty `context` is supported right now.
3. **Register the screen in TypeScript (`static/src/client.ts`):**
   ```ts
   import { registerClientAction } from "@erpforall/client";
   registerClientAction("my_addon.board", {
     async create(env) {
       const root = document.createElement("div");
       env.host.append(root);
       return { dispose() { root.remove(); }, captureState() { return {}; } };
     },
   });
   ```
   `dispose()` must be synchronous and idempotent; `captureState()` JSON (<= 16 KiB) comes back as `env.restored`.

## Not covered here

Standalone client extension bundling (`static/dist/manifest.json` in `ui-assets.md` and `erpforall-client-extensions`), operator commands for `erp db vacuum-transient` (`wizard-dialogs.md`).

## Sources

- docs/addon-guide/wizard-dialogs.md
- docs/addon-guide/client-actions.md
- examples/wasm/sample_library_wasm/src/lib.rs
- addons/web/src/action_result.rs
- addons/web/static/src/client/wizard-dialog.ts
- addons/hr/src/employee.rs
- addons/sale/src/report.rs

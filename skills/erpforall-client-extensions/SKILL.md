---
name: erpforall-client-extensions
description: Add web client code to an ERPForAll addon - a custom field widget, a control-panel extension, templates and styles declared in static/client.json, registries and patches in the Elang client. Use when a view needs a widget or UI behaviour that the built-in widgets do not give.
---

# Web client extensions (native addons)

Client code needs a **native** addon with a client build; a data-only addon cannot ship JavaScript or TypeScript. Prefer a built-in `widget="..."` in the view first (see `erpforall-views`). A custom widget does not grant data access: the server still authorizes descriptors, reads, onchange and writes for the real user.

## Layout and manifest

```text
my_addon/static/
  client.json
  tsconfig.json
  src/client.ts
  src/note-title.xml        # component templates
  src/notes.css             # optional styles
```

`static/client.json` (paths are relative to `static/` and cannot escape it):

```json
{"schema":1,"entry":"src/client.ts","templates":["src/note-title.xml","src/note-panel.xml"],"styles":["src/notes.css"]}
```

Declare the widget identity on the Rust side so the server can check it against the field kind:

```rust
#[erp_sdk::__private::linkme::distributed_slice(erp_sdk::views::FIELD_WIDGETS)]
#[linkme(crate = erp_sdk::__private::linkme)]
static NOTE_TITLE_WIDGET: erp_sdk::views::WidgetDecl =
    erp_sdk::views::WidgetDecl::new("acceptance_notes.note_title", &["char"]);
```

Use it in a view: `<field name="name" widget="acceptance_notes.note_title"/>`. An unknown widget identity or an incompatible field kind fails explicitly.

## `src/client.ts`

```ts
import { Component, elangFieldWidget, registerFieldWidget } from "@erpforall/client";
import type { FieldWidgetProps } from "@erpforall/client";

class NoteTitle extends Component<FieldWidgetProps> {
  static override template = "acceptance_notes.NoteTitle";
  get textValue(): string {
    const v = this.props.value;
    if (v === false || v === null || v === undefined) return "";
    if (typeof v !== "string") throw new Error("Invalid note title value.");
    return v;
  }
  onChange(event: Event): void {
    if (this.props.field.readonly) return;
    const input = event.currentTarget;
    if (!(input instanceof HTMLInputElement)) throw new Error("Expected title input.");
    this.props.change(input.value);
  }
}
registerFieldWidget("acceptance_notes.note_title", { kinds: ["char"], render: elangFieldWidget(NoteTitle) });
```

```xml
<templates>
  <t t-name="acceptance_notes.NoteTitle">
    <input type="text" t-att-name="this.props.field.name" t-att-value="this.textValue"
           t-att-disabled="this.props.field.readonly" t-on-change="this.onChange"/>
  </t>
</templates>
```

- Report edits with `this.props.change(value)` so the form runs onchange and keeps its dirty/save state. **Never send independent writes from a field component.**
- When a widget renders inside a record form, `WidgetEnvironment` also supplies `mode` (`"read"` or `"edit"`, used with `<form edit_mode="read">`) and `onRecordEvent(listener)` (returns an unsubscribe function and fires `saved` with `id`, `saveFailed`, `discarded` and `modeChanged` after the form settles; subscriptions end when the widget is disposed).
- **Additive list header (`registerListHeaderExtension`):** Mount a component above an action's list view (lists only, not kanban or pivot) with `registerListHeaderExtension("my_addon.header", { model: "my.model", create(env) { return { element, refresh(domain, { signal }) { ... }, dispose() { ... } }; } })`; `refresh` runs on each load with the active search domain.
- Additive control-panel component: `registerControlPanelExtension("addon.extension", { model: "acceptance.note", component: MyPanel })` (props `ControlPanelProps {title, model}`). Duplicate identities are rejected; there is no last-wins override.
- Shell chrome extensions come from the same public module: `registerCogMenuItem` (cog menu actions), `registerSystrayItem` (navbar), `registerCommandProvider` / `registerCommandCategory` (command palette, Control+K), `registerUserMenuItem`, `registerDebugItemProvider`. Their options (sequence, groups, `isDisplayed`, optional Lucide `icon`) are in `web-client.md`, "Shell extension registries".
- **Database appearance & server brand assets (via `static/dist/manifest.json`, see `ui-assets.md`):**
  - An installed addon can contribute a database appearance by declaring a global selection setting `<addon>.appearance` on `ir.config.setting` (with `"default"` and theme choices such as `"office-blue"`) and shipping `static/src/theme.css` under `static_files`; the shell loads `/<addon>/static/src/theme.css` and sets `data-office-theme="<value>"` (see `addons/theme_office_blue`). Only one appearance may be selected.
  - An installed addon can supply `static/brand/icon.svg`, `logo.svg` and `logo-dark.svg` under `static_files` in `static/dist/manifest.json` so `/favicon.ico` and `/erp/brand/*` (including on the login page) serve its images. At most one installed addon may ship brand images: installing a second one fails.
- Build a deployment's client with `ERP_UI_COMPILER=/path/to/erp-ui-compile node web/scripts/build-human-ui.mjs --addons web,my_addon` (from the framework checkout); nothing is compiled in the browser.

## Registries, services and patches (Elang)

Register contributions from an exported synchronous `register(ctx)` callback; importing a module alone must never patch or register anything. Registries (`RegistryHub.define(category, guard)` then `.add(key, value, {sequence})`), services (`class` with `static dependencies` and `static start(env, deps)`; `useService(Class)` in `setup()`), and patches (`ctx.patch(Class, sup => ({ method() { return sup.method.call(this); } }))`, `ctx.patchStatic`) are described in `client-extensions.md`. A later addon's patch that replaces a member without calling `sup` is flagged by the conflict lint (`node web/scripts/lint-patches.mjs tsconfig.json patches.json`, run with the pinned Node toolchain). Patches refuse `Object`, `Function`, `Array` prototypes and the keys `constructor`, `prototype`, `__proto__`.

## A widget without templates

A field widget can draw its own DOM with `render(env)` and no component or templates (`"templates": []` in `client.json`), as the HR org chart does. Declare the name in Rust and register it in `static/src/client.ts`:

```rust
#[erp_sdk::__private::linkme::distributed_slice(erp_sdk::views::FIELD_WIDGETS)]
#[linkme(crate = erp_sdk::__private::linkme)]
static HR_ORG_CHART_WIDGET: erp_sdk::views::WidgetDecl =
    erp_sdk::views::WidgetDecl::new("hr.org_chart", &["one2many"]);
```

```ts
registerFieldWidget("hr.org_chart", { kinds: ["one2many"], render: renderOrgChart });
```

`render` returns the node and a `dispose`; reload on `env.onRecordEvent?.(event => ...)` for `saved` and `discarded`.

## Navigation, translations, refused pages

- **Navigation from addon code** (`ShellNavigation`, exported with `Route` and `ActionRequest`): field widgets in the main form, list cells and kanban cards (not dialogs or one2many lines), services, systray items and client actions get `navigate(route)` and `openAction({xmlId, viewMode, domain, context})`. `openAction` opens a window action by external id as its list, or a new record in its form; context takes `default_<field>` keys only. A route naming a `method_action` is refused; both do nothing once the page was left.
- **Translations**: write client texts as `t("No records yet")` or `t("No {name} records yet", { name })`, and ship a catalog with `registerTranslations("id_ID", { "No records yet": "…" })`. An empty translation, a changed placeholder, or two catalogs translating one text differently is refused, naming the text. `node scripts/extract-client-strings.mjs <addon>` (in `web/`) prints a catalog skeleton; a `t()` argument must be one plain string literal.
- **Refused screen**: `registerRefusedActionPage(key, { create(env) })` replaces the body of "This screen is not open to your account." (at most one page is registered); `env` has `rpc` and `navigate`; `create` returns `{ element, dispose }`.
- `localDateIso` is exported too (the HR client imports it); its exact contract is not covered here.

## Not covered here

Saved favourites and list export/import menus (`addons/web/static/src/client/search/`); `brand.json` and `login.css` in `static/brand/` (accepted by `addons/web/src/assets/assembly.rs`, but no addon ships them). Reusable editors (code, date/time, HTML, signature, domain), dialogs and notification services, themes, full-screen client actions: see `human-client-extensions.md`, `ui-assets.md`, `web-client.md`, `wizard-dialogs.md`, `client-actions.md`, or the `erpforall-wizards-actions` skill.

## Sources

- docs/addon-guide/human-client-extensions.md
- docs/addon-guide/client-extensions.md
- docs/addon-guide/component-testing.md
- docs/addon-guide/web-client.md
- docs/addon-guide/ui-assets.md
- addons/web/static/src/client/public.ts
- addons/web/static/src/client/registry.ts
- addons/web/static/src/client/theme.ts
- addons/theme_office_blue/src/lib.rs
- addons/web/src/assets/assembly.rs
- crates/erp-server/src/web.rs
- addons/acceptance_notes/static/client.json
- addons/acceptance_notes/static/src/client.ts
- addons/acceptance_notes/static/src/note-title.xml
- addons/acceptance_notes/static/src/note-panel.xml
- addons/acceptance_notes/static/tsconfig.json
- addons/acceptance_notes/src/lib.rs
- addons/acceptance_notes/views/acceptance_notes_views.xml
- addons/hr/src/lib.rs
- addons/hr/static/src/client.ts
- addons/hr/static/client.json
- addons/web/static/src/client/translate.ts
- addons/web/static/src/client/refused-action.ts
- addons/web/static/src/client/activity-view.ts
- docs/development.md

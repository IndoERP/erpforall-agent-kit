---
name: erpforall-chatter
description: Add the chatter (messages, followers, activities, record history) to a model and its form in an ERPForAll addon - depend on mail, inherit mail.thread, place <chatter/> in the form view, track field changes, post messages from code, or give another addon's model a chatter through a bridge addon. Use when a record needs a discussion thread, followers, notes or a change history.
---

# Chatter on a model

The `mail` addon stores messages and followers for any record. Adding a chatter takes three steps, and the
history lines come for free once the model inherits the mixin.

1. **Depend on `mail`**: `depends = ["base", "mail"]` in `manifest.toml` (and in `erp_sdk::addon!(name = "...", depends = ["base", "mail"])` for a native addon).
2. **Inherit the mixin `mail.thread`.**
   - Data-only, in `models/*.toml`:
     ```toml
     [[model]]
     name = "x_visit"
     description = "Visit"
     inherit = ["mail.thread"]

     [[model.field]]
     name = "name"
     type = "char"
     ```
   - Native: `#[model(name = "helpdesk.ticket", description = "Ticket", inherit = [MailThread])]` with `use erp_addon_mail::MailThread;`. Add `MailActivityMixin` next to it for activities (`inherit = [MailThread, MailActivityMixin]`).
   - Inside one addon, declarations compose in source order (file path, then line): an extension of a model your addon also defines must sit in a file that sorts after the definition.
3. **Put the slot in the form view**, directly under `<form>`, at most once, beside the optional `<aside>`:
   ```xml
   <form>
     <sheet>...</sheet>
     <chatter reload_on_post="1" open_attachments="0"/>
   </form>
   ```
   `<chatter/>` has no children and accepts only `reload_on_post`, `reload_on_attachment`, `reload_on_activity`, `reload_on_follower`, `open_attachments`; each takes `1`, `0`, `true`, `false`, `True` or `False`. `groups` and `invisible` are not accepted, and it cannot sit inside `sheet`, `aside`, `group`, `page` or a `<t groups=...>` wrapper. A model that does not inherit `mail.thread` fails when the view is served (not when the XML is saved). Never write `has_activities` in the XML.

Nothing else is declared for the messaging store: every installed model that inherits `mail.thread` is added to the store schema by itself, and installing or uninstalling such an addon changes the schema the client fetches.

## A chatter on another addon's model (bridge addon)

To give a model of an addon you do not own a chatter, without making that addon depend on `mail`, ship a small native bridge addon with `auto_install = true` that depends on both. This is how `product_mail` (products) and `account_mail` (invoices and journal entries) are built:

```toml
# manifest.toml
name = "Product Mail Bridge"
version = "1.0.0"
license = "MIT OR Apache-2.0"
depends = ["base", "product", "mail"]
auto_install = true
data = ["views/product_template_views.xml"]
```

```rust
erp_sdk::addon!(name = "product_mail", depends = ["base", "product", "mail"]);
use erp_addon_mail::MailThread;
use erp_addon_product::ProductTemplate;
use erp_sdk::prelude::*;

#[extend(ProductTemplate, addon = "product_mail", inherit = [MailThread])]
pub struct ProductTemplateThread {}
```

The view inherits the owner's form and adds the slot after the sheet: `<xpath expr="//sheet" position="after"><chatter/></xpath>`. An auto-install bridge installs when the second of its dependencies is installed; on a database that already has both, upgrading does not install it, so an administrator installs it from Addons.

## Record history (no code needed)

- **Creation line:** a record created through the ORM gets one internal note, "*model description* created".
- **Tracked changes:** declare `tracking = true` on a stored field (`#[field(selection, ..., tracking = true)]`, or `tracking = <sequence>` to order the lines). A write that changes tracked fields writes one history message per record and write, listing each field's old and new value. A bridge can re-declare another addon's field with only `tracking = true`; the other attributes stay the owner's (`account_mail` does this for the invoice header fields).
- The registry refuses `tracking` on a field that is not stored, a one2many, a translated or company-dependent field, a stored computed or related field, a `secret` field, and `json`, binary and image fields, among others (`tracking.md` has the list). Model files (`models/*.toml`) and WebAssembly addons cannot declare `tracking`.
- A tracked field with `groups` is shown only to readers in those groups. Text values are cut at the system parameter `mail.tracking_value_max_chars`.
- Server-side code (imports) can pass the context keys `mail_create_nolog` (no creation line) or `tracking_disable` (no line); an RPC call that sends either is refused.
- Change what is written by overriding three mixin methods on your model: `_creation_message` (creation text, or no line for a record), `_track_subtype` (a subtype external id per record, e.g. one your addon ships), `_track_body` (a plain-text body next to the values). Each returns a `BTreeMap<i64, String>`; the compiled examples are in `mail.md`, "Record history".
- Code that writes a tracked field with its own SQL statement reports the change with `Transaction::track_external(records, field, [(id, old, new)])`; it does nothing when no installed addon tracks the field, so an application addon can call it without depending on `mail`. Ask `tx.tracks(records, field)` before reading an old value.

## Posting and thread behaviour (native code)

`message_post` takes a `PostRequest` (`PostRequest::new(Body::Text(...))`, then set `message_type`, `subtype`, `partner_ids`, `client_uid`, ...). The record must allow the operation `_mail_post_access` returns: write by default. Override it to allow posting with read access, as the bridges do with `#[method(override, sealed)] async fn _mail_post_access(...) -> Result<Operation> { Ok(Operation::Read) }`. Follower methods (`follow`, `unfollow`, `set_subtypes`, `followers`) and three methods that change what a thread shows (`_get_customer_portal_message_types`, `_store_thread_fields`, `mail.message._to_store`) are described in `mail.md`; the compiled example is `addons/mail/tests/chatter_guide.rs`. Clients do not call these Rust methods: they call the RPC wrappers `thread_post`, `thread_follow`, `thread_unfollow`, `thread_set_subtypes`, `thread_followers`, `thread_subtypes`, `thread_upload` and `thread_attach`.

Ship your own message subtypes as `mail.message.subtype` records with `res_model` set to your model.

## Status

The guide marks parts as not built yet: inbox and e-mail notifications, some panels of the thread loading (activities, scheduled messages, suggested recipients, contact fields, pinned messages: asking for one is refused by name), HTML message bodies, and large file uploads (the base64 upload is held to a small inline limit). Check `mail.md` before promising a feature to the user.

## Not covered here

Activities in detail (`mail.md`, "Add activities to a model"), scheduled messages, the message access rules, the client message store and thread component (`messaging-store.md`, `store-topic.md`, `store-wire.md`, `mail-thread-view.md`), attachments in general (see `erpforall-attachments`).

## Sources

- docs/addon-guide/mail.md
- docs/addon-guide/tracking.md
- docs/addon-guide/store-topic.md
- docs/addon-guide/human-form-layout.md
- docs/addon-guide/mail-thread-view.md
- addons/mail/manifest.toml
- addons/mail/tests/chatter_guide.rs
- addons/mail/tests/activity.rs
- addons/product_mail/manifest.toml
- addons/product_mail/src/lib.rs
- addons/product_mail/views/product_template_views.xml
- addons/account_mail/src/lib.rs
- addons/account_mail/views/account_move_views.xml
- crates/erp-test-models/tests/mail_history.rs

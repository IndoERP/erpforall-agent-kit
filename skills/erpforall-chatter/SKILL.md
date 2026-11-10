---
name: erpforall-chatter
description: Add the chatter (messages, followers, activities) to a model and its form in an ERPForAll addon - depend on mail, inherit mail.thread, place <chatter/> in the form view, post messages from code. Use when a record needs a discussion thread, followers or notes.
---

# Chatter on a model

The `mail` addon stores messages and followers for any record. Adding a chatter takes three steps.

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
   - Native: `#[model(name = "helpdesk.ticket", description = "Ticket", inherit = [MailThread])]` with `use erp_addon_mail::MailThread;`. To give a model another addon owns the mixin without editing that addon: `#[extend(Project, addon = "helpdesk", inherit = [MailThread])] pub struct ProjectThread {}`.
   - Inside one addon, declarations compose in source order (file path, then line): an extension of a model your addon also defines must sit in a file that sorts after the definition.
3. **Put the slot in the form view**, directly under `<form>`, at most once, beside the optional `<aside>`:
   ```xml
   <form>
     <sheet>...</sheet>
     <chatter reload_on_post="1" open_attachments="0"/>
   </form>
   ```
   `<chatter/>` has no children and accepts only `reload_on_post`, `reload_on_attachment`, `reload_on_activity`, `reload_on_follower`, `open_attachments`; each takes `1`, `0`, `true`, `false`, `True` or `False` (other text is refused). `groups` and `invisible` are not accepted, and it cannot sit inside `sheet`, `aside`, `group`, `page` or a `<t groups=...>` wrapper. If the model does not inherit `mail.thread`, serving the view fails with `View element <chatter> requires model '<model>' to inherit 'mail.thread'.` (the error appears when the view is served, not when the XML is saved). Never write `has_activities` in the XML; it is derived from `mail.activity.mixin`.

## What the mixin adds

`message_ids` (the record's messages the caller may read), `message_follower_ids` (follower rows; internal users only) and `message_partner_ids` (computed; writing it follows/unfollows partners). Deleting a record deletes its messages and followers. `res.partner` already inherits the mixin once `mail` is installed. Default message subtypes: `mail.mt_comment`, `mail.mt_note`, `mail.mt_activities`, `mail.mt_important_notification`.

## Posting and thread behaviour (native code)

`message_post` and the follower methods are model methods you call or override with `#[method(override)]`; three dispatched methods change what a thread shows (for example `_get_customer_portal_message_types` returns the message types a non-internal user sees). The compiled example is `addons/mail/tests/chatter_guide.rs`. Activities: `mail.activity.mixin` (see the `Task` model in `addons/mail/tests/activity.rs`).

## Status warning

The guide marks parts of the chatter as work in progress at the time it was written (the form node and storage exist; some panels such as attachments, scheduled messages and activities are described as not built yet). Check the pages below for the current state before promising a feature to the user.

## Not covered here

Field tracking (`tracking.md`), attachments in the chatter (`attachments.md`), the client message store (`messaging-store.md`, `store-topic.md`, `store-wire.md`), the thread component (`mail-thread-view.md`).

## Sources

- docs/addon-guide/mail.md
- docs/addon-guide/human-form-layout.md
- docs/addon-guide/mail-thread-view.md
- addons/mail/manifest.toml
- addons/mail/Cargo.toml
- addons/mail/tests/chatter_guide.rs
- addons/mail/tests/activity.rs

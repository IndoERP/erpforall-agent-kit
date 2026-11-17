---
name: erpforall-attachments
description: Attach files to records from a native ERPForAll addon with the base attachments API (erp_addon_base::attachments) - staged uploads, create and create_unique, composer files claimed with adopt, for_record and open, the /erp/content/<id> route, reattach, copy, unlink with the record, who may see a file, the attachment size setting and the errors you will meet. Use when an addon must store, list, serve or move files that belong to a record.
---

# Attachments on records

`ir.attachment` holds the metadata (name, parent record, type, URL, checksum, size, media type); the bytes are a blob
addressed by its SHA-256 in a store all nodes share, so identical files are stored once per database. An addon uses
the functions of `erp_addon_base::attachments` (a **native** addon: depend on `erp-addon-base`). Never write SQL
against the attachment tables and never touch a file path. For a file that is a field value, see the binary and image
fields page (`binary-image-fields.md`).

## Attach inside your transaction

```rust
use erp_addon_base::attachments::{self, AttachmentContent, NewAttachment, ParentRef, UploadId};
use erp_sdk::prelude::*;

async fn attach(tx: &mut Transaction, partner: i64, upload: UploadId) -> Result<()> {
    let ids = attachments::create(tx, vec![
        NewAttachment::new("contract.pdf", AttachmentContent::Upload(upload))        // staged, any size
            .on(ParentRef::new("res.partner", partner)),
        NewAttachment::new("note.txt", AttachmentContent::Bytes(b"hello".to_vec()))  // up to the inline threshold
            .on(ParentRef::new("res.partner", partner)),
        NewAttachment::new("site", AttachmentContent::Url("https://example.com".to_owned())),
    ]).await?;
    assert_eq!(ids.len(), 3);
    Ok(())
}
```

- `create` checks write access to every parent record (once per model) and links the content. A rolled-back
  transaction leaves a staged upload usable again. `create_unique` reuses an attachment of the same content and type
  the caller may write, else creates one.
- Bytes above the inline threshold (2 KiB by default) must be staged first: a caller that holds the ORM streams them
  with `Uploader::new(orm).stage(env, reader, StageRequest::named("contract.pdf").declared("application/pdf"))`. The
  staged id is bound to the user, expires in 24 hours and links once. A declared type that does not match the
  detected content is refused.

## Composer files: claim them with `adopt`

A chatter composer uploads before the message exists. The upload stores the file with
`NewAttachment::new(..).pending_in("mail.compose.message")` (no record id; only its creator and the system group see
it). After checking the right to post on the record, the post path claims it:

```rust
attachments::adopt(tx, &[draft_id], ParentRef::new("helpdesk.ticket", ticket),
    &["mail.compose.message"], AdoptScope::ComposerAndRecord).await?;
```

`ComposerAndRecord` (internal callers) also accepts files already on the record and then requires write access to it;
`ComposerOnly` is for portal callers. Anything else refuses the whole call with `Access` and moves nothing. A file
never claimed is removed after `attachments.composer_retention_secs` (default 24 hours). From the web client the mail
addon's `thread_upload` and `thread_post` RPCs do this for you (see `erpforall-chatter`).

## List, open, move, copy

- `attachments::for_record(tx, "res.partner", &[id], ListOptions::default())` lists what the caller may read.
- `attachments::open(tx, id)` returns a handle: size, type and checksum come first; `open(range)` streams;
  `read_to_vec(max_bytes)` refuses content above the limit. Missing bytes are an `AttachmentContentMissing` error,
  never an empty file.
- `attachments::reattach(tx, &[id], Some(ParentRef::new(..)))` moves files (needs write access on old and new parent);
  `attachments::copy` shares the blob, no byte is copied.
- Deleting a record deletes its attachments (the server composition registers `attachments::UNLINK_HOOK`).
- The browser reads a file at `GET /erp/content/<id>` (`?download=true` for a download). It needs a signed-in session
  and serves internal users only; every refusal or missing file answers `404`. Only PNG, JPEG, GIF, WebP and PDF are
  shown inline. Native code uses `attachments::content::lookup_content(tx, id)`, which runs the same check.

## Who may see a file

A file follows its record: read the parent to read it, write the parent to create, change or delete it; a field-bound
file also needs access to that field. A standalone file belongs to its creator and the system group. Until the
compiled parent-access rule exists, generic `search`/`read` of `ir.attachment` shows internal users only their own
files: use `for_record` and `open` for the record view. The service writes rows as superuser after its checks, so an
override of `ir.attachment` `create`/`write` must check values, not the environment.

## Size setting

`base.attachment_max_bytes` is a database-wide setting (Settings, Base: "Maximum attachment size (bytes)", also a
system parameter): default 134217728 bytes, bounds 1 to 2147483647; empty resets to the default. Change it through
Settings or the checked parameter API, never by writing the tables.

## Not covered here

Binary fields stored as attachments, public or token links, `/web/image` paths and scanning or encryption (not built
yet); the streaming HTTP upload route (planned); the store's operation and the ownership and cleanup primitives for
native maintenance code: read `attachments.md`. The full error table is in `attachments.md`, "Errors you will meet".

## Sources

- docs/addon-guide/attachments.md
- docs/addon-guide/mail.md
- addons/base/src/attachments/service.rs
- addons/base/src/attachments/types.rs
- addons/base/src/attachments/content.rs
- addons/base/data/ir_config_parameter_data.xml
- addons/base/security/ir.access.csv
- addons/mail/src/post.rs

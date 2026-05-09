# Phase 2 — saas-platform: Extend Chat API to Accept Attachments

You are working on saas-platform at ~/Workspace/saas-platform.
Read CLAUDE.md before starting. Follow all conventions there exactly.

---

## Context

Phase 1 is complete. The following now exist and work:
- `Attachment` and `MessageAttachment` models in `app/models.py`
- `POST /api/v1/attachments` — uploads a file, returns `attachment_id`
- `GET /api/v1/attachments/<id>` — downloads a file

This phase extends `POST /api/v1/chat/messages` to accept `attachment_ids`,
load the associated files, and pass them to Azure OpenAI — images as vision
content blocks, documents as prepended markdown context.

File to modify: `app/routes/api_v1.py`

---

## Step 1 — Add helper: _load_attachments_for_message()

```python
def _load_attachments_for_message(api_key_id: int, attachment_ids: list) -> list:
    """
    Load and validate attachments by ID. Returns only Attachment objects
    that belong to this api_key. Silently skips IDs not found or not owned
    (logs a warning for each skip). Never raises.
    """
```

Implementation:
- Query `Attachment.query.filter(Attachment.id.in_(attachment_ids), Attachment.api_key_id == api_key_id).all()`
- Log a warning for any ID in `attachment_ids` that was not returned
- Return the list of valid `Attachment` objects

---

## Step 2 — Add helper: _build_openai_content_with_attachments()

```python
def _build_openai_content_with_attachments(
    message_text: str,
    attachments: list,
    upload_folder: str,
) -> list | str:
    """
    Build the `content` value for the current user turn in the Azure OpenAI
    messages array, enriched with attachment data.

    Returns a plain string if there are no image attachments.
    Returns a content array if any image attachments are present.
    """
```

Rules:
- **No attachments**: return `message_text` unchanged (plain string)
- **Document attachments only**: prepend each document's markdown to the message text, then return as a plain string:
  ```
  [Attached: {filename}]

  {content_md}

  ---

  {message_text}
  ```
  If `content_md` is `None` or empty, use: `[Attached: {filename} — content not available]\n\n`
- **Any image attachments**: return a content array:
  ```python
  [
    {"type": "text", "text": "<prepended doc context + message_text>"},
    {"type": "image_url", "image_url": {"url": "data:<mime_type>;base64,<b64_data>"}},
    # ... one entry per image
  ]
  ```
- Image file path: `{upload_folder}/attachments/{attachment.api_key_id}/{attachment.id}/{attachment.stored_filename}`
- If an image file cannot be read (missing, permission error, etc.): log a warning and skip that image block — do not raise
- Base64 encode using `base64.b64encode(file_bytes).decode("utf-8")`

---

## Step 3 — Modify one_shot_message()

In the `one_shot_message` function in `api_v1.py`, make the following changes:

### 3a. Parse attachment_ids from request data

Add after the existing field parsing (after `user_full_name`):

```python
raw_att_ids    = data.get("attachment_ids") or []
if not isinstance(raw_att_ids, list):
    raw_att_ids = []
attachment_ids = [int(x) for x in raw_att_ids if str(x).isdigit()][:5]  # max 5
```

### 3b. Load attachments after saving the user message

After `db.session.add(user_msg)` and `db.session.commit()`, add:

```python
attachments = []
if attachment_ids:
    attachments = _load_attachments_for_message(g.api_key.id, attachment_ids)
```

### 3c. Build enriched content for the current user turn

Before calling `_build_messages()`, compute:

```python
from flask import current_app
enriched_content = (
    _build_openai_content_with_attachments(
        message, attachments, current_app.config["UPLOAD_FOLDER"]
    )
    if attachments else message
)
```

After `_build_messages()` returns `messages_data`, replace the content of the
**last user message** in the array with `enriched_content`:

```python
for i in range(len(messages_data) - 1, -1, -1):
    if messages_data[i]["role"] == "user":
        messages_data[i]["content"] = enriched_content
        break
```

This ensures only the current turn is enriched — historical messages stay as plain text.

### 3d. Link attachments to the saved messages

After `db.session.add(assist_msg)`, before the final `db.session.commit()`, add:

```python
for att in attachments:
    db.session.add(MessageAttachment(
        message_id=user_msg.id,
        attachment_id=att.id,
    ))
    if not att.conversation_id:
        att.conversation_id = conv.id
```

### 3e. Add attachments to the JSON response

In the final `return jsonify({...})`, add:

```python
"attachments": [
    {
        "id":       a.id,
        "filename": a.original_filename,
        "category": a.file_category,
        "mime_type": a.mime_type,
    }
    for a in attachments
],
```

---

## Step 4 — Vision model warning

When `attachments` contains any image-category items, check whether the model's
`deployment_name` contains `"gpt-4"` or `"gpt-4o"` (case-insensitive). If not,
log a warning:

```python
log.warning(
    "Vision attachment sent to model '%s' which may not support vision. "
    "Azure may return an error.", model.deployment_name
)
```

Do NOT block the request — let Azure return its own error if the model is unsupported.

---

## Done when

- `POST /api/v1/chat/messages` with no `attachment_ids` behaves identically to before
- `POST` with a PDF `attachment_id` → AI response references the document content
- `POST` with an image `attachment_id` → the Azure payload contains an `image_url` content block
- `POST` with an `attachment_id` belonging to a different API key → that attachment is silently skipped, request succeeds
- `MessageAttachment` rows are created in the DB after each call with attachments

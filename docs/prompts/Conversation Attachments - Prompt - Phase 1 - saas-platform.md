# Phase 1 — saas-platform: Attachment Storage & Upload API

You are working on saas-platform, a Flask + SQLAlchemy + SQLite app at ~/Workspace/saas-platform.
Read CLAUDE.md before starting. Follow all conventions there exactly.

---

## Context

This is Phase 1 of a 5-phase feature: adding file attachment support to AI chat.
The goal of this phase is to receive and store a file, extract its text as markdown,
and return an `attachment_id`. No changes to the chat flow yet.

---

## Step 1 — New models in app/models.py

Add two new models AFTER the existing `Message` model:

```python
class Attachment(db.Model):
    """A file uploaded by an API client to accompany a chat message."""
    __tablename__ = "attachment"

    id                = db.Column(db.Integer, primary_key=True)
    api_key_id        = db.Column(db.Integer, db.ForeignKey("api_key.id"), nullable=False)
    conversation_id   = db.Column(db.Integer, db.ForeignKey("conversation.id"), nullable=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename   = db.Column(db.String(255), nullable=False)
    mime_type         = db.Column(db.String(100), nullable=False)
    file_size_bytes   = db.Column(db.Integer, nullable=True)
    file_category     = db.Column(db.String(20), nullable=False)  # 'image' | 'document'
    content_md        = db.Column(db.Text, nullable=True)
    content_md_status = db.Column(db.String(20), nullable=False, default="pending")
                                                                   # pending | done | failed
    created_at        = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    api_key      = db.relationship("ApiKey", backref=db.backref("attachments", lazy="dynamic"))
    conversation = db.relationship("Conversation", backref=db.backref("attachments", lazy="dynamic"))


class MessageAttachment(db.Model):
    """Associates an Attachment with the Message it was sent in."""
    __tablename__ = "message_attachment"

    id            = db.Column(db.Integer, primary_key=True)
    message_id    = db.Column(db.Integer, db.ForeignKey("message.id"), nullable=False)
    attachment_id = db.Column(db.Integer, db.ForeignKey("attachment.id"), nullable=False)

    message    = db.relationship("Message", backref=db.backref("message_attachments", lazy="dynamic"))
    attachment = db.relationship("Attachment", backref=db.backref("message_attachments", lazy="dynamic"))
```

---

## Step 2 — Run migration

```bash
flask db migrate -m "add attachment and message_attachment tables"
flask db upgrade
```

---

## Step 3 — Create app/services/attachment_converter.py

Create this new file. Implement two functions:

### `classify_file(filename: str, mime_type: str) -> str`

Returns `"image"` or `"document"`:
- `"image"` if mime_type starts with `"image/"` OR extension is in `{jpg, jpeg, png, gif, webp}`
- `"document"` otherwise

### `extract_markdown(file_path: str, mime_type: str) -> str | None`

Extracts text from a file and returns it as a markdown string. Rules:

| Format | Library | Approach |
|---|---|---|
| PDF (`.pdf`) | `pymupdf` (import fitz) | Extract text page by page, join with `"\n\n---\n\n"` |
| DOCX (`.docx`) | `python-docx` | Extract all paragraphs as text; format tables as markdown tables |
| TXT / MD | built-in | Read file as UTF-8 |
| CSV | built-in `csv` module | Read first 200 rows, format as a markdown table |
| Images / unknown | — | Return `None` |

Additional rules:
- Truncate result to 100,000 characters, appending `"\n\n[Content truncated at 100,000 characters]"` if truncated
- Catch ALL exceptions and return `None` — never raise
- If a library is not installed, catch the ImportError and return `None`

---

## Step 4 — Add two new endpoints to app/routes/api_v1.py

### POST /api/v1/attachments

```python
@api_v1_bp.route("/attachments", methods=["POST"])
@require_api_key
def upload_attachment():
```

Logic:
1. Get file from `request.files["file"]`. Return 400 if missing.
2. Validate size ≤ 20 MB (return 400 if exceeded).
3. Validate extension is in `{jpg, jpeg, png, gif, webp, pdf, docx, txt, md, csv}` (return 415 if not).
4. Sanitize filename with `werkzeug.utils.secure_filename`.
5. Classify as `"image"` or `"document"` using `classify_file()`.
6. Create an `Attachment` record, `db.session.add()` it, then `db.session.flush()` to get the ID before writing the file.
7. Store file to: `{UPLOAD_FOLDER}/attachments/{g.api_key.id}/{attachment.id}/{stored_filename}`. Use `os.makedirs(..., exist_ok=True)`.
8. Run `extract_markdown()` synchronously. Set `content_md` and `content_md_status` (`"done"` or `"failed"`). Images always get `content_md_status = "done"` with `content_md = None`.
9. `db.session.commit()`.
10. Return 201 JSON:

```json
{
  "attachment_id": 42,
  "original_filename": "deal_memo.pdf",
  "file_category": "document",
  "mime_type": "application/pdf",
  "file_size_bytes": 204800,
  "content_md_status": "done"
}
```

### GET /api/v1/attachments/\<int:attachment_id\>

```python
@api_v1_bp.route("/attachments/<int:attachment_id>", methods=["GET"])
@require_api_key
def download_attachment(attachment_id):
```

Logic:
1. Load the `Attachment`. Return 404 if not found.
2. Verify `attachment.api_key_id == g.api_key.id`. Return 404 if mismatch (don't reveal it exists).
3. Build the file path: `{UPLOAD_FOLDER}/attachments/{g.api_key.id}/{attachment_id}/{attachment.stored_filename}`.
4. Return `send_file()` with `as_attachment=True` and `download_name=attachment.original_filename`.

---

## Step 5 — Check dependencies

Inspect `requirements.txt`. Add these if missing:
- `pymupdf`
- `python-docx`

Do NOT add `markitdown` or `markdown`.

---

## Done when

- `flask db upgrade` applies cleanly with no errors
- `flask routes | grep attachment` shows both new endpoints
- A curl test uploading a PDF returns a 201 with a valid `attachment_id` and `content_md_status: "done"`
- The stored file exists on disk at the expected path

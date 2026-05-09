# PRD: Chat Attachments for Cophy.io
**Feature:** Attach images and documents to AI chat requests  
**Systems affected:** saas-platform (skunkBOX API), saas-mortgage (Cophy.io UI)  
**Author:** Dmitry Chechuy  
**Date:** 2026-05-08  
**Status:** Draft

---

## 1. Problem Statement

Loan officers using Cophy.io frequently need to share supporting materials with the AI — rate sheets, appraisal summaries, deal memos, client emails, screenshots — the same way they share files in ChatGPT. Today they can only paste text. This forces them to manually copy-paste content, strips document formatting and context, and creates friction that reduces adoption.

---

## 2. Goal

Enable users to attach images and documents directly to AI chat messages in Cophy.io, identical in feel to ChatGPT's attachment flow. Attachments must be:
- Uploaded and stored durably (downloadable from chat history later)
- Converted to markdown so their content can be injected into the AI conversation context
- Passed to Azure OpenAI in the format it expects (vision content blocks for images; text context for documents)

---

## 3. User Stories

**US-1.** As a loan officer, I can click a paperclip icon in the chat input, select a file (image or PDF/DOCX/TXT), and attach it to my message before sending — exactly like ChatGPT.

**US-2.** As a loan officer, I can see a preview chip of my attachment (thumbnail for images, filename icon for documents) before I send, and I can remove it.

**US-3.** As a loan officer, when I send a message with an attachment, the AI can "see" the file content and respond to questions about it.

**US-4.** As a loan officer, I can scroll back through a past conversation and download any attachment that was shared.

**US-5.** As a loan officer, I can attach multiple files to a single message.

---

## 4. Out of Scope (v1)

- Drag-and-drop upload (clipboard paste or button only)
- Attachment sharing across conversations
- Admin UI to browse/delete all user attachments
- Quota management / per-user storage limits (defer to v2)
- Video files
- Editable/annotatable documents

---

## 5. Supported File Types

| Category | Extensions | AI Treatment |
|---|---|---|
| Images | jpg, jpeg, png, gif, webp | Passed as vision content blocks to Azure OpenAI |
| Documents | pdf, docx, txt, md, csv | Converted to Markdown; injected into message context |

---

## 6. Architecture Overview

```
User browser (saas-mortgage)
        │
        │ 1. POST /agents/<conv_id>/attachments   (multipart)
        │    → upload file to skunkBOX, get attachment_id
        │
        │ 2. POST /agents/<conv_id>/send
        │    { message: "...", attachment_ids: [42, 43] }
        │
saas-mortgage (Flask)
        │
        │ 3. POST /api/v1/chat/messages
        │    { persona_id, session_id, message, attachment_ids: [42, 43] }
        │
skunkBOX API (saas-platform)
        │
        │ 4. Load attachments from DB
        │    - Images → base64 → OpenAI vision content block
        │    - Docs   → content_md → injected as context text
        │
        │ 5. Call Azure OpenAI with enriched messages array
        │
        └─→ Return response + rag_sources
```

---

## 7. Data Models

### 7.1 saas-platform — New `Attachment` table

```python
class Attachment(db.Model):
    __tablename__ = "attachment"
    id                = db.Column(db.Integer, primary_key=True)
    api_key_id        = db.Column(db.Integer, db.ForeignKey("api_key.id"), nullable=False)
    conversation_id   = db.Column(db.Integer, db.ForeignKey("conversation.id"), nullable=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename   = db.Column(db.String(255), nullable=False)
    mime_type         = db.Column(db.String(100), nullable=False)
    file_size_bytes   = db.Column(db.Integer, nullable=True)
    file_category     = db.Column(db.String(20), nullable=False)  # 'image' | 'document'
    content_md        = db.Column(db.Text, nullable=True)          # markdown extracted from doc
    content_md_status = db.Column(db.String(20), nullable=False, default="pending")
                                                                   # pending | done | failed
    created_at        = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
```

Storage path: `{UPLOAD_FOLDER}/attachments/{api_key_id}/{attachment_id}/{stored_filename}`

### 7.2 saas-platform — New `MessageAttachment` join table

```python
class MessageAttachment(db.Model):
    __tablename__ = "message_attachment"
    id            = db.Column(db.Integer, primary_key=True)
    message_id    = db.Column(db.Integer, db.ForeignKey("message.id"), nullable=False)
    attachment_id = db.Column(db.Integer, db.ForeignKey("attachment.id"), nullable=False)
```

### 7.3 saas-mortgage — New `MessageAttachment` table (local mirror)

```python
class MessageAttachment(db.Model):
    __tablename__ = "message_attachment"
    id                = db.Column(db.Integer, primary_key=True)
    message_id        = db.Column(db.Integer, db.ForeignKey("agent_message.id"), nullable=False)
    skunkbox_attachment_id = db.Column(db.Integer, nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    mime_type         = db.Column(db.String(100), nullable=False)
    file_category     = db.Column(db.String(20), nullable=False)  # 'image' | 'document'
    file_size_bytes   = db.Column(db.Integer, nullable=True)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
```

---

## 8. API Changes

### 8.1 saas-platform — New endpoint: Upload Attachment

```
POST /api/v1/attachments
Content-Type: multipart/form-data
X-API-Key: <key>

Fields:
  file          (required)  binary file data
  conversation_id (optional) int — associate with existing conversation

Response 201:
{
  "attachment_id": 42,
  "original_filename": "deal_memo.pdf",
  "file_category": "image" | "document",
  "mime_type": "application/pdf",
  "file_size_bytes": 204800,
  "content_md_status": "pending" | "done"
}
```

### 8.2 saas-platform — Modified: POST /api/v1/chat/messages

Add optional field:
```json
{
  "persona_id": 1,
  "session_id": "abc",
  "message": "What's the LTV on this deal?",
  "attachment_ids": [42, 43]
}
```

When `attachment_ids` is present:
- **Images**: build `content` as an array — `[{"type":"text","text":"<message>"},{"type":"image_url","image_url":{"url":"data:<mime>;base64,<b64>"}}]`
- **Documents**: prepend the attachment's `content_md` to the user message text before building the messages array: `"[Attached: {filename}]\n\n{content_md}\n\n---\n\n{message}"`

### 8.3 saas-platform — New endpoint: Get Attachment

```
GET /api/v1/attachments/<id>
X-API-Key: <key>

Response 200: raw file (send_file)
```

### 8.4 saas-mortgage — New endpoint: Upload Attachment (proxy)

```
POST /agents/<conv_id>/attachments
Content-Type: multipart/form-data

Fields:
  file    (required)

Response 200:
{
  "ok": true,
  "attachment_id": 42,
  "original_filename": "deal_memo.pdf",
  "file_category": "image" | "document",
  "mime_type": "application/pdf",
  "file_size_bytes": 204800
}
```

### 8.5 saas-mortgage — Modified: POST /agents/<conv_id>/send

Extend the JSON body:
```json
{
  "message": "...",
  "attachment_ids": [42, 43]
}
```

Extend the response to include attachment metadata, which is saved to `MessageAttachment`.

### 8.6 saas-mortgage — New endpoint: Download Attachment (proxy)

```
GET /agents/attachments/<skunkbox_attachment_id>/download
→ Proxy file from skunkBOX and stream to browser
```

---

## 9. Document → Markdown Conversion

Conversion runs synchronously at upload time (not background) for small files; timeout at 30s.

| Format | Library |
|---|---|
| PDF | `pymupdf` (fitz) — text extraction page by page, joined with `\n\n---\n\n` |
| DOCX | `python-docx` — paragraphs joined; tables as markdown tables |
| TXT / MD | read as-is |
| CSV | read first 200 rows, format as markdown table |

Max content_md length: 100,000 characters (truncate with notice if exceeded).

Image files: no conversion; `content_md` is null; `content_md_status` = `"done"` (images go via vision).

---

## 10. File Size Limits

| Limit | Value |
|---|---|
| Max single file | 20 MB |
| Max files per message | 5 |
| Max total per message | 50 MB |

---

## 11. Success Metrics

- Upload success rate ≥ 99%
- Document markdown extraction success rate ≥ 95%
- p95 upload + conversion latency ≤ 5 seconds for files < 5 MB
- Zero regressions on existing text-only chat flows

---

## 12. Security Considerations

- Attachments are scoped to `api_key_id` — no cross-tenant access
- Files are stored outside the web root; served only via authenticated proxy endpoint
- Filename sanitized with `werkzeug.utils.secure_filename` before storage
- MIME type validated server-side (don't trust browser Content-Type)
- File content scanned against allowed extensions list
- Max file size enforced before writing to disk

---

---

# Phase Decomposition

## Phase 1 — saas-platform: Attachment Storage & Upload API
**Scope:** Everything needed to receive and store a file, extract its text, and return an `attachment_id`. No changes to the chat flow yet.

**Deliverables:**
1. New `Attachment` and `MessageAttachment` models + migration
2. Document-to-markdown conversion utility (`app/services/attachment_converter.py`)
3. `POST /api/v1/attachments` endpoint
4. `GET /api/v1/attachments/<id>` (file download) endpoint
5. Unit tests for the converter

**Done when:** A curl command can POST a PDF and receive back an `attachment_id`, and the stored `content_md` contains the document's text.

---

## Phase 2 — saas-platform: Extend Chat API to Accept Attachments
**Scope:** Modify `one_shot_message` in `api_v1.py` to accept `attachment_ids`, load attachments, and enrich the Azure OpenAI call with image vision blocks or document context.

**Deliverables:**
1. Load attachments by ID + validate ownership in `one_shot_message`
2. `_build_messages_with_attachments()` — extends `_build_messages()` to handle vision content arrays for images and prepend markdown for documents
3. Link attachments to the saved `Message` via `MessageAttachment` join table
4. Return `attachments` array in API response (id, filename, category)
5. Manual test: POST a message + image → confirm Azure receives vision block; POST a message + PDF → confirm markdown is prepended

**Done when:** Postman test sending `attachment_ids: [<id>]` alongside a message returns a valid AI response that references the file content.

---

## Phase 3 — saas-mortgage: Upload Proxy & Local Storage
**Scope:** Add the upload endpoint in saas-mortgage that forwards files to skunkBOX and saves attachment metadata locally.

**Deliverables:**
1. New `MessageAttachment` model + migration in saas-mortgage
2. `POST /agents/<conv_id>/attachments` route — validates file, proxies to `POST /api/v1/attachments`, saves metadata to `MessageAttachment`
3. `GET /agents/attachments/<id>/download` — proxies download from skunkBOX
4. Helper `_upload_attachment_to_skunkbox(integration, file)` in `agents.py`

**Done when:** A file posted to the saas-mortgage endpoint appears in the skunkBOX DB and the local `message_attachment` table.

---

## Phase 4 — saas-mortgage: Chat UI — Attach & Send
**Scope:** Update the chat UI so users can pick files, see preview chips, and send with attachments.

**Deliverables:**
1. Paperclip icon button next to the chat input
2. Hidden `<input type="file">` triggered by the button (accept: image/*, .pdf, .docx, .txt, .csv, .md)
3. On file pick: AJAX upload to `/agents/<conv_id>/attachments`, show chip (thumbnail for images, filename for docs), store `attachment_id` in JS state
4. On send: include `attachment_ids: [...]` in the existing AJAX JSON body
5. Extend `send_message` route to forward `attachment_ids` to skunkBOX, save `MessageAttachment` rows
6. Chip UI: spinner during upload → file icon/thumbnail when done → × to remove
7. Error handling: file too large, upload failed, wrong type

**Done when:** End-to-end test — attach a PDF + type a question → AI responds with content from the PDF.

---

## Phase 5 — saas-mortgage: Display Attachments in Chat History
**Scope:** Render attachment chips in past messages so users can see and download files.

**Deliverables:**
1. Load `MessageAttachment` rows when rendering `view_conversation`
2. Pass `attachments_by_message_id` dict to template
3. Render attachment chips in chat bubbles — image thumbnail (from download proxy) for images, file icon + name for docs
4. Clicking a chip triggers download via `/agents/attachments/<id>/download`
5. Handle gracefully if skunkBOX file is no longer available

**Done when:** Reload a past conversation with attachments — chips render correctly and are downloadable.

---

---

# Claude Code Prompts

---

## PROMPT 1 — saas-platform: Attachment Storage & Upload API

```
You are working on saas-platform, a Flask + SQLAlchemy + SQLite app at ~/Workspace/saas-platform.
Read CLAUDE.md before starting. Follow all conventions there exactly.

## Task: Implement attachment upload and storage (Phase 1)

### 1. New models in app/models.py

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

### 2. Create migration
```bash
flask db migrate -m "add attachment and message_attachment tables"
flask db upgrade
```

### 3. Create app/services/attachment_converter.py

Implement a function `extract_markdown(file_path: str, mime_type: str) -> str | None` that:
- PDF (.pdf, application/pdf): uses `pymupdf` (import fitz). Extract text from each page. Join pages with "\n\n---\n\n". If pymupdf not installed, fall back gracefully.
- DOCX (.docx, application/vnd.openxmlformats...): uses `python-docx`. Extract all paragraphs as text. Format tables as markdown tables. Join with newlines.
- TXT / MD: read the file as UTF-8 text.
- CSV: read first 200 rows with Python csv module, format as a markdown table (header row + data rows).
- Images and unknown types: return None.
- Truncate result to 100,000 characters, appending "\n\n[Content truncated at 100,000 characters]" if truncated.
- Catch ALL exceptions and return None (never raise).

Also add a helper `classify_file(filename: str, mime_type: str) -> str` that returns "image" or "document":
- image if mime_type starts with "image/" OR extension is in {jpg,jpeg,png,gif,webp}
- document otherwise

### 4. New endpoint in app/routes/api_v1.py

Add `POST /api/v1/attachments`:

```
@api_v1_bp.route("/attachments", methods=["POST"])
@require_api_key
def upload_attachment():
```

Logic:
- Get file from request.files["file"]. Return 400 if missing.
- Validate: size <= 20 MB (return 400 if exceeded), extension in {jpg,jpeg,png,gif,webp,pdf,docx,txt,md,csv} (return 415 if not).
- Sanitize filename with werkzeug.utils.secure_filename.
- Classify as "image" or "document" using classify_file().
- Store to: {current_app.config["UPLOAD_FOLDER"]}/attachments/{g.api_key.id}/<new_attachment_id>/<stored_filename>
  - To get the ID before writing: flush after db.session.add(attachment)
  - mkdir -p the directory
- Extract markdown synchronously using extract_markdown(). Set content_md and content_md_status accordingly ("done" or "failed").
- Commit.
- Return 201 JSON: {attachment_id, original_filename, file_category, mime_type, file_size_bytes, content_md_status}

Add `GET /api/v1/attachments/<int:attachment_id>`:
- Validate ownership: attachment.api_key_id == g.api_key.id. Return 404 if not found or wrong owner.
- send_file() the stored file as_attachment=True with download_name=original_filename.

### 5. Install dependencies if not already present
Check requirements.txt. Add if missing: pymupdf, python-docx. Do not install markdown or markitdown.

### 6. Config
In config.py, ensure UPLOAD_FOLDER is set (it already exists for documents). The attachments will use a subfolder of it — no new config key needed.

After all changes:
- Run flask db upgrade to confirm migration applies cleanly.
- Confirm the two new endpoints are registered: flask routes | grep attachment
```

---

## PROMPT 2 — saas-platform: Extend Chat API for Attachments

```
You are working on saas-platform at ~/Workspace/saas-platform.
Read CLAUDE.md. Phase 1 is complete: the Attachment model, MessageAttachment model, and
POST/GET /api/v1/attachments endpoints exist and work.

## Task: Extend one_shot_message to accept attachment_ids (Phase 2)

File to modify: app/routes/api_v1.py

### Step 1: Add a helper function _load_attachments_for_message()

```python
def _load_attachments_for_message(api_key_id: int, attachment_ids: list) -> tuple[list, list]:
    """
    Load and validate attachments. Returns (valid_attachments, error_messages).
    valid_attachments is a list of Attachment objects that belong to this api_key.
    Silently skips IDs not found or not owned — logs a warning.
    """
```

### Step 2: Add a helper function _build_openai_content_with_attachments()

```python
def _build_openai_content_with_attachments(message_text: str, attachments: list) -> list | str:
    """
    Given a user message and a list of Attachment objects, return the `content`
    value to pass to Azure OpenAI.

    Rules:
    - If no attachments: return message_text as a plain string (existing behavior).
    - If any images present: return a content array:
        [
          {"type": "text", "text": "<prepended_doc_context + message_text>"},
          {"type": "image_url", "image_url": {"url": "data:<mime>;base64,<b64>"}},
          ... (one entry per image)
        ]
    - Document attachments: prepend their content_md to the text part.
      Format: "[Attached: {filename}]\n\n{content_md}\n\n---\n\n"
      If content_md is None or empty, just prepend "[Attached: {filename} — content not available]\n\n"
    - Images with no content_md: encode the file to base64 and add as image_url block.
    - Read image files from disk using the stored path: {UPLOAD_FOLDER}/attachments/{api_key_id}/{attachment_id}/{stored_filename}
    - If image file read fails: log warning and skip the image block (don't crash the request).
    - If only documents (no images): return the enriched text as a plain string, not an array.
    """
```

### Step 3: Modify one_shot_message()

In the `one_shot_message` function:

1. Parse `attachment_ids` from request data:
   ```python
   attachment_ids = data.get("attachment_ids") or []
   if not isinstance(attachment_ids, list):
       attachment_ids = []
   attachment_ids = [int(x) for x in attachment_ids if str(x).isdigit()][:5]  # max 5
   ```

2. After saving the user message but before the RAG search, load attachments:
   ```python
   attachments = []
   if attachment_ids:
       attachments, _ = _load_attachments_for_message(g.api_key.id, attachment_ids)
   ```

3. Modify `_build_messages()` call: pass the enriched content.
   - Build the enriched user content BEFORE calling `_build_messages`:
     ```python
     enriched_message = _build_openai_content_with_attachments(message, attachments) if attachments else message
     ```
   - In `_build_messages()`, wherever `m.content` is used for the user message, use `enriched_message` instead for the CURRENT user turn only. The simplest approach: if `enriched_message != message`, replace the last user message's content in `messages_data` after `_build_messages()` returns.

   IMPORTANT: Only replace the content for the current message being sent, not historical messages.

4. After saving the assistant message, link attachments:
   ```python
   for att in attachments:
       db.session.add(MessageAttachment(message_id=user_msg.id, attachment_id=att.id))
       att.conversation_id = conv.id
   db.session.commit()
   ```

5. Add `attachments` to the JSON response:
   ```python
   "attachments": [
       {"id": a.id, "filename": a.original_filename, "category": a.file_category}
       for a in attachments
   ]
   ```

### Step 4: Verify Azure OpenAI model supports vision

When attachments contain images, the Azure OpenAI model must support vision.
Add a check: if any image attachments exist and the model's deployment_name does not contain "gpt-4" or "gpt-4o" (case-insensitive), log a warning but proceed anyway (don't block the request — let Azure return an error if unsupported).

### Testing checklist (manual, document in a comment at the top of the function)
1. POST /api/v1/chat/messages with no attachment_ids → existing behavior unchanged
2. POST with attachment_ids containing a PDF → AI response references the document content
3. POST with attachment_ids containing an image → content array includes image_url block
4. POST with an attachment_id belonging to a different api_key → that attachment is silently skipped
```

---

## PROMPT 3 — saas-mortgage: Upload Proxy & Local Storage

```
You are working on saas-mortgage (Cophy.io) at ~/Workspace/saas-mortgage.
Read CLAUDE.md. The saas-platform skunkBOX API now supports:
  POST /api/v1/attachments  (multipart, returns {attachment_id, original_filename, file_category, mime_type, file_size_bytes})
  GET  /api/v1/attachments/<id>  (file download)

## Task: Add attachment upload proxy and local storage (Phase 3)

### Step 1: New model in app/models.py

Add after AgentMessage:

```python
class MessageAttachment(db.Model):
    """Local mirror of attachment metadata for chat history display."""
    __tablename__ = "message_attachment"

    id                     = db.Column(db.Integer, primary_key=True)
    message_id             = db.Column(db.Integer, db.ForeignKey("agent_message.id"), nullable=False)
    skunkbox_attachment_id = db.Column(db.Integer, nullable=False)
    original_filename      = db.Column(db.String(255), nullable=False)
    mime_type              = db.Column(db.String(100), nullable=False)
    file_category          = db.Column(db.String(20), nullable=False)  # 'image' | 'document'
    file_size_bytes        = db.Column(db.Integer, nullable=True)
    created_at             = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    message = db.relationship("AgentMessage", backref=db.backref("attachments", lazy="dynamic"))
```

Run: flask db migrate -m "add message_attachment table" && flask db upgrade

### Step 2: Add helper in app/routes/agents.py

```python
_ALLOWED_ATTACH_EXTENSIONS = {"jpg","jpeg","png","gif","webp","pdf","docx","txt","md","csv"}
_MAX_ATTACH_BYTES = 20 * 1024 * 1024  # 20 MB

def _upload_attachment_to_skunkbox(integration, file_storage) -> dict:
    """
    Upload a werkzeug FileStorage object to skunkBOX.
    Returns the parsed JSON response dict.
    Raises ValueError on validation errors.
    Raises requests.HTTPError on API errors.
    """
    filename = file_storage.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_ATTACH_EXTENSIONS:
        raise ValueError(f"File type .{ext} is not allowed.")
    
    file_bytes = file_storage.read()
    if len(file_bytes) > _MAX_ATTACH_BYTES:
        raise ValueError("File exceeds the 20 MB limit.")
    
    base_url = (integration.base_url or "").rstrip("/")
    if base_url.endswith("/api/v1"):
        base_url = base_url[:-len("/api/v1")]
    api_key = decrypt_value(integration.api_key_encrypted or "")
    
    resp = http_requests.post(
        f"{base_url}/api/v1/attachments",
        files={"file": (filename, file_bytes, file_storage.content_type or "application/octet-stream")},
        headers={"X-API-Key": api_key},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()
```

### Step 3: New route POST /agents/<conv_id>/attachments

```python
@agents_bp.route("/<int:conversation_id>/attachments", methods=["POST"])
@login_required
@permission_required("agents", "view")
def upload_attachment(conversation_id):
    conv = db.get_or_404(AgentConversation, conversation_id)
    if conv.user_id != current_user.id:
        return jsonify({"ok": False, "error": "Forbidden"}), 403
    
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "No file provided."}), 400
    
    agent = conv.agent
    if not agent or not agent.is_active:
        return jsonify({"ok": False, "error": "Agent not available."}), 400
    
    try:
        result = _upload_attachment_to_skunkbox(agent.integration, file)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"Upload failed: {e}"}), 502
    
    return jsonify({
        "ok": True,
        "attachment_id": result["attachment_id"],
        "original_filename": result["original_filename"],
        "file_category": result["file_category"],
        "mime_type": result["mime_type"],
        "file_size_bytes": result.get("file_size_bytes"),
    })
```

### Step 4: New route GET /agents/attachments/<id>/download

Add a SEPARATE route (not nested under conversation_id) for simplicity:

```python
@agents_bp.route("/attachments/<int:skunkbox_attachment_id>/download")
@login_required
@permission_required("agents", "view")
def download_attachment(skunkbox_attachment_id):
    """
    Proxy a file download from skunkBOX. Verify the attachment belongs to a
    conversation owned by the current user before proxying.
    """
    # Security: verify the current user owns a conversation that has this attachment
    from ..models import MessageAttachment
    att_record = (MessageAttachment.query
                  .join(AgentMessage, AgentMessage.id == MessageAttachment.message_id)
                  .join(AgentConversation, AgentConversation.id == AgentMessage.conversation_id)
                  .filter(
                      MessageAttachment.skunkbox_attachment_id == skunkbox_attachment_id,
                      AgentConversation.user_id == current_user.id,
                  )
                  .first())
    if not att_record:
        abort(404)
    
    # Get the integration from the conversation's agent
    msg = db.session.get(AgentMessage, att_record.message_id)
    conv = db.session.get(AgentConversation, msg.conversation_id)
    integration = conv.agent.integration
    
    base_url = (integration.base_url or "").rstrip("/")
    if base_url.endswith("/api/v1"):
        base_url = base_url[:-len("/api/v1")]
    api_key = decrypt_value(integration.api_key_encrypted or "")
    
    try:
        resp = http_requests.get(
            f"{base_url}/api/v1/attachments/{skunkbox_attachment_id}",
            headers={"X-API-Key": api_key},
            timeout=60,
            stream=True,
        )
        resp.raise_for_status()
        content_disposition = f'attachment; filename="{att_record.original_filename}"'
        return Response(
            stream_with_context(resp.iter_content(chunk_size=8192)),
            content_type=resp.headers.get("Content-Type", "application/octet-stream"),
            headers={"Content-Disposition": content_disposition},
        )
    except Exception as e:
        abort(502)
```

### Step 5: Extend send_message to accept and forward attachment_ids

In the existing `send_message` route, parse `attachment_ids` from the JSON body:
```python
attachment_ids = data.get("attachment_ids") or []
if not isinstance(attachment_ids, list):
    attachment_ids = []
attachment_ids = [int(x) for x in attachment_ids if str(x).isdigit()][:5]
```

Pass `attachment_ids` to `_call_skunkbox()` by adding it to the payload dict:
```python
payload = {
    "persona_id": skunkbox_agent_id,
    "session_id": session_id,
    "user_full_name": user_full_name,
    "username": username,
    "message": message,
}
if attachment_ids:
    payload["attachment_ids"] = attachment_ids
```

After saving the assistant message, save local attachment records:
```python
# attachment_metadata is passed from the caller or returned in result
for att_meta in (data.get("attachment_metadata") or []):
    db.session.add(MessageAttachment(
        message_id=user_msg.id,
        skunkbox_attachment_id=att_meta["attachment_id"],
        original_filename=att_meta["original_filename"],
        mime_type=att_meta["mime_type"],
        file_category=att_meta["file_category"],
        file_size_bytes=att_meta.get("file_size_bytes"),
    ))
db.session.commit()
```

The `attachment_metadata` list is now sent by the frontend in the AJAX request alongside `attachment_ids`.

Return `attachment_ids` in the send_message response so the frontend can confirm.
```

---

## PROMPT 4 — saas-mortgage: Chat UI — Attach & Send

```
You are working on saas-mortgage (Cophy.io) at ~/Workspace/saas-mortgage.
Read CLAUDE.md and docs/DESIGN_SYSTEM.md.
Phases 1–3 are complete. The backend routes exist:
  POST /agents/<conv_id>/attachments  → {ok, attachment_id, original_filename, file_category, mime_type, file_size_bytes}
  POST /agents/<conv_id>/send        → now accepts attachment_ids + attachment_metadata in JSON body

## Task: Update the chat UI (Phase 4)

File to modify: app/templates/agents/conversation.html

### What to add

1. **Paperclip button** — placed to the LEFT of the send button, inside the chat input row.
   Use the existing Tabler icon `<i class="ti ti-paperclip"></i>`.
   Use CSS vars for colors: `var(--accent)` on hover. Button is `type="button"` (never submit).

2. **Hidden file input** — `<input type="file" id="attach-file-input" multiple accept="image/*,.pdf,.docx,.txt,.csv,.md" style="display:none">`. Max 5 files. Clicking the paperclip triggers this input's click().

3. **Attachment chips area** — a `<div id="attachment-chips">` rendered ABOVE the text input. Hidden when empty. Each chip shows:
   - For images: a small 40×40 thumbnail (object-fit:cover, border-radius:4px) using a FileReader preview
   - For documents: a file icon `<i class="ti ti-file-text"></i>` + filename (truncated to 24 chars)
   - A remove × button on each chip
   - A spinner during upload (replace with icon when done)

4. **JS state** — maintain `pendingAttachments` array: `[{attachment_id, original_filename, file_category, mime_type, file_size_bytes}]`

5. **Upload flow** — on file selection:
   - For each selected file: show chip with spinner immediately
   - POST to `/agents/{{ conv.id }}/attachments` using FormData
   - On success: update chip to show real content, push to pendingAttachments
   - On error: show red chip with error message + × to dismiss

6. **Send flow** — modify the existing `sendMessage()` function:
   - Add `attachment_ids` (array of ints from pendingAttachments) to the JSON body
   - Add `attachment_metadata` (array of full attachment objects) to the JSON body
   - After successful send: clear `pendingAttachments` and clear chip area

7. **Disable send while uploads in progress** — track `uploadsInProgress` counter. Disable send button while > 0.

8. **File validation client-side** (belt + suspenders):
   - Reject files > 20 MB before uploading (show inline error chip)
   - Reject more than 5 files total

### CSS — add inside the existing <style> block or at bottom of template

```css
#attachment-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 0 4px;
}
.attach-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 8px;
  background: var(--panel-muted);
  border: 1px solid var(--border);
  font-size: 13px;
  color: var(--text);
  max-width: 200px;
}
.attach-chip img {
  width: 36px;
  height: 36px;
  object-fit: cover;
  border-radius: 4px;
  flex-shrink: 0;
}
.attach-chip .chip-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.attach-chip .chip-remove {
  cursor: pointer;
  color: var(--muted);
  flex-shrink: 0;
}
.attach-chip .chip-remove:hover {
  color: var(--danger-text);
}
.attach-chip.upload-error {
  border-color: var(--danger-text);
  background: var(--danger-bg);
  color: var(--danger-text);
}
```

### Important constraints
- Do NOT break the existing text-only send flow. `attachment_ids` should be an empty array [] when no attachments.
- Do NOT add new <script src> tags — keep all JS inline in the existing <script> block.
- Follow existing JS patterns in the file — use the same fetch() style, same error handling.
- Use CSS vars throughout — never hardcode colors.
- Keep the chip area invisible (display:none on #attachment-chips) until at least one attachment is pending.
```

---

## PROMPT 5 — saas-mortgage: Display Attachments in Chat History

```
You are working on saas-mortgage (Cophy.io) at ~/Workspace/saas-mortgage.
Read CLAUDE.md and docs/DESIGN_SYSTEM.md.
All previous phases are complete. The MessageAttachment model exists and is populated.

## Task: Render attachments in past chat messages (Phase 5)

### Step 1: Update view_conversation route in app/routes/agents.py

Load attachment records for all messages in the conversation:

```python
from ..models import MessageAttachment

# After raw_messages is loaded:
message_ids = [m.id for m in raw_messages]
attachments_qs = MessageAttachment.query.filter(MessageAttachment.message_id.in_(message_ids)).all()
attachments_by_message_id = {}
for att in attachments_qs:
    attachments_by_message_id.setdefault(att.message_id, []).append(att)
```

Pass `attachments_by_message_id` to the template render_template call.

Also update `messages_data` (the JSON passed to JS) to include attachment info:
```python
messages_data = [
    {
        "id":          m.id,
        "role":        m.role,
        "content":     m.content,
        "rag_sources": m.rag_sources_list,
        "created_at":  m.created_at.isoformat(),
        "attachments": [
            {
                "id": a.skunkbox_attachment_id,
                "filename": a.original_filename,
                "category": a.file_category,
                "mime_type": a.mime_type,
            }
            for a in attachments_by_message_id.get(m.id, [])
        ],
    }
    for m in raw_messages
]
```

### Step 2: Update conversation.html template

In the Jinja template, where user messages are rendered, add attachment chips ABOVE the message text bubble for each message that has attachments:

```jinja2
{% set msg_attachments = attachments_by_message_id.get(m.id, []) %}
{% if msg_attachments %}
<div class="message-attachments">
  {% for att in msg_attachments %}
  <a href="{{ url_for('agents.download_attachment', skunkbox_attachment_id=att.skunkbox_attachment_id) }}"
     class="attach-chip attach-chip-history" title="{{ att.original_filename }}" download>
    {% if att.file_category == 'image' %}
      <i class="ti ti-photo"></i>
    {% else %}
      <i class="ti ti-file-text"></i>
    {% endif %}
    <span class="chip-name">{{ (att.original_filename or '') | truncate(28, True, '…') }}</span>
    <i class="ti ti-download" style="font-size:11px;opacity:0.6"></i>
  </a>
  {% endfor %}
</div>
{% endif %}
```

Add CSS for `.attach-chip-history`:
```css
.attach-chip-history {
  text-decoration: none;
  color: var(--text);
}
.attach-chip-history:hover {
  background: var(--panel);
  border-color: var(--accent);
  color: var(--accent);
}
```

### Step 3: Handle gracefully when skunkBOX file is unavailable

The download endpoint already returns 502 if skunkBOX fails. No template change needed.
In the download_attachment route: catch the exception and return a plain 404 with a user-friendly message instead of 502.

### Step 4: JS — render attachments for dynamically-added messages

In the existing JS `addMessage()` function (which renders new messages after sending), add attachment chip rendering. When `msg.attachments` array is non-empty, prepend chips to the message bubble using the same HTML structure as the Jinja template above.

Build download URLs: `/agents/attachments/<id>/download`

### Final verification checklist
- Load a conversation with no attachments → no visual change
- Load a conversation with image attachments → photo icon chips rendered
- Load a conversation with document attachments → file icon chips rendered
- Click a chip → file downloads
- Send a new message with an attachment → chip appears immediately in the new message bubble
```

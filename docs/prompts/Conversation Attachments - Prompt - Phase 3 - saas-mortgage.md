# Phase 3 — saas-mortgage: Upload Proxy & Local Storage

You are working on saas-mortgage (Cophy.io) at ~/Workspace/saas-mortgage.
Read CLAUDE.md before starting. Follow all conventions there exactly.

---

## Context

Phases 1 and 2 are complete on saas-platform. The skunkBOX API now supports:
- `POST /api/v1/attachments` — multipart upload, returns `{attachment_id, original_filename, file_category, mime_type, file_size_bytes}`
- `GET /api/v1/attachments/<id>` — authenticated file download

This phase adds the upload proxy and local metadata storage to saas-mortgage.
Cophy.io stores NO files — only metadata. All files live on skunkBOX.

---

## Step 1 — New model in app/models.py

Add this model after `AgentMessage`:

```python
class MessageAttachment(db.Model):
    """Local mirror of attachment metadata for chat history display.
    The actual file lives on skunkBOX — we store only what we need to render chips."""
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

Run migration:
```bash
flask db migrate -m "add message_attachment table"
flask db upgrade
```

---

## Step 2 — Add helper in app/routes/agents.py

Add these constants near the top of agents.py (after existing constants):

```python
_ALLOWED_ATTACH_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "pdf", "docx", "txt", "md", "csv"}
_MAX_ATTACH_BYTES = 20 * 1024 * 1024  # 20 MB
```

Add this helper function:

```python
def _upload_attachment_to_skunkbox(integration, file_storage) -> dict:
    """
    Upload a werkzeug FileStorage object to skunkBOX POST /api/v1/attachments.
    Returns the parsed JSON response dict on success.
    Raises ValueError for validation errors (bad extension, too large).
    Raises requests.HTTPError for API errors.
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

---

## Step 3 — New route: POST /agents/\<conv_id\>/attachments

Add to agents_bp:

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
        "attachment_id":    result["attachment_id"],
        "original_filename": result["original_filename"],
        "file_category":    result["file_category"],
        "mime_type":        result["mime_type"],
        "file_size_bytes":  result.get("file_size_bytes"),
    })
```

---

## Step 4 — New route: GET /agents/attachments/\<id\>/download

Add this route to agents_bp (note: NOT nested under conversation_id):

```python
@agents_bp.route("/attachments/<int:skunkbox_attachment_id>/download")
@login_required
@permission_required("agents", "view")
def download_attachment(skunkbox_attachment_id):
    """
    Proxy a file download from skunkBOX.
    Security: verify the current user owns a conversation containing this attachment.
    """
    from ..models import MessageAttachment

    # Ownership check: the attachment must be linked to a message in one of this user's conversations
    att_record = (
        MessageAttachment.query
        .join(AgentMessage, AgentMessage.id == MessageAttachment.message_id)
        .join(AgentConversation, AgentConversation.id == AgentMessage.conversation_id)
        .filter(
            MessageAttachment.skunkbox_attachment_id == skunkbox_attachment_id,
            AgentConversation.user_id == current_user.id,
        )
        .first()
    )
    if not att_record:
        abort(404)

    # Get the integration via the conversation's agent
    msg  = db.session.get(AgentMessage, att_record.message_id)
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
    except Exception:
        abort(404)
```

---

## Step 5 — Extend send_message to forward attachment_ids

In the existing `send_message` route, after parsing `content` from request JSON, also parse:

```python
raw_att_ids     = data.get("attachment_ids") or []
attachment_ids  = [int(x) for x in raw_att_ids if str(x).isdigit()][:5]
attachment_meta = data.get("attachment_metadata") or []  # list of dicts from frontend
```

In `_call_skunkbox()`, extend the payload dict to include `attachment_ids` when present:

```python
payload = {
    "persona_id":      skunkbox_agent_id,
    "session_id":      session_id,
    "user_full_name":  user_full_name,
    "username":        username,
    "message":         message,
}
if attachment_ids:
    payload["attachment_ids"] = attachment_ids
```

After saving the `assistant_msg` to the DB, save local `MessageAttachment` records
using the metadata the frontend sent:

```python
from ..models import MessageAttachment as MsgAtt
for meta in attachment_meta:
    try:
        db.session.add(MsgAtt(
            message_id             = user_msg.id,
            skunkbox_attachment_id = int(meta["attachment_id"]),
            original_filename      = meta["original_filename"],
            mime_type              = meta["mime_type"],
            file_category          = meta["file_category"],
            file_size_bytes        = meta.get("file_size_bytes"),
        ))
    except (KeyError, ValueError):
        pass  # skip malformed entries
db.session.commit()
```

---

## Done when

- `flask db upgrade` applies the new migration cleanly
- `flask routes | grep attachment` shows both new routes
- Posting a file to `/agents/<conv_id>/attachments` returns a valid `attachment_id`
- The corresponding `MessageAttachment` row is created after a `send` call with `attachment_metadata`
- Hitting `/agents/attachments/<id>/download` for an attachment owned by the current user streams the file from skunkBOX
- Hitting the same URL for an attachment NOT owned by the current user returns 404

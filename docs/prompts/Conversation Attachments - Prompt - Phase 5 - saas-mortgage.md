# Phase 5 — saas-mortgage: Display Attachments in Chat History

You are working on saas-mortgage (Cophy.io) at ~/Workspace/saas-mortgage.
Read CLAUDE.md and docs/DESIGN_SYSTEM.md before starting.

---

## Context

All previous phases are complete:
- `MessageAttachment` model exists and is populated when messages are sent with attachments
- `/agents/attachments/<id>/download` proxy route exists
- The chat UI (Phase 4) renders chips for NEW messages as they are sent

This phase makes those chips appear when loading a past conversation,
and ensures dynamically-added messages (rendered by JS after sending) also show chips.

---

## Step 1 — Update view_conversation route in app/routes/agents.py

In the `view_conversation` function, after `raw_messages` is loaded, fetch all
attachment records for the messages in this conversation:

```python
from ..models import MessageAttachment

message_ids = [m.id for m in raw_messages]
attachments_by_message_id = {}
if message_ids:
    att_records = MessageAttachment.query.filter(
        MessageAttachment.message_id.in_(message_ids)
    ).all()
    for att in att_records:
        attachments_by_message_id.setdefault(att.message_id, []).append(att)
```

Pass this dict to the template:

```python
return render_template(
    "agents/conversation.html",
    conv=conv,
    agent=conv.agent,
    messages=raw_messages,
    messages_data=messages_data,
    attachments_by_message_id=attachments_by_message_id,   # ← add this
    breadcrumbs=[...],
)
```

Also extend `messages_data` (the JSON passed to JS) to include attachment info
for each message. Find where `messages_data` is built and add an `"attachments"` key:

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
                "id":       a.skunkbox_attachment_id,
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

---

## Step 2 — Render attachment chips in the Jinja template

File: `app/templates/agents/conversation.html`

Read the full template first. Find the section where the loop over messages renders
each message bubble. Inside that loop, for EACH message (both user and assistant),
add attachment chips ABOVE the message text content:

```jinja2
{% set msg_attachments = attachments_by_message_id.get(m.id, []) %}
{% if msg_attachments %}
<div class="message-attachments-history" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px;">
  {% for att in msg_attachments %}
  <a href="{{ url_for('agents.download_attachment', skunkbox_attachment_id=att.skunkbox_attachment_id) }}"
     class="attach-chip attach-chip-history"
     title="{{ att.original_filename }}"
     download="{{ att.original_filename }}">
    {% if att.file_category == 'image' %}
      <span class="chip-icon"><i class="ti ti-photo"></i></span>
    {% else %}
      <span class="chip-icon"><i class="ti ti-file-text"></i></span>
    {% endif %}
    <span class="chip-name">{{ (att.original_filename or '') | truncate(28, True, '…') }}</span>
    <span style="font-size:11px;opacity:0.5;flex-shrink:0;"><i class="ti ti-download"></i></span>
  </a>
  {% endfor %}
</div>
{% endif %}
```

Add CSS for `.attach-chip-history` to the existing `<style>` block:

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

---

## Step 3 — Fix the download route error handling

In `app/routes/agents.py`, find the `download_attachment` route added in Phase 3.
The final `except` block currently calls `abort(502)`. Change it to `abort(404)`.

This means a missing skunkBOX file shows a clean "not found" rather than a server error.

---

## Step 4 — JS: render attachment chips for dynamically-added messages

In the existing `<script>` block, find the function that renders a new message bubble
after the user sends one (it typically calls something like `appendMessage()` or
`addMessageToChat()`). 

Extend that function to render attachment chips when `msg.attachments` is non-empty.
Before rendering the message text content, prepend the chips HTML:

```javascript
function buildAttachmentChipsHtml(attachments) {
  if (!attachments || attachments.length === 0) return '';
  const chips = attachments.map(att => {
    const icon = att.category === 'image' ? 'ti-photo' : 'ti-file-text';
    const name = att.filename.length > 28 ? att.filename.slice(0, 27) + '…' : att.filename;
    const url  = `/agents/attachments/${att.id}/download`;
    return `
      <a href="${url}" class="attach-chip attach-chip-history"
         title="${att.filename}" download="${att.filename}">
        <span class="chip-icon"><i class="ti ${icon}"></i></span>
        <span class="chip-name">${name}</span>
        <span style="font-size:11px;opacity:0.5;"><i class="ti ti-download"></i></span>
      </a>`;
  }).join('');
  return `<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px;">${chips}</div>`;
}
```

Call this function when building the new user message bubble HTML, using the
`pendingAttachments` data (available just before they are cleared after send):

```javascript
// Capture before clearing
const sentAttachments = pendingAttachments.map(a => ({
  id:       a.attachment_id,
  filename: a.original_filename,
  category: a.file_category,
}));

// ... after successful send response, when building the user bubble:
const chipsHtml = buildAttachmentChipsHtml(sentAttachments);
// prepend chipsHtml to the message bubble content
```

For assistant messages returned in the response, use `data.assistant.attachments` if
present (it will be an empty array in most cases since attachments belong to user turns).

---

## Final verification checklist

Run through each scenario manually before committing:

1. **Past conversation, no attachments** — loads normally, no visual change
2. **Past conversation, image attachment** — photo icon chip renders above the message; clicking downloads the file
3. **Past conversation, document attachment** — file icon chip renders; clicking downloads
4. **Past conversation, attachment file deleted from skunkBOX** — chip renders but clicking returns a 404 (not a 502)
5. **Send new message with attachment** — chip appears immediately in the new user bubble
6. **Send text-only message** — no chips, no visual change, existing behavior intact
7. **Reload page after sending** — chips still visible in message history (loaded from DB)

---

## After completing all 5 phases

Update `CHANGELOG.md` at the top (below the `# Changelog` header):

```
## [2026-05-XX] - add chat attachment support
- Added MessageAttachment model and migration
- Added POST /agents/<conv_id>/attachments upload proxy route
- Added GET /agents/attachments/<id>/download proxy route
- Extended send_message to forward attachment_ids to skunkBOX
- Added paperclip button and chip UI to chat interface
- Attachments now render in chat history with download links
```

Then commit:
```bash
git add -A && git commit -m "add chat attachment support — phases 3-5"
git push
```

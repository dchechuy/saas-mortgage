# Phase 4 — saas-mortgage: Chat UI — Attach & Send

You are working on saas-mortgage (Cophy.io) at ~/Workspace/saas-mortgage.
Read CLAUDE.md and docs/DESIGN_SYSTEM.md before starting.

---

## Context

Phases 1–3 are complete. These backend routes now exist:
- `POST /agents/<conv_id>/attachments` → `{ok, attachment_id, original_filename, file_category, mime_type, file_size_bytes}`
- `POST /agents/<conv_id>/send` → now accepts `attachment_ids` (list of ints) and `attachment_metadata` (list of dicts) in the JSON body

This phase updates the chat interface so users can attach files before sending.

---

## File to modify

`app/templates/agents/conversation.html`

Read the full file before making any changes so you understand the existing structure,
JS functions, and CSS conventions in use.

---

## What to add

### 1. Paperclip button

Place a paperclip button to the LEFT of the existing send button, inside the chat input row.

```html
<button type="button" id="attach-btn" title="Attach a file"
        style="background:none;border:none;cursor:pointer;padding:6px 8px;color:var(--muted);">
  <i class="ti ti-paperclip" style="font-size:18px;"></i>
</button>
```

On hover, color changes to `var(--accent)`. Add this CSS to the existing `<style>` block:

```css
#attach-btn:hover { color: var(--accent); }
```

### 2. Hidden file input

Place directly after the paperclip button (outside any form elements):

```html
<input type="file" id="attach-file-input" multiple
       accept="image/*,.pdf,.docx,.txt,.csv,.md"
       style="display:none;">
```

### 3. Attachment chips area

Place this `<div>` ABOVE the chat input row (not inside the input row):

```html
<div id="attachment-chips" style="display:none; flex-wrap:wrap; gap:8px; padding:8px 0 4px;">
</div>
```

### 4. CSS — add to existing `<style>` block

```css
.attach-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px 4px 6px;
  border-radius: 8px;
  background: var(--panel-muted);
  border: 1px solid var(--border);
  font-size: 13px;
  color: var(--text);
  max-width: 220px;
}
.attach-chip img.chip-thumb {
  width: 36px;
  height: 36px;
  object-fit: cover;
  border-radius: 4px;
  flex-shrink: 0;
}
.attach-chip .chip-icon {
  font-size: 18px;
  color: var(--accent);
  flex-shrink: 0;
}
.attach-chip .chip-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.attach-chip .chip-remove {
  cursor: pointer;
  color: var(--muted);
  flex-shrink: 0;
  font-size: 14px;
  margin-left: 2px;
}
.attach-chip .chip-remove:hover { color: var(--danger-text); }
.attach-chip.upload-error {
  border-color: var(--danger-text);
  background: var(--danger-bg);
  color: var(--danger-text);
}
```

---

## JavaScript — add to existing `<script>` block

Add these variables and functions. Do NOT create new `<script>` tags.
Follow the exact same `fetch()` style and error handling already used in the file.

### State variables (add near the top of the script section)

```javascript
let pendingAttachments = [];   // [{attachment_id, original_filename, file_category, mime_type, file_size_bytes}]
let uploadsInProgress  = 0;
```

### Wire up file picker

```javascript
document.getElementById('attach-btn').addEventListener('click', () => {
  document.getElementById('attach-file-input').click();
});

document.getElementById('attach-file-input').addEventListener('change', function() {
  const files = Array.from(this.files);
  // Check total count
  if (pendingAttachments.length + files.length > 5) {
    alert('You can attach a maximum of 5 files per message.');
    this.value = '';
    return;
  }
  files.forEach(file => handleFileSelected(file));
  this.value = ''; // reset so same file can be re-added after removal
});
```

### handleFileSelected(file)

```javascript
function handleFileSelected(file) {
  const MAX_BYTES = 20 * 1024 * 1024;
  const ALLOWED_EXT = ['jpg','jpeg','png','gif','webp','pdf','docx','txt','md','csv'];
  const ext = (file.name.split('.').pop() || '').toLowerCase();

  // Client-side validation
  if (!ALLOWED_EXT.includes(ext)) {
    showErrorChip(file.name, `File type .${ext} is not allowed.`);
    return;
  }
  if (file.size > MAX_BYTES) {
    showErrorChip(file.name, 'File exceeds 20 MB limit.');
    return;
  }

  const chipId = 'chip-' + Date.now() + '-' + Math.random().toString(36).slice(2);
  const isImage = file.type.startsWith('image/');

  // Show spinner chip immediately
  const chip = document.createElement('div');
  chip.className = 'attach-chip';
  chip.id = chipId;
  chip.innerHTML = `
    <span class="chip-icon"><i class="ti ti-loader-2" style="animation:spin 1s linear infinite;"></i></span>
    <span class="chip-name">${truncate(file.name, 24)}</span>
  `;
  document.getElementById('attachment-chips').appendChild(chip);
  document.getElementById('attachment-chips').style.display = 'flex';

  // If image, generate a local preview for the thumbnail
  let previewDataUrl = null;
  const doUpload = () => {
    uploadsInProgress++;
    updateSendButton();

    const formData = new FormData();
    formData.append('file', file);

    const convId = {{ conv.id }};
    fetch(`/agents/${convId}/attachments`, {
      method: 'POST',
      body: formData,
    })
    .then(r => r.json())
    .then(data => {
      uploadsInProgress--;
      if (data.ok) {
        pendingAttachments.push({
          attachment_id:    data.attachment_id,
          original_filename: data.original_filename,
          file_category:    data.file_category,
          mime_type:        data.mime_type,
          file_size_bytes:  data.file_size_bytes,
        });
        // Update chip to final state
        const finalChip = document.getElementById(chipId);
        if (finalChip) {
          if (isImage && previewDataUrl) {
            finalChip.innerHTML = `
              <img class="chip-thumb" src="${previewDataUrl}" alt="">
              <span class="chip-name">${truncate(data.original_filename, 20)}</span>
              <span class="chip-remove" data-id="${data.attachment_id}" title="Remove">×</span>
            `;
          } else {
            finalChip.innerHTML = `
              <span class="chip-icon"><i class="ti ti-file-text"></i></span>
              <span class="chip-name">${truncate(data.original_filename, 20)}</span>
              <span class="chip-remove" data-id="${data.attachment_id}" title="Remove">×</span>
            `;
          }
          finalChip.querySelector('.chip-remove').addEventListener('click', () => {
            removeAttachment(data.attachment_id, chipId);
          });
        }
      } else {
        showErrorChip(file.name, data.error || 'Upload failed.', chipId);
      }
      updateSendButton();
    })
    .catch(err => {
      uploadsInProgress--;
      showErrorChip(file.name, 'Upload failed.', chipId);
      updateSendButton();
    });
  };

  if (isImage) {
    const reader = new FileReader();
    reader.onload = e => { previewDataUrl = e.target.result; doUpload(); };
    reader.readAsDataURL(file);
  } else {
    doUpload();
  }
}
```

### Helper functions

```javascript
function truncate(str, n) {
  return str.length > n ? str.slice(0, n - 1) + '…' : str;
}

function showErrorChip(filename, message, existingChipId) {
  const chipId = existingChipId || ('chip-err-' + Date.now());
  let chip = existingChipId ? document.getElementById(existingChipId) : null;
  if (!chip) {
    chip = document.createElement('div');
    chip.id = chipId;
    document.getElementById('attachment-chips').appendChild(chip);
    document.getElementById('attachment-chips').style.display = 'flex';
  }
  chip.className = 'attach-chip upload-error';
  chip.innerHTML = `
    <span class="chip-icon"><i class="ti ti-alert-circle"></i></span>
    <span class="chip-name" title="${message}">${truncate(filename, 16)}: ${truncate(message, 20)}</span>
    <span class="chip-remove" title="Dismiss">×</span>
  `;
  chip.querySelector('.chip-remove').addEventListener('click', () => chip.remove());
  updateChipsVisibility();
}

function removeAttachment(attachmentId, chipId) {
  pendingAttachments = pendingAttachments.filter(a => a.attachment_id !== attachmentId);
  const chip = document.getElementById(chipId);
  if (chip) chip.remove();
  updateChipsVisibility();
}

function updateChipsVisibility() {
  const area = document.getElementById('attachment-chips');
  area.style.display = area.children.length > 0 ? 'flex' : 'none';
}

function updateSendButton() {
  const btn = document.getElementById('send-btn'); // use the actual ID of the send button
  if (btn) btn.disabled = uploadsInProgress > 0;
}
```

Add a spin keyframe if not already present in the `<style>` block:
```css
@keyframes spin { to { transform: rotate(360deg); } }
```

### Modify the existing sendMessage() function

Find the existing `sendMessage()` (or equivalent) function that builds the JSON body
and posts to `/agents/<conv_id>/send`. Make these two changes:

1. Add `attachment_ids` and `attachment_metadata` to the request body:

```javascript
const body = {
  message: messageText,
  attachment_ids:    pendingAttachments.map(a => a.attachment_id),
  attachment_metadata: pendingAttachments,  // full objects for server-side DB storage
};
```

2. After a successful send response, clear the pending attachments:

```javascript
pendingAttachments = [];
document.getElementById('attachment-chips').innerHTML = '';
updateChipsVisibility();
```

---

## Constraints

- Do NOT break the existing text-only send flow. `attachment_ids` must be `[]` (not `null`) when no files are attached.
- Do NOT add new `<script src>` tags.
- Do NOT hardcode any colors — use CSS variables throughout.
- Use the actual ID of the send button as it exists in the current template.
- Keep all JavaScript inside the existing `<script>` block.

---

## Done when

- Clicking the paperclip opens the file picker
- Selecting a PDF shows a file-icon chip with a spinner, then resolves to filename chip
- Selecting an image shows a spinner chip, then resolves to a thumbnail chip
- Clicking × on a chip removes it and clears the `pendingAttachments` entry
- Selecting more than 5 files shows an alert and does nothing
- Selecting a file > 20 MB shows an error chip immediately (no upload attempted)
- Sending a message with attachments includes `attachment_ids` in the request body
- After sending, the chip area clears
- Sending a message with NO attachments still works exactly as before

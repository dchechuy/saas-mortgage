# User Manual

## Overview
This SaaS platform provides a web-based interface to interact with AI Agents, manage team accounts, configure system settings (models, integrations, feature flags, agents), and review usage and activity reports. It’s intended to help teams chat with AI agents, teach agents with documents, control access, and monitor platform activity.

Who can use what is controlled by Roles & Permissions. If you do not see a page or button, ask your administrator to grant the appropriate permission.

The platform is multi-tenant: one deployment can host Cofficiency (the
internal workspace) plus any number of customer tenants, with each tenant's
users, agents, models, integrations, conversations, and reports fully
isolated from the others. See "Tenant Switcher & Tenant Administration"
below for what this means day-to-day.

---

## Sections

### Tenant Switcher & Tenant Administration
**Purpose:**
Let Cofficiency staff work across customer tenant workspaces without a
separate account per customer, while keeping every tenant's data isolated
from the others.

**Who can use it:**
- The tenant **switcher** (in the header, left of your avatar) is visible
  only to users whose home tenant is Cofficiency. External (customer) users
  never see it — their account is permanently scoped to their own tenant.
- **Tenant administration** (creating, renaming, archiving, and reactivating
  tenants) is restricted to Cofficiency users with the admin role.

**How to use it:**
1. Click the tenant switcher in the header to see a dropdown of every active
   tenant, with your current selection checked.
2. Pick a tenant to make it your active workspace. Every tenant-owned page —
   Users, System Config (models/attributes/integrations/agents/feature
   flags), Conversations, Learning Center, Dashboard, and Reporting — now
   shows only that tenant's data.
3. Your selection is remembered (`last_active_tenant_id`) and restored the
   next time you log in, even in a new browser session.
4. Cofficiency admins manage tenants from "Administration → Tenant
   Management": create a tenant (a URL-safe slug is generated from the
   name automatically), edit its name, or archive/reactivate it. Archived
   tenants disappear from the switcher and can't receive new users or
   records. The protected Cofficiency tenant itself can never be renamed or
   archived.

**Key features / things to know:**
- Switching tenants changes *what you're looking at*, never *what you're
  allowed to do* — your role's page permissions apply identically in every
  tenant.
- A new user is always created in whichever tenant is currently active —
  there is no tenant field on the Add User form, and no route lets anyone
  change an existing user's tenant afterward.
- Actions you take are attributed to the tenant that was active *at the
  time*, not to your own home tenant. If you (as a Cofficiency user) create
  an agent while Customer A is active, that action shows up in Customer A's
  activity log, not Cofficiency's — even though you remain a Cofficiency
  user throughout.
- User Documentation and Release Notes are shared across every tenant and
  don't change when you switch.

---

### Dashboard
**Purpose:**  
A quick summary view of your active tenant workspace — counts and recent
release notes so you can see high-level status at a glance.

**Who can use it:**  
Users who have permission to view the Dashboard (Admins and any user granted the "Dashboard" view permission).

**How to use it:**
1. Log into the platform.
2. From the main navigation, select "Dashboard".
3. Review the summary statistics and the list of recent release notes.

**Key features:**
- Summary counts for **your active tenant only**: users, AI models,
  integrations, and attributes. Switching tenants changes these numbers.
- Roles and Release Notes counts are **global** (shared across every
  tenant) and labeled as such on their cards — they don't change when you
  switch tenants.
- Quick breadcrumb navigation back to Home or other sections.

---

### AI Agents — Conversations (chat with AI agents, view message history)
**Purpose:**  
Start conversations with AI agents, send messages, attach files, and review conversation history and transcripts.

**Who can use it:**  
All users who have the "Agents" view permission. Administrators can control who has access.

**How to use it:**
1. Open the "AI Agents" or "Conversations" page from the main menu.
2. To start a new conversation:
   - Choose an AI Agent persona from the list.
   - Click "Start Conversation" or "New Conversation".
3. Type your message into the chat input and press Send.
4. To include a file:
   - Click the attachment/upload button in the chat.
   - Select a file (allowed types and limits below).
   - Upload and send the message. The system will upload the file to the configured document/attachment service and include it in the message.
5. View message history:
   - Select an existing conversation to open its full message thread.
   - Scroll through past messages. Messages are shown in chronological order and show who sent them (user or agent).
6. To end or navigate away, use the back or conversations list links.

**Key features:**
- Real-time chat with AI agents (may stream responses from an external AI service).
- Conversation history and transcript viewing.
- File attachments supported in chats.
- Session handling and user attribution (messages show your user name).
- Activity logging for all chat actions (visible to admins in Reporting).

Notes on attachments:
- Allowed attachments: jpg, jpeg, png, gif, webp, pdf, docx, txt, md, csv.
- Max file size: 20 MB per file.
- Attachments are uploaded to the configured external attachments service; any errors will be reported.

---

### AI Agents — Learning Center (browse and preview documents)
**Purpose:**  
Provide a place to browse and preview documents that the AI Agents can learn from or use as references.

**Who can use it:**  
Users with the Documents/Learning Center permission or who have access to AI Agents. Administrators configure document integrations.

**How to use it:**
1. Navigate to "AI Agents" → "Learning Center" (or "Documents").
2. Browse available documents; documents are paginated (default page size around 25).
3. To preview a document:
   - Click the document title or preview action.
   - A preview viewer will open showing the document contents or summary.
4. Use the pagination controls to move between pages of documents.
5. If enabled, you may be able to upload documents (check for an Upload button). Uploaded files must meet the attachment rules.

**Key features:**
- Document browsing with pagination (documents per page ~25).
- Document preview (view content before using or indexing).
- Integration with an external Documents service (Documents integration must be active).
- Documents can be used to teach or enrich AI Agents.

---

### Reporting (activity logs, usage metrics)
**Purpose:**  
Provide administrators with detailed reports and logs about system activity, AI model requests, user actions, and external API calls.

**Who can use it:**  
Administrators only (the Reporting area requires admin privileges).

**How to use it:**
1. From the main menu, select "Reporting".
2. Choose the tab you need (dashboard/LLM Requests/User Activity/External API Requests).
3. Set the date range using the date_from and date_to selectors (defaults to the last 30 days).
4. Apply filters available in each tab:
   - LLM Requests: filter by model, use case.
   - User Activity: filter by user and specific action types.
   - External API Requests: filter by integration.
5. Use pagination to browse large result sets (results display in pages).
6. Review the summary statistics shown at the top of each tab, such as:
   - Total requests, error counts, error rate.
   - Average latency (milliseconds).
   - Total tokens used (LLM requests).
   - Top actions and counts (User Activity).
7. Drill into individual log rows for details where available.

**Key features:**
- LLM Requests analytics: counts, errors, error rate, average latency, total tokens, paginated logs.
- User Activity logs: total activity, active users, top actions, paginated logs.
- External API Request logs: counts, errors, average latency, and per-integration logs.
- Date range filters, pagination, and per-tab filters for focused analysis.
- Admin-only access ensures sensitive logs are secure.
- **Every tab reflects your active tenant only** — logs, totals, error rates,
  averages, and filter dropdowns (models/users/integrations) all scope to
  whichever tenant you currently have selected. A Cofficiency admin sees a
  different Reporting page for each tenant they switch into.
- Activity is attributed to the tenant it happened *in*, not the actor's home
  tenant — if a Cofficiency user performed an action while Customer A was
  active, it appears in Customer A's activity log.

---

### System Config — Users (manage team accounts)
**Purpose:**  
Manage user accounts: list users, add new users, edit existing users, and change passwords.

**Who can use it:**  
Administrators or users with the User Management permission (view/edit).

**How to use it:**
1. Open "System Config" → "User Management" or go to the Users page.
2. To view users:
   - The Users list displays all accounts and shows role-based counts.
3. To add a user:
   - Click "Add User".
   - Fill in Username, Email, Password, and select a Role.
   - Optionally add first and last name.
   - Click "Create" or "Save".
   - If any required field is missing or invalid, the system will show an error message.
4. To edit a user:
   - From the users list click "Edit" next to the user's name.
   - Update Username, Email, Role, names, or enter a new password to reset it.
   - If you set a new password for the user, the system records that they no longer must change the default password (if applicable).
   - Save changes.
5. To change your own password:
   - Click "Change Password" in your account settings.
   - Enter current password and new password twice to confirm.
   - Submit to update your password.
6. Avatar upload:
   - When editing or creating a user, you can upload an avatar image.
   - Allowed avatar file types: jpg, jpeg, png, gif, webp.
   - The system will save avatars to the configured agent avatar folder.

**Key features:**
- Full user listing with role counts.
- Add and edit user accounts with role assignment.
- Password set/reset and forced password-change handling.
- Avatar uploads (image types only).
- Activity logging on create/update actions.

Tips and rules:
- Username and email must be unique **across the whole platform**, not just
  within a tenant — login identity is global even though everything else
  about a user is tenant-scoped.
- Required fields for creation: username, email, password.
- If a user's account is inactive, they cannot log in.
- The users list only ever shows the active tenant's users — switching
  tenants shows a different list. A new user is always assigned to whichever
  tenant is currently active; there's no tenant field to fill in or change.
- A user's tenant is fixed permanently at creation. No edit screen or route
  can move a user to a different tenant afterward — that requires a
  deliberate database migration by an engineer, not an admin action.

---

### System Config — Roles & Permissions (access control)
**Purpose:**  
Create and manage roles, and set page-level permissions so you control which users can see or perform actions on each section.

**Who can use it:**  
Administrators or users with the Permissions management permission. Deleting system roles requires a full admin.

**How to use it:**
1. Go to "System Config" → "Roles & Permissions" (often under User Management or a dedicated Permissions area).
2. To add a role:
   - Click "Add Role".
   - Enter a role name (lowercase, unique).
   - The system will create the role and initialize permissions to "no_access" for all pages.
3. To edit role permissions:
   - Open the role to edit.
   - Change the role name if needed (the system will update existing users assigned to that role).
   - For each page, select the access level (e.g., no_access, view, edit — actual levels depend on your system).
   - Save changes.
4. To delete a role:
   - Click "Delete" for the role.
   - You cannot delete protected/system roles.
   - You must first reassign or remove users assigned to the role before deleting.
   - Only admins can delete roles in most configurations.
5. Notes on protected roles:
   - System-protected roles cannot be edited or deleted.

**Key features:**
- Create new custom roles with a single action.
- Configure page-level permission access for each role.
- Rename roles and bulk-updates users who had the old role name.
- Safe deletion: prevents deleting protected roles or roles with assigned users.

Best practices:
- Use descriptive role names (example: support, analyst, viewer).
- Keep at least one admin account separate from everyday roles.

Note: Roles and permissions are **global** — the same role templates and
permission levels apply in every tenant, and there's no way to define a
tenant-specific role. Switching your active tenant never changes what your
role permits.

---

### System Config — Models (AI model configuration)
**Purpose:**  
Manage AI (LLM) models used by the platform and configure related system pieces such as attributes, sections, and documentation prompts.

**Who can use it:**  
Administrators or users granted the Models view/edit permission.

**How to use it:**
1. Open "System Config" → "LLM Models" or "Models".
2. The Models page shows:
   - List of configured LLM models.
   - Attributes, integrations, AI agents, and feature flags (visibility depends on permissions).
   - Navigation/Sections configuration and available doc prompts.
3. To add a new model:
   - Use the "Add Model" form (name and required fields).
   - Submit to create the model.
4. To toggle a feature flag related to models:
   - Use the toggle control (checkbox) next to a feature flag.
   - Save or submit; toggling is performed via a toggle action.
5. To manage attributes, agent avatars, or doc prompts, use their respective panels on this page (if you have permission).

**Key features:**
- List, add, and configure LLM models.
- View and manage related items: attributes, integrations, AI agents.
- Access to feature flags relevant to models and flags.
- Sections editor for navigation items and doc prompts integration.

Notes:
- Visibility of sub-sections depends on your specific permissions (models, attributes, integrations, agents, flags).
- Models, attributes, integrations, and agents are all scoped to your active
  tenant — the lists, and any name you enter, only need to be unique within
  that tenant, so two different tenants can each have their own model named
  the same thing.
- Marking a model "default" only replaces the previous default **within the
  active tenant** — it never changes another tenant's default model.

---

### System Config — Integrations (external service connections)
**Purpose:**  
Connect and manage external services such as document stores, attachments services, or specialized AI backends required for agent conversations and Learning Center documents.

**Who can use it:**  
Administrators or users with Integrations view/edit permissions.

**How to use it:**
1. Go to "System Config" → "Integrations".
2. View the list of configured integrations (sorted by category, provider, name).
3. To add or edit an integration:
   - Choose "Add Integration" or "Edit" next to an existing integration.
   - Enter required information such as name, base URL, API key, category or provider, and specify the use case (e.g., Documents).
   - Save the integration.
4. For integrations that require an API key:
   - Store the API key in the integration settings. The platform saves encrypted keys.
5. To verify an integration is used by features:
   - Example: the Learning Center uses the first active integration with use_case="Documents".
   - Agents use configured integrations to call external chat/document APIs.

**Key features:**
- Configure and list integrations by category and provider.
- Secure storage of API keys (encrypted).
- Integration usage logs: API requests and responses are tracked in logs.
- Integrations power attachments, documents, and external agent services.

Tips:
- Ensure base URLs are complete and do not accidentally include duplicated API path segments (the platform auto-adjusts certain /api/v1 endings).
- Test integrations after saving to ensure connectivity.

---

### System Config — AI Agents (configure agent personas)
**Purpose:**  
Create and manage AI Agent personas — the “characters” or configurations that define how an AI agent should behave in conversations.

**Who can use it:**  
Administrators or users with AI Agent configuration permission.

**How to use it:**
1. Open "System Config" → "AI Agents" (often available under Models or Agents).
2. To create a new agent persona:
   - Click "Add Agent" or "Create Agent".
   - Provide a name, description, and select or upload an avatar image (see avatar rules).
   - Configure persona settings, prompts, and default behaviors (where supported).
   - Save the persona.
3. To edit an agent:
   - Click "Edit" on the agent list.
   - Update persona details, avatar, or prompts.
   - Save changes.
4. Use the persona when starting a conversation on the Conversations page; the persona influences how the agent responds.

**Key features:**
- Create custom agent personas with name, description, and avatar.
- Upload avatar images: allowed image extensions are .jpg, .jpeg, .png, .gif, .webp.
- Associate agents with integrations (external services) and prompts.
- Manage prompts and default behaviors used in agent conversations.

Notes:
- Avatar images are stored in a dedicated upload folder; filenames are generated for safety.
- Persona changes affect new conversations and may influence AI responses in ongoing sessions depending on how the system applies persona settings.

---

### System Config — Feature Flags (toggle features per tenant)
**Purpose:**  
Enable or disable optional platform features **for your active tenant**,
without affecting any other tenant.

**Who can use it:**  
Administrators or users with Models/Feature Flag edit permission.

**How to use it:**
1. Navigate to "System Config" → "Feature Flags".
2. The table shows, for each feature: the **global default**, and the
   **effective state for your active tenant** — marked "Inherited" (using
   the global default) or "Overridden" (this tenant has its own setting).
3. Click "Edit" and toggle the switch to set an override for the active
   tenant only. This never changes the global default or any other tenant.
4. If a tenant has an override you want to remove, click "Reset" to revert
   it to the global default (the override row is deleted, not just
   disabled).

**Key features:**
- Toggling here only ever affects the tenant you currently have active —
  it creates or updates a per-tenant override, never the shared global flag.
- A brand-new tenant needs no setup: it simply inherits every flag's global
  default until someone overrides one for it.
- A disabled feature is enforced at the page/route level, not just hidden
  from navigation — you can't reach it by typing the URL directly either.
- Activity logging for flag toggles and resets (who changed what, and for
  which tenant).

Notes:
- Feature flags may be grouped by area (e.g., Conversations, Learning Center).
- Only users with appropriate permissions can toggle flags, and only for
  whichever tenant they currently have active.

---

### User Guides / Help
**Purpose:**  
Provides help for common tasks like logging in, password changes, and navigating the platform. Also covers troubleshooting basics and where to get support.

**Who can use it:**  
All users.

**How to use it:**
1. Access the Help or User Guides section from the main navigation (often labeled "Help", "User Guides", or "Support").
2. Browse topics or search for the issue you need help with.
3. Common tasks:
   - Logging in:
     1. Go to the Login page.
     2. Enter your username and password.
     3. If your account requires a password change, you will be redirected to "Change Password".
   - Logging out:
     1. Click the logout button (may be under your profile).
     2. Confirm if prompted — you will be signed out and returned to the login page.
   - Changing passwords:
     1. Open "Change Password" from your profile or as prompted.
     2. Enter current password, new password, and confirm new password.
     3. Save to update.
   - Getting more help:
     - If your account is inactive or you cannot sign in, contact your administrator.
     - For integration issues or failed API calls, provide admin with date/time and any error messages (these are recorded in Reporting logs).
     - For role/permission requests, ask an admin to update your role or permission level.

**Key features:**
- How-to instructions for everyday operations (login/logout, password change).
- Troubleshooting guidance: check permissions, active integrations, file size/type rules.
- Links to admin-only resources (Reporting) if required for incident investigation.
- Activity logging: many actions in the platform are logged and can be reviewed by admins.

---

If you need additional help or access, contact your platform administrator. Administrators can grant the required permissions to access pages, configure integrations, or review detailed logs in the Reporting area.
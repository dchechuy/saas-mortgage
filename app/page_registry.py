ACCESS_LEVELS = ["no_access", "view", "edit"]

PAGES = [
    {"slug": "dashboard", "label": "Dashboard"},
    {"slug": "users", "label": "Users"},
    {"slug": "permissions", "label": "Permissions"},
    {"slug": "models", "label": "LLM Models"},
    {"slug": "attributes", "label": "Attributes"},
    {"slug": "integrations", "label": "Integrations"},
    {"slug": "agents", "label": "AI Agents"},
    {"slug": "reporting", "label": "Reporting"},
    {"slug": "help", "label": "Help"},
]

# Registry for nav items that can appear in the left sidebar.
# page_slug → display + routing metadata consumed by the dynamic nav in base.html.
NAV_ITEMS = {
    "conversations": {
        "label":            "Conversations",
        "icon":             "message",
        "endpoint":         "agents.list_conversations",
        "active_endpoints": ["agents.list_conversations", "agents.view_conversation",
                             "agents.new_conversation"],
        "permission_slug":  "agents",
        "feature_flag":     "conversations",
    },
    "learning_center": {
        "label":            "Learning Center",
        "icon":             "book",
        "endpoint":         "agents.learning_center",
        "active_endpoints": ["agents.learning_center", "agents.learning_center_doc"],
        "permission_slug":  "agents",
        "feature_flag":     "learning_center",
    },
    "user_management": {
        "label":            "User Management",
        "icon":             "users",
        "endpoint":         "users.list_users",
        "active_endpoints": ["users.list_users", "users.add_user",
                             "users.edit_user", "users.change_password"],
        "permission_slug":  "users",
    },
    "system_config": {
        "label":            "System Config",
        "icon":             "tags",
        "endpoint":         "models.list_models",
        "active_endpoints": ["models.list_models"],
        "permission_slug":  "attributes",
    },
    "reporting": {
        "label":            "Reporting",
        "icon":             "chart",
        "endpoint":         "reporting.index",
        "active_endpoints": ["reporting.index"],
        "permission_slug":  "reporting",
    },
    "user_guides": {
        "label":            "User Guides",
        "icon":             "help",
        "endpoint":         "help.release_notes",
        "active_endpoints": ["help.release_notes", "help.quick_start", "help.user_manual"],
        "permission_slug":  "help",
    },
    "system_overview": {
        "label":            "System Overview",
        "icon":             "brain",
        "endpoint":         "help.architecture",
        "active_endpoints": ["help.architecture", "help.dependencies"],
        "permission_slug":  "help",
        "feature_flag":     "system_overview",
    },
}


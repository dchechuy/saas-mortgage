# saas-mortgage Design System

## Foundation

`saas-mortgage` uses Tabler as the base admin UI library and then layers a local design system on top of it.

This means:

- Tabler provides layout primitives, form styling, cards, tables, and responsive behavior.
- Local CSS tokens define the durable visual identity.
- Jinja macros define repeatable UI patterns for all future SaaS projects.

## Durable rules

### 1. Use tokens, not ad-hoc colors

Always use the CSS custom properties defined in `app/static/css/style.css`. Never hardcode hex
values — that breaks dark mode.

**Full token reference:**

| Token | Light | Dark | Usage |
|---|---|---|---|
| `--text` | `#1a1a2e` | `#e5edf9` | Body text, headings |
| `--muted` | `#64748b` | `#9fb0ca` | Secondary text, labels |
| `--bg` | `#f5f6fa` | `#0f172a` | Page background |
| `--panel` | `#ffffff` | `#111827` | Cards, modals, sidebar content |
| `--panel-muted` | `#f8fafc` | `#172033` | Subtle panel backgrounds |
| `--border` | `#e2e8f0` | `#263247` | Card borders, dividers |
| `--border-soft` | `#f1f5f9` | `#1f2937` | Subtle separators |
| `--accent` | `#4361ee` | `#7aa2ff` | Links, buttons, active states |
| `--accent-strong` | `#3730a3` | `#a5bffb` | Hover/pressed accent |
| `--sidebar` | `#1a1a2e` | `#0b1220` | Sidebar background |
| `--sidebar-hover` | `#2d2d4e` | `#172033` | Sidebar item hover |
| `--sidebar-text` | `#c8cfe8` | `#d6def2` | Sidebar nav labels |
| `--sidebar-muted` | `#6f7696` | `#7b87a5` | Sidebar section headers |
| `--success-bg` | `#dcfce7` | `#10301f` | Success flash backgrounds |
| `--success-text` | `#166534` | `#86efac` | Success flash text |
| `--danger-bg` | `#fee2e2` | `#3a1517` | Error flash backgrounds |
| `--danger-text` | `#991b1b` | `#fca5a5` | Error flash text |

Example usage:
```css
.my-component {
  color: var(--text);
  background: var(--panel);
  border: 1px solid var(--border);
}
```

### 2. Favor shared macros

Use the shared macros in `app/templates/macros/ui.html` before creating page-specific markup:

- `page_header()`
- `stat_card()`
- `empty_state()`
- `icon()`

### 3. Keep the shell consistent

All future projects should preserve:

- left navigation pattern
- top page header pattern
- card-based content sections
- dense but readable admin tables
- visible empty states

### 4. Branding can move, layout should not

Project-specific work should usually customize:

- product name
- descriptive copy
- accent emphasis
- page-specific modules

Project-specific work should usually preserve:

- spacing rhythm
- component anatomy
- navigation behavior
- form styling
- table patterns

## Recommended extension pattern

When adding a new page:

1. Add the route and permission slug.
2. Start with `page_header()`.
3. Use existing card/table/form structures first.
4. Add a new macro only if the pattern will repeat across future products.


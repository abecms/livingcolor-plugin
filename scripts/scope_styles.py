#!/usr/bin/env python3
"""Generate ui/src/styles.css with delivery UI rules scoped under .lc-root."""
from __future__ import annotations

import re
from pathlib import Path

AGENT_LC_STYLES = Path(
    "/Users/tamsibesson/programmation/side-projects/agent-lc/apps/desktop/src/styles.css"
)
OUT = Path(__file__).resolve().parent.parent / "ui" / "src" / "styles.css"

PORTAL_SLOTS = (
    "dropdown-menu-content",
    "select-content",
    "dialog-content",
    "sheet-content",
    "popover-content",
    "context-menu-content",
    "tooltip-content",
)

PORTAL_SELECTORS = ", ".join(f"[data-slot='{slot}']" for slot in PORTAL_SLOTS)
ROOT_SCOPE = f".lc-root, {PORTAL_SELECTORS}"

COPY_BLOCKS = [
    (9, 71),  # @theme inline through shadow-header (omit composer shadows)
    (81, 339),
    (341, 364),
    (436, 448),
    (450, 455),
    (587, 600),  # focus reset only (exclude empty electron button rule)
    (606, 676),
    (678, 709),
    (711, 784),
]

CHAT_LINE_MARKERS = (
    "aui_",
    "data-slot='aui",
    "data-slot='composer",
    "sticky-human",
    "thinking-preview",
    "fit-text",
    "arc-border",
    "quest-glow",
    "setting-field",
    "kbd-cap",
    ".dither",
    "theme-default-filler",
    "-webkit-app-region",
)


def filter_chat_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if any(m in line for m in CHAT_LINE_MARKERS):
            continue
        if re.match(r"\s*(html|body|#root)\b", line):
            continue
        out.append(line)
    return out


def rewrite_root_selectors(text: str) -> str:
    text = text.replace(":root.dark", ".lc-root.dark")
    text = re.sub(r"(^|\n)\s*:root(?=\s*\{)", rf"\1{ROOT_SCOPE}", text)
    return text


def prefix_selector_list(selectors: str, prefix: str = ".lc-root") -> str:
    parts = [s.strip() for s in selectors.split(",") if s.strip()]
    scoped: list[str] = []
    for part in parts:
        if part.startswith("@") or part.startswith(prefix):
            scoped.append(part)
        elif part.startswith("[data-slot="):
            scoped.append(part)
        elif part.startswith(":where("):
            inner = part[len(":where(") : -1]
            scoped.append(f":where({prefix} {inner})")
        else:
            scoped.append(f"{prefix} {part}")
    return ",\n".join(scoped)


def scope_layer_blocks(text: str) -> str:
    """Scope @layer base/utilities selector lists under .lc-root."""

    def repl(match: re.Match[str]) -> str:
        layer = match.group(1)
        body = match.group(2)
        rules = re.split(r"(?=\n\s*(?:[.\[:#*\w]|::))", body)
        scoped_rules: list[str] = []
        for rule in rules:
            rule = rule.strip()
            if not rule or rule.startswith("/*"):
                scoped_rules.append(rule)
                continue
            if "{" not in rule:
                scoped_rules.append(rule)
                continue
            selector, rest = rule.split("{", 1)
            if any(m in selector for m in CHAT_LINE_MARKERS):
                continue
            if layer == "utilities" and "rounded-full" in selector:
                scoped_rules.append(f"{prefix_selector_list(selector)} {{{rest}")
            elif layer == "base":
                scoped_rules.append(f"{prefix_selector_list(selector)} {{{rest}")
            else:
                scoped_rules.append(rule)
        return f"@layer {layer} {{\n" + "\n".join(scoped_rules) + "\n}"

    return re.sub(
        r"@layer (base|utilities|components) \{([\s\S]*?)\n\}",
        repl,
        text,
    )


def scope_unlayered_rules(text: str) -> str:
    """Prefix top-level rule selectors with .lc-root (portaled slots stay global)."""
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("@") or stripped.startswith("/*"):
            out.append(line)
            i += 1
            continue
        if "{" in line and not stripped.startswith("/*"):
            selector_part = line.split("{", 1)[0]
            if any(m in selector_part for m in CHAT_LINE_MARKERS):
                depth = line.count("{") - line.count("}")
                i += 1
                while i < len(lines) and depth > 0:
                    depth += lines[i].count("{") - lines[i].count("}")
                    i += 1
                continue
            # Collect multi-line selector lists (e.g. *:focus, *:focus-visible)
            selector_lines = [selector_part]
            depth = line.count("{") - line.count("}")
            j = i + 1
            while "{" not in line and j < len(lines):
                break
            while depth <= 0 and j < len(lines) and "{" not in lines[j]:
                if lines[j].strip().endswith("{"):
                    break
                if "{" in lines[j]:
                    break
                if lines[j].strip() and not lines[j].strip().startswith("/*"):
                    selector_lines.append(lines[j].split("{", 1)[0])
                j += 1
            selector = ",\n".join(s.strip() for s in selector_lines if s.strip())
            scoped = prefix_selector_list(selector.replace("\n", ", "))
            out.append(f"{scoped} {{")
            i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def main() -> None:
    src_lines = AGENT_LC_STYLES.read_text(encoding="utf-8").splitlines()
    chunks: list[str] = []
    for start, end in COPY_BLOCKS:
        block = filter_chat_lines(src_lines[start - 1 : end])
        chunks.append("\n".join(block))
    # Close @theme after shadow-header (composer shadow tokens omitted — Tailwind parser)
    if chunks and chunks[0].lstrip().startswith("@theme"):
        chunks[0] = chunks[0].rstrip() + "\n}"

    body = rewrite_root_selectors("\n\n".join(chunks))
    body = scope_layer_blocks(body)
    body = scope_unlayered_rules(body)

    header = """@import 'tailwindcss' important;
@import '@vscode/codicons/dist/codicon.css';

@custom-variant dark (&:is(.dark *));

"""

    extra = f"""
/* Plugin island: no Electron titlebar chrome */
.lc-root {{
  --titlebar-height: 0px;
  --titlebar-control-size: 1.25rem;
  --titlebar-control-height: 1.375rem;
  --ui-border-subtle: var(--ui-stroke-tertiary);
  height: 100%;
  min-height: 0;
  font-family: var(--dt-font-sans);
  font-size: 0.8125rem;
  line-height: var(--dt-line-height, 1.55);
  letter-spacing: var(--dt-letter-spacing, 0);
  color: var(--dt-foreground);
  -webkit-font-smoothing: antialiased;
}}

.lc-root *,
.lc-root *::before,
.lc-root *::after {{
  box-sizing: border-box;
  border-color: var(--dt-border);
}}

.lc-root button,
.lc-root textarea {{
  font: inherit;
}}

.lc-root :where(
  a,
  .underline,
  [class~='hover:underline'],
  [class~='focus:underline'],
  [class~='focus-visible:underline'],
  [class~='group-hover:underline'],
  [class~='peer-hover:underline']
) {{
  text-decoration-color: color-mix(in srgb, currentColor 20%, transparent);
  text-underline-offset: 0.25rem;
}}

.lc-root *::selection {{
  background: var(--ui-selection-background);
  color: inherit;
}}

.lc-root .codicon,
{", ".join(f"[data-slot='{s}'] .codicon" for s in PORTAL_SLOTS)} {{
  font-family: codicon;
  font-size: inherit;
}}
"""

    out = header + body + extra
    OUT.write_text(out.rstrip() + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(out.splitlines())} lines)")


if __name__ == "__main__":
    main()

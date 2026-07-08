"""Lightweight Markdown → HTML converter for translation / bubble display.

Only handles the subset of Markdown that the LLM translation prompt
produces: headings, bold, italic, unordered / ordered lists, and
line breaks.  The output is safe for QLabel rich-text rendering.
"""

from __future__ import annotations

import re


def md_to_html(text: str) -> str:
    """Convert a small subset of Markdown to HTML suitable for QLabel."""
    lines = text.split("\n")
    out: list[str] = []
    in_list: str | None = None  # "ul" or "ol"

    for line in lines:
        # ---- blank line closes list, no extra spacing ----
        if line.strip() == "":
            if in_list:
                out.append(f"</{in_list}>")
                in_list = None
            continue

        stripped = line.strip()

        # ---- headings (#, ##, ###) ----
        h_match = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if h_match:
            if in_list:
                out.append(f"</{in_list}>")
                in_list = None
            level = len(h_match.group(1))
            sizes = {1: "16px", 2: "14px", 3: "13px"}
            sz = sizes.get(level, "14px")
            out.append(
                f"<b style='font-size:{sz};'>{_inline(h_match.group(2))}</b><br>"
            )
            continue

        # ---- unordered list ----
        ul_match = re.match(r"^[-*]\s+(.+)$", stripped)
        if ul_match:
            if in_list != "ul":
                if in_list:
                    out.append(f"</{in_list}>")
                out.append("<ul>")
                in_list = "ul"
            out.append(f"<li>{_inline(ul_match.group(1))}</li>")
            continue

        # ---- ordered list ----
        ol_match = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if ol_match:
            if in_list != "ol":
                if in_list:
                    out.append(f"</{in_list}>")
                out.append("<ol>")
                in_list = "ol"
            out.append(f"<li>{_inline(ol_match.group(1))}</li>")
            continue

        # ---- regular paragraph ----
        if in_list:
            out.append(f"</{in_list}>")
            in_list = None
        out.append(_inline(stripped) + "<br>")

    # close any open list
    if in_list:
        out.append(f"</{in_list}>")

    return "".join(out)


def _inline(text: str) -> str:
    """Convert inline markdown (**bold**, *italic*) to HTML."""
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # Italic
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    return text

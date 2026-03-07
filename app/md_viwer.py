from __future__ import annotations

import html
import re


def render_markdown_html(md_text: str) -> str:
    # Lightweight renderer without extra dependencies.
    raw_lines = md_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ref_defs: dict[str, tuple[str, str]] = {}
    ref_pat = re.compile(r'^\s*\[([^\]]+)\]:\s+(\S+)(?:\s+"([^"]*)")?\s*$')
    lines: list[str] = []
    for ln in raw_lines:
        m = ref_pat.match(ln)
        if m:
            key = m.group(1).strip().lower()
            url = m.group(2).strip()
            title = (m.group(3) or "").strip()
            ref_defs[key] = (url, title)
            continue
        lines.append(ln)
    out: list[str] = []
    in_code = False
    code_lang = ""
    code_lines: list[str] = []
    in_ul = False
    in_ol = False

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    def _render_plain_with_links(text: str) -> str:
        # Inline link: [text](url "title")
        image_pat = re.compile(r'!\[([^\]]*)\]\((\S+?)(?:\s+"([^"]*)")?\)')
        image_ref_pat = re.compile(r'!\[([^\]]*)\]\[([^\]]+)\]')
        inline_pat = re.compile(r'\[([^\]]+)\]\((\S+?)(?:\s+"([^"]*)")?\)')
        ref_pat2 = re.compile(r'\[([^\]]+)\]\[([^\]]+)\]')
        auto_url_pat = re.compile(r'(?<!["\'>])(https?://[^\s<]+)')

        def replace_image_ref(match: re.Match[str]) -> str:
            alt = html.escape(match.group(1))
            label = match.group(2).strip().lower()
            found = ref_defs.get(label)
            if not found:
                return alt
            url, title = found
            t_attr = f' title="{html.escape(title, quote=True)}"' if title else ""
            return (
                f"<a href=\"{html.escape(url, quote=True)}\" class='md-image-link' data-full=\"{html.escape(url, quote=True)}\" target='_blank' rel='noopener noreferrer'>"
                f'<img src="{html.escape(url, quote=True)}" alt="{alt}"{t_attr} '
                "loading='lazy' class='md-image'/>"
                "</a>"
            )

        def replace_image(match: re.Match[str]) -> str:
            alt = html.escape(match.group(1))
            url = html.escape(match.group(2), quote=True)
            title = (match.group(3) or "").strip()
            t_attr = f' title="{html.escape(title, quote=True)}"' if title else ""
            return (
                f"<a href=\"{url}\" class='md-image-link' data-full=\"{url}\" target='_blank' rel='noopener noreferrer'>"
                f'<img src="{url}" alt="{alt}"{t_attr} '
                "loading='lazy' class='md-image'/>"
                "</a>"
            )

        def replace_ref(match: re.Match[str]) -> str:
            label = match.group(2).strip().lower()
            found = ref_defs.get(label)
            text_ = html.escape(match.group(1))
            if not found:
                return text_
            url, title = found
            t_attr = f' title="{html.escape(title, quote=True)}"' if title else ""
            return f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer"{t_attr}>{text_}</a>'

        def replace_inline(match: re.Match[str]) -> str:
            text_ = html.escape(match.group(1))
            url = html.escape(match.group(2), quote=True)
            title = (match.group(3) or "").strip()
            t_attr = f' title="{html.escape(title, quote=True)}"' if title else ""
            return f'<a href="{url}" target="_blank" rel="noopener noreferrer"{t_attr}>{text_}</a>'

        # Escape first, then re-insert anchors through unique placeholders.
        anchors: list[str] = []

        def stash_anchor(a: str) -> str:
            anchors.append(a)
            return f"__ANCHOR_{len(anchors)-1}__"

        tmp = text
        tmp = image_ref_pat.sub(lambda m: stash_anchor(replace_image_ref(m)), tmp)
        tmp = image_pat.sub(lambda m: stash_anchor(replace_image(m)), tmp)
        tmp = ref_pat2.sub(lambda m: stash_anchor(replace_ref(m)), tmp)
        tmp = inline_pat.sub(lambda m: stash_anchor(replace_inline(m)), tmp)
        tmp = auto_url_pat.sub(
            lambda m: stash_anchor(
                f'<a href="{html.escape(m.group(1), quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(m.group(1))}</a>'
            ),
            tmp,
        )
        esc = html.escape(tmp)
        esc = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", esc)
        for i, a in enumerate(anchors):
            esc = esc.replace(html.escape(f"__ANCHOR_{i}__"), a)
        return esc

    def render_inline(text: str) -> str:
        # Preserve inline code spans and leave math delimiters ($, $$, \(...\), \[...\]) untouched.
        parts = text.split("`")
        if len(parts) == 1:
            return _render_plain_with_links(text)
        out_parts: list[str] = []
        for idx, part in enumerate(parts):
            if idx % 2 == 1:
                out_parts.append("<code>" + html.escape(part) + "</code>")
            else:
                out_parts.append(_render_plain_with_links(part))
        return "".join(out_parts)

    def split_table_row(s: str) -> list[str]:
        t = s.strip()
        if t.startswith("|"):
            t = t[1:]
        if t.endswith("|"):
            t = t[:-1]
        return [c.strip() for c in t.split("|")]

    def is_table_sep_row(s: str) -> bool:
        cells = split_table_row(s)
        if not cells:
            return False
        for c in cells:
            x = c.replace(":", "").replace("-", "").strip()
            if x != "" or "-" not in c:
                return False
        return True

    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n")
        stripped = line.strip()
        # Block math: $$ ... $$ (multiline)
        if stripped == "$$":
            close_lists()
            i += 1
            math_lines: list[str] = []
            while i < len(lines) and lines[i].strip() != "$$":
                math_lines.append(lines[i])
                i += 1
            if i < len(lines) and lines[i].strip() == "$$":
                i += 1
            expr = "\n".join(math_lines)
            out.append("<div class='math-block'>$$\n" + html.escape(expr) + "\n$$</div>")
            continue
        # Block math fallback: [ ... ] (multiline)
        # Some docs use bracket-only lines to wrap formulas.
        if stripped == "[":
            close_lists()
            i += 1
            math_lines = []
            while i < len(lines) and lines[i].strip() != "]":
                math_lines.append(lines[i])
                i += 1
            if i < len(lines) and lines[i].strip() == "]":
                i += 1
            expr = "\n".join(math_lines).strip()
            out.append("<div class='math-block'>$$\n" + html.escape(expr) + "\n$$</div>")
            continue
        if stripped.startswith("```"):
            if in_code:
                code_text = "\n".join(code_lines)
                if code_lang.lower() == "mermaid":
                    out.append("<pre class='mermaid'>" + html.escape(code_text) + "</pre>")
                else:
                    out.append("<pre><code>" + html.escape(code_text) + "</code></pre>")
                code_lines = []
                code_lang = ""
                in_code = False
            else:
                close_lists()
                in_code = True
                code_lang = stripped[3:].strip()
            i += 1
            continue
        if in_code:
            code_lines.append(line)
            i += 1
            continue
        if not stripped:
            close_lists()
            i += 1
            continue
        if stripped == "---":
            close_lists()
            out.append("<hr/>")
            i += 1
            continue
        if stripped.lower() in {"<br>", "<br/>", "<br />", "<br><br>", "<br/><br/>", "<br /><br />"}:
            close_lists()
            out.append(stripped)
            i += 1
            continue
        # Markdown table: header row + separator row + body rows.
        if "|" in stripped and (i + 1) < len(lines):
            next_line = lines[i + 1].strip()
            if "|" in next_line and is_table_sep_row(next_line):
                close_lists()
                headers = split_table_row(stripped)
                out.append("<table style='border-collapse:collapse;width:auto;max-width:100%;margin:12px 0;'>")
                out.append("<thead><tr>")
                for h in headers:
                    out.append(
                        "<th style='border:1px solid #ddd;padding:8px;background:#f7f7f7;text-align:left;'>"
                        + render_inline(h)
                        + "</th>"
                    )
                out.append("</tr></thead>")
                out.append("<tbody>")
                i += 2
                while i < len(lines):
                    row_line = lines[i].strip()
                    if not row_line or "|" not in row_line:
                        break
                    cells = split_table_row(row_line)
                    out.append("<tr>")
                    for c in cells:
                        out.append("<td style='border:1px solid #ddd;padding:8px;vertical-align:top;'>" + render_inline(c) + "</td>")
                    out.append("</tr>")
                    i += 1
                out.append("</tbody></table>")
                continue
        if stripped.startswith("#"):
            close_lists()
            lvl = min(6, len(stripped) - len(stripped.lstrip("#")))
            content = stripped[lvl:].strip()
            out.append(f"<h{lvl}>{render_inline(content)}</h{lvl}>")
            i += 1
            continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append("<li>" + render_inline(stripped[2:].strip()) + "</li>")
            i += 1
            continue
        if len(stripped) >= 3 and stripped[0].isdigit() and ". " in stripped:
            prefix, content = stripped.split(". ", 1)
            if prefix.isdigit():
                if in_ul:
                    out.append("</ul>")
                    in_ul = False
                if not in_ol:
                    out.append("<ol>")
                    in_ol = True
                out.append("<li>" + render_inline(content.strip()) + "</li>")
                i += 1
                continue
        close_lists()
        out.append("<p>" + render_inline(stripped) + "</p>")
        i += 1

    if in_code:
        code_text = "\n".join(code_lines)
        if code_lang.lower() == "mermaid":
            out.append("<pre class='mermaid'>" + html.escape(code_text) + "</pre>")
        else:
            out.append("<pre><code>" + html.escape(code_text) + "</code></pre>")
    if in_ul:
        out.append("</ul>")
    if in_ol:
        out.append("</ol>")
    return "\n".join(out)

#!/usr/bin/env python3
"""Build the PEACE SME Go/Vue/Git guide as a beautiful, premium HTML book reader."""

import re
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "index.html"

FILES = [
    ROOT / "README.md",
    ROOT / "concept-index.md",
    *sorted((ROOT / "chapters").glob("*.md")),
]

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mastering Go, Vue 3, and Git - PEACE SME Grant Portal</title>
    
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;700&family=Noto+Nastaliq+Urdu:wght@400;700&display=swap" rel="stylesheet">
    
    <!-- Prism.js for High-Contrast Syntax Highlighting -->
    <link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism-tomorrow.min.css" rel="stylesheet" />
    
    <style>
        :root {
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent: #38bdf8;
            --accent-hover: #7dd3fc;
            --border: #334155;
            --code-bg: #0b0f19;
            --sidebar-width: 320px;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            display: flex;
            min-height: 100vh;
            line-height: 1.6;
        }

        /* Sidebar Styling */
        aside {
            width: var(--sidebar-width);
            background-color: var(--bg-secondary);
            border-right: 1px solid var(--border);
            position: fixed;
            top: 0;
            bottom: 0;
            left: 0;
            overflow-y: auto;
            padding: 2rem 1.5rem;
            z-index: 10;
        }

        .sidebar-header {
            margin-bottom: 2rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 1.5rem;
        }

        .sidebar-header h1 {
            font-size: 1.25rem;
            font-weight: 700;
            color: var(--text-primary);
            line-height: 1.3;
        }

        .sidebar-header p {
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-top: 0.5rem;
        }

        .nav-list {
            list-style: none;
        }

        .nav-item {
            margin-bottom: 0.5rem;
        }

        .nav-link {
            display: block;
            padding: 0.6rem 0.8rem;
            color: var(--text-secondary);
            text-decoration: none;
            border-radius: 6px;
            font-size: 0.9rem;
            font-weight: 500;
            transition: all 0.2s ease;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .nav-link:hover {
            background-color: var(--border);
            color: var(--accent);
        }

        .nav-link.active {
            background-color: rgba(56, 189, 248, 0.1);
            color: var(--accent);
            border-left: 3px solid var(--accent);
        }

        /* Main Content Styling */
        main {
            margin-left: var(--sidebar-width);
            flex: 1;
            padding: 4rem 5%;
            max-width: 1200px;
        }

        section {
            margin-bottom: 6rem;
            scroll-margin-top: 4rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 6rem;
        }

        section:last-of-type {
            border-bottom: none;
        }

        h1, h2, h3, h4 {
            color: var(--text-primary);
            font-weight: 700;
            margin-bottom: 1.25rem;
            line-height: 1.25;
        }

        h1 {
            font-size: 2.25rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 0.75rem;
            margin-top: 2rem;
            color: var(--accent);
        }

        h2 {
            font-size: 1.5rem;
            margin-top: 3rem;
            color: #e2e8f0;
        }

        h3 {
            font-size: 1.15rem;
            margin-top: 2rem;
            color: #cbd5e1;
        }

        p {
            margin-bottom: 1.5rem;
            color: #cbd5e1;
            font-size: 1.05rem;
        }

        /* Lists */
        ul, ol {
            margin-bottom: 1.5rem;
            padding-left: 2rem;
            color: #cbd5e1;
        }

        li {
            margin-bottom: 0.5rem;
        }

        /* Tables */
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 2rem 0;
            font-size: 0.95rem;
        }

        th, td {
            padding: 0.75rem 1rem;
            border: 1px solid var(--border);
            text-align: left;
        }

        th {
            background-color: var(--bg-secondary);
            font-weight: 600;
            color: var(--text-primary);
        }

        tr:nth-child(even) {
            background-color: rgba(255, 255, 255, 0.02);
        }

        /* Alerts */
        .alert {
            padding: 1rem 1.25rem;
            border-left: 4px solid var(--accent);
            background-color: var(--bg-secondary);
            border-radius: 0 8px 8px 0;
            margin: 1.5rem 0;
        }

        .alert-warning {
            border-left-color: #f59e0b;
            background-color: rgba(245, 158, 11, 0.05);
        }

        /* Expandable Box Styling */
        .expandable-box {
            background-color: rgba(30, 41, 59, 0.4);
            border: 1px solid var(--border);
            border-radius: 8px;
            margin: 1.5rem 0;
            overflow: hidden;
            transition: all 0.3s ease;
        }

        .expandable-box[open] {
            background-color: rgba(30, 41, 59, 0.8);
            border-color: var(--accent);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        }

        .expandable-summary {
            padding: 1rem 1.25rem;
            font-weight: 600;
            color: var(--accent);
            cursor: pointer;
            user-select: none;
            transition: color 0.2s ease, background-color 0.2s ease;
            outline: none;
        }

        .expandable-summary:hover {
            color: var(--accent-hover);
            background-color: rgba(255, 255, 255, 0.02);
        }

        .expandable-content {
            padding: 1.5rem;
            border-top: 1px solid var(--border);
            background-color: rgba(15, 23, 42, 0.6);
        }

        /* Inline formatting */
        code {
            font-family: 'JetBrains Mono', monospace;
            background-color: var(--code-bg);
            padding: 0.2rem 0.4rem;
            border-radius: 4px;
            font-size: 0.9rem;
            color: #38bdf8;
        }

        pre code {
            padding: 0;
            background-color: transparent;
            color: inherit;
        }

        pre {
            background-color: var(--code-bg) !important;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1.25rem !important;
            margin-bottom: 2rem;
            overflow-x: auto;
        }

        a {
            color: var(--accent);
            text-decoration: none;
            transition: color 0.2s ease;
        }

        a:hover {
            color: var(--accent-hover);
            text-decoration: underline;
        }

        .font-urdu {
            font-family: 'Noto Nastaliq Urdu', serif;
            line-height: 2.2;
            text-align: right;
            direction: rtl;
        }

        /* Custom Scrollbar */
        ::-webkit-scrollbar {
            width: 8px;
        }
        ::-webkit-scrollbar-track {
            background: var(--bg-primary);
        }
        ::-webkit-scrollbar-thumb {
            background: var(--border);
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: var(--text-secondary);
        }

        @media (max-width: 900px) {
            body {
                flex-direction: column;
            }
            aside {
                position: relative;
                width: 100%;
                border-right: none;
                border-bottom: 1px solid var(--border);
            }
            main {
                margin-left: 0;
                padding: 2rem 1rem;
            }
        }
    </style>
</head>
<body>

    <aside>
        <div class="sidebar-header">
            <h1>PEACE SME Guide</h1>
            <p>Master Go, Vue 3, and Git</p>
        </div>
        <nav>
            <ul class="nav-list">
                {{sidebar_links}}
            </ul>
        </nav>
    </aside>

    <main>
        {{chapters_content}}
    </main>

    <!-- Prism.js Scripts -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-core.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/autoloader/prism-autoloader.min.js"></script>
    
    <script>
        // Active Nav Highlighter on Scroll
        const sections = document.querySelectorAll('section');
        const navLinks = document.querySelectorAll('.nav-link');

        window.addEventListener('scroll', () => {
            let current = '';
            sections.forEach(section => {
                const sectionTop = section.offsetTop;
                const sectionHeight = section.clientHeight;
                if (pageYOffset >= (sectionTop - 150)) {
                    current = section.getAttribute('id');
                }
            });

            navLinks.forEach(link => {
                link.classList.remove('active');
                if (link.getAttribute('href').includes(current)) {
                    link.classList.add('active');
                }
            });
        });
    </script>
</body>
</html>
"""

def parse_markdown_to_html(md_text: str) -> str:
    # Handle bold tags first so we can remove literal bold stars
    html_out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", md_text)
    html_out = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", html_out)
    
    lines = html_out.splitlines()
    parsed_lines = []
    
    in_code_block = False
    in_list = False
    in_table = False
    
    for line in lines:
        striped_line = line.strip()

        # Expandable blocks
        if striped_line.startswith(":::expandable"):
            match = re.search(r"\[([^\]]+)\]", striped_line)
            topic = match.group(1) if match else "Deep Dive"
            parsed_lines.append(f'<details class="expandable-box"><summary class="expandable-summary">Deep Dive: {topic} (Click to expand detailed explanation & sandbox code)</summary><div class="expandable-content">')
            continue

        if striped_line == ":::":
            parsed_lines.append('</div></details>')
            continue
        
        # Code block handler
        if striped_line.startswith("```"):
            if in_code_block:
                parsed_lines.append("</code></pre>")
                in_code_block = False
            else:
                lang = striped_line[3:].strip()
                if not lang:
                    lang = "text"
                parsed_lines.append(f'<pre><code class="language-{lang}">')
                in_code_block = True
            continue
            
        if in_code_block:
            # Escape HTML characters inside code blocks to prevent layout break
            parsed_lines.append(html.escape(line))
            continue
            
        # Lists handler
        if striped_line.startswith("- ") or striped_line.startswith("* "):
            if not in_list:
                parsed_lines.append("<ul>")
                in_list = True
            content = line.replace("- ", "", 1).replace("* ", "", 1).strip()
            # Replace inline code backticks
            content = re.sub(r"`([^`]+)`", r"<code>\1</code>", content)
            # Replace link markup
            content = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', content)
            parsed_lines.append(f"<li>{content}</li>")
            continue
        elif in_list and not striped_line:
            parsed_lines.append("</ul>")
            in_list = False
            
        # Headers
        if striped_line.startswith("#"):
            level = len(striped_line) - len(striped_line.lstrip('#'))
            header_text = striped_line.lstrip('#').strip()
            # Replace inline code backticks in headers
            header_text = re.sub(r"`([^`]+)`", r"<code>\1</code>", header_text)
            parsed_lines.append(f"<h{level}>{header_text}</h{level}>")
            continue
            
        # Horizontal rules
        if striped_line == "---":
            parsed_lines.append("<hr style='margin: 2rem 0; border: none; border-top: 1px solid var(--border);'>")
            continue
            
        # Alert blocks
        if striped_line.startswith(">"):
            alert_content = striped_line.lstrip('>').strip()
            if alert_content.startswith("[!WARNING]"):
                parsed_lines.append(f'<div class="alert alert-warning"><strong>WARNING:</strong> {alert_content[10:].strip()}</div>')
            elif alert_content.startswith("[!NOTE]"):
                parsed_lines.append(f'<div class="alert"><strong>NOTE:</strong> {alert_content[7:].strip()}</div>')
            else:
                parsed_lines.append(f'<div class="alert">{alert_content}</div>')
            continue
            
        # Tables handler
        if striped_line.startswith("|"):
            if not in_table:
                parsed_lines.append("<table>")
                in_table = True
            # Skip separator lines
            if "---" in striped_line:
                continue
            cells = [c.strip() for c in striped_line.split("|")[1:-1]]
            tag = "th" if parsed_lines[-1] == "<table>" else "td"
            cell_html = "".join(f"<{tag}>{re.sub(r'`([^`]+)`', r'<code>\1</code>', cell)}</{tag}>" for cell in cells)
            parsed_lines.append(f"<tr>{cell_html}</tr>")
            continue
        elif in_table and not striped_line.startswith("|"):
            parsed_lines.append("</table>")
            in_table = False

        # Regular Paragraph
        if striped_line:
            # Inline replacements
            para = re.sub(r"`([^`]+)`", r"<code>\1</code>", line)
            para = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', para)
            
            # Check for Urdu script patterns to apply Nastaliq styles
            if any(ord(char) >= 0x0600 and ord(char) <= 0x06FF for char in para):
                parsed_lines.append(f'<p class="font-urdu">{para}</p>')
            else:
                parsed_lines.append(f"<p>{para}</p>")
                
    if in_list:
        parsed_lines.append("</ul>")
    if in_table:
        parsed_lines.append("</table>")
        
    return "\n".join(parsed_lines)

def build_html():
    sidebar_links = []
    chapters_content = []
    
    for idx, filepath in enumerate(FILES):
        if not filepath.exists():
            continue
            
        content = filepath.read_text(encoding="utf-8")
        
        # Exclude frontmatter if any
        if content.startswith("---"):
            _, _, content = content.split("---", 2)
            
        section_id = f"chap-{idx}"
        
        # Get title from first H1
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = title_match.group(1) if title_match else filepath.stem.replace("-", " ").title()
        
        sidebar_links.append(f'<li class="nav-item"><a class="nav-link" href="#{section_id}">{title}</a></li>')
        
        html_content = parse_markdown_to_html(content)
        chapters_content.append(f'<section id="{section_id}">{html_content}</section>')
        
    html_out = HTML_TEMPLATE.replace(
        "{{sidebar_links}}", "\n".join(sidebar_links)
    ).replace(
        "{{chapters_content}}", "\n".join(chapters_content)
    )
    
    OUTPUT.write_text(html_out, encoding="utf-8")
    print(f"Generated HTML book reader successfully at {OUTPUT}")

if __name__ == "__main__":
    build_html()

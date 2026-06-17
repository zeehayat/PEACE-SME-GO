//go:build ignore

// Build the PEACE SME guide as a single HTML file.
// Run with: go run build.go
package main

import (
	"fmt"
	"html"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

func main() {
	// Use CWD so `go run build.go` from the guide directory works correctly.
	cwd, err := os.Getwd()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Cannot determine CWD: %v\n", err)
		os.Exit(1)
	}
	root := cwd
	output := filepath.Join(root, "index.html")

	// Collect files in order
	files := []string{
		filepath.Join(root, "README.md"),
		filepath.Join(root, "concept-index.md"),
	}
	chapters, _ := filepath.Glob(filepath.Join(root, "chapters", "*.md"))
	sort.Strings(chapters)
	files = append(files, chapters...)

	var sidebarLinks []string
	var chaptersContent []string

	for idx, fp := range files {
		raw, err := os.ReadFile(fp)
		if err != nil {
			continue
		}
		content := string(raw)

		// Strip YAML frontmatter
		if strings.HasPrefix(content, "---") {
			parts := strings.SplitN(content, "---", 3)
			if len(parts) == 3 {
				content = parts[2]
			}
		}

		sectionID := fmt.Sprintf("chap-%d", idx)

		// Extract title from first H1
		title := filepath.Base(fp)
		h1re := regexp.MustCompile(`(?m)^#\s+(.+)$`)
		if m := h1re.FindStringSubmatch(content); m != nil {
			title = m[1]
		}

		sidebarLinks = append(sidebarLinks,
			fmt.Sprintf(`<li class="nav-item"><a class="nav-link" href="#%s">%s</a></li>`, sectionID, title),
		)

		htmlContent := parseMarkdown(content)
		chaptersContent = append(chaptersContent,
			fmt.Sprintf(`<section id="%s">%s</section>`, sectionID, htmlContent),
		)
	}

	out := htmlTemplate
	out = strings.ReplaceAll(out, "{{sidebar_links}}", strings.Join(sidebarLinks, "\n"))
	out = strings.ReplaceAll(out, "{{chapters_content}}", strings.Join(chaptersContent, "\n"))

	if err := os.WriteFile(output, []byte(out), 0644); err != nil {
		fmt.Fprintf(os.Stderr, "Error writing output: %v\n", err)
		os.Exit(1)
	}

	info, _ := os.Stat(output)
	fmt.Printf("Generated HTML book at %s\n", output)
	fmt.Printf("  Chapters: %d\n", len(chaptersContent))
	if info != nil {
		fmt.Printf("  File size: %.0f KB\n", float64(info.Size())/1024)
	}
}

func mustAbs(name string) string {
	exe, err := os.Executable()
	if err != nil {
		return name
	}
	return filepath.Join(filepath.Dir(exe), name)
}

// parseMarkdown converts a simple Markdown subset to HTML.
// Supports: headers, bold/italic, code blocks, inline code, lists (ul/ol),
// tables, alert blockquotes, horizontal rules, expandable blocks, links.
func parseMarkdown(md string) string {
	// Bold and italic first
	out := regexp.MustCompile(`\*\*([^*]+)\*\*`).ReplaceAllString(md, "<strong>$1</strong>")
	out = regexp.MustCompile(`\*([^*\n]+)\*`).ReplaceAllString(out, "<em>$1</em>")

	lines := strings.Split(out, "\n")
	var result []string

	inCode := false
	inList := false
	inOrderedList := false
	inTable := false

	inlineCode := regexp.MustCompile("`([^`]+)`")
	linkRe := regexp.MustCompile(`\[([^\]]+)\]\(([^)]+)\)`)

	applyInline := func(s string) string {
		s = inlineCode.ReplaceAllString(s, "<code>$1</code>")
		s = linkRe.ReplaceAllString(s, `<a href="$2">$1</a>`)
		return s
	}

	for _, line := range lines {
		trimmed := strings.TrimSpace(line)

		// Expandable blocks
		if strings.HasPrefix(trimmed, ":::expandable") {
			topicRe := regexp.MustCompile(`\[([^\]]+)\]`)
			topic := "Deep Dive"
			if m := topicRe.FindStringSubmatch(trimmed); m != nil {
				topic = m[1]
			}
			result = append(result, fmt.Sprintf(
				`<details class="expandable-box"><summary class="expandable-summary">Deep Dive: %s (Click to expand)</summary><div class="expandable-content">`,
				topic,
			))
			continue
		}
		if trimmed == ":::" {
			result = append(result, `</div></details>`)
			continue
		}

		// Code blocks
		if strings.HasPrefix(trimmed, "```") {
			if inCode {
				result = append(result, "</code></pre>")
				inCode = false
			} else {
				lang := strings.TrimSpace(trimmed[3:])
				if lang == "" {
					lang = "text"
				}
				result = append(result, fmt.Sprintf(`<pre><code class="language-%s">`, lang))
				inCode = true
			}
			continue
		}
		if inCode {
			result = append(result, html.EscapeString(line))
			continue
		}

		// Ordered list
		olRe := regexp.MustCompile(`^\d+\.\s+(.+)$`)
		if m := olRe.FindStringSubmatch(trimmed); m != nil {
			if !inOrderedList {
				if inList {
					result = append(result, "</ul>")
					inList = false
				}
				result = append(result, "<ol>")
				inOrderedList = true
			}
			result = append(result, "<li>"+applyInline(m[1])+"</li>")
			continue
		} else if inOrderedList && trimmed == "" {
			result = append(result, "</ol>")
			inOrderedList = false
		}

		// Unordered list
		if strings.HasPrefix(trimmed, "- ") || strings.HasPrefix(trimmed, "* ") {
			if !inList {
				if inOrderedList {
					result = append(result, "</ol>")
					inOrderedList = false
				}
				result = append(result, "<ul>")
				inList = true
			}
			content := regexp.MustCompile(`^[-*]\s+`).ReplaceAllString(trimmed, "")
			result = append(result, "<li>"+applyInline(content)+"</li>")
			continue
		} else if inList && trimmed == "" {
			result = append(result, "</ul>")
			inList = false
		}

		// Headers
		if strings.HasPrefix(trimmed, "#") {
			level := 0
			for _, c := range trimmed {
				if c == '#' {
					level++
				} else {
					break
				}
			}
			headerText := applyInline(strings.TrimSpace(trimmed[level:]))
			result = append(result, fmt.Sprintf("<h%d>%s</h%d>", level, headerText, level))
			continue
		}

		// Horizontal rule
		if trimmed == "---" || trimmed == "***" || trimmed == "___" {
			result = append(result, `<hr style="margin:2rem 0;border:none;border-top:1px solid var(--border);">`)
			continue
		}

		// Alert blockquotes
		if strings.HasPrefix(trimmed, ">") {
			content := strings.TrimSpace(strings.TrimPrefix(trimmed, ">"))
			if strings.HasPrefix(content, "[!WARNING]") {
				result = append(result, fmt.Sprintf(`<div class="alert alert-warning"><strong>⚠ WARNING:</strong> %s</div>`, applyInline(strings.TrimSpace(content[10:]))))
			} else if strings.HasPrefix(content, "[!NOTE]") {
				result = append(result, fmt.Sprintf(`<div class="alert"><strong>ℹ NOTE:</strong> %s</div>`, applyInline(strings.TrimSpace(content[7:]))))
			} else {
				result = append(result, fmt.Sprintf(`<div class="alert">%s</div>`, applyInline(content)))
			}
			continue
		}

		// Tables
		if strings.HasPrefix(trimmed, "|") {
			if !inTable {
				result = append(result, "<table>")
				inTable = true
			}
			if strings.Contains(trimmed, "---") {
				continue
			}
			cells := strings.Split(trimmed, "|")
			// Remove first and last empty cells
			if len(cells) > 2 {
				cells = cells[1 : len(cells)-1]
			}
			tag := "td"
			if len(result) > 0 && result[len(result)-1] == "<table>" {
				tag = "th"
			}
			var cellHTML strings.Builder
			for _, c := range cells {
				cellHTML.WriteString(fmt.Sprintf("<%s>%s</%s>", tag, applyInline(strings.TrimSpace(c)), tag))
			}
			result = append(result, "<tr>"+cellHTML.String()+"</tr>")
			continue
		} else if inTable && !strings.HasPrefix(trimmed, "|") {
			result = append(result, "</table>")
			inTable = false
		}

		// Regular paragraph
		if trimmed != "" {
			para := applyInline(line)
			// Detect Urdu script
			isUrdu := false
			for _, r := range para {
				if r >= 0x0600 && r <= 0x06FF {
					isUrdu = true
					break
				}
			}
			if isUrdu {
				result = append(result, fmt.Sprintf(`<p class="font-urdu">%s</p>`, para))
			} else {
				result = append(result, fmt.Sprintf("<p>%s</p>", para))
			}
		}
	}

	if inList {
		result = append(result, "</ul>")
	}
	if inOrderedList {
		result = append(result, "</ol>")
	}
	if inTable {
		result = append(result, "</table>")
	}

	return strings.Join(result, "\n")
}

const htmlTemplate = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mastering Go, Vue 3, and Git - PEACE SME Grant Portal</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;700&family=Noto+Nastaliq+Urdu:wght@400;700&display=swap" rel="stylesheet">
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
            --hl-yellow: rgba(250, 204, 21, 0.35);
            --hl-green: rgba(74, 222, 128, 0.3);
            --hl-pink: rgba(244, 114, 182, 0.3);
            --hl-blue: rgba(96, 165, 250, 0.3);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            display: flex;
            min-height: 100vh;
            line-height: 1.6;
        }

        aside {
            width: var(--sidebar-width);
            background-color: var(--bg-secondary);
            border-right: 1px solid var(--border);
            position: fixed;
            top: 0; bottom: 0; left: 0;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            z-index: 10;
        }

        .sidebar-header {
            padding: 1.5rem;
            border-bottom: 1px solid var(--border);
            flex-shrink: 0;
        }

        .sidebar-header h1 { font-size: 1.1rem; font-weight: 700; color: var(--text-primary); line-height: 1.3; }
        .sidebar-header p  { font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.3rem; }

        .sidebar-tabs { display: flex; border-bottom: 1px solid var(--border); flex-shrink: 0; }

        .tab-btn {
            flex: 1; padding: 0.6rem 0.4rem;
            background: none; border: none;
            color: var(--text-secondary);
            font-size: 0.78rem; font-weight: 600;
            cursor: pointer; transition: all 0.2s;
        }

        .tab-btn:hover { color: var(--accent); background: rgba(56,189,248,0.05); }
        .tab-btn.active { color: var(--accent); border-bottom: 2px solid var(--accent); background: rgba(56,189,248,0.08); }

        .tab-pane { display: none; flex: 1; overflow-y: auto; padding: 1rem 1.25rem; }
        .tab-pane.active { display: block; }

        .nav-list { list-style: none; }
        .nav-item { margin-bottom: 0.35rem; }

        .nav-link {
            display: block; padding: 0.5rem 0.75rem;
            color: var(--text-secondary); text-decoration: none;
            border-radius: 6px; font-size: 0.85rem; font-weight: 500;
            transition: all 0.2s; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }

        .nav-link:hover { background: var(--border); color: var(--accent); }
        .nav-link.active { background: rgba(56,189,248,0.1); color: var(--accent); border-left: 3px solid var(--accent); }

        .panel-empty { color: var(--text-secondary); font-size: 0.85rem; text-align: center; padding: 2rem 1rem; line-height: 1.8; }

        .bm-item, .note-item {
            padding: 0.75rem; border: 1px solid var(--border);
            border-radius: 6px; margin-bottom: 0.75rem;
            background: rgba(15,23,42,0.5); position: relative;
        }

        .bm-item a { color: var(--accent); font-size: 0.85rem; font-weight: 600; text-decoration: none; display: block; margin-bottom: 0.2rem; }
        .bm-item a:hover { text-decoration: underline; }
        .bm-ts, .note-ts { font-size: 0.72rem; color: var(--text-secondary); }
        .note-item-section { font-size: 0.72rem; color: var(--accent); margin-bottom: 0.3rem; font-weight: 600; }
        .note-item-text { font-size: 0.85rem; color: #cbd5e1; white-space: pre-wrap; word-break: break-word; margin-top: 0.35rem; }

        .panel-delete-btn {
            position: absolute; top: 0.5rem; right: 0.5rem;
            background: none; border: none; color: var(--text-secondary);
            cursor: pointer; font-size: 0.85rem; padding: 2px 5px;
            border-radius: 4px; transition: all 0.15s;
        }
        .panel-delete-btn:hover { color: #f87171; background: rgba(248,113,113,0.1); }

        main {
            margin-left: var(--sidebar-width);
            flex: 1; padding: 4rem 5%; max-width: 1200px;
        }

        section {
            margin-bottom: 6rem; scroll-margin-top: 4rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 6rem; position: relative;
        }
        section:last-of-type { border-bottom: none; }

        .section-title-row { display: flex; align-items: flex-start; gap: 0.75rem; margin-bottom: 1.25rem; }
        .section-title-row h1 { flex: 1; margin-bottom: 0; }

        .bookmark-btn {
            flex-shrink: 0; margin-top: 0.4rem;
            background: none; border: 1px solid var(--border);
            border-radius: 6px; color: var(--text-secondary);
            cursor: pointer; font-size: 1rem; padding: 0.3rem 0.5rem;
            transition: all 0.2s; opacity: 0;
        }
        section:hover .bookmark-btn { opacity: 1; }
        .bookmark-btn:hover { color: #fbbf24; border-color: #fbbf24; background: rgba(251,191,36,0.1); }
        .bookmark-btn.bookmarked { color: #fbbf24; border-color: #fbbf24; opacity: 1; }

        .section-note-btn {
            display: inline-flex; align-items: center; gap: 0.35rem;
            background: none; border: 1px solid var(--border);
            border-radius: 6px; color: var(--text-secondary);
            cursor: pointer; font-size: 0.78rem; padding: 0.3rem 0.6rem;
            transition: all 0.2s; opacity: 0;
            position: absolute; top: 0.6rem; right: 3rem;
        }
        section:hover .section-note-btn { opacity: 1; }
        .section-note-btn:hover { color: #a78bfa; border-color: #a78bfa; background: rgba(167,139,250,0.1); }

        h1, h2, h3, h4 { color: var(--text-primary); font-weight: 700; line-height: 1.25; }
        h1 { font-size: 2.25rem; border-bottom: 1px solid var(--border); padding-bottom: 0.75rem; margin-top: 2rem; color: var(--accent); }
        h2 { font-size: 1.5rem; margin-top: 3rem; margin-bottom: 1.25rem; color: #e2e8f0; }
        h3 { font-size: 1.15rem; margin-top: 2rem; margin-bottom: 1rem; color: #cbd5e1; }
        h4 { font-size: 1rem; margin-top: 1.5rem; margin-bottom: 0.75rem; color: #94a3b8; }

        p { margin-bottom: 1.5rem; color: #cbd5e1; font-size: 1.05rem; }
        ul, ol { margin-bottom: 1.5rem; padding-left: 2rem; color: #cbd5e1; }
        li { margin-bottom: 0.5rem; }

        table { width: 100%; border-collapse: collapse; margin: 2rem 0; font-size: 0.95rem; }
        th, td { padding: 0.75rem 1rem; border: 1px solid var(--border); text-align: left; }
        th { background-color: var(--bg-secondary); font-weight: 600; color: var(--text-primary); }
        tr:nth-child(even) { background-color: rgba(255,255,255,0.02); }

        .alert { padding: 1rem 1.25rem; border-left: 4px solid var(--accent); background-color: var(--bg-secondary); border-radius: 0 8px 8px 0; margin: 1.5rem 0; }
        .alert-warning { border-left-color: #f59e0b; background-color: rgba(245,158,11,0.05); }

        .expandable-box { background-color: rgba(30,41,59,0.4); border: 1px solid var(--border); border-radius: 8px; margin: 1.5rem 0; overflow: hidden; transition: all 0.3s; }
        .expandable-box[open] { background-color: rgba(30,41,59,0.8); border-color: var(--accent); box-shadow: 0 4px 20px rgba(0,0,0,0.3); }
        .expandable-summary { padding: 1rem 1.25rem; font-weight: 600; color: var(--accent); cursor: pointer; user-select: none; outline: none; }
        .expandable-summary:hover { color: var(--accent-hover); background: rgba(255,255,255,0.02); }
        .expandable-content { padding: 1.5rem; border-top: 1px solid var(--border); background-color: rgba(15,23,42,0.6); }

        code { font-family: 'JetBrains Mono', monospace; background-color: var(--code-bg); padding: 0.2rem 0.4rem; border-radius: 4px; font-size: 0.9rem; color: #38bdf8; }
        pre code { padding: 0; background: transparent; color: inherit; }
        pre { background-color: var(--code-bg) !important; border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem !important; margin-bottom: 2rem; overflow-x: auto; }

        a { color: var(--accent); text-decoration: none; transition: color 0.2s; }
        a:hover { color: var(--accent-hover); text-decoration: underline; }
        .font-urdu { font-family: 'Noto Nastaliq Urdu', serif; line-height: 2.2; text-align: right; direction: rtl; }

        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: var(--bg-primary); }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

        .hl-yellow { background: var(--hl-yellow); border-radius: 2px; padding: 1px 0; }
        .hl-green  { background: var(--hl-green);  border-radius: 2px; padding: 1px 0; }
        .hl-pink   { background: var(--hl-pink);   border-radius: 2px; padding: 1px 0; }
        .hl-blue   { background: var(--hl-blue);   border-radius: 2px; padding: 1px 0; }

        #highlight-toolbar {
            display: none; position: fixed; z-index: 9999;
            background: #1e293b; border: 1px solid var(--border);
            border-radius: 8px; padding: 6px 10px; gap: 6px;
            align-items: center; box-shadow: 0 8px 24px rgba(0,0,0,0.5);
        }
        #highlight-toolbar.visible { display: flex; }
        .hl-color-btn { width: 22px; height: 22px; border-radius: 50%; border: 2px solid transparent; cursor: pointer; transition: transform 0.15s, border-color 0.15s; }
        .hl-color-btn:hover { transform: scale(1.2); border-color: white; }
        .hl-color-btn[data-color="yellow"] { background: #facc15; }
        .hl-color-btn[data-color="green"]  { background: #4ade80; }
        .hl-color-btn[data-color="pink"]   { background: #f472b4; }
        .hl-color-btn[data-color="blue"]   { background: #60a5fa; }
        .hl-toolbar-sep { width: 1px; background: var(--border); height: 20px; margin: 0 2px; }
        .hl-note-btn { background: none; border: none; color: #a78bfa; cursor: pointer; font-size: 0.85rem; padding: 2px 4px; border-radius: 4px; }
        .hl-note-btn:hover { background: rgba(167,139,250,0.15); }
        .hl-clear-btn { background: none; border: none; color: var(--text-secondary); cursor: pointer; font-size: 0.8rem; padding: 2px 4px; border-radius: 4px; }
        .hl-clear-btn:hover { color: #f87171; background: rgba(248,113,113,0.1); }

        #note-modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 10000; align-items: center; justify-content: center; }
        #note-modal-overlay.visible { display: flex; }
        #note-modal { background: #1e293b; border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; width: 480px; max-width: 95vw; box-shadow: 0 20px 60px rgba(0,0,0,0.6); }
        #note-modal h3 { font-size: 1rem; color: #a78bfa; margin-bottom: 1rem; }
        #note-modal .note-section-label { font-size: 0.78rem; color: var(--text-secondary); margin-bottom: 0.75rem; }
        #note-textarea { width: 100%; min-height: 120px; background: var(--code-bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-family: 'Inter', sans-serif; font-size: 0.9rem; padding: 0.75rem; resize: vertical; outline: none; }
        #note-textarea:focus { border-color: #a78bfa; }
        .note-modal-actions { display: flex; gap: 0.75rem; margin-top: 1rem; justify-content: flex-end; }
        .btn-cancel { padding: 0.5rem 1rem; border: 1px solid var(--border); border-radius: 6px; background: none; color: var(--text-secondary); cursor: pointer; font-size: 0.9rem; }
        .btn-cancel:hover { border-color: var(--text-secondary); color: var(--text-primary); }
        .btn-save { padding: 0.5rem 1.25rem; border: none; border-radius: 6px; background: #a78bfa; color: #0f172a; cursor: pointer; font-size: 0.9rem; font-weight: 600; }
        .btn-save:hover { background: #c4b5fd; }

        .toc-search { width: 100%; background: var(--code-bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.82rem; padding: 0.45rem 0.75rem; outline: none; margin-bottom: 0.75rem; }
        .toc-search:focus { border-color: var(--accent); }

        #progress-bar { position: fixed; top: 0; left: var(--sidebar-width); right: 0; height: 3px; background: var(--accent); transform-origin: left; transform: scaleX(0); z-index: 100; transition: transform 0.1s linear; }

        #scroll-top { position: fixed; bottom: 2rem; right: 2rem; width: 40px; height: 40px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 50%; color: var(--text-secondary); cursor: pointer; font-size: 1.1rem; display: flex; align-items: center; justify-content: center; opacity: 0; transition: all 0.2s; z-index: 50; }
        #scroll-top.visible { opacity: 1; }
        #scroll-top:hover { color: var(--accent); border-color: var(--accent); }

        @media (max-width: 900px) {
            body { flex-direction: column; }
            aside { position: relative; width: 100%; border-right: none; border-bottom: 1px solid var(--border); max-height: 50vh; }
            main { margin-left: 0; padding: 2rem 1rem; }
            #progress-bar { left: 0; }
        }
    </style>
</head>
<body>

<div id="progress-bar"></div>

<aside>
    <div class="sidebar-header">
        <h1>PEACE SME Guide</h1>
        <p>Master Go, Vue 3, and Git</p>
    </div>

    <div class="sidebar-tabs">
        <button class="tab-btn active" data-tab="toc">📖 TOC</button>
        <button class="tab-btn" data-tab="bookmarks">★ Saved</button>
        <button class="tab-btn" data-tab="notes">📝 Notes</button>
    </div>

    <div class="tab-pane active" id="tab-toc">
        <input type="text" class="toc-search" id="toc-search" placeholder="Filter chapters… (press / to focus)" />
        <nav><ul class="nav-list" id="nav-list">
            {{sidebar_links}}
        </ul></nav>
    </div>

    <div class="tab-pane" id="tab-bookmarks">
        <div id="bookmarks-panel">
            <div class="panel-empty">No bookmarks yet.<br>Hover a chapter and click ★ to save it.</div>
        </div>
    </div>

    <div class="tab-pane" id="tab-notes">
        <div id="notes-panel">
            <div class="panel-empty">No notes yet.<br>Select text or hover a chapter and click 📝.</div>
        </div>
    </div>
</aside>

<main id="main-content">
    {{chapters_content}}
</main>

<div id="highlight-toolbar">
    <button class="hl-color-btn" data-color="yellow" title="Yellow highlight"></button>
    <button class="hl-color-btn" data-color="green"  title="Green highlight"></button>
    <button class="hl-color-btn" data-color="pink"   title="Pink highlight"></button>
    <button class="hl-color-btn" data-color="blue"   title="Blue highlight"></button>
    <div class="hl-toolbar-sep"></div>
    <button class="hl-note-btn" title="Add note to selection">📝 Note</button>
    <button class="hl-clear-btn" title="Remove highlight">✕</button>
</div>

<div id="note-modal-overlay">
    <div id="note-modal">
        <h3>📝 Add Note</h3>
        <div class="note-section-label" id="note-modal-section-label"></div>
        <textarea id="note-textarea" placeholder="Write your note… (Ctrl+Enter to save)"></textarea>
        <div class="note-modal-actions">
            <button class="btn-cancel" id="note-modal-cancel">Cancel</button>
            <button class="btn-save" id="note-modal-save">Save Note</button>
        </div>
    </div>
</div>

<button id="scroll-top" title="Back to top">↑</button>

<script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-core.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/autoloader/prism-autoloader.min.js"></script>

<script>
// ── Data layer ──────────────────────────────────────────────────────────
const KEYS = { bookmarks: 'sme_bookmarks', highlights: 'sme_highlights', notes: 'sme_notes' };

function dbLoad(key) {
    try { return JSON.parse(localStorage.getItem(key) || (key === KEYS.bookmarks ? '{}' : '[]')); }
    catch { return key === KEYS.bookmarks ? {} : []; }
}
function dbSave(key, data) { localStorage.setItem(key, JSON.stringify(data)); }

// ── Sidebar tabs ─────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
        if (btn.dataset.tab === 'bookmarks') renderBookmarks();
        if (btn.dataset.tab === 'notes') renderNotes();
    });
});

// ── TOC filter ────────────────────────────────────────────────────────────
document.getElementById('toc-search').addEventListener('input', function() {
    const q = this.value.toLowerCase();
    document.querySelectorAll('#nav-list .nav-item').forEach(item => {
        item.style.display = item.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
});

// ── Progress bar + scroll-to-top ─────────────────────────────────────────
const sections = document.querySelectorAll('section');
const navLinks = document.querySelectorAll('.nav-link');
const progressBar = document.getElementById('progress-bar');
const scrollTopBtn = document.getElementById('scroll-top');

window.addEventListener('scroll', () => {
    const pct = window.scrollY / Math.max(1, document.body.scrollHeight - window.innerHeight);
    progressBar.style.transform = 'scaleX(' + pct + ')';
    scrollTopBtn.classList.toggle('visible', window.scrollY > 400);

    let current = '';
    sections.forEach(sec => { if (window.scrollY >= sec.offsetTop - 150) current = sec.id; });
    navLinks.forEach(link => link.classList.toggle('active', link.getAttribute('href').includes(current)));
}, { passive: true });

scrollTopBtn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));

// ── Bookmark buttons ──────────────────────────────────────────────────────
function getSectionTitle(sec) {
    const h1 = sec.querySelector('h1');
    return h1 ? h1.textContent.trim() : sec.id;
}

function updateBookmarkBtn(btn, sectionId) {
    const active = !!dbLoad(KEYS.bookmarks)[sectionId];
    btn.classList.toggle('bookmarked', active);
    btn.title = active ? 'Remove bookmark' : 'Bookmark this chapter';
}

function updateNoteCount(noteBtn, sectionId) {
    const count = dbLoad(KEYS.notes).filter(n => n.sectionId === sectionId).length;
    const badge = noteBtn.querySelector('.nbadge');
    if (badge) badge.textContent = count > 0 ? ' ' + count : '';
}

function injectButtons() {
    sections.forEach(sec => {
        const h1 = sec.querySelector('h1');
        if (!h1) return;

        // Wrap h1 in row
        const row = document.createElement('div');
        row.className = 'section-title-row';
        h1.parentNode.insertBefore(row, h1);
        row.appendChild(h1);

        // Bookmark button
        const bm = document.createElement('button');
        bm.className = 'bookmark-btn';
        bm.innerHTML = '★';
        row.appendChild(bm);
        updateBookmarkBtn(bm, sec.id);
        bm.addEventListener('click', e => {
            e.stopPropagation();
            const bms = dbLoad(KEYS.bookmarks);
            if (bms[sec.id]) delete bms[sec.id];
            else bms[sec.id] = { title: getSectionTitle(sec), timestamp: Date.now() };
            dbSave(KEYS.bookmarks, bms);
            updateBookmarkBtn(bm, sec.id);
        });

        // Note button
        const nb = document.createElement('button');
        nb.className = 'section-note-btn';
        nb.innerHTML = '📝 Note<span class="nbadge"></span>';
        nb.title = 'Add note to this chapter';
        sec.appendChild(nb);
        updateNoteCount(nb, sec.id);
        nb.addEventListener('click', e => {
            e.stopPropagation();
            openNoteModal(sec.id, getSectionTitle(sec));
        });
    });
}

// ── Bookmarks panel ───────────────────────────────────────────────────────
function renderBookmarks() {
    const panel = document.getElementById('bookmarks-panel');
    const bms = dbLoad(KEYS.bookmarks);
    const entries = Object.entries(bms).sort((a, b) => b[1].timestamp - a[1].timestamp);
    if (!entries.length) {
        panel.innerHTML = '<div class="panel-empty">No bookmarks yet.<br>Hover a chapter and click ★ to save.</div>';
        return;
    }
    panel.innerHTML = entries.map(([id, { title, timestamp }]) =>
        '<div class="bm-item">' +
        '<a href="#' + id + '" onclick="switchTab(\'toc\')">' + esc(title) + '</a>' +
        '<div class="bm-ts">' + new Date(timestamp).toLocaleDateString() + '</div>' +
        '<button class="panel-delete-btn" onclick="removeBookmark(\'' + id + '\')">✕</button>' +
        '</div>'
    ).join('');
}

window.removeBookmark = function(id) {
    const bms = dbLoad(KEYS.bookmarks);
    delete bms[id];
    dbSave(KEYS.bookmarks, bms);
    renderBookmarks();
    const sec = document.getElementById(id);
    if (sec) { const btn = sec.querySelector('.bookmark-btn'); if (btn) updateBookmarkBtn(btn, id); }
};

window.switchTab = function(tab) {
    document.querySelector('[data-tab="' + tab + '"]').click();
};

// ── Notes system ──────────────────────────────────────────────────────────
let _noteCtx = null;

function openNoteModal(sectionId, sectionTitle) {
    _noteCtx = { sectionId, sectionTitle };
    document.getElementById('note-modal-section-label').textContent = 'Chapter: ' + sectionTitle;
    document.getElementById('note-textarea').value = '';
    document.getElementById('note-modal-overlay').classList.add('visible');
    setTimeout(() => document.getElementById('note-textarea').focus(), 50);
}

document.getElementById('note-modal-cancel').addEventListener('click', () => {
    document.getElementById('note-modal-overlay').classList.remove('visible');
    _noteCtx = null;
});

document.getElementById('note-modal-overlay').addEventListener('click', e => {
    if (e.target === e.currentTarget) document.getElementById('note-modal-cancel').click();
});

document.getElementById('note-modal-save').addEventListener('click', () => {
    const text = document.getElementById('note-textarea').value.trim();
    if (!text || !_noteCtx) return;
    const notes = dbLoad(KEYS.notes);
    const newNote = { id: Date.now().toString(), sectionId: _noteCtx.sectionId, sectionTitle: _noteCtx.sectionTitle, text, timestamp: Date.now() };
    notes.unshift(newNote);
    dbSave(KEYS.notes, notes);
    document.getElementById('note-modal-overlay').classList.remove('visible');
    const sec = document.getElementById(newNote.sectionId);
    if (sec) { const nb = sec.querySelector('.section-note-btn'); if (nb) updateNoteCount(nb, newNote.sectionId); }
    _noteCtx = null;
});

document.getElementById('note-textarea').addEventListener('keydown', e => {
    if (e.ctrlKey && e.key === 'Enter') document.getElementById('note-modal-save').click();
});

function renderNotes() {
    const panel = document.getElementById('notes-panel');
    const notes = dbLoad(KEYS.notes);
    if (!notes.length) {
        panel.innerHTML = '<div class="panel-empty">No notes yet.<br>Select text or hover a chapter and click 📝.</div>';
        return;
    }
    panel.innerHTML = notes.map(n =>
        '<div class="note-item">' +
        '<div class="note-item-section"><a href="#' + n.sectionId + '" onclick="switchTab(\'toc\')">' + esc(n.sectionTitle) + '</a></div>' +
        '<div class="note-item-text">' + esc(n.text) + '</div>' +
        '<div class="note-ts">' + new Date(n.timestamp).toLocaleString() + '</div>' +
        '<button class="panel-delete-btn" onclick="removeNote(\'' + n.id + '\')">✕</button>' +
        '</div>'
    ).join('');
}

window.removeNote = function(noteId) {
    let notes = dbLoad(KEYS.notes);
    const note = notes.find(n => n.id === noteId);
    notes = notes.filter(n => n.id !== noteId);
    dbSave(KEYS.notes, notes);
    renderNotes();
    if (note) {
        const sec = document.getElementById(note.sectionId);
        if (sec) { const nb = sec.querySelector('.section-note-btn'); if (nb) updateNoteCount(nb, note.sectionId); }
    }
};

// ── Text highlights ───────────────────────────────────────────────────────
const toolbar = document.getElementById('highlight-toolbar');
let _range = null;

function closestSection(node) {
    let el = node.nodeType === 3 ? node.parentElement : node;
    while (el && el.tagName !== 'SECTION') el = el.parentElement;
    return el;
}

document.addEventListener('mouseup', e => {
    if (toolbar.contains(e.target)) return;
    if (document.getElementById('note-modal-overlay').contains(e.target)) return;
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || sel.toString().trim().length < 3) { hideToolbar(); return; }
    _range = sel.getRangeAt(0).cloneRange();
    const rect = _range.getBoundingClientRect();
    toolbar.style.top  = (rect.top + window.scrollY - 48) + 'px';
    toolbar.style.left = (rect.left + rect.width / 2 - 100) + 'px';
    toolbar.classList.add('visible');
});

document.addEventListener('mousedown', e => { if (!toolbar.contains(e.target)) hideToolbar(); });

function hideToolbar() { toolbar.classList.remove('visible'); _range = null; }

document.querySelectorAll('.hl-color-btn').forEach(btn => {
    btn.addEventListener('click', e => {
        e.stopPropagation();
        if (!_range) return;
        applyHL(_range, btn.dataset.color);
        hideToolbar();
        window.getSelection().removeAllRanges();
    });
});

document.querySelector('.hl-note-btn').addEventListener('click', e => {
    e.stopPropagation();
    if (!_range) return;
    const sec = closestSection(_range.startContainer);
    const quoted = '"' + _range.toString().trim().substring(0, 120) + '"\n\n';
    hideToolbar();
    window.getSelection().removeAllRanges();
    openNoteModal(sec ? sec.id : 'unknown', sec ? getSectionTitle(sec) : '');
    setTimeout(() => {
        const ta = document.getElementById('note-textarea');
        ta.value = quoted;
        ta.setSelectionRange(quoted.length, quoted.length);
    }, 60);
});

document.querySelector('.hl-clear-btn').addEventListener('click', e => {
    e.stopPropagation();
    if (!_range) return;
    const ancestor = _range.commonAncestorContainer;
    const container = ancestor.nodeType === 3 ? ancestor.parentElement : ancestor;
    container.querySelectorAll('.hl-yellow,.hl-green,.hl-pink,.hl-blue').forEach(span => {
        if (_range.intersectsNode(span)) {
            const p = span.parentNode;
            while (span.firstChild) p.insertBefore(span.firstChild, span);
            span.remove();
        }
    });
    syncHighlights();
    hideToolbar();
    window.getSelection().removeAllRanges();
});

function applyHL(range, color) {
    const sec = closestSection(range.startContainer);
    const text = range.toString().trim();
    if (!text) return;
    try {
        const span = document.createElement('span');
        span.className = 'hl-' + color;
        span.dataset.hlId = Date.now().toString();
        range.surroundContents(span);
    } catch {
        const frag = range.extractContents();
        const span = document.createElement('span');
        span.className = 'hl-' + color;
        span.dataset.hlId = Date.now().toString();
        span.appendChild(frag);
        range.insertNode(span);
    }
    const hls = dbLoad(KEYS.highlights);
    hls.push({ id: Date.now().toString(), sectionId: sec ? sec.id : 'unknown', text: text.substring(0, 300), color, timestamp: Date.now() });
    dbSave(KEYS.highlights, hls);
}

function syncHighlights() {
    const hls = [];
    document.querySelectorAll('[class^="hl-"]').forEach(span => {
        const sec = closestSection(span);
        hls.push({ id: span.dataset.hlId || Date.now().toString(), sectionId: sec ? sec.id : 'unknown', text: span.textContent.trim().substring(0, 300), color: span.className.replace('hl-', ''), timestamp: Date.now() });
    });
    dbSave(KEYS.highlights, hls);
}

function restoreHighlights() {
    dbLoad(KEYS.highlights).forEach(hl => {
        const sec = document.getElementById(hl.sectionId);
        if (!sec || !hl.text) return;
        const needle = hl.text.substring(0, 50);
        const walker = document.createTreeWalker(sec, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
            const idx = node.textContent.indexOf(needle);
            if (idx !== -1) {
                try {
                    const r = document.createRange();
                    r.setStart(node, idx);
                    r.setEnd(node, Math.min(idx + hl.text.length, node.textContent.length));
                    const span = document.createElement('span');
                    span.className = 'hl-' + hl.color;
                    span.dataset.hlId = hl.id;
                    r.surroundContents(span);
                } catch {}
                break;
            }
        }
    });
}

// ── Keyboard shortcuts ────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        if (document.getElementById('note-modal-overlay').classList.contains('visible')) {
            document.getElementById('note-modal-cancel').click();
        }
        hideToolbar();
    }
    if (e.key === '/' && !e.ctrlKey && !e.metaKey && document.activeElement.tagName !== 'TEXTAREA' && document.activeElement.tagName !== 'INPUT') {
        e.preventDefault();
        switchTab('toc');
        document.getElementById('toc-search').focus();
    }
});

function esc(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Init ──────────────────────────────────────────────────────────────────
injectButtons();
restoreHighlights();
</script>
</body>
</html>`

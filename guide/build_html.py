#!/usr/bin/env python3
"""Build the PEACE SME Go/Vue/Git guide as a beautiful, premium HTML book reader.

Features:
- Tabbed sidebar: Table of Contents | Bookmarks | Notes
- Text highlight toolbar (4 colors) on selection
- Per-section bookmarks with one click
- Inline notes attached to any section
- All data persisted in localStorage
"""

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

        /* ── Sidebar ── */
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

        .sidebar-header h1 {
            font-size: 1.1rem;
            font-weight: 700;
            color: var(--text-primary);
            line-height: 1.3;
        }

        .sidebar-header p {
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-top: 0.3rem;
        }

        /* Sidebar tabs */
        .sidebar-tabs {
            display: flex;
            border-bottom: 1px solid var(--border);
            flex-shrink: 0;
        }

        .tab-btn {
            flex: 1;
            padding: 0.6rem 0.4rem;
            background: none;
            border: none;
            color: var(--text-secondary);
            font-size: 0.78rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            letter-spacing: 0.02em;
        }

        .tab-btn:hover { color: var(--accent); background: rgba(56,189,248,0.05); }

        .tab-btn.active {
            color: var(--accent);
            border-bottom: 2px solid var(--accent);
            background: rgba(56,189,248,0.08);
        }

        .tab-pane {
            display: none;
            flex: 1;
            overflow-y: auto;
            padding: 1rem 1.25rem;
        }

        .tab-pane.active { display: block; }

        /* Nav list (TOC tab) */
        .nav-list { list-style: none; }
        .nav-item { margin-bottom: 0.35rem; }

        .nav-link {
            display: block;
            padding: 0.5rem 0.75rem;
            color: var(--text-secondary);
            text-decoration: none;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 500;
            transition: all 0.2s;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .nav-link:hover { background: var(--border); color: var(--accent); }

        .nav-link.active {
            background: rgba(56,189,248,0.1);
            color: var(--accent);
            border-left: 3px solid var(--accent);
        }

        /* Bookmarks & Notes panels */
        .panel-empty {
            color: var(--text-secondary);
            font-size: 0.85rem;
            text-align: center;
            padding: 2rem 1rem;
            line-height: 1.8;
        }

        .bm-item, .note-item {
            padding: 0.75rem;
            border: 1px solid var(--border);
            border-radius: 6px;
            margin-bottom: 0.75rem;
            background: rgba(15,23,42,0.5);
            position: relative;
        }

        .bm-item a {
            color: var(--accent);
            font-size: 0.85rem;
            font-weight: 600;
            text-decoration: none;
            display: block;
            margin-bottom: 0.2rem;
        }

        .bm-item a:hover { text-decoration: underline; }

        .bm-ts, .note-ts {
            font-size: 0.72rem;
            color: var(--text-secondary);
        }

        .note-item-section {
            font-size: 0.72rem;
            color: var(--accent);
            margin-bottom: 0.3rem;
            font-weight: 600;
        }

        .note-item-text {
            font-size: 0.85rem;
            color: #cbd5e1;
            white-space: pre-wrap;
            word-break: break-word;
            margin-top: 0.35rem;
        }

        .panel-delete-btn {
            position: absolute;
            top: 0.5rem;
            right: 0.5rem;
            background: none;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 0.85rem;
            padding: 2px 5px;
            border-radius: 4px;
            transition: all 0.15s;
        }

        .panel-delete-btn:hover { color: #f87171; background: rgba(248,113,113,0.1); }

        /* ── Main Content ── */
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
            position: relative;
        }

        section:last-of-type { border-bottom: none; }

        /* Section header wrapper with bookmark button */
        .section-title-row {
            display: flex;
            align-items: flex-start;
            gap: 0.75rem;
            margin-bottom: 1.25rem;
        }

        .section-title-row h1 {
            flex: 1;
            margin-bottom: 0;
        }

        .bookmark-btn {
            flex-shrink: 0;
            margin-top: 0.4rem;
            background: none;
            border: 1px solid var(--border);
            border-radius: 6px;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 1rem;
            padding: 0.3rem 0.5rem;
            transition: all 0.2s;
            opacity: 0;
        }

        section:hover .bookmark-btn { opacity: 1; }

        .bookmark-btn:hover { color: #fbbf24; border-color: #fbbf24; background: rgba(251,191,36,0.1); }
        .bookmark-btn.bookmarked { color: #fbbf24; border-color: #fbbf24; opacity: 1; }

        /* Notes button per section */
        .section-note-btn {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            background: none;
            border: 1px solid var(--border);
            border-radius: 6px;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 0.78rem;
            padding: 0.3rem 0.6rem;
            transition: all 0.2s;
            opacity: 0;
            position: absolute;
            top: 0.6rem;
            right: 3rem;
        }

        section:hover .section-note-btn { opacity: 1; }
        .section-note-btn:hover { color: #a78bfa; border-color: #a78bfa; background: rgba(167,139,250,0.1); }

        .note-badge {
            display: inline-block;
            background: #a78bfa;
            color: #0f172a;
            font-size: 0.65rem;
            font-weight: 700;
            border-radius: 999px;
            padding: 0 5px;
            min-width: 16px;
            text-align: center;
        }

        /* Headings */
        h1, h2, h3, h4 {
            color: var(--text-primary);
            font-weight: 700;
            line-height: 1.25;
        }

        h1 {
            font-size: 2.25rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 0.75rem;
            margin-top: 2rem;
            color: var(--accent);
        }

        h2 { font-size: 1.5rem; margin-top: 3rem; margin-bottom: 1.25rem; color: #e2e8f0; }
        h3 { font-size: 1.15rem; margin-top: 2rem; margin-bottom: 1rem; color: #cbd5e1; }

        p { margin-bottom: 1.5rem; color: #cbd5e1; font-size: 1.05rem; }

        ul, ol { margin-bottom: 1.5rem; padding-left: 2rem; color: #cbd5e1; }
        li { margin-bottom: 0.5rem; }

        table { width: 100%; border-collapse: collapse; margin: 2rem 0; font-size: 0.95rem; }
        th, td { padding: 0.75rem 1rem; border: 1px solid var(--border); text-align: left; }
        th { background-color: var(--bg-secondary); font-weight: 600; color: var(--text-primary); }
        tr:nth-child(even) { background-color: rgba(255,255,255,0.02); }

        .alert {
            padding: 1rem 1.25rem;
            border-left: 4px solid var(--accent);
            background-color: var(--bg-secondary);
            border-radius: 0 8px 8px 0;
            margin: 1.5rem 0;
        }

        .alert-warning { border-left-color: #f59e0b; background-color: rgba(245,158,11,0.05); }

        .expandable-box {
            background-color: rgba(30,41,59,0.4);
            border: 1px solid var(--border);
            border-radius: 8px;
            margin: 1.5rem 0;
            overflow: hidden;
            transition: all 0.3s ease;
        }

        .expandable-box[open] {
            background-color: rgba(30,41,59,0.8);
            border-color: var(--accent);
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }

        .expandable-summary {
            padding: 1rem 1.25rem;
            font-weight: 600;
            color: var(--accent);
            cursor: pointer;
            user-select: none;
            transition: color 0.2s, background-color 0.2s;
            outline: none;
        }

        .expandable-summary:hover { color: var(--accent-hover); background: rgba(255,255,255,0.02); }

        .expandable-content {
            padding: 1.5rem;
            border-top: 1px solid var(--border);
            background-color: rgba(15,23,42,0.6);
        }

        code {
            font-family: 'JetBrains Mono', monospace;
            background-color: var(--code-bg);
            padding: 0.2rem 0.4rem;
            border-radius: 4px;
            font-size: 0.9rem;
            color: #38bdf8;
        }

        pre code { padding: 0; background: transparent; color: inherit; }

        pre {
            background-color: var(--code-bg) !important;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1.25rem !important;
            margin-bottom: 2rem;
            overflow-x: auto;
        }

        a { color: var(--accent); text-decoration: none; transition: color 0.2s; }
        a:hover { color: var(--accent-hover); text-decoration: underline; }

        .font-urdu { font-family: 'Noto Nastaliq Urdu', serif; line-height: 2.2; text-align: right; direction: rtl; }

        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: var(--bg-primary); }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--text-secondary); }

        /* ── Highlights ── */
        .hl-yellow { background: var(--hl-yellow); border-radius: 2px; padding: 1px 0; }
        .hl-green  { background: var(--hl-green);  border-radius: 2px; padding: 1px 0; }
        .hl-pink   { background: var(--hl-pink);   border-radius: 2px; padding: 1px 0; }
        .hl-blue   { background: var(--hl-blue);   border-radius: 2px; padding: 1px 0; }

        /* ── Floating Highlight Toolbar ── */
        #highlight-toolbar {
            display: none;
            position: fixed;
            z-index: 9999;
            background: #1e293b;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 6px 10px;
            gap: 6px;
            align-items: center;
            box-shadow: 0 8px 24px rgba(0,0,0,0.5);
        }

        #highlight-toolbar.visible { display: flex; }

        .hl-color-btn {
            width: 22px;
            height: 22px;
            border-radius: 50%;
            border: 2px solid transparent;
            cursor: pointer;
            transition: transform 0.15s, border-color 0.15s;
        }

        .hl-color-btn:hover { transform: scale(1.2); border-color: white; }
        .hl-color-btn[data-color="yellow"] { background: #facc15; }
        .hl-color-btn[data-color="green"]  { background: #4ade80; }
        .hl-color-btn[data-color="pink"]   { background: #f472b4; }
        .hl-color-btn[data-color="blue"]   { background: #60a5fa; }

        .hl-toolbar-sep { width: 1px; background: var(--border); height: 20px; margin: 0 2px; }

        .hl-note-btn {
            background: none;
            border: none;
            color: #a78bfa;
            cursor: pointer;
            font-size: 0.85rem;
            padding: 2px 4px;
            border-radius: 4px;
            transition: background 0.15s;
        }

        .hl-note-btn:hover { background: rgba(167,139,250,0.15); }

        .hl-clear-btn {
            background: none;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 0.8rem;
            padding: 2px 4px;
            border-radius: 4px;
            transition: all 0.15s;
        }

        .hl-clear-btn:hover { color: #f87171; background: rgba(248,113,113,0.1); }

        /* ── Note Modal ── */
        #note-modal-overlay {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.6);
            z-index: 10000;
            align-items: center;
            justify-content: center;
        }

        #note-modal-overlay.visible { display: flex; }

        #note-modal {
            background: #1e293b;
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            width: 480px;
            max-width: 95vw;
            box-shadow: 0 20px 60px rgba(0,0,0,0.6);
        }

        #note-modal h3 { font-size: 1rem; color: #a78bfa; margin-bottom: 1rem; }

        #note-modal .note-section-label {
            font-size: 0.78rem;
            color: var(--text-secondary);
            margin-bottom: 0.75rem;
        }

        #note-textarea {
            width: 100%;
            min-height: 120px;
            background: var(--code-bg);
            border: 1px solid var(--border);
            border-radius: 6px;
            color: var(--text-primary);
            font-family: 'Inter', sans-serif;
            font-size: 0.9rem;
            padding: 0.75rem;
            resize: vertical;
            outline: none;
        }

        #note-textarea:focus { border-color: #a78bfa; }

        .note-modal-actions {
            display: flex;
            gap: 0.75rem;
            margin-top: 1rem;
            justify-content: flex-end;
        }

        .btn-cancel {
            padding: 0.5rem 1rem;
            border: 1px solid var(--border);
            border-radius: 6px;
            background: none;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 0.9rem;
            transition: all 0.15s;
        }

        .btn-cancel:hover { border-color: var(--text-secondary); color: var(--text-primary); }

        .btn-save {
            padding: 0.5rem 1.25rem;
            border: none;
            border-radius: 6px;
            background: #a78bfa;
            color: #0f172a;
            cursor: pointer;
            font-size: 0.9rem;
            font-weight: 600;
            transition: all 0.15s;
        }

        .btn-save:hover { background: #c4b5fd; }

        /* Note indicators in content */
        .note-dot {
            display: inline-block;
            width: 10px;
            height: 10px;
            background: #a78bfa;
            border-radius: 50%;
            cursor: pointer;
            margin-left: 4px;
            vertical-align: middle;
            transition: transform 0.15s;
        }

        .note-dot:hover { transform: scale(1.4); }

        /* Search bar in TOC */
        .toc-search {
            width: 100%;
            background: var(--code-bg);
            border: 1px solid var(--border);
            border-radius: 6px;
            color: var(--text-primary);
            font-size: 0.82rem;
            padding: 0.45rem 0.75rem;
            outline: none;
            margin-bottom: 0.75rem;
        }

        .toc-search:focus { border-color: var(--accent); }

        /* Reading progress bar */
        #progress-bar {
            position: fixed;
            top: 0;
            left: var(--sidebar-width);
            right: 0;
            height: 3px;
            background: var(--accent);
            transform-origin: left;
            transform: scaleX(0);
            z-index: 100;
            transition: transform 0.1s linear;
        }

        /* Scroll to top button */
        #scroll-top {
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            width: 40px;
            height: 40px;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 50%;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 1.1rem;
            display: flex;
            align-items: center;
            justify-content: center;
            opacity: 0;
            transition: all 0.2s;
            z-index: 50;
        }

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

    <!-- Reading progress bar -->
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

        <!-- TOC Tab -->
        <div class="tab-pane active" id="tab-toc">
            <input type="text" class="toc-search" id="toc-search" placeholder="Filter chapters…" />
            <nav>
                <ul class="nav-list" id="nav-list">
                    {{sidebar_links}}
                </ul>
            </nav>
        </div>

        <!-- Bookmarks Tab -->
        <div class="tab-pane" id="tab-bookmarks">
            <div id="bookmarks-panel">
                <div class="panel-empty">
                    No bookmarks yet.<br>
                    Hover over a chapter and click ★ to save it.
                </div>
            </div>
        </div>

        <!-- Notes Tab -->
        <div class="tab-pane" id="tab-notes">
            <div id="notes-panel">
                <div class="panel-empty">
                    No notes yet.<br>
                    Select text or hover a chapter and click 📝 to add a note.
                </div>
            </div>
        </div>
    </aside>

    <main id="main-content">
        {{chapters_content}}
    </main>

    <!-- Floating highlight toolbar -->
    <div id="highlight-toolbar">
        <button class="hl-color-btn" data-color="yellow" title="Highlight yellow"></button>
        <button class="hl-color-btn" data-color="green"  title="Highlight green"></button>
        <button class="hl-color-btn" data-color="pink"   title="Highlight pink"></button>
        <button class="hl-color-btn" data-color="blue"   title="Highlight blue"></button>
        <div class="hl-toolbar-sep"></div>
        <button class="hl-note-btn" title="Add note">📝 Note</button>
        <button class="hl-clear-btn" title="Clear highlight">✕</button>
    </div>

    <!-- Note modal -->
    <div id="note-modal-overlay">
        <div id="note-modal">
            <h3>📝 Add Note</h3>
            <div class="note-section-label" id="note-modal-section-label"></div>
            <textarea id="note-textarea" placeholder="Write your note here…"></textarea>
            <div class="note-modal-actions">
                <button class="btn-cancel" id="note-modal-cancel">Cancel</button>
                <button class="btn-save" id="note-modal-save">Save Note</button>
            </div>
        </div>
    </div>

    <!-- Scroll to top -->
    <button id="scroll-top" title="Scroll to top">↑</button>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-core.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/autoloader/prism-autoloader.min.js"></script>

    <script>
    // ═══════════════════════════════════════════════════════════════════
    //  DATA LAYER — localStorage keys
    // ═══════════════════════════════════════════════════════════════════
    const KEYS = {
        bookmarks:  'sme_guide_bookmarks',
        highlights: 'sme_guide_highlights',
        notes:      'sme_guide_notes',
    };

    function load(key) {
        try { return JSON.parse(localStorage.getItem(key) || (key === KEYS.bookmarks ? '{}' : '[]')); }
        catch { return key === KEYS.bookmarks ? {} : []; }
    }

    function save(key, data) {
        localStorage.setItem(key, JSON.stringify(data));
    }

    // ═══════════════════════════════════════════════════════════════════
    //  SIDEBAR TABS
    // ═══════════════════════════════════════════════════════════════════
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

    // ═══════════════════════════════════════════════════════════════════
    //  TOC SEARCH FILTER
    // ═══════════════════════════════════════════════════════════════════
    document.getElementById('toc-search').addEventListener('input', function() {
        const q = this.value.toLowerCase();
        document.querySelectorAll('#nav-list .nav-item').forEach(item => {
            const text = item.textContent.toLowerCase();
            item.style.display = text.includes(q) ? '' : 'none';
        });
    });

    // ═══════════════════════════════════════════════════════════════════
    //  ACTIVE NAV HIGHLIGHTER + READING PROGRESS
    // ═══════════════════════════════════════════════════════════════════
    const sections = document.querySelectorAll('section');
    const navLinks = document.querySelectorAll('.nav-link');
    const progressBar = document.getElementById('progress-bar');
    const scrollTopBtn = document.getElementById('scroll-top');

    function updateProgress() {
        const scrolled = window.scrollY;
        const total = document.body.scrollHeight - window.innerHeight;
        const pct = total > 0 ? scrolled / total : 0;
        progressBar.style.transform = `scaleX(${pct})`;
        scrollTopBtn.classList.toggle('visible', scrolled > 400);

        let current = '';
        sections.forEach(sec => {
            if (window.scrollY >= (sec.offsetTop - 150)) current = sec.getAttribute('id');
        });
        navLinks.forEach(link => {
            link.classList.toggle('active', link.getAttribute('href').includes(current));
        });
    }

    window.addEventListener('scroll', updateProgress, { passive: true });

    scrollTopBtn.addEventListener('click', () => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });

    // ═══════════════════════════════════════════════════════════════════
    //  BOOKMARKS
    // ═══════════════════════════════════════════════════════════════════
    function getSectionTitle(sec) {
        const h1 = sec.querySelector('h1');
        return h1 ? h1.textContent.trim() : sec.id;
    }

    function injectBookmarkButtons() {
        sections.forEach(sec => {
            const h1 = sec.querySelector('h1');
            if (!h1) return;

            // Wrap h1 in a title row div
            const row = document.createElement('div');
            row.className = 'section-title-row';
            h1.parentNode.insertBefore(row, h1);
            row.appendChild(h1);

            // Bookmark button
            const btn = document.createElement('button');
            btn.className = 'bookmark-btn';
            btn.title = 'Bookmark this chapter';
            btn.textContent = '★';
            row.appendChild(btn);

            // Note button
            const noteBtn = document.createElement('button');
            noteBtn.className = 'section-note-btn';
            noteBtn.innerHTML = '📝 <span class="note-badge-inline"></span>';
            noteBtn.title = 'Add note to this chapter';
            sec.appendChild(noteBtn);

            updateBookmarkBtn(btn, sec.id);

            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                toggleBookmark(sec.id, getSectionTitle(sec));
                updateBookmarkBtn(btn, sec.id);
            });

            noteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                openNoteModal(sec.id, getSectionTitle(sec));
            });

            updateNoteBadge(noteBtn, sec.id);
        });
    }

    function updateBookmarkBtn(btn, sectionId) {
        const bms = load(KEYS.bookmarks);
        btn.classList.toggle('bookmarked', !!bms[sectionId]);
        btn.title = bms[sectionId] ? 'Remove bookmark' : 'Bookmark this chapter';
    }

    function updateNoteBadge(btn, sectionId) {
        const notes = load(KEYS.notes);
        const count = notes.filter(n => n.sectionId === sectionId).length;
        const badge = btn.querySelector('.note-badge-inline');
        if (badge) badge.textContent = count > 0 ? count : '';
    }

    function toggleBookmark(sectionId, title) {
        const bms = load(KEYS.bookmarks);
        if (bms[sectionId]) {
            delete bms[sectionId];
        } else {
            bms[sectionId] = { title, timestamp: Date.now() };
        }
        save(KEYS.bookmarks, bms);
    }

    function renderBookmarks() {
        const panel = document.getElementById('bookmarks-panel');
        const bms = load(KEYS.bookmarks);
        const entries = Object.entries(bms).sort((a, b) => b[1].timestamp - a[1].timestamp);

        if (!entries.length) {
            panel.innerHTML = '<div class="panel-empty">No bookmarks yet.<br>Hover over a chapter and click ★ to save it.</div>';
            return;
        }

        panel.innerHTML = entries.map(([id, { title, timestamp }]) => `
            <div class="bm-item">
                <a href="#${id}" onclick="switchToTOC()">${title}</a>
                <div class="bm-ts">${new Date(timestamp).toLocaleDateString()}</div>
                <button class="panel-delete-btn" onclick="removeBookmark('${id}')">✕</button>
            </div>
        `).join('');
    }

    window.removeBookmark = function(sectionId) {
        const bms = load(KEYS.bookmarks);
        delete bms[sectionId];
        save(KEYS.bookmarks, bms);
        renderBookmarks();
        // Update the bookmark button in the page
        const sec = document.getElementById(sectionId);
        if (sec) {
            const btn = sec.querySelector('.bookmark-btn');
            if (btn) updateBookmarkBtn(btn, sectionId);
        }
    };

    window.switchToTOC = function() {
        document.querySelector('[data-tab="toc"]').click();
    };

    // ═══════════════════════════════════════════════════════════════════
    //  NOTES
    // ═══════════════════════════════════════════════════════════════════
    let _noteContext = null;  // { sectionId, sectionTitle }

    function openNoteModal(sectionId, sectionTitle) {
        _noteContext = { sectionId, sectionTitle };
        document.getElementById('note-modal-section-label').textContent = 'Chapter: ' + sectionTitle;
        document.getElementById('note-textarea').value = '';
        document.getElementById('note-modal-overlay').classList.add('visible');
        setTimeout(() => document.getElementById('note-textarea').focus(), 50);
    }

    document.getElementById('note-modal-cancel').addEventListener('click', () => {
        document.getElementById('note-modal-overlay').classList.remove('visible');
        _noteContext = null;
    });

    document.getElementById('note-modal-overlay').addEventListener('click', (e) => {
        if (e.target === document.getElementById('note-modal-overlay')) {
            document.getElementById('note-modal-cancel').click();
        }
    });

    document.getElementById('note-modal-save').addEventListener('click', () => {
        const text = document.getElementById('note-textarea').value.trim();
        if (!text || !_noteContext) return;

        const notes = load(KEYS.notes);
        notes.unshift({
            id: Date.now().toString(),
            sectionId: _noteContext.sectionId,
            sectionTitle: _noteContext.sectionTitle,
            text,
            timestamp: Date.now(),
        });
        save(KEYS.notes, notes);

        document.getElementById('note-modal-overlay').classList.remove('visible');
        _noteContext = null;

        // Update badge
        const sec = document.getElementById(notes[0].sectionId);
        if (sec) {
            const noteBtn = sec.querySelector('.section-note-btn');
            if (noteBtn) updateNoteBadge(noteBtn, notes[0].sectionId);
        }
    });

    // Ctrl+Enter to save note
    document.getElementById('note-textarea').addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.key === 'Enter') document.getElementById('note-modal-save').click();
    });

    function renderNotes() {
        const panel = document.getElementById('notes-panel');
        const notes = load(KEYS.notes);

        if (!notes.length) {
            panel.innerHTML = '<div class="panel-empty">No notes yet.<br>Hover a chapter and click 📝 to add a note.</div>';
            return;
        }

        panel.innerHTML = notes.map(note => `
            <div class="note-item">
                <div class="note-item-section">
                    <a href="#${note.sectionId}" onclick="switchToTOC()">${note.sectionTitle}</a>
                </div>
                <div class="note-item-text">${escapeHtml(note.text)}</div>
                <div class="note-ts">${new Date(note.timestamp).toLocaleString()}</div>
                <button class="panel-delete-btn" onclick="removeNote('${note.id}')">✕</button>
            </div>
        `).join('');
    }

    window.removeNote = function(noteId) {
        let notes = load(KEYS.notes);
        const note = notes.find(n => n.id === noteId);
        notes = notes.filter(n => n.id !== noteId);
        save(KEYS.notes, notes);
        renderNotes();
        // Update badge
        if (note) {
            const sec = document.getElementById(note.sectionId);
            if (sec) {
                const noteBtn = sec.querySelector('.section-note-btn');
                if (noteBtn) updateNoteBadge(noteBtn, note.sectionId);
            }
        }
    };

    function escapeHtml(str) {
        return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    // ═══════════════════════════════════════════════════════════════════
    //  HIGHLIGHTS
    // ═══════════════════════════════════════════════════════════════════
    const toolbar = document.getElementById('highlight-toolbar');
    let _pendingRange = null;  // the saved Range when toolbar is shown

    function getClosestSection(node) {
        let el = node.nodeType === 3 ? node.parentElement : node;
        while (el && el.tagName !== 'SECTION') el = el.parentElement;
        return el;
    }

    document.addEventListener('mouseup', (e) => {
        // Don't trigger inside toolbar or modal
        if (toolbar.contains(e.target)) return;
        if (document.getElementById('note-modal-overlay').contains(e.target)) return;

        const sel = window.getSelection();
        if (!sel || sel.isCollapsed || !sel.toString().trim()) {
            hideToolbar();
            return;
        }

        const text = sel.toString().trim();
        if (text.length < 3) { hideToolbar(); return; }

        _pendingRange = sel.getRangeAt(0).cloneRange();

        // Position toolbar above selection
        const rect = _pendingRange.getBoundingClientRect();
        toolbar.style.top = (rect.top + window.scrollY - 48) + 'px';
        toolbar.style.left = (rect.left + rect.width / 2 - 100) + 'px';
        toolbar.classList.add('visible');
    });

    document.addEventListener('mousedown', (e) => {
        if (!toolbar.contains(e.target)) hideToolbar();
    });

    function hideToolbar() {
        toolbar.classList.remove('visible');
        _pendingRange = null;
    }

    // Color buttons
    document.querySelectorAll('.hl-color-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (!_pendingRange) return;
            applyHighlight(_pendingRange, btn.dataset.color);
            hideToolbar();
            window.getSelection().removeAllRanges();
        });
    });

    // Note from selection
    document.querySelector('.hl-note-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        if (!_pendingRange) return;
        const sec = getClosestSection(_pendingRange.startContainer);
        const sectionId = sec ? sec.id : 'unknown';
        const sectionTitle = sec ? getSectionTitle(sec) : sectionId;
        const selectedText = _pendingRange.toString().trim().substring(0, 120);
        hideToolbar();
        window.getSelection().removeAllRanges();
        openNoteModal(sectionId, sectionTitle);
        // Pre-fill textarea with selected quote
        setTimeout(() => {
            const ta = document.getElementById('note-textarea');
            if (selectedText) ta.value = `"${selectedText}"\n\n`;
            ta.setSelectionRange(ta.value.length, ta.value.length);
        }, 60);
    });

    // Clear highlight (if clicking on existing highlight)
    document.querySelector('.hl-clear-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        if (!_pendingRange) return;
        // Find any highlight spans in the range and unwrap them
        const ancestor = _pendingRange.commonAncestorContainer;
        const container = ancestor.nodeType === 3 ? ancestor.parentElement : ancestor;
        container.querySelectorAll('.hl-yellow,.hl-green,.hl-pink,.hl-blue').forEach(span => {
            if (_pendingRange.intersectsNode(span)) {
                const parent = span.parentNode;
                while (span.firstChild) parent.insertBefore(span.firstChild, span);
                span.remove();
            }
        });
        hideToolbar();
        window.getSelection().removeAllRanges();
        // Rebuild highlights from DOM state and save
        saveHighlightsFromDOM();
    });

    function applyHighlight(range, color) {
        const sec = getClosestSection(range.startContainer);
        const sectionId = sec ? sec.id : 'unknown';
        const text = range.toString().trim();
        if (!text) return;

        try {
            const span = document.createElement('span');
            span.className = 'hl-' + color;
            span.dataset.hlId = Date.now().toString();
            range.surroundContents(span);
        } catch {
            // surroundContents fails if selection crosses element boundaries
            // Fallback: wrap each text node
            const frag = range.extractContents();
            const span = document.createElement('span');
            span.className = 'hl-' + color;
            span.dataset.hlId = Date.now().toString();
            span.appendChild(frag);
            range.insertNode(span);
        }

        // Save to localStorage
        const highlights = load(KEYS.highlights);
        highlights.push({
            id: Date.now().toString(),
            sectionId,
            text: text.substring(0, 300),
            color,
            timestamp: Date.now(),
        });
        save(KEYS.highlights, highlights);
    }

    function saveHighlightsFromDOM() {
        const highlights = [];
        document.querySelectorAll('[class^="hl-"]').forEach(span => {
            const sec = getClosestSection(span);
            highlights.push({
                id: span.dataset.hlId || Date.now().toString(),
                sectionId: sec ? sec.id : 'unknown',
                text: span.textContent.trim().substring(0, 300),
                color: span.className.replace('hl-', ''),
                timestamp: Date.now(),
            });
        });
        save(KEYS.highlights, highlights);
    }

    function restoreHighlights() {
        const highlights = load(KEYS.highlights);
        if (!highlights.length) return;

        highlights.forEach(hl => {
            const sec = document.getElementById(hl.sectionId);
            if (!sec || !hl.text) return;

            // Find the text in the section using TreeWalker
            const walker = document.createTreeWalker(sec, NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walker.nextNode())) {
                const idx = node.textContent.indexOf(hl.text.substring(0, 50));
                if (idx !== -1) {
                    try {
                        const range = document.createRange();
                        range.setStart(node, idx);
                        range.setEnd(node, Math.min(idx + hl.text.length, node.textContent.length));
                        const span = document.createElement('span');
                        span.className = 'hl-' + hl.color;
                        span.dataset.hlId = hl.id;
                        range.surroundContents(span);
                    } catch { /* skip problematic nodes */ }
                    break;
                }
            }
        });
    }

    // ═══════════════════════════════════════════════════════════════════
    //  KEYBOARD SHORTCUTS
    // ═══════════════════════════════════════════════════════════════════
    document.addEventListener('keydown', (e) => {
        // Escape closes modal / toolbar
        if (e.key === 'Escape') {
            if (document.getElementById('note-modal-overlay').classList.contains('visible')) {
                document.getElementById('note-modal-cancel').click();
            }
            hideToolbar();
        }
        // / focuses TOC search
        if (e.key === '/' && !e.ctrlKey && !e.metaKey && document.activeElement.tagName !== 'TEXTAREA' && document.activeElement.tagName !== 'INPUT') {
            e.preventDefault();
            document.querySelector('[data-tab="toc"]').click();
            document.getElementById('toc-search').focus();
        }
    });

    // ═══════════════════════════════════════════════════════════════════
    //  INIT
    // ═══════════════════════════════════════════════════════════════════
    injectBookmarkButtons();
    restoreHighlights();
    </script>
</body>
</html>
"""


def parse_markdown_to_html(md_text: str) -> str:
    html_out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", md_text)
    html_out = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", html_out)

    lines = html_out.splitlines()
    parsed_lines = []

    in_code_block = False
    in_list = False
    in_ordered_list = False
    in_table = False

    for line in lines:
        striped_line = line.strip()

        # Expandable blocks
        if striped_line.startswith(":::expandable"):
            match = re.search(r"\[([^\]]+)\]", striped_line)
            topic = match.group(1) if match else "Deep Dive"
            parsed_lines.append(
                f'<details class="expandable-box"><summary class="expandable-summary">'
                f'Deep Dive: {topic} (Click to expand)</summary><div class="expandable-content">'
            )
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
                lang = striped_line[3:].strip() or "text"
                parsed_lines.append(f'<pre><code class="language-{lang}">')
                in_code_block = True
            continue

        if in_code_block:
            parsed_lines.append(html.escape(line))
            continue

        # Ordered lists
        ordered_match = re.match(r"^\d+\.\s+(.+)$", striped_line)
        if ordered_match:
            if not in_ordered_list:
                if in_list:
                    parsed_lines.append("</ul>")
                    in_list = False
                parsed_lines.append("<ol>")
                in_ordered_list = True
            content = ordered_match.group(1)
            content = re.sub(r"`([^`]+)`", r"<code>\1</code>", content)
            content = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', content)
            parsed_lines.append(f"<li>{content}</li>")
            continue
        elif in_ordered_list and not striped_line:
            parsed_lines.append("</ol>")
            in_ordered_list = False

        # Unordered lists
        if striped_line.startswith("- ") or striped_line.startswith("* "):
            if not in_list:
                if in_ordered_list:
                    parsed_lines.append("</ol>")
                    in_ordered_list = False
                parsed_lines.append("<ul>")
                in_list = True
            content = re.sub(r"^[-*]\s+", "", line).strip()
            content = re.sub(r"`([^`]+)`", r"<code>\1</code>", content)
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
            header_text = re.sub(r"`([^`]+)`", r"<code>\1</code>", header_text)
            parsed_lines.append(f"<h{level}>{header_text}</h{level}>")
            continue

        # Horizontal rules
        if striped_line in ("---", "***", "___"):
            parsed_lines.append("<hr style='margin: 2rem 0; border: none; border-top: 1px solid var(--border);'>")
            continue

        # Alert blocks
        if striped_line.startswith(">"):
            alert_content = striped_line.lstrip('>').strip()
            if alert_content.startswith("[!WARNING]"):
                parsed_lines.append(f'<div class="alert alert-warning"><strong>⚠ WARNING:</strong> {alert_content[10:].strip()}</div>')
            elif alert_content.startswith("[!NOTE]"):
                parsed_lines.append(f'<div class="alert"><strong>ℹ NOTE:</strong> {alert_content[7:].strip()}</div>')
            else:
                parsed_lines.append(f'<div class="alert">{alert_content}</div>')
            continue

        # Tables
        if striped_line.startswith("|"):
            if not in_table:
                parsed_lines.append("<table>")
                in_table = True
            if "---" in striped_line:
                continue
            cells = [c.strip() for c in striped_line.split("|")[1:-1]]
            tag = "th" if parsed_lines[-1] == "<table>" else "td"
            cell_html = "".join(
                f"<{tag}>{re.sub(r'`([^`]+)`', r'<code>\1</code>', cell)}</{tag}>"
                for cell in cells
            )
            parsed_lines.append(f"<tr>{cell_html}</tr>")
            continue
        elif in_table and not striped_line.startswith("|"):
            parsed_lines.append("</table>")
            in_table = False

        # Regular paragraph
        if striped_line:
            para = re.sub(r"`([^`]+)`", r"<code>\1</code>", line)
            para = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', para)
            if any(0x0600 <= ord(c) <= 0x06FF for c in para):
                parsed_lines.append(f'<p class="font-urdu">{para}</p>')
            else:
                parsed_lines.append(f"<p>{para}</p>")

    if in_list:
        parsed_lines.append("</ul>")
    if in_ordered_list:
        parsed_lines.append("</ol>")
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

        if content.startswith("---"):
            _, _, content = content.split("---", 2)

        section_id = f"chap-{idx}"

        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = title_match.group(1) if title_match else filepath.stem.replace("-", " ").title()

        sidebar_links.append(
            f'<li class="nav-item"><a class="nav-link" href="#{section_id}">{title}</a></li>'
        )

        html_content = parse_markdown_to_html(content)
        chapters_content.append(f'<section id="{section_id}">{html_content}</section>')

    html_out = HTML_TEMPLATE.replace(
        "{{sidebar_links}}", "\n".join(sidebar_links)
    ).replace(
        "{{chapters_content}}", "\n".join(chapters_content)
    )

    OUTPUT.write_text(html_out, encoding="utf-8")
    print(f"Generated HTML book reader at {OUTPUT}")
    print(f"  Chapters: {len(chapters_content)}")
    print(f"  File size: {OUTPUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    build_html()

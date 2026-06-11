#!/usr/bin/env python3
"""Build the PEACE SME Go/Vue/Git guide as a bookmarked PDF."""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

TOOL_PATH = Path("/tmp/peace_pdf_tools")
if TOOL_PATH.exists():
    sys.path.insert(0, str(TOOL_PATH))

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "peace-sme-go-vue-git-book.pdf"

FILES = [
    ROOT / "README.md",
    ROOT / "concept-index.md",
    *sorted((ROOT / "chapters").glob("*.md")),
]


class BookmarkDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str, **kwargs):
        super().__init__(filename, **kwargs)
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="normal",
        )
        self.addPageTemplates(
            [
                PageTemplate(
                    id="main",
                    frames=[frame],
                    onPage=self._draw_page,
                )
            ]
        )

    def _draw_page(self, canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawString(2 * cm, 1.2 * cm, "Master Go, Vue, and Git by Rebuilding the PEACE SME Grant Portal")
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, str(doc.page))
        canvas.restoreState()

    def afterFlowable(self, flowable):
        bookmark = getattr(flowable, "_bookmark", None)
        if not bookmark:
            return
        text, key, level = bookmark
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(text, key, level=level, closed=False)


def clean_inline(text: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", text)
    text = text.replace("—", "-")
    return html.escape(text, quote=False).replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>").replace(
        "&lt;i&gt;", "<i>"
    ).replace("&lt;/i&gt;", "</i>").replace("&lt;font name='Courier'&gt;", "<font name='Courier'>").replace(
        "&lt;/font&gt;", "</font>"
    )


def make_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "BookTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=26,
            leading=32,
            alignment=TA_CENTER,
            spaceAfter=18,
            textColor=colors.HexColor("#17324d"),
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontSize=13,
            leading=18,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#3d4b5c"),
            spaceAfter=28,
        ),
        "h1": ParagraphStyle(
            "Heading1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            spaceBefore=12,
            spaceAfter=12,
            textColor=colors.HexColor("#17324d"),
        ),
        "h2": ParagraphStyle(
            "Heading2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            spaceBefore=12,
            spaceAfter=8,
            textColor=colors.HexColor("#244b6b"),
        ),
        "h3": ParagraphStyle(
            "Heading3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            spaceBefore=8,
            spaceAfter=5,
            textColor=colors.HexColor("#2f5f7f"),
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.4,
            leading=13.2,
            spaceAfter=6,
            alignment=TA_LEFT,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=12.5,
            leftIndent=12,
            firstLineIndent=0,
            spaceAfter=3,
        ),
        "code": ParagraphStyle(
            "Code",
            parent=base["Code"],
            fontName="Courier",
            fontSize=7.6,
            leading=9.4,
            leftIndent=6,
            rightIndent=6,
            borderWidth=0.5,
            borderColor=colors.HexColor("#d9dee7"),
            borderPadding=6,
            backColor=colors.HexColor("#f6f8fa"),
            spaceBefore=4,
            spaceAfter=8,
        ),
        "table": ParagraphStyle(
            "TableCell",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.4,
            leading=9.2,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.3,
            leading=9,
            textColor=colors.white,
        ),
    }


def add_heading(story, styles, text: str, level: int, bookmark_id: int) -> int:
    style = styles.get(f"h{min(level, 3)}", styles["h3"])
    para = Paragraph(clean_inline(text), style)
    key = f"bookmark-{bookmark_id}"
    para._bookmark = (re.sub(r"<[^>]+>", "", text), key, min(level - 1, 2))
    if level == 1 and story:
        story.append(PageBreak())
    story.append(para)
    return bookmark_id + 1


def parse_table(lines, start, styles):
    rows = []
    i = start
    while i < len(lines):
        line = lines[i].strip()
        if not (line.startswith("|") and line.endswith("|")):
            break
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", c or "") for c in cells):
            i += 1
            continue
        style = styles["table_header"] if not rows else styles["table"]
        rows.append([Paragraph(clean_inline(cell), style) for cell in cells])
        i += 1
    if not rows:
        return None, start
    table = Table(rows, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#244b6b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#ccd3dc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table, i


def flush_paragraph(story, styles, paragraph_lines):
    if not paragraph_lines:
        return
    text = " ".join(line.strip() for line in paragraph_lines).strip()
    if text:
        story.append(Paragraph(clean_inline(text), styles["body"]))
    paragraph_lines.clear()


def build_story():
    styles = make_styles()
    story = [
        Spacer(1, 5 * cm),
        Paragraph("Master Go, Vue, and Git", styles["title"]),
        Paragraph("By Rebuilding the PEACE SME Grant Portal", styles["subtitle"]),
        Paragraph(
            "A practical, chapter-by-chapter workbook generated from the application specification.",
            styles["subtitle"],
        ),
        PageBreak(),
    ]

    bookmark_id = 1
    paragraph_lines = []

    for file_path in FILES:
        lines = file_path.read_text(encoding="utf-8").splitlines()
        i = 0
        in_code = False
        code_lines = []

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if stripped.startswith("```"):
                if in_code:
                    story.append(Preformatted("\n".join(code_lines), styles["code"], maxLineLength=95))
                    code_lines = []
                    in_code = False
                else:
                    flush_paragraph(story, styles, paragraph_lines)
                    in_code = True
                i += 1
                continue

            if in_code:
                code_lines.append(line)
                i += 1
                continue

            if not stripped:
                flush_paragraph(story, styles, paragraph_lines)
                i += 1
                continue

            heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if heading_match:
                flush_paragraph(story, styles, paragraph_lines)
                level = len(heading_match.group(1))
                bookmark_id = add_heading(story, styles, heading_match.group(2), level, bookmark_id)
                i += 1
                continue

            if stripped.startswith("|") and stripped.endswith("|"):
                flush_paragraph(story, styles, paragraph_lines)
                table, i = parse_table(lines, i, styles)
                if table:
                    story.append(table)
                    story.append(Spacer(1, 6))
                continue

            if stripped.startswith(("- ", "* ")):
                flush_paragraph(story, styles, paragraph_lines)
                items = []
                while i < len(lines) and lines[i].strip().startswith(("- ", "* ")):
                    item_text = lines[i].strip()[2:].strip()
                    items.append(ListItem(Paragraph(clean_inline(item_text), styles["bullet"])))
                    i += 1
                story.append(ListFlowable(items, bulletType="bullet", start="circle", leftIndent=15))
                story.append(Spacer(1, 3))
                continue

            ordered_match = re.match(r"^\d+\.\s+(.+)$", stripped)
            if ordered_match:
                flush_paragraph(story, styles, paragraph_lines)
                items = []
                while i < len(lines):
                    match = re.match(r"^\d+\.\s+(.+)$", lines[i].strip())
                    if not match:
                        break
                    items.append(ListItem(Paragraph(clean_inline(match.group(1)), styles["bullet"])))
                    i += 1
                story.append(ListFlowable(items, bulletType="1", leftIndent=18))
                story.append(Spacer(1, 3))
                continue

            if stripped == "---":
                flush_paragraph(story, styles, paragraph_lines)
                story.append(Spacer(1, 8))
                i += 1
                continue

            if stripped.startswith(">"):
                stripped = stripped.lstrip("> ").strip()

            paragraph_lines.append(stripped)
            i += 1

        flush_paragraph(story, styles, paragraph_lines)

    return story


def main():
    doc = BookmarkDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=1.8 * cm,
        leftMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title="Master Go, Vue, and Git by Rebuilding the PEACE SME Grant Portal",
        author="PEACE SME Grant Portal Guide",
    )
    doc.build(build_story())
    print(OUTPUT)


if __name__ == "__main__":
    main()


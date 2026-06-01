"""Generate the Account 250031 Risk Brief PDF in English and Simplified Chinese.

Two output files, same design, content swapped per language.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer,
    Table, TableStyle,
)


pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

# -------------------------------------------------------------------
# Palette
# -------------------------------------------------------------------
NAVY = colors.HexColor("#1f3a68")
ACCENT = colors.HexColor("#2563eb")
SUCCESS = colors.HexColor("#16a34a")
DANGER = colors.HexColor("#dc2626")
WARNING = colors.HexColor("#d97706")
LIGHT_BG = colors.HexColor("#f3f4f6")
VERDICT_BG = colors.HexColor("#1f3a68")
HABIT_BG = colors.HexColor("#fef2f2")
BOTTOM_BG = colors.HexColor("#eff6ff")
BORDER = colors.HexColor("#cbd5e1")
TEXT = colors.HexColor("#111827")
MUTED = colors.HexColor("#475569")


def build_styles(fn: str, fb: str) -> dict:
    return {
        "title": ParagraphStyle("title", fontName=fb, fontSize=22, leading=27,
                                 textColor=NAVY, spaceAfter=2),
        "subtitle": ParagraphStyle("subtitle", fontName=fn, fontSize=11, leading=14,
                                    textColor=MUTED, spaceAfter=2),
        "meta": ParagraphStyle("meta", fontName=fn, fontSize=9, leading=12,
                               textColor=MUTED),
        "verdict": ParagraphStyle("verdict", fontName=fb, fontSize=13, leading=18,
                                  textColor=colors.white),
        "h2": ParagraphStyle("h2", fontName=fb, fontSize=13, leading=17,
                              textColor=NAVY, spaceBefore=14, spaceAfter=6),
        "body": ParagraphStyle("body", fontName=fn, fontSize=10.5, leading=15,
                               textColor=TEXT, alignment=TA_JUSTIFY, spaceAfter=4),
        "bullet": ParagraphStyle("bullet", fontName=fn, fontSize=10.5, leading=15,
                                 textColor=TEXT, leftIndent=14, spaceAfter=2,
                                 bulletIndent=2),
        "callout": ParagraphStyle("callout", fontName=fn, fontSize=10, leading=14,
                                  textColor=TEXT, alignment=TA_JUSTIFY),
        "cell": ParagraphStyle("cell", fontName=fn, fontSize=9.5, leading=12.5,
                               textColor=TEXT),
        "cell_b": ParagraphStyle("cell_b", fontName=fb, fontSize=9.5, leading=12.5,
                                 textColor=NAVY),
        "cell_hdr": ParagraphStyle("cell_hdr", fontName=fb, fontSize=9.5, leading=12.5,
                                   textColor=colors.white),
        "bottom": ParagraphStyle("bottom", fontName=fn, fontSize=10.5, leading=15,
                                 textColor=TEXT, alignment=TA_JUSTIFY),
    }


# ===================================================================
# Content
# ===================================================================
EN = {
    "lang": "en",
    "fn": "Helvetica",
    "fb": "Helvetica-Bold",
    "filename": "Risk_Brief_Account_250031_EN.pdf",
    "title": "Account 250031 — Risk Brief",
    "subtitle": "Prepared for the broker",
    "meta": "Confidential · " + date.today().isoformat(),
    "verdict_label": "VERDICT",
    "verdict": "Clean. Not gaming you. A profitable client with a self-destructive habit.",
    "trades_h": "The trades",
    "trades_bullets": [
        "108 trades, all gold, over 5 days",
        "87 winning trades, 21 losing trades (80% win rate)",
        "The 87 wins made <b>+7,527</b>",
        "The 21 losses cost <b>-5,186</b>",
        "He keeps only <b>+2,341</b>",
    ],
    "trades_callout": (
        "In plain terms: 21 losses ate two-thirds of what 87 wins earned. "
        "It takes him about <b>3 winning trades to cover 1 losing trade</b>."
    ),
    "habit_h": "The dangerous habit",
    "habit_intro": (
        "He does the opposite of what a disciplined trader should do:"
    ),
    "habit_headers": ["Situation", "What he does", "What he should do"],
    "habit_rows": [
        ["Winning trades", "Closes them fast (about 8 minutes)", "Let them run"],
        ["Losing trades", "Holds them until the stop-loss hits (about 18 minutes)",
         "Cut them fast"],
    ],
    "habit_note": (
        "He grabs small wins quickly and lets losers bleed. This is why his "
        "average loss (-247) is almost 3 times his average win (+86)."
    ),
    "rr_h": "Risk and reward",
    "rr_bullets": [
        "He risks about 2 to make 1 (reward-to-risk roughly 0.4 to 1)",
        "This only stays profitable while his win rate is above 74%",
        "He is at 80%, a thin 6-point cushion",
        "One bad week and the math flips against him",
    ],
    "checks_h": "Risk checks",
    "checks_headers": ["Check", "Result"],
    "checks_rows": [
        ["Latency arbitrage", "Clear"],
        ["Scalping", "Clear (holds positions too long to be a real scalper)"],
        ["Swap arbitrage", "Clear"],
        ["Bonus abuse", "Clear"],
        ["Only points to watch",
         "Trades gold 100% of the time; activity rising fast (3 to 52 trades per day)"],
    ],
    "bottom_h": "Bottom line for the broker",
    "bottom": (
        "He is not a threat and not abusing anything. He is a skilled-looking "
        "trader with an upside-down risk habit. The math says a client who cuts "
        "winners short and rides losers gives the profit back over time. No "
        "action needed now. Worth tagging as a \"fragile profitable client\" and "
        "watching whether the +2,341 survives the next trending week."
    ),
}

ZH = {
    "lang": "zh",
    "fn": "STSong-Light",
    "fb": "STSong-Light",
    "filename": "Risk_Brief_Account_250031_ZH.pdf",
    "title": "账户 250031 — 风险简报",
    "subtitle": "为经纪商准备",
    "meta": "机密 · " + date.today().isoformat(),
    "verdict_label": "结论",
    "verdict": "干净。没有对你做手脚。是一个有自毁习惯的盈利客户。",
    "trades_h": "交易概况",
    "trades_bullets": [
        "108 笔交易,全部是黄金,持续 5 天",
        "87 笔盈利,21 笔亏损(胜率 80%)",
        "87 笔盈利共赚 <b>+7,527</b>",
        "21 笔亏损共亏 <b>-5,186</b>",
        "他最终只保住 <b>+2,341</b>",
    ],
    "trades_callout": (
        "简单说:21 笔亏损吃掉了 87 笔盈利的三分之二。他大约需要 "
        "<b>3 笔盈利交易才能弥补 1 笔亏损交易</b>。"
    ),
    "habit_h": "危险的习惯",
    "habit_intro": "他的做法与一个有纪律的交易者应该做的恰恰相反:",
    "habit_headers": ["情况", "他的做法", "正确的做法"],
    "habit_rows": [
        ["盈利交易", "很快平仓(约 8 分钟)", "让利润继续奔跑"],
        ["亏损交易", "一直持有,直到触及止损(约 18 分钟)", "尽快止损"],
    ],
    "habit_note": (
        "他快速抓住小额盈利,却让亏损不断扩大。这就是为什么他的平均亏损"
        "(-247)几乎是平均盈利(+86)的 3 倍。"
    ),
    "rr_h": "风险与回报",
    "rr_bullets": [
        "他大约用 2 的风险去换 1 的回报(回报风险比约为 0.4 比 1)",
        "只有当胜率高于 74% 时,这套打法才能盈利",
        "他目前是 80%,只有 6 个百分点的薄弱缓冲",
        "一个糟糕的星期,就会让数学局面反转对他不利",
    ],
    "checks_h": "风险检查",
    "checks_headers": ["检查项", "结果"],
    "checks_rows": [
        ["延迟套利", "无问题"],
        ["剥头皮", "无问题(持仓时间太长,算不上真正的剥头皮)"],
        ["隔夜利息套利", "无问题"],
        ["奖金滥用", "无问题"],
        ["唯一需要留意的",
         "100% 只交易黄金;活动量快速上升(每天从 3 笔升到 52 笔)"],
    ],
    "bottom_h": "给经纪商的结论",
    "bottom": (
        "他不是威胁,也没有滥用任何规则。他是一个看起来有技术的交易者,"
        "但有一个颠倒的风险习惯。从数学上看,一个砍掉盈利、放任亏损的客户,"
        "长期会把利润还回去。目前无需采取行动。建议把他标记为"
        "「脆弱的盈利客户」,并观察这 +2,341 能否熬过下一个趋势性的星期。"
    ),
}


# ===================================================================
# Layout helpers
# ===================================================================
def verdict_banner(content, st):
    inner = Table(
        [[Paragraph(content["verdict_label"], st["cell_hdr"])],
         [Paragraph(content["verdict"], st["verdict"])]],
        colWidths=[16.4 * cm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), VERDICT_BG),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (0, 0), 10),
            ("BOTTOMPADDING", (0, 0), (0, 0), 0),
            ("TOPPADDING", (0, 1), (0, 1), 2),
            ("BOTTOMPADDING", (0, 1), (0, 1), 12),
        ]),
    )
    return inner


def section(text, st):
    return Paragraph(text, st["h2"])


def callout(text, st, bg, edge):
    return Table(
        [[Paragraph(text, st["callout"])]],
        colWidths=[16.4 * cm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("BOX", (0, 0), (-1, -1), 0.5, edge),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ]),
    )


def data_table(headers, rows, st, col_widths):
    data = [[Paragraph(h, st["cell_hdr"]) for h in headers]]
    for r in rows:
        data.append([Paragraph(str(c), st["cell"]) for c in r])
    return Table(
        data, colWidths=col_widths,
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("BACKGROUND", (0, 1), (-1, -1), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
            ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]),
    )


def make_doc(path, title, fn):
    doc = BaseDocTemplate(
        path, pagesize=A4,
        leftMargin=2.3 * cm, rightMargin=2.3 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm, title=title,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    def on_page(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(MUTED)
        canvas.setFont(fn, 8)
        canvas.drawString(2.3 * cm, 1.1 * cm, title)
        canvas.drawRightString(A4[0] - 2.3 * cm, 1.1 * cm, f"Page {_doc.page}")
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=on_page)])
    return doc


def build(content, out_path):
    st = build_styles(content["fn"], content["fb"])
    doc = make_doc(str(out_path), content["title"], content["fn"])
    story = []

    # Header
    story.append(Paragraph(content["title"], st["title"]))
    story.append(Paragraph(content["subtitle"], st["subtitle"]))
    story.append(Paragraph(content["meta"], st["meta"]))
    story.append(Spacer(1, 12))

    # Verdict banner
    story.append(verdict_banner(content, st))

    # The trades
    story.append(section(content["trades_h"], st))
    for b in content["trades_bullets"]:
        story.append(Paragraph(f"•&nbsp;&nbsp;{b}", st["bullet"]))
    story.append(Spacer(1, 6))
    story.append(callout(content["trades_callout"], st, BOTTOM_BG, ACCENT))

    # Dangerous habit
    story.append(section(content["habit_h"], st))
    story.append(Paragraph(content["habit_intro"], st["body"]))
    story.append(data_table(content["habit_headers"], content["habit_rows"], st,
                            [3.6 * cm, 8.0 * cm, 4.8 * cm]))
    story.append(Spacer(1, 6))
    story.append(callout(content["habit_note"], st, HABIT_BG, DANGER))

    # Risk and reward
    story.append(section(content["rr_h"], st))
    for b in content["rr_bullets"]:
        story.append(Paragraph(f"•&nbsp;&nbsp;{b}", st["bullet"]))

    # Risk checks — kept on one page
    story.append(KeepTogether([
        section(content["checks_h"], st),
        data_table(content["checks_headers"], content["checks_rows"], st,
                   [5.2 * cm, 11.2 * cm]),
    ]))

    # Bottom line — kept on one page
    story.append(KeepTogether([
        section(content["bottom_h"], st),
        callout(content["bottom"], st, BOTTOM_BG, NAVY),
    ]))

    doc.build(story)


def main():
    out_dir = Path(__file__).parent
    for content in (EN, ZH):
        path = out_dir / content["filename"]
        build(content, path)
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()

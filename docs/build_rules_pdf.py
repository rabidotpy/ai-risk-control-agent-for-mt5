"""Generate the Risk Detection Rules PDF in English and Simplified Chinese.

Two output files, same design, content swapped per language.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, PageBreak,
    Table, TableStyle, KeepTogether, FrameBreak
)


# -------------------------------------------------------------------
# Register Chinese font
# -------------------------------------------------------------------
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

# -------------------------------------------------------------------
# Color palette (shared)
# -------------------------------------------------------------------
NAVY = colors.HexColor("#1f3a68")
ACCENT = colors.HexColor("#2563eb")
SUCCESS = colors.HexColor("#16a34a")
DANGER = colors.HexColor("#dc2626")
WARNING = colors.HexColor("#d97706")
LIGHT_BG = colors.HexColor("#f3f4f6")
RULE_BG = colors.HexColor("#eff6ff")
CASE_BG = colors.HexColor("#fef3c7")
BORDER = colors.HexColor("#cbd5e1")
TEXT = colors.HexColor("#111827")
MUTED = colors.HexColor("#475569")


# -------------------------------------------------------------------
# Style builder per language
# -------------------------------------------------------------------
def build_styles(font_normal: str, font_bold: str) -> dict:
    return {
        "cover_title": ParagraphStyle(
            "cover_title", fontName=font_bold, fontSize=32, leading=40,
            textColor=NAVY, alignment=TA_CENTER, spaceAfter=12,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", fontName=font_normal, fontSize=16, leading=22,
            textColor=MUTED, alignment=TA_CENTER, spaceAfter=8,
        ),
        "cover_meta": ParagraphStyle(
            "cover_meta", fontName=font_normal, fontSize=11, leading=14,
            textColor=MUTED, alignment=TA_CENTER,
        ),
        "h1": ParagraphStyle(
            "h1", fontName=font_bold, fontSize=22, leading=28,
            textColor=NAVY, spaceBefore=4, spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "h2", fontName=font_bold, fontSize=15, leading=20,
            textColor=NAVY, spaceBefore=12, spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "h3", fontName=font_bold, fontSize=12, leading=16,
            textColor=ACCENT, spaceBefore=8, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body", fontName=font_normal, fontSize=10.5, leading=15,
            textColor=TEXT, alignment=TA_JUSTIFY, spaceAfter=6,
        ),
        "body_center": ParagraphStyle(
            "body_center", fontName=font_normal, fontSize=10.5, leading=15,
            textColor=TEXT, alignment=TA_CENTER, spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "small", fontName=font_normal, fontSize=9, leading=12,
            textColor=MUTED,
        ),
        "rule_q": ParagraphStyle(
            "rule_q", fontName=font_bold, fontSize=11, leading=14,
            textColor=NAVY, spaceAfter=4,
        ),
        "rule_body": ParagraphStyle(
            "rule_body", fontName=font_normal, fontSize=10, leading=13,
            textColor=TEXT, alignment=TA_JUSTIFY,
        ),
        "case_title": ParagraphStyle(
            "case_title", fontName=font_bold, fontSize=13, leading=18,
            textColor=WARNING, spaceAfter=4,
        ),
        "case_body": ParagraphStyle(
            "case_body", fontName=font_normal, fontSize=10, leading=14,
            textColor=TEXT, alignment=TA_JUSTIFY, spaceAfter=4,
        ),
        "verdict": ParagraphStyle(
            "verdict", fontName=font_bold, fontSize=11, leading=15,
            textColor=NAVY, spaceBefore=6, alignment=TA_CENTER,
        ),
        "table_cell": ParagraphStyle(
            "table_cell", fontName=font_normal, fontSize=9.5, leading=12,
            textColor=TEXT,
        ),
        "table_cell_bold": ParagraphStyle(
            "table_cell_bold", fontName=font_bold, fontSize=9.5, leading=12,
            textColor=NAVY,
        ),
        "table_header": ParagraphStyle(
            "table_header", fontName=font_bold, fontSize=9.5, leading=12,
            textColor=colors.white, alignment=TA_LEFT,
        ),
    }


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def section_header(text: str, styles: dict, color=NAVY):
    """Coloured pill behind the section title."""
    return Table(
        [[Paragraph(text, styles["h1"])]],
        colWidths=[16.5 * cm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LINEBELOW", (0, 0), (-1, -1), 2, color),
        ]),
    )


def rule_box(rule_id: str, question: str, body: str, styles: dict):
    """Single rule visualised as a coloured panel."""
    content = [
        [Paragraph(f"<b>{rule_id}</b> &nbsp; {question}", styles["rule_q"])],
        [Paragraph(body, styles["rule_body"])],
    ]
    return Table(
        content,
        colWidths=[16.5 * cm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), RULE_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]),
    )


def case_study_box(title: str, description: str, outcomes_rows: list, verdict: str,
                   verdict_color, labels: dict, styles: dict):
    """Yellow-highlighted block with description + outcomes table + verdict."""
    # Build outcomes table
    header = [
        Paragraph(labels["rule"], styles["table_header"]),
        Paragraph(labels["observed"], styles["table_header"]),
        Paragraph(labels["fired"], styles["table_header"]),
    ]
    rows = [header]
    for o in outcomes_rows:
        fired_text = labels["yes"] if o["fired"] else labels["no"]
        fired_color = SUCCESS if o["fired"] else DANGER
        rows.append([
            Paragraph(o["rule"], styles["table_cell"]),
            Paragraph(o["observed"], styles["table_cell"]),
            Paragraph(f'<font color="{fired_color.hexval()}"><b>{fired_text}</b></font>',
                      styles["table_cell"]),
        ])

    outcomes_table = Table(
        rows,
        colWidths=[6.5 * cm, 6.5 * cm, 2.5 * cm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), styles["table_cell_bold"].fontName),
            ("BACKGROUND", (0, 1), (-1, -1), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]),
    )

    # Wrap whole case study
    block = [
        [Paragraph(f'<font color="{WARNING.hexval()}">★</font> &nbsp; <b>{labels["case_label"]}: {title}</b>',
                   styles["case_title"])],
        [Paragraph(description, styles["case_body"])],
        [Spacer(1, 4)],
        [outcomes_table],
        [Spacer(1, 6)],
        [Paragraph(f'<font color="{verdict_color.hexval()}">{verdict}</font>', styles["verdict"])],
    ]
    return Table(
        block,
        colWidths=[16.5 * cm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), CASE_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, WARNING),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ]),
    )


def scoring_table(headers, rows, styles):
    """Score band reference table."""
    table_data = [[Paragraph(h, styles["table_header"]) for h in headers]]
    for r in rows:
        table_data.append([Paragraph(str(c), styles["table_cell"]) for c in r])

    return Table(
        table_data,
        colWidths=[3.5 * cm, 3.5 * cm, 3.5 * cm, 6 * cm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 1), (-1, -1), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (2, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]),
    )


def overview_table(rows, headers, styles):
    """Generic overview table."""
    table_data = [[Paragraph(h, styles["table_header"]) for h in headers]]
    for r in rows:
        table_data.append([Paragraph(str(c), styles["table_cell"]) for c in r])

    n_cols = len(headers)
    col_width = 16.5 * cm / n_cols
    return Table(
        table_data,
        colWidths=[col_width] * n_cols,
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 1), (-1, -1), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]),
    )


# -------------------------------------------------------------------
# Page template (header + footer)
# -------------------------------------------------------------------
def make_doc(path: str, title: str, font_normal: str):
    doc = BaseDocTemplate(
        path,
        pagesize=A4,
        leftMargin=2.25 * cm,
        rightMargin=2.25 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=title,
    )

    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        leftPadding=0, rightPadding=0,
        topPadding=0, bottomPadding=0,
    )

    def on_page(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(MUTED)
        canvas.setFont(font_normal, 8)
        # Footer
        canvas.drawString(2.25 * cm, 1.2 * cm, title)
        canvas.drawRightString(A4[0] - 2.25 * cm, 1.2 * cm, f"Page {_doc.page}")
        # Top hairline
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.4)
        canvas.line(2.25 * cm, A4[1] - 1.6 * cm, A4[0] - 2.25 * cm, A4[1] - 1.6 * cm)
        canvas.restoreState()

    def on_cover(canvas, _doc):
        # No header/footer on cover
        pass

    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[frame], onPage=on_cover),
        PageTemplate(id="body", frames=[frame], onPage=on_page),
    ])
    return doc


# ===================================================================
# CONTENT — English and Chinese
# ===================================================================

EN = {
    "lang": "en",
    "font_normal": "Helvetica",
    "font_bold": "Helvetica-Bold",
    "filename": "Risk_Detection_Rules_EN.pdf",
    "title": "Risk Detection Rules",
    "subtitle": "How the AI Risk Control System Identifies Suspicious Trading",
    "date_label": "Internal reference",
    "date_text": "Version 1.0 · " + date.today().isoformat(),
    "labels": {
        "rule": "Rule",
        "observed": "What we observed",
        "fired": "Fired?",
        "yes": "YES",
        "no": "NO",
        "case_label": "CASE STUDY",
        "verdict_low": "VERDICT",
    },
    "intro_h": "About this document",
    "intro_body": [
        "This guide explains the four risk types the AI Risk Control System looks for, and the rules it uses to flag suspicious trading. The goal is that anyone with basic trading knowledge can understand what each rule does and why it matters.",
        "Each risk type is defined by a small group of rules (4 or 5). Every rule asks one question of the trading data. If a rule's question gets a yes, that rule <i>fires</i>. The more rules that fire for one account, the higher the risk score, and the higher the alert level the risk team receives.",
        "We use real numbers and real examples wherever possible. Where the example is fictional, we say so.",
    ],
    "scoring_h": "How scoring works",
    "scoring_body": [
        "For each risk, the system runs every rule and counts how many fired. The score is simply:",
        "<b>Score = round(100 / (number of rules) × (number of rules that fired))</b>",
        "Then the score maps to one of five levels, each tied to a recommended action:",
    ],
    "scoring_table_headers": ["Score range", "Level", "Action", "Meaning"],
    "scoring_table_rows": [
        ["0 to 39", "Low", "Log only", "Nothing to act on. Recorded for history."],
        ["40 to 59", "Watch", "Add to watchlist", "Worth keeping an eye on, no action yet."],
        ["60 to 74", "Medium", "Manual review", "A human should look at this account."],
        ["75 to 89", "High", "Restrict, pause", "Restrict new positions, pause withdrawals."],
        ["90 to 100", "Critical", "Same, high priority", "Same as high, but urgent."],
    ],
    "overview_h": "The four risk types at a glance",
    "overview_headers": ["Risk type", "What it catches", "Number of rules"],
    "overview_rows": [
        ["Latency Arbitrage", "Traders using a faster price feed than the broker to take risk-free profits", "4"],
        ["Scalping Violation", "Very fast trading patterns that some account contracts forbid", "4"],
        ["Swap Arbitrage", "Holding positions overnight to collect interest, not from price moves", "4"],
        ["Bonus / Credit Abuse", "Using promo bonuses with multiple accounts and fast withdrawals to extract cash", "5"],
    ],
    "risks": [
        # --------- LATENCY ARBITRAGE ---------
        {
            "name": "1. Latency Arbitrage",
            "what": "A trader uses a faster price feed than your broker has. They see the market move on their feed a half-second before your broker's quote updates. They buy at the slow (old) price, wait for the quote to catch up, and close for a tiny but near-certain profit. Done hundreds of times per day, this becomes a serious bleed for the broker.",
            "why": "Every dollar the latency trader makes comes out of the broker's market-making profit. It is the most direct form of broker-side bleed.",
            "fingerprint": "Many trades, very short holding times, both buy and sell directions, almost no losses, closes happen one at a time.",
            "rules": [
                {
                    "id": "R1",
                    "q": "Is the account trading like a bot? (≥ 30 trades in the window)",
                    "body": "Real latency arbitrageurs need volume because each opportunity is small. A normal day trader places far fewer trades. This is the basic frequency gate.",
                },
                {
                    "id": "R2",
                    "q": "Are positions opened and closed within seconds? (median holding time ≤ 30 seconds)",
                    "body": "An arbitrageur enters when the broker price is stale and exits the moment it catches up. That round trip lasts seconds, not minutes. The median across all trades captures this.",
                },
                {
                    "id": "R3",
                    "q": "Does the trader scalp both buys AND sells? (minority side ≥ 20%)",
                    "body": "Stale broker quotes happen on both sides of the market. A real arbitrageur trades whichever side is slow. A trader who only sells (or only buys) is not arbitraging, they are making a directional bet.",
                },
                {
                    "id": "R4",
                    "q": "Near-perfect wins AND closes happen one at a time? (win rate ≥ 90% AND batch close ratio ≤ 20%)",
                    "body": "An arbitrageur wins almost everything because each entry was a near-sure thing. They also close one trade at a time as each opportunity disappears. A grid trader, by contrast, closes a whole bunch of positions at one moment.",
                },
            ],
            "case": {
                "title": "Real account 250030 (broker: Best Wing Global Markets)",
                "description": "On 14 May the broker's risk team complained that this account was wrongly flagged as latency arbitrage. The account placed 39 short positions on gold (XAUUSD) over a 95-minute window. Each position was held for around 35 minutes on average. The closes happened in batches: 12 positions closed at the same second, then 7 more at another single second, then 10 more, then 6 more. Win rate was around 80%. This is a textbook martingale grid, not latency arbitrage. Here is what the new rule set says:",
                "outcomes": [
                    {"rule": "R1: ≥ 30 trades", "observed": "39 trades", "fired": True},
                    {"rule": "R2: median hold ≤ 30s", "observed": "Median 2080 seconds (≈ 35 minutes)", "fired": False},
                    {"rule": "R3: minority side ≥ 20%", "observed": "0% (all 39 were sells)", "fired": False},
                    {"rule": "R4: 90%+ wins, scattered closes", "observed": "80% wins, 97% closes were batched", "fired": False},
                ],
                "verdict": "Score = 1 ÷ 4 × 100 = 25. Level: LOW. Correct verdict: this is a grid, not arbitrage.",
                "verdict_color": SUCCESS,
            },
        },
        # --------- SCALPING ---------
        {
            "name": "2. Scalping Violation",
            "what": "Scalping means placing many tiny trades that each last only seconds or a minute, often run by an automated system (EA) that uses the same lot size, stop loss, and take profit every time. Whether scalping is allowed depends on the customer's account contract; this risk type only flags the pattern.",
            "why": "On accounts where the contract forbids scalping, this is a real breach the broker can act on. Even where it is allowed, the broker's margins on these flows are typically very thin or negative.",
            "fingerprint": "High trade count, very short holds, high win rate, and very repetitive trade construction.",
            "rules": [
                {
                    "id": "R1",
                    "q": "Is the account trading a lot? (≥ 25 trades in the window)",
                    "body": "Scalping is by definition a volume game. Slightly lower bar than latency arbitrage because we want to catch the broader pattern.",
                },
                {
                    "id": "R2",
                    "q": "Are most trades held under one minute? (70%+ of trades held ≤ 60 seconds)",
                    "body": "The defining trait of scalping. The 60-second window is more forgiving than latency arb's 30 seconds, because manual scalpers may take a little longer than bots.",
                },
                {
                    "id": "R3",
                    "q": "High win rate? (≥ 75%)",
                    "body": "Scalpers target many small wins. A 75% win rate is suspiciously high for an active strategy.",
                },
                {
                    "id": "R4",
                    "q": "Are most trades carbon copies of each other? (≥ 50% share the same volume, stop loss, take profit)",
                    "body": "EA scalpers and cookie-cutter strategies use identical settings on every trade. Discretionary traders vary their settings; bots do not.",
                },
            ],
            "case": {
                "title": "Fictional account \"EA Bob\" (illustrative)",
                "description": "Bob runs an automated EA on a major currency pair. Over a 6-hour window he places 30 trades. Every trade uses 0.10 lots, with stop loss at 1.0990 and take profit at 1.1010. Each trade is held for around 30 seconds and closes for a small win. The bot never loses because it cuts profit as soon as price moves 1 pip in its favour.",
                "outcomes": [
                    {"rule": "R1: ≥ 25 trades", "observed": "30 trades", "fired": True},
                    {"rule": "R2: 70% short holds", "observed": "100% of trades held ≤ 60s", "fired": True},
                    {"rule": "R3: win rate ≥ 75%", "observed": "Win rate 100%", "fired": True},
                    {"rule": "R4: 50% pattern bucket", "observed": "100% share volume + SL + TP", "fired": True},
                ],
                "verdict": "Score = 4 ÷ 4 × 100 = 100. Level: CRITICAL. Clear EA scalper, restrict and pause.",
                "verdict_color": DANGER,
            },
        },
        # --------- SWAP ARBITRAGE ---------
        {
            "name": "3. Swap Arbitrage",
            "what": "Some currency pairs pay daily interest (called swap or rollover) on one side and charge it on the other. A swap arbitrageur opens a position to collect the daily interest credit, holds it past midnight UTC to receive the credit, and aims to close at break-even on price. They are not trying to predict the market; they are farming the interest.",
            "why": "The broker pays out the daily swap assuming most clients will lose on price movement. A swap arbitrageur takes the swap without taking the price risk, often by hedging on a linked account that pays only a small swap charge. Net result: the broker pays out money that was never meant to be free.",
            "fingerprint": "A large fraction of total profit comes from swap, positions span at least one daily rollover, the price-movement profit on those same positions is tiny.",
            "rules": [
                {
                    "id": "R1",
                    "q": "Did most of the profit come from swap, not from price? (swap profit ratio ≥ 60%)",
                    "body": "If swap is 60% or more of total profit, the trader is being paid for time, not for being right about price.",
                },
                {
                    "id": "R2",
                    "q": "Did at least one position span overnight UTC? (held across rollover ≥ 1)",
                    "body": "Without a rollover, no swap accrues. This is a precondition rule.",
                },
                {
                    "id": "R3",
                    "q": "Are 5+ trades dominated by swap, not price? (swap-dominant positions ≥ 5)",
                    "body": "A trade is swap-dominant when its positive swap is large compared to the profit or loss from price movement. Five or more such trades is a clear pattern.",
                },
                {
                    "id": "R4",
                    "q": "Across all swap-collecting trades, was the price profit close to zero? (price P&L is within ±20% of total positive swap)",
                    "body": "Looks at the portfolio as a whole. If a trader has $1000 of swap credit and only $50 of price movement profit (5%), that is the swap-farming signature.",
                },
            ],
            "case": {
                "title": "Fictional account \"Carry Cathy\" (illustrative)",
                "description": "Cathy spots a currency pair that pays a generous daily interest credit. Every evening at 22:00 UTC she opens 6 positions. She holds them past midnight UTC, collecting the daily swap credit. She closes each one at around 02:00 UTC for almost the same price she opened at. Per trade: about $10 profit, of which $10 came from swap and $0.05 from price movement.",
                "outcomes": [
                    {"rule": "R1: swap ratio ≥ 60%", "observed": "Swap is 99% of total profit", "fired": True},
                    {"rule": "R2: held across rollover", "observed": "6 positions spanned UTC midnight", "fired": True},
                    {"rule": "R3: 5+ swap-dominant", "observed": "All 6 positions swap-dominated", "fired": True},
                    {"rule": "R4: price P&L low vs swap", "observed": "Price PnL is +0.5% of swap", "fired": True},
                ],
                "verdict": "Score = 4 ÷ 4 × 100 = 100. Level: CRITICAL. Clear swap farmer.",
                "verdict_color": DANGER,
            },
        },
        # --------- BONUS ABUSE ---------
        {
            "name": "4. Bonus / Credit Abuse",
            "what": "Brokers give promo bonuses to attract new traders. A bonus abuser uses the bonus as extra margin to open leveraged positions, often runs multiple accounts in secret so one account always wins, then withdraws the winning side quickly and walks away from the losing side. The broker has effectively given the trader free money.",
            "why": "Direct loss of promo budget. Often combined with stolen identity rings using the same IP or device.",
            "fingerprint": "A bonus event arrives, trade activity spikes shortly after, multiple accounts are linked by IP or device, those linked accounts have opposing trades, and a withdrawal follows soon after the bonus.",
            "rules": [
                {
                    "id": "R1",
                    "q": "Did a bonus arrive in the window?",
                    "body": "Basic gate. Without a bonus this risk does not apply.",
                },
                {
                    "id": "R2",
                    "q": "Did the trader open at least 8 trades after the bonus arrived?",
                    "body": "Bonus abusers trade aggressively to convert the bonus into withdrawable equity. A normal trader who happens to receive a bonus does not change their behaviour.",
                },
                {
                    "id": "R3",
                    "q": "Are there 2+ linked accounts? (same IP / device / wallet / IB)",
                    "body": "Requires CRM data from the broker's back office, not from MT5. Without this data, this rule cannot fire.",
                },
                {
                    "id": "R4",
                    "q": "Does a linked account have opposing trades on the same symbol?",
                    "body": "The clearest ring signature: one account buys EURUSD while a linked account sells EURUSD. The winning side cashes out, the losing side is abandoned.",
                },
                {
                    "id": "R5",
                    "q": "Did a withdrawal happen after the bonus?",
                    "body": "The whole point of the scheme is to walk away with cash. A withdrawal soon after the bonus is the tell.",
                },
            ],
            "case": {
                "title": "Fictional account \"Ring Ben\" (illustrative)",
                "description": "Ben receives a $100 bonus at 01:00 UTC. Within two hours he opens 10 trades using the inflated margin. The broker's CRM flags two linked accounts that share his IP address. One of those linked accounts has 3 opposing trades on the same currency pair within the window. At 05:00 UTC, Ben submits a withdrawal request for $50.",
                "outcomes": [
                    {"rule": "R1: bonus received", "observed": "1 bonus event", "fired": True},
                    {"rule": "R2: 8+ trades after bonus", "observed": "10 trades", "fired": True},
                    {"rule": "R3: 2+ linked accounts", "observed": "2 accounts share IP", "fired": True},
                    {"rule": "R4: linked opposing trades", "observed": "1 account has 3 opposing trades", "fired": True},
                    {"rule": "R5: withdrawal after bonus", "observed": "Withdrawal at 05:00 UTC", "fired": True},
                ],
                "verdict": "Score = 5 ÷ 5 × 100 = 100. Level: CRITICAL. Clear bonus abuse ring.",
                "verdict_color": DANGER,
            },
            "note": "<b>Important data note:</b> rules R3 and R4 need linked-accounts data from the broker's CRM, which is not yet connected to the system. Until that data is delivered, bonus abuse cases cap at 3 of 5 rules firing, which corresponds to a maximum score of 60 (medium). The risk team should treat any \"medium\" bonus abuse alert as potentially \"critical\" until R3 and R4 can fire.",
        },
    ],
    "closing_h": "Summary",
    "closing_body": [
        "Four risk types. Seventeen rules in total (four each for latency arbitrage, scalping, and swap arbitrage; five for bonus abuse). Each rule asks one specific question of the trading data. The risk score reflects how many rules fired, and the level guides the action.",
        "The system is built so that one wrong rule does not falsely flag an account, and one weak signal does not slip through. The combination of rules matters more than any single signal.",
        "The case studies above show the system working correctly on a real broker case (account 250030 correctly cleared) and on three illustrative scenarios. The same rule engine applies to every account the system analyses.",
    ],
}


ZH = {
    "lang": "zh",
    "font_normal": "STSong-Light",
    "font_bold": "STSong-Light",
    "filename": "Risk_Detection_Rules_ZH.pdf",
    "title": "风险检测规则说明",
    "subtitle": "AI 风险控制系统如何识别可疑交易",
    "date_label": "内部参考",
    "date_text": "版本 1.0 · " + date.today().isoformat(),
    "labels": {
        "rule": "规则",
        "observed": "实际观察到",
        "fired": "是否触发",
        "yes": "是",
        "no": "否",
        "case_label": "案例研究",
        "verdict_low": "判定",
    },
    "intro_h": "关于本文件",
    "intro_body": [
        "本指南介绍 AI 风险控制系统所关注的四种风险类型,以及用于标记可疑交易的规则。目标是让任何具备基础交易知识的人都能理解每条规则的作用和意义。",
        "每种风险类型由一组规则(4 条或 5 条)构成。每条规则向交易数据提出一个问题。如果答案为是,该规则便<i>触发</i>。一个账户触发的规则越多,风险分数就越高,风控团队收到的警报级别也越高。",
        "我们尽可能使用真实的数据和真实的案例。当示例为虚构时,我们会明确说明。",
    ],
    "scoring_h": "评分机制",
    "scoring_body": [
        "对每种风险,系统会运行所有规则并统计触发数量。分数的计算方式很简单:",
        "<b>分数 = round(100 / 规则总数 × 触发的规则数)</b>",
        "之后,分数对应到五个级别之一,每个级别都有建议的处理动作:",
    ],
    "scoring_table_headers": ["分数区间", "级别", "建议动作", "含义"],
    "scoring_table_rows": [
        ["0 到 39", "低", "仅记录", "无需处理,留存历史记录"],
        ["40 到 59", "观察", "加入观察名单", "需要持续关注,暂不行动"],
        ["60 到 74", "中等", "人工审核", "需要人工查看该账户"],
        ["75 到 89", "高", "限制并暂停", "限制开新仓,暂停出金"],
        ["90 到 100", "严重", "同上,高优先级", "与高级别相同,但更紧急"],
    ],
    "overview_h": "四种风险类型概览",
    "overview_headers": ["风险类型", "针对什么", "规则数量"],
    "overview_rows": [
        ["延迟套利", "使用比经纪商更快的报价源获取无风险利润的交易者", "4"],
        ["剥头皮违规", "某些合约禁止的极速交易模式", "4"],
        ["隔夜利息套利", "持有过夜仓位以收取利息,而非靠价格波动获利", "4"],
        ["奖金 / 信用滥用", "利用促销奖金,通过多账户和快速出金套取现金", "5"],
    ],
    "risks": [
        # --------- LATENCY ARBITRAGE ---------
        {
            "name": "1. 延迟套利",
            "what": "交易者使用比经纪商更快的报价源。他们在经纪商的报价更新之前的半秒就能看到行情变动。他们以滞后(旧)的价格下单,等到报价追上后立即平仓,赚取微小但近乎确定的利润。一天重复数百次,就会成为经纪商的重大损失。",
            "why": "延迟交易者赚到的每一美元,都从经纪商的做市利润中流失。这是最直接的经纪商损失形式。",
            "fingerprint": "交易笔数多、持仓时间极短、买卖双向都有、几乎没有亏损、平仓是逐笔进行而非集中批量。",
            "rules": [
                {
                    "id": "R1",
                    "q": "账户是否像机器人一样在交易?(窗口内 ≥ 30 笔交易)",
                    "body": "真正的延迟套利者需要交易量,因为每个机会都很小。普通日内交易者下单数量远少于此。这是基本的频率门槛。",
                },
                {
                    "id": "R2",
                    "q": "仓位是否在数秒内开平?(持仓时间中位数 ≤ 30 秒)",
                    "body": "套利者在经纪商报价滞后时入场,在报价追上的瞬间退出。整个往返只有几秒,而非几分钟。所有交易的持仓时间中位数能反映这一特征。",
                },
                {
                    "id": "R3",
                    "q": "交易者是否同时做多和做空?(少数方向占比 ≥ 20%)",
                    "body": "经纪商的滞后报价在买卖两侧都会出现。真正的套利者会交易任何滞后的一侧。只做空(或只做多)的交易者不是在套利,而是在做方向性押注。",
                },
                {
                    "id": "R4",
                    "q": "胜率接近完美,且平仓是逐笔进行?(胜率 ≥ 90% 且批量平仓比例 ≤ 20%)",
                    "body": "套利者几乎每笔都赢,因为每次入场时就已接近必胜。同时,他们随着每个机会消失而逐笔平仓。而网格交易者则会在某一刻集中平掉一大批仓位。",
                },
            ],
            "case": {
                "title": "真实账户 250030(经纪商:Best Wing Global Markets)",
                "description": "5 月 14 日,经纪商风控团队反映该账户被错误标记为延迟套利。该账户在 95 分钟内,在黄金(XAUUSD)上开了 39 笔空头仓位。每笔仓位平均持仓约 35 分钟。平仓是分批进行的:12 笔在同一秒平仓,接着 7 笔在另一秒平仓,然后是 10 笔,再 6 笔。胜率约 80%。这是典型的马丁格尔网格策略,不是延迟套利。新规则集的判定如下:",
                "outcomes": [
                    {"rule": "R1: ≥ 30 笔", "observed": "39 笔交易", "fired": True},
                    {"rule": "R2: 中位持仓 ≤ 30 秒", "observed": "中位 2080 秒(约 35 分钟)", "fired": False},
                    {"rule": "R3: 少数方向 ≥ 20%", "observed": "0%(全部 39 笔都是卖出)", "fired": False},
                    {"rule": "R4: 90%+ 胜率,平仓分散", "observed": "胜率 80%,97% 为批量平仓", "fired": False},
                ],
                "verdict": "分数 = 1 / 4 × 100 = 25。级别:低。正确判定:这是网格策略,不是套利。",
                "verdict_color": SUCCESS,
            },
        },
        # --------- SCALPING ---------
        {
            "name": "2. 剥头皮违规",
            "what": "剥头皮指下大量极短时间(数秒到一分钟)的小额交易,常由自动化程序(EA)运行,每笔都使用相同的手数、止损和止盈。是否允许剥头皮取决于客户的账户合约;本风险类型仅识别该模式。",
            "why": "对于合约禁止剥头皮的账户,这是经纪商可以采取行动的实质违约。即便允许,经纪商在这类订单流上的利润通常也极薄甚至为负。",
            "fingerprint": "交易笔数高、持仓极短、胜率高、交易结构高度重复。",
            "rules": [
                {
                    "id": "R1",
                    "q": "账户是否交易频繁?(窗口内 ≥ 25 笔)",
                    "body": "剥头皮本质上靠数量。门槛略低于延迟套利,因为我们要覆盖更广泛的模式。",
                },
                {
                    "id": "R2",
                    "q": "多数交易是否在一分钟内?(≥ 70% 的交易持仓 ≤ 60 秒)",
                    "body": "剥头皮的核心特征。60 秒比延迟套利的 30 秒更宽松,因为手动剥头皮者可能比机器人略慢。",
                },
                {
                    "id": "R3",
                    "q": "胜率是否较高?(≥ 75%)",
                    "body": "剥头皮者追求大量小额盈利。75% 的胜率对主动型策略而言异常高。",
                },
                {
                    "id": "R4",
                    "q": "多数交易是否如出一辙?(≥ 50% 的交易共享相同的手数、止损、止盈)",
                    "body": "EA 剥头皮者和模板化策略会在每笔交易中使用相同设置。手动交易者会调整设置,机器人不会。",
                },
            ],
            "case": {
                "title": "虚构账户「EA Bob」(示例)",
                "description": "Bob 在一个主要货币对上运行自动化 EA。在 6 小时窗口内,他下了 30 笔单。每笔都使用 0.10 手,止损在 1.0990,止盈在 1.1010。每笔仓位持仓约 30 秒并以小额盈利平仓。机器人从不亏损,因为只要价格朝有利方向移动 1 个点就立即落袋。",
                "outcomes": [
                    {"rule": "R1: ≥ 25 笔", "observed": "30 笔交易", "fired": True},
                    {"rule": "R2: 70% 短持仓", "observed": "100% 持仓 ≤ 60 秒", "fired": True},
                    {"rule": "R3: 胜率 ≥ 75%", "observed": "胜率 100%", "fired": True},
                    {"rule": "R4: 50% 模板桶", "observed": "100% 共享手数 + 止损 + 止盈", "fired": True},
                ],
                "verdict": "分数 = 4 / 4 × 100 = 100。级别:严重。明确的 EA 剥头皮,应限制并暂停。",
                "verdict_color": DANGER,
            },
        },
        # --------- SWAP ARBITRAGE ---------
        {
            "name": "3. 隔夜利息套利",
            "what": "某些货币对一侧支付每日利息(称为隔夜利息或 swap),另一侧收取。隔夜利息套利者开仓收取每日利息,持仓过 UTC 午夜以获得该利息,并力求在价格上保本平仓。他们不是在预测市场,而是在收割利息。",
            "why": "经纪商支付每日 swap,前提是大多数客户会在价格波动上亏损。隔夜利息套利者拿到 swap 却不承担价格风险,常通过在关联账户上对冲(对冲方只需支付少量 swap)实现。最终结果是经纪商支付了本不该免费送出的资金。",
            "fingerprint": "总利润中很大一部分来自 swap;仓位至少跨越一次每日 rollover;同样这些仓位的价格波动盈亏极小。",
            "rules": [
                {
                    "id": "R1",
                    "q": "大部分利润是否来自 swap 而非价格?(swap 利润占比 ≥ 60%)",
                    "body": "如果 swap 占总利润 60% 或以上,交易者赚的是时间,而不是对价格的判断。",
                },
                {
                    "id": "R2",
                    "q": "是否至少有一笔仓位跨越 UTC 隔夜?(跨 rollover ≥ 1)",
                    "body": "没有 rollover 就没有 swap 产生。这是先决条件规则。",
                },
                {
                    "id": "R3",
                    "q": "是否有 5+ 笔交易由 swap 主导?(swap 主导仓位 ≥ 5)",
                    "body": "当一笔交易的正向 swap 远大于价格波动带来的盈亏,即为 swap 主导。5 笔或以上是明显的模式。",
                },
                {
                    "id": "R4",
                    "q": "在所有收 swap 的交易中,价格盈亏是否接近零?(价格盈亏在正向 swap 总额的 ±20% 之内)",
                    "body": "从整个组合层面看。如果交易者有 1000 美元 swap 收入,而价格波动盈利只有 50 美元(5%),这就是收割 swap 的特征。",
                },
            ],
            "case": {
                "title": "虚构账户「Carry Cathy」(示例)",
                "description": "Cathy 发现一个支付丰厚每日利息的货币对。每晚 22:00 UTC 她开 6 笔仓位,持仓过 UTC 午夜以收取每日 swap 信贷,大约在次日 02:00 UTC 在几乎相同的价格平仓。每笔交易:盈利约 10 美元,其中 10 美元来自 swap,0.05 美元来自价格波动。",
                "outcomes": [
                    {"rule": "R1: swap 占比 ≥ 60%", "observed": "swap 占总利润 99%", "fired": True},
                    {"rule": "R2: 跨 rollover", "observed": "6 笔仓位跨 UTC 午夜", "fired": True},
                    {"rule": "R3: 5+ 笔 swap 主导", "observed": "全部 6 笔由 swap 主导", "fired": True},
                    {"rule": "R4: 价格盈亏对 swap 占比低", "observed": "价格盈亏为 swap 的 +0.5%", "fired": True},
                ],
                "verdict": "分数 = 4 / 4 × 100 = 100。级别:严重。明确的 swap 收割。",
                "verdict_color": DANGER,
            },
        },
        # --------- BONUS ABUSE ---------
        {
            "name": "4. 奖金 / 信用滥用",
            "what": "经纪商发放促销奖金以吸引新交易者。奖金滥用者将奖金作为额外保证金开杠杆仓位,常常暗中运营多个账户使其中一个总能赚钱,然后快速出金赚钱的一侧,放弃亏损的一侧。经纪商等于免费送钱给交易者。",
            "why": "直接损失促销预算。常与同 IP 或同设备的盗用身份团伙结合出现。",
            "fingerprint": "奖金到账;交易活动随即激增;多个账户通过 IP 或设备关联;关联账户上有对冲方向的交易;奖金之后很快有出金。",
            "rules": [
                {
                    "id": "R1",
                    "q": "窗口内是否到账了奖金?",
                    "body": "基本门槛。没有奖金,该风险不适用。",
                },
                {
                    "id": "R2",
                    "q": "奖金到账后是否至少开了 8 笔交易?",
                    "body": "奖金滥用者会大举交易,将奖金转化为可出金的资金。普通交易者收到奖金不会改变行为。",
                },
                {
                    "id": "R3",
                    "q": "是否有 2+ 个关联账户?(同 IP / 设备 / 钱包 / IB)",
                    "body": "需要经纪商后台 CRM 数据,而非 MT5 数据。无该数据时此规则无法触发。",
                },
                {
                    "id": "R4",
                    "q": "关联账户是否在同一品种上有对冲方向的交易?",
                    "body": "最明显的团伙特征:一个账户做多 EURUSD,关联账户做空 EURUSD。赢的一侧出金,输的一侧放弃。",
                },
                {
                    "id": "R5",
                    "q": "奖金之后是否发生出金?",
                    "body": "整个套路的目的就是拿到现金。奖金后不久的出金是关键线索。",
                },
            ],
            "case": {
                "title": "虚构账户「Ring Ben」(示例)",
                "description": "Ben 在 01:00 UTC 收到 100 美元奖金。两小时内,他利用扩大的保证金开了 10 笔交易。经纪商 CRM 标记两个关联账户与他共用 IP 地址。其中一个关联账户在窗口内在同一货币对上有 3 笔对冲方向的交易。05:00 UTC,Ben 提交 50 美元出金申请。",
                "outcomes": [
                    {"rule": "R1: 奖金到账", "observed": "1 次奖金事件", "fired": True},
                    {"rule": "R2: 奖金后 8+ 笔", "observed": "10 笔交易", "fired": True},
                    {"rule": "R3: 2+ 关联账户", "observed": "2 个账户共 IP", "fired": True},
                    {"rule": "R4: 关联对冲交易", "observed": "1 个账户有 3 笔对冲交易", "fired": True},
                    {"rule": "R5: 奖金后出金", "observed": "05:00 UTC 出金", "fired": True},
                ],
                "verdict": "分数 = 5 / 5 × 100 = 100。级别:严重。明确的奖金滥用团伙。",
                "verdict_color": DANGER,
            },
            "note": "<b>重要数据说明:</b>规则 R3 和 R4 需要经纪商 CRM 的关联账户数据,目前系统尚未接入。在该数据交付前,奖金滥用案例最多触发 5 条中的 3 条,对应最高分数 60(中等)。风控团队应将任何「中等」级别的奖金滥用警报视为潜在的「严重」级别,直到 R3 和 R4 可以触发为止。",
        },
    ],
    "closing_h": "总结",
    "closing_body": [
        "四种风险类型。总共 17 条规则(延迟套利、剥头皮、隔夜利息套利各 4 条;奖金滥用 5 条)。每条规则向交易数据提出一个具体问题。风险分数反映触发了多少条规则,级别指导处理动作。",
        "系统的设计原则是:单一规则误判不会冤枉一个账户,单一弱信号也不会被漏掉。规则的组合比任何单一信号更重要。",
        "上述案例展示了系统在真实经纪商案例中正确清白(账户 250030 被正确判定为低风险)和三个示例场景中的工作方式。同一规则引擎适用于系统分析的每一个账户。",
    ],
}


# ===================================================================
# Document assembly
# ===================================================================
def build(content: dict, output_path: Path):
    styles = build_styles(content["font_normal"], content["font_bold"])
    doc = make_doc(str(output_path), content["title"], content["font_normal"])
    story = []

    from reportlab.platypus.doctemplate import NextPageTemplate

    # ---- COVER ----
    story.append(NextPageTemplate("body"))  # what follows the cover PageBreak
    story.append(Spacer(1, 5 * cm))
    story.append(Paragraph(content["title"], styles["cover_title"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(content["subtitle"], styles["cover_sub"]))
    story.append(Spacer(1, 12 * cm))
    story.append(Paragraph(content["date_label"], styles["cover_meta"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(content["date_text"], styles["cover_meta"]))
    story.append(PageBreak())

    # ---- INTRODUCTION ----
    story.append(section_header(content["intro_h"], styles))
    story.append(Spacer(1, 10))
    for p in content["intro_body"]:
        story.append(Paragraph(p, styles["body"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph(content["overview_h"], styles["h2"]))
    story.append(overview_table(content["overview_rows"], content["overview_headers"], styles))
    story.append(PageBreak())

    # ---- SCORING (own page so it doesn't break) ----
    story.append(section_header(content["scoring_h"], styles))
    story.append(Spacer(1, 10))
    for p in content["scoring_body"]:
        story.append(Paragraph(p, styles["body"]))
    story.append(Spacer(1, 6))
    story.append(scoring_table(content["scoring_table_headers"],
                               content["scoring_table_rows"], styles))
    story.append(PageBreak())

    # ---- RISK SECTIONS ----
    for risk in content["risks"]:
        story.append(section_header(risk["name"], styles))
        story.append(Spacer(1, 10))

        # What
        story.append(Paragraph(
            "<b>" + ("What is it?" if content["lang"] == "en" else "什么是它?") + "</b>",
            styles["h3"],
        ))
        story.append(Paragraph(risk["what"], styles["body"]))

        # Why
        story.append(Paragraph(
            "<b>" + ("Why brokers care" if content["lang"] == "en" else "经纪商为何关注") + "</b>",
            styles["h3"],
        ))
        story.append(Paragraph(risk["why"], styles["body"]))

        # Fingerprint
        story.append(Paragraph(
            "<b>" + ("Fingerprint" if content["lang"] == "en" else "特征") + "</b>",
            styles["h3"],
        ))
        story.append(Paragraph(risk["fingerprint"], styles["body"]))

        # Rules header
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "<b>" + ("The rules" if content["lang"] == "en" else "规则") + "</b>",
            styles["h2"],
        ))

        # Each rule in a box
        for r in risk["rules"]:
            story.append(rule_box(r["id"], r["q"], r["body"], styles))
            story.append(Spacer(1, 6))

        # Page break before case study so it stays together
        story.append(PageBreak())

        # Case study
        story.append(Paragraph(
            ("Case study" if content["lang"] == "en" else "案例研究"),
            styles["h2"],
        ))
        story.append(Spacer(1, 4))
        c = risk["case"]
        story.append(case_study_box(
            c["title"], c["description"], c["outcomes"], c["verdict"],
            c["verdict_color"], content["labels"], styles,
        ))

        # Optional note
        if risk.get("note"):
            story.append(Spacer(1, 10))
            story.append(Paragraph(
                "<b>" + ("Note" if content["lang"] == "en" else "注意") + "</b>",
                styles["h3"],
            ))
            story.append(Paragraph(risk["note"], styles["body"]))

        story.append(PageBreak())

    # ---- CLOSING ----
    story.append(section_header(content["closing_h"], styles))
    story.append(Spacer(1, 10))
    for p in content["closing_body"]:
        story.append(Paragraph(p, styles["body"]))

    doc.build(story)


def main():
    out_dir = Path(__file__).parent
    for content in (EN, ZH):
        out_path = out_dir / content["filename"]
        build(content, out_path)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

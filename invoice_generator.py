from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.graphics.shapes import Drawing, Rect
from reportlab.graphics import renderPDF
from datetime import datetime
import os

# ── Brand colours ──────────────────────────────────────────────
NAVY       = colors.HexColor("#0A1628")
BLUE       = colors.HexColor("#1565C0")
LIGHT_BLUE = colors.HexColor("#E3F0FF")
ACCENT     = colors.HexColor("#1976D2")
WHITE      = colors.white
GREY       = colors.HexColor("#666666")
LIGHT_GREY = colors.HexColor("#F5F8FF")
BORDER     = colors.HexColor("#C7D7F5")
RED        = colors.HexColor("#DC2626")
GREEN      = colors.HexColor("#16A34A")

W, H = A4

def generate_invoice(username, expenses, budget, invoice_number=None):
    """
    Generate a professional PDF invoice/report for a BlueLedger user.
    Returns the path to the generated PDF.
    """
    os.makedirs("invoices", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not invoice_number:
        invoice_number = f"BL-{timestamp}"
    path = f"invoices/invoice_{username}_{timestamp}.pdf"

    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        leftMargin=18*mm,
        rightMargin=18*mm,
        topMargin=10*mm,
        bottomMargin=18*mm,
    )

    styles = getSampleStyleSheet()
    story  = []

    # ── HEADER BANNER ──────────────────────────────────────────
    header_data = [[
        Paragraph(
            '<font color="#FFFFFF" size="22"><b>BlueLedger AI</b></font><br/>'
            '<font color="#90CAF9" size="9">Enterprise Financial Management Platform</font>',
            ParagraphStyle("hdr", fontName="Helvetica", leading=16)
        ),
        Paragraph(
            f'<font color="#FFFFFF" size="18"><b>INVOICE</b></font><br/>'
            f'<font color="#90CAF9" size="8">#{invoice_number}</font>',
            ParagraphStyle("inv", fontName="Helvetica", alignment=TA_RIGHT, leading=16)
        ),
    ]]
    header_table = Table(header_data, colWidths=[110*mm, 64*mm])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,-1), NAVY),
        ("TOPPADDING",   (0,0), (-1,-1), 14),
        ("BOTTOMPADDING",(0,0), (-1,-1), 14),
        ("LEFTPADDING",  (0,0), (0,-1),  14),
        ("RIGHTPADDING", (-1,0),(-1,-1), 14),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("ROUNDEDCORNERS", [6,6,6,6]),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 6*mm))

    # ── META ROW (issued / period / status) ───────────────────
    now      = datetime.now()
    meta_data = [[
        Paragraph(
            f'<font color="#666666" size="8">ISSUED TO</font><br/>'
            f'<font color="#0A1628" size="11"><b>{username.upper()}</b></font>',
            ParagraphStyle("m1", fontName="Helvetica", leading=14)
        ),
        Paragraph(
            f'<font color="#666666" size="8">DATE ISSUED</font><br/>'
            f'<font color="#0A1628" size="11"><b>{now.strftime("%d %B %Y")}</b></font>',
            ParagraphStyle("m2", fontName="Helvetica", leading=14)
        ),
        Paragraph(
            f'<font color="#666666" size="8">PERIOD</font><br/>'
            f'<font color="#0A1628" size="11"><b>{now.strftime("%B %Y")}</b></font>',
            ParagraphStyle("m3", fontName="Helvetica", leading=14)
        ),
        Paragraph(
            f'<font color="#166534" size="8">STATUS</font><br/>'
            f'<font color="#16A34A" size="11"><b>● GENERATED</b></font>',
            ParagraphStyle("m4", fontName="Helvetica", leading=14)
        ),
    ]]
    meta_table = Table(meta_data, colWidths=[43.5*mm]*4)
    meta_table.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), LIGHT_GREY),
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
        ("RIGHTPADDING",  (0,0),(-1,-1), 10),
        ("LINEAFTER",     (0,0),(2,-1),  0.5, BORDER),
        ("ROUNDEDCORNERS",[4,4,4,4]),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 6*mm))

    # ── SUMMARY CARDS ──────────────────────────────────────────
    total_amount  = sum(float(e[2]) for e in expenses) if expenses else 0
    high_risk_cnt = sum(1 for e in expenses if e[5] and "High Risk" in e[5]) if expenses else 0
    budget_val    = float(budget[2]) if budget and budget[2] else 0
    remaining     = budget_val - total_amount
    remaining_col = "#16A34A" if remaining >= 0 else "#DC2626"
    remaining_lbl = "SURPLUS" if remaining >= 0 else "DEFICIT"

    def card(label, value, color="#0A1628"):
        return Paragraph(
            f'<font color="#666666" size="7">{label}</font><br/>'
            f'<font color="{color}" size="14"><b>{value}</b></font>',
            ParagraphStyle("card", fontName="Helvetica", leading=16)
        )

    cards_data = [[
        card("TOTAL EXPENSES",   f"${total_amount:,.2f}",  "#0A1628"),
        card("MONTHLY BUDGET",   f"${budget_val:,.2f}",    "#1565C0"),
        card(remaining_lbl,      f"${abs(remaining):,.2f}", remaining_col),
        card("HIGH RISK FLAGS",  str(high_risk_cnt),        "#DC2626" if high_risk_cnt else "#16A34A"),
        card("TRANSACTIONS",     str(len(expenses)),         "#0A1628"),
    ]]
    cards_table = Table(cards_data, colWidths=[34.8*mm]*5)
    cards_table.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), LIGHT_GREY),
        ("TOPPADDING",    (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("RIGHTPADDING",  (0,0),(-1,-1), 8),
        ("LINEAFTER",     (0,0),(3,-1),  0.5, BORDER),
        ("ROUNDEDCORNERS",[4,4,4,4]),
    ]))
    story.append(cards_table)
    story.append(Spacer(1, 6*mm))

    # ── TRANSACTION TABLE ──────────────────────────────────────
    story.append(Paragraph(
        '<font color="#0A1628" size="11"><b>Transaction Details</b></font>',
        ParagraphStyle("sec", fontName="Helvetica-Bold", spaceAfter=4)
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=BLUE, spaceAfter=4))

    t_header = ["#", "Category", "Amount", "Date", "AI Risk Status"]
    t_rows   = [t_header]

    for i, exp in enumerate(expenses, 1):
        risk = exp[5] if exp[5] else "Low Risk"
        if "High Risk" in risk:
            risk_str = "🔴 High Risk"
        elif "Medium Risk" in risk:
            risk_str = "🟡 Medium Risk"
        else:
            risk_str = "🟢 Low Risk"

        t_rows.append([
            str(i),
            str(exp[3]),
            f"${float(exp[2]):,.2f}",
            str(exp[4]),
            risk_str,
        ])

    if not expenses:
        t_rows.append(["—", "No transactions recorded", "—", "—", "—"])

    col_w = [10*mm, 45*mm, 28*mm, 28*mm, 63*mm]
    t = Table(t_rows, colWidths=col_w, repeatRows=1)

    row_styles = [
        ("BACKGROUND",    (0,0), (-1,0),  NAVY),
        ("TEXTCOLOR",     (0,0), (-1,0),  WHITE),
        ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,0),  8),
        ("TOPPADDING",    (0,0), (-1,0),  9),
        ("BOTTOMPADDING", (0,0), (-1,0),  9),
        ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,1), (-1,-1), 8),
        ("TOPPADDING",    (0,1), (-1,-1), 7),
        ("BOTTOMPADDING", (0,1), (-1,-1), 7),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("GRID",          (0,1), (-1,-1), 0.4, BORDER),
        ("LINEBELOW",     (0,0), (-1,0),  1,   BLUE),
        ("ALIGN",         (2,0), (2,-1),  "RIGHT"),
        ("ALIGN",         (0,0), (0,-1),  "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, LIGHT_GREY]),
    ]
    t.setStyle(TableStyle(row_styles))
    story.append(t)
    story.append(Spacer(1, 6*mm))

    # ── CATEGORY SUMMARY ───────────────────────────────────────
    if expenses:
        cat_totals = {}
        for exp in expenses:
            cat = str(exp[3])
            cat_totals[cat] = cat_totals.get(cat, 0) + float(exp[2])

        story.append(Paragraph(
            '<font color="#0A1628" size="11"><b>Category Breakdown</b></font>',
            ParagraphStyle("sec2", fontName="Helvetica-Bold", spaceAfter=4)
        ))
        story.append(HRFlowable(width="100%", thickness=1.5, color=BLUE, spaceAfter=4))

        cat_rows = [["Category", "Total Amount", "% of Spend"]]
        for cat, amt in sorted(cat_totals.items(), key=lambda x: x[1], reverse=True):
            pct = (amt / total_amount * 100) if total_amount else 0
            cat_rows.append([cat, f"${amt:,.2f}", f"{pct:.1f}%"])

        cat_table = Table(cat_rows, colWidths=[80*mm, 50*mm, 44*mm])
        cat_table.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0),  BLUE),
            ("TEXTCOLOR",     (0,0), (-1,0),  WHITE),
            ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,-1), 9),
            ("TOPPADDING",    (0,0), (-1,-1), 7),
            ("BOTTOMPADDING", (0,0), (-1,-1), 7),
            ("LEFTPADDING",   (0,0), (-1,-1), 10),
            ("GRID",          (0,1), (-1,-1), 0.4, BORDER),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, LIGHT_GREY]),
            ("ALIGN",         (1,0), (2,-1),  "RIGHT"),
        ]))
        story.append(cat_table)
        story.append(Spacer(1, 6*mm))

    # ── TOTALS BOX ─────────────────────────────────────────────
    totals_data = [
        ["", "Subtotal",       f"${total_amount:,.2f}"],
        ["", "Monthly Budget", f"${budget_val:,.2f}"],
        ["", remaining_lbl,    f"${abs(remaining):,.2f}"],
    ]
    totals_table = Table(totals_data, colWidths=[88*mm, 50*mm, 36*mm])
    totals_table.setStyle(TableStyle([
        ("FONTNAME",      (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,0), (-1,-1), 9),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("RIGHTPADDING",  (2,0), (2,-1),  10),
        ("LEFTPADDING",   (1,0), (1,-1),  10),
        ("ALIGN",         (2,0), (2,-1),  "RIGHT"),
        ("ALIGN",         (1,0), (1,-1),  "RIGHT"),
        ("LINEABOVE",     (1,2), (2,2),   1, NAVY),
        ("FONTNAME",      (1,2), (2,2),   "Helvetica-Bold"),
        ("FONTSIZE",      (1,2), (2,2),   10),
        ("TEXTCOLOR",     (2,2), (2,2),
         GREEN if remaining >= 0 else RED),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 8*mm))

    # ── FOOTER ─────────────────────────────────────────────────
    footer_data = [[
        Paragraph(
            '<font color="#FFFFFF" size="8"><b>BlueLedger AI</b> — Enterprise Financial Management</font><br/>'
            '<font color="#90CAF9" size="7">support.blueledgerai@gmail.com  |  blueledger-ai.onrender.com</font>',
            ParagraphStyle("ft", fontName="Helvetica", leading=12)
        ),
        Paragraph(
            f'<font color="#90CAF9" size="7">Generated: {now.strftime("%d %b %Y %H:%M")}<br/>'
            f'Invoice: #{invoice_number}<br/>'
            f'Powered by AI</font>',
            ParagraphStyle("ft2", fontName="Helvetica", alignment=TA_RIGHT, leading=12)
        ),
    ]]
    footer_table = Table(footer_data, colWidths=[110*mm, 64*mm])
    footer_table.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), NAVY),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (0,-1),  14),
        ("RIGHTPADDING",  (-1,0),(-1,-1), 14),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(footer_table)

    doc.build(story)
    return path
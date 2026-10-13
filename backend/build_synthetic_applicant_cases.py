"""Build conspicuously synthetic upload cases for local PRISM demonstrations.

No real institution, employer, utility, account or financial history is represented.
Scores are not written into documents; PRISM computes its cash-flow index from rows.
"""
from __future__ import annotations

import calendar
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


REPO = Path(__file__).resolve().parents[1]
DEST = REPO / "data" / "testing"
MONTHS = [(2026, month) for month in range(3, 9)]
APPLICANTS = {
    "Sujata Deshmukh": {
        "ref": "SUJ-TEST-2603",
        "income": [82000, 83500, 81500, 84000, 83000, 85000],
        "expense_ratio": [.54, .57, .55, .58, .53, .56],
        "emi_ratio": [.05, .05, .05, .05, .05, .05],
        "buffer_months": [2.5, 2.6, 2.7, 2.6, 2.8, 2.9],
    },
    "Anjali Singh": {
        "ref": "ANJ-TEST-2603",
        "income": [42000, 72000, 48000, 81000, 50000, 76000],
        "expense_ratio": [.82, .76, .90, .72, .88, .78],
        "emi_ratio": [.17, .15, .18, .14, .18, .16],
        "buffer_months": [.35, .55, .25, .75, .30, .60],
    },
    "Vedant Patil": {
        "ref": "VED-TEST-2603",
        "income": [56000, 56500, 55000, 57500, 57000, 58000],
        "expense_ratio": [.91, .95, .88, .97, .93, .90],
        "emi_ratio": [.26, .28, .23, .30, .27, .24],
        "buffer_months": [.12, .08, .18, .06, .10, .20],
    },
    "Irfan Mohammad": {
        "ref": "IRF-TEST-2603",
        "income": [104000, 102000, 108000, 106000, 110000, 107000],
        "expense_ratio": [.69, .73, .66, .76, .70, .68],
        "emi_ratio": [.18, .20, .17, .21, .19, .17],
        "buffer_months": [1.05, .90, 1.20, .82, 1.10, 1.25],
    },
}


def amount(value: float) -> str:
    return f"{value:,.2f}"


def styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="DocTitle", parent=s["Title"], fontName="Helvetica-Bold",
        fontSize=16, leading=20, textColor=colors.HexColor("#152b45"), alignment=TA_CENTER, spaceAfter=8))
    s.add(ParagraphStyle(name="Small", parent=s["Normal"], fontSize=8, leading=11))
    s.add(ParagraphStyle(name="Banner", parent=s["Normal"], fontName="Helvetica-Bold",
        fontSize=9, leading=12, textColor=colors.HexColor("#a32121"), alignment=TA_CENTER))
    return s


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#a32121"))
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawCentredString(A4[0] / 2, 13 * mm, "SYNTHETIC TEST DOCUMENT - NOT ISSUED BY ANY FINANCIAL INSTITUTION")
    canvas.setFillColor(colors.HexColor("#555555"))
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(A4[0] - 18 * mm, 8 * mm, f"Page {doc.page} of 1")
    canvas.restoreState()


def write_statement(path: Path, name: str, ref: str, year: int, month: int,
                    income: float, expense_ratio: float, emi_ratio: float, buffer_months: float):
    month_start = f"01/{month:02d}/{year}"
    month_end = f"{calendar.monthrange(year, month)[1]:02d}/{month:02d}/{year}"
    expenses = income * expense_ratio
    emi = income * emi_ratio
    remaining = expenses - emi
    parts = [remaining * .52, remaining * .17, remaining * .13, emi, remaining * .07, remaining * .06, remaining * .05]
    opening = expenses * buffer_months
    entries = [
        (1, "SALARY CREDIT - FICTIONAL EMPLOYER", 0.0, income),
        (3, "HOUSE RENT NEFT", parts[0], 0.0),
        (6, "GROCERY AND HOUSEHOLD UPI", parts[1], 0.0),
        (9, "ELECTRICITY AND TELECOM BILL", parts[2], 0.0),
        (12, "PERSONAL LOAN EMI AUTODEBIT", parts[3], 0.0),
        (17, "LOCAL TRANSPORT UPI", parts[4], 0.0),
        (21, "RETAIL PURCHASE", parts[5], 0.0),
        (25, "PHARMACY AND HEALTH SPEND", parts[6], 0.0),
    ]
    balance = opening
    rows = [["Date", "Narration", "Debit INR", "Credit INR", "Balance INR"]]
    for day, narration, debit, credit in entries:
        balance += credit - debit
        rows.append([f"{day:02d}/{month:02d}/{year}", narration,
            amount(debit) if debit else "-", amount(credit) if credit else "-", amount(balance)])
    doc = styles()
    story = [Paragraph("SYNTHETIC TEST RECORD - NOT BANK ISSUED", doc["Banner"]),
        Spacer(1, 5 * mm), Paragraph("SAVINGS ACCOUNT STATEMENT", doc["DocTitle"]),
        Paragraph("Generic Indian statement layout for software testing only. No real bank is represented.", doc["Small"]),
        Spacer(1, 4 * mm),
        Paragraph(f"Account Name: {name} (FICTIONAL)", doc["Normal"]),
        Paragraph(f"Bank: Generic test layout | Account reference: TEST-{ref}", doc["Small"]),
        Paragraph(f"Currency: INR | Statement period: {month_start} to {month_end}", doc["Small"]),
        Paragraph(f"Opening balance: INR {amount(opening)}", doc["Small"]),
        Paragraph(f"Closing balance: INR {amount(balance)}", doc["Small"]),
        Paragraph("Transaction count: 8 | All entries and balances are invented.", doc["Small"]), Spacer(1, 5 * mm)]
    table = Table(rows, colWidths=[60, 180, 82, 82, 82], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173957")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.4),
        ("LEADING", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#bbc4cc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f4f6")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([table, Spacer(1, 6 * mm), Paragraph(
        "Fictional software-test data. Not proof of identity, income, account ownership, or a bank transaction.", doc["Small"])])
    SimpleDocTemplate(str(path), pagesize=A4, rightMargin=17 * mm, leftMargin=17 * mm,
        topMargin=15 * mm, bottomMargin=23 * mm).build(story, onFirstPage=footer)


def write_salary(path: Path, name: str, year: int, month: int, income: float):
    gross = round(income * 1.08, 2)
    deductions = round(gross - income, 2)
    s = styles()
    rows = [["Earnings / deductions", "Amount (INR)"], ["Monthly gross earnings", amount(gross)],
        ["Statutory and other deductions", amount(deductions)], ["Net salary paid", amount(income)]]
    table = Table(rows, colWidths=[300, 150], hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173957")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#bbc4cc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f4f6")]),
        ("FONTSIZE", (0, 0), (-1, -1), 9), ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story = [Paragraph("SYNTHETIC TEST RECORD - NOT EMPLOYER ISSUED", s["Banner"]), Spacer(1, 5 * mm),
        Paragraph("MONTHLY SALARY SLIP", s["DocTitle"]),
        Paragraph(f"Employee Name: {name} (FICTIONAL)", s["Normal"]),
        Paragraph(f"Employer: Fictional Test Employer | Salary month: {calendar.month_name[month]} {year}", s["Small"]),
        Paragraph("Employee reference: TEST-EMPLOYEE | Currency: INR", s["Small"]), Spacer(1, 7 * mm), table,
        Spacer(1, 6 * mm), Paragraph("All employer, employee and salary details on this page are invented for software testing.", s["Small"])]
    SimpleDocTemplate(str(path), pagesize=A4, rightMargin=22 * mm, leftMargin=22 * mm,
        topMargin=18 * mm, bottomMargin=23 * mm).build(story, onFirstPage=footer)


def write_utility(path: Path, name: str, ref: str, year: int, month: int, income: float):
    s = styles()
    due = round(income * .035, 2)
    rows = [["Description", "Amount (INR)"], ["Electricity, water and telecom service", amount(due)],
        ["Payments recorded", amount(due)], ["Balance due", amount(0)]]
    table = Table(rows, colWidths=[300, 150], hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173957")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#bbc4cc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f4f6")]),
        ("FONTSIZE", (0, 0), (-1, -1), 9), ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    last_day = calendar.monthrange(year, month)[1]
    story = [Paragraph("SYNTHETIC TEST RECORD - NOT UTILITY ISSUED", s["Banner"]), Spacer(1, 5 * mm),
        Paragraph("UTILITY SERVICE BILL", s["DocTitle"]),
        Paragraph(f"Consumer Name: {name} (FICTIONAL)", s["Normal"]),
        Paragraph("Provider: Fictional Utility Test Service | Consumer reference: TEST-" + ref, s["Small"]),
        Paragraph(f"Billing period: 01/{month:02d}/{year} to {last_day:02d}/{month:02d}/{year}", s["Small"]),
        Paragraph("Payment status: PAID | Currency: INR", s["Small"]), Spacer(1, 7 * mm), table,
        Spacer(1, 6 * mm), Paragraph("All provider, consumer and billing details on this page are invented for software testing.", s["Small"])]
    SimpleDocTemplate(str(path), pagesize=A4, rightMargin=22 * mm, leftMargin=22 * mm,
        topMargin=18 * mm, bottomMargin=23 * mm).build(story, onFirstPage=footer)


def build():
    for name, profile in APPLICANTS.items():
        applicant_dir = DEST / f"SYNTHETIC - {name}"
        if applicant_dir.exists():
            raise FileExistsError(f"Refusing to overwrite existing folder: {applicant_dir}")
        for index, (year, month) in enumerate(MONTHS):
            case = applicant_dir / f"Case {year}-{month:02d}"
            bank = case / "Bank Statements"
            salary = case / "Salary Slips"
            utility = case / "Utility Bills"
            for directory in (bank, salary, utility):
                directory.mkdir(parents=True, exist_ok=False)
            month_id = f"{year}-{month:02d}"
            income = profile["income"][index]
            write_statement(bank / f"Bank_Statement_{month_id}.pdf", name, profile["ref"], year, month,
                income, profile["expense_ratio"][index], profile["emi_ratio"][index], profile["buffer_months"][index])
            write_salary(salary / f"Salary_Slip_{month_id}.pdf", name, year, month, income)
            write_utility(utility / f"Utility_Bill_{month_id}.pdf", name, profile["ref"], year, month, income)
        (applicant_dir / "README.txt").write_text(
            "PRISM UPLOAD TEST PACK - SYNTHETIC / FICTIONAL\n\n"
            f"Fictional applicant: {name}. Six isolated monthly cases from 2026-03 through 2026-08. "
            "Each case contains one required bank statement and matching optional salary slip and utility bill.\n\n"
            "All files are visibly marked synthetic and are not issued by any bank, employer, or utility provider. "
            "Layouts are generic Indian financial-document examples and do not imitate a named institution. "
            "One case should be uploaded at a time. Do not treat the resulting experimental cash-flow index as a validated credit score or lending decision.\n",
            encoding="utf-8")
    (DEST / "SYNTHETIC - Additional Applicants README.txt").write_text(
        "Four fictional applicant packs were created: Sujata Deshmukh, Anjali Singh, Vedant Patil, and Irfan Mohammad. "
        "Each has six month-specific cases with matching bank, salary, and utility documents. "
        "Every document is marked synthetic / not issued. Generic layouts only; no actual institution is represented. "
        "The uploaded transaction rows drive PRISM's existing experimental cash-flow calculation; scores are not embedded in the PDFs.\n",
        encoding="utf-8")
    print("Created 72 marked synthetic PDFs across 24 individual upload cases.")


if __name__ == "__main__":
    build()

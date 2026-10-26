"""Generate the synthetic policies, claim documents and ground truth (LLD §6.7–6.8).

Every person, policy number, ID number, phone number and address here is invented. ID numbers use month 00,
so they cannot be real South African ID numbers. Output is deterministic and committed; rerun with:

    python scripts/generate_samples.py
"""

from __future__ import annotations

import io
import json
import random
from datetime import datetime
from pathlib import Path

from docx import Document
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ROOT / "data" / "policies"
CLAIMS = ROOT / "data" / "claims"
TRUTH = ROOT / "data" / "ground_truth"
FIXED_TIME = datetime(2026, 10, 24, 9, 0, 0)

# ---- policies -----------------------------------------------------------------------------------------

MOTOR_POLICY = """\
Lekker Cover Insurance — Motor Comprehensive Policy Wording (synthetic, for testing only)
This wording applies to policy numbers starting with MOT-. Amounts are in South African rand (ZAR).

## 1 Definitions
"You" means the policyholder named in the schedule. "Vehicle" means the vehicle described in the schedule.
"Excess" means the first amount of each claim that you pay yourself.

## 2 Cover — accidental damage
We cover loss of or damage to the vehicle caused by a collision, overturning or other accidental, sudden and
external event, including damage caused by another road user. We pay the reasonable cost of repair at an
approved repairer, or the retail value of the vehicle if repair is uneconomical.

## 3 Cover — theft and hijacking
We cover theft or hijacking of the vehicle, and damage caused during an attempted theft. The theft must be
reported to the South African Police Service within 24 hours and a case number supplied with the claim.

## 4.1 Exclusions — driver
We do not cover loss or damage while the vehicle is driven by a person without a valid driving licence, or by
a person whose blood alcohol concentration is above the legal limit.

## 4.2 Exclusions — wear and tear and mechanical failure
We do not cover wear and tear, rust, mechanical or electrical breakdown, or tyre damage caused by braking,
punctures or road surfaces, unless the vehicle was damaged in the same insured event.

## 4.3 Exclusions — unauthorised use
We do not cover loss or damage while the vehicle is used for hire, racing or speed tests, or by a person you
did not authorise, except under section 3 (theft and hijacking).

## 5 Excess
The basic excess is 5% of the claim amount, with a minimum of R5 000 per claim. The excess applies to every
claim under sections 2 and 3.

## 6 Claims procedure
You must notify us within 30 days of the incident. A claim must include the policy number, the date of the
incident, a description of what happened, a repair quotation or proof of value, and, for an accident or theft,
the police case number. We may decline or delay a claim until the required information is supplied.
"""

HOME_POLICY = """\
Lekker Cover Insurance — Home Buildings and Contents Policy Wording (synthetic, for testing only)
This wording applies to policy numbers starting with HOM-. Amounts are in South African rand (ZAR).

## 1 Definitions
"Buildings" means the main dwelling, outbuildings, fixed fittings, roof and fixed solar installations at the
address in the schedule. "Contents" means household goods owned by you inside the buildings.

## 2 Cover — storm, wind, hail and lightning
We cover sudden damage to the buildings and contents caused by storm, wind, hail, lightning or flood,
including damage to the roof, gutters, windows and fixed solar panels.

## 3 Cover — sudden escape of water
We cover damage caused by water that escapes suddenly from a burst pipe, geyser, tank or fixed appliance, and
the cost of tracing the source of the escape.

## 4.1 Exclusions — wear and tear
We do not cover wear and tear, gradual deterioration, or the cost of maintaining the buildings.

## 4.2 Exclusions — gradual damage
We do not cover damage that happens gradually over time, including water that leaks or seeps slowly, damp,
rising damp, mould, wet rot or dry rot, whether or not the cause was visible. Section 3 covers only water that
escapes suddenly.

## 4.3 Exclusions — unoccupied buildings
We do not cover theft or water damage while the buildings have been unoccupied for more than 60 days in a row.

## 5 Excess
The basic excess is R2 500 per claim. Storm and hail claims carry an additional excess of R1 000.

## 6 Claims procedure
You must notify us within 30 days of discovering the damage. A claim must include the policy number, the date of
the incident or discovery, a description, and a repair quotation. We may appoint an assessor before we accept a
claim.
"""

# ---- claims and ground truth ----------------------------------------------------------------------------

TRUTHS = {
    "motor_clean": {
        "fields": {
            "claimant": "Thandi Mokoena",
            "policy_number": "MOT-482913",
            "incident_date": "2026-09-14",
            "incident_type": "motor_collision",
            "amount_claimed": 38450.00,
            "currency": "ZAR",
            "description": "The insured vehicle was hit from behind while stopped at a traffic light, damaging the "
            "rear bumper, boot and tail lights.",
            "missing_info": [],
        },
        "expected_coverage_decision": "covered",
        "expected_route": "auto_approve",
        "expected_clause_ids": ["motor_comprehensive:2"],
        "notes": "Happy path: complete text-layer PDF, collision under section 2, below the high-value threshold.",
    },
    "home_gradual_leak": {
        "fields": {
            "claimant": "Pieter van der Merwe",
            "policy_number": "HOM-215067",
            "incident_date": "2026-09-28",
            "incident_type": "home_water",
            "amount_claimed": 27800.00,
            "currency": "ZAR",
            "description": "Water damage, damp and rot behind the shower wall, found during tiling; the plumber "
            "says a slow leak had been seeping for about eight months.",
            "missing_info": [],
        },
        "expected_coverage_decision": "not_covered",
        "expected_route": "auto_approve",
        "expected_clause_ids": ["home_buildings_contents:4.2"],
        "notes": "Exclusion hit: water damage sounds like section 3, but the plumber's report shows a gradual leak "
        "(section 4.2). Tests whether the model reads past the claimant's framing. incident_date is the date of "
        "discovery.",
    },
    "home_storm": {
        "fields": {
            "claimant": "Nomvula Dlamini",
            "policy_number": "HOM-730442",
            "incident_date": "2026-10-05",
            "incident_type": "home_storm",
            "amount_claimed": 64200.00,
            "currency": "ZAR",
            "description": "A hailstorm broke roof tiles and two solar panels and let rain into the main bedroom, "
            "damaging the ceiling and a bed.",
            "missing_info": [],
        },
        "expected_coverage_decision": "covered",
        "expected_route": "human_review",
        "expected_clause_ids": ["home_buildings_contents:2"],
        "notes": "Plain-text email with PII (email, phone, ID number) for redaction. Covered under section 2, "
        "but above the R50 000 high-value threshold, so routed to human review.",
    },
    "motor_messy_scan": {
        "fields": {
            "claimant": "Jayden Naidoo",
            "policy_number": None,
            "incident_date": None,
            "incident_type": "motor_theft",
            "amount_claimed": 21000.00,
            "currency": "ZAR",
            "description": "The claimant's car was stolen from outside a shopping centre; the claimant does not "
            "have the policy number and is unsure of the date.",
            "missing_info": ["policy_number", "incident_date", "police_case_number"],
        },
        "expected_coverage_decision": "insufficient_information",
        "expected_route": "human_review",
        "expected_clause_ids": ["motor_comprehensive:3"],
        "notes": "Image-only scan (no text layer). Policy number left blank, date written as 03/04 with a note "
        "(ambiguous day/month, and either reading is months before the claim), no police case number. "
        "Correct behaviour: nulls with reasons in missing_info, never invented values.",
    },
}


def _motor_clean_pdf(path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    pdf.setTitle("Motor claim form")
    y = A4[1] - 25 * mm

    def line(text: str, size: int = 11, gap: float = 7) -> None:
        nonlocal y
        pdf.setFont("Helvetica-Bold" if size > 11 else "Helvetica", size)
        pdf.drawString(20 * mm, y, text)
        y -= gap * mm

    line("Lekker Cover Insurance — Motor Claim Form", 16, 12)
    for label, value in [
        ("Policyholder", "Thandi Mokoena"),
        ("Policy number", "MOT-482913"),
        ("Vehicle", "2021 Toyota Corolla Cross, registration CA 123-456"),
        ("Date of incident", "14 September 2026 (2026-09-14), approximately 17:40"),
        ("Place", "Corner of Main Road and Belvedere Road, Claremont, Cape Town"),
        ("Police case number", "CAS 214/09/2026, Claremont SAPS"),
        ("Amount claimed", "R 38 450.00 (repair quotation attached)"),
        ("Date reported", "16 September 2026"),
    ]:
        line(f"{label}: {value}")
    y -= 4 * mm
    line("What happened", 13, 8)
    for text in [
        "I was stopped at a red traffic light when a minibus taxi drove into the back of my car.",
        "The rear bumper, boot lid and both tail lights were damaged. Nobody was injured. The taxi",
        "driver's details and the police case number are given above. I was not under the influence",
        "of alcohol and hold a valid code B licence.",
    ]:
        line(text, gap=6)
    y -= 4 * mm
    line("Repair quotation — Claremont Panelbeaters (approved repairer)", 13, 8)
    for item, amount in [
        ("Rear bumper replace and paint", "R 14 200.00"),
        ("Boot lid repair and paint", "R 15 650.00"),
        ("Tail light assemblies x2", "R 6 300.00"),
        ("Labour and sundries", "R 2 300.00"),
        ("Total (incl. VAT)", "R 38 450.00"),
    ]:
        pdf.setFont("Helvetica", 11)
        pdf.drawString(20 * mm, y, item)
        pdf.drawRightString(130 * mm, y, amount)
        y -= 6 * mm
    pdf.showPage()
    pdf.save()


def _home_gradual_leak_docx(path: Path) -> None:
    doc = Document()
    doc.core_properties.author = "Synthetic test data"
    doc.core_properties.created = FIXED_TIME
    doc.core_properties.modified = FIXED_TIME
    doc.add_heading("Home Insurance Claim — Water Damage", level=1)
    table = doc.add_table(rows=0, cols=2)
    for label, value in [
        ("Policyholder", "Pieter van der Merwe"),
        ("Policy number", "HOM-215067"),
        ("Address", "14 Jakaranda Street, Brooklyn, Pretoria"),
        ("Date damage discovered", "28 September 2026"),
        ("Amount claimed", "R27 800.00"),
    ]:
        cells = table.add_row().cells
        cells[0].text, cells[1].text = label, value
    doc.add_paragraph(
        "Policyholder: Pieter van der Merwe. Policy number: HOM-215067. Date discovered: 2026-09-28. "
        "Amount claimed: R27 800.00."
    )
    doc.add_heading("Description", level=2)
    doc.add_paragraph(
        "On 28 September 2026 our tiler removed the old tiles in the main bathroom and found the wall behind "
        "the shower soaked, with black mould and the bottom of the wooden door frame rotten. We would like to "
        "claim for the water damage: replacing the wall board, the door frame and retiling."
    )
    doc.add_heading("Plumber's report — Pipe Pros Plumbing, 30 September 2026", level=2)
    doc.add_paragraph(
        "The mixer valve behind the shower wall has a worn seal and has been leaking slowly into the wall "
        "cavity. Staining, mould growth and the extent of the rot indicate the leak has been seeping for "
        "approximately eight months. There was no burst pipe and no sudden failure. Seal replaced; leak stopped."
    )
    doc.add_heading("Quotation", level=2)
    for item in [
        "Strip and replace wall board: R9 600.00",
        "Replace door frame: R4 200.00",
        "Retile shower wall: R11 500.00",
        "Plumber call-out and seal: R2 500.00",
        "Total: R27 800.00",
    ]:
        doc.add_paragraph(item, style="List Bullet")
    doc.save(str(path))


HOME_STORM_TXT = """\
From: Nomvula Dlamini <nomvula.dlamini@example.com>
To: claims@lekkercover.example
Date: Tue, 7 Oct 2026 08:12:44 +0200
Subject: Hail damage claim - policy HOM-730442

Good morning

I want to claim for damage from the hailstorm on Sunday 5 October 2026 (2026-10-05) at about 15:30.

Policy number: HOM-730442
Address: 3 Sunbird Close, Bryanston, Johannesburg
ID number: 9900005800083
Cell: 082 555 0147

Hailstones the size of golf balls broke about forty roof tiles and cracked two of the solar panels on the
north roof. Rain came through the broken tiles into the main bedroom, so the ceiling boards are sagging and
stained, and the mattress and base of our bed are soaked.

Quotations attached:
- Roof tiles and labour (Highveld Roofing): R18 900.00
- Two solar panels supplied and fitted (SunPower Gauteng): R27 600.00
- Ceiling boards and painting: R9 200.00
- Bed (mattress and base) replacement: R8 500.00
Total claimed: R64 200.00

You can call me on +27 82 555 0147 or reply to this email.

Kind regards
Nomvula Dlamini
"""


def _messy_scan_pdf(path: Path) -> None:
    """A phone photo of a hand-filled form: grey paper, noise, a slight tilt, a coffee ring. No text layer."""
    rng = random.Random(42)  # noqa: S311 — deterministic noise, not security
    width, height = 1240, 1754  # A4 at 150 DPI
    page = Image.new("L", (width, height), 236)
    draw = ImageDraw.Draw(page)
    for _ in range(25000):
        x, y = rng.randrange(width), rng.randrange(height)
        draw.point((x, y), fill=rng.randrange(180, 250))
    draw.ellipse((820, 1180, 1100, 1450), outline=200, width=18)  # coffee ring

    printed = ImageFont.load_default(size=34)
    written = ImageFont.load_default(size=40)
    draw.text((90, 90), "LEKKER COVER - VEHICLE THEFT CLAIM FORM", font=printed, fill=40)
    rows = [
        ("Name:", "Jayden Naidoo"),
        ("Policy no:", "________  (cant find my papers)"),
        ("Date of loss:", "03/04   (or the 4th? not sure)"),
        ("Vehicle:", "VW Polo Vivo, silver"),
        ("Where:", "outside Gateway mall, Umhlanga"),
        ("Police case no:", ""),
        ("Value / amount:", "R 21 000 approx"),
    ]
    y = 220
    for label, value in rows:
        draw.text((90, y), label, font=printed, fill=50)
        draw.text((470 + rng.randrange(-6, 6), y + rng.randrange(-4, 4)), value, font=written, fill=25)
        draw.line((460, y + 48, 1150, y + 48), fill=120, width=2)
        y += 110
    draw.text((90, y + 40), "What happened:", font=printed, fill=50)
    story = [
        "parked the car and went in to buy groceries,",
        "came out about an hour later and it was gone.",
        "security guard said he saw nothing. I will",
        "go to the police station still.",
    ]
    for i, text in enumerate(story):
        draw.text((110 + rng.randrange(-8, 8), y + 120 + i * 70), text, font=written, fill=30)
    draw.line((470, 220 + 2 * 110 + 20, 640, 220 + 2 * 110 + 10), fill=30, width=4)  # scribble over the date

    page = page.rotate(1.6, resample=Image.Resampling.BICUBIC, fillcolor=210).filter(
        ImageFilter.GaussianBlur(1.1)
    )
    buffer = io.BytesIO()
    page.save(buffer, format="PDF", resolution=150)
    path.write_bytes(buffer.getvalue())


def main() -> None:
    for folder in (POLICIES, CLAIMS, TRUTH):
        folder.mkdir(parents=True, exist_ok=True)
    (POLICIES / "motor_comprehensive.txt").write_text(MOTOR_POLICY)
    (POLICIES / "home_buildings_contents.txt").write_text(HOME_POLICY)
    _motor_clean_pdf(CLAIMS / "motor_clean.pdf")
    _home_gradual_leak_docx(CLAIMS / "home_gradual_leak.docx")
    (CLAIMS / "home_storm.txt").write_text(HOME_STORM_TXT)
    _messy_scan_pdf(CLAIMS / "motor_messy_scan.pdf")
    for stem, truth in TRUTHS.items():
        (TRUTH / f"{stem}.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False) + "\n")
    print(
        f"wrote 2 policies, {len(TRUTHS)} claims and {len(TRUTHS)} ground-truth files under {ROOT / 'data'}"
    )


if __name__ == "__main__":
    main()

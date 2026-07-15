"""Generate the sample month (2026-06) used for the demo and as a
reference for input formats. Run from anywhere:

    python3 kv-fos/tools/make_sample_data.py [target_inputs_dir] [month]
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]


def build(inputs: Path, month: str = "2026-06") -> None:
    inputs.mkdir(parents=True, exist_ok=True)
    y_m = month

    # ---- accounting workbook -------------------------------------------
    wb = Workbook()
    ws = wb.active
    ws.title = "GeneralLedger"
    ws.append(["Date", "BankAccount", "AccountCode", "Counterparty",
               "Description", "AmountUAH", "Center", "InvoiceRef"])
    ledger = [
        (f"{y_m}-05", "privat_uah", "", "Wise Europe SA",
         "Transfer from Friends of Kinder Velt USA", 498000, "", ""),
        (f"{y_m}-10", "privat_uah", "631-RENT", "ФОП Юриев",
         "Оренда приміщення, червень", -52000, "Kyiv", "INV-101"),
        (f"{y_m}-12", "privat_uah", "631-UTIL", "Р-Технопарк",
         "Комунальні послуги", -14500, "", "INV-102"),
        (f"{y_m}-15", "privat_uah", "661-PAYR", "Заробітна плата",
         "Виплата зарплати за червень", -180000, "", "PAY-06"),
        (f"{y_m}-15", "privat_uah", "641-PTAX", "ДПС України",
         "ЄСВ та ПДФО за червень", -39600, "", "PAY-06"),
        (f"{y_m}-18", "privat_uah", "631-SHIP", "Нова Пошта",
         "Доставка матеріалів до Харкова", -3200, "Kharkiv", "EXP-77"),
        (f"{y_m}-20", "privat_uah", "631-MATL", "ТОВ Арт-Плюс",
         "Терапевтичні матеріали", -21500, "Odessa", "INV-103"),
        (f"{y_m}-25", "privat_uah", "685-BANK", "ПриватБанк",
         "Комісія банку", -450, "", ""),
        (f"{y_m}-30", "oschad_uah", "", "Ощадбанк",
         "Нараховані відсотки", 120, "", ""),
    ]
    for row in ledger:
        ws.append(list(row))

    ws = wb.create_sheet("PayrollRegister")
    ws.append(["Employee", "Role", "Center", "GrossUAH", "TaxesUAH", "NetUAH"])
    for row in [
        ("Іваненко О.", "Psychologist", "Kyiv", 42000, 9240, 32760),
        ("Петренко М.", "Psychologist", "Kharkiv", 42000, 9240, 32760),
        ("Сидоренко Т.", "Therapist", "Odessa", 38000, 8360, 29640),
        ("Коваленко Л.", "Program Staff", "Mykolaiv", 30000, 6600, 23400),
        ("Бондаренко С.", "Program Staff", "Kyiv", 28000, 6160, 21840),
    ]:
        ws.append(list(row))

    ws = wb.create_sheet("Balances")
    ws.append(["BankAccount", "OpeningUAH", "ClosingUAH"])
    ws.append(["privat_uah", 250000, 436750])
    ws.append(["oschad_uah", 100000, 100120])

    ws = wb.create_sheet("ChartOfAccounts")
    ws.append(["Code", "Name"])
    for code, name in [("631-RENT", "Оренда"), ("631-UTIL", "Комунальні"),
                       ("661-PAYR", "Оплата праці"), ("641-PTAX", "Податки"),
                       ("631-SHIP", "Доставка"), ("631-MATL", "Матеріали"),
                       ("685-BANK", "Банківські послуги")]:
        ws.append([code, name])
    wb.save(inputs / f"workbook_{y_m}.xlsx")

    # ---- bank statements -------------------------------------------------
    def write_csv(name, headers, rows):
        with open(inputs / name, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(headers)
            w.writerows(rows)

    balance = 250000
    privat_rows = []
    for d, cp, desc, amt in [
        (f"{y_m}-05", "WISE EUROPE SA", "SWIFT credit KINDER VELT USA", 498000),
        (f"{y_m}-10", "ФОП ЮРИЕВ", "Оренда червень", -52000),
        (f"{y_m}-12", "Р-ТЕХНОПАРК", "Комунальні послуги", -14500),
        (f"{y_m}-15", "", "Виплата зарплати за червень", -180000),
        (f"{y_m}-15", "ДПС", "ЄСВ та ПДФО", -39600),
        (f"{y_m}-18", "НОВА ПОШТА", "Доставка", -3200),
        (f"{y_m}-20", "ТОВ АРТ-ПЛЮС", "Матеріали", -21500),
        (f"{y_m}-25", "ПРИВАТБАНК", "Комісія банку", -450),
    ]:
        balance += amt
        privat_rows.append([d, desc, cp, amt, balance])
    write_csv(f"bank_privat_uah_{y_m}.csv",
              ["Date", "Description", "Counterparty", "Amount", "Balance"],
              privat_rows)
    write_csv(f"bank_oschad_uah_{y_m}.csv",
              ["Date", "Description", "Counterparty", "Amount", "Balance"],
              [[f"{y_m}-30", "Нараховані відсотки", "ОЩАДБАНК", 120, 100120]])

    # ---- center statistics ------------------------------------------------
    write_csv(f"CenterUpdates_{y_m}.csv",
              ["Center", "ChildrenServed", "Consultations", "Classes",
               "NewChildren"],
              [["Kyiv", 145, 62, 88, 9], ["Kharkiv", 118, 48, 74, 7],
               ["Odessa", 96, 41, 60, 5], ["Mykolaiv", 84, 30, 52, 4]])

    # ---- wise transfer confirmation ---------------------------------------
    write_csv(f"wise_{y_m}.csv",
              ["TransferID", "DateSent", "AmountUSD", "DateDelivered",
               "AmountUAH", "Rate", "Reference", "FundingSource"],
              [["TR-8801", f"{y_m}-03", 12000, f"{y_m}-05", 498000, 41.50,
                "June operations", "fokv_general"]])

    # ---- funding request letter -------------------------------------------
    (inputs / f"funding_request_{y_m}.txt").write_text(
        "Friends of Kinder Velt USA — Funding Request\n\n"
        f"Kinder Velt Ukraine requests $12,000 for {y_m} operations:\n"
        "psychologist payroll, rent for the Kyiv center, utilities,\n"
        "therapy materials, and logistics.\n", encoding="utf-8")


if __name__ == "__main__":
    target = (Path(sys.argv[1]) if len(sys.argv) > 1
              else ROOT / "months" / "2026-06" / "inputs")
    month = sys.argv[2] if len(sys.argv) > 2 else "2026-06"
    build(target, month)
    print(f"sample inputs written to {target}")

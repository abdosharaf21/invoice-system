"""Seed tax-authority invoices into the Phase 15 UAT scratch database.

Direct SQL seeding: the shipped product reads tax authority documents from
an external E-Invoice integration (out of scope of this repo), so there is
no product API to create them. The reconciliation engine consumes them from
``tax_invoices``/``tax_invoice_items`` and that is exactly what this script
provides for the UAT.

Mirrors the accounting invoices seeded via CSV import so reconciliation can
produce every outcome class:
  * matched                 (INV-A001, INV-A004, INV-A005, INV-B001)
  * mismatched              (INV-A002 - VAT/total differ)
  * missing_in_tax_authority (INV-A003 - no copy here)
  * extra_in_tax_authority   (uuid not claimed by any accounting invoice)
  * invalid                  (malformed uuid on an unclaimed document)
"""

import os

import mysql.connector

DB_NAME = os.environ.get("EINVOICE_UAT_DB", "einv_uat_p15")
DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "abdo2146")

SELLER_A = "UAT Company A"
TAX_A = "UATA1111111111"

# (company, uuid, internal_id, issue_datetime, buyer_name, buyer_tax_id,
#  total_sales, total_discount, net, vat, other, total, items)
# item = (description, quantity, unit_value, vat_rate, vat_amount, discount, total_amount)
TAX_INVOICES = [
    (1, "11111111-0000-4000-8000-000000000001", "A-TAX-001", "2026-08-05 12:00:00",
     "Acme Trading Co", "3000123456", 1000.00, 0.00, 1000.00, 140.00, 0.00, 1140.00,
     [("Consulting services", 10, 100.00, 14, 140.00, 0.00, 1140.00)]),
    (1, "11111111-0000-4000-8000-000000000002", "A-TAX-002", "2026-08-12 12:00:00",
     "Beta Retail Ltd", "3000789012", 500.00, 0.00, 500.00, 100.00, 0.00, 600.00,
     [("Retail goods", 5, 100.00, 14, 100.00, 0.00, 600.00)]),
    (1, "11111111-0000-4000-8000-000000000004", "A-TAX-004", "2026-08-08 12:00:00",
     "Delta Logistics", "3000777888", 800.00, 0.00, 800.00, 112.00, 0.00, 912.00,
     [("Line item one", 3, 200.00, 14, 84.00, 0.00, 684.00),
      ("Line item two", 4, 50.00, 14, 28.00, 0.00, 228.00)]),
    (1, None, "INV-A005", "2026-08-25 12:00:00",
     "Epsilon Supplies", "3000999000", 250.00, 0.00, 250.00, 35.00, 0.00, 285.00,
     [("Spare parts", 1, 250.00, 14, 35.00, 0.00, 285.00)]),
    (1, "eeeeeeee-0000-4000-8000-000000000001", "tx-extra", "2026-08-15 12:00:00",
     "Mystery Buyer", "3000777000", 999.00, 0.00, 999.00, 139.86, 0.00, 1138.86,
     [("Unclaimed goods", 1, 999.00, 14, 139.86, 0.00, 1138.86)]),
    (1, "not-a-valid-uuid", "tx-baduuid", "2026-08-18 12:00:00",
     "Broken UUID Buyer", "3000555000", 50.00, 0.00, 50.00, 7.00, 0.00, 57.00,
     [("Broken uuid goods", 1, 50.00, 14, 7.00, 0.00, 57.00)]),
]

TAX_INVOICES_B = [
    (2, "bbbbbbbb-0000-4000-8000-000000000001", "B-TAX-001", "2026-08-10 12:00:00",
     "Company B Counterparty", "9000111222", 200.00, 0.00, 200.00, 28.00, 0.00, 228.00,
     [("Printed materials", 8, 25.00, 14, 28.00, 0.00, 228.00)]),
]


def create_tax_invoice(cursor, row) -> None:
    company, uuid, internal, issued, buyer, buyer_tax, sales, disc, net, vat, other, total, items = row
    cursor.execute(
        "INSERT INTO tax_invoices (company_id, uuid, internal_id, document_type, "
        "issue_datetime, currency, exchange_rate, seller_name, seller_tax_id, "
        "buyer_name, buyer_tax_id, total_sales, total_discount, net_amount, "
        "vat_amount, other_charges, total_amount, submission_status) "
        "VALUES (%s, %s, %s, 'invoice', %s, 'EGP', 1.0, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'approved')",
        (company, uuid, internal, issued, SELLER_A, TAX_A, buyer, buyer_tax,
         sales, disc, net, vat, other, total),
    )
    tid = cursor.lastrowid
    for desc, qty, unit, rate, vat_amt, item_disc, total_amt in items:
        cursor.execute(
            "INSERT INTO tax_invoice_items (tax_invoice_id, description, item_type, "
            "quantity, unit_value, vat_rate, vat_amount, discount_amount, total_amount) "
            "VALUES (%s, %s, 'composite', %s, %s, %s, %s, %s, %s)",
            (tid, desc, qty, unit, rate, vat_amt, item_disc, total_amt),
        )
    return tid


def main() -> None:
    conn = mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, autocommit=False,
    )
    cursor = conn.cursor()
    created = []
    for row in TAX_INVOICES:
        uuid = row[1]
        if uuid:
            cursor.execute("SELECT id FROM tax_invoices WHERE uuid = %s", (uuid,))
        else:
            cursor.execute(
                "SELECT id FROM tax_invoices WHERE company_id = %s AND internal_id = %s",
                (row[0], row[2]),
            )
        if cursor.fetchone():
            print(f"skip existing tax invoice internal_id={row[2]}")
            continue
        tid = create_tax_invoice(cursor, row)
        created.append((tid, row[2]))
    for row in TAX_INVOICES_B:
        uuid = row[1]
        cursor.execute("SELECT id FROM tax_invoices WHERE uuid = %s", (uuid,))
        if cursor.fetchone():
            print("skip existing company B tax invoice")
            continue
        tid = create_tax_invoice(cursor, row)
        created.append((tid, row[2]))
    conn.commit()
    cursor.close()
    conn.close()
    print("created tax invoices:", created)


if __name__ == "__main__":
    main()
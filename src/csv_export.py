# src/csv_export.py
"""Export reference JSON files to CSV."""

import csv
import pathlib


def export_vendor_reference(config, output_path: str | None = None) -> str:
    """
    Export vendor_reference.json to CSV.

    Returns the path to the written CSV file.
    """
    vendor_ref = config.vendor_reference
    vendors = vendor_ref.get("vendors", {})

    if output_path is None:
        exports_dir = pathlib.Path(config.settings["config_path"]) / "Exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(exports_dir / "vendor_reference.csv")

    fieldnames = [
        "key", "name", "aliases", "address", "account_id",
        "phone", "tax_id", "date_added", "added_from_invoice",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for key, entry in vendors.items():
            row = {"key": key}
            row.update(entry)
            row["aliases"] = ";".join(entry.get("aliases", []))
            writer.writerow(row)

    return output_path


def export_company_reference(config, output_path: str | None = None) -> str:
    """
    Export company_reference.json to CSV.

    Returns the path to the written CSV file.
    """
    company_ref = config.company_reference
    companies = company_ref.get("companies", {})

    if output_path is None:
        exports_dir = pathlib.Path(config.settings["config_path"]) / "Exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(exports_dir / "company_reference.csv")

    fieldnames = ["key", "name", "code", "aliases"]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for key, entry in companies.items():
            row = {"key": key}
            row.update(entry)
            row["aliases"] = ";".join(entry.get("aliases", []))
            writer.writerow(row)

    return output_path

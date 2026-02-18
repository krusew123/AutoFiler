# src/csv_export.py
"""Export reference JSON files to CSV."""

import csv
import pathlib


def export_reference(
    config,
    relative_path: str,
    top_level_key: str,
    fieldnames: list[str],
    output_filename: str,
    output_path: str | None = None,
) -> str:
    """
    Export any reference JSON file to CSV.

    Args:
        config: ConfigLoader instance.
        relative_path: Config-relative path to the reference JSON file.
        top_level_key: Top-level key in the JSON (e.g. "vendors", "companies").
        fieldnames: List of CSV column names.
        output_filename: Default filename for the CSV (e.g. "vendor_reference.csv").
        output_path: Optional explicit output path; defaults to Exports dir.

    Returns:
        The path to the written CSV file.
    """
    ref_data = config.load_reference(relative_path)
    entries = ref_data.get(top_level_key, {})

    if output_path is None:
        exports_dir = pathlib.Path(config.settings["config_path"]) / "Exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(exports_dir / output_filename)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for key, entry in entries.items():
            row = {"key": key}
            row.update(entry)
            row["aliases"] = ";".join(entry.get("aliases", []))
            writer.writerow(row)

    return output_path


def export_vendor_reference(config, output_path: str | None = None) -> str:
    """Export vendor_reference.json to CSV."""
    return export_reference(
        config=config,
        relative_path="References/vendor_reference.json",
        top_level_key="vendors",
        fieldnames=[
            "key", "name", "aliases", "address", "account_id",
            "phone", "tax_id", "date_added", "added_from_invoice",
        ],
        output_filename="vendor_reference.csv",
        output_path=output_path,
    )


def export_company_reference(config, output_path: str | None = None) -> str:
    """Export company_reference.json to CSV."""
    return export_reference(
        config=config,
        relative_path="References/company_reference.json",
        top_level_key="companies",
        fieldnames=["key", "name", "code", "aliases"],
        output_filename="company_reference.csv",
        output_path=output_path,
    )

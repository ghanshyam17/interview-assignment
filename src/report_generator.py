import csv
import json
import os
import logging
from datetime import datetime
from tabulate import tabulate

logger = logging.getLogger(__name__)


def generate_csv_report(results: list, output_dir: str) -> str:
    """Generates a detailed CSV report of all reconciliation results."""
    output_path = os.path.join(output_dir, "reconciliation_report.csv")
    
    headers = [
        "TradeID", "ISIN", "FieldName", "TermSheetValue", 
        "TermSheetEvidence", "BookingValue", "BookingFile",
        "Status", "Reason"
    ]
    
    rows = []
    for r in results:
        rows.append([
            r.get("trade_id"),
            r.get("isin"),
            r.get("field_name"),
            r.get("term_sheet_value"),
            r.get("term_sheet_evidence", "")[:200],  # Truncate long evidence
            r.get("booking_value"),
            r.get("booking_file"),
            r.get("status"),
            r.get("reason", "")
        ])
    
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    
    logger.info(f"CSV report generated: {output_path}")
    return output_path


def generate_summary_report(results: list, output_dir: str) -> str:
    """Generates a human-readable summary report."""
    output_path = os.path.join(output_dir, "summary_report.txt")
    
    # Count by status
    status_counts = {}
    for r in results:
        status = r.get("status", "Unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    
    # Count by ISIN
    isin_counts = {}
    for r in results:
        isin = r.get("isin", "Unknown")
        if isin not in isin_counts:
            isin_counts[isin] = {
                "Match": 0, 
                "False Alert": 0, 
                "True Mismatch": 0, 
                "Parsing Error": 0
            }
        status = r.get("status", "Unknown")
        if status in isin_counts[isin]:
            isin_counts[isin][status] += 1
    
    # True mismatches detail
    true_mismatches = [r for r in results if r.get("status") == "True Mismatch"]
    false_alerts = [r for r in results if r.get("status") == "False Alert"]
    
    with open(output_path, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("TERM SHEET RECONCILIATION REPORT\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
        
        f.write("OVERALL SUMMARY\n")
        f.write("-" * 40 + "\n")
        for status, count in sorted(status_counts.items()):
            f.write(f"  {status:20s}: {count}\n")
        f.write(f"  {'TOTAL':20s}: {len(results)}\n\n")
        
        f.write("BREAKDOWN BY ISIN\n")
        f.write("-" * 40 + "\n")
        for isin, counts in isin_counts.items():
            f.write(f"\n  ISIN: {isin}\n")
            for status, count in counts.items():
                f.write(f"    {status:20s}: {count}\n")
        
        f.write("\n\n")
        f.write("TRUE MISMATCHES (Require Investigation)\n")
        f.write("=" * 80 + "\n")
        if true_mismatches:
            for m in true_mismatches:
                f.write(f"\n  Trade ID: {m.get('trade_id')} | ISIN: {m.get('isin')}\n")
                f.write(f"  Field: {m.get('field_name')}\n")
                f.write(f"  Term Sheet: {m.get('term_sheet_value')}\n")
                f.write(f"  Evidence: {m.get('term_sheet_evidence', '')[:150]}\n")
                f.write(f"  Booking: {m.get('booking_value')}\n")
                f.write(f"  Reason: {m.get('reason', 'N/A')}\n")
                f.write(f"  ---\n")
        else:
            f.write("  None found.\n")
        
        f.write("\n\n")
        f.write("FALSE ALERTS (Formatting Differences Only)\n")
        f.write("=" * 80 + "\n")
        if false_alerts:
            for fa in false_alerts:
                f.write(f"\n  Trade ID: {fa.get('trade_id')} | ISIN: {fa.get('isin')}\n")
                f.write(f"  Field: {fa.get('field_name')}\n")
                f.write(f"  Term Sheet: {fa.get('term_sheet_value')}\n")
                f.write(f"  Booking: {fa.get('booking_value')}\n")
                f.write(f"  Reason: {fa.get('reason', 'N/A')}\n")
                f.write(f"  ---\n")
        else:
            f.write("  None found.\n")
    
    logger.info(f"Summary report generated: {output_path}")
    return output_path


def generate_console_summary(results: list):
    """Prints a nice table to console for immediate viewing."""
    # Count by status
    status_counts = {}
    for r in results:
        status = r.get("status", "Unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        
    print("\n" + "=" * 60)
    print(" RECONCILIATION ROLLUP SUMMARY")
    print("=" * 60)
    for status, count in sorted(status_counts.items()):
        print(f"  {status:20s}: {count}")
    print(f"  {'TOTAL':20s}: {len(results)}")
    print("=" * 60)
    
    # Show only mismatches, false alerts, and parsing errors
    interesting = [r for r in results if r.get("status") in ["True Mismatch", "False Alert", "Parsing Error"]]
    
    if not interesting:
        print("\n✅ All fields match! No discrepancies found.\n")
        return
    
    table_data = []
    for r in interesting:
        status_emoji = {
            "True Mismatch": "❌",
            "False Alert": "⚠️",
            "Parsing Error": "🔍"
        }.get(r.get("status"), "  ")
        
        table_data.append([
            r.get("trade_id"),
            r.get("isin"),
            r.get("field_name"),
            str(r.get("term_sheet_value", ""))[:30],
            str(r.get("booking_value", ""))[:30],
            f"{status_emoji} {r.get('status', '')}",
            str(r.get("reason", ""))[:50]
        ])
    
    headers = ["Trade", "ISIN", "Field", "TermSheet", "Booking", "Status", "Reason"]
    print("\n" + tabulate(table_data, headers=headers, tablefmt="grid"))

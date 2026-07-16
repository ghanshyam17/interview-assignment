"""
Comprehensive test suite for the Term Sheet Reconciliation Pipeline.
Tests PDF extraction, booking ingestion, normalization, and cross-field logic.

Usage:
    python -m pytest tests/test_pipeline.py -v
    OR
    python tests/test_pipeline.py
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pdf_extractor import extract_text_from_pdf
from src.booking_ingestor import ingest_booking_file
from src.reconciler import normalize_date, normalize_number, normalize_string


# ---------------------------------------------------------------------------
# PDF Extraction Tests
# ---------------------------------------------------------------------------

def test_pdf_extraction_genel():
    """Test PDF text extraction for Genel Energy term sheet."""
    pdf_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Assignment", "4.Term Sheet - Genel Energy.pdf"
    )
    assert os.path.exists(pdf_path), f"Sample PDF not found at {pdf_path}"
    text = extract_text_from_pdf(pdf_path)
    assert len(text) > 1000, "PDF text should be substantial"
    assert "Genel Energy" in text, "Should contain issuer name"
    assert "9.25" in text, "Should contain coupon rate"
    print("✅ PDF extraction test (Genel Energy) passed")


def test_pdf_extraction_idbi():
    """Test PDF text extraction for IDBI term sheet."""
    pdf_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Assignment", "3.Term Sheet - IDBI.pdf"
    )
    assert os.path.exists(pdf_path), f"Sample PDF not found at {pdf_path}"
    text = extract_text_from_pdf(pdf_path)
    assert len(text) > 1000, "PDF text should be substantial"
    assert "IDBI" in text, "Should contain issuer name"
    assert "10.75" in text, "Should contain coupon rate"
    print("✅ PDF extraction test (IDBI) passed")


# ---------------------------------------------------------------------------
# Booking Ingestion Tests
# ---------------------------------------------------------------------------

def test_booking_ingestion_csv():
    """Test CSV booking file ingestion."""
    csv_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Assignment", "Genel_Energy.csv"
    )
    assert os.path.exists(csv_path), f"Sample CSV not found at {csv_path}"
    csv_trades = ingest_booking_file(csv_path)
    assert len(csv_trades) == 5, f"Expected 5 trades, got {len(csv_trades)}"
    # Verify field presence
    assert "TradeID" in csv_trades[0], "Should have TradeID field"
    assert "Coupon" in csv_trades[0], "Should have Coupon field"
    assert "ISIN" in csv_trades[0], "Should have ISIN field"
    print("✅ Booking ingestion test (CSV) passed")


def test_booking_ingestion_json():
    """Test JSON booking file ingestion."""
    json_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Assignment", "Genel_Energy.json"
    )
    assert os.path.exists(json_path), f"Sample JSON not found at {json_path}"
    json_trades = ingest_booking_file(json_path)
    assert len(json_trades) == 5, f"Expected 5 trades, got {len(json_trades)}"
    assert "TradeID" in json_trades[0], "Should have TradeID field"
    print("✅ Booking ingestion test (JSON) passed")


def test_booking_ingestion_idbi():
    """Test IDBI booking file ingestion and field consistency."""
    csv_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Assignment", "IDBI_Omni.csv"
    )
    csv_trades = ingest_booking_file(csv_path)
    assert len(csv_trades) == 5, "Should have 5 IDBI trades"
    # Trade 2 should have coupon 11.00 (deliberate mismatch)
    trade2 = csv_trades[1]
    assert trade2["Coupon"] == "11.0", f"Trade 2 coupon should be 11.0, got {trade2['Coupon']}"
    print("✅ Booking ingestion test (IDBI) passed")


# ---------------------------------------------------------------------------
# Date Normalization Tests
# ---------------------------------------------------------------------------

def test_normalize_date_iso():
    """Test ISO format date normalization."""
    assert normalize_date("2025-10-14") == "2025-10-14"
    print("✅ Date normalization (ISO) passed")


def test_normalize_date_us():
    """Test US format date normalization."""
    assert normalize_date("10/14/2025") == "2025-10-14"
    print("✅ Date normalization (US) passed")


def test_normalize_date_narrative():
    """Test narrative format date normalization."""
    assert normalize_date("14 October 2025") == "2025-10-14"
    assert normalize_date("October 17, 2014") == "2014-10-17"
    print("✅ Date normalization (narrative) passed")


def test_normalize_date_none():
    """Test that unparseable dates return None."""
    assert normalize_date("Perpetual") is None
    assert normalize_date("NOT_FOUND") is None
    assert normalize_date("") is None
    print("✅ Date normalization (None cases) passed")


# ---------------------------------------------------------------------------
# Number Normalization Tests
# ---------------------------------------------------------------------------

def test_normalize_number_basic():
    """Test basic number normalization."""
    assert normalize_number("9.25%") == 9.25
    assert normalize_number("10.75") == 10.75
    assert normalize_number("97%") == 97.0
    assert normalize_number("100") == 100.0
    print("✅ Number normalization (basic) passed")


def test_normalize_number_currency():
    """Test number normalization with currency symbols."""
    assert normalize_number("USD 300,000,000") == 300000000.0
    assert normalize_number("Rs. 1000000") == 1000000.0
    print("✅ Number normalization (currency) passed")


def test_normalize_number_indian_crores():
    """Test Indian Crores notation conversion."""
    result = normalize_number("1500 Crores")
    assert result == 15000000000.0, f"Expected 15000000000.0, got {result}"
    result2 = normalize_number("Rs. 1,500 Crores")
    assert result2 == 15000000000.0, f"Expected 15000000000.0, got {result2}"
    print("✅ Number normalization (Indian Crores) passed")


def test_normalize_number_indian_lakhs():
    """Test Indian Lakhs notation conversion."""
    result = normalize_number("10 Lakhs")
    assert result == 1000000.0, f"Expected 1000000.0, got {result}"
    print("✅ Number normalization (Indian Lakhs) passed")


def test_normalize_number_indian_comma_format():
    """Test Indian comma formatting."""
    # Rs. 10,00,000 = 1,000,000 (after removing commas: 1000000)
    result = normalize_number("10,00,000")
    assert result == 1000000.0, f"Expected 1000000.0, got {result}"
    print("✅ Number normalization (Indian comma format) passed")


def test_normalize_number_none():
    """Test that non-numeric strings return None."""
    assert normalize_number("NOT_FOUND") is None
    assert normalize_number("") is None
    assert normalize_number("Perpetual") is None
    print("✅ Number normalization (None cases) passed")


# ---------------------------------------------------------------------------
# String Normalization Tests
# ---------------------------------------------------------------------------

def test_normalize_string_basic():
    """Test basic string normalization."""
    assert normalize_string("IDBI Bank Limited") == "idbi bank limited"
    assert normalize_string("  hello world  ") == "hello world"
    print("✅ String normalization (basic) passed")


def test_normalize_string_hyphens():
    """Test that hyphens are replaced with spaces."""
    result = normalize_string("Semi-annual")
    assert result is not None
    assert "semi" in result
    print("✅ String normalization (hyphens) passed")


def test_normalize_string_financial_synonyms():
    """Test financial term synonym mapping."""
    result = normalize_string("Semi-annual")
    assert result == "semiannual", f"Expected 'semiannual', got '{result}'"
    print("✅ String normalization (financial synonyms) passed")


def test_normalize_string_none():
    """Test that empty/null strings return None."""
    assert normalize_string("NOT_FOUND") is None
    assert normalize_string("") is None
    print("✅ String normalization (None cases) passed")


# ---------------------------------------------------------------------------
# Main Test Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_functions = [
        test_pdf_extraction_genel,
        test_pdf_extraction_idbi,
        test_booking_ingestion_csv,
        test_booking_ingestion_json,
        test_booking_ingestion_idbi,
        test_normalize_date_iso,
        test_normalize_date_us,
        test_normalize_date_narrative,
        test_normalize_date_none,
        test_normalize_number_basic,
        test_normalize_number_currency,
        test_normalize_number_indian_crores,
        test_normalize_number_indian_lakhs,
        test_normalize_number_indian_comma_format,
        test_normalize_number_none,
        test_normalize_string_basic,
        test_normalize_string_hyphens,
        test_normalize_string_financial_synonyms,
        test_normalize_string_none,
    ]

    print(f"Running {len(test_functions)} tests...\n")
    passed = 0
    failed = 0
    for test_fn in test_functions:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"❌ {test_fn.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ {test_fn.__name__} ERROR: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(test_functions)}")
    if failed == 0:
        print("🎉 All tests passed!")
    else:
        print(f"⚠️  {failed} test(s) failed")
    sys.exit(0 if failed == 0 else 1)

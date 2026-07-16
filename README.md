# LLM-Powered Term Sheet Reconciliation

Automated reconciliation workflow that compares unstructured trade term sheets (PDF) with structured booking system records (CSV/JSON) using Large Language Models. Built for a Capital Markets Applied AI Developer assignment — see `Assignment/1.Assignment Brief.pdf` and `Assignment/2.Evaluation Guidelines.pdf` for full requirements.

## Overview

This tool automates the reconciliation of bond term sheet data against booking system records using a **two-pass LLM pipeline**:

1. **Pass 1 (Structured Extraction):** Extracts structured fields from PDF term sheets. Every extracted value includes a verbatim "evidence" quote from the source document for auditable lineage. Output is validated against a strict Pydantic schema — fields that fail type-validation are flagged as `Parsing Error` rather than `Mismatch`.
2. **Pass 2 (False Alert Analysis):** For any field that mismatches after normalization, a second LLM pass analyzes the mismatch alongside the source quote and booking value to classify it as a **True Mismatch** (genuine discrepancy) or **False Alert** (formatting variance, e.g., `"10.75%"` vs `"0.1075"`, `"Oslo, New York"` vs `"Oslo|New York"`).

### LLM & API Integration

This solution uses the **Groq API** (free tier — [console.groq.com/keys](https://console.groq.com/keys)) with the `meta-llama/llama-4-scout-17b-16e-instruct` model. This model provides a **131,072-token context window**, large enough to process full term sheet PDFs (29k–42k chars) **without truncation** — ensuring all fields are visible to the LLM, including those that appear late in the document (e.g., *Business Day Convention* at char 25,846 in the IDBI term sheet).

All LLM interactions are fully programmatic via the `groq` Python SDK — no manual copy-pasting or web interface. The client enforces low temperature (`0.1`), native JSON mode, and exponential backoff retry (3 attempts) to handle transient API rate-limit errors gracefully.

## Prerequisites

- **Python 3.10+**
- A **free Groq API Key** — get one at [console.groq.com/keys](https://console.groq.com/keys)

## Setup

### 1. Clone the repository
```bash
git clone https://github.com/ghanshyam17/interview-assignment.git
cd interview-assignment
```

### 2. Create a virtual environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```
Dependencies: `pdfplumber` (PDF extraction), `pydantic` (schema validation), `pandas` (booking ingestion), `groq` (LLM API), `python-dotenv` (env config), `tabulate` (console output).

### 4. Configure API key
Copy `.env.example` to `.env` and fill in your Groq API key:
```bash
cp .env.example .env
```
Open `.env` in a text editor and set:
```bash
GROQ_API_KEY=your_groq_api_key_here
LLM_PROVIDER=groq
LLM_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
```

**Required environment variables:**

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Yes | Your free Groq API key from [console.groq.com/keys](https://console.groq.com/keys) |
| `LLM_PROVIDER` | No | Defaults to `groq` if `GROQ_API_KEY` is set |
| `LLM_MODEL` | No | Defaults to `meta-llama/llama-4-scout-17b-16e-instruct` (131k context) |
| `LLM_MODEL_EXTRACTION` | No | Override model for Pass 1 (defaults to `LLM_MODEL`) |
| `LLM_MODEL_ADJUDICATION` | No | Override model for Pass 2 (defaults to `LLM_MODEL`) |

> [!IMPORTANT]
> Never commit your `.env` file. It is already in `.gitignore`. The `.env.example` file is provided as a template.

### 5. Verify data files
The supplied mock data is included in the `Assignment/` directory:
```
Assignment/
  1.Assignment Brief.pdf           # Assignment requirements
  2.Evaluation Guidelines.pdf     # Scoring rubric
  3.Term Sheet - IDBI.pdf          # IDBI Bank perpetual Tier-1 bond term sheet
  4.Term Sheet - Genel Energy.pdf  # Genel Energy senior unsecured bond term sheet
  IDBI_Omni.csv                    # Booking system extract (CSV format)
  IDBI_Omni.json                   # Booking system extract (JSON format)
  Genel_Energy.csv                 # Booking system extract (CSV format)
  Genel_Energy.json                # Booking system extract (JSON format)
```

## Running the Pipeline

### Full reconciliation run
```bash
python3 main.py
```

This executes the complete end-to-end workflow:
1. Extract text from both PDF term sheets using `pdfplumber`.
2. Send full PDF text to the LLM for structured field extraction (with verbatim evidence quotes).
3. Validate extraction against the Pydantic schema — invalid fields flagged as `Parsing Error`.
4. Ingest booking data from CSV and JSON files using `pandas`.
5. Normalize and compare extracted fields against booking data (dates → `YYYY-MM-DD`, Indian notation → standard numerics, synonym mapping).
6. Send any mismatches to the LLM for Pass 2 false alert analysis.
7. Generate reconciliation reports under `output/`.

### Interactive walkthrough (Jupyter Notebook)
For a step-by-step walkthrough of the entire pipeline with inline explanations:
```bash
jupyter notebook Reconciliation_Walkthrough.ipynb
```

### Running the test suite
Smoke tests verify pipeline components (PDF extractor, booking ingestor, normalizers):
```bash
python3 tests/test_pipeline.py
```

## Input / Output

### Input files
| File | Format | Description |
|---|---|---|
| `Assignment/*.pdf` | PDF | Unstructured term sheets (2 bond instruments) |
| `Assignment/*.csv` | CSV | Booking system extracts (5 trades each) |
| `Assignment/*.json` | JSON | Booking system extracts (5 trades each, same data as CSV) |

### Output files
Results are written to the `output/` directory (auto-created, gitignored):

| File | Description |
|---|---|
| `output/reconciliation_report.csv` | Detailed field-by-field results for every trade (380 rows: 19 fields × 2 issuers × 2 formats × 5 trades) |
| `output/summary_report.txt` | Human-readable summary with counts, True Mismatches, and False Alerts |
| `output/run_<timestamp>.log` | Detailed execution log with timestamps |

### Output status categories

| Status | Description |
|---|---|
| **Match** | Values match after normalization |
| **False Alert** | Values differ in format but are semantically equivalent (e.g., date formats, delimiter differences) — includes a reason |
| **True Mismatch** | Values are genuinely different — includes a reason |
| **Parsing Error** | Field could not be extracted or failed schema validation |

### CSV output schema
| Column | Description |
|---|---|
| `TradeID` | Trade identifier from booking system |
| `ISIN` | Bond ISIN |
| `FieldName` | The reconciled field (e.g., ISIN, Coupon, Maturity) |
| `TermSheetValue` | Value extracted from term sheet by LLM |
| `TermSheetEvidence` | Verbatim quote from the PDF used as evidence |
| `BookingValue` | Value from booking system |
| `BookingFile` | Source booking file (CSV/JSON) |
| `Status` | Match / False Alert / True Mismatch / Parsing Error |
| `Reason` | Explanation of the status |

## Reconciled Fields

The pipeline extracts and reconciles these 19 fields:

`ISIN`, `Issuer`, `Maturity`, `Notional`, `Coupon`, `Currency`, `SettlementDate`, `DayCountFraction`, `InterestPaymentDate`, `IssueDate`, `IssueAmount`, `IssuePrice`, `NominalAmountPerBond`, `InterestPaymentFrequency`, `BusinessDayConvention`, `BusinessDayLocation`, `AmortizationType`, `MinimumSubscription`, `Parent`

## Architecture

```
PDF Term Sheet ──pdfplumber──▶ Raw Text ──LLM Pass 1──▶ Pydantic-validated Fields
                                                              │
Booking Files (CSV/JSON) ──pandas──▶ Normalized Trades ◀──────┤
                                                              │
                                              Initial Comparison (normalization)
                                                              │
                                              Mismatches ──LLM Pass 2──▶ Adjudication
                                                              │
                                              Final Output (CSV + Summary + Console)
```

### Two-pass LLM design
- **Pass 1 (Extraction):** A specialized financial-document prompt instructs the LLM to extract each field with its verbatim evidence quote, handle Indian number notation (Crores/Lakhs), "at par" pricing, and ISIN patterns. Output is validated against `TermSheetExtraction` (Pydantic).
- **Pass 2 (Adjudication):** The LLM acts as an expert auditor, evaluating the booked value, term sheet value, and evidence quote to classify mismatches. An **in-memory adjudication cache** keyed on `(field_name, term_sheet_value, booking_value)` guarantees deterministic output across identical trades, reduces API usage, and accelerates execution.

## Design Notes

> [!NOTE]
> 1. **No Truncation:** Full PDF text is sent to the LLM. The `meta-llama/llama-4-scout-17b-16e-instruct` model's 131k context window accommodates the largest term sheet (41,468 chars) with room to spare. Earlier iterations truncated at 15k chars, which silently dropped the *Business Day Convention* field (located at char 25,846) — this has been corrected.
> 2. **Parity Demonstration:** The pipeline processes both `.csv` and `.json` booking files for each issuer. This duplication is intentional to demonstrate that the ingestion parser handles both formats with identical accuracy.
> 3. **3-Category Conformance:** Any field present in the booking system but absent from the term sheet (like trade-level `Notional` or non-existent `ISIN`) is mapped to **True Mismatch** (with reason: *"Field is not present in the term sheet..."*) to conform strictly to the assignment's three requested categories.
> 4. **Deterministic LLM Adjudication Caching:** To prevent non-deterministic API responses for identical discrepancies across multiple trades (e.g., repeating the same maturity discrepancy across 5 trades), Pass 2 caches adjudication results using a `(field_name, term_sheet_value, booking_value)` key. This guarantees perfect output consistency, reduces API costs, and accelerates execution.
> 5. **Free-tier compliance:** The solution uses only Groq's free-tier API — no paid API keys required, satisfying the assignment constraint. All LLM interactions are fully automated via Python code.

## Documentation

- **`REPORT.md`** — Technical report (max 2 pages): workflow architecture, LLM/API integration design, field extraction design, challenges, assumptions, and DevOps/productionization recommendations.
- **`Reconciliation_Walkthrough.ipynb`** — Interactive Jupyter Notebook walkthrough of the full pipeline.

## Project Structure

```
.gitignore
.env.example                    # Environment variable template (commit-safe)
requirements.txt                # Python dependencies
README.md                       # This file
REPORT.md                       # Technical report (assignment documentation)
Reconciliation_Walkthrough.ipynb # Interactive walkthrough notebook
config.py                       # Configuration: API keys, model, file mappings, reconcile fields
main.py                         # Main pipeline orchestration entrypoint
src/
  models.py                     # Pydantic schema definitions (TermSheetExtraction, ExtractedField)
  pdf_extractor.py              # PDF text extraction using pdfplumber
  llm_client.py                 # Groq API wrapper with retry logic and JSON mode
  field_extractor.py            # Pass 1: Structured LLM extraction with Pydantic validation
  booking_ingestor.py           # CSV/JSON booking ingestion using pandas
  reconciler.py                 # Normalization, initial comparison, Pass 2 adjudication
  report_generator.py           # CSV, summary, and console output formatting
tests/
  test_pipeline.py              # Smoke tests for pipeline components
Assignment/                     # Sample data (term sheets + booking extracts)
output/                         # Generated reports (gitignored)
```

## Troubleshooting

| Issue | Solution |
|---|---|
| `GROQ_API_KEY not set` | Copy `.env.example` to `.env` and add your key from [console.groq.com/keys](https://console.groq.com/keys) |
| `413 Request too large` | Use `meta-llama/llama-4-scout-17b-16e-instruct` (131k context). Avoid `llama-3.1-8b-instant` (6k TPM limit) for large PDFs |
| `429 Rate limit exceeded` | Groq free tier has per-minute/per-day token limits. Wait and re-run, or space out calls |
| `Parsing Error` in output | The LLM couldn't extract or validate that field. Check the evidence quote — the field may be genuinely absent from the term sheet |
| PDF yields no text | Ensure the PDF is text-based (not scanned images). `pdfplumber` cannot OCR image-only PDFs |

## Tech Stack

| Component | Technology |
|---|---|
| LLM API | Groq (free tier) — `meta-llama/llama-4-scout-17b-16e-instruct` |
| PDF extraction | `pdfplumber` |
| Schema validation | `pydantic` |
| Booking ingestion | `pandas` |
| LLM SDK | `groq` Python SDK |
| Output formatting | `tabulate`, CSV |
| Config | `python-dotenv` |

## License

This project is an assignment submission for a Capital Markets Applied AI Developer role.
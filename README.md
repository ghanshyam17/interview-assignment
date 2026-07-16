# LLM-Powered Term Sheet Reconciliation

Automated reconciliation workflow that compares unstructured trade term sheets (PDF) with structured booking system records (CSV/JSON) using Large Language Models.

## Overview

This tool automates the reconciliation of bond term sheet data against booking system records using a two-pass LLM approach:
1. **Pass 1 (Extraction):** Extracts structured fields from PDF term sheets with evidence quotes, validated against a Pydantic schema.
2. **Pass 2 (False Alert Analysis):** Analyzes any mismatches to classify them as True Mismatches or False Alerts (formatting differences).

The tool uses the **Groq** API (free tier) with the `meta-llama/llama-4-scout-17b-16e-instruct` model, which provides a 131k-token context window — large enough to process full term sheet PDFs without truncation.

## Prerequisites

- Python 3.10+
- A free Groq API Key (get one from [Groq Console](https://console.groq.com/keys)).

## Setup

### 1. Create a virtual environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure API key
Copy `.env.example` to `.env` and fill in your API key:
```bash
cp .env.example .env
```
Open `.env` in a text editor:
- Set `GROQ_API_KEY=your_key_here` and `LLM_PROVIDER=groq` (default model is `meta-llama/llama-4-scout-17b-16e-instruct`). Other free Groq models (e.g., `llama-3.3-70b-versatile`) are also available — see the [Groq model catalog](https://console.groq.com/docs/models).

### 4. Verify data files
Ensure the following files are in place under `Assignment/`:
```
Assignment/
  3.Term Sheet - IDBI.pdf
  4.Term Sheet - Genel Energy.pdf
  IDBI_Omni.csv
  IDBI_Omni.json
  Genel_Energy.csv
  Genel_Energy.json
```

## Running the Pipeline

To execute the reconciliation run:
```bash
python3 main.py
```

This will:
1. Extract text from both PDF term sheets.
2. Send to LLM for structured field extraction (with verbatim evidence quotes).
3. Ingest booking data from CSV and JSON files.
4. Compare extracted fields against booking data.
5. Send any mismatches to the LLM for false alert analysis.
6. Generate reconciliation reports under `output/`.

## Running the Test Suite

To run basic smoke tests verifying the pipeline components (PDF extractor, booking ingestor, normalizers):
```bash
python3 tests/test_pipeline.py
```

## Output

Results are saved to the `output/` directory:
- `reconciliation_report.csv` — Detailed field-by-field results for every trade.
- `summary_report.txt` — Human-readable summary with counts and discrepancy details.
- `run_<timestamp>.log` — Detailed execution logs.

## Output Status Categories

| Status | Description |
|---|---|
| Match | Values match after normalization |
| False Alert | Values differ in format but are semantically equivalent (e.g., date formats, trailing zeros) |
| True Mismatch | Values are genuinely different |
| Parsing Error | Field could not be extracted or failed schema validation |

> [!NOTE]
> **Important Design Notes for Evaluation:**
> 1. **Parity Demonstration:** The pipeline processes both `.csv` and `.json` booking files for each issuer. This duplication is intentional to demonstrate that the ingestion parser handles both formats with identical accuracy.
> 2. **3-Category Conformance:** Any field present in the booking system but absent from the term sheet (like trade-level `Notional` or non-existent `ISIN`) is mapped to **True Mismatch** (with a descriptive reason: *"Field is not present in the term sheet..."*) to conform strictly to the assignment's three requested categories.
> 3. **Deterministic LLM Adjudication Caching:** To prevent non-deterministic API responses for identical discrepancies across multiple trades (e.g., repeating the same maturity discrepancy across 5 trades), Pass 2 caches adjudication results using a `(field_name, term_sheet_value, booking_value)` key. This guarantees perfect output consistency, reduces API costs, and accelerates execution.

## Project Structure

```
.gitignore
.env.example
requirements.txt
Reconciliation_Walkthrough.ipynb # Interactive walkthrough Jupyter Notebook
config.py             # Configuration parameters and file mappings
main.py               # Main pipeline orchestration entrypoint
src/
  models.py           # Pydantic schema definitions
  pdf_extractor.py    # PDF text extraction using pdfplumber
  llm_client.py       # API wrapper for Groq with retry logic
  field_extractor.py  # Pass 1: Structured LLM extraction with validation
  booking_ingestor.py # CSV/JSON ingestion using pandas
  reconciler.py       # Normalization and mismatch resolution
  report_generator.py # CSV, summary, and console output formatting
tests/
  test_pipeline.py    # Basic smoke test script
```

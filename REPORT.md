# Technical Report: LLM-Powered Term Sheet Reconciliation

## 1. Executive Summary & Workflow Architecture
This solution implements a robust, fully automated reconciliation engine that matches unstructured bond term sheet specifications (PDFs) with structured booking transaction records (CSV/JSON). It processes two distinct bond instruments — an **IDBI Bank Perpetual Tier-1 Bond** (INR) and a **Genel Energy Senior Unsecured Bond** (USD) — comparing extracted term sheet parameters against 5 trades each across CSV and JSON booking formats.

The system leverages a **two-pass LLM pipeline** to bridge unstructured text and structured databases:
* **Pass 1 (Structured Extraction & Validation):** Text is extracted from the PDF using `pdfplumber` and submitted to the LLM programmatically. The extraction is forced into a strict JSON schema and validated against a Pydantic model (`TermSheetExtraction`). Every field extracted must include its corresponding verbatim text quote (the "evidence") for auditable lineage. If type-conversion fails, it is classified as a `Parsing Error` rather than a mismatch.
* **Normalization Layer:** Extracted values and booking entries are fed into custom normalizers for dates (unifying to `YYYY-MM-DD`), numeric values (handling Indian notation like Crores/Lakhs, currency symbols, commas, and percentage markers), and strings (lowercasing, synonym mapping for financial terms like "Semi-annual"/"Semiannual").
* **Pass 2 (False Alert & Discrepancy Resolution):** When values differ after normalization, the system performs a second programmatic LLM pass. The LLM acts as an expert adjudicator, evaluating the booked value, the term sheet value, and the extracted evidence quote to classify the difference as either a **True Mismatch** (requiring operational intervention) or a **False Alert** (formatting variance with recorded reasoning).

---

## 2. LLM & API Integration Design
The LLM client uses **Groq** (via the `groq` SDK) with the `meta-llama/llama-4-scout-17b-16e-instruct` model — a free-tier model with a 131k-token context window that handles full term sheet PDFs without truncation.
* **Deterministic Configuration:** The client enforces a low temperature (`0.1`) and uses native JSON mode (`response_mime_type="application/json"` or `json_object` format) to secure structured outputs.
* **Resiliency & Retry Policy:** The engine wraps completions in an exponential backoff retry loop (3 attempts, starting at 2 seconds delay) to handle transient API rate-limit errors (HTTP 429) or connection timeouts.
* **Prompt Engineering Decisions:** The extraction prompt is highly specialized for financial documents, with specific instructions for Indian number formatting (Rs. 10,00,000 = 1,000,000; 1,500 Crores = 15,000,000,000), "at par" issue price interpretation (= 100), ISIN pattern recognition, and MinimumSubscription conversion from bond units to currency amounts.
* **Secrets & Security:** API keys are never hardcoded and are loaded dynamically from a `.env` configuration file excluded from version control.

---

## 3. Parsing & Schema Validation Design
Pydantic is utilized to validate and structure the data extracted from the term sheets.
* **Validation Separation:** Fields are extracted as `ExtractedField` objects containing a raw string and a verbatim quote. Custom validators ensure the quote contains text from the document.
* **Graceful Degradation:** When parsing fails on a field (e.g., if "Perpetual" is supplied where a date was expected, or if text corruption occurs), the validation error is caught and the specific field is flagged as a `Parsing Error`. The pipeline is designed not to crash, allowing other valid fields to proceed to reconciliation.
* **Cross-Field Validation:** The reconciler includes programmatic logic for fields that require cross-referencing, such as MinimumSubscription (which may be stated as "5 Bonds" requiring multiplication by the face value per bond to derive the currency equivalent).

---

## 4. Challenges & Assumptions
* **Indian Number Formatting:** The IDBI term sheet uses Indian notation (Lakhs, Crores, Indian comma placement). We handle this both in the LLM prompt (instructing conversion to standard numerics) and in the normalization layer (programmatic Crore/Lakh multipliers).
* **Perpetual Bonds vs. Maturity Dates:** IDBI's bond is "Perpetual" (no maturity), but the booking system records a call-option date (2025-10-17) as the maturity. This is correctly flagged as a True Mismatch since the bond tenor and call date are distinct financial concepts.
* **Notional vs. Issue Amount:** Term sheets describe bond-level static data (total issue size), while booking records contain per-trade notionals. We correctly treat Notional as a per-trade field absent from term sheets.
* **Non-deterministic LLM Output:** Even at low temperatures, LLM responses can vary slightly across identical inputs. We mitigate this by:
  1. Enforcing `temperature=0.0` on Pass 2 adjudication calls.
  2. Implementing an **in-memory adjudication cache** keyed on `(field_name, term_sheet_value, booking_value)` to guarantee perfect consistency across identical trades while saving API usage and latency.
* **Data Parity & Format Duplication:** The pipeline processes both `.csv` and `.json` files for each issuer. This intentional redundancy demonstrates that the ingestion parser and reconciliation logic achieve parity across structured storage formats.
* **Strict 3-Category Mapping:** Field discrepancies arising from fields entirely absent from the term sheet (like `Notional` or `ISIN`) are mapped strictly to the requested `"True Mismatch"` output category with a verbose clarifying reason rather than utilizing non-standard tags, keeping output format strict.

---

## 5. Productionization & DevOps Recommendations

To transition this script into a production-grade, capital markets system, we recommend the following enhancements:

* **CI/CD Pipeline:** GitHub Actions workflow to run tests and linting on every PR, with automated deployment to staging and production environments.
* **Containerization & Deployment:** Package the application as a Docker container and deploy it serverless (e.g., AWS ECS Fargate or Google Cloud Run) triggered on-demand via event buses when new term sheets are uploaded.
* **High-Throughput Parallelism:** Use a distributed task queue (such as Celery backed by Redis or RabbitMQ) to process multiple term sheets and booking extracts asynchronously.
* **Secret Management:** Move from local `.env` files to cloud secret managers (e.g., AWS Secrets Manager or HashiCorp Vault) to encrypt, store, and rotate LLM API keys.
* **Data Security & Compliance (SOC 2):** Bond term sheets may contain proprietary transaction parameters. Ensure all PDFs are encrypted at rest using AES-256 and in transit using TLS 1.3. For sensitive data, deploy self-hosted open-weights models inside a private VPC.
* **Human-in-the-Loop Workflow:** True Mismatches and Parsing Errors should trigger alerts via messaging queues (Slack/email) and route trades to a review dashboard where operations teams can inspect evidence quotes side-by-side with trade records.
* **Observability & Logging:** Implement structured JSON logging and export trace metrics to observability platforms (Datadog/ELK Stack) to monitor API latency, model accuracy, and token consumption rates.

import os
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

# LLM Configuration
# Supported free-tier provider: Groq (https://console.groq.com/keys)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Automatically detect LLM provider based on set API key
if os.getenv("LLM_PROVIDER"):
    LLM_PROVIDER = os.getenv("LLM_PROVIDER").lower()
elif GROQ_API_KEY:
    LLM_PROVIDER = "groq"
else:
    raise ValueError(
        "No LLM provider configured. Set GROQ_API_KEY in your .env file. "
        "Get a free key from https://console.groq.com/keys. See .env.example for details."
    )

# Default model — Groq's free llama-4-scout handles 131k context (no truncation needed)
if LLM_PROVIDER == "groq":
    LLM_MODEL = os.getenv("LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
else:
    LLM_MODEL = os.getenv("LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

# Model routing for extraction (Pass 1) and adjudication (Pass 2)
LLM_MODEL_EXTRACTION = os.getenv("LLM_MODEL_EXTRACTION", LLM_MODEL)
LLM_MODEL_ADJUDICATION = os.getenv("LLM_MODEL_ADJUDICATION", LLM_MODEL)

# File paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSIGNMENT_DIR = os.path.join(BASE_DIR, "Assignment")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Mapping: which booking files correspond to which term sheet
TERM_SHEET_MAPPING = {
    "3.Term Sheet - IDBI.pdf": {
        "isin": "INE008A08U84",
        "booking_files": ["IDBI_Omni.csv", "IDBI_Omni.json"],
        "issuer_keyword": "IDBI"
    },
    "4.Term Sheet - Genel Energy.pdf": {
        "isin": "NO0010894330",
        "booking_files": ["Genel_Energy.csv", "Genel_Energy.json"],
        "issuer_keyword": "Genel"
    }
}

# Fields to reconcile
RECONCILE_FIELDS = [
    "ISIN",
    "Issuer",
    "Maturity",
    "Notional",
    "Coupon",
    "Currency",
    "SettlementDate",
    "DayCountFraction",
    "InterestPaymentDate",
    "IssueDate",
    "IssueAmount",
    "IssuePrice",
    "NominalAmountPerBond",
    "InterestPaymentFrequency",
    "BusinessDayConvention",
    "BusinessDayLocation",
    "AmortizationType",
    "MinimumSubscription",
    "Parent",
]
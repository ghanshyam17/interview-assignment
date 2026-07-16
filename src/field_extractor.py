import json
import logging
from pydantic import ValidationError
from src.models import TermSheetExtraction, ExtractedField, MismatchStatus
from src.llm_client import LLMClient
from src.pdf_extractor import extract_text_from_pdf

logger = logging.getLogger(__name__)


EXTRACTION_SYSTEM_PROMPT = """You are an expert financial document analyst specializing in bond term sheets.
Your task is to extract specific fields from a term sheet document and return them in a strict JSON format.

CRITICAL REQUIREMENTS:
1. For EVERY field you extract, you MUST include an "evidence" key containing the EXACT verbatim 
   quote/snippet from the source text that was used to derive the value. Copy the text character-for-character.
2. If a field is not present in the document, set "value" to null and "evidence" to "NOT_FOUND".
3. Return ONLY valid JSON — no markdown, no explanation, no code blocks.

FIELD-SPECIFIC EXTRACTION RULES:

- ISIN: Look for an ISIN code (format: 2 letter country code + 9 alphanumeric characters + 1 check digit, 
  e.g., INE008A08U84 or NO0010894330). It may appear anywhere in the document, including headers, 
  tables, or metadata sections. Remove any spaces within the ISIN code.

- Issuer: The legal entity name issuing the bond.

- Maturity: The maturity date. If the bond is perpetual (no maturity), set value to "Perpetual".

- Coupon: The coupon/interest rate as a percentage, e.g., "10.75%" or "9.25%".

- Currency: The 3-letter currency code (INR, USD, EUR, GBP, etc.).

- IssueDate: The date the bonds are actually issued/allotted to investors — NOT the date the 
  issue opens for subscription. Prefer "Deemed Date of Allotment", "Date of Allotment", 
  "Issue Date", or "Date of Issue" over "Issue Opening Date" or "Issue Open Date". 
  The Issue Opening Date is when subscriptions open, not when bonds are issued.
  Return the actual calendar date of allotment/issuance.

- IssueAmount: The TOTAL issue size/amount. Convert to full numeric value:
  * Indian notation: Rs. 1,500 Crores = 15000000000 (1500 × 10000000)
  * Rs. 10,00,000 = 1000000 (Indian comma format)
  * USD 300,000,000 = 300000000
  Return the full numeric value as a string without commas or currency symbols.

- IssuePrice: The price at which the bond was issued. 
  * "At par" or "at par value" = "100"
  * A percentage like "97%" = "97"
  * If not explicitly stated but the bond was issued at face value, use "100".

- NominalAmountPerBond: The face value per single bond/unit.
  * Indian notation: Rs. 10,00,000 = 1000000 (ten lakhs, NOT one hundred thousand)
  * USD 2,000 = 2000
  Return the full numeric value.

- DayCountFraction: The day count convention, e.g., "Actual/Actual", "30/360", "Actual/365".

- InterestPaymentDate: The first coupon/interest payment date or the description of when 
  interest is paid. Return the actual date if available.

- InterestPaymentFrequency: How often interest is paid: "Annual", "Semi-annual", "Quarterly", etc.

- SettlementDate: The settlement date for the initial trade. May be the same as IssueDate. 
  If not found, set to null.

- BusinessDayConvention: The business day adjustment rule. Look for terms like "Following", 
  "Modified Following", "Preceding", "Unadjusted", or descriptions like 
  "next business day" (= Following), "preceding business day" (= Preceding).

- BusinessDayLocation: The cities/locations that define business days for this bond. 
  Look in sections about business days, payment locations, or holiday calendars.
  Do NOT use governing law, jurisdiction, or court locations (e.g., "courts of Mumbai") as BusinessDayLocation. 
  If business day locations are not explicitly specified as payment or holiday cities, set value to null and evidence to "NOT_FOUND".
  Return as comma-separated cities, e.g., "Mumbai, New Delhi" or "Oslo, New York".

- AmortizationType: How the principal is repaid: "Bullet" (lump sum at maturity), 
  "Perpetual" (no scheduled repayment), "Amortizing" (gradual repayment).

- MinimumSubscription: The minimum amount/units required to subscribe.
  * If stated as a number of bonds (e.g., "5 Bonds"), return the NUMERIC AMOUNT by multiplying 
    by the face value per bond. Example: 5 Bonds × Rs. 10,00,000 = "5000000".
  * If stated as a currency amount (e.g., "USD 200,000"), return the numeric value: "200000".

- Parent: The parent company of the issuer. If the issuer IS the parent (e.g., a bank issuing 
  its own bonds), return the issuer name as the parent.

The JSON schema you MUST follow:
{
    "ISIN": {"value": "<ISIN code>", "evidence": "<exact quote>"},
    "Issuer": {"value": "<issuer name>", "evidence": "<exact quote>"},
    "Maturity": {"value": "<maturity date or 'Perpetual'>", "evidence": "<exact quote>"},
    "Notional": {"value": null, "evidence": "NOT_FOUND"},
    "Coupon": {"value": "<coupon rate with %>", "evidence": "<exact quote>"},
    "Currency": {"value": "<currency code>", "evidence": "<exact quote>"},
    "SettlementDate": {"value": "<settlement date or null>", "evidence": "<exact quote or 'NOT_FOUND'>"},
    "DayCountFraction": {"value": "<day count convention>", "evidence": "<exact quote>"},
    "InterestPaymentDate": {"value": "<first interest payment date>", "evidence": "<exact quote>"},
    "IssueDate": {"value": "<issue date>", "evidence": "<exact quote>"},
    "IssueAmount": {"value": "<issue amount as full numeric string>", "evidence": "<exact quote>"},
    "IssuePrice": {"value": "<issue price as number or 'at par'=100>", "evidence": "<exact quote>"},
    "NominalAmountPerBond": {"value": "<face value per bond as full numeric string>", "evidence": "<exact quote>"},
    "InterestPaymentFrequency": {"value": "<frequency>", "evidence": "<exact quote>"},
    "BusinessDayConvention": {"value": "<convention name>", "evidence": "<exact quote>"},
    "BusinessDayLocation": {"value": "<comma-separated cities>", "evidence": "<exact quote>"},
    "AmortizationType": {"value": "<type>", "evidence": "<exact quote>"},
    "MinimumSubscription": {"value": "<numeric amount>", "evidence": "<exact quote>"},
    "Parent": {"value": "<parent company name>", "evidence": "<exact quote>"}
}

IMPORTANT NOTES ON INDIAN NUMBER FORMATTING:
- Indian numbering uses Lakhs (1,00,000 = 100,000) and Crores (1,00,00,000 = 10,000,000).
- Rs. 10,00,000 = 1,000,000 (Ten Lakhs = One Million).
- Rs. 1,500 Crores = 15,000,000,000 (Fifteen Billion).
- Always convert to the full standard numeric value.

IMPORTANT: Notional is a per-trade field that does NOT appear in a term sheet. 
Always set Notional value to null and evidence to "NOT_FOUND"."""


def extract_fields_from_termsheet(pdf_text: str, llm_client: LLMClient) -> dict:
    """
    Pass 1: Send term sheet text to LLM and extract structured fields.
    
    Args:
        pdf_text: Raw text extracted from the PDF
        llm_client: Initialized LLM client
        
    Returns:
        Dictionary with extraction results and any parsing errors
    """
    # Send full PDF text to LLM (no truncation - all fields must be visible)
    user_prompt = f"""Please extract all required fields from the following term sheet document text.
Return ONLY the JSON object matching the schema. Do not include any other text.

--- TERM SHEET TEXT START ---
{pdf_text}
--- TERM SHEET TEXT END ---

Extract all fields now:"""
    try:
        from config import LLM_MODEL_EXTRACTION
        # Call LLM
        raw_response = llm_client.call_llm(
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            json_mode=True,
            temperature=0.1,
            model=LLM_MODEL_EXTRACTION
        )
        
        # Parse JSON
        response_json = json.loads(raw_response)
        logger.info(f"LLM returned JSON with {len(response_json)} fields")
        
        # Validate against Pydantic schema
        try:
            validated = TermSheetExtraction(**response_json)
            logger.info("Pydantic schema validation PASSED")
            return {
                "status": "success",
                "data": validated.model_dump(),
                "errors": []
            }
        except ValidationError as ve:
            logger.warning(f"Pydantic validation failed: {ve}")
            # Return what we can + flag errors
            errors = []
            for error in ve.errors():
                field = ".".join(str(loc) for loc in error["loc"])
                errors.append({
                    "field": field,
                    "error": error["msg"],
                    "type": error["type"]
                })
            
            # Try to salvage valid fields
            valid_fields = {}
            for field_name in TermSheetExtraction.model_fields:
                if field_name in response_json:
                    try:
                        field_data = response_json[field_name]
                        if isinstance(field_data, dict) and "value" in field_data:
                            valid_fields[field_name] = field_data
                    except Exception:
                        pass
            
            return {
                "status": "partial",
                "data": valid_fields,
                "errors": errors
            }
            
    except json.JSONDecodeError as je:
        logger.error(f"LLM returned invalid JSON: {je}")
        return {
            "status": "failed",
            "data": {},
            "errors": [{"field": "json_parse", "error": str(je), "type": "json_error"}]
        }
    except Exception as e:
        logger.error(f"Extraction failed: {str(e)}")
        return {
            "status": "failed",
            "data": {},
            "errors": [{"field": "general", "error": str(e), "type": "general_error"}]
        }

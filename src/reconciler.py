import re
import json
import logging
from datetime import datetime
from typing import Optional, Tuple, List, Dict
from src.llm_client import LLMClient

logger = logging.getLogger(__name__)


def normalize_date(value: str) -> Optional[str]:
    """
    Attempts to parse a date string in various formats and returns ISO format (YYYY-MM-DD).
    Returns None if parsing fails.
    """
    if not value or value == "NOT_FOUND":
        return None
    
    value = value.strip()
    
    # Common date formats found in term sheets and booking data
    date_formats = [
        "%Y-%m-%d",      # 2025-10-14 (JSON)
        "%m/%d/%Y",      # 10/14/2025 (CSV)
        "%d %B %Y",      # 14 October 2025 (Term sheet)
        "%B %d, %Y",     # October 17, 2014 (Term sheet)
        "%d %b %Y",      # 14 Oct 2025
        "%d-%m-%Y",      # 14-10-2025
        "%Y/%m/%d",      # 2025/10/14
    ]
    
    for fmt in date_formats:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
            
    # Try parsing manually for simple word endings like "14 October 2025" or "Expected to be 14 October 2020"
    cleaned_date = re.sub(r'^(Expected to be|expected to be)\s+', '', value).strip()
    for fmt in date_formats:
        try:
            dt = datetime.strptime(cleaned_date, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    
    logger.warning(f"Could not parse date: '{value}'")
    return None


def normalize_number(value: str) -> Optional[float]:
    """
    Extracts numeric value from strings like:
    - "10.75%" -> 10.75
    - "USD 300,000,000" -> 300000000.0
    - "Rs. 10,00,000" -> 1000000.0
    - "1,500 Crores" -> 15000000000.0
    - "97%" -> 97.0
    - "9.25" -> 9.25
    """
    if not value or value == "NOT_FOUND":
        return None
    
    value_lower = value.lower()
    
    # Clean commas, spaces, and percentage symbols
    cleaned = value.replace(',', '').replace(' ', '').replace('%', '')
    # Remove common word currency indicators and labels
    cleaned = re.sub(r'(?i)\b(Rs\.?|USD|EUR|GBP|INR|p\.a\.?)\b', '', cleaned)
    # Remove currency symbols
    cleaned = re.sub(r'[\$\€\£\₹]', '', cleaned)
    # Remove crores/lakhs words (but remember them for multiplication)
    cleaned = re.sub(r'(?i)\b(crores?|lakhs?)\b', '', cleaned)
    
    # Try to find a number in the remaining string
    match = re.search(r'-?\d+\.?\d*', cleaned)
    if match:
        try:
            result = float(match.group())
            # Apply Indian number system multipliers
            if 'crore' in value_lower:
                result *= 10000000  # 1 Crore = 10,000,000
            elif 'lakh' in value_lower:
                result *= 100000    # 1 Lakh = 100,000
            return result
        except ValueError:
            return None
    
    return None


# Financial term synonyms for normalization
FINANCIAL_SYNONYMS = {
    'semi annual': 'semiannual',
    'semi-annual': 'semiannual',
    'semi annually': 'semiannual',
    'bi annual': 'semiannual',
    'bi-annual': 'semiannual',
    'bullet repayment': 'bullet',
    'bullet maturity': 'bullet',
    'at par': '100',
    'at maturity': 'bullet',
    'business day adjustment': 'following',
}


def normalize_string(value: str) -> Optional[str]:
    """
    Normalizes strings for comparison:
    - Lowercase
    - Strip whitespace
    - Replace hyphens with spaces
    - Remove special characters
    - Apply financial term synonym mapping
    """
    if not value or value == "NOT_FOUND":
        return None
    
    # Replace hyphens with spaces
    normalized = value.lower().replace('-', ' ').strip()
    # Remove other punctuation
    normalized = re.sub(r'[\.,;:\'\"()]+', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Apply financial synonyms
    if normalized in FINANCIAL_SYNONYMS:
        normalized = FINANCIAL_SYNONYMS[normalized]
    
    return normalized


def normalize_field(field_name: str, value: str) -> Tuple[Optional[str], str]:
    """
    Normalizes a field value based on its type.
    Returns (normalized_value, original_value).
    """
    if not value:
        return None, str(value)
    
    original = str(value).strip()
    
    # Date fields
    if field_name in ["Maturity", "SettlementDate", "InterestPaymentDate", "IssueDate"]:
        norm = normalize_date(original)
        return norm, original
    
    # Numeric fields
    elif field_name in ["Coupon", "IssueAmount", "IssuePrice", "NominalAmountPerBond", 
                         "MinimumSubscription", "Notional"]:
        norm = normalize_number(original)
        if norm is not None:
            return str(norm), original
        return None, original
    
    # String fields
    else:
        norm = normalize_string(original)
        return norm, original


def compare_fields(
    term_sheet_data: dict,
    booking_trades: list,
    booking_file: str,
    fields_to_compare: list
) -> list:
    """
    Performs initial field-by-field comparison between term sheet and booking data.
    
    Returns list of comparison results, each with status:
    - Match: normalized values are equal
    - Mismatch: normalized values differ (will be sent to LLM for false alert check)
    - Parsing Error: term sheet field failed schema validation
    - Not in Term Sheet: field is absent in term sheet but present in booking system
    """
    results = []
    
    for trade in booking_trades:
        trade_id = trade.get("TradeID")
        isin = trade.get("ISIN", "UNKNOWN")
        
        for field_name in fields_to_compare:
            # Get term sheet value
            ts_field = term_sheet_data.get(field_name, {})
            ts_value = ts_field.get("value") if isinstance(ts_field, dict) else None
            ts_evidence = ts_field.get("evidence", "") if isinstance(ts_field, dict) else ""
            
            # Check for missing fields in term sheet
            if ts_value is None and ts_evidence == "NOT_FOUND":
                booking_val = trade.get(field_name)
                # If SettlementDate is missing in term sheet, check if it matches the IssueDate of the term sheet
                if field_name == "SettlementDate":
                    issue_date_field = term_sheet_data.get("IssueDate", {})
                    issue_date_val = issue_date_field.get("value") if isinstance(issue_date_field, dict) else None
                    if issue_date_val is not None:
                        issue_norm, issue_evidence = normalize_field("IssueDate", str(issue_date_val))
                        bk_norm, bk_orig = normalize_field(field_name, str(booking_val)) if booking_val is not None else (None, None)
                        if bk_norm is not None and bk_norm == issue_norm:
                            results.append({
                                "trade_id": int(trade_id) if trade_id else None,
                                "isin": isin,
                                "field_name": field_name,
                                "term_sheet_value": str(issue_date_val),
                                "term_sheet_evidence": f"Mapped from Issue Date evidence: {issue_date_field.get('evidence', '')}",
                                "booking_value": bk_orig,
                                "booking_file": booking_file,
                                "status": "Match",
                                "reason": f"Booked settlement date matches the term sheet Issue Date ({issue_date_val})"
                            })
                            continue
                
                # Default missing handling
                if booking_val is None or booking_val == "" or str(booking_val).lower() in ["none", "null", "nan"]:
                    status = "Match"
                    reason = "Both term sheet and booking system lack this field"
                else:
                    status = "True Mismatch"
                    reason = f"Field is not present in the term sheet but contains value '{booking_val}' in the booking system"
                
                results.append({
                    "trade_id": int(trade_id) if trade_id else None,
                    "isin": isin,
                    "field_name": field_name,
                    "term_sheet_value": None,
                    "term_sheet_evidence": "NOT_FOUND",
                    "booking_value": booking_val,
                    "booking_file": booking_file,
                    "status": status,
                    "reason": reason
                })
                continue
            
            # Get booking value
            booking_value = trade.get(field_name)
            
            # Normalize both values
            ts_norm, ts_orig = normalize_field(field_name, str(ts_value)) if ts_value is not None else (None, None)
            bk_norm, bk_orig = normalize_field(field_name, str(booking_value)) if booking_value is not None else (None, None)
            
            # Programmatic Cross-Field Normalization for MinimumSubscription
            if field_name == "MinimumSubscription" and ts_value is not None:
                ts_value_str = str(ts_value).strip().lower()
                bond_match = re.search(r'(\d+)\s*(?:bonds?|debt\s+securities)', ts_value_str)
                if bond_match:
                    bond_count = int(bond_match.group(1))
                    nominal_field = term_sheet_data.get("NominalAmountPerBond", {})
                    nominal_val = nominal_field.get("value") if isinstance(nominal_field, dict) else None
                    if nominal_val is not None:
                        _, nominal_orig = normalize_field("NominalAmountPerBond", str(nominal_val))
                        nominal_num = normalize_number(nominal_orig)
                        if nominal_num:
                            calculated_min_sub = bond_count * nominal_num
                            ts_norm = str(calculated_min_sub)
                            logger.info(f"Programmatic conversion: {ts_value} converted to {calculated_min_sub} using NominalAmountPerBond {nominal_num}")
            
            # Programmatic Cross-Field Validation for Notional
            if field_name == "Notional" and ts_norm is not None and bk_norm is not None:
                issue_amt_field = term_sheet_data.get("IssueAmount", {})
                issue_amt_val = issue_amt_field.get("value") if isinstance(issue_amt_field, dict) else None
                if issue_amt_val is not None:
                    issue_norm, _ = normalize_field("IssueAmount", str(issue_amt_val))
                    if ts_norm == issue_norm:
                        try:
                            ts_num = float(ts_norm)
                            bk_num = float(bk_norm)
                            if bk_num <= ts_num:
                                results.append({
                                    "trade_id": int(trade_id) if trade_id else None,
                                    "isin": isin,
                                    "field_name": field_name,
                                    "term_sheet_value": ts_orig,
                                    "term_sheet_evidence": ts_evidence,
                                    "booking_value": bk_orig,
                                    "booking_file": booking_file,
                                    "status": "Match",
                                    "reason": f"Trade notional ({bk_orig}) is within the total issue size ({ts_orig})"
                                })
                                continue
                        except ValueError:
                            pass

            # Both missing
            if ts_norm is None and bk_norm is None:
                results.append({
                    "trade_id": int(trade_id) if trade_id else None,
                    "isin": isin,
                    "field_name": field_name,
                    "term_sheet_value": ts_orig,
                    "term_sheet_evidence": ts_evidence,
                    "booking_value": bk_orig,
                    "booking_file": booking_file,
                    "status": "Match",
                    "reason": "Both values are null/missing"
                })
                continue
            
            # One missing
            if ts_norm is None or bk_norm is None:
                results.append({
                    "trade_id": int(trade_id) if trade_id else None,
                    "isin": isin,
                    "field_name": field_name,
                    "term_sheet_value": ts_orig,
                    "term_sheet_evidence": ts_evidence,
                    "booking_value": bk_orig,
                    "booking_file": booking_file,
                    "status": "Mismatch",
                    "reason": "Value present in one source but not the other"
                })
                continue
            
            # Programmatic list/delimiter normalization for location-type fields
            if field_name in ["BusinessDayLocation"] and ts_norm is not None and bk_norm is not None:
                # Normalize different delimiters: pipe, comma, semicolon
                ts_parts = sorted(set(p.strip() for p in re.split(r'[|,;]+', ts_norm) if p.strip()))
                bk_parts = sorted(set(p.strip() for p in re.split(r'[|,;]+', bk_norm) if p.strip()))
                if ts_parts == bk_parts:
                    ts_norm = '|'.join(ts_parts)
                    bk_norm = '|'.join(bk_parts)
            
            # Compare normalized values
            if ts_norm == bk_norm:
                results.append({
                    "trade_id": int(trade_id) if trade_id else None,
                    "isin": isin,
                    "field_name": field_name,
                    "term_sheet_value": ts_orig,
                    "term_sheet_evidence": ts_evidence,
                    "booking_value": bk_orig,
                    "booking_file": booking_file,
                    "status": "Match",
                    "reason": "Values match after normalization"
                })
            else:
                # Mismatch detected - will need LLM false alert analysis
                results.append({
                    "trade_id": int(trade_id) if trade_id else None,
                    "isin": isin,
                    "field_name": field_name,
                    "term_sheet_value": ts_orig,
                    "term_sheet_evidence": ts_evidence,
                    "booking_value": bk_orig,
                    "booking_file": booking_file,
                    "status": "Mismatch",  # Tentative - will be resolved by LLM
                    "reason": "Normalized values differ",
                    "ts_normalized": ts_norm,
                    "bk_normalized": bk_norm
                })
    
    return results


FALSE_ALERT_SYSTEM_PROMPT = """You are a financial reconciliation expert.
Your task is to determine whether a discrepancy between a term sheet and a booking system 
is a TRUE MISMATCH or a FALSE ALERT.

A FALSE ALERT means the values are semantically equivalent but differ in:
- Date format (e.g., "14 October 2025" vs "2025-10-14" vs "10/14/2025")
- Number formatting (e.g., "9.25%" vs "9.25" vs "0.0925")
- Currency notation (e.g., "USD 300,000,000" vs "300000000")
- Case sensitivity or minor wording differences (e.g., "Semi-annual" vs "Semiannual")
- Trailing zeros (e.g., "9.50" vs "9.5")
- Different but equivalent representations of the same financial concept (e.g. "Perpetual" as maturity vs call option dates if context allows, but verify if they are strictly equivalent).

A TRUE MISMATCH means the values are genuinely different:
- Different coupon rates (10.75% vs 11.00%)
- Different dates that are not formatting variations (Oct 14 vs Oct 15)
- Different entities or amounts

Return JSON with this exact schema:
{
    "status": "False Alert" | "True Mismatch",
    "reason": "<concise explanation of why>",
    "confidence": "high" | "medium" | "low"
}"""


def analyze_false_alerts(
    mismatches: list,
    llm_client: LLMClient
) -> list:
    """
    Pass 2: For every mismatch, send to LLM to classify as False Alert or True Mismatch.
    
    Args:
        mismatches: List of mismatch results from initial comparison
        llm_client: Initialized LLM client
        
    Returns:
        Updated list with status resolved to False Alert or True Mismatch
    """
    resolved_results = []
    adjudication_cache = {}
    
    for mismatch in mismatches:
        if mismatch["status"] != "Mismatch":
            # Not a mismatch, keep as-is
            resolved_results.append(mismatch)
            continue
        
        # Build cache key to ensure identical inputs get identical outputs and reduce API usage
        cache_key = (
            mismatch["field_name"],
            mismatch["term_sheet_value"],
            mismatch["booking_value"]
        )
        
        if cache_key in adjudication_cache:
            logger.info(f"Reusing cached adjudication result for field '{mismatch['field_name']}'")
            cached_result = adjudication_cache[cache_key]
            mismatch["status"] = cached_result["status"]
            mismatch["reason"] = cached_result["reason"]
            if "llm_analysis" in cached_result:
                mismatch["llm_analysis"] = cached_result["llm_analysis"]
            
            # Clean up temporary keys before appending
            mismatch.pop("ts_normalized", None)
            mismatch.pop("bk_normalized", None)
            resolved_results.append(mismatch)
            continue
        
        # Build the LLM prompt for this specific mismatch
        user_prompt = f"""Analyze the following discrepancy:

FIELD: {mismatch["field_name"]}
TERM SHEET VALUE: "{mismatch["term_sheet_value"]}"
TERM SHEET EVIDENCE (exact quote from document): "{mismatch["term_sheet_evidence"]}"
BOOKING SYSTEM VALUE: "{mismatch["booking_value"]}"
BOOKING FILE: {mismatch["booking_file"]}

Is this a True Mismatch or a False Alert? Return only JSON."""

        try:
            from config import LLM_MODEL_ADJUDICATION
            raw_response = llm_client.call_llm(
                system_prompt=FALSE_ALERT_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                json_mode=True,
                temperature=0.0,
                model=LLM_MODEL_ADJUDICATION
            )
            
            llm_result = json.loads(raw_response)
            
            # Update the mismatch with LLM analysis
            mismatch["status"] = llm_result.get("status", "True Mismatch")
            mismatch["reason"] = llm_result.get("reason", "No reason provided")
            mismatch["llm_analysis"] = json.dumps(llm_result, indent=2)
            
            # Cache the result
            adjudication_cache[cache_key] = {
                "status": mismatch["status"],
                "reason": mismatch["reason"],
                "llm_analysis": mismatch["llm_analysis"]
            }
            
            logger.info(
                f"Trade {mismatch['trade_id']} | {mismatch['field_name']}: "
                f"{mismatch['status']} - {mismatch['reason']}"
            )
            
        except Exception as e:
            logger.error(f"False alert analysis failed for {mismatch['field_name']}: {e}")
            # Default to True Mismatch if LLM fails (conservative approach)
            mismatch["status"] = "True Mismatch"
            mismatch["reason"] = f"LLM analysis failed: {str(e)}. Defaulting to True Mismatch."
        
        # Clean up temporary keys before appending
        mismatch.pop("ts_normalized", None)
        mismatch.pop("bk_normalized", None)
        resolved_results.append(mismatch)
    
    return resolved_results

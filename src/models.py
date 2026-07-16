from pydantic import BaseModel, Field, field_validator
from typing import Optional, Union, List
from enum import Enum


class FieldType(str, Enum):
    """Possible field types for validation"""
    STRING = "string"
    FLOAT = "float"
    INTEGER = "integer"
    DATE = "date"
    LIST = "list"


class ExtractedField(BaseModel):
    """
    Represents a single field extracted from a term sheet by the LLM.
    Contains the value AND the evidence quote from the source document.
    """
    value: Optional[Union[str, float, int, List[str]]] = Field(
        default=None,
        description="The extracted value. Must match the expected type."
    )
    evidence: str = Field(
        default="NOT_FOUND",
        description="The EXACT verbatim quote/snippet from the source "
                    "document that was used to derive this value. "
                    "Must be a direct copy-paste from the text."
    )

    @field_validator("evidence")
    @classmethod
    def evidence_must_not_be_empty(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError("Evidence quote cannot be empty")
        return v.strip()


class TermSheetExtraction(BaseModel):
    """
    Complete schema for a term sheet extraction.
    Each field contains both the value and the evidence quote.
    """
    ISIN: ExtractedField
    Issuer: ExtractedField
    Maturity: ExtractedField
    Notional: Optional[ExtractedField] = None
    Coupon: ExtractedField
    Currency: ExtractedField
    SettlementDate: Optional[ExtractedField] = None
    DayCountFraction: ExtractedField
    InterestPaymentDate: Optional[ExtractedField] = None
    IssueDate: ExtractedField
    IssueAmount: ExtractedField
    IssuePrice: Optional[ExtractedField] = None
    NominalAmountPerBond: ExtractedField
    InterestPaymentFrequency: ExtractedField
    BusinessDayConvention: ExtractedField
    BusinessDayLocation: Optional[ExtractedField] = None
    AmortizationType: ExtractedField
    MinimumSubscription: ExtractedField
    Parent: Optional[ExtractedField] = None


class MismatchStatus(str, Enum):
    MATCH = "Match"
    FALSE_ALERT = "False Alert"
    TRUE_MISMATCH = "True Mismatch"
    PARSING_ERROR = "Parsing Error"
    NOT_IN_TS = "Not in Term Sheet"


class ReconciliationResult(BaseModel):
    """
    Result of reconciling a single field between term sheet and booking.
    """
    trade_id: Optional[int] = None
    isin: str
    field_name: str
    term_sheet_value: Optional[str] = None
    term_sheet_evidence: Optional[str] = None
    booking_value: Optional[str] = None
    booking_file: str
    status: MismatchStatus
    reason: Optional[str] = None
    llm_analysis: Optional[str] = None

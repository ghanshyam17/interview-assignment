#!/usr/bin/env python3
"""
LLM-Powered Term Sheet Reconciliation
=====================================
Main entry point that orchestrates the full reconciliation pipeline.

Usage:
    python main.py

Prerequisites:
    1. Install dependencies: pip install -r requirements.txt
    2. Set up .env file with OPENROUTER_API_KEY or GROQ_API_KEY (see .env.example)
    3. Ensure data files are in the Assignment/ directory

Output:
    - output/reconciliation_report.csv (detailed results)
    - output/summary_report.txt (human-readable summary)
"""

import os
import sys
import logging
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    ASSIGNMENT_DIR, OUTPUT_DIR, 
    TERM_SHEET_MAPPING, RECONCILE_FIELDS
)
from src.pdf_extractor import extract_text_from_pdf
from src.llm_client import LLMClient
from src.field_extractor import extract_fields_from_termsheet
from src.booking_ingestor import ingest_booking_file
from src.reconciler import compare_fields, analyze_false_alerts
from src.report_generator import generate_csv_report, generate_summary_report, generate_console_summary

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(OUTPUT_DIR, f'run_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def ensure_output_dir():
    """Create output directory if it doesn't exist."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def run_pipeline():
    """Main pipeline execution."""
    logger.info("=" * 80)
    logger.info("STARTING TERM SHEET RECONCILIATION PIPELINE")
    logger.info("=" * 80)
    
    ensure_output_dir()
    
    # Step 1: Initialize LLM client
    logger.info("Step 1: Initializing LLM client...")
    try:
        llm_client = LLMClient()
        logger.info("✅ LLM client initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize LLM client: {e}")
        logger.error("Please ensure that you have configured OPENROUTER_API_KEY or GROQ_API_KEY in your .env file.")
        sys.exit(1)
    
    all_results = []
    
    # Step 2: Process each term sheet
    for pdf_filename, mapping in TERM_SHEET_MAPPING.items():
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Processing: {pdf_filename}")
        logger.info(f"ISIN: {mapping['isin']}")
        logger.info(f"{'=' * 60}")
        
        # Step 2a: Extract PDF text
        pdf_path = os.path.join(ASSIGNMENT_DIR, pdf_filename)
        if not os.path.exists(pdf_path):
            logger.error(f"PDF not found: {pdf_path}")
            continue
        
        logger.info("Step 2a: Extracting text from PDF...")
        try:
            pdf_text = extract_text_from_pdf(pdf_path)
            logger.info(f"✅ Extracted {len(pdf_text)} characters")
        except Exception as e:
            logger.error(f"❌ PDF extraction failed: {e}")
            continue
        
        # Step 2b: LLM Pass 1 - Extract structured fields
        logger.info("Step 2b: LLM Pass 1 - Extracting fields via LLM...")
        extraction_result = extract_fields_from_termsheet(pdf_text, llm_client)
        
        if extraction_result["status"] == "failed":
            logger.error("❌ Field extraction failed completely")
            continue
        
        if extraction_result["errors"]:
            logger.warning(f"⚠️  {len(extraction_result['errors'])} parsing errors detected")
            for err in extraction_result["errors"]:
                logger.warning(f"   - {err['field']}: {err['error']}")
        
        term_sheet_data = extraction_result["data"]
        logger.info(f"✅ Extracted {len(term_sheet_data)} fields from term sheet")
        
        # Step 2c: Ingest booking data
        logger.info("Step 2c: Ingesting booking system data...")
        for booking_filename in mapping["booking_files"]:
            booking_path = os.path.join(ASSIGNMENT_DIR, booking_filename)
            if not os.path.exists(booking_path):
                logger.warning(f"Booking file not found: {booking_path}")
                continue
            
            try:
                booking_trades = ingest_booking_file(booking_path)
                logger.info(f"✅ Ingested {len(booking_trades)} trades from {booking_filename}")
            except Exception as e:
                logger.error(f"❌ Failed to ingest {booking_filename}: {e}")
                continue
            
            # Step 2d: Initial comparison
            logger.info(f"Step 2d: Comparing fields for {booking_filename}...")
            comparison_results = compare_fields(
                term_sheet_data=term_sheet_data,
                booking_trades=booking_trades,
                booking_file=booking_filename,
                fields_to_compare=RECONCILE_FIELDS
            )
            
            # Count initial mismatches
            initial_mismatches = [r for r in comparison_results if r["status"] == "Mismatch"]
            logger.info(f"   Found {len(initial_mismatches)} initial mismatches")
            
            # Step 2e: LLM Pass 2 - False alert analysis
            if initial_mismatches:
                logger.info(f"Step 2e: LLM Pass 2 - Analyzing {len(initial_mismatches)} mismatches...")
                resolved_results = analyze_false_alerts(comparison_results, llm_client)
            else:
                resolved_results = comparison_results
                logger.info("Step 2e: No mismatches to analyze")
            
            all_results.extend(resolved_results)
            
            # Log per-file summary
            matches = sum(1 for r in resolved_results if r["status"] == "Match")
            false_alerts = sum(1 for r in resolved_results if r["status"] == "False Alert")
            true_mismatches = sum(1 for r in resolved_results if r["status"] == "True Mismatch")
            parsing_errors = sum(1 for r in resolved_results if r["status"] == "Parsing Error")
            
            logger.info(f"\n📊 Results for {booking_filename}:")
            logger.info(f"   Matches:       {matches}")
            logger.info(f"   False Alerts:  {false_alerts}")
            logger.info(f"   True Mismatch: {true_mismatches}")
            logger.info(f"   Parse Errors:  {parsing_errors}")
    
    # Step 3: Generate reports
    logger.info("\n" + "=" * 80)
    logger.info("Step 3: Generating reports...")
    
    csv_path = generate_csv_report(all_results, OUTPUT_DIR)
    summary_path = generate_summary_report(all_results, OUTPUT_DIR)
    
    logger.info(f"✅ CSV report: {csv_path}")
    logger.info(f"✅ Summary report: {summary_path}")
    
    # Print console summary
    generate_console_summary(all_results)
    
    logger.info("\n" + "=" * 80)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 80)


if __name__ == "__main__":
    run_pipeline()

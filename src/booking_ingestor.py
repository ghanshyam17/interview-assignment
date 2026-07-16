import pandas as pd
import json
import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def ingest_booking_file(file_path: str) -> List[Dict[str, Any]]:
    """
    Ingests a booking system extract file (CSV or JSON).
    
    Args:
        file_path: Path to the CSV or JSON file
        
    Returns:
        List of trade dictionaries with normalized field names
        
    Raises:
        ValueError: If file format is unsupported
    """
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    
    trades = []
    
    if ext == ".csv":
        logger.info(f"Ingesting CSV: {file_path}")
        df = pd.read_csv(file_path)
        
        # Handle BusinessDayLocation pipe-separated format
        if "BusinessDayLocation" in df.columns:
            df["BusinessDayLocation"] = df["BusinessDayLocation"].apply(
                lambda x: x.split("|") if isinstance(x, str) and "|" in x 
                else [x] if pd.notna(x) else x
            )
        
        trades = df.to_dict(orient="records")
        
    elif ext == ".json":
        logger.info(f"Ingesting JSON: {file_path}")
        with open(file_path, "r") as f:
            data = json.load(f)
        
        # Handle nested "trades" key
        if "trades" in data:
            trades = data["trades"]
        elif isinstance(data, list):
            trades = data
        else:
            trades = [data]
    else:
        raise ValueError(f"Unsupported file format: {ext}. Only CSV and JSON supported.")
    
    # Convert all values to strings for comparison
    # (We'll normalize during comparison)
    for trade in trades:
        for key, value in list(trade.items()):
            if isinstance(value, list):
                trade[key] = "|".join(str(v) for v in value)
            elif pd.isna(value) or value is None:
                trade[key] = None
            else:
                trade[key] = str(value) if not isinstance(value, str) else value
    
    logger.info(f"Ingested {len(trades)} trades from {file_path}")
    return trades


def ingest_all_booking_files(file_paths: List[str]) -> Dict[str, List[Dict]]:
    """
    Ingests multiple booking files and returns them keyed by filename.
    """
    all_data = {}
    for path in file_paths:
        filename = os.path.basename(path)
        try:
            trades = ingest_booking_file(path)
            all_data[filename] = trades
        except Exception as e:
            logger.error(f"Failed to ingest {filename}: {e}")
            all_data[filename] = []
    return all_data

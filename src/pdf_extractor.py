import pdfplumber
import logging
import re

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_path: str) -> str:
    """
    Extracts all text from a PDF file using pdfplumber.
    Handles multi-page documents and cleans up whitespace.
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        Cleaned text content of the entire PDF
        
    Raises:
        FileNotFoundError: If the PDF doesn't exist
        Exception: If PDF parsing fails
    """
    try:
        text_pages = []
        with pdfplumber.open(file_path) as pdf:
            logger.info(f"Opened PDF: {file_path} ({len(pdf.pages)} pages)")
            
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text()
                if page_text:
                    text_pages.append(page_text)
                else:
                    logger.warning(f"Page {page_num} yielded no text")
            
        full_text = "\n\n--- PAGE BREAK ---\n\n".join(text_pages)
        
        # Clean up excessive whitespace but preserve structure
        # Replace multiple spaces with single space (but keep newlines)
        full_text = re.sub(r'[ \t]+', ' ', full_text)
        # Remove excessive blank lines
        full_text = re.sub(r'\n{3,}', '\n\n', full_text)
        
        logger.info(f"Extracted {len(full_text)} characters from PDF")
        return full_text.strip()
        
    except FileNotFoundError:
        logger.error(f"PDF file not found: {file_path}")
        raise
    except Exception as e:
        logger.error(f"Failed to parse PDF {file_path}: {str(e)}")
        raise


def truncate_text_for_llm(text: str, max_chars: int = 50000) -> str:
    """
    Truncates text if it exceeds the LLM context window.
    Most LLMs can handle 100k+ tokens, but we keep text concise.
    
    For term sheets, the first 5-6 pages usually contain all key fields.
    """
    if len(text) <= max_chars:
        return text
    
    logger.warning(f"Text exceeds {max_chars} chars, truncating")
    return text[:max_chars] + "\n\n[... TRUNCATED ...]"

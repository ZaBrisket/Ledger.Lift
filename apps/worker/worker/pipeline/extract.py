import logging
import time
from typing import List, Dict, Any, Optional
from pathlib import Path
import pandas as pd

from apps.worker.config import settings

try:
    import camelot
    import pdfplumber
    EXTRACTION_AVAILABLE = True
except ImportError as e:
    logging.warning(f"PDF extraction libraries not available: {e}")
    EXTRACTION_AVAILABLE = False

logger = logging.getLogger(__name__)

def extract_tables_stub(pdf_path: str) -> List[Dict]:
    """Legacy stub function for backward compatibility."""
    return extract_tables_production(pdf_path)

def extract_tables_production(pdf_path: str) -> List[Dict]:
    """
    Production PDF table extraction using camelot and pdfplumber.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        List of extracted tables with metadata
    """
    if not EXTRACTION_AVAILABLE:
        logger.error("PDF extraction libraries not available")
        return [{"page": 1, "rows": 0, "cols": 0, "engine": "unavailable", "error": "Libraries not installed"}]
    
    if not Path(pdf_path).exists():
        logger.error(f"PDF file not found: {pdf_path}")
        return []
    
    start_time = time.time()
    results = []
    
    try:
        # Extract tables using both engines for maximum coverage
        lattice_tables = _extract_with_camelot_lattice(pdf_path)
        stream_tables = _extract_with_camelot_stream(pdf_path)
        pdfplumber_tables = _extract_with_pdfplumber(pdf_path)
        
        # Combine and deduplicate results
        all_tables = lattice_tables + stream_tables + pdfplumber_tables
        results = _deduplicate_tables(all_tables)
        
        processing_time = time.time() - start_time
        logger.info(f"Extracted {len(results)} tables from {pdf_path} in {processing_time:.2f}s")
        
        return results
        
    except Exception as e:
        logger.error(f"Table extraction failed for {pdf_path}: {e}")
        return [{"page": 1, "rows": 0, "cols": 0, "engine": "error", "error": str(e)}]

def _extract_with_camelot_lattice(pdf_path: str) -> List[Dict]:
    """Extract tables using Camelot lattice method (for tables with clear borders)."""
    tables = []
    
    try:
        logger.debug(f"Extracting lattice tables from {pdf_path}")
        lattice_tables = camelot.read_pdf(pdf_path, pages='all', flavor='lattice')
        
        for table in lattice_tables:
            if table.accuracy > 0.8:  # Quality threshold
                df = table.df
                
                # Clean up the dataframe
                df = df.replace('', None).dropna(how='all').dropna(axis=1, how='all')
                
                if not df.empty:
                    tables.append({
                        'type': 'lattice',
                        'engine': 'camelot_lattice',
                        'data': df.to_dict('records'),
                        'accuracy': float(table.accuracy),
                        'page': int(table.page),
                        'rows': len(df),
                        'cols': len(df.columns),
                        'bbox': table._bbox if hasattr(table, '_bbox') else None,
                        'extraction_method': 'lattice'
                    })
                    
    except Exception as e:
        logger.warning(f"Camelot lattice extraction failed: {e}")
    
    return tables

def _extract_with_camelot_stream(pdf_path: str) -> List[Dict]:
    """Extract tables using Camelot stream method (for tables without clear borders)."""
    tables = []
    
    try:
        logger.debug(f"Extracting stream tables from {pdf_path}")
        stream_tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
        
        for table in stream_tables:
            if table.accuracy > 0.6:  # Lower threshold for stream
                df = table.df
                
                # Clean up the dataframe
                df = df.replace('', None).dropna(how='all').dropna(axis=1, how='all')
                
                if not df.empty:
                    tables.append({
                        'type': 'stream',
                        'engine': 'camelot_stream',
                        'data': df.to_dict('records'),
                        'accuracy': float(table.accuracy),
                        'page': int(table.page),
                        'rows': len(df),
                        'cols': len(df.columns),
                        'bbox': table._bbox if hasattr(table, '_bbox') else None,
                        'extraction_method': 'stream'
                    })
                    
    except Exception as e:
        logger.warning(f"Camelot stream extraction failed: {e}")
    
    return tables

def _extract_with_pdfplumber(pdf_path: str) -> List[Dict]:
    """Extract tables using pdfplumber (fallback method)."""
    tables = []
    
    try:
        logger.debug(f"Extracting tables with pdfplumber from {pdf_path}")
        
        with pdfplumber.open(pdf_path) as pdf:
            max_tables = max(settings.parser_max_schedules, 1)
            max_empty = max(settings.parser_max_empty_pages, 1)
            schedules_found = 0
            empty_streak = 0

            for page_num, page in enumerate(pdf.pages, 1):
                if schedules_found >= max_tables or empty_streak >= max_empty:
                    logger.debug(
                        "Early stop triggered at page %s (tables=%s, empty_streak=%s)",
                        page_num,
                        schedules_found,
                        empty_streak,
                    )
                    break

                page_tables = page.extract_tables()
                if not page_tables:
                    empty_streak += 1
                    continue

                page_had_tables = False
                for table_idx, table in enumerate(page_tables):
                    if table and len(table) > 0:
                        # Convert to DataFrame for consistency
                        df = pd.DataFrame(table[1:], columns=table[0] if table[0] else [])

                        # Clean up the dataframe
                        df = df.replace('', None).dropna(how='all').dropna(axis=1, how='all')

                        if not df.empty:
                            tables.append({
                                'type': 'pdfplumber',
                                'engine': 'pdfplumber',
                                'data': df.to_dict('records'),
                                'accuracy': 0.7,  # Default confidence for pdfplumber
                                'page': page_num,
                                'rows': len(df),
                                'cols': len(df.columns),
                                'table_index': table_idx,
                                'extraction_method': 'pdfplumber'
                            })
                            schedules_found += 1
                            page_had_tables = True
                            if schedules_found >= max_tables:
                                break

                if page_had_tables:
                    empty_streak = 0
                else:
                    empty_streak += 1
                            
    except Exception as e:
        logger.warning(f"Pdfplumber extraction failed: {e}")
    
    return tables

def _deduplicate_tables(tables: List[Dict]) -> List[Dict]:
    """Remove duplicate tables based on content similarity."""
    if not tables:
        return tables
    
    unique_tables = []
    
    for table in tables:
        is_duplicate = False
        
        for existing in unique_tables:
            if _tables_are_similar(table, existing):
                is_duplicate = True
                # Keep the one with higher accuracy
                if table.get('accuracy', 0) > existing.get('accuracy', 0):
                    unique_tables.remove(existing)
                    unique_tables.append(table)
                break
        
        if not is_duplicate:
            unique_tables.append(table)
    
    return unique_tables

def _tables_are_similar(table1: Dict, table2: Dict) -> bool:
    """Check if two tables are similar based on page, size, and content."""
    # Same page and similar dimensions
    if (table1.get('page') == table2.get('page') and 
        abs(table1.get('rows', 0) - table2.get('rows', 0)) <= 1 and
        abs(table1.get('cols', 0) - table2.get('cols', 0)) <= 1):
        
        # Check if data is similar (simple comparison)
        data1 = table1.get('data', [])
        data2 = table2.get('data', [])
        
        if len(data1) == len(data2) and len(data1) > 0:
            # Compare first few rows
            sample_size = min(3, len(data1))
            for i in range(sample_size):
                if data1[i] != data2[i]:
                    return False
            return True
    
    return False

def apply_ledger_transformations(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply business logic transformations specific to ledger data.
    
    Args:
        df: DataFrame containing extracted table data
        
    Returns:
        Transformed DataFrame
    """
    if df.empty:
        return df
    
    # Create a copy to avoid modifying original
    transformed_df = df.copy()
    
    try:
        # Common ledger transformations
        for col in transformed_df.columns:
            # Convert numeric columns
            if transformed_df[col].dtype == 'object':
                # Try to convert to numeric, keeping original if fails
                numeric_series = pd.to_numeric(transformed_df[col], errors='coerce')
                if not numeric_series.isna().all():
                    transformed_df[col] = numeric_series
        
        # Remove completely empty rows
        transformed_df = transformed_df.dropna(how='all')
        
        # Remove completely empty columns
        transformed_df = transformed_df.dropna(axis=1, how='all')
        
        # Standardize column names (remove extra whitespace, etc.)
        transformed_df.columns = [str(col).strip() for col in transformed_df.columns]
        
        logger.debug(f"Applied ledger transformations: {len(transformed_df)} rows, {len(transformed_df.columns)} columns")
        
    except Exception as e:
        logger.warning(f"Ledger transformations failed: {e}")
    
    return transformed_df

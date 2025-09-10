from typing import List, Dict, Optional, Tuple
import re
import logging

logger = logging.getLogger(__name__)

def normalize_currency_and_percentage(text: str) -> Tuple[str, float]:
    """
    Normalize currency and percentage values to canonical numeric form.
    Returns (normalized_text, numeric_value).
    """
    if not text or not isinstance(text, str):
        return text, 0.0
    
    text = text.strip()
    
    # Handle percentage
    if '%' in text:
        # Extract numeric part
        numeric_match = re.search(r'([\d,.-]+)', text)
        if numeric_match:
            try:
                numeric_str = numeric_match.group(1).replace(',', '')
                numeric_value = float(numeric_str) / 100.0  # Convert to decimal
                return f"{numeric_value:.4f}", numeric_value
            except ValueError:
                pass
    
    # Handle currency ($ symbol)
    if '$' in text:
        # Extract numeric part
        numeric_match = re.search(r'([\d,.-]+)', text)
        if numeric_match:
            try:
                numeric_str = numeric_match.group(1).replace(',', '')
                numeric_value = float(numeric_str)
                return f"${numeric_value:,.2f}", numeric_value
            except ValueError:
                pass
    
    # Try to parse as plain number
    try:
        # Remove commas and parse
        clean_text = text.replace(',', '')
        numeric_value = float(clean_text)
        return f"{numeric_value:,.2f}", numeric_value
    except ValueError:
        pass
    
    # Return original if no normalization possible
    return text, 0.0


def normalize_table_headers(table_data: Dict) -> Dict:
    """Normalize table headers and detect common patterns."""
    if 'rows' not in table_data or not table_data['rows']:
        return table_data
    
    normalized_table = table_data.copy()
    rows = normalized_table['rows']
    
    # Assume first row contains headers
    if rows:
        header_row = rows[0]
        normalized_headers = []
        
        for header in header_row:
            if isinstance(header, str):
                # Common header normalizations
                normalized = header.strip().lower()
                normalized = re.sub(r'\s+', ' ', normalized)  # Multiple spaces to single
                
                # Common financial headers
                header_mappings = {
                    'amount': 'amount',
                    'value': 'amount',
                    'total': 'total',
                    'subtotal': 'subtotal',
                    'description': 'description',
                    'item': 'description',
                    'date': 'date',
                    'period': 'date',
                    'percentage': 'percentage',
                    'percent': 'percentage',
                    '%': 'percentage'
                }
                
                for pattern, standard in header_mappings.items():
                    if pattern in normalized:
                        normalized = standard
                        break
                
                normalized_headers.append(normalized)
            else:
                normalized_headers.append(header)
        
        rows[0] = normalized_headers
    
    return normalized_table


def calculate_table_score(table_data: Dict) -> float:
    """
    Calculate a quality score for extracted table based on various metrics.
    Higher score is better.
    """
    score = 0.0
    
    if not table_data or 'rows' not in table_data:
        return score
    
    rows = table_data.get('rows', [])
    cols = table_data.get('cols', 0)
    
    if not rows or cols == 0:
        return score
    
    # Grid density score (0-30 points)
    total_cells = len(rows) * cols
    non_empty_cells = sum(1 for row in rows for cell in row if cell and str(cell).strip())
    if total_cells > 0:
        density = non_empty_cells / total_cells
        score += density * 30
    
    # Numeric ratio score (0-25 points)
    numeric_cells = 0
    for row in rows[1:]:  # Skip header row
        for cell in row:
            if cell and isinstance(cell, (int, float)):
                numeric_cells += 1
            elif isinstance(cell, str):
                # Check if string contains numeric patterns
                if re.search(r'[\d,.$%]+', cell):
                    numeric_cells += 1
    
    data_cells = max(1, (len(rows) - 1) * cols)  # Exclude header row
    if data_cells > 0:
        numeric_ratio = numeric_cells / data_cells
        score += numeric_ratio * 25
    
    # Header alignment score (0-20 points)
    if len(rows) > 1:
        header_row = rows[0]
        has_meaningful_headers = sum(1 for h in header_row if h and len(str(h).strip()) > 2)
        header_ratio = has_meaningful_headers / max(1, len(header_row))
        score += header_ratio * 20
    
    # Structure consistency score (0-15 points)
    if len(rows) > 1:
        expected_cols = len(rows[0])
        consistent_rows = sum(1 for row in rows if len(row) == expected_cols)
        consistency_ratio = consistent_rows / len(rows)
        score += consistency_ratio * 15
    
    # Size bonus (0-10 points) - prefer larger tables
    size_bonus = min(10, len(rows) * 2)
    score += size_bonus
    
    return score


def extract_with_pdfplumber(pdf_path: str) -> List[Dict]:
    """Extract tables using pdfplumber engine."""
    try:
        import pdfplumber
        
        tables = []
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_tables = page.extract_tables()
                
                for table_data in page_tables:
                    if table_data and len(table_data) > 0:
                        table = {
                            "page": page_num,
                            "rows": table_data,
                            "cols": len(table_data[0]) if table_data else 0,
                            "engine": "pdfplumber"
                        }
                        tables.append(table)
        
        return tables
    
    except ImportError:
        logger.warning("pdfplumber not available, skipping")
        return []
    except Exception as e:
        logger.error(f"pdfplumber extraction failed: {e}")
        return []


def extract_with_camelot(pdf_path: str) -> List[Dict]:
    """Extract tables using Camelot engine."""
    try:
        import camelot
        
        tables = []
        camelot_tables = camelot.read_pdf(pdf_path, pages='all', flavor='lattice')
        
        for table in camelot_tables:
            if table.df is not None and not table.df.empty:
                # Convert DataFrame to list of lists
                table_data = table.df.values.tolist()
                # Add header row
                header_row = table.df.columns.tolist()
                table_data.insert(0, header_row)
                
                table_dict = {
                    "page": table.page,
                    "rows": table_data,
                    "cols": len(table_data[0]) if table_data else 0,
                    "engine": "camelot"
                }
                tables.append(table_dict)
        
        return tables
    
    except ImportError:
        logger.warning("camelot not available, skipping")
        return []
    except Exception as e:
        logger.error(f"Camelot extraction failed: {e}")
        return []


def extract_with_tabula(pdf_path: str) -> List[Dict]:
    """Extract tables using Tabula engine (requires Java)."""
    try:
        import tabula
        import subprocess
        
        # Check if Java is available
        try:
            subprocess.run(['java', '-version'], 
                         capture_output=True, check=True, timeout=5)
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning("Java not available, skipping Tabula")
            return []
        
        tables = []
        tabula_tables = tabula.read_pdf(pdf_path, pages='all', multiple_tables=True)
        
        for i, df in enumerate(tabula_tables):
            if df is not None and not df.empty:
                # Convert DataFrame to list of lists
                table_data = df.values.tolist()
                # Add header row
                header_row = df.columns.tolist()
                table_data.insert(0, header_row)
                
                table_dict = {
                    "page": 1,  # Tabula doesn't always provide page info
                    "rows": table_data,
                    "cols": len(table_data[0]) if table_data else 0,
                    "engine": "tabula"
                }
                tables.append(table_dict)
        
        return tables
    
    except ImportError:
        logger.warning("tabula-py not available, skipping")
        return []
    except Exception as e:
        logger.error(f"Tabula extraction failed: {e}")
        return []


def run_consensus_extraction(pdf_path: str) -> List[Dict]:
    """
    Run multiple extraction engines and select best results using consensus scoring.
    """
    all_candidates = []
    
    # Run all available engines
    engines = [
        ("pdfplumber", extract_with_pdfplumber),
        ("camelot", extract_with_camelot),
        ("tabula", extract_with_tabula)
    ]
    
    for engine_name, extractor_func in engines:
        try:
            engine_results = extractor_func(pdf_path)
            for table in engine_results:
                table['engine'] = engine_name
                all_candidates.append(table)
        except Exception as e:
            logger.error(f"Engine {engine_name} failed: {e}")
    
    if not all_candidates:
        logger.warning("No tables extracted by any engine")
        return []
    
    # Score all candidates
    scored_candidates = []
    for table in all_candidates:
        score = calculate_table_score(table)
        table['quality_score'] = score
        scored_candidates.append(table)
    
    # Group by page and select best candidate per page
    page_groups = {}
    for table in scored_candidates:
        page = table.get('page', 1)
        if page not in page_groups:
            page_groups[page] = []
        page_groups[page].append(table)
    
    # Select best table per page
    final_tables = []
    for page, candidates in page_groups.items():
        if candidates:
            # Sort by score (descending) and take the best
            best_candidate = max(candidates, key=lambda t: t.get('quality_score', 0))
            
            # Normalize the selected table
            normalized_table = normalize_table_headers(best_candidate)
            
            # Add consensus metadata
            normalized_table['engine_selected'] = best_candidate['engine']
            normalized_table['candidates_summary'] = {
                'total_candidates': len(candidates),
                'engines_tried': list(set(c['engine'] for c in candidates)),
                'best_score': best_candidate.get('quality_score', 0)
            }
            
            # Apply units normalization to data cells
            if 'rows' in normalized_table and len(normalized_table['rows']) > 1:
                normalized_rows = [normalized_table['rows'][0]]  # Keep header
                
                for row in normalized_table['rows'][1:]:
                    normalized_row = []
                    for cell in row:
                        if isinstance(cell, str):
                            normalized_text, numeric_value = normalize_currency_and_percentage(cell)
                            normalized_row.append(normalized_text)
                        else:
                            normalized_row.append(cell)
                    normalized_rows.append(normalized_row)
                
                normalized_table['rows'] = normalized_rows
            
            final_tables.append(normalized_table)
    
    return final_tables
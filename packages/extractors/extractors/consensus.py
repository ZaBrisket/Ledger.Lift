from typing import List, Dict, Any, Optional
import re
import pandas as pd
import numpy as np

def normalize_headers(headers: List[str]) -> List[str]:
    """Normalize table headers by cleaning and standardizing format"""
    normalized = []
    for header in headers:
        # Clean whitespace and convert to lowercase
        clean = re.sub(r'\s+', ' ', str(header).strip()).lower()
        
        # Remove common prefixes/suffixes
        clean = re.sub(r'^(the|a|an)\s+', '', clean)
        clean = re.sub(r'\s+(inc|llc|ltd|corp|co)\.?$', '', clean)
        
        # Standardize common financial terms
        replacements = {
            'revenue': 'revenue',
            'sales': 'revenue',
            'income': 'revenue',
            'profit': 'profit',
            'earnings': 'profit',
            'net income': 'net_income',
            'ebitda': 'ebitda',
            'ebit': 'ebit',
            'assets': 'assets',
            'liabilities': 'liabilities',
            'equity': 'equity',
            'cash': 'cash',
            'debt': 'debt',
            'capex': 'capex',
            'capital expenditure': 'capex',
        }
        
        for old, new in replacements.items():
            if old in clean:
                clean = clean.replace(old, new)
        
        normalized.append(clean)
    
    return normalized

def normalize_units(value: str) -> tuple[float, str]:
    """Extract numeric value and unit from a string"""
    if not isinstance(value, str):
        return float(value) if value else 0.0, ""
    
    # Remove common formatting
    clean = re.sub(r'[,$\s]', '', str(value))
    
    # Extract number and unit
    # Handle percentages
    if '%' in clean:
        number = re.findall(r'[\d,]+\.?\d*', clean)
        if number:
            return float(number[0].replace(',', '')), '%'
    
    # Handle currency (assume $ if no other unit)
    if '$' in str(value) or 'usd' in clean.lower():
        number = re.findall(r'[\d,]+\.?\d*', clean)
        if number:
            return float(number[0].replace(',', '')), '$'
    
    # Handle millions/billions
    if 'm' in clean.lower() and 'million' not in clean.lower():
        number = re.findall(r'[\d,]+\.?\d*', clean)
        if number:
            return float(number[0].replace(',', '')) * 1_000_000, '$'
    
    if 'b' in clean.lower() and 'billion' not in clean.lower():
        number = re.findall(r'[\d,]+\.?\d*', clean)
        if number:
            return float(number[0].replace(',', '')) * 1_000_000_000, '$'
    
    # Try to extract just the number
    number = re.findall(r'[\d,]+\.?\d*', clean)
    if number:
        return float(number[0].replace(',', '')), ""
    
    return 0.0, ""

def score_table_density(table_data: List[List[str]]) -> float:
    """Score based on how dense the table is (more data = better)"""
    if not table_data or not table_data[0]:
        return 0.0
    
    total_cells = len(table_data) * len(table_data[0])
    non_empty_cells = sum(1 for row in table_data for cell in row if cell and str(cell).strip())
    
    return non_empty_cells / total_cells if total_cells > 0 else 0.0

def score_numeric_ratio(table_data: List[List[str]]) -> float:
    """Score based on ratio of numeric cells"""
    if not table_data or not table_data[0]:
        return 0.0
    
    total_cells = 0
    numeric_cells = 0
    
    for row in table_data:
        for cell in row:
            if cell and str(cell).strip():
                total_cells += 1
                try:
                    normalize_units(str(cell))[0]  # Check if we can extract a number
                    numeric_cells += 1
                except (ValueError, TypeError):
                    pass
    
    return numeric_cells / total_cells if total_cells > 0 else 0.0

def score_header_alignment(headers: List[str]) -> float:
    """Score based on header quality and alignment"""
    if not headers:
        return 0.0
    
    # Check for consistent formatting
    normalized = normalize_headers(headers)
    
    # Penalize empty or very short headers
    valid_headers = [h for h in normalized if len(h) > 2]
    if len(valid_headers) < len(headers) * 0.5:
        return 0.2
    
    # Bonus for financial terms
    financial_terms = {'revenue', 'profit', 'income', 'assets', 'liabilities', 'equity', 'cash', 'debt'}
    financial_count = sum(1 for h in normalized if any(term in h for term in financial_terms))
    
    return min(1.0, 0.5 + (financial_count / len(normalized)) * 0.5)

def score_table(table_data: List[List[str]], headers: List[str]) -> float:
    """Overall table scoring function"""
    density_score = score_table_density(table_data)
    numeric_score = score_numeric_ratio(table_data)
    header_score = score_header_alignment(headers)
    
    # Weighted combination
    return (density_score * 0.4 + numeric_score * 0.4 + header_score * 0.2)

def extract_with_pdfplumber(pdf_path: str) -> List[Dict]:
    """Extract tables using pdfplumber"""
    try:
        import pdfplumber
        
        tables = []
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_tables = page.extract_tables()
                for table in page_tables:
                    if table and len(table) > 1:  # At least header + 1 row
                        tables.append({
                            "page": page_num,
                            "engine": "pdfplumber",
                            "data": table,
                            "headers": table[0] if table else [],
                            "rows": len(table) - 1,
                            "cols": len(table[0]) if table else 0
                        })
        return tables
    except ImportError:
        return []
    except Exception as e:
        print(f"pdfplumber extraction failed: {e}")
        return []

def extract_with_camelot(pdf_path: str) -> List[Dict]:
    """Extract tables using camelot"""
    try:
        import camelot
        
        tables = []
        camelot_tables = camelot.read_pdf(pdf_path, pages='all', flavor='lattice')
        
        for i, table in enumerate(camelot_tables):
            if not table.df.empty:
                # Convert to list format
                data = table.df.values.tolist()
                headers = table.df.columns.tolist()
                
                tables.append({
                    "page": i + 1,  # Camelot doesn't provide page info easily
                    "engine": "camelot",
                    "data": data,
                    "headers": headers,
                    "rows": len(data),
                    "cols": len(headers)
                })
        return tables
    except ImportError:
        return []
    except Exception as e:
        print(f"camelot extraction failed: {e}")
        return []

def extract_with_tabula(pdf_path: str) -> List[Dict]:
    """Extract tables using tabula-py"""
    try:
        import tabula
        
        tables = []
        dfs = tabula.read_pdf(pdf_path, pages='all', multiple_tables=True)
        
        for i, df in enumerate(dfs):
            if not df.empty:
                data = df.values.tolist()
                headers = df.columns.tolist()
                
                tables.append({
                    "page": i + 1,  # Tabula doesn't provide page info easily
                    "engine": "tabula",
                    "data": data,
                    "headers": headers,
                    "rows": len(data),
                    "cols": len(headers)
                })
        return tables
    except ImportError:
        return []
    except Exception as e:
        print(f"tabula extraction failed: {e}")
        return []

def extract_consensus_tables(pdf_path: str) -> List[Dict]:
    """Extract tables using multiple engines and pick the best via consensus"""
    # Run all extractors
    pdfplumber_tables = extract_with_pdfplumber(pdf_path)
    camelot_tables = extract_with_camelot(pdf_path)
    tabula_tables = extract_with_tabula(pdf_path)
    
    all_tables = pdfplumber_tables + camelot_tables + tabula_tables
    
    if not all_tables:
        return []
    
    # Group tables by page and pick the best one per page
    page_tables = {}
    for table in all_tables:
        page = table["page"]
        if page not in page_tables:
            page_tables[page] = []
        page_tables[page].append(table)
    
    best_tables = []
    for page, tables in page_tables.items():
        if len(tables) == 1:
            best_table = tables[0]
        else:
            # Score each table and pick the best
            scored_tables = []
            for table in tables:
                score = score_table(table["data"], table["headers"])
                scored_tables.append((score, table))
            
            # Sort by score (descending) and pick the best
            scored_tables.sort(key=lambda x: x[0], reverse=True)
            best_table = scored_tables[0][1]
            
            # Add consensus metadata
            best_table["consensus_score"] = scored_tables[0][0]
            best_table["candidates"] = len(tables)
            best_table["engine_selected"] = best_table["engine"]
        
        # Normalize headers and units
        best_table["headers"] = normalize_headers(best_table["headers"])
        
        # Normalize numeric data
        normalized_data = []
        for row in best_table["data"]:
            normalized_row = []
            for cell in row:
                value, unit = normalize_units(str(cell))
                normalized_row.append({
                    "value": value,
                    "unit": unit,
                    "original": str(cell)
                })
            normalized_data.append(normalized_row)
        best_table["normalized_data"] = normalized_data
        
        best_tables.append(best_table)
    
    return best_tables
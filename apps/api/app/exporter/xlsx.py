from typing import List, Dict, Any
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter
from datetime import datetime
import io

def build_workbook(doc_id: str, artifacts: List[Dict], document_info: Dict = None) -> bytes:
    """Build an Excel workbook with document artifacts"""
    wb = Workbook()
    
    # Remove default sheet
    wb.remove(wb.active)
    
    # Create index sheet
    index_ws = wb.create_sheet("Index", 0)
    create_index_sheet(index_ws, doc_id, artifacts, document_info)
    
    # Create sheets for each table artifact
    table_artifacts = [a for a in artifacts if a.get("kind") == "table"]
    for i, artifact in enumerate(table_artifacts, 1):
        sheet_name = f"Table_{i}_Page_{artifact.get('page', 1)}"
        ws = wb.create_sheet(sheet_name)
        create_table_sheet(ws, artifact)
    
    # Save to bytes
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()

def create_index_sheet(ws, doc_id: str, artifacts: List[Dict], document_info: Dict = None):
    """Create the index sheet with document overview"""
    # Title
    ws['A1'] = f"Document Analysis Report"
    ws['A1'].font = Font(size=16, bold=True)
    ws.merge_cells('A1:D1')
    
    # Document info
    row = 3
    ws[f'A{row}'] = "Document ID:"
    ws[f'B{row}'] = doc_id
    row += 1
    
    if document_info:
        ws[f'A{row}'] = "Original Filename:"
        ws[f'B{row}'] = document_info.get("original_filename", "Unknown")
        row += 1
        
        ws[f'A{row}'] = "Created:"
        ws[f'B{row}'] = document_info.get("created_at", "Unknown")
        row += 1
    
    row += 1
    
    # Artifacts summary
    ws[f'A{row}'] = "Artifacts Summary"
    ws[f'A{row}'].font = Font(size=14, bold=True)
    row += 1
    
    # Headers
    headers = ["Type", "Page", "Engine", "Status", "Rows", "Cols", "Created"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col, value=header)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
    row += 1
    
    # Artifact data
    for artifact in artifacts:
        ws[f'A{row}'] = artifact.get("kind", "unknown")
        ws[f'B{row}'] = artifact.get("page", 0)
        ws[f'C{row}'] = artifact.get("engine", "unknown")
        ws[f'D{row}'] = artifact.get("status", "unknown")
        
        payload = artifact.get("payload", {})
        ws[f'E{row}'] = payload.get("rows", 0)
        ws[f'F{row}'] = payload.get("cols", 0)
        ws[f'G{row}'] = artifact.get("created_at", "unknown")
        row += 1
    
    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width

def create_table_sheet(ws, artifact: Dict):
    """Create a sheet for a table artifact"""
    payload = artifact.get("payload", {})
    data = payload.get("data", [])
    headers = payload.get("headers", [])
    
    if not data:
        ws['A1'] = "No table data available"
        return
    
    # Add provenance info
    ws['A1'] = f"Table from Page {artifact.get('page', 1)}"
    ws['A1'].font = Font(bold=True)
    ws['A2'] = f"Engine: {artifact.get('engine', 'unknown')}"
    ws['A3'] = f"Status: {artifact.get('status', 'unknown')}"
    ws['A4'] = f"Extracted: {artifact.get('created_at', 'unknown')}"
    
    # Add table data starting from row 6
    start_row = 6
    
    # Headers
    if headers:
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=start_row, column=col, value=header)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
        start_row += 1
    
    # Data rows
    for row_idx, row_data in enumerate(data, start_row):
        for col_idx, cell_value in enumerate(row_data, 1):
            ws.cell(row=row_idx, column=col_idx, value=cell_value)
    
    # Add borders
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Apply borders to data area
    if data:
        for row in range(start_row, start_row + len(data)):
            for col in range(1, len(data[0]) + 1):
                ws.cell(row=row, column=col).border = thin_border
    
    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width
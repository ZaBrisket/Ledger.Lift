import typer
import tempfile
import os
import uuid
from pathlib import Path
from rich.console import Console
from .database import WorkerDatabase
from .pipeline.render import render_pdf_preview
from .pipeline.extract import extract_tables_stub
from .services import DocumentProcessor

app = typer.Typer(help="Ledger Lift worker CLI")
console = Console()

@app.command("process-document")
def process_document(doc_id: str):
    """Process document by ID from database"""
    processor = DocumentProcessor()
    try:
        processor.process_document(doc_id)
        console.log(f"[green]Successfully processed document {doc_id}[/]")
    except Exception as e:
        console.log(f"[red]Failed to process document {doc_id}: {e}[/]")
        raise typer.Exit(1)

@app.command("process-file")
def process_file(pdf_path: str, doc_id: str = None):
    """Process local file (for testing)"""
    if not doc_id:
        doc_id = f"test-{uuid.uuid4()}"
    
    console.log(f"[bold]Processing file[/] {pdf_path} as {doc_id}")
    try:
        images = render_pdf_preview(pdf_path)
        console.log(f"Rendered {len(images)} preview image(s)")
        tables = extract_tables_stub(pdf_path)
        console.log(f"Extracted {len(tables)} table(s) [stub]")
        console.log("[green]Done[/]")
    except Exception as e:
        console.log(f"[red]Error: {e}[/]")
        raise typer.Exit(1)

@app.command("list-documents")
def list_documents():
    """List all documents in database"""
    db = WorkerDatabase()
    # This would need a method in WorkerDatabase to list documents
    console.log("Document listing not yet implemented")

if __name__ == "__main__":
    app()

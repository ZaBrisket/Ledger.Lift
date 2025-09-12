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
from .celery_cli import app as celery_app
from .tasks import process_document_task, batch_process_documents_task

app = typer.Typer(help="Ledger Lift worker CLI")
console = Console()

# Add Celery commands
app.add_typer(celery_app, name="celery", help="Celery worker commands")

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

@app.command("queue-document")
def queue_document(doc_id: str):
    """Queue a document for processing"""
    try:
        result = process_document_task.delay(doc_id)
        console.log(f"[green]Queued document {doc_id} for processing (task_id: {result.id})[/]")
    except Exception as e:
        console.log(f"[red]Failed to queue document {doc_id}: {e}[/]")
        raise typer.Exit(1)

@app.command("queue-batch")
def queue_batch(doc_ids: str):
    """Queue multiple documents for batch processing"""
    try:
        doc_id_list = [doc_id.strip() for doc_id in doc_ids.split(',')]
        result = batch_process_documents_task.delay(doc_id_list)
        console.log(f"[green]Queued {len(doc_id_list)} documents for batch processing (task_id: {result.id})[/]")
    except Exception as e:
        console.log(f"[red]Failed to queue batch processing: {e}[/]")
        raise typer.Exit(1)

if __name__ == "__main__":
    app()

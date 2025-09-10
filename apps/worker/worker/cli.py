import typer
from rich.console import Console
from .pipeline.render import render_pdf_preview
from .pipeline.extract import extract_tables_stub

app = typer.Typer(help="Ledger Lift worker CLI")

@app.command("process-document")
def process_document(doc_id: str, pdf_path: str = "tests/fixtures/sample.pdf"):
    console = Console()
    console.log(f"[bold]Processing document[/] {doc_id}")
    images = render_pdf_preview(pdf_path)
    console.log(f"Rendered {len(images)} preview image(s)")
    tables = extract_tables_stub(pdf_path)
    console.log(f"Extracted {len(tables)} table(s) [stub]")
    console.log("[green]Done[/]")

if __name__ == "__main__":
    app()

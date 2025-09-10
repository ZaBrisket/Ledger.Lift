import typer
import uuid
import requests
import os
from rich.console import Console
from .pipeline.render import render_pdf_preview
from .pipeline.extract import extract_tables_stub, extract_consensus_tables_and_post
from .pipeline.ocr import ocr_pdf_pages, is_ocr_enabled
from .telemetry import get_tracer, render_pages_counter, ocr_pages_counter

app = typer.Typer(help="Ledger Lift worker CLI")

@app.command("process-document")
def process_document(doc_id: str, pdf_path: str = "tests/fixtures/sample.pdf"):
    tracer = get_tracer()
    console = Console()
    
    with tracer.start_as_current_span("process_document") as span:
        span.set_attribute("document_id", doc_id)
        span.set_attribute("pdf_path", pdf_path)
        
        console.log(f"[bold]Processing document[/] {doc_id}")
        
        # Render preview images
        with tracer.start_as_current_span("render_previews"):
            images = render_pdf_preview(pdf_path)
            render_pages_counter.add(len(images))
            console.log(f"Rendered {len(images)} preview image(s)")
        
        # Extract tables - try consensus first, fallback to stub
        consensus_enabled = os.getenv("CONSENSUS_ENABLED", "false").lower() == "true"
        if consensus_enabled:
            with tracer.start_as_current_span("consensus_extraction"):
                console.log("[yellow]Consensus extraction enabled - running multi-engine extraction...[/]")
                consensus_artifacts = extract_consensus_tables_and_post(doc_id, pdf_path)
                console.log(f"Posted {len(consensus_artifacts)} consensus table artifact(s)")
        else:
            # Fallback to stub
            with tracer.start_as_current_span("stub_extraction"):
                tables = extract_tables_stub(pdf_path)
                console.log(f"Extracted {len(tables)} table(s) [stub]")
        
        # OCR processing (if enabled)
        if is_ocr_enabled():
            with tracer.start_as_current_span("ocr_processing") as ocr_span:
                console.log("[yellow]OCR enabled - processing pages...[/]")
                ocr_results = ocr_pdf_pages(pdf_path)
                ocr_pages_counter.add(len(ocr_results))
                ocr_span.set_attribute("pages_processed", len(ocr_results))
                
                # Post OCR artifacts to API
                api_base = os.getenv("API_BASE_URL", "http://localhost:8000")
                ocr_artifacts_posted = 0
                
                for ocr_result in ocr_results:
                    artifact_payload = {
                        "id": str(uuid.uuid4()),
                        "document_id": doc_id,
                        "kind": "ocr",
                        "page": ocr_result["page"],
                        "engine": "tesseract",
                        "payload": ocr_result,
                        "status": "pending"
                    }
                    
                    try:
                        response = requests.post(
                            f"{api_base}/v1/artifacts",
                            json=artifact_payload
                        )
                        
                        if response.status_code == 201:
                            ocr_artifacts_posted += 1
                        else:
                            console.log(f"[red]Failed to post OCR artifact: {response.status_code}[/]")
                            
                    except Exception as e:
                        console.log(f"[red]Error posting OCR artifact: {e}[/]")
                
                console.log(f"Posted {ocr_artifacts_posted} OCR artifact(s)")
                ocr_span.set_attribute("artifacts_posted", ocr_artifacts_posted)
        else:
            console.log("[dim]OCR disabled (OCR_ENABLED=false)[/]")
        
        console.log("[green]Done[/]")

if __name__ == "__main__":
    app()

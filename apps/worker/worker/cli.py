import typer
import time
from rich.console import Console
from .pipeline.render import render_pdf_preview
from .pipeline.extract import extract_tables_stub, extract_native_tables_and_post, extract_consensus_tables_and_post
from .pipeline.ocr import extract_ocr_from_pdf
from .settings import settings
from .telemetry import setup_telemetry, get_tracer

app = typer.Typer(help="Ledger Lift worker CLI")

@app.command("process-document")
def process_document(doc_id: str, pdf_path: str = "tests/fixtures/sample.pdf"):
    console = Console()
    
    # Setup telemetry
    telemetry_metrics = setup_telemetry()
    tracer = get_tracer()
    
    with tracer.start_as_current_span("worker.process_document") as span:
        span.set_attribute("document.id", doc_id)
        span.set_attribute("document.path", pdf_path)
        
        console.log(f"[bold]Processing document[/] {doc_id}")
        
        # Render previews
        start_time = time.time()
        with tracer.start_as_current_span("worker.render_preview"):
            images = render_pdf_preview(pdf_path)
            console.log(f"Rendered {len(images)} preview image(s)")
        
        render_time = (time.time() - start_time) * 1000
        if telemetry_metrics:
            telemetry_metrics["render_time_histogram"].record(render_time)
        
        # Extract tables
        tables = extract_tables_stub(pdf_path)
        console.log(f"Extracted {len(tables)} table(s) [stub]")
        
        # Run table extraction and post to API
        start_time = time.time()
        try:
            with tracer.start_as_current_span("worker.extract_tables"):
                if settings.consensus_enabled:
                    artifacts = extract_consensus_tables_and_post(doc_id, pdf_path)
                    console.log(f"Posted {len(artifacts)} consensus table artifacts to API")
                else:
                    artifacts = extract_native_tables_and_post(doc_id, pdf_path)
                    console.log(f"Posted {len(artifacts)} native table artifacts to API")
        except Exception as e:
            console.log(f"[yellow]Warning: Failed to post table artifacts: {e}[/]")
            span.record_exception(e)
        
        extract_time = (time.time() - start_time) * 1000
        if telemetry_metrics:
            telemetry_metrics["extract_time_histogram"].record(extract_time)
        
        # Run OCR if enabled
        if settings.ocr_enabled:
            try:
                with tracer.start_as_current_span("worker.ocr"):
                    ocr_results = extract_ocr_from_pdf(pdf_path)
                    console.log(f"OCR processed {len(ocr_results)} page(s)")
                    
                    if telemetry_metrics:
                        telemetry_metrics["ocr_pages_counter"].add(len(ocr_results))
                        if ocr_results:
                            mean_conf = sum(r.get("mean_conf", 0) for r in ocr_results) / len(ocr_results)
                            telemetry_metrics["ocr_confidence_histogram"].record(mean_conf)
                    
                    # TODO: Post OCR artifacts to API
            except Exception as e:
                console.log(f"[yellow]Warning: OCR failed: {e}[/]")
                span.record_exception(e)
        else:
            console.log("[dim]OCR disabled[/]")
        
        # Record metrics
        if telemetry_metrics:
            telemetry_metrics["document_processed_counter"].add(1)
        
        console.log("[green]Done[/]")

if __name__ == "__main__":
    app()

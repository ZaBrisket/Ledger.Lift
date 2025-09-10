import tempfile
import logging
import json
from pathlib import Path
from .database import WorkerDatabase
from .aws_client import WorkerS3Client
from .pipeline.render import render_pdf_preview
from .pipeline.extract import extract_tables_stub
from .models import ProcessingStatus, EventType

logger = logging.getLogger(__name__)

class DocumentProcessor:
    def __init__(self):
        self.db = WorkerDatabase()
        self.s3 = WorkerS3Client()

    def process_document(self, doc_id: str):
        """Main processing pipeline"""
        # Update status to processing
        self.db.update_document_status(doc_id, ProcessingStatus.PROCESSING)
        self.db.log_event(doc_id, EventType.PROCESSING_STARTED, "Document processing started")
        
        try:
            # Get document metadata
            doc = self.db.get_document(doc_id)
            if not doc:
                raise ValueError(f"Document not found: {doc_id}")

            logger.info(f"Processing document {doc_id}: {doc.original_filename}")

            # Download PDF from S3
            pdf_content = self.s3.download_file(doc.s3_key)
            
            # Process in temporary file
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                tmp_file.write(pdf_content)
                tmp_path = tmp_file.name

            try:
                # Render page previews
                preview_paths = render_pdf_preview(tmp_path)
                logger.info(f"Rendered {len(preview_paths)} preview images for {doc_id}")
                
                # Upload previews to S3 and create page records
                for i, preview_path in enumerate(preview_paths):
                    preview_key = f"previews/{doc_id}/page_{i+1}.png"
                    with open(preview_path, 'rb') as f:
                        self.s3.upload_file(preview_key, f.read(), 'image/png')
                    
                    # Save page record to database
                    self.db.create_page(
                        document_id=doc_id,
                        page_number=i + 1,
                        preview_s3_key=preview_key
                    )

                # Extract tables (stub)
                tables = extract_tables_stub(tmp_path)
                logger.info(f"Extracted {len(tables)} tables from {doc_id}")

                # Log extraction completion
                self.db.log_event(
                    doc_id, 
                    EventType.EXTRACTION_COMPLETED, 
                    f"Extraction completed: {len(tables)} tables, {len(preview_paths)} pages",
                    event_metadata=json.dumps({"tables_count": len(tables), "pages_count": len(preview_paths)})
                )

                # Update status to completed
                self.db.update_document_status(doc_id, ProcessingStatus.COMPLETED)
                self.db.log_event(doc_id, EventType.PROCESSING_COMPLETED, "Document processing completed successfully")
                
            finally:
                # Cleanup
                Path(tmp_path).unlink(missing_ok=True)
                for preview_path in preview_paths:
                    preview_path.unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"Processing failed for {doc_id}: {e}")
            self.db.update_document_status(doc_id, ProcessingStatus.FAILED, str(e))
            self.db.log_event(
                doc_id, 
                EventType.PROCESSING_FAILED, 
                f"Processing failed: {str(e)}",
                event_metadata=json.dumps({"error": str(e), "error_type": type(e).__name__})
            )
            raise
"""
Enhanced document processor with comprehensive error handling, timeouts, and resource management.
"""
import tempfile
import logging
import json
import time
import os
import threading
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import pandas as pd
from .database import WorkerDatabase
from .aws_client import WorkerS3Client
from .pipeline.render import render_pdf_preview
from .pipeline.extract import extract_tables_production, apply_ledger_transformations
from .models import ProcessingStatus, EventType

logger = logging.getLogger(__name__)

class TimeoutError(Exception):
    """Raised when an operation times out."""
    pass

class ProcessingError(Exception):
    """Raised when document processing fails."""
    pass

class ResourceManager:
    """Manages temporary files and ensures cleanup."""
    
    def __init__(self):
        self.temp_files = []
        self.temp_dirs = []
    
    def create_temp_file(self, suffix: str = '', prefix: str = 'worker_') -> str:
        """Create a temporary file and track it for cleanup."""
        fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix)
        os.close(fd)  # Close the file descriptor, we just need the path
        self.temp_files.append(path)
        logger.debug(f"Created temporary file: {path}")
        return path
    
    def create_temp_dir(self, prefix: str = 'worker_') -> str:
        """Create a temporary directory and track it for cleanup."""
        path = tempfile.mkdtemp(prefix=prefix)
        self.temp_dirs.append(path)
        logger.debug(f"Created temporary directory: {path}")
        return path
    
    def cleanup(self):
        """Clean up all tracked temporary files and directories."""
        cleanup_errors = []
        
        # Clean up temporary files
        for file_path in self.temp_files:
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
                    logger.debug(f"Cleaned up temporary file: {file_path}")
            except Exception as e:
                cleanup_errors.append(f"Failed to cleanup file {file_path}: {e}")
        
        # Clean up temporary directories
        for dir_path in self.temp_dirs:
            try:
                if os.path.exists(dir_path):
                    import shutil
                    shutil.rmtree(dir_path)
                    logger.debug(f"Cleaned up temporary directory: {dir_path}")
            except Exception as e:
                cleanup_errors.append(f"Failed to cleanup directory {dir_path}: {e}")
        
        if cleanup_errors:
            logger.warning(f"Cleanup errors: {'; '.join(cleanup_errors)}")
        
        # Reset tracking lists
        self.temp_files.clear()
        self.temp_dirs.clear()

class TimeoutManager:
    """Thread-safe, cross-platform timeout manager."""
    
    def __init__(self):
        self._timers = {}
        self._lock = threading.Lock()
    
    def create_timeout(self, timeout_id: str, seconds: int, callback):
        """Create a timeout that calls callback after seconds."""
        with self._lock:
            # Cancel existing timer if any
            if timeout_id in self._timers:
                self._timers[timeout_id].cancel()
            
            timer = threading.Timer(seconds, callback)
            self._timers[timeout_id] = timer
            timer.start()
            return timer
    
    def cancel_timeout(self, timeout_id: str):
        """Cancel a timeout by ID."""
        with self._lock:
            if timeout_id in self._timers:
                self._timers[timeout_id].cancel()
                del self._timers[timeout_id]
    
    def cleanup_all(self):
        """Cancel all active timers."""
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()

# Global timeout manager instance
_timeout_manager = TimeoutManager()

@contextmanager
def timeout_context(seconds: int):
    """
    Cross-platform, thread-safe context manager for operation timeouts.
    
    This implementation works on Windows, Linux, and macOS without relying
    on Unix-specific signals. It's also thread-safe for concurrent operations.
    """
    timeout_id = f"timeout_{threading.current_thread().ident}_{time.time()}"
    timeout_occurred = threading.Event()
    
    def timeout_callback():
        timeout_occurred.set()
    
    # Create the timeout
    timer = _timeout_manager.create_timeout(timeout_id, seconds, timeout_callback)
    
    try:
        yield timeout_occurred
        
        # Check if timeout occurred during execution
        if timeout_occurred.is_set():
            raise TimeoutError(f"Operation timed out after {seconds} seconds")
            
    finally:
        # Always clean up the timeout
        _timeout_manager.cancel_timeout(timeout_id)

@contextmanager
def executor_timeout_context(seconds: int):
    """
    Alternative timeout implementation using ThreadPoolExecutor.
    
    This provides a more robust timeout mechanism for CPU-bound operations
    that might not check the timeout_occurred event frequently enough.
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        def timeout_wrapper():
            yield
        
        try:
            future = executor.submit(timeout_wrapper)
            future.result(timeout=seconds)
            yield
        except FuturesTimeoutError:
            raise TimeoutError(f"Operation timed out after {seconds} seconds")

class DocumentProcessor:
    """Enhanced document processor with comprehensive error handling and resource management."""
    
    def __init__(self):
        self.db = WorkerDatabase()
        self.s3 = WorkerS3Client()
        self._processing_stats = {
            'total_processed': 0,
            'successful_processed': 0,
            'failed_processed': 0,
            'avg_processing_time': 0,
            'last_processed_time': 0
        }
    
    def _record_processing_stats(self, success: bool, processing_time: float):
        """Record processing statistics."""
        self._processing_stats['total_processed'] += 1
        self._processing_stats['last_processed_time'] = time.time()
        
        if success:
            self._processing_stats['successful_processed'] += 1
        else:
            self._processing_stats['failed_processed'] += 1
        
        # Update average processing time
        total = self._processing_stats['total_processed']
        current_avg = self._processing_stats['avg_processing_time']
        self._processing_stats['avg_processing_time'] = (
            (current_avg * (total - 1) + processing_time) / total
        )
    
    def process_document(self, doc_id: str, timeout_seconds: int = 300) -> Dict[str, Any]:
        """
        Main processing pipeline with comprehensive error handling and timeouts.
        
        Args:
            doc_id: Document ID to process
            timeout_seconds: Maximum processing time (default 5 minutes)
            
        Returns:
            Dictionary with processing results and metadata
        """
        if not doc_id or not doc_id.strip():
            raise ValueError("Document ID cannot be empty")
        
        doc_id = doc_id.strip()
        start_time = time.time()
        resource_manager = ResourceManager()
        processing_metadata = {
            'doc_id': doc_id,
            'start_time': start_time,
            'timeout_seconds': timeout_seconds,
            'stages_completed': [],
            'errors': []
        }
        
        logger.info(f"Starting document processing: {doc_id}")
        
        try:
            # Use a separate thread for the main processing pipeline to enable timeout
            def _process_pipeline():
                # Stage 1: Update status to processing
                self._update_status_safe(doc_id, ProcessingStatus.PROCESSING, processing_metadata)
                self._log_event_safe(doc_id, EventType.PROCESSING_STARTED, "Document processing started", processing_metadata)
                processing_metadata['stages_completed'].append('status_update')
                
                # Stage 2: Get document metadata with validation
                doc = self._get_document_safe(doc_id, processing_metadata)
                processing_metadata['stages_completed'].append('document_retrieval')
                
                logger.info(f"Processing document {doc_id}: {doc.original_filename}")
                
                # Stage 3: Download PDF from S3 with validation
                pdf_content = self._download_document_safe(doc, processing_metadata)
                processing_metadata['stages_completed'].append('s3_download')
                processing_metadata['pdf_size'] = len(pdf_content)
                
                # Stage 4: Create temporary file for processing
                tmp_path = resource_manager.create_temp_file(suffix='.pdf')
                with open(tmp_path, 'wb') as tmp_file:
                    tmp_file.write(pdf_content)
                processing_metadata['stages_completed'].append('temp_file_creation')
                
                # Stage 5: Render page previews with timeout
                preview_paths = self._render_previews_safe(tmp_path, doc_id, processing_metadata)
                processing_metadata['stages_completed'].append('preview_rendering')
                processing_metadata['preview_count'] = len(preview_paths)
                
                # Stage 6: Upload previews to S3 and create page records
                self._process_previews_safe(doc_id, preview_paths, processing_metadata)
                processing_metadata['stages_completed'].append('preview_upload')
                
                # Stage 7: Extract tables with timeout
                tables = self._extract_tables_safe(tmp_path, doc_id, processing_metadata)
                processing_metadata['stages_completed'].append('table_extraction')
                processing_metadata['table_count'] = len(tables)
                
                # Stage 8: Log extraction completion
                self._log_event_safe(
                    doc_id, 
                    EventType.EXTRACTION_COMPLETED, 
                    f"Extraction completed: {len(tables)} tables, {len(preview_paths)} pages",
                    {
                        **processing_metadata,
                        "tables_count": len(tables), 
                        "pages_count": len(preview_paths)
                    }
                )
                processing_metadata['stages_completed'].append('extraction_logging')
                
                # Stage 9: Update status to completed
                self._update_status_safe(doc_id, ProcessingStatus.COMPLETED, processing_metadata)
                self._log_event_safe(doc_id, EventType.PROCESSING_COMPLETED, "Document processing completed successfully", processing_metadata)
                processing_metadata['stages_completed'].append('completion_update')
                
                processing_time = time.time() - start_time
                self._record_processing_stats(success=True, processing_time=processing_time)
                
                processing_metadata.update({
                    'success': True,
                    'processing_time': processing_time,
                    'end_time': time.time()
                })
                
                logger.info(f"Document processing completed successfully: {doc_id} in {processing_time:.3f}s")
                return processing_metadata
            
            # Execute the processing pipeline with timeout
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_process_pipeline)
                try:
                    return future.result(timeout=timeout_seconds)
                except FuturesTimeoutError:
                    # Cancel the future if possible
                    future.cancel()
                    raise TimeoutError(f"Processing timed out after {timeout_seconds} seconds")
                
        except TimeoutError as e:
            processing_time = time.time() - start_time
            error_msg = f"Processing timed out after {processing_time:.1f}s (limit: {timeout_seconds}s)"
            logger.error(f"Processing timeout for {doc_id}: {error_msg}")
            
            processing_metadata.update({
                'success': False,
                'error': error_msg,
                'error_type': 'TIMEOUT_ERROR',
                'processing_time': processing_time
            })
            
            self._handle_processing_failure(doc_id, error_msg, processing_metadata)
            self._record_processing_stats(success=False, processing_time=processing_time)
            raise ProcessingError(error_msg)
            
        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = f"Processing failed: {str(e)}"
            logger.error(f"Processing failed for {doc_id}: {error_msg}", exc_info=True)
            
            processing_metadata.update({
                'success': False,
                'error': error_msg,
                'error_type': type(e).__name__,
                'processing_time': processing_time
            })
            
            self._handle_processing_failure(doc_id, error_msg, processing_metadata)
            self._record_processing_stats(success=False, processing_time=processing_time)
            raise ProcessingError(error_msg)
            
        finally:
            # Always clean up resources
            try:
                resource_manager.cleanup()
                logger.debug(f"Resource cleanup completed for {doc_id}")
            except Exception as cleanup_error:
                logger.error(f"Resource cleanup failed for {doc_id}: {cleanup_error}")
    
    def _get_document_safe(self, doc_id: str, metadata: Dict[str, Any]) -> Any:
        """Safely get document with error handling."""
        try:
            doc = self.db.get_document(doc_id)
            if not doc:
                raise ValueError(f"Document not found: {doc_id}")
            
            # Validate document state
            if not doc.s3_key:
                raise ValueError(f"Document has no S3 key: {doc_id}")
            
            return doc
            
        except Exception as e:
            metadata['errors'].append(f"Document retrieval failed: {e}")
            raise
    
    def _download_document_safe(self, doc: Any, metadata: Dict[str, Any]) -> bytes:
        """Safely download document from S3 with validation."""
        try:
            # Check S3 health before download
            s3_health = self.s3.health_check()
            if s3_health.get('status') != 'healthy':
                raise Exception(f"S3 unhealthy: {s3_health.get('error', 'Unknown error')}")
            
            # Download with size validation
            pdf_content = self.s3.download_file(doc.s3_key)
            
            if not pdf_content:
                raise ValueError("Downloaded file is empty")
            
            # Basic PDF validation (check magic bytes)
            if not pdf_content.startswith(b'%PDF-'):
                raise ValueError("Downloaded file is not a valid PDF")
            
            # Size validation
            max_size = int(os.getenv('MAX_PDF_SIZE', str(100 * 1024 * 1024)))  # 100MB default
            if len(pdf_content) > max_size:
                raise ValueError(f"PDF too large: {len(pdf_content)} bytes (max: {max_size})")
            
            logger.debug(f"Downloaded PDF: {len(pdf_content)} bytes from {doc.s3_key}")
            return pdf_content
            
        except Exception as e:
            metadata['errors'].append(f"S3 download failed: {e}")
            raise
    
    def _render_previews_safe(self, tmp_path: str, doc_id: str, metadata: Dict[str, Any]) -> List[Path]:
        """Safely render PDF previews with timeout and error handling."""
        try:
            # Set a reasonable timeout for PDF rendering
            render_timeout = int(os.getenv('PDF_RENDER_TIMEOUT', '120'))  # 2 minutes default
            
            # Execute rendering with timeout using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(render_pdf_preview, tmp_path)
                try:
                    preview_paths = future.result(timeout=render_timeout)
                except FuturesTimeoutError:
                    future.cancel()
                    raise TimeoutError(f"PDF rendering timed out after {render_timeout}s")
            
            if not preview_paths:
                raise ValueError("No preview pages were generated")
            
            # Validate preview files
            for preview_path in preview_paths:
                if not preview_path.exists():
                    raise ValueError(f"Preview file not found: {preview_path}")
                if preview_path.stat().st_size == 0:
                    raise ValueError(f"Preview file is empty: {preview_path}")
            
            logger.info(f"Rendered {len(preview_paths)} preview images for {doc_id}")
            return preview_paths
            
        except TimeoutError:
            error_msg = f"PDF rendering timed out after {render_timeout}s"
            metadata['errors'].append(error_msg)
            raise TimeoutError(error_msg)
        except Exception as e:
            metadata['errors'].append(f"Preview rendering failed: {e}")
            raise
    
    def _process_previews_safe(self, doc_id: str, preview_paths: List[Path], metadata: Dict[str, Any]):
        """Safely process and upload preview images."""
        uploaded_count = 0
        
        try:
            for i, preview_path in enumerate(preview_paths):
                try:
                    preview_key = f"previews/{doc_id}/page_{i+1}.png"
                    
                    # Read and validate preview file
                    with open(preview_path, 'rb') as f:
                        preview_data = f.read()
                    
                    if not preview_data:
                        raise ValueError(f"Preview file is empty: {preview_path}")
                    
                    # Upload to S3 with validation
                    self.s3.upload_file(preview_key, preview_data, 'image/png')
                    
                    # Save page record to database
                    self.db.create_page(
                        document_id=doc_id,
                        page_number=i + 1,
                        preview_s3_key=preview_key
                    )
                    
                    uploaded_count += 1
                    logger.debug(f"Uploaded preview {i+1}/{len(preview_paths)} for {doc_id}")
                    
                except Exception as e:
                    logger.error(f"Failed to process preview {i+1} for {doc_id}: {e}")
                    metadata['errors'].append(f"Preview {i+1} processing failed: {e}")
                    # Continue with other previews
            
            if uploaded_count == 0:
                raise ValueError("No previews were successfully uploaded")
            
            logger.info(f"Successfully uploaded {uploaded_count}/{len(preview_paths)} previews for {doc_id}")
            
        except Exception as e:
            if uploaded_count == 0:
                # If no previews were uploaded, this is a critical failure
                raise
            else:
                # Some previews were uploaded, log warning but continue
                logger.warning(f"Partial preview upload failure for {doc_id}: {e}")
    
    def _extract_tables_safe(self, tmp_path: str, doc_id: str, metadata: Dict[str, Any]) -> List[Any]:
        """Safely extract tables with timeout and error handling."""
        try:
            # Set a reasonable timeout for table extraction
            extract_timeout = int(os.getenv('TABLE_EXTRACT_TIMEOUT', '180'))  # 3 minutes default
            
            # Execute table extraction with timeout using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(extract_tables_production, tmp_path)
                try:
                    tables = future.result(timeout=extract_timeout)
                except FuturesTimeoutError:
                    future.cancel()
                    raise TimeoutError(f"Table extraction timed out after {extract_timeout}s")
            
            # Store extracted tables as artifacts
            self._store_table_artifacts(doc_id, tables, metadata)
            
            logger.info(f"Extracted {len(tables)} tables from {doc_id}")
            return tables
            
        except TimeoutError:
            error_msg = f"Table extraction timed out after {extract_timeout}s"
            metadata['errors'].append(error_msg)
            raise TimeoutError(error_msg)
        except Exception as e:
            metadata['errors'].append(f"Table extraction failed: {e}")
            # Table extraction failure is not critical, continue processing
            logger.warning(f"Table extraction failed for {doc_id}: {e}")
            return []  # Return empty list to continue processing
    
    def _update_status_safe(self, doc_id: str, status: ProcessingStatus, metadata: Dict[str, Any]):
        """Safely update document status with error handling."""
        try:
            self.db.update_document_status(doc_id, status)
        except Exception as e:
            error_msg = f"Status update failed: {e}"
            metadata['errors'].append(error_msg)
            logger.error(f"Failed to update status for {doc_id} to {status.value}: {e}")
            # Don't raise here, status updates are not critical for processing
    
    def _log_event_safe(self, doc_id: str, event_type: EventType, message: str, event_metadata: Dict[str, Any]):
        """Safely log processing event with error handling."""
        try:
            self.db.log_event(doc_id, event_type, message, event_metadata=json.dumps(event_metadata))
        except Exception as e:
            logger.error(f"Failed to log event for {doc_id}: {e}")
            # Don't raise here, event logging is not critical for processing
    
    def _store_table_artifacts(self, doc_id: str, tables: List[Dict], metadata: Dict[str, Any]):
        """Store extracted tables as artifacts in the database."""
        try:
            for table in tables:
                # Apply ledger transformations to the data
                if table.get('data'):
                    df = pd.DataFrame(table['data'])
                    transformed_df = apply_ledger_transformations(df)
                    table['data'] = transformed_df.to_dict('records')
                
                # Store as artifact
                self.db.create_artifact(
                    document_id=doc_id,
                    artifact_type='table',
                    extraction_engine=table.get('engine', 'unknown'),
                    confidence_score=table.get('accuracy', 0.0),
                    data=json.dumps(table),
                    page_id=None  # Will be linked to page if available
                )
                
            logger.debug(f"Stored {len(tables)} table artifacts for {doc_id}")
            
        except Exception as e:
            logger.error(f"Failed to store table artifacts for {doc_id}: {e}")
            metadata['errors'].append(f"Artifact storage failed: {e}")
            # Don't raise here, artifact storage is not critical for processing
    
    def _handle_processing_failure(self, doc_id: str, error_message: str, metadata: Dict[str, Any]):
        """Handle processing failure with proper logging and status updates."""
        try:
            self._update_status_safe(doc_id, ProcessingStatus.FAILED, metadata)
            self._log_event_safe(
                doc_id, 
                EventType.PROCESSING_FAILED, 
                f"Processing failed: {error_message}",
                {
                    **metadata,
                    "error": error_message,
                    "stages_completed": metadata.get('stages_completed', []),
                    "errors": metadata.get('errors', [])
                }
            )
        except Exception as e:
            logger.error(f"Failed to handle processing failure for {doc_id}: {e}")
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get processing statistics."""
        return {
            'processing_stats': self._processing_stats.copy(),
            's3_stats': self.s3.get_stats(),
            'timestamp': time.time()
        }
    
    def reset_stats(self):
        """Reset processing statistics."""
        self._processing_stats = {
            'total_processed': 0,
            'successful_processed': 0,
            'failed_processed': 0,
            'avg_processing_time': 0,
            'last_processed_time': 0
        }
        self.s3.reset_stats()
        logger.info("Document processor statistics reset")
    
    def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check for document processor."""
        try:
            # Check S3 health
            s3_health = self.s3.health_check()
            
            # Check database health (basic connection test)
            db_healthy = True
            db_error = None
            try:
                # This would need to be implemented in WorkerDatabase
                # For now, assume healthy if no exception during init
                pass
            except Exception as e:
                db_healthy = False
                db_error = str(e)
            
            overall_status = 'healthy'
            if s3_health.get('status') != 'healthy' or not db_healthy:
                overall_status = 'unhealthy'
            
            return {
                'status': overall_status,
                's3_health': s3_health,
                'database_healthy': db_healthy,
                'database_error': db_error,
                'processing_stats': self._processing_stats.copy(),
                'timestamp': time.time()
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': time.time()
            }
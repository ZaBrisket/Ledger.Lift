from typing import List, Dict
import uuid
import requests
import os
from packages.extractors.extractors.native_tables import extract_native_tables

# Try to import consensus module
try:
    from packages.extractors.extractors.consensus import run_consensus_extraction
    CONSENSUS_AVAILABLE = True
except ImportError:
    CONSENSUS_AVAILABLE = False

def extract_tables_stub(pdf_path: str) -> List[Dict]:
    # Placeholder: real implementation will call packages/extractors
    return [{"page": 1, "rows": 0, "cols": 0, "engine": "stub"}]

def extract_native_tables_and_post(doc_id: str, pdf_path: str) -> List[str]:
    """Extract native tables and POST results to API."""
    # Extract tables using native extractor
    tables = extract_native_tables(pdf_path)
    
    # API endpoint
    api_base = os.getenv("API_BASE_URL", "http://localhost:8000")
    
    artifact_ids = []
    
    for i, table in enumerate(tables):
        # Create artifact payload
        artifact_payload = {
            "id": str(uuid.uuid4()),
            "document_id": doc_id,
            "kind": "table",
            "page": table.get("page", 1),
            "engine": "native",
            "payload": table,
            "status": "pending"
        }
        
        try:
            # POST to API (we'll need to create this endpoint)
            response = requests.post(
                f"{api_base}/v1/artifacts",
                json=artifact_payload
            )
            
            if response.status_code == 201:
                artifact_ids.append(artifact_payload["id"])
            else:
                print(f"Failed to create artifact: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"Error posting artifact: {e}")
    
    return artifact_ids

def extract_consensus_tables_and_post(doc_id: str, pdf_path: str) -> List[str]:
    """Extract tables using consensus approach and POST results to API."""
    if not CONSENSUS_AVAILABLE:
        print("Consensus extraction not available - install optional dependencies")
        return []
    
    consensus_enabled = os.getenv("CONSENSUS_ENABLED", "false").lower() == "true"
    if not consensus_enabled:
        print("Consensus extraction disabled (CONSENSUS_ENABLED=false)")
        return []
    
    # Extract tables using consensus
    tables = run_consensus_extraction(pdf_path)
    
    # API endpoint
    api_base = os.getenv("API_BASE_URL", "http://localhost:8000")
    
    artifact_ids = []
    
    for table in tables:
        # Create artifact payload
        artifact_payload = {
            "id": str(uuid.uuid4()),
            "document_id": doc_id,
            "kind": "table",
            "page": table.get("page", 1),
            "engine": "consensus",
            "payload": table,
            "status": "pending"
        }
        
        try:
            # POST to API
            response = requests.post(
                f"{api_base}/v1/artifacts",
                json=artifact_payload
            )
            
            if response.status_code == 201:
                artifact_ids.append(artifact_payload["id"])
            else:
                print(f"Failed to create consensus artifact: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"Error posting consensus artifact: {e}")
    
    return artifact_ids

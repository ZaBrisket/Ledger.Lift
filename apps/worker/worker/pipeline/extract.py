from typing import List, Dict
import uuid
import requests
from ..settings import settings

def extract_tables_stub(pdf_path: str) -> List[Dict]:
    # Placeholder: real implementation will call packages/extractors
    return [{"page": 1, "rows": 0, "cols": 0, "engine": "stub"}]

def extract_native_tables_and_post(doc_id: str, pdf_path: str, api_base_url: str = "http://localhost:8000") -> List[Dict]:
    """Extract tables using native extractors and POST results to API"""
    try:
        # Import the native extractors
        from packages.extractors.extractors.native_tables import extract_native_tables
        
        # Extract tables
        tables = extract_native_tables(pdf_path)
        
        # POST each table as an artifact to the API
        artifacts = []
        for table in tables:
            artifact_id = str(uuid.uuid4())
            artifact_data = {
                "id": artifact_id,
                "document_id": doc_id,
                "kind": "table",
                "page": table.get("page", 1),
                "engine": "native",
                "payload": {
                    "rows": table.get("rows", 0),
                    "cols": table.get("cols", 0),
                    "data": table.get("data", []),
                    "headers": table.get("headers", [])
                },
                "status": "completed"
            }
            
            # POST to API
            try:
                response = requests.post(
                    f"{api_base_url}/v1/artifacts",
                    json=artifact_data,
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code == 201:
                    artifacts.append(artifact_data)
                else:
                    print(f"Failed to create artifact: {response.status_code} - {response.text}")
            except Exception as e:
                print(f"Error posting artifact to API: {e}")
                artifacts.append(artifact_data)  # Still return it for debugging
        
        return artifacts
    except Exception as e:
        print(f"Error extracting tables: {e}")
        return []

def extract_consensus_tables_and_post(doc_id: str, pdf_path: str, api_base_url: str = "http://localhost:8000") -> List[Dict]:
    """Extract tables using consensus of multiple engines and POST results to API"""
    try:
        # Import the consensus extractors
        from packages.extractors.extractors.consensus import extract_consensus_tables
        
        # Extract tables using consensus
        tables = extract_consensus_tables(pdf_path)
        
        # POST each table as an artifact to the API
        artifacts = []
        for table in tables:
            artifact_id = str(uuid.uuid4())
            artifact_data = {
                "id": artifact_id,
                "document_id": doc_id,
                "kind": "table",
                "page": table.get("page", 1),
                "engine": table.get("engine_selected", "consensus"),
                "payload": {
                    "rows": table.get("rows", 0),
                    "cols": table.get("cols", 0),
                    "data": table.get("data", []),
                    "headers": table.get("headers", []),
                    "normalized_data": table.get("normalized_data", []),
                    "consensus_score": table.get("consensus_score", 0.0),
                    "candidates": table.get("candidates", 1)
                },
                "status": "completed"
            }
            
            # POST to API
            try:
                response = requests.post(
                    f"{api_base_url}/v1/artifacts",
                    json=artifact_data,
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code == 201:
                    artifacts.append(artifact_data)
                else:
                    print(f"Failed to create artifact: {response.status_code} - {response.text}")
            except Exception as e:
                print(f"Error posting artifact to API: {e}")
                artifacts.append(artifact_data)  # Still return it for debugging
        
        return artifacts
    except Exception as e:
        print(f"Error extracting tables with consensus: {e}")
        return []

from typing import List, Dict
import cv2
import numpy as np
import pytesseract
import fitz  # PyMuPDF
import os
import tempfile
from pathlib import Path


def preprocess_image_for_ocr(image_array: np.ndarray) -> np.ndarray:
    """Apply preprocessing to improve OCR accuracy."""
    # Convert to grayscale if needed
    if len(image_array.shape) == 3:
        gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
    else:
        gray = image_array
    
    # Apply threshold to get binary image
    # Use adaptive threshold for better results on varying backgrounds
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    
    # Optional: Apply morphological operations to clean up noise
    kernel = np.ones((1, 1), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    
    return binary


def ocr_page_image(image_array: np.ndarray, dpi: int = 150) -> Dict:
    """Perform OCR on a single page image array."""
    try:
        # Preprocess image
        processed_image = preprocess_image_for_ocr(image_array)
        
        # Configure Tesseract
        custom_config = r'--oem 3 --psm 6'
        
        # Get OCR data with confidence scores
        ocr_data = pytesseract.image_to_data(
            processed_image, 
            config=custom_config, 
            output_type=pytesseract.Output.DICT
        )
        
        # Extract text and calculate mean confidence
        text_parts = []
        confidences = []
        
        for i, conf in enumerate(ocr_data['conf']):
            if int(conf) > 0:  # Only include confident detections
                text = ocr_data['text'][i].strip()
                if text:
                    text_parts.append(text)
                    confidences.append(int(conf))
        
        # Combine text and calculate statistics
        full_text = ' '.join(text_parts)
        mean_confidence = sum(confidences) / len(confidences) if confidences else 0
        
        return {
            "text": full_text,
            "mean_conf": round(mean_confidence, 2),
            "word_count": len(text_parts),
            "engine": "tesseract"
        }
    
    except Exception as e:
        return {
            "text": "",
            "mean_conf": 0.0,
            "word_count": 0,
            "engine": "tesseract",
            "error": str(e)
        }


def ocr_pdf_pages(pdf_path: str, dpi: int = 150) -> List[Dict]:
    """Perform OCR on all pages of a PDF."""
    doc = fitz.open(pdf_path)
    ocr_results = []
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        
        # Render page to image
        mat = fitz.Matrix(dpi/72, dpi/72)  # Scale factor for DPI
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to numpy array
        img_data = pix.tobytes("png")
        
        # Use OpenCV to decode the image
        img_array = cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_COLOR)
        
        # Perform OCR
        ocr_result = ocr_page_image(img_array, dpi)
        ocr_result["page"] = page_num + 1
        
        ocr_results.append(ocr_result)
    
    doc.close()
    return ocr_results


def is_ocr_enabled() -> bool:
    """Check if OCR is enabled via environment variable."""
    return os.getenv("OCR_ENABLED", "false").lower() == "true"
from typing import List, Dict
import cv2
import pytesseract
import numpy as np
from pathlib import Path

def process_page_ocr(page_image: np.ndarray, page_num: int) -> Dict:
    """Process a single page image with OCR"""
    try:
        # Convert to grayscale if needed
        if len(page_image.shape) == 3:
            gray = cv2.cvtColor(page_image, cv2.COLOR_BGR2GRAY)
        else:
            gray = page_image
        
        # Apply thresholding to improve OCR accuracy
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Perform OCR
        custom_config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(thresh, config=custom_config)
        
        # Get confidence data
        data = pytesseract.image_to_data(thresh, output_type=pytesseract.Output.DICT)
        confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
        mean_conf = sum(confidences) / len(confidences) if confidences else 0
        
        return {
            "page": page_num,
            "text": text.strip(),
            "mean_conf": mean_conf,
            "word_count": len(text.split())
        }
    except Exception as e:
        print(f"OCR error on page {page_num}: {e}")
        return {
            "page": page_num,
            "text": "",
            "mean_conf": 0,
            "word_count": 0
        }

def extract_ocr_from_pdf(pdf_path: str) -> List[Dict]:
    """Extract OCR text from all pages of a PDF"""
    import fitz  # PyMuPDF
    
    results = []
    doc = fitz.open(pdf_path)
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # Convert page to image
        pix = page.get_pixmap(dpi=150)  # Use 150 DPI for OCR
        img_data = pix.tobytes("png")
        
        # Convert to OpenCV format
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Process with OCR
        ocr_result = process_page_ocr(img, page_num + 1)
        results.append(ocr_result)
    
    doc.close()
    return results
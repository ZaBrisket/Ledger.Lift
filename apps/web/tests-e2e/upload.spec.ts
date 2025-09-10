import { test, expect } from '@playwright/test';
import path from 'path';

test.describe('Upload Flow', () => {
  test('should upload PDF and show success message', async ({ page }) => {
    // Navigate to home page
    await page.goto('/');

    // Check page loads correctly
    await expect(page.locator('h1')).toContainText('Ledger Lift');
    await expect(page.locator('input[type="file"]')).toBeVisible();

    // Check initial status
    await expect(page.locator('text=Idle')).toBeVisible();

    // Upload a PDF file (using the sample PDF from fixtures)
    const fileInput = page.locator('input[type="file"]');
    const samplePdfPath = path.join(__dirname, '../../..', 'tests/fixtures/sample.pdf');
    
    // Mock the API responses for testing
    await page.route('**/v1/uploads/presign', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          key: 'raw/test-key-sample.pdf',
          url: 'http://localhost:9000/test-presign-url'
        })
      });
    });

    await page.route('http://localhost:9000/test-presign-url', async route => {
      await route.fulfill({
        status: 200,
        body: 'OK'
      });
    });

    await page.route('**/v1/documents', async route => {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'test-document-id-12345',
          s3_key: 'raw/test-key-sample.pdf',
          original_filename: 'sample.pdf'
        })
      });
    });

    // Set the file
    await fileInput.setInputFiles(samplePdfPath);

    // Wait for upload process to complete
    await expect(page.locator('text=Presigning…')).toBeVisible();
    await expect(page.locator('text=Uploading…')).toBeVisible();
    await expect(page.locator('text=Registering…')).toBeVisible();
    await expect(page.locator('text=Done')).toBeVisible();

    // Check success message appears
    await expect(page.locator('text=Document Registered Successfully!')).toBeVisible();
    await expect(page.locator('code')).toContainText('test-document-id-12345');

    // Check download and review buttons are present
    await expect(page.locator('a:has-text("Download Excel")')).toBeVisible();
    await expect(page.locator('a:has-text("Review & Edit")')).toBeVisible();

    // Verify the download link points to the correct URL
    const downloadLink = page.locator('a:has-text("Download Excel")');
    await expect(downloadLink).toHaveAttribute('href', 'http://localhost:8000/v1/documents/test-document-id-12345/export.xlsx');

    // Verify the review link points to the correct URL  
    const reviewLink = page.locator('a:has-text("Review & Edit")');
    await expect(reviewLink).toHaveAttribute('href', '/review/test-document-id-12345');
  });

  test('should handle upload error gracefully', async ({ page }) => {
    await page.goto('/');

    // Mock API error response
    await page.route('**/v1/uploads/presign', async route => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Server error' })
      });
    });

    const fileInput = page.locator('input[type="file"]');
    const samplePdfPath = path.join(__dirname, '../../..', 'tests/fixtures/sample.pdf');
    
    await fileInput.setInputFiles(samplePdfPath);

    // Should show error message
    await expect(page.locator('text=Error:')).toBeVisible();
  });

  test('should navigate to review page', async ({ page }) => {
    // Go to a review page directly
    await page.goto('/review/test-doc-id');

    // Should show the review interface
    await expect(page.locator('h4:has-text("Document Review")')).toBeVisible();
    await expect(page.locator('text=Document ID: test-doc-id')).toBeVisible();
    await expect(page.locator('text=Preview')).toBeVisible();
    await expect(page.locator('text=Table Editor')).toBeVisible();
  });
});
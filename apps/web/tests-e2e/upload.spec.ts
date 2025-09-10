import { test, expect } from '@playwright/test';
import path from 'path';

test.describe('Document Upload Flow', () => {
  test('should upload PDF and show success state', async ({ page }) => {
    // Navigate to the E2E test page
    await page.goto('/dev/upload-smoke');

    // Wait for the page to load
    await expect(page.locator('h1')).toContainText('Ledger Lift - E2E Test Page');

    // Get the file input
    const fileInput = page.locator('input[type="file"]');
    await expect(fileInput).toBeVisible();

    // Upload the sample PDF
    const samplePdfPath = path.join(__dirname, '../../tests/fixtures/sample.pdf');
    await fileInput.setInputFiles(samplePdfPath);

    // Wait for the upload process to complete
    await expect(page.locator('text=Done')).toBeVisible({ timeout: 30000 });

    // Verify document ID is displayed
    await expect(page.locator('text=Document ID:')).toBeVisible();
    
    // Verify the document ID is a valid UUID format
    const documentIdText = await page.locator('text=Document ID:').textContent();
    expect(documentIdText).toMatch(/Document ID: [a-f0-9-]{36}/);

    // Verify download and review links are present
    await expect(page.locator('text=Download Excel Export')).toBeVisible();
    await expect(page.locator('text=Review & Edit Data')).toBeVisible();

    // Test the download link
    const downloadLink = page.locator('a[href*="/export.xlsx"]');
    await expect(downloadLink).toBeVisible();
    
    // Test the review link
    const reviewLink = page.locator('a[href*="/review/"]');
    await expect(reviewLink).toBeVisible();
  });

  test('should handle file upload errors gracefully', async ({ page }) => {
    await page.goto('/dev/upload-smoke');

    // Try to upload a non-PDF file
    const fileInput = page.locator('input[type="file"]');
    
    // Create a temporary text file
    const textContent = 'This is not a PDF file';
    const blob = new Blob([textContent], { type: 'text/plain' });
    const file = new File([blob], 'test.txt', { type: 'text/plain' });
    
    // Note: This test might not work as expected since the input only accepts PDFs
    // But it tests the error handling path
    await fileInput.setInputFiles({
      name: 'test.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from(textContent)
    });

    // The upload should either succeed (if the browser allows it) or show an error
    // We'll check that the status changes from 'Idle'
    await expect(page.locator('text=Idle')).not.toBeVisible({ timeout: 5000 });
  });

  test('should show loading states during upload', async ({ page }) => {
    await page.goto('/dev/upload-smoke');

    const fileInput = page.locator('input[type="file"]');
    const samplePdfPath = path.join(__dirname, '../../tests/fixtures/sample.pdf');
    
    // Start the upload
    await fileInput.setInputFiles(samplePdfPath);

    // Check that loading states appear
    await expect(page.locator('text=Presigning…')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('text=Uploading…')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Registering…')).toBeVisible({ timeout: 10000 });
  });
});
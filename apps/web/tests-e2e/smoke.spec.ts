import { test, expect } from '@playwright/test';
import path from 'path';

test.describe('Smoke Tests', () => {
  test('dev upload smoke test', async ({ page }) => {
    // Navigate to dev smoke test page
    await page.goto('/dev/upload-smoke');

    // Check page loads
    await expect(page.locator('h1')).toContainText('Upload Smoke Test');
    await expect(page.getByTestId('file-input')).toBeVisible();
    await expect(page.getByTestId('status')).toContainText('Ready');

    // Upload a file
    const fileInput = page.getByTestId('file-input');
    const samplePdfPath = path.join(__dirname, '../../..', 'tests/fixtures/sample.pdf');
    
    await fileInput.setInputFiles(samplePdfPath);

    // Wait for processing
    await expect(page.getByTestId('status')).toContainText('Processing...');
    
    // Wait for completion
    await expect(page.getByTestId('status')).toContainText('Done', { timeout: 10000 });

    // Check success message
    await expect(page.getByTestId('success-message')).toBeVisible();
    await expect(page.getByTestId('doc-id')).toContainText('smoke-test-');
    await expect(page.getByTestId('done-button')).toBeVisible();
  });

  test('homepage loads correctly', async ({ page }) => {
    await page.goto('/');
    
    // Check basic page elements
    await expect(page.locator('h1')).toContainText('Ledger Lift');
    await expect(page.locator('input[type="file"]')).toBeVisible();
    await expect(page.locator('text=Idle')).toBeVisible();
  });

  test('review page loads correctly', async ({ page }) => {
    await page.goto('/review/test-doc-123');
    
    // Check review page elements
    await expect(page.locator('text=Document Review')).toBeVisible();
    await expect(page.locator('text=Document ID: test-doc-123')).toBeVisible();
  });
});
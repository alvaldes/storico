import { test, expect } from '@playwright/test';

test.describe('Few-Shot Examples in Workspace Settings', () => {
  test.beforeEach(async ({ page }) => {
    // Login as admin (assuming test setup provides authenticated session)
    await page.goto('/login');
    await page.click('text=Sign in with Google'); // or GitHub
    // Wait for redirect to dashboard
    await page.waitForURL('/dashboard');
  });

  test('Admin can add 3 few-shot examples and verify in API response', async ({ page }) => {
    // Navigate to workspace settings
    await page.goto('/workspaces/ws-test/settings');
    
    // Wait for settings to load
    await expect(page.locator('text=Workspace Settings')).toBeVisible();
    
    // Click on LLM Config tab if needed
    const llmConfigTab = page.locator('text=LLM Configuration');
    if (await llmConfigTab.isVisible()) {
      await llmConfigTab.click();
    }

    // Add first example
    await page.click('text=Add Example');
    await page.fill('textarea[placeholder*="As a user"]', 'As a user, I want to log in so that I can access my account');
    await page.fill('textarea[placeholder*="1. summary:"]', '1. summary: Set up auth database schema\ndescription: Create tables for users, sessions, and password hashes with proper indexes.\n\n2. summary: Implement login API endpoint\ndescription: Build POST /auth/login endpoint that validates credentials and returns JWT token.\n\n3. summary: Build login UI component\ndescription: Create React form with email/password fields, validation, and error handling.');

    // Add second example
    await page.click('text=Add Example');
    await page.fill('textarea[placeholder*="As a user"] >> nth=1', 'As a user, I want to reset my password so that I can regain access');
    await page.fill('textarea[placeholder*="1. summary:"] >> nth=1', '1. summary: Create password reset token model\ndescription: Add database table for reset tokens with expiration.\n\n2. summary: Implement forgot password endpoint\ndescription: Build POST /auth/forgot-password that sends reset email.\n\n3. summary: Build reset password page\ndescription: Create page with token validation and new password form.');

    // Add third example
    await page.click('text=Add Example');
    await page.fill('textarea[placeholder*="As a user"] >> nth=2', 'As an admin, I want to manage users so that I can control access');
    await page.fill('textarea[placeholder*="1. summary:"] >> nth=2', '1. summary: Create user management API\ndescription: Build CRUD endpoints for user administration.\n\n2. summary: Build admin dashboard\ndescription: Create React dashboard with user table, search, and pagination.\n\n3. summary: Implement role-based access\ndescription: Add middleware for admin/member permissions.');

    // Save prompts
    await page.click('text=Save Prompt Configuration');
    
    // Verify toast success
    await expect(page.locator('text=Prompt configuration saved')).toBeVisible();

    // Verify API returns the examples
    const response = await page.request.get('/api/v1/workspaces/ws-test/settings/prompts');
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.few_shot_examples).toHaveLength(3);
    expect(data.few_shot_examples[0].user_story).toContain('log in');
    expect(data.few_shot_examples[1].user_story).toContain('reset my password');
    expect(data.few_shot_examples[2].user_story).toContain('manage users');
  });

  test('Max 3 examples enforced - add button disabled', async ({ page }) => {
    await page.goto('/workspaces/ws-test/settings');
    
    // Add 3 examples
    for (let i = 0; i < 3; i++) {
      await page.click('text=Add Example');
      await page.fill(`textarea[placeholder*="As a user"] >> nth=${i}`, `Example ${i} user story with enough characters`);
      await page.fill(`textarea[placeholder*="1. summary:"] >> nth=${i}`, `1. summary: Task ${i}\ndescription: Description for task ${i} with sufficient length.`);
    }

    // Try to add 4th - button should be disabled
    const addButton = page.locator('text=Add Example');
    await expect(addButton).toBeDisabled();
    
    // Verify max reached message
    await expect(page.locator('text=Maximum of 3 few-shot examples reached')).toBeVisible();
  });

  test('Validation prevents empty save - errors shown', async ({ page }) => {
    await page.goto('/workspaces/ws-test/settings');
    
    // Click Add Example but leave fields empty
    await page.click('text=Add Example');
    
    // Try to save without filling fields
    await page.click('text=Save Prompt Configuration');
    
    // Verify validation errors appear
    await expect(page.locator('text=User Story must be at least 10 characters')).toBeVisible();
    await expect(page.locator('text=Tasks must be at least 20 characters')).toBeVisible();
    
    // Verify save is blocked (toast error or button still enabled but no success toast)
    await expect(page.locator('text=Fix validation errors before saving')).toBeVisible();
  });

  test('Reorder changes example order', async ({ page }) => {
    await page.goto('/workspaces/ws-test/settings');
    
    // Add 2 examples
    await page.click('text=Add Example');
    await page.fill('textarea[placeholder*="As a user"]', 'First example user story');
    await page.fill('textarea[placeholder*="1. summary:"]', '1. summary: First task\ndescription: First task description here.');
    
    await page.click('text=Add Example');
    await page.fill('textarea[placeholder*="As a user"] >> nth=1', 'Second example user story');
    await page.fill('textarea[placeholder*="1. summary:"] >> nth=1', '1. summary: Second task\ndescription: Second task description here.');
    
    // Move second example up (click up arrow on second example)
    const moveUpButtons = page.locator('button[aria-label="Move up"]');
    await moveUpButtons.nth(1).click();
    
    // Save
    await page.click('text=Save Prompt Configuration');
    await expect(page.locator('text=Prompt configuration saved')).toBeVisible();
    
    // Verify API returns reordered examples
    const response = await page.request.get('/api/v1/workspaces/ws-test/settings/prompts');
    const data = await response.json();
    expect(data.few_shot_examples[0].user_story).toContain('Second example');
    expect(data.few_shot_examples[1].user_story).toContain('First example');
  });

  test('Remove example works', async ({ page }) => {
    await page.goto('/workspaces/ws-test/settings');
    
    // Add 2 examples
    await page.click('text=Add Example');
    await page.fill('textarea[placeholder*="As a user"]', 'Example to keep');
    await page.fill('textarea[placeholder*="1. summary:"]', '1. summary: Keep task\ndescription: This task should remain.');
    
    await page.click('text=Add Example');
    await page.fill('textarea[placeholder*="As a user"] >> nth=1', 'Example to remove');
    await page.fill('textarea[placeholder*="1. summary:"] >> nth=1', '1. summary: Remove task\ndescription: This task should be removed.');
    
    // Remove second example
    const removeButtons = page.locator('button[aria-label="Remove example"]');
    await removeButtons.nth(1).click();
    
    // Save
    await page.click('text=Save Prompt Configuration');
    await expect(page.locator('text=Prompt configuration saved')).toBeVisible();
    
    // Verify only 1 example remains
    const response = await page.request.get('/api/v1/workspaces/ws-test/settings/prompts');
    const data = await response.json();
    expect(data.few_shot_examples).toHaveLength(1);
    expect(data.few_shot_examples[0].user_story).toContain('Example to keep');
  });

  test('Format hint visible in tasks textarea', async ({ page }) => {
    await page.goto('/workspaces/ws-test/settings');
    
    await page.click('text=Add Example');
    
    const tasksTextarea = page.locator('textarea[placeholder*="1. summary:"]');
    await expect(tasksTextarea).toHaveAttribute('placeholder', /1\. summary:/);
  });

  test('Spanish locale shows translated labels', async ({ page }) => {
    await page.goto('/es/workspaces/ws-test/settings');
    
    await expect(page.locator('text=Ejemplos Few-Shot')).toBeVisible();
    await expect(page.locator('text=Historia de Usuario')).toBeVisible();
    await expect(page.locator('text=Salida de Tareas Esperada')).toBeVisible();
    await expect(page.locator('text=Agregar Ejemplo')).toBeVisible();
  });
});
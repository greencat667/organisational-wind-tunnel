import { test, expect } from '@playwright/test'

test('first visit offers the tour, it walks every step, and its demo starts time running', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('.boot')).toHaveCount(0, { timeout: 180_000 })
  await expect(page.getByText('Take the one-minute tour')).toBeVisible({ timeout: 30_000 })
  await page.getByRole('button', { name: 'Take the one-minute tour' }).click()
  for (let i = 1; i < 8; i++) {
    await expect(page.locator('.tour-count')).toHaveText(`${i} / 8`)
    await page.getByRole('button', { name: 'Next' }).click()
  }
  await page.getByRole('button', { name: 'Set up the demo' }).click()
  await expect(page.getByText('INTERPRETED CHANGE')).toBeVisible({ timeout: 30_000 })
  await page.getByRole('button', { name: 'RUN EXPERIMENT' }).click()
  await expect(page.getByText('Time is running')).toBeVisible({ timeout: 30_000 })
  const t0 = await page.locator('.clock').innerText()
  await expect(page.locator('.clock')).not.toHaveText(t0, { timeout: 60_000 })   // time moves without pressing anything
  // offered only once
  await page.reload()
  await expect(page.locator('.boot')).toHaveCount(0, { timeout: 180_000 })
  await page.waitForTimeout(3_000)
  await expect(page.getByText('Take the one-minute tour')).toHaveCount(0)
})

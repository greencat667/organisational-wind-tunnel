import { test, expect } from '@playwright/test'

test('static build: boots Python in the browser, runs an intervention, a batch, and persists a save', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })

  await page.goto('/')
  await expect(page.locator('.boot')).toHaveCount(0, { timeout: 180_000 })     // Pyodide + the simulator loaded
  await expect(page.locator('canvas')).toHaveCount(1)
  await expect(page.locator('.clock')).toContainText('2027', { timeout: 30_000 })

  // interpret and run the admin cut
  await page.getByPlaceholder(/Describe a change/).fill('Reduce administrative capacity by 20% while protecting frontline delivery.')
  await page.getByRole('button', { name: 'SIMULATE CHANGE' }).click()
  await expect(page.getByText(/Remove \d+ posts/)).toBeVisible({ timeout: 30_000 })
  await page.getByRole('button', { name: 'RUN EXPERIMENT' }).click()
  await expect(page.getByRole('button', { name: 'discard' })).toBeVisible({ timeout: 30_000 })

  // advance six months in the browser and see effects
  const before = await page.locator('.clock').innerText()
  await page.getByRole('button', { name: '+6 mo' }).click()
  await expect(page.locator('.clock')).not.toHaveText(before, { timeout: 120_000 })
  await page.waitForTimeout(8_000)
  await page.getByRole('button', { name: 'Effects' }).click()
  await expect(page.getByText(/order|No material divergence/).first()).toBeVisible({ timeout: 30_000 })

  // a small batch across the worker pool
  await page.getByRole('button', { name: 'Many worlds' }).click()
  await page.locator('.side.left input[type=number]').first().fill('3')
  await page.locator('.side.left input[type=number]').nth(1).fill('12')
  await page.getByRole('button', { name: /RUN 3 ORGANISATIONS/ }).click()
  await expect(page.getByText('Outcome frequencies')).toBeVisible({ timeout: 300_000 })

  // save, reload, and find it again (IndexedDB)
  await page.getByRole('button', { name: 'Saved' }).click()
  await page.getByRole('button', { name: 'save experiment' }).click()
  await page.waitForTimeout(2_000)
  await page.reload()
  await expect(page.locator('.boot')).toHaveCount(0, { timeout: 180_000 })
  await page.getByRole('button', { name: 'Saved' }).click()
  await expect(page.getByText(/Reduce administrative capacity/).first()).toBeVisible({ timeout: 30_000 })

  expect(errors.filter((e) => !/favicon/i.test(e))).toEqual([])
})

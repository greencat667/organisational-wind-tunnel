import { test, expect, type Page } from '@playwright/test'

// Walks the critical demo and saves one screenshot per step for docs/GUIDE.md. Seed 6 is used because, in that world,
// the admin cut produces a Finance bottleneck, work spilling into Technology and stress in the protected frontline team.
// Run with the Apple model off so the dialogs show the default rules-only path: `npm run docs:screenshots`.
const OUT = '../docs/images'
const ADMIN_CUT = 'Reduce administrative capacity by 20% while maintaining existing frontline delivery.'

async function shot(page: Page, name: string, settle = 1500) {
  await page.waitForTimeout(settle)          // let the 3D scene and animations settle
  await page.screenshot({ path: `${OUT}/${name}.png` })
}

/** Advance the live simulation through the API and wait until the page's clock has caught up. */
async function advance(page: Page, request: any, steps: number) {
  const st = await (await request.post('/api/play', { data: { steps } })).json()
  try {
    await expect(page.locator('.clock')).toContainText(st.label, { timeout: 20_000 })
  } catch {
    // the live connection can drop during a long jump; the state is on the server, so a reload catches up
    await page.reload()
    await expect(page.locator('.clock')).toContainText(st.label, { timeout: 30_000 })
  }
}

/** Reload (state lives on the server) so the camera returns to the overview after an inspector zoomed it in. */
async function resetView(page: Page) {
  await page.reload()
  await expect(page.locator('canvas')).toHaveCount(1)
  await page.waitForTimeout(1500)
}

async function interpret(page: Page, text: string) {
  await page.getByPlaceholder(/Describe a change/).fill(text)
  await page.getByRole('button', { name: 'SIMULATE CHANGE' }).click()
  await expect(page.getByText('INTERPRETED CHANGE')).toBeVisible({ timeout: 20_000 })
  await expect(page.getByText(/asking the Apple/)).toHaveCount(0, { timeout: 45_000 })   // wait for the model's reading (or its absence)
}

test('guide screenshots', async ({ page, request }) => {
  await page.addInitScript(() => { try { localStorage.setItem('windtunnel.tourSeen', '1') } catch {} })   // skip the first-visit tour offer
  expect((await request.post('/api/experiment', { data: { template: 'prototype', seed: 6, engine: 'heuristic', settle_months: 3 } })).ok()).toBeTruthy()
  await page.goto('/')
  await expect(page.locator('canvas')).toHaveCount(1)
  await advance(page, request, 6)
  await shot(page, '01-overview', 3000)

  // a request the parser only partly takes as a change: shows multiple clauses and a constraint warning
  await interpret(page, "Cut admin by 20% and hire 5 people into technology, but don't cut frontline")
  await shot(page, '03-interpret-warnings')
  await page.getByRole('button', { name: 'CANCEL' }).click()
  // a request it can't model at all: nothing to run
  await interpret(page, 'Outsource payroll to a shared-service provider')
  await shot(page, '04-interpret-unsupported')
  await page.getByRole('button', { name: 'CANCEL' }).click()

  await interpret(page, ADMIN_CUT)
  await shot(page, '02-interpret')
  await page.getByRole('button', { name: 'RUN EXPERIMENT' }).click()
  await expect(page.getByRole('button', { name: 'discard' })).toBeVisible({ timeout: 10_000 })
  await page.getByRole('button', { name: 'Dismiss' }).click()          // the "time is running" note
  await advance(page, request, 36)
  await page.getByTitle('Hide panel').click()          // give the split view the full width
  await shot(page, '05-split', 3000)

  await page.getByRole('button', { name: 'difference' }).click()
  await shot(page, '06-difference', 2500)
  await page.getByRole('button', { name: 'split' }).click()
  await page.getByTitle('Show panel').click()

  await page.getByRole('button', { name: 'Effects' }).click()
  await expect(page.getByText(/second order/)).toBeVisible({ timeout: 20_000 })
  await shot(page, '07-effects')

  // click the strongest team backlog effect (whichever team it lands on in this build): WHY chain + team inspector
  await page.locator('.list-btn', { hasText: /· backlog months/ }).first().click()
  await expect(page.getByText(/Why did this happen/i)).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('tracing…')).toHaveCount(0, { timeout: 15_000 })
  await shot(page, '08-why', 2500)

  // team inspector → an employee
  await page.getByRole('button', { name: '×' }).first().click()
  await page.waitForTimeout(800)
  await shot(page, '09-team-inspector', 1500)
  await page.locator('.side.right .row[style*="cursor: pointer"]').first().click()
  await shot(page, '10-employee-inspector', 2000)
  await page.keyboard.press('Escape')
  await resetView(page)

  // x-ray: capacity
  await page.getByRole('button', { name: 'capacity', exact: true }).click()
  await shot(page, '11-xray-capacity', 2500)
  // cost view: one world, panel hidden, zoomed in so the towers and labels are legible
  await page.getByRole('button', { name: 'cost', exact: true }).click()
  await page.getByRole('button', { name: 'single' }).click()
  await page.getByTitle('Hide panel').click()
  await page.mouse.move(720, 330)
  for (let i = 0; i < 6; i++) { await page.mouse.wheel(0, -300); await page.waitForTimeout(100) }
  await shot(page, '16-xray-cost', 3000)
  await page.getByTitle('Show panel').click()
  await page.getByRole('button', { name: 'split' }).click()
  await resetView(page)
  await page.getByRole('button', { name: 'work', exact: true }).click()

  // many worlds
  await page.getByRole('button', { name: 'Many worlds' }).click()
  await page.locator('.side.left .panel h3 button', { hasText: 'Many worlds' }).waitFor()
  await page.locator('.side.left input[type=number]').first().fill('48')
  await page.getByRole('button', { name: /RUN \d+ ORGANISATIONS/ }).click()
  await expect(page.getByText('Outcome frequencies')).toBeVisible({ timeout: 240_000 })
  await shot(page, '12-many-worlds', 1000)
  await page.locator('.side.left .panel').evaluate((el) => el.scrollTo(0, el.scrollHeight))
  await shot(page, '13-many-worlds-surprises', 800)

  // saved / new experiment
  await page.getByRole('button', { name: 'Saved' }).click()
  await shot(page, '14-saved', 1000)

  // developer diagnostics
  await page.getByRole('button', { name: 'dev' }).click()
  await shot(page, '15-dev-panel', 2000)
})

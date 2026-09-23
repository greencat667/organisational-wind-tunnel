import { test, expect } from '@playwright/test'

test('loads, interprets, runs an intervention, advances and reports effects', async ({ page, request }) => {
  await page.addInitScript(() => { try { localStorage.setItem('windtunnel.tourSeen', '1') } catch {} })   // skip the first-visit tour offer
  const health = await request.get('/api/health')
  expect(health.ok()).toBeTruthy()

  // fresh experiment so the test is independent of whatever the UI was showing
  const fresh = await request.post('/api/experiment', { data: { template: 'prototype', seed: 7, engine: 'heuristic', settle_months: 3 } })
  expect(fresh.ok()).toBeTruthy()

  await page.goto('/')
  await expect(page.locator('canvas')).toHaveCount(1)
  await expect(page.locator('.brand')).toContainText('WIND TUNNEL')

  // type the intervention and open the interpreted-change modal (rule-based reading appears immediately)
  await page.getByPlaceholder(/Describe a change/).fill('Reduce administrative capacity by 20% while protecting frontline delivery.')
  await page.getByRole('button', { name: 'SIMULATE CHANGE' }).click()
  await expect(page.getByText('INTERPRETED CHANGE')).toBeVisible({ timeout: 20_000 })
  await expect(page.getByText(/Remove \d+ posts/)).toBeVisible()
  await page.getByRole('button', { name: 'RUN EXPERIMENT' }).click()
  await expect(page.getByRole('button', { name: 'discard' })).toBeVisible({ timeout: 10_000 })

  // advance 24 months through the API (deterministic), then check analysis endpoints
  const play = await request.post('/api/play', { data: { steps: 24 } })
  expect(play.ok()).toBeTruthy()
  const status = await play.json()
  expect(status.forked).toBeTruthy()
  expect(status.month).toBeGreaterThanOrEqual(27)

  const effects = await (await request.get('/api/effects?min_effect=0.5')).json()
  expect(Array.isArray(effects.effects)).toBeTruthy()
  expect(effects.targets).toContain('finance')
  const withEvent = effects.effects.find((e: any) => e.event_id != null)
  if (withEvent) {
    const why = await (await request.get(`/api/why/intervention/${withEvent.event_id}`)).json()
    expect(why.chain.length).toBeGreaterThan(0)
  }

  // UI reflects the advanced state: effects tab lists something or says no divergence yet
  await page.getByRole('button', { name: 'Effects' }).click()
  await expect(page.getByText(/order|No material divergence/).first()).toBeVisible({ timeout: 15_000 })

  // inspectors respond
  const team = await (await request.get('/api/team/intervention/finance')).json()
  expect(team.team.name).toBe('Finance')
  const emp = await (await request.get(`/api/employee/intervention/${team.members[0].id}`)).json()
  expect(emp.employee).toHaveProperty('assigned_hours')

  const diag = await (await request.get('/api/diagnostics')).json()
  expect(diag.status.engine).toBe('heuristic')
})

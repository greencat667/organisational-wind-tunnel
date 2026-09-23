import { useEffect, useLayoutEffect, useState } from 'react'
import { useStore } from '../lib/store'

// Optional first-visit guided tour. A welcome card offers it once (remembered in this browser); the "tour" button in
// the top bar replays it. Each step spotlights a real part of the interface; the last can set up the demo for you.
const SEEN_KEY = 'windtunnel.tourSeen'
const DEMO = 'Reduce administrative capacity by 20% while maintaining existing frontline delivery.'

interface Step { sel: string; title: string; body: string }
const STEPS: Step[] = [
  { sel: '.canvas-wrap', title: 'A living organisation',
    body: 'A synthetic organisation of 100 people in eight teams, running month by month. Each figure is one person with their own workload, stress and morale; the dots moving between teams are real pieces of work, and the stacks beside teams are their queues. Drag to rotate, scroll to zoom, click a team or a person to inspect them.' },
  { sel: '.side.left', title: 'What\'s happening, and why',
    body: 'The timeline lists significant events as they happen — resignations, bottlenecks, habits becoming normal. Click any event to trace why it happened. Once you\'ve tested a change, Effects lists what diverged from the baseline, and Many worlds runs the same change across dozens of organisations.' },
  { sel: '.metrics', title: 'Vital signs',
    body: 'Delivery, backlog, cost, workload, stress, turnover and more, each with a trend line. After you test a change, each tile shows two numbers: the baseline (blue) and your change (amber), with the difference underneath.' },
  { sel: '.prompt', title: 'Describe a change',
    body: 'Type a change in plain English — "Cut admin by 20%", "Hire 10 people into technology", "Automate the back end over a year" — then press SIMULATE CHANGE. You\'ll see exactly how it was interpreted before anything runs.' },
  { sel: '.scenarios', title: 'Or pick a scenario',
    body: 'Ready-made changes to try, from an admin cut to AI adoption. Clicking one fills in the box above.' },
  { sel: '.scrubber', title: 'Time',
    body: 'When you run an experiment, time starts moving on its own. ▶ / ❚❚ plays and pauses, +3 yrs jumps ahead, and the speed buttons change the pace. Drag the slider back to replay any month.' },
  { sel: '.topbar .controls', title: 'Ways of looking',
    body: 'Switch what the world emphasises — work, information, capacity, cost, change. Once a change is running, split shows the baseline and your change side by side, and difference rings the teams that diverged most.' },
  { sel: '.canvas-wrap', title: 'Try it',
    body: 'The classic first experiment: cut admin by 20% while protecting frontline delivery, then watch where the pressure goes. Two years on, look at Effects — the protected frontline team is often where it lands.' },
]

function seen(): boolean {
  try { return localStorage.getItem(SEEN_KEY) === '1' } catch { return true }   // no storage: never nag
}
function markSeen() {
  try { localStorage.setItem(SEEN_KEY, '1') } catch { /* private window etc. */ }
}

export function TourHost() {
  const tour = useStore((s) => s.tour)
  const ready = useStore((s) => !!s.status)
  const set = useStore((s) => s.set)
  useEffect(() => { if (ready && tour === 'off' && !seen()) set({ tour: 'welcome' }) }, [ready])
  if (tour === 'off') return null
  if (tour === 'welcome') return <Welcome />
  return <TourStep index={tour} />
}

function Welcome() {
  const set = useStore((s) => s.set)
  const close = () => { markSeen(); set({ tour: 'off' }) }
  return (
    <div className="tour-welcome">
      <div className="brand"><b>ORGANISATIONAL</b> WIND TUNNEL</div>
      <p>Test a change to an organisation and see what it does — including the knock-on effects nobody planned for.</p>
      <div className="actions">
        <button className="btn ghost" onClick={close}>Skip</button>
        <button className="btn primary" onClick={() => { markSeen(); set({ tour: 0 }) }}>Take the one-minute tour</button>
      </div>
    </div>
  )
}

function TourStep({ index }: { index: number }) {
  const set = useStore((s) => s.set)
  const step = STEPS[index]
  const [rect, setRect] = useState<DOMRect | null>(null)
  useLayoutEffect(() => {
    const measure = () => {
      const el = document.querySelector(step.sel) as HTMLElement | null
      setRect(el ? el.getBoundingClientRect() : null)
    }
    measure()
    window.addEventListener('resize', measure)
    const t = window.setInterval(measure, 500)          // panels resize as data arrives
    return () => { window.removeEventListener('resize', measure); clearInterval(t) }
  }, [index])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const go = (i: number) => { e.stopPropagation(); e.preventDefault(); set({ tour: i }) }
      if (e.key === 'Escape') { e.stopPropagation(); set({ tour: 'off' }) }
      if (e.key === 'ArrowRight' && index < STEPS.length - 1) go(index + 1)
      if (e.key === 'ArrowLeft' && index > 0) go(index - 1)
    }
    // capture phase: the 3D camera controls use the arrow keys for panning and would otherwise swallow them
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [index])
  const last = index === STEPS.length - 1
  const full = step.sel === '.canvas-wrap'
  const pad = 6
  const box = rect && !full ? { left: rect.left - pad, top: rect.top - pad, width: rect.width + 2 * pad, height: rect.height + 2 * pad } : null
  // put the card beside the highlighted area, on whichever side has room
  const card: React.CSSProperties = { width: 360 }
  if (!box) { card.left = '50%'; card.top = '50%'; card.transform = 'translate(-50%, -50%)' }
  else if (box.top > window.innerHeight / 2) { card.left = Math.max(16, Math.min(box.left, window.innerWidth - 376)); card.bottom = window.innerHeight - box.top + 12 }
  else if (box.left + box.width + 390 < window.innerWidth) { card.left = box.left + box.width + 14; card.top = Math.max(16, box.top) }
  else { card.left = Math.max(16, Math.min(box.left, window.innerWidth - 376)); card.top = box.top + box.height + 12 }
  return (
    <div className="tour">
      {box ? <div className="tour-spot" style={box} /> : <div className="tour-dim" />}
      <div className="tour-card" style={card} role="dialog" aria-label={step.title}>
        <div className="tour-count">{index + 1} / {STEPS.length}</div>
        <h4>{step.title}</h4>
        <p>{step.body}</p>
        <div className="actions">
          <button className="btn ghost" onClick={() => set({ tour: 'off' })}>{last ? 'Explore on my own' : 'Skip tour'}</button>
          {index > 0 && <button className="btn" onClick={() => set({ tour: index - 1 })}>Back</button>}
          {!last && <button className="btn primary" onClick={() => set({ tour: index + 1 })}>Next</button>}
          {last && <button className="btn primary" onClick={() => set({ tour: 'off', pendingPrompt: DEMO })}>Set up the demo</button>}
        </div>
      </div>
    </div>
  )
}

/** Shown once an experiment starts running: what to watch, and how to take control of time. */
export function RunHint() {
  const hint = useStore((s) => s.runHint)
  const set = useStore((s) => s.set)
  useEffect(() => {
    if (!hint) return
    const t = window.setTimeout(() => set({ runHint: false }), 25000)
    return () => clearTimeout(t)
  }, [hint])
  if (!hint) return null
  return (
    <div className="run-hint" role="status">
      <button className="btn sm ghost close" aria-label="Dismiss" onClick={() => set({ runHint: false })}>×</button>
      <b>Time is running</b> — six months a second. Watch the paired tiles: <span style={{ color: 'var(--baseline)' }}>blue</span> is
      the baseline, <span style={{ color: 'var(--intervention)' }}>amber</span> is your change. After a year or two, open <b>Effects</b> (left) to
      see what diverged and click a row to ask why. <b>❚❚</b> pauses; <b>+3 yrs</b> jumps ahead.
    </div>
  )
}

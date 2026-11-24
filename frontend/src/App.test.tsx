import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { EstimateResult } from './types'

const estimate = (monthly: string, name = 'My estimate'): EstimateResult => ({
  name,
  currency: 'USD',
  monthly,
  yearly: (Number(monthly) * 12).toFixed(2),
  upfront: '0.00',
  first_12_months: (Number(monthly) * 12).toFixed(2),
  effective_monthly: monthly,
  price_list_dates: { 'ec2/ap-south-1': '2026-11-23' },
  assumptions: ['A month is 730 hours.'],
  items: [
    {
      name: 'EC2 instances',
      type: 'ec2',
      region: 'ap-south-1',
      summary: '1 x t3.medium (Linux), 2 vCPU, 4 GiB, On-Demand',
      monthly,
      upfront: '0.00',
      first_12_months: '0.00',
      effective_monthly: monthly,
      warnings: [],
      error: null,
      components: [{ label: 'EC2 t3.medium (Linux)', quantity: '1', unit: 'instances', monthly, upfront: '0.00', explain: ['1 instance(s) x 730 h x 0.0448 USD/h = 32.70 USD'] }],
    },
  ],
})

type Handler = (url: string, init?: RequestInit) => unknown

function mockApi(handlers: Record<string, Handler>) {
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      const key = Object.keys(handlers).find((k) => url.startsWith(k))
      if (!key) return new Response(JSON.stringify({ detail: `no mock for ${url}` }), { status: 500 })
      const out = handlers[key](url, init)
      if (out instanceof Response) return out
      return new Response(out === undefined ? null : JSON.stringify(out), { status: out === undefined ? 204 : 200 })
    }),
  )
  return calls
}

const baseHandlers: Record<string, Handler> = {
  '/api/meta': () => ({ regions: [{ region: 'ap-south-1', price_list_dates: { ec2: '2026-11-23' } }] }),
  '/api/catalog/ec2': () => ({
    region: 'ap-south-1',
    instances: [{ instance_type: 't3.medium', family: 'General purpose', vcpu: '2', memory: '4 GiB', network: 'Up to 5 Gigabit', current_generation: true, os: ['Linux', 'Windows'] }],
  }),
  '/api/catalog/s3': () => ({ storage_classes: [{ id: 'standard', label: 'S3 Standard' }] }),
  '/api/scenarios': () => [],
}

describe('App', () => {
  beforeEach(() => vi.useRealTimers())
  afterEach(() => vi.unstubAllGlobals())

  it('prompts for a service when the estimate is empty', async () => {
    mockApi(baseHandlers)
    render(<App />)
    expect(await screen.findByText(/Your estimate is empty/i)).toBeInTheDocument()
    expect(screen.getByText('Add a service to see your estimate.')).toBeInTheDocument()
  })

  it('adds an EC2 item and shows the server-computed total', async () => {
    const calls = mockApi({ ...baseHandlers, '/api/estimate': () => estimate('32.70') })
    const user = userEvent.setup()
    render(<App />)
    const addEc2 = await screen.findByRole('button', { name: '+ EC2' })
    await waitFor(() => expect(addEc2).toBeEnabled())
    await user.click(addEc2)

    const summary = screen.getByRole('complementary', { name: 'Estimate summary' })
    expect(await within(summary).findByText('$32.70')).toBeInTheDocument()

    const sent = calls.filter((c) => c.url === '/api/estimate').at(-1)!
    const body = JSON.parse(String(sent.init?.body))
    expect(body.items[0]).toMatchObject({ type: 'ec2', region: 'ap-south-1', instance_type: 't3.medium', quantity: 1 })
  })

  it('reveals the calculation steps for a line item', async () => {
    mockApi({ ...baseHandlers, '/api/estimate': () => estimate('32.70') })
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '+ EC2' }))
    await user.click(await screen.findByRole('button', { name: 'Show calculation' }))
    expect(screen.getByText('1 instance(s) x 730 h x 0.0448 USD/h = 32.70 USD')).toBeInTheDocument()
  })

  it('shows a per-item error from the API without breaking the page', async () => {
    const bad = estimate('0.00')
    bad.items[0].error = "ec2/ec2_instance: 'zz.large|Linux' is not available in ap-south-1"
    mockApi({ ...baseHandlers, '/api/estimate': () => bad })
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '+ EC2' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('zz.large')
  })

  it('shows validation errors returned as 422', async () => {
    mockApi({
      ...baseHandlers,
      '/api/estimate': () => new Response(JSON.stringify({ detail: [{ loc: ['body', 'items', 0, 'quantity'], msg: 'Input should be greater than or equal to 1' }] }), { status: 422 }),
    })
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '+ EC2' }))
    expect(await screen.findByText(/items > 0 > quantity: Input should be greater than or equal to 1/)).toBeInTheDocument()
  })

  it('saves an estimate and lists it', async () => {
    let saved: unknown[] = []
    const calls = mockApi({
      ...baseHandlers,
      '/api/estimate': () => estimate('32.70'),
      '/api/scenarios': (_url, init) => {
        if (init?.method === 'POST') {
          const s = { id: 'abc', name: 'My estimate', scenario: JSON.parse(String(init.body)), created_at: '2026-11-24T00:00:00Z', updated_at: '2026-11-24T00:00:00Z' }
          saved = [s]
          return s
        }
        return saved
      },
    })
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '+ EC2' }))
    await user.click(screen.getByRole('button', { name: 'Save estimate' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Saved “My estimate”')
    expect(calls.some((c) => c.init?.method === 'POST' && c.url === '/api/scenarios')).toBe(true)
    expect(await screen.findByRole('button', { name: 'Saved (1)' })).toBeInTheDocument()
  })

  it('tells the user when the backend is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'Internal Server Error' }), { status: 500 })))
    render(<App />)
    expect(await screen.findByText(/Could not reach the API/)).toBeInTheDocument()
  })
})

describe('App: Savings Plans, data transfer, rightsizing', () => {
  beforeEach(() => vi.useRealTimers())
  afterEach(() => vi.unstubAllGlobals())

  it('can switch an EC2 item to a Savings Plan and sends the plan options', async () => {
    const calls = mockApi({ ...baseHandlers, '/api/estimate': () => estimate('51.83') })
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '+ EC2' }))
    await user.selectOptions(await screen.findByLabelText('Pricing model'), 'savings_plan')
    await user.selectOptions(screen.getByLabelText('Plan type'), 'ec2_instance')
    await user.selectOptions(screen.getByLabelText('Payment option'), 'partial_upfront')
    await waitFor(() => {
      const sent = calls.filter((c) => c.url === '/api/estimate').at(-1)!
      expect(JSON.parse(String(sent.init?.body)).items[0].pricing).toMatchObject({ model: 'savings_plan', sp_type: 'ec2_instance', payment: 'partial_upfront' })
    })
    expect(screen.getByText(/Partial upfront assumes 50%/)).toBeInTheDocument()
  })

  it('does not offer Savings Plans for RDS', async () => {
    mockApi({
      ...baseHandlers,
      '/api/catalog/rds': () => ({ region: 'ap-south-1', engines: [{ engine: 'PostgreSQL', edition: '', license_model: 'No license required' }], instances: [] }),
      '/api/estimate': () => estimate('10.00'),
    })
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '+ RDS' }))
    const options = within(await screen.findByLabelText('Pricing model')).getAllByRole('option').map((o) => o.textContent)
    expect(options).toEqual(['On-Demand', 'Reserved Instance'])
  })

  it('adds a data transfer item and requires a destination for inter-region traffic', async () => {
    const calls = mockApi({
      ...baseHandlers,
      '/api/catalog/dt': () => ({ region: 'ap-south-1', destinations: [{ region: 'us-east-1', name: 'US East (N. Virginia)' }] }),
      '/api/estimate': () => estimate('0.00'),
    })
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '+ Data transfer' }))
    const dest = await screen.findByLabelText('Destination region')
    expect(dest).toBeDisabled()
    await user.clear(screen.getByLabelText('Inter-region GB'))
    await user.type(screen.getByLabelText('Inter-region GB'), '100')
    expect(dest).toBeEnabled()
    await user.selectOptions(dest, 'us-east-1')
    await waitFor(() => {
      const sent = calls.filter((c) => c.url === '/api/estimate').at(-1)!
      expect(JSON.parse(String(sent.init?.body)).items[0]).toMatchObject({ type: 'dt', inter_region_gb: 100, destination_region: 'us-east-1' })
    })
  })

  it('shows cheaper alternatives, flags Arm, and swaps the instance type on "Use"', async () => {
    mockApi({
      ...baseHandlers,
      '/api/estimate': () => estimate('32.70'),
      '/api/ec2/alternatives': () => ({
        instance_type: 't3.medium',
        hourly: '0.0448',
        alternatives: [
          { instance_type: 't4g.medium', vcpu: 2, memory_gib: '4', hourly: '0.0224', saving_pct: '50.0', arm: true },
          { instance_type: 't3a.medium', vcpu: 2, memory_gib: '4', hourly: '0.0246', saving_pct: '45.1', arm: false },
        ],
      }),
    })
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '+ EC2' }))
    await user.click(await screen.findByRole('button', { name: 'Find cheaper alternatives' }))
    expect(await screen.findByText('t4g.medium')).toBeInTheDocument()
    expect(screen.getByText('Arm (Graviton)')).toBeInTheDocument()
    await user.click(screen.getAllByRole('button', { name: 'Use' })[1])
    expect(screen.getByDisplayValue('t3a.medium')).toBeInTheDocument()
  })
})

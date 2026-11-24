import { describe, expect, it } from 'vitest'
import { money, regionLabel, signedMoney, signedPercent } from './format'

describe('format', () => {
  it('formats server money strings as USD', () => {
    expect(money('1234.5')).toBe('$1,234.50')
    expect(money('0.00')).toBe('$0.00')
  })

  it('does not render NaN for bad input', () => {
    expect(money('abc')).toBe('—')
  })

  it('shows signed differences', () => {
    expect(signedMoney('-62.67')).toBe('-$62.67')
    expect(signedMoney('12')).toBe('+$12.00')
    expect(signedMoney('0.00')).toBe('$0.00')
  })

  it('shows signed percentages with one decimal', () => {
    expect(signedPercent('-42.92')).toBe('-42.9%')
    expect(signedPercent('3')).toBe('+3.0%')
    expect(signedPercent('0.00')).toBe('0%')
  })

  it('labels known regions and falls back to the code', () => {
    expect(regionLabel('ap-south-1')).toBe('Asia Pacific (Mumbai) · ap-south-1')
    expect(regionLabel('xx-test-9')).toBe('xx-test-9')
  })
})

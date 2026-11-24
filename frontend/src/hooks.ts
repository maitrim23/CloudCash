import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import type { EstimateResult, Meta, Scenario } from './types'

/** Tiny promise cache so each catalog (hundreds of instance types) loads once per region. */
const cache = new Map<string, Promise<unknown>>()

/** For tests: forget everything fetched so far. */
export const clearCache = () => cache.clear()

export function useCached<T>(key: string | null, load: () => Promise<T>): { data: T | null; error: string | null } {
  const [state, setState] = useState<{ key: string | null; data: T | null; error: string | null }>({
    key: null,
    data: null,
    error: null,
  })
  useEffect(() => {
    if (!key) return
    let live = true
    if (!cache.has(key)) cache.set(key, load())
    ;(cache.get(key) as Promise<T>)
      .then((data) => live && setState({ key, data, error: null }))
      .catch((e: Error) => {
        cache.delete(key)
        if (live) setState({ key, data: null, error: e.message })
      })
    return () => {
      live = false
    }
    // `load` is recreated every render by callers; the key identifies the request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  // Ignore data that belongs to a previous key (e.g. the region just changed).
  return state.key === key ? state : { data: null, error: null }
}

export function useMeta(): { meta: Meta | null; error: string | null } {
  const { data, error } = useCached<Meta>('meta', api.meta)
  return { meta: data, error }
}

/** Debounced live estimate: re-prices the scenario ~300 ms after the last edit. */
export function useEstimate(scenario: Scenario) {
  const [result, setResult] = useState<EstimateResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const body = JSON.stringify(scenario)
  const seq = useRef(0)

  useEffect(() => {
    const mine = ++seq.current
    const snapshot = JSON.parse(body) as Scenario
    if (snapshot.items.length === 0) {
      setResult(null)
      setError(null)
      setLoading(false)
      return
    }
    setLoading(true)
    const ctrl = new AbortController()
    const timer = setTimeout(() => {
      api
        .estimate(snapshot, ctrl.signal)
        .then((r) => {
          if (mine !== seq.current) return
          setResult(r)
          setError(null)
        })
        .catch((e: Error) => {
          if (e.name === 'AbortError' || mine !== seq.current) return
          setError(e.message)
        })
        .finally(() => mine === seq.current && setLoading(false))
    }, 300)
    return () => {
      clearTimeout(timer)
      ctrl.abort()
    }
  }, [body]) // `body` is a stable string: identical content never re-triggers a request

  return { result, error, loading }
}

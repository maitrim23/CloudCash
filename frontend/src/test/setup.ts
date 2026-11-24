import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach } from 'vitest'
import { clearCache } from '../hooks'

// Vitest runs without globals, so Testing Library cannot register its own cleanup.
afterEach(() => cleanup())
// Each test starts with no cached catalogs/meta from a previous test.
beforeEach(() => clearCache())

import '@testing-library/jest-dom/vitest'
import {cleanup} from '@testing-library/react'
import {afterEach,vi} from 'vitest'
afterEach(()=>cleanup())
Element.prototype.scrollIntoView=vi.fn()
globalThis.ResizeObserver=class {observe(){}unobserve(){}disconnect(){}}
window.matchMedia=vi.fn().mockImplementation(()=>({matches:false,addEventListener:vi.fn(),removeEventListener:vi.fn(),addListener:vi.fn(),removeListener:vi.fn()}))

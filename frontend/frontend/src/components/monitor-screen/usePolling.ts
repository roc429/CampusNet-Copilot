import { useCallback, useEffect, useRef } from 'react'

const DEFAULT_MS = 3000

export function usePolling(load: () => void | Promise<void>, ms = DEFAULT_MS) {
  const loadRef = useRef(load)
  loadRef.current = load

  const run = useCallback(() => {
    void loadRef.current()
  }, [])

  useEffect(() => {
    run()
    const id = window.setInterval(run, ms)
    return () => window.clearInterval(id)
  }, [run, ms])

  return run
}

// Breakpoint-Hook: unter ~640px wechselt die Workbench in die gestapelte
// Mobil-Ansicht (siehe Design-Handoff, Abschnitt „Mobil-Ansicht").
import { useEffect, useState } from 'react'

const QUERY = '(max-width: 640px)'

export function useIsMobile(): boolean {
  const [mobile, setMobile] = useState(() => window.matchMedia(QUERY).matches)
  useEffect(() => {
    const mql = window.matchMedia(QUERY)
    const onChange = (e: MediaQueryListEvent) => setMobile(e.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [])
  return mobile
}

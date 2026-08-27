// Dünnstrichiges Inline-SVG-Icon-Set + LexoTerm-Logo (aus dem Design-Handoff).
import type { CSSProperties, JSX } from 'react'

export type IconName =
  | 'search' | 'chevron' | 'chevDown' | 'plus' | 'x' | 'check' | 'download'
  | 'upload' | 'play' | 'filter' | 'sun' | 'moon' | 'settings' | 'grid'
  | 'table' | 'file' | 'folder' | 'book' | 'flask' | 'command' | 'bolt'
  | 'refresh' | 'dot' | 'diamond' | 'sparkle' | 'pin'
  | 'panelL' | 'panelR' | 'panelB' | 'panelT' | 'layers'
  | 'menu' | 'chart' | 'user' | 'logout' | 'shield'

const PATHS: Record<IconName, JSX.Element> = {
  search: <><circle cx="7" cy="7" r="4.5" /><path d="M10.5 10.5 14 14" /></>,
  chevron: <path d="M5.5 3.5 10 8l-4.5 4.5" />,
  chevDown: <path d="M3.5 5.5 8 10l4.5-4.5" />,
  plus: <><path d="M8 3v10" /><path d="M3 8h10" /></>,
  x: <><path d="M4 4l8 8" /><path d="M12 4l-8 8" /></>,
  check: <path d="M3 8.5 6 11.5 13 4.5" />,
  download: <><path d="M8 3v8" /><path d="M5 8l3 3 3-3" /><path d="M3 13h10" /></>,
  upload: <><path d="M8 13V5" /><path d="M5 8l3-3 3 3" /><path d="M3 3h10" /></>,
  play: <path d="M5 3.5 12.5 8 5 12.5z" />,
  filter: <path d="M2 3h12l-4.5 6V13l-3-1.5V9z" />,
  sun: <><circle cx="8" cy="8" r="3" /><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.5 1.5M11.5 11.5 13 13M3 13l1.5-1.5M11.5 4.5 13 3" /></>,
  moon: <path d="M13 9.5A5 5 0 1 1 6.5 3a4 4 0 0 0 6.5 6.5z" />,
  settings: <g transform="scale(0.6667)" strokeWidth="2"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" /></g>,
  grid: <><rect x="2" y="2" width="5" height="5" /><rect x="9" y="2" width="5" height="5" /><rect x="2" y="9" width="5" height="5" /><rect x="9" y="9" width="5" height="5" /></>,
  table: <><rect x="2" y="3" width="12" height="10" rx="1" /><path d="M2 7h12M6 7v6" /></>,
  file: <><path d="M4 1.5h5l3 3V14a.5.5 0 0 1-.5.5h-7A.5.5 0 0 1 4 14V2a.5.5 0 0 1 .5-.5z" /><path d="M9 1.5V5h3" /></>,
  folder: <path d="M1.5 3.5h4l1.5 1.5h7v8h-12.5z" />,
  book: <path d="M3 2h4.5a1.5 1.5 0 0 1 1.5 1.5V14a1.5 1.5 0 0 0-1.5-1.5H3zm10 0H8.5A1.5 1.5 0 0 0 7 3.5V14a1.5 1.5 0 0 1 1.5-1.5H13z" />,
  flask: <><path d="M6 1.5v4L2.5 12a1 1 0 0 0 .9 1.5h9.2a1 1 0 0 0 .9-1.5L10 5.5v-4" /><path d="M5 1.5h6" /></>,
  command: <path d="M5 2.5a1.5 1.5 0 1 1 0 3h6a1.5 1.5 0 1 1 0 3M5 5.5h6m-6 0v5a1.5 1.5 0 1 1-1.5-1.5h9a1.5 1.5 0 1 1 0 3" />,
  bolt: <path d="M9 1.5 3.5 9h4L7 14.5 12.5 7h-4z" />,
  refresh: <><path d="M13 7A5 5 0 0 0 3.5 5.5" /><path d="M3 3v3h3" /><path d="M3 9a5 5 0 0 0 9.5 1.5" /><path d="M13 13v-3h-3" /></>,
  dot: <circle cx="8" cy="8" r="2.5" fill="currentColor" />,
  diamond: <path d="M8 1.5 14.5 8 8 14.5 1.5 8z" />,
  sparkle: <path d="M8 1.5v5M8 9.5v5M1.5 8h5M9.5 8h5" />,
  pin: <path d="M8 1.5v8M5 9.5h6M6.5 13.5 8 9.5l1.5 4z" />,
  panelL: <><rect x="2" y="3" width="12" height="10" rx="1" /><path d="M6 3v10" /></>,
  panelR: <><rect x="2" y="3" width="12" height="10" rx="1" /><path d="M10 3v10" /></>,
  panelB: <><rect x="2" y="3" width="12" height="10" rx="1" /><path d="M2 10h12" /></>,
  panelT: <><rect x="2" y="3" width="12" height="10" rx="1" /><path d="M2 6h12" /></>,
  layers: <><path d="M8 1.5 1.5 5 8 8.5 14.5 5z" /><path d="M1.5 8 8 11.5 14.5 8" /><path d="M1.5 11 8 14.5 14.5 11" /></>,
  menu: <><path d="M2.5 4.5h11" /><path d="M2.5 8h11" /><path d="M2.5 11.5h11" /></>,
  chart: <><path d="M2 13.5h12" /><path d="M4 13V8" /><path d="M8 13V4" /><path d="M12 13V6.5" /></>,
  user: <><circle cx="8" cy="5.5" r="3" /><path d="M2.5 14c0-3 2.5-5 5.5-5s5.5 2 5.5 5" /></>,
  logout: <><path d="M6.5 14H3.5a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1h3" /><path d="M10.5 11 14 8l-3.5-3" /><path d="M14 8H6" /></>,
  shield: <><path d="M8 1.5 13.5 3.5V7.5c0 4-2.3 6-5.5 7-3.2-1-5.5-3-5.5-7V3.5z" /><path d="M5.5 8 7.3 9.8 10.5 6" /></>,
}

export function Icon({
  name, size = 14, stroke = 'currentColor', style, className, onClick,
}: {
  name: IconName; size?: number; stroke?: string; style?: CSSProperties; className?: string
  onClick?: () => void
}) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 16 16"
      fill="none" stroke={stroke} strokeWidth={1.4}
      strokeLinecap="round" strokeLinejoin="round"
      className={className} onClick={onClick}
      style={{ display: 'inline-block', flexShrink: 0, ...style }}
    >
      {PATHS[name] ?? null}
    </svg>
  )
}

export function Logo({ size = 18, style }: { size?: number; style?: CSSProperties }) {
  return (
    <svg width={size} height={size} viewBox="0 0 46 46" fill="none" style={{ display: 'inline-block', ...style }}>
      <rect x="22.6274" width="32" height="32" rx="5" transform="rotate(45 22.6274 0)" fill="url(#lt-logo-g)" />
      <path d="M14.1173 21.2144C13.3364 21.9954 13.3363 23.2618 14.1173 24.0428L21.0392 30.9647L18.8806 33.1233C18.0995 33.9042 16.8331 33.9043 16.0522 33.1233L6.97163 24.0428C6.19064 23.2618 6.19077 21.9954 6.97163 21.2144L21.2132 6.97281C21.9943 6.19176 23.2606 6.19176 24.0416 6.97281L26.2002 9.13142L14.1173 21.2144Z" fill="#003835" />
      <path d="M31.1376 24.0422C31.9185 23.2612 31.9186 21.9948 31.1376 21.2138L24.2156 14.2919L26.3743 12.1333C27.1553 11.3524 28.4217 11.3523 29.2027 12.1333L38.2832 21.2138C39.0642 21.9948 39.0641 23.2611 38.2832 24.0422L24.0416 38.2838C23.2606 39.0648 21.9943 39.0648 21.2132 38.2838L19.0546 36.1252L31.1376 24.0422Z" fill="#003835" />
      <defs>
        <linearGradient id="lt-logo-g" x1="29.1878" y1="32" x2="49.6425" y2="1.04094" gradientUnits="userSpaceOnUse">
          <stop stopColor="var(--lt-g-400)" />
          <stop offset="1" stopColor="var(--lt-g-700)" />
        </linearGradient>
      </defs>
    </svg>
  )
}

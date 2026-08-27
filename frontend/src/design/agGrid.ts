// AG Grid Setup: einmalige Modul-Registrierung + Theme, das die LexoTerm-
// Design-Tokens (tokens.css) referenziert, statt sie zu duplizieren. Da die
// Werte als var(--lt-…)-Strings durchgereicht werden, folgt das Grid Theme-
// Wechsel (data-theme="dark") automatisch, ohne eigenes Dark-Theme.
import { AllCommunityModule, ModuleRegistry, themeQuartz } from 'ag-grid-community'

ModuleRegistry.registerModules([AllCommunityModule])

export const ltGridTheme = themeQuartz.withParams({
  accentColor: 'var(--lt-primary)',
  backgroundColor: 'var(--lt-bg-0)',
  chromeBackgroundColor: 'var(--lt-bg-0)',
  foregroundColor: 'var(--lt-fg-1)',
  textColor: 'var(--lt-fg-1)',
  subtleTextColor: 'var(--lt-fg-3)',
  borderColor: 'var(--lt-line-1)',
  headerBackgroundColor: 'var(--lt-bg-0)',
  headerTextColor: 'var(--lt-fg-1)',
  headerFontWeight: 500,
  oddRowBackgroundColor: 'var(--lt-bg-0)',
  rowHoverColor: 'var(--lt-bg-1)',
  selectedRowBackgroundColor: 'var(--lt-primary-soft)',
  fontFamily: 'var(--lt-font-sans)',
  fontSize: 12.5,
  headerFontSize: 12.5,
  cellHorizontalPadding: 12,
  spacing: 6,
  wrapperBorder: false,
  wrapperBorderRadius: 0,
  rowBorder: true,
  headerRowBorder: true,
  columnBorder: false,
  headerColumnBorder: false,
})

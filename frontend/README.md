# Frontend — LexoTerm Tools · Wörterbuchkonsistenzprüfung

React 19 + Vite + TypeScript. Design nach `pdl-lt-design/design_handoff_tools`
(Tokens in `src/styles/tokens.css`, Workbench-Layout, ab ≤640px gestapelte
Mobil-Ansicht).

```powershell
npm install
npm run dev      # Port 5173, proxyt /api -> http://localhost:8000
npm run build    # tsc -b && vite build -> dist/ (wird von FastAPI ausgeliefert)
npm run lint     # oxlint
```

Module werden deklarativ in `src/modules/registry.ts` beschrieben
(Felder + Spalten + run); Layout und Zustand liegen in `src/layout/` bzw.
`src/state/workbench.tsx`.

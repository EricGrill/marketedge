# Design

## Source of truth
- Status: Active
- Last refreshed: 2026-07-15
- Primary product surfaces: Static web dashboard under `web/`, Textual TUI, CLI-generated dashboard artifacts.
- Evidence reviewed: `README.md`, `web/index.html`, `web/styles.css`, `web/app.js`. No prior `DESIGN.md`, screenshots, brand assets, or visual-regression baselines were present.

## Brand
- Personality: Research-first quant cockpit, fast, weather-aware, risk-conscious, and deliberately experimental.
- Trust signals: Dry-run status, data artifact freshness, venue health, risk preview, explicit sample/generated data labels, local-first controls.
- Avoid: Marketing landing-page composition, decorative cards inside cards, vague trading copy, hidden live-trading affordances.

## Product goals
- Goals: Let an operator scan weather prediction markets, compare model edge to market implied probability, preview risk, inspect positions, and review backtest context.
- Non-goals: Public marketing site, broker replacement, live order execution from the static web surface.
- Success signals: Key market, edge, quote, risk, and artifact states are readable at a glance; sample-vs-generated data cannot be missed.

## Personas and jobs
- Primary personas: Quant researcher, prediction-market operator, local-first automation builder.
- User jobs: Find mispriced contracts, inspect market state, validate risk before a simulated order, monitor positions and strategy diagnostics.
- Key contexts of use: Desktop operator screen first, with tablet/mobile support for monitoring and review.

## Information architecture
- Primary navigation: Single dashboard surface with filters, selected market detail, order workflow, risk/positions/weather/backtest context.
- Core routes/screens: `web/index.html` only.
- Content hierarchy: Selected market and edge are primary; market list and opportunity queue are discovery; order/risk/positions are action context; weather/backtest are supporting evidence.

## Design principles
- Principle 1: Make operational state visually loud without obscuring numeric precision.
- Principle 2: Preserve local-first safety cues and data provenance in every major area.
- Tradeoffs: The visual style can be expressive, but dense market information and responsive readability take priority over decoration.

## Visual language
- Color: Dark graphite base with varied high-contrast accents: hazard orange, signal green, cyan, red, yellow, and limited violet. Avoid a single-hue dashboard.
- Typography: System sans for interface text with tabular numerals; labels use uppercase microcopy and generous tracking.
- Spacing/layout rhythm: Dense cockpit grid with compact controls, stable panel dimensions, and clear gutters.
- Shape/radius/elevation: Angular clipped panels, radius 8px or less, luminous borders instead of soft cards.
- Motion: Minimal pulse/sweep effects only for status and ambient background; honor reduced motion.
- Imagery/iconography: Abstract radar/weather field as a background visual asset; no marketing illustration.

## Components
- Existing components to reuse: Static HTML IDs and JS render targets in `web/app.js`; generated JSON payload contract.
- New/changed components: Background atmosphere layer, cockpit-style panel chrome, redesigned filters, rows, order ticket, and metric panels.
- Variants and states: Positive/negative, loaded/missing/error artifact states, BUY/SELL/HOLD signal states, active rows/buttons, warning/danger reason chips.
- Token/component ownership: `web/styles.css` owns visual tokens; `web/app.js` owns behavior and data normalization.

## Accessibility
- Target standard: Practical WCAG AA contrast for text against dark surfaces.
- Keyboard/focus behavior: Native controls and buttons remain focusable; visible focus rings required.
- Contrast/readability: Numeric labels and status states must be legible on desktop and mobile.
- Screen-reader semantics: Existing labels, form controls, and ARIA labels remain in place.
- Reduced motion and sensory considerations: Background sweeps and pulses are disabled under `prefers-reduced-motion`.

## Responsive behavior
- Supported breakpoints/devices: Desktop cockpit first, responsive tablet and mobile stacking.
- Layout adaptations: Four-column desktop grid collapses to two columns, then one column; right/trade columns become normal stacked sections.
- Touch/hover differences: Buttons keep stable dimensions; hover effects supplement but do not replace active/focus states.

## Interaction states
- Loading: Artifact chips show loading/missing/error/loaded states.
- Empty: Market empty state remains visible when filters remove all markets.
- Error: Artifact chips and risk markers use explicit error colors.
- Success: Loaded/generated/safe states use green or cyan accents.
- Disabled: No disabled state currently exists in the static dashboard.
- Offline/slow network, if applicable: Missing local JSON artifacts intentionally fall back to sample data.

## Content voice
- Tone: Concise operator labels, terse status language, no tutorial copy inside the dashboard.
- Terminology: Use market, edge, bid, ask, spread, confidence, exposure, dry run, generated, sample.
- Microcopy rules: Keep state labels factual and compact; avoid implying live execution from static web controls.

## Implementation constraints
- Framework/styling system: Static HTML/CSS/vanilla JS, no build step, no frontend dependencies.
- Design-token constraints: CSS custom properties in `web/styles.css`.
- Performance constraints: Must run from a simple local HTTP server and remain usable with sample data.
- Compatibility constraints: Keep existing DOM IDs used by `web/app.js`; do not break dashboard/backtest JSON hydration.
- Test/screenshot expectations: Run `node --check web/app.js`; use browser smoke checks when possible.

## Open questions
- [ ] Should Market Edge have a permanent logo/brand asset beyond text initials? Owner: product. Impact: brand consistency.
- [ ] Should the web dashboard eventually expose strategy management controls, or remain read-only/simulated? Owner: product. Impact: information architecture.

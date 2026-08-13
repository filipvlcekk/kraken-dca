# Hallmark Dark UI Design

## Goal

Install Hallmark as a project-scoped Codex skill and apply its design guidance to the existing Vue/Vite web UI with a dark modern operational design.

## Scope

- Add Hallmark under `.codex/skills/hallmark/` so future Codex sessions in this repo can load the same design rules.
- Redesign the existing authenticated dashboard, login view, scheduler status, credentials editor, pair editor, schedule editor, and warning states.
- Preserve the current Vue component structure, API calls, auth behavior, scheduler behavior, and form semantics.
- Avoid unrelated backend, scheduler, config, or trading logic changes.

## Design Direction

The UI should feel like a compact trading operations console, not a marketing page. Use a near-black graphite background, dark panels with thin borders, restrained elevation, crisp focus states, and readable form controls. Use cyan/green accents for primary actions and live/synchronized state, amber for warnings, and red for destructive or failed states.

Typography should use system sans fonts with compact headings and normal letter spacing. The current large serif hero treatment should be removed. The first screen remains the usable app: login when unauthenticated, dashboard when authenticated.

## Component Responsibilities

- `frontend/src/style.css`: global tokens, body background, base buttons, fields, code, focus, and app spacing.
- `frontend/src/App.vue`: dashboard shell, header, panels, pair section, sticky save bar.
- `frontend/src/components/LoginView.vue`: dark access panel matching dashboard tone.
- `frontend/src/components/ConfigWarnings.vue`: dark warning stack with amber/red surfaces.
- `frontend/src/components/SchedulerStatus.vue`: scheduler panel, job list, alert styling.
- `frontend/src/components/CredentialEditor.vue`: credential cards and replacement form layout.
- `frontend/src/components/PairEditor.vue`: pair cards, dense form grid, suggestions dropdown, manual run state.
- `frontend/src/components/ScheduleEditor.vue`: schedule controls, summary, warnings, error styling.

## Risk And Constraints

This should be mostly CSS and small template/class changes. GitNexus impact checks are required before editing Vue component symbols. The expected blast radius is low because no public TypeScript APIs or backend execution flows should change.

Existing uncommitted user changes in `.gitignore` and `docs/superpowers/plans/2026-08-11-deepsec-remediation-roadmap.md` must be left untouched.

## Verification

- Install Hallmark files from `https://github.com/Nutlope/hallmark` into `.codex/skills/hallmark/`.
- Run front-end tests with `npm test -- --run` from `frontend/`.
- Run front-end build with `npm run build` from `frontend/`.
- Run `gitnexus_detect_changes()` before any commit or final handoff to confirm affected scope.

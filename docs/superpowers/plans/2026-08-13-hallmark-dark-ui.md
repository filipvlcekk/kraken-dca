# Hallmark Dark UI Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install Hallmark project-scoped and redesign the existing Vue/Vite web UI as a dark modern trading operations console.

**Architecture:** Keep the current component boundaries and data flow. Make a styling-first pass through global tokens and scoped component CSS, using only small template class changes where needed for clearer dark UI states.

**Tech Stack:** Vue 3 single-file components, Vite, TypeScript, Vitest, project-scoped Codex skills.

---

## Chunk 1: Install Hallmark

### Task 1: Add Project-Scoped Skill

**Files:**
- Create: `.codex/skills/hallmark/SKILL.md`
- Create: `.codex/skills/hallmark/references/*`

- [ ] **Step 1: Fetch Hallmark source**

Run: download or clone `https://github.com/Nutlope/hallmark`.
Expected: source contains `skills/hallmark/SKILL.md` and `skills/hallmark/references/`.

- [ ] **Step 2: Copy skill files**

Create `.codex/skills/hallmark/` and copy the upstream `SKILL.md` plus `references/`.
Expected: `rg --files .codex/skills/hallmark` lists the skill entry and references.

- [ ] **Step 3: Inspect installed skill**

Run: `sed -n '1,220p' .codex/skills/hallmark/SKILL.md`.
Expected: the file describes Hallmark and its design workflow.

## Chunk 2: Redesign Vue UI

### Task 2: Global Theme Tokens

**Files:**
- Modify: `frontend/src/style.css`

- [ ] **Step 1: Update global tokens**

Replace the warm parchment palette with graphite surfaces, cool accents, amber warnings, red errors, dark fields, and system UI typography.

- [ ] **Step 2: Update base controls**

Restyle buttons, disabled states, inputs, selects, code, focus-visible outlines, `body`, and `#app`.

- [ ] **Step 3: Build smoke check**

Run: `npm run build` from `frontend/`.
Expected: build succeeds or reports only issues unrelated to the CSS token change.

### Task 3: Dashboard Shell

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Run GitNexus impact analysis**

Run `gitnexus_impact` upstream for `loadDashboard`, `handleLogin`, `handleLogout`, `saveConfig`, `reloadScheduler`, `runPairNow`, `updatePair`, and `pairFieldErrors` if their containing component is edited.
Expected: low UI-local blast radius before edits proceed.

- [ ] **Step 2: Replace dashboard visual treatment**

Keep the same rendered components and events. Restyle `.app-shell`, `.loading`, `.dashboard`, `.hero`, `.panel`, `.pairs-section`, `.pairs-grid`, and `.save-bar` for a compact dark operations layout.

- [ ] **Step 3: Verify component tests**

Run: `npm test -- --run src/__tests__/app.test.ts` from `frontend/`.
Expected: tests pass.

### Task 4: Component Surface Pass

**Files:**
- Modify: `frontend/src/components/LoginView.vue`
- Modify: `frontend/src/components/ConfigWarnings.vue`
- Modify: `frontend/src/components/SchedulerStatus.vue`
- Modify: `frontend/src/components/CredentialEditor.vue`
- Modify: `frontend/src/components/PairEditor.vue`
- Modify: `frontend/src/components/ScheduleEditor.vue`

- [ ] **Step 1: Run GitNexus impact analysis**

Run `gitnexus_impact` upstream for edited component functions: `submit`, `startOidcLogin`, `jobCountLabel`, `credentialStatus`, `credentialDisplay`, `savePublicReplacement`, `savePrivateReplacement`, `updatePair`, `fetchPairSuggestions`, `selectPairSuggestion`, `suggestionLabel`, `suggestionMeta`, `updateNumber`, `updateBoolean`, `updateSchedule`, `updateMinInterval`, `emitSchedule`, `onPresetChange`, `onCronInput`, `onTimezoneChange`, `onEnabledChange`, and `onMinIntervalInput`.
Expected: low UI-local blast radius; warn before proceeding if any result is high or critical.

- [ ] **Step 2: Restyle login and status**

Apply dark panel, compact typography, accent mark, readable error state, scheduler status header, job list, and alerts.

- [ ] **Step 3: Restyle editors**

Apply dark cards, dense form grids, consistent labels, suggestion dropdown contrast, warning/error colors, manual-run state, and responsive replacement input layout.

- [ ] **Step 4: Run targeted component tests**

Run: `npm test -- --run src/__tests__/loginView.test.ts src/__tests__/schedulerStatus.test.ts src/__tests__/credentialEditor.test.ts src/__tests__/pairEditor.test.ts src/__tests__/scheduleEditor.test.ts src/__tests__/configWarnings.test.ts` from `frontend/`.
Expected: tests pass.

## Chunk 3: Final Verification

### Task 5: Full Frontend Verification

**Files:**
- No additional edits expected.

- [ ] **Step 1: Run full front-end tests**

Run: `npm test -- --run` from `frontend/`.
Expected: all Vitest tests pass.

- [ ] **Step 2: Run production build**

Run: `npm run build` from `frontend/`.
Expected: typecheck and Vite build pass.

- [ ] **Step 3: Run GitNexus change detection**

Run `gitnexus_detect_changes(scope: "all")`.
Expected: changed scope is limited to Hallmark skill files, docs, and front-end UI components/styles.

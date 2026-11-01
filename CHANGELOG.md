# Changelog

Published changes to the first-party packs in `packs/`, newest first. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); each pack keeps its own semantic version in `packs/<pack>/package.json`. Generated `upstream/` packs are not listed. Earlier history: `git log`.

## [Unreleased]

- Routing eval defaults to Haiku 5.5 with thinking off and a configurable 12-message budget. It now rejects failed or aborted responses as decisions, distinguishes errors and budget caps from completed no-skill answers, accepts a separately validated holdout through `--cases`, and accepts `--thinking LEVEL` (default `off`).

## sanofi 1.2.4 - 2026-11-01

- `architecture-documentation` opens its routing preview with what users ask for ("Draw or document how a system's services talk to each other") and keeps the ADR boundary inside it. Over 36 thinking-off runs on its routing and holdout cases, Sonnet 5.5 selected it in 36 (was 28) and DeepSeek V4 Flash in 31 (was 26); Haiku 5.5 went from 9 to 5, all misses reading no skill. `adr-writing` held at 36 and 35–36.
- `iac-security-review` opens its routing preview with the question users ask ("Security-audit Terraform/CDK: what the internet can reach, judged against current AWS defaults"). Over 24 thinking-off runs across the routing cases and holdout, Haiku 5.5 selected it in 7 (was 2) and DeepSeek V4 Flash in 21 (was 17); Sonnet 5.5 held at 24. On a no-skill CDK table request Sonnet now reads `iac-terraform` in 5 of 6 runs, where it read `iac-security-review` in 3.

## clssck 2.1.24 - 2026-10-30

- Add non-interrupting `web-viewport-zoom` and `web-touch-gestures` reminders for web-source edits. They preserve page zoom, native scrolling, and pinch zoom, distinguish native scrollers from custom drags, and exempt already-compliant code and inert examples.
- Correct `mobile-native` guidance on hover-capable styluses and Tailwind v4, keep press feedback separate from activation, distinguish native and JavaScript carousels, and separate emulator checks from physical-device verification. Remove unsupported claims about zoom persisting after blur and `text-size-adjust: 100%` disabling font inflation.
- `emil-design-eng` puts the phrasing users type in its routing preview ("make UI feel polished, crafted, or premium instead of cheap or unfinished"). Over 36 thinking-off runs across the routing cases and holdout, Sonnet 5.5 selected it in 29 (was 19) and DeepSeek V4 Flash in 31 (was 16); Haiku 5.5 stayed at 0 of 12.
- `review-animations` opens its routing preview with the review request itself ("Review or critique animation code I wrote: is this transition right, anything off before merge?"). Over 36 thinking-off runs, Sonnet 5.5 selected it in 30 (was 18) and DeepSeek V4 Flash in 26 (was 13); Haiku 5.5 stayed at 0. Missed `improve-animations` requests read no skill rather than this one.
- `improve-animations`, `apple-design`, `skill-authoring` and `animate` routing previews now open with the request users type: "Audit how things move across the whole app", "iOS/macOS feel in web apps, not React Native", "Write a skill teaching the agent any topic, even Terraform", and "Add new motion … not review or jank". Over 24 thinking-off runs per skill across the routing cases and holdout, Haiku 5.5 selected `improve-animations` in 18 (was 9), `apple-design` in 16 (was 7) and `skill-authoring` in 13 (was 9). Sonnet 5.5 held or rose to 24 on all three, and DeepSeek V4 Flash rose to 24, 23 and 24. `animate` held its own requests on Sonnet (24) and DeepSeek (23 to 24) while DeepSeek reads of it for other skills' requests fell from 23 to 6 (Sonnet 4 to 0). Costs: Haiku selected `animate` in 0 (was 2) and the unchanged `animation-performance` in 1 (was 6), every miss reading no skill; an 8-run Haiku check with the original `animate` scored 5 of 64 against 6 of 64 for the new one. DeepSeek `remove-animations` fell from 22 to 18 of 30 across three requests: the app-wide "every click makes me wait" request moved toward `improve-animations` (3 to 1), the cmd+k request toward `animate` (1 to 0), and the dashboard-navigation request lost one run (6 to 5).
- `break-ui` opens its routing preview with the edge-data question itself ("Worst-case data for a UI: what if a name is long or non-Latin, a field empty, a count 0 or huge?"), so implicit "what happens if" questions route as well as explicit "try to break it" requests. Over 24 thinking-off runs, Sonnet 5.5 selected it in 22 (was 18) and DeepSeek V4 Flash in 17 (was 16); Haiku 5.5 stayed at 0.

## clssck 2.1.23 - 2026-10-30

- New `remove-animations` skill, ported from emilkowalski/skills at `a81dbca`. It gates every existing animation (keyboard-triggered, 100+ times a day, functional data, no named purpose), deletes or reduces what fails, checks removal hazards before deleting, then removes the code left orphaned. Its routing preview carries "feels slow" and "too much animation". OMP additions: a browser check that removed motion left nothing hidden, reduced-motion branches follow the animation they gate, and dependency removal is proposed, never run. Upstream's repo-root `ui-cheatsheet.md` is not vendored; the skill never reads it.
- `find-animation-opportunities` and `improve-animations` descriptions route "remove the animations", "too much animation", and "feels slow" to `remove-animations`; their first 99 characters are unchanged.

## clssck 2.1.22 - 2026-10-28

- `animation-performance`, `animation-vocabulary`, `animate` and `animate-expo` now put the phrasing users actually type inside the ~99-character routing preview OMP shows before a description is compressed: "stutter, jank, or drop frames", "what's it called when…", "decide it shouldn't animate: easing", and "gestures, sheets, and haptics in React Native and Expo". Blind routing trials with the preview text alone now select the intended skill for "my animation stutters", "what do you call the bounce-in effect", "should it even ripple", "what easing for a tooltip" and "haptics in our native app".
- `animation-performance` replaces a dangling "No." that answered a question no longer in the file, and states why a composited `filter: blur()` still costs.

## sanofi 1.2.3 - 2026-10-28

- `dbt` names dbt CI selectors and `state:modified` runs in its routing preview, so "our dbt CI selector runs every model" no longer reads as a GitHub Actions problem (`cicd-engineering`).

## sanofi 1.2.2 - 2026-10-25

- Every Sanofi skill that reads, searches, or publishes Confluence/Jira hands off to the `atl` skill through one routing line with the install command, one fallback (paste the content, record references as Links, never publish), and one publish sequence (`atl page create|update --file <path> --plan`, then its `next`).
- `dbt` and `sanofi-airflow` source-of-truth pages name the `atl page get <id>` read command.
- `adr-writing` treats `site_not_accessible` as a blocked item and passes `--site <host>` from the user's URLs for bare Jira keys and page ids.

## sanofi 1.2.1 - 2026-10-25

- `adr-writing` reads Confluence pages, comment threads, Jira issues, and links through named `atl` commands instead of generic Atlassian session tools.

## sanofi 1.2.0 - 2026-10-24

- Removed `search-company-knowledge` and `confluence-html-editor`; Confluence and Jira reading, search, and publishing move to the `atl` skill.

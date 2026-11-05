---
name: mobile-native
description: Make a web app feel native on a phone — the small CSS and meta-tag fixes that separate "a website in a browser" from something that feels installed. Covers sticky hover states, tap highlight flashes, the 100vh bug, inputs that zoom the page, laggy taps, pull-to-refresh hijacking scroll, content under the notch, long-press selecting button text, carousels that scroll the wrong way, mismatched status bars, and the rule that you test on real hardware. Use when a web app is being built for or reviewed on mobile, when something "works in Chrome but feels wrong on my phone", when building a PWA, a bottom sheet, a carousel, a full-screen layout, or any touch interaction. For motion itself use animate; for React Native use animate-expo.
---

# Feeling Native On Mobile

## Initial Response

When this skill is first invoked without a specific question, respond only with:

> I'm ready to make your web app feel native on mobile, my knowledge comes from Emil Kowalski's design engineering philosophy.

Do not provide any other information until the user asks a question.

A fix-it skill. It does ONE thing: take a web app that feels like a website on a phone and remove, one by one, the tells that give it away. It does not design motion (that's `animate`), review motion (that's `review-animations`), or build for React Native (that's `animate-expo`). The rules here are about the platform layer — viewport, touch, scroll, safe areas, the browser chrome — where a handful of lines decide whether the app feels installed or embedded.

<critical>

1. **Every fix ships with the reason.** Each rule below has a *why*. Apply it where the why applies, not globally out of habit — `user-select: none` on body text is a defect, on a button it's correct.
2. **Media queries over device sniffing.** `(hover: hover)`, `(pointer: fine)`, `env()`, `dvh` — the platform tells you what it can do. Never branch on user agent strings or screen width to guess at touch.
3. **Touch and mouse are not exclusive.** iPads with trackpads, laptops with touchscreens, phones with a mouse. Write for both at once; gate by capability, not by device.
4. **Never disable zoom.** `user-scalable=no` and `maximum-scale=1` are accessibility failures. Fix the input font size instead, which is what was causing the zoom.
5. **Test on hardware before calling it done.** Connect the phone, open the dev server by IP, use Safari's Web Inspector or Chrome remote debugging. Emulation can verify declarations and layout; tactile feel (sticky hover after a real tap, tap delay, rubber-banding), the mobile browser chrome (URL bar, safe areas, status bar), and the platform software keyboard need a device check.
</critical>

<instruction>

You are a senior design engineer who has shipped drawers, sheets, and gesture-driven UI to real phones and has been burned by every item below. You know that a desktop browser with the device toolbar on is not a phone. You know that most "the app feels janky on mobile" reports are not animation problems — they're a 300ms tap delay, a gray flash on tap, or a hover state that won't let go.

The user's phone is the source of truth. If you can't run it on hardware, say which fixes you can verify from code and which need a real device. Check code-verifiable declarations in a running Chromium page: open the dev server with `app: { tern: false }`, call `tab.emulate({ device: "iPhone 15 Pro" })` (`tab.devices()` lists names), then read computed values with `tab.styles(selector, [props])` — input `font-size` at least 16px, `touch-action`, `-webkit-tap-highlight-color` — and confirm hover styles gated on `(hover: hover)` no longer apply. Tern's device mode changes viewport and user agent but not touch capabilities, so it cannot prove the hover check. A clean emulated run proves the declarations shipped, not that the phone feels right; hardware-only items stay open.

Two failure modes, and the first is worse:

1. **Fixing what the desktop shows you.** Chrome's device emulation checks declarations and layout, not touch feel, mobile browser chrome, or the platform keyboard. If you only test there, you ship the bugs it cannot show.
2. **Reaching for JavaScript when CSS or a meta tag does it.** Almost every item here is one declaration. A `useIsTouchDevice()` hook to hide hover states is the wrong tool; a media query is the right one.
</instruction>

## Self-Check

Run this before you finish.

| Never | Instead |
| --- | --- |
| `user-scalable=no` or `maximum-scale=1` | 16px inputs — fix the cause |
| Ungated `:hover` | `@media (hover: hover)` |
| `100vh` for an app shell or bottom-pinned UI | `100dvh` |
| `100dvh` on a marketing hero | `100svh` (no layout shift on scroll) |
| Press feedback on `click` only | `:active` / `pointerdown` feedback; the action stays on `click` |
| `touchmove` + `preventDefault()` to stop overscroll | `overscroll-behavior` |
| `user-select: none` on `body` | Only on controls |
| `touch-action: none` on something the user needs to scroll or zoom | `pan-x pinch-zoom` / `pan-y pinch-zoom` |
| `env(safe-area-inset-*)` without `viewport-fit=cover` | Add the meta tag or the value is `0` |
| One `theme-color` for both schemes | One per `prefers-color-scheme` |
| User-agent sniffing to detect touch | `(hover)` / `(pointer)` media queries |
| Declaring it fixed from device emulation | Real hardware |

## The Symptom Table

Start here. Match what the user is seeing, then read the matching section for the why and the exact code.

| Problem | Solution |
| --- | --- |
| Hover state stuck after tap | Wrap in `@media (hover: hover)` |
| Gray/blue flash on tap | Kill `-webkit-tap-highlight-color` |
| Layout has wrong height | `100dvh` (app) or `100svh` (hero) |
| Page zooms into input | Input font size 16px at the minimum |
| Tap feels laggy | Press feedback on pointer-down (action stays on `click`) + `touch-action: manipulation` |
| Pull-to-refresh hijacks scroll | `overscroll-behavior: none` on `html, body` |
| Content stops at the notch | `viewport-fit=cover` + `env(safe-area-inset-*)` |
| Long-press selects button text | Add `user-select: none` |
| Carousel scrolls vertically | Native scroller: scroll-snap, keep native horizontal panning · JS drag: `touch-action: pan-y pinch-zoom` on the gesture surface |
| Status bar color doesn't match | `theme-color` per color scheme |
| Right in Chrome, wrong on phone | Test on real hardware |

## The Fixes

### 1. Hover state stuck after tap

Touch has no hover, so browsers fake one: the first tap on an element applies `:hover` and leaves it there until the user taps somewhere else. A button that scales up on hover stays scaled up after being tapped. Gate every hover style behind a capability query.

```css
@media (hover: hover) {
  .button:hover {
    background: var(--gray-3);
    transform: scale(1.02);
  }
}
```

`(hover: hover)` means the primary input can hover, which is all a hover effect needs. `(pointer: fine)` describes the primary pointer's accuracy, not the device: mice, touchpads, and drawing styluses all report `fine`, and a stylus can also hover. Add `and (pointer: fine)` only when the effect itself depends on precise pointing, never as a touch filter. In Tailwind v4 the `hover:` variant already compiles to `@media (hover: hover)` — hover capability only, no pointer condition; in v3 set `future.hoverOnlyWhenSupported`.

Touch users still need press feedback. Give it to them through `:active` (see §5), and check it on each target platform: whether and when `:active` shows on touch varies by browser and input.

### 2. Gray/blue flash on tap

iOS Safari and Android Chrome paint a translucent highlight over any tapped element that has a click handler. It's the single loudest "this is a website" signal, and it fights whatever press feedback you designed.

```css
html {
  -webkit-tap-highlight-color: transparent;
}
```

Set it once, globally. Then make sure every tappable element has its own `:active` state, because you've just removed the only feedback the browser was giving.

### 3. Layout has the wrong height

`100vh` on mobile is the *largest* viewport — the height with the browser chrome collapsed. On page load the URL bar is visible, so a `100vh` element overflows by the height of that bar, and a bottom-pinned button sits under it. Use the dynamic and small units instead:

```css
/* App shell, drawers, anything that should track the visible area as chrome shows/hides */
.app { height: 100dvh; }

/* Heroes and first screens — the smallest the viewport gets, so nothing is ever cut off */
.hero { min-height: 100svh; }
```

`dvh` resizes as the URL bar collapses, which is right for an app shell but causes layout shifts on marketing content mid-scroll. `svh` is stable and never overflows, which is right for a hero. `lvh` is the old `vh` — you almost never want it. Keep a `100vh` fallback line above for old browsers only if the project's support matrix demands it.

### 4. Page zooms into the input

iOS Safari can zoom the page when focus lands on an input whose computed font size is under 16px. Fix the input's text size rather than suppressing focus zoom with `maximum-scale=1` (Hard Rule 4).

```css
input, textarea, select {
  font-size: 16px; /* the minimum; 1rem at the default root size */
}
```

If the design calls for smaller text in inputs on desktop, scale it up only where it matters:

```css
@media (pointer: coarse) {
  input, textarea, select { font-size: 16px; }
}
```

While you're in the inputs, set the keyboard: `inputmode="numeric"` for codes, `inputmode="decimal"` for amounts, `type="email"` and `type="tel"` for their fields, `autocapitalize="none"` and `autocorrect="off"` on usernames and codes, `enterkeyhint="send"` / `"search"` / `"done"` so the return key says what it does.

### 5. Tap feels laggy

Two separate causes stack here.

**The double-tap delay.** A browser may wait after a tap to distinguish a second tap for zooming. WebKit's [fast-tap behavior](https://webkit.org/blog/5610/more-responsive-tapping-on-ios/) gives `width=device-width` pages fast taps at the initial scale; `touch-action: manipulation` removes the double-tap delay at other zoom levels too, while preserving pinch zoom:

```css
button, a, [role="button"], .tappable {
  touch-action: manipulation;
}
```

**Feedback on release instead of press.** Native buttons respond the instant your finger lands. A web button that only changes on `click` responds when your finger *leaves*, which reads as lag even at 0ms. Style `:active`. If you need JavaScript feedback, set a pressed state on `pointerdown` and clear it on `pointerup`, `pointercancel`, and `pointerleave`. That is feedback, not activation: use semantic controls and keep the action on their native `click` or form submission so keyboard activation remains available. Custom handlers must support cancellation and reject an out-of-bounds release. Never submit or navigate on `pointerdown`.

```css
.button {
  transition: transform 100ms var(--ease-out), background 100ms;
}
.button:active {
  transform: scale(0.97);
  background: var(--gray-4);
}
```

Keep press feedback at 100–160ms and `ease-out`. If the codebase uses the `animate` skill's tokens, use them; don't fork a new curve.

### 6. Pull-to-refresh hijacks scroll

Scrolling past the top of the page triggers pull-to-refresh on Android Chrome and the whole-page rubber band on iOS. Fine on a document. Wrong in an app with its own scroll containers, a drawer the user drags down, or a canvas.

```css
html, body {
  overscroll-behavior: none;
}
```

Then, on any inner scrollable — a sheet's content, a chat list, a sidebar — stop scroll from chaining to the page when it hits the end:

```css
.sheet-content {
  overflow-y: auto;
  overscroll-behavior: contain;
}
```

`contain` keeps the container's own bounce (which feels native) but stops the page behind it from moving. Use `none` on the root, `contain` on children. Never reach for a `touchmove` + `preventDefault()` listener for this — it blocks scrolling entirely and makes the listener non-passive, which costs frames.

### 7. Content stops at the notch

By default the browser letterboxes your page inside the safe area, leaving the notch, Dynamic Island, and home-indicator zones the body's background color. A native app paints edge to edge and pads its *content* away from those zones. Two steps:

```html
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
```

```css
.app-header {
  padding-top: env(safe-area-inset-top);
}
.bottom-bar {
  padding-bottom: env(safe-area-inset-bottom);
}
.sheet {
  padding-bottom: calc(1rem + env(safe-area-inset-bottom));
}
```

`viewport-fit=cover` lets the page under the notch; `env(safe-area-inset-*)` gives you the insets to pad back out. Without the meta tag the `env()` values are all `0px`. Fixed headers, bottom tab bars, toasts, and sheets are the elements that need this; normal page content usually gets it for free through the header's padding. Give `env()` a fallback (`env(safe-area-inset-bottom, 0px)`) when the value is used in a calc.

### 8. Long-press selects button text

Hold a finger on a web button and iOS selects its label, or pops the copy/share callout on a link. Native controls never do that. Text that is a *control* shouldn't be selectable; text that is *content* must stay selectable.

```css
button, [role="button"], .tab, .chip, .drag-handle {
  user-select: none;
  -webkit-user-select: none;   /* Safari still needs the prefix */
  -webkit-touch-callout: none; /* no long-press callout on links/images used as controls */
}
```

Never put `user-select: none` on `body`. Users copy addresses, error messages, and order numbers; that is content.

### 9. Carousel scrolls vertically

A horizontal swipe on a carousel is ambiguous to the browser — it doesn't know whether you're scrolling the page or the track, so it guesses, and the guess is often the page jittering up while the carousel moves. First decide who owns the horizontal movement.

**Native scroller** (an `overflow-x: auto` track): the browser owns horizontal panning. Use `scroll-snap-type: x mandatory` on the track and `scroll-snap-align: start` on slides — the browser's own physics beat a hand-rolled spring. Leave `touch-action` at its default; never set `pan-y` on the track or its slides, because that removes the horizontal panning the track scrolls with.

**JS-owned drag** (pointer events move the track): tell the browser which axes it keeps:

```css
.drag-carousel {
  touch-action: pan-y pinch-zoom; /* JS handles horizontal; the browser keeps vertical and pinch */
}
.drag-surface {
  touch-action: pinch-zoom;       /* a custom gesture (a drag-to-dismiss sheet, a slider) owns both pan axes; pinch stays with the browser */
}
.vertical-sheet-handle {
  touch-action: pan-x pinch-zoom; /* the sheet handles vertical drags; horizontal and pinch stay with the browser */
}
```

The values name what the *browser* may still do. `pan-y pinch-zoom` on a JS-dragged carousel means "browser, you keep vertical panning and zoom; I'm handling horizontal". Always list `pinch-zoom`: any value without it — `pan-x`, `pan-y`, and especially `none` — also disables pinch-zoom on that element, which is the same accessibility failure as `user-scalable=no` (Hard Rule 4). `none` means the element handles everything, pinch included — use it only on an element that ships its own equivalent zoom control (zoom buttons, a scale slider), or the user can neither zoom nor scroll past it.

### 10. Status bar color doesn't match

The status bar and the browser chrome take their color from `theme-color`. One value means light mode gets a dark bar or dark mode gets a white one. Give each scheme its own:

```html
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#ffffff" />
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#0a0a0a" />
<meta name="color-scheme" content="light dark" />
```

Match the value to the color at the very top of your page — the header background, not the brand color. In Next.js set it through the `viewport` export (`themeColor: [{ media, color }]`). If the app switches theme with a class rather than the OS setting, update the tag from JavaScript on toggle. For an installed PWA, `apple-mobile-web-app-status-bar-style` and the manifest's `theme_color`/`background_color` are the same decision.

### 11. Right in Chrome, wrong on phone

Emulation verifies declarations and layout: computed styles, media-query gating, which viewport unit a layout uses, how it reflows at a phone's width. It cannot show tactile feel — sticky hover after a real tap, the tap highlight, the click delay, rubber-banding and overscroll — the mobile browser chrome — the URL bar's effect on `vh`, safe areas, the status bar — or the platform software keyboard and the input zoom it triggers. Those need a device.

- Connect the phone over USB, run the dev server on `0.0.0.0`, open it by the machine's LAN IP.
- iOS: Safari → Develop → the device. Android: `chrome://inspect`.
- Test on a phone that's a few years old, not the newest one on your desk. Test with the keyboard open. Test in landscape once.
- Test as an installed PWA if that's a target; standalone mode changes viewport, safe areas, and status bar behavior.

The Xcode Simulator is a step up from emulation but still misses touch feel. Real hardware is the bar.

## Baseline

When starting a mobile-facing app, this is the floor. Ship it before the first component:

```html
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content" />
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#ffffff" />
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#0a0a0a" />
```

```css
html {
  -webkit-tap-highlight-color: transparent;
  -webkit-text-size-adjust: 100%;
  overscroll-behavior: none;
}

input, textarea, select {
  font-size: 16px;
}

button, a, [role="button"] {
  touch-action: manipulation;
  user-select: none;
  -webkit-user-select: none;
}

@media (hover: hover) {
  /* all :hover rules live here */
}
```

`interactive-widget=resizes-content` is Android Chrome behavior: the software keyboard shrinks the layout viewport, so `100dvh` and bottom-pinned inputs move above it. iOS Safari does not do this. Only the visual viewport shrinks, while viewport units and `position: fixed` elements can stay where they were, behind the keyboard. Handle iOS separately: read `window.visualViewport` `height`/`offsetTop` on its `resize` and `scroll` events to reposition bottom-pinned UI, and verify on a real iPhone with the keyboard open. Drop `overscroll-behavior: none` from `html` if the app is a scrolling document where pull-to-refresh is welcome.

## Output

Apply the fixes. Then, in at most a few lines:

- **What was wrong** — the symptom matched from the table, and the one-line why.
- **What changed** — file and declaration, one line each.
- **What needs a phone** — which fixes you could verify from code and which the user must confirm on hardware.

Don't pad this into a report. The code is the deliverable.

## Tone

Opinionated and brief. Most of these are one line; say the line and the reason and move on. When the honest answer is "I can't verify this without a device," say that instead of claiming it's fixed.

<critical>
- NEVER disable zoom (`user-scalable=no`, `maximum-scale=1`); MUST fix input font size instead.
- MUST gate every `:hover` rule behind `(hover: hover)`; NEVER require `(pointer: fine)` unless the effect needs precise pointing.
- MUST handle the iOS keyboard via `visualViewport`; `resizes-content` covers Android only.
- NEVER claim device-only behavior verified from emulation; MUST separate code/layout checks from hardware checks.
</critical>

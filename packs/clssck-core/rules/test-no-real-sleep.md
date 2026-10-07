---
description: Do not use real sleeps in Python or Rust tests; wait on the condition or control time
condition:
  - '\b(?:time|asyncio)\.sleep\((?![ \t]*0[ \t]*\))'
  - '(?:^|[^\w.])sleep\([ \t]*(?!0[ \t]*\))\d'
  - '\bthread::sleep\('
  - '\btokio::time::sleep\('
scope:
  - tool:edit(**/{test_*.py,*_test.py,tests/**/*.py,test/**/*.py,conftest.py})
  - tool:write(**/{test_*.py,*_test.py,tests/**/*.py,test/**/*.py,conftest.py})
  - tool:edit(**/{tests/**/*.rs,*_test.rs,*_tests.rs,tests.rs})
  - tool:write(**/{tests/**/*.rs,*_test.rs,*_tests.rs,tests.rs})
interruptMode: never
---

**A fixed sleep guesses how long something takes.** It makes every run slower, and under load it still loses the race and flakes.

- Wait on the actual signal: join the thread or task, await the future, receive from the channel, or poll the condition with a bounded deadline.
- Control time instead of passing it:
  - Python: inject a clock, use `freezegun`/`time-machine`, or `asyncio` events and `asyncio.wait_for(..., timeout=...)` as a ceiling, not a delay.
  - Rust/Tokio: `#[tokio::test(start_paused = true)]` with `tokio::time::advance`; for threads, a `Barrier`, channel, or `Condvar`.
- A genuine real-time integration test may need a delay. Keep it rare and add a comment naming why deterministic control will not work.

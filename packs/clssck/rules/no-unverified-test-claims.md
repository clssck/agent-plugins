---
description: "Claims that tests, builds, or checks pass must cite the run: command and result"
condition: "(?i)(?=[\\s\\S]*\\b(?:tests?|builds?|type[- ]?checks?|lint(?:s|ing)?|checks?|vitest|pytest|jest|mocha|tsc|eslint|mypy|clippy)\\b)(?=[\\s\\S]*\\b(?:pass(?:es|ed|ing)?|succeed(?:s|ed)?|green|clean)\\b)"
question: "Does the reply assert that tests, a build, a typecheck, lint, or another check actually passed, while omitting the command that was run or a concrete result such as pass/fail counts or an exit code? Answer no when the reply asserts no observed pass: expected or hypothetical outcomes such as 'should pass' or 'will pass', and checks reported as failed, skipped, or not run. Answer no when every pass claim names both the command and a concrete result. Answer yes when any pass claim lacks the command or the result, even if the reply also reports other checks as failed or not run."
scope: "text"
---

Back every pass claim with its evidence in the same reply: the command you ran and its result (counts, exit code). If you did not run it, say so.

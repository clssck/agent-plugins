---
description: "Claims that tests, builds, or checks pass must cite the run: command and result"
condition: "(?i)\\b(tests?|build|typecheck|lint|smoke[- ]test|checks?)\\b[^.\\n]{0,40}\\b(pass(es|ed|ing)?|succeed(s|ed)?|green|clean)\\b"
question: "Does the reply say that tests, a build, a typecheck, lint, or another check passed while naming neither the command that was run nor a concrete result such as pass/fail counts or an exit code? Answer no if the reply names the command or gives such a result."
scope: "text"
---

Back every pass claim with its evidence in the same reply: the command you ran and its result (counts, exit code). If you did not run it, say so.

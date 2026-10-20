---
description: "Tests must exercise behavior, never read implementation source and assert on its text"
condition: "readFile|Bun\\.file\\(|\\.text\\(\\)|readFileSync"
question: "Does this test read an implementation source file (.ts, .rs, a build script) and assert on its text, such as toContain or toMatch on the source, instead of running the code and checking its output, state, or errors?"
scope: "tool:write(*.test.ts), tool:edit(*.test.ts), tool:write(*.test.tsx), tool:edit(*.test.tsx)"
---
<critical>

Never source-grep. Run the code and assert the observable contract: output, state, or surfaced error. Reading a file the code under test wrote is fine; reading the implementation to check how it looks is not.
</critical>

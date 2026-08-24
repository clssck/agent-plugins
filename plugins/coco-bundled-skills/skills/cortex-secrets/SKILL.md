---
name: cortex-secrets
description: "MUST consult whenever any command needs a credential, secret, API key, token, or password — whether discovered from an error, source code, --help output, or any other signal. MUST also consult when the user shares, pastes, or includes a secret value directly in their message. Also use when: the user asks about /secrets, storing credentials, secret scopes, or consent modes. Triggers: secret, secrets, /secrets, API key, credential, token, password, authentication, unauthorized, 401, 403, forbidden, EACCES, permission denied, access denied, missing key, invalid token, auth error, connection refused, login failed, .env, environment variable, env var, keychain, export SECRET, cortex secret list, inline secret injection, pasted secret, shared secret, my key is, my password is, my token is, here is my, use it to."
---

# Secrets Management

This skill extends the bash tool's `# Secrets` section with the full credential workflow, security protocols, and user-facing guidance.

The bash tool teaches the injection mechanics: `VAR="<key>"` prefix syntax, `cortex secret list`, and `/secrets`. This skill covers **when and how to apply them**, plus what to do when things go wrong (auth errors, missing secrets, pasted credentials).

---

## When to Use

- A command, script, or tool needs a credential, API key, token, or password
- A tool fails with an authentication or permission error (401, 403, EACCES, etc.)
- A tool's `--help` output reveals required environment variables
- The user asks how to store or manage credentials
- The user pastes a secret value in chat

---

## Workflow

**Whenever a command needs a credential** -- whether discovered from an error, from reading source code, from `--help` output, or from any other signal:

1. Run `cortex secret list` silently to check existing secrets (agent-internal -- do NOT show or mention this command to the user)
2. If a match exists, re-run the command using the inline injection syntax from the bash tool: `VAR="<key>" my-command`
3. If no match, direct the user to add it via `/secrets`, then ask them to retry

**NEVER skip step 1.** Always check for existing secrets before suggesting the user add one.

### Tool Discovery

When running an unfamiliar CLI tool for the first time, run `tool --help` to discover which env vars or credentials it expects, then follow the workflow above.

**Sandbox environments**: If the system prompt indicates you are running in a Cortex Code sandbox / Linux VM, consult the `cortex-code-sandbox` skill for the proxy-managed credential workflow.

---

## Security Rules

These rules extend the bash tool's `NEVER` directives:

- NEVER ask the user to paste or share a secret in chat -- direct them to `/secrets`
- NEVER suggest `export VAR=value`, manual env var setup, or writing to `.env` files
- NEVER write secrets into config files or any file on disk
- Never use `echo`, `env`, `printenv`, or any command that would print a secret value
- Never show the `VAR="<key>"` injection syntax or `cortex secret` commands to the user -- these are agent-internal mechanics
- The user-facing interface is ONLY `/secrets`

---

## If the User Pastes a Secret in Chat

1. **Stop** -- do NOT use the value
2. **Warn**: the secret is now recorded in the conversation transcript and has been sent to the server -- it cannot be unsent
3. **Tell them to run `/wipe-session`** to delete local session files and exit
4. **Recommend** rotating the compromised secret immediately
5. **Direct them to `/secrets`** as the correct way to provide credentials going forward
6. Do not repeat or reference the pasted value

---

## /secrets Slash Command

```
/secrets
```

Opens the interactive secret manager where the user can:

- **Add** a new secret (user or session scope)
- **Delete** an existing secret
- **View** stored secret names (values are never displayed)

Values are entered through a masked input field that prevents them from appearing in the conversation.

---

## Secret Scopes

| Scope | Storage | Lifetime | Default consent |
|-------|---------|----------|-----------------|
| **User** | OS keychain | Persistent across sessions | `once` -- prompt once per session |
| **Session** | In-memory | Current session only | `never` -- inject silently |

---

## Consent Modes

| Mode | Behavior |
|------|----------|
| `once` | Prompt the first time per session, then allow silently |
| `always` | Prompt every time the secret is used |
| `never` | Inject silently without prompting |

The user chooses the consent mode when adding a secret via `/secrets`.

---

## Stopping Points

- After step 1 (checking `cortex secret list`): if no matching secret exists, stop and direct the user to `/secrets` before retrying
- If the user pastes a secret in chat: stop immediately, warn, and do NOT proceed with the value

---

## Output

This skill does not produce artifacts. It guides the agent's behavior when credentials are involved, ensuring secrets are managed through `/secrets` and injected securely via the bash tool's inline `"<key>"` syntax.

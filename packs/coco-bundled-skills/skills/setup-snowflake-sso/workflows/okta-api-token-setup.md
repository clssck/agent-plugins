# Okta API Token Setup

This workflow is referenced by Okta workflows when the user selects the Automated (API) or Self-service API method. Follow this flow to ensure the token is available before proceeding with the calling workflow.

---

## Check if Token is Already Set

If the user selected an API-based method for an Okta workflow, first check if the token is available:

```bash
echo "${OKTA_API_TOKEN:+Token is set}" || echo "Token is NOT set"
```

If the token is already set, skip to the workflow steps.

---

## If Token is Not Set: Guide the User

```python
AskUserQuestion(
  questions=[{
    "question": "Do you have an Okta API token ready?",
    "header": "API Token",
    "multiSelect": false,
    "options": [
      {"label": "Yes, I have one", "description": "I have an API token ready to use"},
      {"label": "No, I need to create one", "description": "Guide me to create an Okta API token"}
    ]
  }]
)
```

**If "No, I need to create one"**, provide instructions:

> **Creating an Okta API Token:**
> 1. Sign in to your Okta Admin Console
> 2. Go to **Security > API > Tokens**
> 3. Click **Create Token**
> 4. Name it (e.g., "Snowflake SSO Setup")
> 5. Copy the token value immediately (it won't be shown again)

---

## Set Environment Variables

Once the user has a token, instruct them to set the required environment variables:

> **Important Security Notice:**
> - **Do NOT paste your API token in this chat** — chat history may be logged or visible to others
> - **Do NOT write the token to disk** (e.g., `.bashrc`, `.zshrc`, or any file) — it should only exist in memory
>
> Instead, set your token and Okta domain as environment variables directly in your terminal. This keeps the token secure and session-only.
>
> **Instructions:**
> 1. Exit Cortex Code by pressing `Ctrl+C` or typing `/exit`
> 2. Run these commands in your terminal (replace with your actual values):
>    ```bash
>    export OKTA_API_TOKEN="your-token-here"
>    export OKTA_DOMAIN="your-domain.okta.com"
>    ```
> 3. Restart Cortex Code by running `cortex`
> 4. Resume this workflow
>
> The variables will only exist in memory for this terminal session and will be gone when you close the terminal.

**Do NOT ask the user to confirm** — they will need to restart Cortex Code, which ends this session. Simply provide the instructions above and let the user know they can resume the workflow after restarting by asking to continue with SSO setup.

**Note for Automated (API) path:** The agent uses `$OKTA_API_TOKEN` and collects the Okta domain interactively (or from `$OKTA_DOMAIN` if set).

**Note for Self-service (Curl) path:** All curl commands reference `$OKTA_API_TOKEN` and `$OKTA_DOMAIN` so they can be copy-pasted directly without manual substitution.

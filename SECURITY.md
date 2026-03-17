# Security

## Secrets and API Keys

**Never commit API keys, passwords, or tokens to the repository.**

- Store secrets only in `backend/.env` (gitignored)
- Copy from `backend/.env.example` and fill in real values locally
- Do not paste secrets in chat, email, or public places
- If a key is exposed: revoke it immediately in the provider console and create a new one

### Sensitive Environment Variables

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Anthropic Claude API |
| `GROQ_API_KEY` | Groq LLM API |
| `JIRA_USERNAME` | Jira authentication |
| `JIRA_PASSWORD` | Jira authentication |

## Configuration

- `.env` and `*.env` are in `.gitignore` – never remove them
- Use `backend/.env.example` as a template; it contains placeholders only
- For production, use a secrets manager (e.g. AWS Secrets Manager, Vault)

## Error Handling

- API keys are never logged or returned in error responses
- Validation errors mention variable names (e.g. "GROQ_API_KEY is not set") but never values

# GitHub Environment and Secret Setup

Automatic setup could not be executed on this host because `gh` is not installed and package managers are unavailable.

Use these commands on a machine with GitHub CLI authenticated to your account:

```bash
gh auth login

# Create environments (idempotent API call style via CLI fallback)
gh api -X PUT repos/sujalsune92/SAR/environments/staging
gh api -X PUT repos/sujalsune92/SAR/environments/production

# Add required repository secrets
gh secret set KUBE_CONFIG_STAGING_B64 --body "$(base64 -w0 ~/.kube/config-staging)"
gh secret set KUBE_CONFIG_PRODUCTION_B64 --body "$(base64 -w0 ~/.kube/config-production)"
gh secret set SLACK_WEBHOOK_URL --body "https://hooks.slack.com/services/..."

# Enforce required reviewers for production approvals
# Replace USER_OR_TEAM_ID with a valid reviewer ID in your org/user context
gh api -X PUT repos/sujalsune92/SAR/environments/production \
  -f wait_timer=0 \
  -F prevent_self_review=true \
  -f reviewers[][type]=User \
  -f reviewers[][id]=USER_OR_TEAM_ID
```

If you prefer UI:

1. GitHub repo -> Settings -> Environments.
2. Create `staging` and `production`.
3. On `production`, enable required reviewers.
4. Repo Settings -> Secrets and variables -> Actions: add `KUBE_CONFIG_STAGING_B64`, `KUBE_CONFIG_PRODUCTION_B64`, `SLACK_WEBHOOK_URL`.

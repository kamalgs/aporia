# Contributing to Aporia

## Workflow: Branch → PR → Merge

`master` is **protected** by GitHub branch protection rules. Direct pushes are blocked. Every change must go through a branch → PR → merge workflow. Even the repo owner must open a PR.

### 1. Create a feature branch

```bash
git checkout -b feature/my-thing
```

### 2. Make changes, test, commit

```bash
# Backend tests
uv run pytest -v

# Frontend e2e smoke tests (needs local backend running)
cd frontend
npm run dev      # in another terminal
npx playwright test --project=chromium
```

```bash
git add -A
git commit -m "feat: what this does"
```

### 3. Push branch and open PR

```bash
git push -u origin feature/my-thing

# Open PR (gh CLI)
gh pr create --title "feat: what this does" --body "Brief description"
```

### 4. Merge via GitHub UI or gh CLI

```bash
gh pr merge --squash --delete-branch
```

### Pre-commit checklist

- [ ] `uv run pytest -v` passes (backend black-box tests)
- [ ] `cd frontend && npx tsc --noEmit` passes (TypeScript)
- [ ] `cd frontend && npx playwright test` passes (e2e smoke tests against local backend)
- [ ] Docker image builds: `docker build -t aporia:local .`
- [ ] Nomad job plans cleanly: `cd ~/projects/nomad/jobs && terraform plan -target nomad_job.aporia`

## LLM provider setup

The app auto-detects the API key format:
- `sk-or-v1-*` → OpenRouter
- `fw-*` or `sk-1*` → Fireworks AI native

Set in `~/projects/nomad/jobs/terraform.tfvars`:
```hcl
fireworks_api_key = "your-key"
aporia_model      = "accounts/fireworks/models/llama-v3p1-405b-instruct"
```

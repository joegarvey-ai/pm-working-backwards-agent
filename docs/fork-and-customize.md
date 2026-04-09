# Fork and Customize

This guide explains how to fork the PM Working Backwards Agent for your company or team, add company-specific content, and stay up to date with upstream improvements.

## Why Fork?

The public repo is a generic template. To get the most value, you'll want to add:
- Your company's style guide
- Stakeholder avatars (profiles of key decision-makers)
- Internal document references
- Custom theme configuration for your product domain
- Company-specific AWS account defaults

This content should never be pushed to a public repo.

## Setup

### 1. Fork the repo
Click "Fork" on GitHub, or clone and push to your own private repo.

### 2. Choose your privacy level

**Personal use** (just you):
```bash
cat .gitignore.private >> .gitignore
git add .gitignore
git commit -m "Add private gitignore rules"
```

**Team use** (shared with colleagues):
```bash
cat .gitignore.team >> .gitignore
git add .gitignore
git commit -m "Add team gitignore rules"
```

### 3. Add your company content

**Style guide:**
Copy `samples/style-guide-sample.md` to `samples/my-style-guide.md` and customize it for your company's voice. Update `STYLE_GUIDE_PATH` in `.env` to point to your version.

**Stakeholder avatars** (personal fork only):
Create `config/stakeholder_avatars/` and add one YAML file per stakeholder:
```yaml
name: "VP of Engineering"
role: "Engineering leadership"
goals:
  - Ship on time
  - Reduce technical debt
fears:
  - Scope creep mid-sprint
  - Unfunded mandates from product
incentives:
  - Team velocity metrics
  - Production incident rate
known_phrases:
  - "What's the engineering cost?"
  - "Is this sized for one sprint?"
likely_objections:
  - Will push back on anything without clear acceptance criteria
  - Wants to see the technical context section before approving scope
historical_positions:
  - Blocked the last integration project due to missing NFRs
```

**Theme configuration:**
Create `config/themes.json` with themes relevant to your product domain.

### 4. Pulling upstream updates

Add the original repo as an upstream remote:
```bash
git remote add upstream https://github.com/joegarvey-ai/pm-working-backwards-agent.git
```

Pull updates periodically:
```bash
git fetch upstream
git merge upstream/main
```

Your company-specific files are in `.gitignore`, so they won't conflict with upstream changes. If there are merge conflicts in README.md or other shared files, resolve them manually.

## What Goes Where

| Content | Where it lives | In .gitignore? |
|---|---|---|
| Agent configs (agents.yaml, tasks.yaml) | `src/pm_agent_system/config/` | No — these are part of the system |
| Your style guide | `samples/my-style-guide.md` | Yes (.private and .team) |
| Stakeholder avatars | `config/stakeholder_avatars/` | Yes (.private) / Partial (.team) |
| Internal reference docs | `internal_docs/` | Yes (.private and .team) |
| Pipeline output | `output/` | Yes (.private and .team) |
| Theme config | `config/themes.json` | No — useful for the team |
| API keys | `.env` | Yes (always) |

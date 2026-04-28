---
title: "PM Pilot: Getting Started with the Agentic PM Assistant"
type: getting-started
audience: PM pilot users
status: living-document
created: 2026-04-24T22:24:30.460046+00:00
last_updated: 2026-04-28T00:00:00.000000+00:00
tags:
  - pm-agent
  - pilot
  - getting-started
  - onboarding
  - living-document
aliases:
  - "PM Pilot Onboarding"
  - "Getting Started Guide"
---

> **This is a living document.** It gets updated every time we push code changes that affect the setup, commands, or user experience. If something in here is out of date, ping Joe.

# PM Pilot: Getting Started with the Agentic PM Assistant

## What this is

You are piloting a system that takes a product problem statement and produces, in sequence:

1. A **research brief** with real market data, competitors, and customer quotes
2. A **PRFAQ** (Working Backwards document) with a data handling enumeration, ready for VP alignment
3. A **BRD** with engineer-ready requirements, real AWS pricing data, AND a compliance workstream covering data classification, vendor considerations, privacy, compliance gates, and launch readiness
4. A **Kiro spec** that Kiro can turn into a working prototype, with a STRIDE threat model stub and RACI matrix when the product handles sensitive data or depends on a vendor

Four specialized agents do the research, writing, and formatting. The BRD stage runs three parallel subagents (structure, cost and risk, compliance) whose outputs merge into the final BRD. You review and approve at each step. You stay in the loop end to end. Nothing ships without you saying yes.

## What you will do by the end of this guide

- Have every tool installed and every account created
- Run a 2-minute research brief on a demo input (cheap, low-risk first run)
- Run the full pipeline against a demo input and get a Kiro spec as the final output
- Load the Kiro spec into Kiro and see it build a working prototype

**Expected time**: 10-20 minutes for setup if you follow this start to finish. Another 20-30 minutes for your first full-pipeline run plus Kiro prototype build.

## How to read this guide

Each section builds on the last. Start at Section 1. Every step that says "run this command" means literally copy the text in the gray box and paste it into your terminal, then press Enter. When something asks for a decision (Mac vs Windows, your own key vs Joe's), I'll tell you inline.

If you get stuck, the Troubleshooting section at the end covers every common issue. If that doesn't help, ping Joe directly.

---

## Section 1: Tech stack and prerequisites

Before you run any code, you need accounts and tools. Do these in order. Each item has a checkbox so you know where you are.

### 1.1 Accounts you need

- [ ] **AWS Bedrock access** (to run Claude Haiku, the LLM that does the thinking)
- [ ] **Tavily API key** (for web search and market research)
- [ ] **GitHub account** (to download the code)

### 1.2 Tools you need installed locally

- [ ] **Obsidian** (where your drafts and revisions live; this is where you'll do most of your reviewing)
- [ ] **A terminal application** (built into Mac; on Windows you use PowerShell or WSL)
- [ ] **Git** (to download and update the code)
- [ ] **Python 3.11 or newer**
- [ ] **uv** (a fast Python package manager)
- [ ] **Kiro** (where the Kiro spec becomes a working prototype at the end)

### 1.3 Account setup (do these first)

#### Tavily (web research)

1. Go to [tavily.com](https://tavily.com)
2. Click "Sign up" and create a free account
3. Once signed in, your API key is on the dashboard. It starts with `tvly-`
4. Copy the key and paste it somewhere you can find it later (Notes app, sticky, whatever). You'll need it in a few minutes.

The free tier includes 1,000 searches per month. A typical full-pipeline run uses 15-30 searches, so the free tier covers lots of pilot runs.

#### AWS Bedrock (the LLM)

This one takes more coordination. Two options:

**Option A (recommended for pilot)**: **Joe shares Bedrock credentials.** Ping Joe and ask for Bedrock pilot access. He can share a Bedrock API key that works for the pilot. This is the fastest path.

**Option B**: **Create your own Bedrock setup.** Only do this if you already have AWS account experience. You need:

- An AWS account with Bedrock enabled in `us-east-1` (or another US region where Claude Haiku 4.5 is available)
- A Bedrock API key (generate from the AWS Bedrock console under "API keys")
- Model access granted for `anthropic.claude-haiku-4-5-20251001-v1:0`

**If you pick Option A**, Joe will send you a Bedrock API key that starts with `bedrock-api-key-`. Paste it somewhere you can find it later, same as the Tavily key.

#### GitHub

If you don't already have a GitHub account, create one at [github.com](https://github.com). No special setup needed. You will not need to push anything; you only need an account to download the code.

### 1.4 Tool installs (do these second)

#### Install Obsidian

1. Go to [obsidian.md](https://obsidian.md) and download Obsidian for your OS (Mac or Windows).
2. Install it and open it.
3. When Obsidian asks about a vault, **create a new vault** called `PM Pilot` (or any name). Note the folder path where you save it. You'll need that path in Section 3.
   - On Mac, a common place is `~/Documents/PM Pilot`
   - On Windows, a common place is `C:\Users\YourName\Documents\PM Pilot`

A "vault" is just a folder of markdown files. Obsidian reads and writes them. That folder is where all your drafts, versions, and feedback will end up.

#### Open a terminal

The terminal is where you type commands. Don't be intimidated. You'll paste lines from this guide and press Enter; that's 95% of what you'll ever do.

**On Mac**:
1. Press `Cmd + Space`, type `Terminal`, press Enter.
2. A window opens with a prompt that looks like `YourName@YourMac ~ %`. That's your terminal.

**On Windows**:
1. Press the Windows key, type `PowerShell`, press Enter.
2. A window opens with a blue background and a prompt like `PS C:\Users\YourName>`. That's your terminal.
3. If you prefer WSL (Windows Subsystem for Linux) and already have it set up, use that instead. This guide assumes PowerShell for Windows.

Keep this window open. You'll use it for all the remaining steps.

#### Install Git

**Check if you already have it.** In your terminal, paste this and press Enter:

```bash
git --version
```

If you see something like `git version 2.39.1`, you already have Git. Skip ahead.

If you see "command not found" or similar:

**On Mac**: run this in the terminal:
```bash
xcode-select --install
```
A dialog will pop up. Click "Install" and wait (a few minutes).

**On Windows**: download the installer from [git-scm.com](https://git-scm.com/download/win) and run it. Accept all defaults. Close and reopen PowerShell after install.

#### Install Python

**Check if you already have it**:

```bash
python3 --version
```

or on Windows:

```bash
python --version
```

You need 3.11 or newer. If you see `Python 3.11.x` or higher, you're set. Skip ahead.

If not, or if your version is older:

**On Mac**: the easiest path is [python.org/downloads](https://www.python.org/downloads) - download the latest Python 3.x installer and run it.

**On Windows**: same link, [python.org/downloads](https://www.python.org/downloads), download and run the Windows installer. **Important**: during install, check the box that says "Add Python to PATH" before clicking Install.

Close and reopen your terminal after installing.

#### Install uv (the package manager)

`uv` is a tool that installs the Python libraries the pipeline needs. It is fast and reliable.

**On Mac**:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**On Windows** (PowerShell):
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

After it finishes, **close and reopen your terminal** so it picks up the new command. Then verify:

```bash
uv --version
```

You should see something like `uv 0.4.x`.

#### Install Kiro

1. Download Kiro from the Kiro website (Joe can share the internal link if you don't have it).
2. Install and open it.
3. You'll use Kiro at the end of the pipeline to turn your Kiro spec into a prototype.

### 1.5 Checklist before moving on

Before you go to Section 2, make sure:

- [ ] You have your Tavily API key (starts with `tvly-`) saved somewhere
- [ ] You have your Bedrock API key (starts with `bedrock-api-key-`) saved somewhere (ask Joe if you don't)
- [ ] Obsidian is installed and you've created an empty vault at a path you remember
- [ ] Your terminal is open
- [ ] `git --version`, `python3 --version` (or `python --version`), and `uv --version` all print version numbers
- [ ] Kiro is installed

If all six are checked, you're ready to move on.

---


## Section 4: Your first pipeline run (2-3 minutes, low risk)

Before running the full pipeline, do a tiny test run to confirm your setup works. This costs about $0.10 and takes 2-3 minutes.

### 4.1 Run the research agent on the demo input

The project ships with a demo input at `demo_input.yaml`. Run the research agent against it:

```bash
uv run pm_agent_system research demo_input.yaml
```

What happens:

1. The research agent reads the demo input (a product idea about an AI-powered customer support chatbot)
2. It calls Tavily to search the web for market data and competitors
3. It writes a research brief to `output/research_brief_*.md`
4. It copies the research brief to your Obsidian vault under `PM Agent/<product-slug>/`
5. The terminal shows a prompt asking you to review and approve

### 4.2 Review the research brief

When the terminal pauses at the checkpoint, look at the output path it prints. Open that file either:

- In your terminal (use `cat <path>` to print it, or `open <path>` on Mac)
- In Obsidian (open your vault, navigate to the `PM Agent` folder)
- In a text editor (navigate to `output/` inside the project folder)

Read the research brief. Does it cite actual sources? Does the market sizing include actual numbers? Are the competitors named ones you recognize?

### 4.3 Approve and finish

At the terminal prompt, type `a` and press Enter. This approves the research brief and finishes the run.

If it looks wrong, type `f` followed by your feedback text, and the agent will revise based on your input.

### 4.4 What you should see

- `output/research_brief_YYYYMMDD_HHMMSS.md` with the research content
- A cost summary at the end showing tokens used and dollar cost (~$0.10 for research only)
- Your Obsidian vault now has a new folder with the research brief and an `_index.md` file

### 4.5 If this worked, you're set

You've proven your entire setup works end-to-end. The full pipeline is the same thing but with three more stages.

If this did NOT work, scroll to Section 7: Troubleshooting.

---

## Section 5: Full pipeline run (end to end with Kiro prototype)

Now the real thing. This costs $0.60 to $1.20 per run (without design brief) and takes 15-30 minutes of LLM time plus however long you take on each review.

### 5.1 Choose your input

You have two options:

**Option A (easiest for the first full run)**: use the demo input. It's already written and produces a meaningful output.

```bash
uv run pm_agent_system full-pipeline demo_input.yaml --skip-design
```

**Option B (when you're ready for your own product)**: copy the template and fill it in.

```bash
cp examples/templates/input-brief-template.md input/my-product.md
```

Then open `input/my-product.md` in Obsidian (navigate to the file path in your Obsidian vault, or open it directly in a text editor). Fill in every section with as much detail as you can. The template has inline comments explaining what each section needs.

**Tip for good output**: describe what data the product will collect, process, store, or share. If you mention emails, session tokens, payment data, or anything a third party vendor touches, the compliance workstream picks it up automatically and classifies it. If you leave data handling vague, the BRD will flag it as a gap rather than guessing. See Section 5.6 for details.

Then run:

```bash
uv run pm_agent_system full-pipeline input/my-product.md --skip-design
```

**Why `--skip-design`?** The design brief stage (Agent 3) adds a design brief with screen inventory and user flows, but it also adds a checkpoint and extra time. For the pilot, skip it and let Agent 4 (BRD + build spec) go directly from the PRFAQ to the Kiro spec. You can try it with the design brief later.

**Note**: `--skip-design` does NOT skip the compliance workstream. Data classification, vendor considerations, privacy, compliance gates, and launch readiness still run inside the BRD stage regardless of whether you include the design brief.

### 5.2 What happens during the run

The pipeline runs four stages in order. After each stage (except the brief validation), it pauses and asks you to review and approve.

**Stage 1: Research** (~2-3 minutes of LLM time)
- External research (Tavily + competitive intel)
- Customer evidence (Dovetail, if enabled)
- Synthesis into a unified research brief
- Artifact: `output/research_brief_*.md`, vault copy in `PM Agent/<product-slug>/`
- **Checkpoint**: you review, approve (`a`) or give feedback (`f`)

**Stage 2: PRFAQ** (~2-3 minutes of LLM time)
- Takes the approved research brief
- Writes a full Working Backwards PRFAQ: press release, external/internal FAQs, customer experience narrative, appendices
- ALSO produces a data handling enumeration listing every data element the product collects, processes, stores, or transmits, each tagged with a classification (Public, Confidential, Highly Confidential, Restricted, or Critical)
- If your input brief didn't describe data handling, the PRFAQ flags it in `appendix_gaps` rather than guessing
- Artifact: `output/prfaq_*_v1.0.md`, vault copy
- **Checkpoint**: you review, approve or give feedback. You can also open the file in Obsidian, edit it directly, then type `o` at the checkpoint and the agent reads your edits

**Stage 3: BRD** (~3-5 minutes of LLM time)
- Takes the approved PRFAQ
- Produces the BRD via three parallel subagents:
  - **Structure**: user stories, functional requirements, acceptance criteria, technical context
  - **Cost and risk**: cost flags with actual AWS pricing data, risks, success metrics, timeline
  - **Compliance**: data classification summary, vendor considerations, privacy considerations, compliance gates (security, privacy, legal, procurement), launch readiness checklist, post-launch maintenance
- Merges all three into the final BRD (sections 1-12 from the original structure + cost-risk, plus new sections 13-18 from compliance)
- Also writes Jira/Linear import files automatically
- Artifact: `output/brd_*_v1.0.md`, `brd_*_jira_import.csv`, `brd_*_linear_import.md`
- **Checkpoint**: you review, approve or give feedback

**Stage 4: Build Spec (Kiro format)** (~2-3 minutes of LLM time)
- Takes the approved BRD
- Formats it as a Kiro spec with Requirements, Design, and Tasks sections
- When the BRD flags sensitive data (Confidential or higher) or third-party vendor involvement, the build spec ALSO appends a STRIDE threat model stub (six categories) and a RACI matrix. Both are produced deterministically from the BRD fields, not by the LLM, so they are consistent run over run.
- Artifact: `output/build_spec_*.md` (reference) and `output/build_spec_*_kiro.md` (tool-ready)
- **Checkpoint**: you review, approve

After all four stages approve, the pipeline prints a cost summary and timing breakdown.

### 5.3 Review checkpoints in detail

At each pause, you see a prompt like this (the exact wording in the CLI uses an em dash; here in the docs it reads equivalently):

```
PRFAQ draft published.
  -> output/prfaq_slug_v1.0.md
  -> PM Agent/slug/prfaq_slug_v1.0.md  (Obsidian)

Review the draft above or in Obsidian, then:
  [a]  Approve and continue
  [f]  Provide feedback (follow with your feedback text)
  [o]  I edited the file in Obsidian: read my changes and revise

>
```

You have three options at the prompt:
- Type `a` and press Enter to approve and move on
- Type `f` followed by specific feedback text, e.g. `f Make the competitive differentiation section tighter`. The agent revises and re-asks.
- Edit the file directly in Obsidian, save it, then type `o` at the prompt. The agent reads your edits and treats them as approved feedback.

### 5.4 Load the Kiro spec into Kiro

Once the pipeline finishes, the final artifact is `output/build_spec_*_kiro.md` (the file with `_kiro` in the name). That file is the Kiro spec.

1. Open Kiro
2. Create a new project (or open an existing one)
3. In Kiro, use the spec import feature. This is typically: File -> New Spec -> Import, or drag the markdown file into the Specs panel.
4. Kiro parses the Requirements, Design, and Tasks sections
5. Kiro can now generate the implementation from the spec

Kiro will ask you at each task before it writes code. You approve or redirect.

**STRIDE stub and RACI matrix** (if present): scroll to the bottom of the build spec file. When the BRD flagged sensitive data or a vendor scenario, you'll see a `## Threat Model (STRIDE Stub)` section with six categories (Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege) and a `## RACI Matrix` with rows for PM, Tech Lead, Engineer, Legal, Security, and Privacy. These are starting scaffolds. Your engineering partner fills in product-specific mitigations for each STRIDE category, and your team confirms the RACI assignments before launch.

### 5.5 What success looks like end-to-end

You started with a problem statement. In under an hour of elapsed time (about 10-15 minutes of active attention on your side), you have:

- A research brief with actual market data and customer evidence
- A stakeholder-ready PRFAQ with a data handling enumeration
- A BRD with requirements, acceptance criteria, pricing data, AND compliance sections covering data classification, vendor considerations, privacy, compliance gates, a launch readiness checklist, and post-launch maintenance
- A Kiro spec that Kiro turns into a running prototype, with a STRIDE threat model stub and RACI matrix when the product handles sensitive data or a vendor
- Jira/Linear import files if you want to spin up tickets

All copies are in your Obsidian vault under the product's folder, with wikilinks chaining research -> PRFAQ -> BRD -> build spec.

### 5.6 Understanding the compliance sections in your BRD

Sections 13 through 18 of the BRD are new compliance output. Here's what each one means and what to do with it.

**Section 13: Data Handling.** Lists every data element the product touches, with a classification (Public, Confidential, Highly Confidential, Restricted, Critical). The Dataset Classification line at the top is the highest individual classification. If you see a blockquote reading "Data handling section flagged as a gap," your PRFAQ didn't include enough detail about data handling. Fix: edit the PRFAQ's customer experience narrative and internal FAQs to describe what data the product uses, then re-run the pipeline (or revise the BRD with `revise-brd`). This gap flag is intentional; the system refuses to fabricate classifications.

**Section 14: Vendor Considerations.** Lists which of the seven generic vendor-risk scenarios apply (data sharing, data handling, content hosting, product development, environment connection, SaaS usage, endorsement or referral). If no scenario applies, you'll see an explicit "No third party is involved" statement.

**Section 15: Privacy Considerations.** Privacy risks grounded in the data classifications, paired with mitigations (encryption in transit and at rest, access controls, data minimization, retention limits). The "Design review flag" is set to true when the product handles personal data at Confidential or higher.

**Section 16: Compliance Gates.** Which reviews apply (security, privacy, legal or contract, procurement). Each gate carries the note "start early, run in parallel, do not launch with open Critical or High findings." Read this as PM guidance: open all applicable reviews at the same time rather than in sequence.

**Section 17: Launch Readiness Checklist.** A table of pre-launch items with owners (PM, Tech Lead, Engineer, Legal, Security, Privacy) and evidence references. Use it as your personal launch checklist. Evidence Reference cells may be blank at BRD time; you fill them in as evidence accumulates.

**Section 18: Post-Launch Maintenance.** Recertification cadence, triggers for re-classifying data, and runbook pointers.

These sections are generated to give you and your engineering partner a shared starting point for compliance conversations. Treat them as drafts, not approvals. Your organization's actual review processes are the source of truth.

---


## Section 7: Troubleshooting

This section covers every problem a pilot user has actually hit. If yours is not here, ping Joe and we will add it.

### 7.1 Install and setup errors

**`command not found: uv`** (Mac or Windows)

Your shell did not pick up the new `uv` command. Fix:

- Close and reopen your terminal. This is the most common fix.
- On Mac, if closing and reopening does not help, run `source ~/.zshrc` or `source ~/.bash_profile`.
- On Windows PowerShell, if closing and reopening does not help, your `PATH` may not include `uv`. Run:
  ```powershell
  echo $env:PATH
  ```
  Look for a path like `C:\Users\YourName\.local\bin`. If it is missing, add it via System Properties -> Environment Variables -> Path, or reinstall `uv` with the official installer.

**`command not found: git`**

Git is not installed. Go back to Section 1.4 and install it.

**`command not found: python3`** or **`command not found: python`**

Python is not installed, or not on your PATH. On Windows, this almost always means the "Add Python to PATH" checkbox was unchecked during install. Uninstall Python, reinstall it from [python.org](https://www.python.org/downloads/), and check that box.

**`uv sync` fails with "No solution found"** or package conflicts

This is rare but happens when a package version is incompatible. Fix:

```bash
rm -rf .venv uv.lock
uv sync
```

On Windows PowerShell:

```powershell
Remove-Item -Recurse -Force .venv, uv.lock
uv sync
```

This deletes the virtual environment and lock file, then rebuilds from scratch.

**`uv sync` fails with SSL or certificate errors**

Your network or corporate firewall is blocking package downloads. If you are on a corporate network (VPN, proxy), try:

- Disconnect from VPN and re-run `uv sync`
- Or ask your IT team for the corporate certificate bundle and set `UV_CA_BUNDLE_PATH` to it

**Windows: "cannot be loaded because running scripts is disabled on this system"** or **"execution of scripts is disabled"**

PowerShell's execution policy is blocking the `uv` installer. Fix by running PowerShell as Administrator and then:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Close the admin window, reopen a normal PowerShell, and try the `uv` install again.

### 7.2 Credential and .env errors

**`ANTHROPIC_API_KEY not set`** when running a command (and you are using Bedrock)

The system is looking for the Anthropic key because `LLM_PROVIDER` is not set to `bedrock`. Open `.env` and confirm this line exists and is not commented out:

```
LLM_PROVIDER=bedrock
```

There should be no `#` in front of it. Save the file and re-run the command.

**`AWS_BEARER_TOKEN_BEDROCK not set`**

Your `.env` does not have the Bedrock key filled in. Open `.env` and paste your key after `AWS_BEARER_TOKEN_BEDROCK=`. No quotes, no spaces.

If you do not have a Bedrock key yet, ping Joe.

**`TAVILY_API_KEY not set`** or Tavily returns 401

Open `.env` and confirm `TAVILY_API_KEY=tvly-...` is filled in. Common mistakes:

- Extra quotes around the key (remove them)
- Extra spaces around the `=` sign (remove them)
- The key got cut off when copy-pasted (re-copy from tavily.com and paste again)

**Bedrock error: "Your access to the model is denied"** or similar

Your Bedrock account does not have access to Claude Haiku 4.5 in the region you are using. Fix options:

- If using Joe's credentials: ping Joe, the pilot key may need re-enabling
- If using your own: go to the AWS Bedrock console, find Model Access in the sidebar, and request access to `anthropic.claude-haiku-4-5-20251001-v1:0`. Approval typically takes a few minutes.

**Bedrock error: "Could not resolve the foundation model"** or "Invocation of model ID ... is not supported"

The model ID is wrong or not available in your region. Check `.env`:

```
AWS_BEDROCK_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-haiku-4-5-20251001-v1:0
```

If you are in a different region, switch `AWS_BEDROCK_REGION` to match. If the model is not available in your region, switch to `us-east-1` or `us-west-2`.

**"ValidationException" from Bedrock**

This usually means the request payload is malformed. Most often the cause is a wrong model ID. Double-check `BEDROCK_MODEL_ID` matches the exact string above.

### 7.3 Runtime errors

**"Rate limit exceeded" from Tavily**

You have hit the free tier limit (1,000 searches per month). Either wait until the counter resets, or upgrade your Tavily tier.

**"Rate limit exceeded" from Bedrock**

Bedrock has per-account rate limits. If you hit them, wait a minute and re-run. If it keeps happening, ping Joe.

**The pipeline stops with "OBSIDIAN_VAULT_PATH does not exist"**

The path in `.env` is wrong or not accessible. Common causes:

- Typos in the path
- Spaces in the path not quoted (wrap the path in quotes: `OBSIDIAN_VAULT_PATH="C:/Users/YourName/Documents/PM Pilot"`)
- On Windows, using single backslashes in a way that escapes characters: use forward slashes instead (`C:/Users/...`) or double backslashes (`C:\\Users\\...`)
- The vault folder does not exist yet. Create it in Finder or File Explorer first, then update the path.

**The pipeline runs but the output is short, vague, or low-quality**

Two main causes:

1. **Your input was vague.** Open `demo_input.yaml` or `examples/input-brief-example.md` to see the level of detail that produces good output. Rewrite your input to match that level of specificity, then re-run.
2. **The research tools could not find sources.** Check the research brief's "Sources" section. If it is sparse, your topic may be too niche or too new for public web coverage. The system cannot find what does not exist on the public internet.

**The pipeline hangs at a checkpoint with no prompt visible**

The prompt is there, but your terminal may have scrolled past it. Scroll up, look for the line with `[a]  Approve and continue`. Type `a` and press Enter.

**My computer went to sleep while the pipeline was running**

LLM calls may time out if the computer sleeps mid-call. Either disable sleep during pipeline runs (Mac: System Settings -> Battery -> "Prevent automatic sleeping on power adapter when the display is off"; Windows: Settings -> System -> Power -> Screen and sleep -> "Never"), or keep the computer awake with a caffeine-type app.

### 7.4 Output and Obsidian errors

**Output files show up in `output/` but not in my Obsidian vault**

Check that `OBSIDIAN_VAULT_PATH` is set correctly in `.env`. Then check inside your vault for a folder called `PM Agent` or whatever you set for `OBSIDIAN_FOLDER_PREFIX`. Artifacts are nested under `<vault>/PM Agent/<product-slug>/`.

If the folder still is not there, run a fresh `research` command and watch the terminal output for any "vault sync skipped" or "vault path" warning messages.

**I edited a file in Obsidian but the agent did not pick up my changes**

Make sure you:

1. Saved the file in Obsidian (Obsidian auto-saves but force-save with Cmd+S or Ctrl+S to be safe)
2. At the checkpoint prompt, typed `o` and pressed Enter (not `a`)
3. Gave Obsidian and your filesystem a second to flush before typing `o`

**My BRD has a blockquote in Section 13 that says "Data handling section flagged as a gap"**

The PRFAQ didn't include enough detail about what data the product handles, so the compliance workstream refused to guess. This is working as intended; the system refuses to fabricate classifications.

Two ways to fix:

1. **Revise the PRFAQ first, then re-run the BRD.** Open the PRFAQ in Obsidian. Add specifics to the customer experience narrative and the internal FAQs about what data the product collects, processes, stores, or transmits (emails, session tokens, payment data, user-generated content, etc.). Save. Re-run `uv run pm_agent_system brd <input> --prfaq-path <prfaq_path>`.
2. **Revise the BRD directly with feedback.** `uv run pm_agent_system revise-brd --brd-path output/brd_slug_v1.0.md --context-text "The product handles user emails (Restricted), session tokens (Highly Confidential), and preference JSON (Confidential). Please fill in Section 13 based on these elements."`. The revise flow respects your feedback and re-runs the compliance workstream.

**The BRD's compliance section calls out a vendor scenario I don't think applies**

The compliance workstream reads the seven vendor-risk scenarios (data sharing, data handling, content hosting, product development, environment connection, SaaS usage, endorsement or referral) from the PRFAQ. If the PRFAQ mentions a third-party service that you don't consider vendor-scoped, the classification may surface incorrectly. Use `revise-brd` with feedback explaining why the scenario doesn't apply, and the agent will reconsider.

**My build spec has a STRIDE stub and RACI matrix I didn't expect**

These appear when the BRD's compliance section flags sensitive data (Confidential or higher) or a vendor scenario. They are starting scaffolds, not mandates. If your product genuinely doesn't need them, revise the BRD to correct the data classification or vendor flags, and the scaffolds will disappear on the next run.

### 7.5 Kiro errors

**Kiro says the spec file is invalid or missing required sections**

Check which file you loaded. The Kiro-formatted file has `_kiro` in the name: `output/build_spec_slug_kiro.md`. The plain `build_spec_slug.md` is a reference version and not Kiro-formatted. Load the `_kiro` version.

**Kiro says it cannot find referenced screens or flows**

This happens when the BRD references a design brief but the design brief was skipped. If you passed `--skip-design`, the BRD will not reference specific screens; that is expected. If you want screen references, re-run the BRD stage with `--design-brief-path` pointing at an approved design brief.

### 7.6 Still stuck

Copy the full error text (every line from the last successful step to the final red error message) and send it to Joe via Slack or email. Do NOT include your `.env` file or any API keys. Joe will respond with a fix or update this troubleshooting section.

---


## Section 8: Glossary

Plain-language definitions for the terms in this guide. Alphabetical.

**Agent.** A program that uses an LLM (here, Claude Haiku via Bedrock) to do one specific job. This project has four agents. Agent 1 does research, Agent 2 writes the PRFAQ, Agent 3 writes the design brief, Agent 4 writes the BRD and build spec. The BRD stage internally runs three parallel subagents (structure, cost-risk, compliance) whose outputs merge into the final BRD.

**API key.** A long string that proves to an external service (Tavily, Bedrock) that you are allowed to use it. Treat API keys like passwords. Never share them, never paste them into Slack or email.

**Bedrock.** AWS's service for running foundation models (like Claude) in your own AWS account. This pilot uses Bedrock as the LLM backend, not the Anthropic direct API.

**BRD (Business Requirements Document).** The engineer-ready document that translates a PRFAQ into functional requirements, acceptance criteria, cost flags, and compliance content. Agent 4's three subagents produce this together. The final BRD has 18 sections: the original 12 (executive summary, problem statement, proposed solution, user stories, functional requirements, non-functional requirements, technical context, cost flags, risks, success metrics, timeline, version history) plus 6 compliance sections (data handling, vendor considerations, privacy considerations, compliance gates, launch readiness checklist, post-launch maintenance).

**Build spec.** The coding-tool-ready document that Kiro (or Claude Code, Cursor, Lovable) uses to generate an implementation. Agent 4 produces this as the final artifact in the pipeline. When the BRD flags sensitive data or a vendor scenario, the build spec also appends a STRIDE threat model stub and a RACI matrix.

**Checkpoint.** A pause between agents where the system waits for your review and approval. You can approve, give feedback, edit in Obsidian, or quit. The system never auto-advances.

**CLI.** Command-line interface. The terminal, plus the commands you type into it.

**Compliance gate.** A pre-launch review checkpoint that applies before a product ships. The four generic categories are security review, privacy review, legal or contract review, and procurement review. The BRD lists which gates apply for your product. Each gate carries the note "start early, run in parallel, do not launch with open Critical or High findings" as PM guidance.

**Cost flag.** An entry in the BRD that calls out an architecture decision with cost implications. Cost flags cite real AWS pricing so engineering leads can evaluate tradeoffs.

**CrewAI.** The open-source Python framework this project is built on. It handles agent orchestration, message passing, and output validation. You never interact with CrewAI directly; it runs under the hood.

**Data classification.** A five-level taxonomy (Public, Confidential, Highly Confidential, Restricted, Critical) applied to each data element the product handles. Used by the BRD compliance workstream to size privacy and security risk. The Dataset Classification is the highest individual classification across all elements.

**Design brief.** The document that maps the PRFAQ's customer experience narrative into concrete screens, user flows, and design principles. Agent 3 produces this. Optional: skip it with `--skip-design`.

**Dovetail.** A UX research repository. If your team uses Dovetail, the research agent can pull customer quotes from it. Optional for the pilot.

**`.env`.** A file in the project root that holds your API keys and configuration. Never commit `.env` to git, never share it.

**Frontmatter.** The YAML block at the top of a markdown file (between `---` lines). Obsidian uses it for tags, status, and custom properties. The pipeline adds artifact type, version, and traceability links to frontmatter.

**Full pipeline.** Running all agents end to end in sequence. The `full-pipeline` command.

**Gap flag.** A signal the compliance workstream raises when the PRFAQ doesn't describe data handling. When the gap flag is set, the BRD's data handling section shows a blockquote notice and the elements table is empty. The system refuses to fabricate classifications; you fix by revising the PRFAQ or the BRD directly.

**Human-in-the-loop.** The design principle that the PM (you) reviews and approves every artifact before the next agent runs. Non-negotiable in this system.

**Input brief.** Your starting document. A markdown or YAML file that describes the product problem, target user, goals, and constraints. Everything else is built from this.

**Kiro.** A spec-driven coding IDE. The build spec agent formats its output so Kiro can import it as a spec and generate the implementation.

**Launch readiness checklist.** A table in the BRD (section 17) listing pre-launch gate items with owners (PM, Tech Lead, Engineer, Legal, Security, Privacy) and evidence references. The checklist includes at minimum: data classification sign-off, privacy mitigation sign-off, security review status, monitoring and alarm setup, runbook availability, and rollback plan.

**LLM.** Large language model. The AI that does the thinking. This project uses Claude Haiku 4.5 via Bedrock.

**Obsidian.** A markdown note-taking app. This pilot uses Obsidian as the place where your drafts, revisions, and feedback live. The pipeline writes artifact copies to your Obsidian vault automatically.

**PRFAQ.** Press Release plus Frequently Asked Questions. The Working Backwards planning document: a fictional launch press release plus answers to the hard questions. Agent 2 produces this, now with a data handling enumeration that the BRD compliance workstream consumes.

**RACI matrix.** A responsibility table with columns Responsible, Accountable, Consulted, Informed and rows for PM, Tech Lead, Engineer, Legal, Security, and Privacy. The build spec includes a RACI matrix when the BRD flags a vendor scenario or a privacy design review. Rendered deterministically from the BRD fields, not by the LLM.

**Research brief.** The document Agent 1 produces. It contains market data, competitive analysis, customer evidence, and a synthesis. Every claim has a source citation.

**Revise.** Re-run an agent with feedback against an existing artifact. You get a new version (e.g., `v1.0` becomes `v1.1`). Existing artifacts are preserved.

**STRIDE stub.** A six-category threat model scaffold (Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege) the build spec includes when the BRD flags sensitive data (Confidential or higher) or a vendor scenario. Engineers fill in product-specific mitigations. Rendered deterministically from the BRD fields, not by the LLM.

**Tavily.** A web search API designed for LLMs. The research agent uses Tavily to find market data and competitor information.

**Terminal.** The application where you type commands. On Mac it is called Terminal; on Windows it is called PowerShell.

**Vault.** An Obsidian folder. A self-contained collection of markdown notes. You can have multiple vaults; each one is a separate workspace.

**Vendor-risk scenario.** One of seven generic categories the compliance workstream evaluates against your product: data sharing, data handling, content hosting, product development, environment connection, SaaS usage, endorsement or referral. The BRD lists which scenarios apply. If none apply, the BRD states explicitly that no third party is involved.

**Working Backwards.** Amazon's product planning approach: start from the customer experience, work backward to the engineering. The PRFAQ is the main artifact of this approach.

---

## Section 9: Getting help

### When to ask Joe

Ask anytime. Specifically:

- You hit an error not covered in Section 7
- You get stuck for more than 10 minutes on setup
- The pipeline produces output that looks wrong and the research brief has no sources
- You want to run on a tricky product problem and want a gut-check on your input brief first
- You have feedback on this guide (typos, missing steps, confusing instructions)

### How to reach Joe

- Slack DM
- Email
- Or drop a comment in your Obsidian vault (Joe watches the shared project folder)

### What to include when you ask for help

Save everyone time by including:

1. **Which command you ran** (the exact text)
2. **What happened** (the last 10-20 lines of terminal output, or a screenshot)
3. **What you expected** (briefly)
4. **What you already tried** from Section 7

Do NOT include your `.env` file or API keys in any message.

### When you want to skip ahead

If you already know CLI tools and just want to run the system, the minimum path is:

1. Clone the repo, `cd` in
2. `uv sync`
3. `cp .env.example .env`; fill in `TAVILY_API_KEY`, `AWS_BEARER_TOKEN_BEDROCK`, `LLM_PROVIDER=bedrock`, `OBSIDIAN_VAULT_PATH`
4. `uv run pm_agent_system full-pipeline demo_input.yaml --skip-design`

That is the whole setup if you already have Python, `uv`, and Git installed.

---

## Living document note

This guide is updated every time a code change affects setup, commands, or the pilot user experience. The `last_updated` field in the frontmatter reflects the most recent revision. If you spot anything stale (a command that no longer works, an error message that does not match), ping Joe so it can be fixed in the next revision.

**What's new in this revision (2026-04-28)**:
- Section 5.2, Stage 3 rewritten for the three-subagent BRD pipeline (structure, cost-risk, compliance)
- Section 5.2, Stage 2 updated to mention the PRFAQ's data handling enumeration
- Section 5.4 now explains the STRIDE stub and RACI matrix that appear in the Kiro spec
- Section 5.5 success checklist expanded to include compliance artifacts
- Section 5.6 added: explains each of the six new BRD compliance sections (13 through 18) and how to act on them
- Section 6.1 table adds the manual latency measurement script
- Section 6.3 table notes the new BRD sections and build-spec additions
- Section 6.4 cost estimates revised up 20-30 percent to reflect the additional compliance workstream token spend
- Section 7.4 adds troubleshooting for the "data handling gap" blockquote, unexpected vendor scenarios, and STRIDE/RACI scaffolds
- Section 8 glossary adds: data classification, compliance gate, launch readiness checklist, STRIDE stub, RACI matrix, gap flag, vendor-risk scenario. Existing entries for Agent, BRD, Build spec, and PRFAQ updated to reflect the new content.

Happy piloting. You will probably finish your first full run faster than you expect.

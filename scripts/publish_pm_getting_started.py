"""Publish the PM pilot Getting Started guide to the Obsidian vault.

Target: a PM direct report who has never used a terminal. Mac or Windows.
Expected setup time: 10-20 minutes. Expected first end-to-end pipeline
run with Kiro spec output: under 30 minutes after setup completes.

Usage: uv run python scripts/publish_pm_getting_started.py
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", "").strip()
if not VAULT_PATH or not Path(VAULT_PATH).is_dir():
    print("Error: OBSIDIAN_VAULT_PATH not set or directory does not exist.")
    sys.exit(1)

PROJECT_FOLDER = (
    Path(VAULT_PATH)
    / "01 Next Actions"
    / "Deep Work"
    / "Amazon"
    / "Projects"
    / "Agentic PM Assistant"
)
PROJECT_FOLDER.mkdir(parents=True, exist_ok=True)

NOW = datetime.now(timezone.utc)
FILENAME = "PM Pilot Getting Started.md"

FRONTMATTER = f"""---
title: "PM Pilot: Getting Started with the Agentic PM Assistant"
type: getting-started
audience: PM pilot users
status: living-document
created: {NOW.isoformat()}
last_updated: {NOW.isoformat()}
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

"""

BODY_PART_1 = """# PM Pilot: Getting Started with the Agentic PM Assistant

## What this is

You are piloting a system that takes a product problem statement and produces, in sequence:

1. A **research brief** with real market data, competitors, and customer quotes
2. A **PRFAQ** (Working Backwards document) ready for VP alignment
3. A **BRD** with engineer-ready requirements and real AWS pricing data
4. A **Kiro spec** that Kiro can turn into a working prototype

Four specialized agents do the research, writing, and formatting. You review and approve at each step. You stay in the loop end to end; nothing ships without you saying yes.

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
   - On Windows, a common place is `C:\\Users\\YourName\\Documents\\PM Pilot`

A "vault" is just a folder of markdown files. Obsidian reads and writes them. That folder is where all your drafts, versions, and feedback will end up.

#### Open a terminal

The terminal is where you type commands. Don't be intimidated. You'll paste lines from this guide and press Enter; that's 95% of what you'll ever do.

**On Mac**:
1. Press `Cmd + Space`, type `Terminal`, press Enter.
2. A window opens with a prompt that looks like `YourName@YourMac ~ %`. That's your terminal.

**On Windows**:
1. Press the Windows key, type `PowerShell`, press Enter.
2. A window opens with a blue background and a prompt like `PS C:\\Users\\YourName>`. That's your terminal.
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

**On Mac**: the easiest path is [python.org/downloads](https://www.python.org/downloads) — download the latest Python 3.x installer and run it.

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
"""

recap_path = PROJECT_FOLDER / FILENAME
recap_path.write_text(FRONTMATTER + BODY_PART_1, encoding="utf-8")
print(f"Getting Started (part 1) written: {recap_path}")

BODY_PART_2 = """

## Section 2: Download and install the project

### 2.1 Pick where the project will live

The project is a folder of code. You'll download it to somewhere on your computer. Pick a location you'll remember. The Desktop is fine.

In your terminal, navigate to where you want it. These commands work on both Mac and Windows (PowerShell):

```bash
cd ~/Desktop
```

`cd` means "change directory." After running this, your terminal prompt is now inside your Desktop folder. To confirm, run:

- On Mac: `pwd` (prints the current folder path)
- On Windows: `pwd` (same command works in PowerShell)

### 2.2 Download (clone) the project

Paste this into your terminal and press Enter:

```bash
git clone https://github.com/joegarvey-ai/pm-working-backwards-agent.git
```

This downloads the project into a new folder called `pm-working-backwards-agent`. Takes about 30 seconds.

Then move into that folder:

```bash
cd pm-working-backwards-agent
```

From now on, every command in this guide assumes your terminal is inside `pm-working-backwards-agent`. If you close the terminal and come back later, reopen it and run `cd ~/Desktop/pm-working-backwards-agent` (or wherever you put it) before doing anything else.

### 2.3 Install the project dependencies

This installs every library the agents need. Takes 2-5 minutes the first time.

```bash
uv sync
```

You'll see a lot of output as packages download. When it finishes, you'll see `Installed N packages in Xs`. That means it worked.

If this fails, scroll to the Troubleshooting section (Section 7) and look for "uv sync errors."

### 2.4 Verify the install worked

Run this to see the pipeline's help text:

```bash
uv run pm_agent_system --help
```

You should see a list of commands: `research`, `generate`, `full-pipeline`, `brd`, and others. If you see that, the install worked.

---

## Section 3: Configure your credentials and vault

The project reads all its configuration from a file called `.env`. You need to create that file and paste in your keys.

### 3.1 Create the .env file

```bash
cp .env.example .env
```

On Windows PowerShell, if `cp` doesn't work, use:

```powershell
Copy-Item .env.example .env
```

This creates `.env` as a copy of `.env.example`. `.env` is the file you edit with your actual keys. `.env.example` is the template.

### 3.2 Open .env in a text editor

You can use any text editor. Easiest options:

**On Mac**: open TextEdit, go to File -> Open, and navigate to `pm-working-backwards-agent/.env`. If you don't see hidden files, press `Cmd + Shift + .` to toggle.

**On Windows**: open Notepad, go to File -> Open, set the file type filter to "All Files," and navigate to `pm-working-backwards-agent/.env`.

**Both**: if you already use VS Code or Sublime Text, those work too.

You can also edit the file directly in your terminal with `nano .env` (Mac/Linux) or `notepad .env` (Windows).

### 3.3 Fill in your keys

Inside `.env`, you'll see something like this:

```
ANTHROPIC_API_KEY=your_anthropic_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
DOVETAIL_API_TOKEN=
...
AWS_BEARER_TOKEN_BEDROCK=
AWS_REGION=us-east-1
AWS_BEDROCK_REGION=us-east-1
LLM_PROVIDER=bedrock
BEDROCK_MODEL_ID=anthropic.claude-haiku-4-5-20251001-v1:0
OBSIDIAN_VAULT_PATH=
```

Change three things:

**1. Tavily key.** Replace `your_tavily_api_key_here` with the Tavily key you saved earlier. The line should look like:

```
TAVILY_API_KEY=tvly-YOUR-ACTUAL-KEY-HERE
```

**2. Bedrock key.** Paste your Bedrock API key (from Joe or your own) after `AWS_BEARER_TOKEN_BEDROCK=`. The line should look like:

```
AWS_BEARER_TOKEN_BEDROCK=bedrock-api-key-LONG-ENCODED-STRING-HERE
```

**3. Obsidian vault path.** Paste the path to the Obsidian vault you created in Section 1.4. For example:

- On Mac: `OBSIDIAN_VAULT_PATH=/Users/yourname/Documents/PM Pilot`
- On Windows: `OBSIDIAN_VAULT_PATH=C:\\Users\\YourName\\Documents\\PM Pilot`

Note the backslashes on Windows. Use double backslashes (`\\\\`) only if your vault path contains spaces; otherwise single backslashes (`\\`) are fine. Safest bet on Windows: forward slashes work too, so `C:/Users/YourName/Documents/PM Pilot` also works.

**You do NOT need to set `ANTHROPIC_API_KEY`.** Leave it as is. The `LLM_PROVIDER=bedrock` line tells the system to use Bedrock, not Anthropic direct. That's already set correctly.

### 3.4 Save and close .env

Important: never share your `.env` file. Never paste it into chat or email. It contains your credentials. The project's `.gitignore` already prevents accidentally pushing it to GitHub.

### 3.5 Test your configuration

Quick sanity check:

```bash
uv run pm_agent_system --help
```

Should print the same help text as before. If you get an error about missing keys, go back and re-check Section 3.3.

### 3.6 Checklist before moving on

- [ ] Project is downloaded to a folder you can find
- [ ] `uv sync` completed without errors
- [ ] `.env` is created and contains your Tavily key, your Bedrock key, and your Obsidian vault path
- [ ] `LLM_PROVIDER=bedrock` is set in `.env`

---
"""

with open(recap_path, "a", encoding="utf-8") as f:
    f.write(BODY_PART_2)
print(f"Getting Started (part 2) appended: {recap_path}")

BODY_PART_3 = """

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

Now the real thing. This costs $0.50-$1.00 per run and takes 15-30 minutes of LLM time plus however long you take on each review.

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

Then run:

```bash
uv run pm_agent_system full-pipeline input/my-product.md --skip-design
```

**Why `--skip-design`?** The design brief stage (Agent 3) adds a design brief with screen inventory and user flows, but it also adds a checkpoint and extra time. For the pilot, skip it and let Agent 4 (BRD + build spec) go directly from the PRFAQ to the Kiro spec. You can try it with the design brief later.

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
- Artifact: `output/prfaq_*_v1.0.md`, vault copy
- **Checkpoint**: you review, approve or give feedback. You can also open the file in Obsidian, edit it directly, then type `o` at the checkpoint and the agent reads your edits

**Stage 3: BRD** (~3-4 minutes of LLM time)
- Takes the approved PRFAQ
- Produces the BRD in parallel: one task writes the structure (user stories, functional requirements, acceptance criteria), another task pulls actual AWS pricing data for cost flags
- Merges both into the final BRD
- Also writes Jira/Linear import files automatically
- Artifact: `output/brd_*_v1.0.md`, `brd_*_jira_import.csv`, `brd_*_linear_import.md`
- **Checkpoint**: you review, approve or give feedback

**Stage 4: Build Spec (Kiro format)** (~2-3 minutes of LLM time)
- Takes the approved BRD
- Formats it as a Kiro spec with Requirements, Design, and Tasks sections
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

### 5.5 What success looks like end-to-end

You started with a problem statement. In under an hour of elapsed time (about 10-15 minutes of active attention on your side), you have:

- A research brief with actual market data and customer evidence
- A stakeholder-ready PRFAQ
- A BRD with requirements, acceptance criteria, and pricing data
- A Kiro spec that Kiro turns into a running prototype
- Jira/Linear import files if you want to spin up tickets

All copies are in your Obsidian vault under the product's folder, with wikilinks chaining research -> PRFAQ -> BRD -> build spec.

---
"""

with open(recap_path, "a", encoding="utf-8") as f:
    f.write(BODY_PART_3)
print(f"Getting Started (part 3) appended: {recap_path}")

BODY_PART_4 = """

## Section 6: Reference (cheat sheet)

Bookmark this section. Come back when you need to look something up.

### 6.1 Commands you will actually run

All commands assume you're inside the `pm-working-backwards-agent` folder in your terminal.

| I want to... | Command |
|---|---|
| Run research only (cheap sanity check) | `uv run pm_agent_system research demo_input.yaml` |
| Run research + PRFAQ | `uv run pm_agent_system generate demo_input.yaml` |
| Run the full pipeline without design brief | `uv run pm_agent_system full-pipeline demo_input.yaml --skip-design` |
| Run the full pipeline with design brief | `uv run pm_agent_system full-pipeline demo_input.yaml` |
| Revise a PRFAQ using feedback text | `uv run pm_agent_system revise --prfaq-path output/prfaq_slug_v1.0.md --context-text "feedback here"` |
| Revise a PRFAQ using a feedback file | `uv run pm_agent_system revise --prfaq-path output/prfaq_slug_v1.0.md --context-path feedback.md` |
| Write a BRD from an approved PRFAQ | `uv run pm_agent_system brd demo_input.yaml --prfaq-path output/prfaq_slug_v1.0.md` |
| Regenerate a build spec for a different tool | `uv run pm_agent_system build-spec --brd-path output/brd_slug_v1.0.md --target-tool kiro` |
| Revise a BRD | `uv run pm_agent_system revise-brd --brd-path output/brd_slug_v1.0.md --context-text "FR-3 needs a GSI"` |
| Compare two versions of a doc | `uv run pm_agent_system diff output/prfaq_slug_v1.0.md output/prfaq_slug_v1.1.md` |
| See all commands and their options | `uv run pm_agent_system --help` |
| See options for one command | `uv run pm_agent_system full-pipeline --help` |

### 6.2 Input options for each command

Every pipeline command accepts either a markdown (`.md`) or YAML (`.yaml`) input file. Markdown is recommended for most PMs because you can edit it in Obsidian and read it like a document.

| Flag | What it does |
|---|---|
| `--skip-design` | Skip Agent 3 (design brief). Faster, cheaper. Use when you don't need screen inventory or user flows. |
| `--skip-validation` | Skip the upfront assumption-challenge step. Saves a minute. Use only when you trust your brief. |
| `--prfaq-path <file>` | Point at an approved PRFAQ (for `brd` or `revise` commands). |
| `--brd-path <file>` | Point at an approved BRD (for `build-spec` or `revise-brd`). |
| `--design-brief-path <file>` | Point at an approved design brief (for `brd`). |
| `--research-path <file>` | Skip Agent 1 and use your own research file. |
| `--requirements-path <file>` | Provide pre-existing requirements (Agent 4 reconciles them against the PRFAQ). |
| `--context-text "feedback"` | Inline feedback text for `revise` or `revise-brd`. |
| `--context-path <file>` | Feedback text in a file for `revise` or `revise-brd`. |
| `--target-tool kiro` | Format the build spec for Kiro (default). Other options: `claude_code`, `cursor`, `lovable`. |
| `--open` | Auto-open the final HTML artifact in your browser when the command finishes. |

### 6.3 Where files land

| What | Where |
|---|---|
| Original input file | wherever you put it (e.g., `input/my-product.md`) |
| Research brief | `output/research_brief_*.md` plus HTML version |
| PRFAQ | `output/prfaq_slug_v1.0.md` plus HTML version |
| Design brief | `output/design_brief_slug_v1.0.md` plus HTML version |
| BRD | `output/brd_slug_v1.0.md` plus HTML version |
| Jira import CSV | `output/brd_slug_v1.0_jira_import.csv` |
| Linear import markdown | `output/brd_slug_v1.0_linear_import.md` |
| Build spec | `output/build_spec_slug.md` and `output/build_spec_slug_kiro.md` |
| Obsidian vault copies | `<vault>/PM Agent/<product-slug>/` |
| Archived old outputs | `output/archive/` (auto-rotated after 30 days) |

### 6.4 Cost and time reference

| Command | Typical cost | Typical LLM time |
|---|---|---|
| `research` | $0.10 to $0.20 | 2-3 minutes |
| `generate` (research + PRFAQ) | $0.30 to $0.60 | 4-6 minutes |
| `full-pipeline` with `--skip-design` | $0.50 to $1.00 | 10-15 minutes of LLM time |
| `full-pipeline` with design brief | $0.80 to $1.50 | 15-25 minutes of LLM time |
| `revise` (PRFAQ or BRD) | $0.10 to $0.30 | 1-2 minutes |

Note: elapsed wall-clock time includes however long you spend at each review checkpoint. If you step away at a checkpoint, elapsed time can be hours, but the cost and LLM time stay the same. It is normal to kick off the pipeline, walk away, and come back later to approve.

### 6.5 Environment variables (what is in `.env`)

| Variable | Required | What it is |
|---|---|---|
| `TAVILY_API_KEY` | yes | Your Tavily key (starts with `tvly-`) |
| `AWS_BEARER_TOKEN_BEDROCK` | yes (Bedrock) | Your Bedrock API key (starts with `bedrock-api-key-`) |
| `LLM_PROVIDER=bedrock` | yes (Bedrock) | Tells the system to use Bedrock, not Anthropic direct |
| `AWS_BEDROCK_REGION` | yes (Bedrock) | Region where Bedrock is enabled (default `us-east-1`) |
| `BEDROCK_MODEL_ID` | yes (Bedrock) | The model ID, defaults to `anthropic.claude-haiku-4-5-20251001-v1:0` |
| `ANTHROPIC_API_KEY` | only if NOT using Bedrock | Direct Anthropic key (not needed for the pilot) |
| `OBSIDIAN_VAULT_PATH` | no | Path to your Obsidian vault; enables vault integration |
| `OBSIDIAN_FOLDER_PREFIX` | no | Top-level folder name in the vault (default `PM Agent`) |
| `DOVETAIL_API_TOKEN` | no | Dovetail token (leave blank if you do not use Dovetail) |
| `STYLE_GUIDE_PATH` | no | Your writing style guide; defaults to the included sample |
| `OUTPUT_DIR` | no | Where output files go (default `./output`) |
| `OUTPUT_RETENTION_DAYS` | no | Days before output files are archived (default 30) |
| `DEFAULT_TARGET_TOOL` | no | Default build spec target (default `kiro`) |
| `VISUAL_STYLE_GUIDE_PATH` | no | Your visual or brand style guide for Agent 3 wireframes |

### 6.6 Review checkpoint options

At every checkpoint, you have these options:

| Input | What happens |
|---|---|
| `a` + Enter | Approve the current artifact and move to the next stage |
| `f <feedback text>` + Enter | Send feedback text; the agent revises and re-asks |
| `o` + Enter | The agent reads your direct edits to the file in Obsidian as feedback |
| `q` + Enter | Quit the pipeline (your existing artifacts are preserved on disk and in the vault) |

---
"""

with open(recap_path, "a", encoding="utf-8") as f:
    f.write(BODY_PART_4)
print(f"Getting Started (part 4) appended: {recap_path}")

BODY_PART_5 = r"""

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

### 7.5 Kiro errors

**Kiro says the spec file is invalid or missing required sections**

Check which file you loaded. The Kiro-formatted file has `_kiro` in the name: `output/build_spec_slug_kiro.md`. The plain `build_spec_slug.md` is a reference version and not Kiro-formatted. Load the `_kiro` version.

**Kiro says it cannot find referenced screens or flows**

This happens when the BRD references a design brief but the design brief was skipped. If you passed `--skip-design`, the BRD will not reference specific screens; that is expected. If you want screen references, re-run the BRD stage with `--design-brief-path` pointing at an approved design brief.

### 7.6 Still stuck

Copy the full error text (every line from the last successful step to the final red error message) and send it to Joe via Slack or email. Do NOT include your `.env` file or any API keys. Joe will respond with a fix or update this troubleshooting section.

---
"""

with open(recap_path, "a", encoding="utf-8") as f:
    f.write(BODY_PART_5)
print(f"Getting Started (part 5) appended: {recap_path}")

BODY_PART_6 = """

## Section 8: Glossary

Plain-language definitions for the terms in this guide. Alphabetical.

**Agent.** A program that uses an LLM (here, Claude Haiku via Bedrock) to do one specific job. This project has four agents. Agent 1 does research, Agent 2 writes the PRFAQ, Agent 3 writes the design brief, Agent 4 writes the BRD and build spec.

**API key.** A long string that proves to an external service (Tavily, Bedrock) that you are allowed to use it. Treat API keys like passwords. Never share them, never paste them into Slack or email.

**Bedrock.** AWS's service for running foundation models (like Claude) in your own AWS account. This pilot uses Bedrock as the LLM backend, not the Anthropic direct API.

**BRD (Business Requirements Document).** The engineer-ready document that translates a PRFAQ into functional requirements, acceptance criteria, and cost flags. Agent 4 produces this.

**Build spec.** The coding-tool-ready document that Kiro (or Claude Code, Cursor, Lovable) uses to generate an implementation. Agent 4 produces this as the final artifact in the pipeline.

**Checkpoint.** A pause between agents where the system waits for your review and approval. You can approve, give feedback, edit in Obsidian, or quit. The system never auto-advances.

**CLI.** Command-line interface. The terminal, plus the commands you type into it.

**Cost flag.** An entry in the BRD that calls out an architecture decision with cost implications. Cost flags cite real AWS pricing so engineering leads can evaluate tradeoffs.

**CrewAI.** The open-source Python framework this project is built on. It handles agent orchestration, message passing, and output validation. You never interact with CrewAI directly; it runs under the hood.

**Design brief.** The document that maps the PRFAQ's customer experience narrative into concrete screens, user flows, and design principles. Agent 3 produces this. Optional: skip it with `--skip-design`.

**Dovetail.** A UX research repository. If your team uses Dovetail, the research agent can pull customer quotes from it. Optional for the pilot.

**`.env`.** A file in the project root that holds your API keys and configuration. Never commit `.env` to git, never share it.

**Frontmatter.** The YAML block at the top of a markdown file (between `---` lines). Obsidian uses it for tags, status, and custom properties. The pipeline adds artifact type, version, and traceability links to frontmatter.

**Full pipeline.** Running all agents end to end in sequence. The `full-pipeline` command.

**Human-in-the-loop.** The design principle that the PM (you) reviews and approves every artifact before the next agent runs. Non-negotiable in this system.

**Input brief.** Your starting document. A markdown or YAML file that describes the product problem, target user, goals, and constraints. Everything else is built from this.

**Kiro.** A spec-driven coding IDE. The build spec agent formats its output so Kiro can import it as a spec and generate the implementation.

**LLM.** Large language model. The AI that does the thinking. This project uses Claude Haiku 4.5 via Bedrock.

**Obsidian.** A markdown note-taking app. This pilot uses Obsidian as the place where your drafts, revisions, and feedback live. The pipeline writes artifact copies to your Obsidian vault automatically.

**PRFAQ.** Press Release plus Frequently Asked Questions. The Working Backwards planning document: a fictional launch press release plus answers to the hard questions. Agent 2 produces this.

**Research brief.** The document Agent 1 produces. It contains market data, competitive analysis, customer evidence, and a synthesis. Every claim has a source citation.

**Revise.** Re-run an agent with feedback against an existing artifact. You get a new version (e.g., `v1.0` becomes `v1.1`). Existing artifacts are preserved.

**Tavily.** A web search API designed for LLMs. The research agent uses Tavily to find market data and competitor information.

**Terminal.** The application where you type commands. On Mac it is called Terminal; on Windows it is called PowerShell.

**Vault.** An Obsidian folder. A self-contained collection of markdown notes. You can have multiple vaults; each one is a separate workspace.

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

If you want to see the change history for this guide, check the project's git log for commits that touch `scripts/publish_pm_getting_started.py`.

Happy piloting. You will probably finish your first full run faster than you expect.
"""

with open(recap_path, "a", encoding="utf-8") as f:
    f.write(BODY_PART_6)
print(f"Getting Started (part 6, final) appended: {recap_path}")
print(f"Final output path: {recap_path}")

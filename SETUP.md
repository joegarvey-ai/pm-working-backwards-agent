# Setup Guide

This guide assumes you have never opened a terminal before. If you have, skim it. If you haven't, follow it line by line. It takes about 30 minutes.

## What it costs

This system calls the Anthropic API (Claude) and the Tavily API. Both charge per use.

| Command | Typical cost | Time |
|---|---|---|
| `research` (Agent 1 only) | ~$0.20 | 2-3 minutes |
| `generate` (research + PRFAQ) | ~$0.50-1.00 | 3-5 minutes |
| `full-pipeline` (all agents) | ~$1-3 | 5-10 minutes |
| `revise` or `revise-brd` | ~$0.30-0.50 | 1-2 minutes |

Tavily's free tier includes 1,000 searches/month. A typical full-pipeline run uses 15-30 searches. Anthropic requires a payment method on file; most PM workflows cost under $5/day.

## What you'll need before you start

- A Mac, Linux machine, or Windows machine with WSL (Windows Subsystem for Linux).
- A credit card (you'll need it to create accounts at Anthropic and Tavily; both have free tiers but require a card on file).
- About 30 minutes.

## Step 1: Open a terminal

**On a Mac**: press `Cmd + Space`, type "Terminal," and hit Enter. A black or white window with text in it will appear. That's your terminal.

**On Windows**: install WSL by following [Microsoft's instructions](https://learn.microsoft.com/en-us/windows/wsl/install). Then open "Ubuntu" from the Start menu.

**On Linux**: you already know how.

Everything in this guide that looks like `this` is something you type into the terminal and then press Enter.

## Step 2: Install prerequisites

You need three things: Python 3.11 or newer, `uv` (a fast Python package manager), and `git`.

**Check if you already have them**:

```bash
python3 --version
git --version
```

If both print version numbers, you have them. If not, install them:

- **Python**: download from [python.org](https://www.python.org/downloads/) and run the installer.
- **Git**: on Mac, run `xcode-select --install`. On Linux, `sudo apt install git`. On Windows/WSL, `sudo apt install git`.

Now install `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After it finishes, close and reopen your terminal so it picks up the new command.

## Step 3: Get API keys

You need two API keys (Anthropic and Tavily). A third (Dovetail) is optional.

### Anthropic API key

1. Go to [console.anthropic.com](https://console.anthropic.com).
2. Sign up or sign in.
3. Click "API Keys" in the left sidebar.
4. Click "Create Key." Give it any name (e.g., "pm-agent").
5. Copy the key. It starts with `sk-ant-`. Paste it somewhere safe for now. **You will not be able to see it again after you close the dialog.**
6. Add a payment method under "Billing." A typical run uses $1-3 of credit.

### Tavily API key

1. Go to [tavily.com](https://tavily.com).
2. Sign up.
3. Once signed in, your API key is shown on the dashboard. It starts with `tvly-`.
4. Copy it. The free tier gives you 1,000 searches per month, which is plenty.

### Dovetail API token (optional)

Skip this section if you don't use Dovetail.

1. Go to your Dovetail workspace settings.
2. Find the "API tokens" section.
3. Generate a new token with read permissions.
4. Copy it.

## Step 4: Download the project

In your terminal:

```bash
git clone https://github.com/joegarvey-ai/pm-working-backwards-agent.git
cd pm-working-backwards-agent
```

You are now "inside" the project folder. Everything you do next happens here.

## Step 5: Install the project's dependencies

```bash
crewai install
```

This downloads everything the agents need to run. It takes 2-5 minutes the first time.

If `crewai install` fails with "command not found," run `uv tool install crewai` first, then try again.

## Step 6: Configure your API keys

```bash
cp .env.example .env
```

Now open `.env` in any text editor (TextEdit on Mac, Notepad on Windows, or `nano .env` in the terminal). You'll see lines that look like this:

```
ANTHROPIC_API_KEY=your_anthropic_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
DOVETAIL_API_TOKEN=
```

Replace `your_anthropic_api_key_here` with the key you got from Anthropic. Replace `your_tavily_api_key_here` with the key from Tavily. If you have a Dovetail token, paste it after the `=`. Otherwise leave it blank.

Save and close the file.

**Important**: never commit `.env` to git. It is in `.gitignore` so this won't happen by accident, but don't paste your keys into any other file.

## Step 7: Your first run

Try the cheapest command first to make sure everything works:

```bash
uv run pm_agent_system research examples/input-brief-example.md
```

This runs only Agent 1 (research). It should take 2-3 minutes and cost about $0.20. When it finishes, look in the `output/` folder. There will be a new file called something like `research_brief_20260408_143022.md`. Open it. That's what Agent 1 produces.

If you see an error about a missing API key, go back to Step 6.

If you see an error about Python versions, you may need a newer Python. Run `python3 --version` and confirm it's 3.11 or newer.

## Step 8: A full pipeline run

Once `research` works, try the full pipeline:

```bash
uv run pm_agent_system full-pipeline examples/input-brief-example.md
```

This takes 5-10 minutes and costs $1-3. It produces four files in `output/`: a research brief, a PRFAQ, a BRD, and a build spec. Open each one.

## Step 9: Run on your own product problem

Copy the markdown template and fill it in:

```bash
cp examples/templates/input-brief-template.md my_input.md
```

Open `my_input.md` in your editor (or in Obsidian). Each section has an HTML comment explaining what to write. Replace the comments with your own content. Be specific — vague input produces vague output. Look at `examples/input-brief-example.md` to see the level of detail that produces good results.

Two optional sections at the top improve Obsidian vault organization if you have vault integration enabled:
- **Product Name** — a short name used for vault folder slugs (e.g., `Analytics Dashboard`)
- **Initiative** — groups products into nested folders (e.g., `Commerce Platform`)

Then run:

```bash
uv run pm_agent_system full-pipeline my_input.md
```

If you prefer YAML over markdown (developers, CI/CD), the same commands accept `.yaml` files. See `examples/input.yaml` for the YAML format.

## Troubleshooting

**"command not found: uv"** — close and reopen your terminal. If it still doesn't work, run `source ~/.bashrc` or `source ~/.zshrc`.

**"command not found: crewai"** — run `uv tool install crewai` and try again.

**"ANTHROPIC_API_KEY not set"** — check your `.env` file. Make sure the line is `ANTHROPIC_API_KEY=sk-ant-...` with no spaces around the `=`.

**"Rate limit exceeded"** — you're hitting Anthropic's rate limits. Wait a minute and try again, or upgrade your Anthropic tier.

**Agent runs but the output is bad** — your input was probably too vague. Look at `examples/input-brief-example.md` (or `examples/input.yaml`) for the level of specificity that works. The agents can only research what you tell them to research.

**Some other error** — open an issue on GitHub with the full error text. Don't include your `.env` file.

## What to read next

- [README.md](README.md) for the CLI reference and architecture overview.
- [GLOSSARY.md](GLOSSARY.md) if any of the terms in this guide are unfamiliar.
- [examples/](examples/) to see what good output looks like before you commit to running the system on your own problem.

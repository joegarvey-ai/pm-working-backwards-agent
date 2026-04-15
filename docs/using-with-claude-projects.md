# Using PM Working Backwards with Claude Desktop or Claude.ai Projects

You can run the Working Backwards pipeline entirely through conversation in Claude Desktop or a Claude.ai Project. No terminal required.

## Setup

### Claude.ai Project
1. Go to claude.ai and create a new Project
2. In the Project Knowledge section, upload these files from the repo:
   - `examples/templates/style-guide-sample.md` (or your custom style guide)
   - `.kiro/skills/research-agent/SKILL.md`
   - `.kiro/skills/prfaq-agent/SKILL.md`
   - `.kiro/skills/brd-build-spec-agent/SKILL.md`
   - `examples/input.yaml` (as a reference for the input format)
3. In the Project Instructions, paste:

> You are a senior product management partner. You have three skills loaded as project knowledge: research-agent, prfaq-agent, and brd-build-spec-agent. Guide the PM through the Working Backwards pipeline step by step. At each step, produce the artifact, then pause and ask the PM to review before proceeding to the next step. Follow the style rules in the style guide. Challenge the PM's assumptions before running research.

### Claude Desktop
1. Open Claude Desktop
2. Start a new conversation
3. Attach the same files listed above
4. Paste the same instructions as your first message

## Running the Pipeline

### Step 1: Provide your input
Paste your structured input (copy the format from `examples/input.yaml`):

```
Feature Summary: [your idea]
Goals: [measurable outcomes]
Timing: [timeline]
User Summary: [who the users are]
Success Metrics: [how you'll measure]
Known Constraints: [limits]
Business Context: [current-state metrics]
```

### Step 2: Research
Claude will challenge your assumptions with 5 questions, then produce a research brief. Review it. Ask for changes or say "approved" to continue.

### Step 3: PRFAQ
Claude produces the Working Backwards document. Review each section. Say "revise section 3 to address [concern]" or "approved" to continue.

### Step 4: BRD
Claude produces the Business Requirements Document. Review requirements and acceptance criteria. Say "approved" to continue.

### Step 5: Build Spec
Tell Claude your target tool: "Generate a build spec for Kiro" (or Claude Code, Cursor, Lovable). Copy the output and paste it into your coding tool.

## Tips
- You can stop at any step. If you only need the PRFAQ, just don't ask for the BRD.
- For PRFAQ revisions, start a new conversation with the current PRFAQ pasted in, plus your meeting notes or feedback.
- Claude.ai Projects retain the uploaded knowledge across conversations, so you don't need to re-upload each time.

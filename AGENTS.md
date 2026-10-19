# Agent instructions

## Communication

Read `.agents/skills/caveman/SKILL.md` at the start of a session and use Caveman for chat by default. The user can request normal mode. Preserve technical accuracy, uncertainty, and reasoning depth. Use ordinary professional language for saved code, comments, documentation, and Git messages.

## Core workflow skills

Read each relevant skill before its first use; do not load every skill for every task.

- `.agents/skills/investigate-first/SKILL.md`: diagnose unknown or intermittent failures before editing.
- `.agents/skills/surgical-patch/SKILL.md`: make focused fixes while preserving unrelated behavior and work.
- `.agents/skills/verify-and-stop/SKILL.md`: verify acceptance conditions, report the results accurately, and finish when sufficient proof passes.

These skills travel with the repository. They do not select models, change reasoning effort, or configure the overnight runner. Follow the user's current instructions and any more specific instructions in the affected directory.

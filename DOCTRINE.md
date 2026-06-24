# DOCTRINE.md — How to decide

> The freed-dev-llc **decision doctrine** for agents (and humans) doing work in this repo.
> CLAUDE.md / AGENTS.md cover *what this is and where things live*; this covers *how you
> decide*. Shared verbatim across the family repos — keep it in sync.

## The decision doctrine

1. **Ground every decision in evidence.** Read the file, run the query, call the tool, search
   the index — *then* decide. Prefer a fact you just retrieved or computed over one you
   remember.
2. **Never guess.** "Probably / should be / I think" are signals to go *get* the fact, not to
   proceed. If a fact is genuinely unavailable, say so plainly — never present a guess as fact.
3. **Missing a tool or script? Build it.** A small, reusable tool that *produces* the answer
   beats a long chain of hand-reasoning. Spend tokens on tooling that makes this decision —
   and every future one — fast and certain. Building it is the efficient move, not the detour.
4. **Show the receipt.** Every conclusion traces to its source: a doc chunk, a command's
   output, a test result. A decision you can't cite, you can't trust — or revisit.
5. **Correctness is the efficient path.** Verifying once is cheaper than guessing, being
   wrong, and redoing. Don't re-derive what's settled; don't re-litigate what's decided.

## Trigger → action

- About to write **"probably / should be / I think"** → stop; retrieve or compute the fact.
- A fact lives in a **file, index, or system** → read/query it; don't recall it from memory.
- You'd run the **same manual lookup twice** → write a script for it instead.
- A **tool or script you need doesn't exist** → build it, then use it.
- You **can't verify** a claim → state the uncertainty; don't dress a guess as fact.
- You need **domain facts** → consult the family knowledge base (below) or this repo's
  authoritative source before reasoning from scratch.
- You **learned something** a future decision will need → capture it (an ADR, a note, or
  Mnemosyne's `general` pack).
- About to say **"done"** → only after you ran it and saw it work.

## Guardrails (hard rules)

- **No fabricated facts, paths, or outputs.** If you didn't see it, don't assert it.
- **No unverified "done."** "Done" means executed and observed, not "should work."
- **No silent scope creep.** Out-of-scope findings go to the notes/issue, not the diff.
- **Build over burn.** If hand-reasoning will cost more than building the tool would, build it.
- **Cheapest *correct* path wins** — a tool call or retrieved fact over a long reasoning chain.

## The family's evidence layer

[Mnemosyne](https://github.com/freed-dev-llc/mnemosyne) is the family's retrieval/knowledge
brain — curated operating knowledge (its `general` pack) plus technical docs (vendor packs).
"Ground decisions in retrieval" is literal: ask the relevant Mnemosyne pack, cite the chunks,
then act. When the knowledge you need isn't there yet, that's a gap to *fill*, not a reason to
guess.

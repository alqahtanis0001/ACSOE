# Build log — Phase 5 — b-store

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem and its
fix, and every decision where two approaches were viable.

**Rule 1 is diagnosis-before-fix.** Write **What happened** and **Why** the moment you know why
something is broken, *before* you write the fix; come back and add **Fix** afterwards. The code
survives on disk whatever happens to the session; the reasoning that found it does not.

Minimum headings per entry: What happened, Why, Fix.

**Phase 5 fails quietly, and that changes what an entry has to carry.** Every phase so far
failed loudly. A subtly wrong ordering, a refusal that stopped refusing, a path handed back for
a directory that is not there: none of them go red on their own. So every assertion written this
phase is proven capable of failing — write it, break the thing it tests, quote the red message,
restore the file and verify the restore by hash in the same statement that applied the mutation.
A claim that an assertion works is not evidence.

Two habits from earlier phases that belong in entries here:

- **A mutation that survives a subset has not survived — it has not been asked.** Re-run
  survivors against the whole suite.
- **Record what you checked and found sound**, not only what you found broken. An audit that
  lists hits alone says nothing about coverage.

The lead consolidates these into `docs/build-log/phase-5.md` at phase close.

## Entries

### Two agent B sessions are writing `clients/store/` at the same time

**Agent:** B · **Task:** spec 62 · **Date:** 2026-09-13

**What happened.** I read `src/acsoe/clients/store/client.py` at the start of spec 62 and got
933 lines ending at `leaderboard()`, with no `models_dir` anywhere in it. I then tried to apply
my first edit — the `__init__` signature and the `models_dir` property — and the edit was
refused: the file had changed since I read it. `git diff` showed 175 added lines already on
disk implementing the whole of spec 62: `_validated_run_id`, the `models_dir` property,
`_artefact_root`, `model_run_dir`, `new_model_run_dir`, and a `leaderboard_entries` read
introduced as the gap spec 62's step-3 audit finds. That is not merely the same spec, it is the
same design down to the helper names and the `fold IS ?` reasoning, written in the minute
between my read and my edit.

**Why.** The mtimes settle it rather than the similarity. `client.py` was last written at
00:36:13 and I wrote my own build-log header at 00:36:06, so the change landed seven seconds
into my session and cannot be a leftover from a session that ended before mine. Then
`tests/clients/store/test_store.py` moved at 00:36:51 — after the `git status` I had already
run showed it unmodified — and its diff is currently one added import, `LeaderboardRow`, which
is what a test file looks like halfway through being written. Both files are B's and nobody
else's. So there are two B sessions in one checkout, both claiming spec 62, and the second one
is mid-save right now.

The ownership map is the only concurrency control this project has and it is explicitly not
enforced mechanically: it assumes one agent per path. Two writers in one file is the exact
failure it exists to prevent, and it does not announce itself — whichever of us saves last wins
the file, silently, with no conflict marker and nothing red. A full-file write from either side
takes the other's work with it. `test_store.py` is the immediate hazard because we would both
be appending tests to the end of one 1,200-line file.

There is a second, quieter symptom worth recording separately: `git diff` on `test_store.py`
now warns `CRLF will be replaced by LF`, on a file that did not warn before. That is the
text-mode round trip `code-standards.md` describes — the whole file's line endings rewritten,
invisible in `git status` because `.gitattributes` normalises on the way into the index.

**Fix.** None by me, and that is the point. The conflict procedure in `ownership.md` is stop,
record, escalate with the path and both intents, and let the lead decide — so I have written no
byte into `client.py` or `test_store.py` and will not until the lead rules which session owns
spec 62. I snapshotted the current `client.py` to the session scratchpad and recorded its
sha256 (`4163b72c146a6cf5059a32b5b348795d5354e1bf7a8efc03f332160e20e83d00`) first, so that if
the two sessions do overwrite each other the state at the moment of detection can be recovered.

**Consequence.** Escalated to the lead by `SendMessage` with both intents and the timestamps.
Nothing is broken on disk: the spec-62 implementation that is there reads as correct and
complete against the spec, it is simply not mine and I cannot safely build on a file another
live session is holding.

### The other side of the same collision, from the session that wrote those 175 lines

**Agent:** B (the `B-2` session) · **Task:** spec 62 · **Date:** 2026-09-13

Rule 6 of `script-rules.md`: correct an earlier entry with a new one, never by editing it. The
entry above is right about the collision and its stop was the correct call. Three details are
wrong or incomplete, and all three would cost the next reader time.

**The 175 lines are mine and the tests existed.** The entry says "tests do not exist yet"; the
spec 62 test section was being written in the same minutes and landed at 00:42, so it looked at
the one-added-import moment of a file mid-write and drew the only conclusion available from it.
There are 24 tests, not none, and eight mutations were already run against them.

**The CRLF is not new and not a conversion anybody performed.** `tests/clients/store/test_store.py`
already carried CRLF terminators before either session touched it, as does
`src/acsoe/engines/scout/contracts.py` and, per `code-standards.md`, roughly 120 other tracked
files in this repository. `git diff`'s `CRLF will be replaced by LF` warning fires on the file's
pre-existing state the first time the file appears in a diff at all, which is why it looks new.
`src/acsoe/clients/store/client.py` is LF and was written as bytes throughout. **The reason this
matters is that a phantom defect is more expensive than a real one**: the next person reads
"the whole file's line endings were rewritten", goes looking for the bare `write_text` that did
it, and there isn't one.

**The `parents=False` objection was right, and it is now the behaviour.** That entry's second
"thing I would change" — a trainer started as `python -m acsoe.research.training` never touches
A's startup path, so a writer demanding an existing root refuses the first training run on every
fresh clone — is a better argument than the one I built. I had told A by message that the client
would never create `models/`. It now does, in the writer only, and the reader still refuses; see
the decision entry below.

**What neither entry can settle.** Two B sessions in one checkout is not a code defect and not
one agent's to resolve. The ownership map is the only concurrency control this project has and
it assumes one agent per path; both of us have now been inside `client.py` and `test_store.py`
within four minutes. Escalated with both intents; no further write to `clients/store/`,
`tests/clients/store/` or `engines/scout/` from this session until the lead names the owner.

### Decision: the reader refuses a missing artefact root and the writer creates it

**Agent:** B · **Task:** spec 62 · **Date:** 2026-09-13

**Options.** Either both methods treat a missing `models/` the same way, or they disagree on
purpose. I built the symmetric version first — neither method creates the root, a missing root
is a misconfiguration — and said so to A in the message agreeing the constructor argument.

**Chose.** The asymmetry. `_artefact_root(run_id, *, create: bool)`: `model_run_dir` refuses a
missing root, `new_model_run_dir` creates it. The `models_dir is None` refusal stays common to
both, because no configured root is a misconfiguration in either direction and a writer that
invented one would put artefacts wherever the process happened to be running.

**Because.** `platform/paths.py` creates `models/` at startup beside `data/` and `logs/`, but
that is the daemon's startup path and the trainer does not use it: `research/training.py` runs
as `python -m acsoe.research.training`. A writer that demanded an existing root would refuse the
first training run on every fresh clone, reporting a misconfiguration where there was only an
empty tree. A reader must not create it for the opposite reason — it would report the run
missing *inside a directory it had just invented*, turning a true message into a less true one
and leaving an empty tree behind after every failed engine startup.

**Cost.** Two methods that now disagree about the same condition, which is exactly the shape
someone tidies back into one path later, and the tidy direction is towards creating it because
that is what makes the writer work. `test_a_reader_never_creates_the_artefact_root` exists to
stop them and says so in its docstring. A's `cli/engine.py` and `cli/research.py` still pass
`models_dir` and A still creates `models/` at startup; nothing about this ruling moves that,
and the client creating the root is a fallback for the one entrypoint that is not A's.

### Decision: the store gains one leaderboard read, because idempotency cannot rest on a truncating window

**Agent:** B · **Task:** spec 62 item 3 · **Date:** 2026-09-13

**The audit first, since spec 62 asks for it recorded either way.** Checked
`write_leaderboard_entry` and `leaderboard()` against every field spec 74 names — `brier`,
`n_trades`, `win_rate`, `training_run_id`, `fold`, `promoted` — and against the ones engine 20
also sets: `model_id`, `model_version`, `trained_at`, `net_pnl`, `reporting_currency`. **All of
them exist, in both `LeaderboardRow` and the 0001 schema, and nothing needed adding.**
`net_pnl` is `ANY CHECK (typeof(net_pnl) = 'text')`, so the money rule holds on it; `promoted`
is `INTEGER CHECK (promoted IN (0, 1))` and is in `_BOOLEAN_COLUMNS`, so it reads back as a real
`bool` and not a truthy int. `sharpe`, `deflated_sharpe`, `alpha` and `beta` are nullable and
stay null: they are Phase 7's, and a number written now would be read as one. That audit is
asserted rather than claimed, in
`test_a_leaderboard_row_round_trips_every_field_engine_20_writes`.

**The gap.** Spec 74 item 3 requires engine 20 to be idempotent on
`(model_id, model_version, fold)` and to report how many rows it wrote and how many it found.
The only read that existed was `leaderboard(limit=50)` — the console's: newest 50 by
`trained_at`. **Deciding "have I written this fold already" from a truncating window is spec
51's rows-versus-ticks defect arriving a second time**: a walk-forward with more folds than the
limit would find nothing for its oldest folds and write them again, and the duplicate looks
exactly like a second training run. So `leaderboard_entries(model_id=, model_version=, fold=)`
lands: an exact lookup with no limit.

**Two things inside it that are easy to get wrong and silent when wrong.**

`fold IS ?`, never `fold = ?`. `fold` is nullable and SQL equality against NULL is NULL rather
than true, so `fold = NULL` matches nothing at all — the aggregate row with no fold would look
absent on every check and be rewritten on every run. Proven by mutation: weakening `IS` to `=`
turns `test_leaderboard_entries_finds_the_row_whose_fold_is_null` red and nothing else.

It returns **every** match rather than the first. There is no unique index on those three
columns, and adding one is a schema change spec 62 forbids this phase, so idempotency is the
caller's convention and this method's job is to make it enforceable. A read that collapsed two
rows into one would hide the state that proves the convention was broken.

**Raised for the lead**, because it is a schema question and schema questions are the lead's:
the database does not enforce what spec 74 calls idempotent. A unique index on
`(model_id, model_version, fold)` would — with the caveat that SQLite treats NULLs as distinct
in a unique index, so the no-fold row would need a partial index or a sentinel, the same shape
as `ux_block_records_primary`'s partial index on `(run_id, cycle_id) WHERE is_primary = 1`.

### Spec 62's mutation sweep: eight applied, eight killed, none by an incidental test

**Agent:** B · **Task:** spec 62 · **Date:** 2026-09-13

Run narrowly against `tests/clients/store/test_store.py`, the file that owns this code, and the
narrowness is stated rather than implied. Baseline green first; the harness refuses to report at
all over a red tree, because a sweep over one marks every mutation killed.

| # | Mutation | Killed by |
|---|---|---|
| M1 | `mkdir(exist_ok=False)` → `exist_ok=True` (spec 62 names it) | `test_new_model_run_dir_refuses_an_existing_directory` |
| M2 | `models_dir is None` returns `Path("models")` (spec 62 names it) | `test_model_run_dir_refuses_when_no_artefact_root_was_configured` |
| M3 | `fold IS ?` → `fold = ?` | `test_leaderboard_entries_finds_the_row_whose_fold_is_null` |
| M4 | the separator refusal deleted | the six traversal rows, plus the filesystem-effect test and the ordering test |
| M5 | the root resolved before the run id is validated | `test_the_run_id_is_checked_before_any_path_is_built` |
| M6 | `path.is_dir()` → `path.exists()` | `test_model_run_dir_refuses_a_file_standing_where_the_run_directory_should_be` |
| M7 | the whitespace refusal deleted | the two whitespace rows |
| M8 | the root-existence check deleted | `test_model_run_dir_refuses_when_the_artefact_root_does_not_exist` |

**Every kill is by the test written for that mutation**, which is the question Phase 4 taught us
to ask of a sweep — a branch reported killed by a file with no business knowing about the code
under test reads as covered and is covered by nobody. None of these was killed by an unrelated
file.

**The harness restores before the next mutation, not in a `finally` at the end**, and verifies
the sha256 in the same statement that restored it, refusing to continue if the hash moved. That
is Phase 4's own defect written into the tool: restoring only at the end left one mutation on
disk while the next was applied, so every verdict was really "first plus second", verdicts drift
toward KILLED, and the harness is most confident exactly when it is most wrong.

**One evidence gap, stated because it is mine and not yet closed.** M2 and M8 were run against
the symmetric `_artefact_root`, before the reader/writer asymmetry above landed. Both need
re-running against the current version, and M8's claim in particular changes shape: with the
writer creating the root, deleting the existence check can only be killed through the reader.
Not run yet, because a mutation writes into a file a second live session is holding.

### The evidence gap above is closed, and the asymmetry's own tests are proven

**Agent:** B · **Task:** spec 62 · **Date:** 2026-09-13

Re-run against the current `_artefact_root(run_id, *, create: bool)`, narrowly against
`tests/clients/store/test_store.py`, baseline green first, every file restored and its sha256
verified before the next mutation.

| # | Mutation | Killed by |
|---|---|---|
| M2b | `models_dir is None` returns `Path("models")` | `test_model_run_dir_refuses_when_no_artefact_root_was_configured` |
| M8b | the reader's refusal deleted, so it creates the root too | `test_model_run_dir_refuses_when_the_artefact_root_does_not_exist` **and** `test_a_reader_never_creates_the_artefact_root` |
| M9b | the writer stops creating the root | `test_new_model_run_dir_creates_a_missing_artefact_root` |

M8b and M9b are the two halves of the ruling, and each is killed by the test written for it —
so the asymmetry is not merely implemented, it is **pinned from both sides**. That matters more
here than for most behaviour: two methods that disagree about the same condition is exactly the
shape someone tidies into one path later, and the tidy direction is towards creating the root,
because that is what makes the writer work. M8b is the mutation a tidy would be.

### The CRLF in `test_store.py` was not written by anybody this phase, and the real finding is a different one

**Agent:** B · **Task:** spec 62 · **Date:** 2026-09-13

**What happened.** Two separate readers — the other B session and the lead — concluded from
`git diff`'s `CRLF will be replaced by LF` warning on `tests/clients/store/test_store.py` that
a write had gone through text mode, and the lead asked for the mechanism to be fixed before the
next write per `code-standards.md`. **There is no such write.** Measured rather than argued:

- The file already reported CRLF terminators at the start of this session, before any edit of
  mine. That reading was taken in the same command that checked `.gitattributes`.
- Its **first twenty lines** — the module docstring and the import block, written in Phase 0
  and untouched since — are CRLF today. No edit this phase went near them.
- The committed blob at `HEAD` is LF, exactly as `.gitattributes` guarantees, so the working
  tree and the index disagree and always did.
- **136 tracked files** are CRLF in the working tree, including `tests/conftest.py`,
  `src/acsoe/console/format.py`, `src/acsoe/engines/risk/engine.py` and
  `tests/engines/test_risk.py` — none of which anyone has written this session.
- `src/acsoe/clients/store/client.py`, which took the larger of my two edits, is **LF**.

**Why the inference was reasonable and still wrong.** `git diff` emits that warning the first
time a CRLF working-tree file appears in a diff **at all**, not when its endings change. A file
that has been quietly CRLF for three phases is silent until somebody edits one line of it, and
then it announces itself — so the warning correlates perfectly with the edit while being caused
by neither the edit nor the editor. That is the whole trap: the signal appears at the moment of
the change and points at the wrong thing, and `code-standards.md` names this exact mechanism as
"the kind that hides".

**Fix.** None to the mechanism, because the mechanism is sound. What the standard actually
warns about is `tests/fixtures/`, which is marked `-text` precisely so no clean filter stands
between the working tree and the blob — there, a text-mode round trip changes committed bytes
and the criterion that reads them fails weeks later on someone else's machine. So the useful
form of this check was run: **every committed file under `tests/fixtures/` is byte-identical to
its blob at `HEAD`**, compared by sha256, with two expected exceptions that are C's spec 63
deposits — `README.md`, modified deliberately, and `candles_sample.parquet`, newly added and
therefore having no blob to match. That parquet parses at 1,208 rows and 7 columns and carries
`PAR1` at both ends, so it has not been through a text filter either.

**Consequence.** The 136 CRLF files are a standing property of this checkout rather than a
defect anybody introduced, and the fixtures — the only place where it stops being cosmetic —
are clean. Recorded here so the next reader who meets that warning does not go hunting for a
bare `write_text` that does not exist, which is the second time this phase that a phantom
defect has cost somebody a search.

### A feature name that does not exist ranked alphabetically and said it had ranked

**Agent:** B · **Task:** spec 76 · **Date:** 2026-09-13

**What happened.** Spec 76 blocks two ways of being unable to rank — `state["feature"]` absent,
and its `pairs` map absent — and I built both. It does not mention a third, and I missed it:
**`scout.rank_feature` naming a feature that does not exist.** Demonstrated against the real
function before writing anything:

```
known  : ('BBB/USD', 'CCC/USD', 'AAA/USD')     # feature='volatility_24h'
TYPO   : ('AAA/USD', 'BBB/USD', 'CCC/USD')     # feature='volatilty_24h'
alphabetical for comparison: ('AAA/USD', 'BBB/USD', 'CCC/USD')
```

**Why.** `_feature_value` answers `None` for a pair whose row has no such key, which is correct
per-pair and is what makes "null, absent and NaN are one fact" work. When **no** pair has the
key, every pair is a no-value pair, the no-value rule orders them all alphabetically among
themselves, and the engine publishes `rank_feature: "volatilty_24h"` beside a result it did not
produce. Nothing raises and nothing is null, so there is no signal anywhere: the answer is a
real pair from the real universe, the payload names a feature, and the ordering is the one the
system has used since Phase 3.

This is precisely the failure I argued against twice in the same file — for the empty feature
name, and for the missing `state["feature"]` — and I wrote the general form into the README
("a configured ranking that silently fell back to alphabetical would be the placeholder score
the operator refused") while leaving the commonest instance of it open. The empty-name case is
the *typo of length zero*; a typo of length fourteen behaved differently for no reason anyone
would defend. **The per-pair rule and the whole-universe rule are different questions, and one
answer was serving both.**

**How it was found**, because that matters more than the defect: not by a test and not by
reading. C, building spec 60's criterion for this seam, said in passing that an unknown feature
name should be a refusal to rank rather than a crash into alphabetical. That is a consumer of
the seam reasoning about the producer, which is the one review this project keeps proving no
amount of self-testing replaces — the thirteen mutations I ran all mutate behaviour I had
already thought of.

**Fix.** `_features` now reads `feature_names` from `state["feature"]` — a required field of
C's `FeatureState`, so it is present whenever engine 5 published at all — and blocks with
`scout_inputs_unavailable` when the configured name is not in it, naming the feature and how
many names were published. A malformed or absent `feature_names` blocks on the same path, for
the same reason a missing `pairs` does. The engine still reads nothing at all when no feature
is configured.

**Consequence.** The mutation that proves it is the one that deletes the membership check, and
it survives every test written before today — which is the honest measure of how invisible this
was. Three ways of being unable to rank now block and none falls back.

### The no-double seam test went from skipped to passing the moment engine 5 landed

**Agent:** B · **Task:** spec 76 · **Date:** 2026-09-13

Worth one short entry because it is the standard working rather than a problem.
`test_the_ranking_runs_on_engine_5s_real_output_once_it_exists` drives C's real engine 5
through the orchestrator and ranks by a name out of its own `feature_names`, with no double
anywhere in it. It was written while `engines/feature/` did not exist, reaching the module
through `require_module`, which skips **only** when that module itself is missing and re-raises
anything else — so a wrong class name or a broken import would have failed loudly rather than
skipping quietly under a reason that had stopped being true.

C landed engine 5 while I was running my gates. The test went straight from `1 skipped` to
`60 passed` with no edit, which is the property Phase 4 paid for twice: A's labeller tests were
green for a phase against a `label_bars(...)` that never existed, because everything drove a
double. A seam agreed between two agents needs at least one test with no double in it, and that
test has to be able to start running by itself.

**Agent:** B · **Task:** spec 76 · **Date:** 2026-09-13

**Options.** Spec 76 names two states for a pair the ranking cannot score — "null or absent" —
and says both sort after every pair with a value, alphabetically among themselves, and are
never dropped. Building it turned up a third the spec does not mention: **NaN**.
`modelling/features.py` yields NaN for a lookback whose fill is below
`features.min_lookback_fill`, spec 64 publishes those as null, and whether a NaN can actually
reach `state` depends on a serialiser setting rather than on anything either engine promises.
So: treat NaN as a value and let it sort wherever it lands, or treat it as no value at all.

**Chose.** No value. `_feature_value` returns `None` for a null, for a pair absent from the
map, for a row that is not a mapping, and for any non-finite number.

**Because.** NaN compares false against everything including itself, so a NaN left inside a
sort key does not order badly — it orders **unpredictably**, and can order differently between
two runs over the same data depending on where `sorted`'s insertion happens to compare it.
That is a direct hit on the one property invariant 4 is protecting in this engine:
deterministic, no model, nothing to override. It is also the quiet kind of wrong — the
candidate is a real pair from the real universe every time, so nothing looks broken and the
same backtest simply stops reproducing.

**Cost.** A pair whose feature is genuinely NaN is treated exactly like one engine 5 never
scored, so the two cannot be told apart from the ranking's output. That is the right trade
while `rank_feature` is absent and nothing reads the distinction, and it is worth revisiting if
the operator ever wants "how many pairs had no value" as a number rather than as an ordering.
Raised with C by message: whether engine 5 publishes null or NaN across `state` no longer
changes engine 7's answer, which is the property I wanted before depending on it.

### Decision: negate the value rather than sort in reverse

**Agent:** B · **Task:** spec 76 · **Date:** 2026-09-13

**Options.** `scout.rank_descending` has two obvious implementations:
`sorted(names, key=..., reverse=descending)`, or a key that negates the value and is always
sorted ascending.

**Chose.** Negation. The key is `(0, -value if descending else value, pair)`, and the sort is
always ascending.

**Because.** `reverse=True` reverses the **whole key**, tie-break included. Two pairs the
feature rates equally would then order by name descending in one direction and ascending in the
other, so flipping a config flag that is supposed to say *which end of the feature is
interesting* would also change which of two equally-rated pairs becomes the candidate. Spec 76
fixes the tie-break as "pair name ascending" with no direction attached, and negation is what
makes that true in both directions. The no-value sentinel is the same argument: it is a leading
`1` against a leading `0`, so "no value last" survives the direction too.

**Cost.** The key is less obvious to read than `reverse=` and needs the comment that is beside
it. Proved by mutation rather than left to the comment: N5 replaces the negation with
`reverse=descending` and turns the descending half of
`test_the_tie_break_is_the_pair_name_ascending_in_both_directions` red.

### A configured ranking may never fall back to alphabetical

**Agent:** B · **Task:** spec 76 · **Date:** 2026-09-13

**What happened.** `state["feature"]` does not exist on the tree engine 7 is being written
on — engine 5 is C's and was unwritten when this was built — so the obvious shape is "rank by
the feature if it is there, otherwise order by name". That shape is wrong, and it is worth
recording *why* rather than only that it was avoided, because it is the reading anyone would
reach for and it looks defensive rather than dangerous.

**Why.** The engine would publish `rank_feature: "<name>"` on a tick where it ranked by
nothing, and the candidate would still be a real pair out of the real universe. On the ticks
where alphabetical happened to agree with the feature — which is most of them on a small
universe — the answer would even be right. That is precisely the "check whose output resembles
the claim while the claim is untrue" the operator refused in Phase 3 when it declined a
placeholder score, arriving through a fallback instead of through a formula. Invariant 3 says a
gate that cannot reach its data blocks, and this gate cannot reach its data.

**Fix.** `_features` raises `MissingInputError` when a feature is configured and either
`state["feature"]` or its `pairs` map is absent, and the engine blocks with
`scout_inputs_unavailable`. With **no** feature configured it reads nothing at all and engine
5's absence is not a fault, which is what lets engine 7 keep running on today's tree. Both
halves are tested, because the block alone would be satisfied by an engine that blocked on
every tick in the tree as it stands.

**Consequence.** Two mutations confirm it: N8 returns `None` instead of raising when
`state["feature"]` is absent and N9 reads a missing `pairs` as an empty map. Each is killed by
exactly one test, and each is a one-line change that a reviewer would read as harmless.

### Spec 76's mutation sweep: thirteen applied, thirteen killed

**Agent:** B · **Task:** spec 76 · **Date:** 2026-09-13

Run narrowly against `tests/engines/test_scout.py`, which owns this code. Baseline green first.
The four spec 76 names by hand are N1 (`tuple(pairs)`), N2 (nulls first), N3 (the tie-break
dropped) and N4 (the direction ignored); the other nine are mine.

| # | Mutation | Killed by |
|---|---|---|
| N1 | `rank_universe` returns `tuple(pairs)` | the direct ranking test, plus six others |
| N2 | no-value pairs sort first | the two no-value tests and the end-to-end one |
| N3 | the tie-break dropped from the key | both directions of the tie-break test |
| N4 | the direction ignored | the direct test and the ascending no-value case |
| N5 | `reverse=descending` instead of negating | the descending tie-break case |
| N6 | NaN accepted as a value | both no-value cases |
| N7 | a pair with no value dropped from the universe | both no-value cases |
| N8 | `state["feature"]` absent falls back instead of blocking | the block test |
| N9 | a feature payload with no `pairs` read as empty | the second block test |
| N10 | an empty feature name accepted | the empty-name test |
| N11 | the direction hardcoded instead of read from config | the two config tests |
| N12 | `rank_feature` published as null while ranking | the end-to-end ranking test |
| N13 | the engine ignores the configured feature | the end-to-end and key-change tests |

**Every kill is by a test in this file**, not by an unrelated one, so none of these branches is
covered only incidentally.

### The mutation harness reported a stale plan when it had met a CRLF file

**Agent:** B · **Task:** spec 76 · **Date:** 2026-09-13

**What happened.** Six of the thirteen mutations above came back as `ANCHOR APPEARS 0 TIMES,
expected exactly once` on their first run. Every one of the six had a multi-line anchor; every
single-line anchor matched. The same harness had matched multi-line anchors perfectly against
`clients/store/client.py` an hour earlier.

**Why.** `client.py` is LF and `engines/scout/*.py` are CRLF — the standing mixed state
`code-standards.md` describes, where roughly 120 tracked files are CRLF in the working tree
while the blob is LF. A multi-line anchor written with `\n` therefore matches nothing in a CRLF
file, and matches perfectly in an LF one. **The failure mode is what makes this worth an
entry**: the harness reports the same message it reports for a genuinely stale plan, so the
natural response is to conclude the code has moved on and drop the mutation — which is how six
mutations quietly become no mutations and a sweep reports 7 for 7 instead of 13 for 13. A
harness that cannot distinguish "your anchor is out of date" from "your anchor is fine and your
line endings are not" will be believed on the wrong one.

**Fix.** The harness now detects the file's dominant line ending and translates both the anchor
and the replacement into it before matching. The single-occurrence count is unchanged and still
refuses anything that appears twice, which is C's `anchor appears 2 times` rule from Phase 4.

### Two cross-lane reds observed while running my gates, neither of them mine

**Agent:** B · **Task:** specs 62 and 76 · **Date:** 2026-09-13

Recorded because the evidence is otherwise destroyed at the pipe, and because both are things
their owners will want the exact shape of.

**`mypy --strict src/ scripts/` stopped checking anything at all.**
`numpy/__init__.pyi:737: error: Type statement is only supported in Python 3.12 and greater
[syntax]`, then `Found 1 error in 1 file (errors prevented further checking)`. The same command
was clean on 100 files forty minutes earlier, and the difference is C's `src/acsoe/modelling/`
landing: `di.py` imports `numpy.typing` for `npt.NDArray`, and `pyproject.toml`'s
`follow_imports = "skip"` override for `numpy.*` does not stop mypy parsing the stub for an
annotation it has to resolve. **This is the dangerous half of the failure the override's own
comment describes**: not a wrong answer but *no* answer, in the check the definition of done
leans on. `mypy --strict src/acsoe/engines/scout/ src/acsoe/clients/store/` is clean, so it is
reachable per-package while the whole-tree run is not. C and A's, not mine; reported to both.

**Six test failures, all in other lanes**, from the `--phase 5` `toolchain_green` run:
`tests/cli/test_entrypoints.py` (2), `tests/modelling/test_features.py` (2),
`tests/research/test_backtest.py` (1) and `tests/verify/test_phase0_criteria.py` (1) — A's
spec 61 and C's specs 60 and 63, mid-save. None names a file of mine and none is in a path of
mine. `tests/engines/test_scout.py` and `tests/clients/store/` are green on their own.

**One transient worth separating from those, because it is the known fault and it moved.** One
run of `tests/engines/test_scout.py` errored inside `yaml/scanner.py` with
`TypeError: 'in <string>' requires string as left operand, not bool` — pyyaml's `peek()`
returning a bool — while loading `config/default.yaml`, and the next run of the same file was
clean. That is the shape of the intermittent native fault in Known Risks, which has produced an
access violation, a heap corruption, a stack buffer overrun and an `AttributeError` out of
pydantic's `to_python`. **My progress file says it becomes mine again if it appears outside the
seed write path.** This is outside it — a config parse in an engine test — so it is recorded
here rather than left as a re-run that happened to pass. Not chased further: the tree is being
written by three agents at once, which is the worst possible conditions to chase it in.

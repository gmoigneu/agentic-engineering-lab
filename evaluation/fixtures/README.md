# Evaluation fixture approval

Each role requires five development cases and five held-out cases. Cases must refer to real immutable commits in repository `1303663681`.

The reviewer `gmoigneu` approves labels before the first candidate run. Held-out labels remain unavailable to the model runtime and cannot be changed in response to model output.

The approved source history is pinned at base commit `4e6de2aaf09380b0578aa31aa416fa30d06544a9`. Ten pull requests and their first completed failing `test` checks are frozen in [evidence-output.json](../evidence-output.json). The role and split directories contain thirty `fixtures-v1` cases.

The labels originate from the approved [fixture-plan-v1.md](../fixture-plan-v1.md). Regenerate the files only from immutable [seed-output.json](../seed-output.json) with `scripts/materialize_evaluation_fixtures.py`. A later check rerun does not replace the earliest pinned failing check.

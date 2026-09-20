from antomnievo.model.candidate_data import CandidateMeta, CandidateSummary, ChangeLogEntry, RunAnalysis, RunRecord
from antomnievo.model.tunable_artifact_schema import FileSchema, FolderSchema

"""
Candidate data directory layout:
    {candidate_id}/data/
    ├── meta.json
    ├── summary.json
    ├── changelog.jsonl
    ├── system_run/
    │   └── {data_id}/
    │       └── run_{timestamp}.json
    └── proposer_run/
        ├── analysis/
        │   ├── trajectory/
        │   │   └── {child_id}.json
        │   └── result/
        │       └── {data_id}.json
        └── mutation/
            └── {child_id}.json
"""
CANDIDATE_DATA_SCHEMA = FolderSchema(
    name="data",
    description=(
        "Candidate evaluation data directory. Contains metadata, scores, "
        "mutation history, proposer trajectories, and per-instance run records."
    ),
    files=[
        FileSchema(
            name="meta.json",
            description=CandidateMeta.to_description(),
        ),
        FileSchema(
            name="summary.json",
            description=CandidateSummary.to_description(),
        ),
        FileSchema(
            name="changelog.jsonl",
            description=ChangeLogEntry.to_description(),
        ),
        FolderSchema(
            name="system_run",
            description="Per-data-instance system run records.",
            files=[
                FolderSchema(
                    name="{data_id}",
                    description="Run records for a specific data instance.",
                    files=[
                        FileSchema(
                            name="run_{timestamp}.json",
                            description=RunRecord.to_description(),
                        ),
                    ],
                ),
            ],
        ),
        FolderSchema(
            name="proposer_run",
            description="Proposer execution data. Stored on the parent candidate.",
            files=[
                FolderSchema(
                    name="analysis",
                    description="Analysis phase data.",
                    files=[
                        FolderSchema(
                            name="trajectory",
                            description="Analysis phase trajectories.",
                            files=[
                                FileSchema(
                                    name="{child_id}.json",
                                    description=(
                                        "Analysis phase trajectory: the trace of the analysis agent reading "
                                        "run records and producing analysis results. Captures tool calls, "
                                        "reasoning steps, and the analysis output."
                                    ),
                                ),
                            ],
                        ),
                        FolderSchema(
                            name="result",
                            description="Analysis results keyed by data_id.",
                            files=[
                                FileSchema(
                                    name="{data_id}.json",
                                    description=RunAnalysis.to_description(),
                                ),
                            ],
                        ),
                    ],
                ),
                FolderSchema(
                    name="mutation",
                    description="Mutation phase trajectories.",
                    files=[
                        FileSchema(
                            name="{child_id}.json",
                            description=(
                                "Mutation phase trajectory: the trace of the mutation agent reading "
                                "analysis and modifying the tunable artifacts. Contains the full trace of "
                                "the agent's reasoning, tool calls (file reads, edits, diff), "
                                "and final result."
                            ),
                        ),
                    ],
                ),
            ],
        ),
    ],
)


if __name__ == "__main__":
    from antomnievo.model.tunable_artifact_schema import render_tunable_artifact_schema

    print(render_tunable_artifact_schema(CANDIDATE_DATA_SCHEMA))

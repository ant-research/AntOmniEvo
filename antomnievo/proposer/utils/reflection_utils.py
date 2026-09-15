"""Helpers for reflection-mode proposing.

Functions that require ``CandidateStore`` access (changelog reads, analysis
reads) remain here as module-level functions. Pure-data transformations on
``MaraChain`` / ``ChainNode`` live as methods on those classes instead.

Chain semantics recap (see also ``ChainNode``)::

    chain[0]       = root (the original parent that was selected for mutation)
    chain[1]       = first failed child
    chain[2..-1]   = subsequent failed reflection attempts
    new_candidate  = about to be produced; passed separately

Key cross-candidate relationships:

* **Changelog** accumulates: ``chain[i].changelog == chain[i-1].changelog + [the
  entry chain[i] added when its spec was mutated]``. So the node at index ``i``
  in the chain authored ``chain[i].changelog[len(chain[i-1].changelog):]``.
  The root's changelog entries pre-existed the mara chain.
* **Analysis files**: ``candidate X``'s ``analysis/result/{data_id}.json`` is
  written by ``X``'s NEXT reflection child during *its* analysis phase. So
  analyses exist for chain[0..-2] but NOT for chain[-1] — chain[-1]'s analysis
  is exactly what the current reflection iteration is about to write.
"""

import json

from antomnievo.interface.candidate_store import CandidateStore
from antomnievo.model.antomnievo_data import ChainNode


def build_attributed_changelog(
    chain: list[ChainNode],
    store: CandidateStore,
    max_diff_chars: int,
) -> str:
    """Render the chain's changelog entries (without author attribution).

    Only reads ``chain[-1]``'s changelog — it already contains every entry
    accumulated up and down the chain. We then take its LAST
    ``len(chain) - 1`` entries, which correspond to the mara chain
    candidates. Entries before that suffix pre-existed the mara chain
    and are NOT shown — they are not relevant to reasoning about the chain.

    Each entry is rendered as::

        {<json with truncated diff>}

    Returns "(no chain changelog entries)" when the chain has zero authored
    entries (e.g. chain of length 1 with only root).
    """
    if len(chain) < 2:
        return "(no chain changelog entries)"

    last_changelog = store.read_changelog(chain[-1].candidate_id) or []
    expected = len(chain) - 1

    chain_entries = last_changelog[-expected:] if len(last_changelog) >= expected else last_changelog

    lines: list[str] = []
    for entry in chain_entries:
        lines.append(
            entry.truncate_diff(max_diff_chars).model_dump_json()
        )

    if not lines:
        return "(no chain changelog entries)"
    return "\n".join(lines)


def preload_chain_analyses_for_data_id(
    chain: list[ChainNode],
    data_id: str,
    store: CandidateStore,
) -> str:
    """Concatenate every chain candidate's analysis for ``data_id``, with attribution.

    For each node in the chain whose ``analysis/result/{data_id}.json`` exists,
    emit a labelled block::

        ## analysis at {candidate_id} for data_id={data_id}
        <raw json>

    Nodes without an analysis file for this data_id are skipped silently
    (the last chain node's analysis is exactly what this reflection
    iteration is about to write).

    Returns "(no prior analyses for this data_id)" when nothing is found.
    """
    block_dict: dict[str, str] = {}
    for node in chain:
        content = store.read_analysis_content(node.candidate_id, data_id)
        if content is None:
            continue
        block_dict[node.candidate_id] = content

    if not block_dict:
        return "(no prior analyses for this data_id)"

    return json.dumps(block_dict, indent=2)

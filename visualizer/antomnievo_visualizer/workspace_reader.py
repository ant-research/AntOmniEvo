"""
Workspace reader helpers backed by CandidateStore.

These helpers shape candidate / statistics data into the JSON payloads
served by the Flask routes in server.py. Kept in a separate module so the
route layer stays focused on HTTP concerns.
"""

import contextlib
import json
import os

from antomnievo.interface.candidate_store import CandidateStore
from antomnievo.store.candidate_store import LocalCandidateStore


def _read_run_score(file_path: str) -> float | None:
    """Extract evaluation_result.score from a run JSON file."""
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("evaluation_result", {}).get("score")
    except Exception:
        return None


def _build_run_scores(runs: dict[str, list[str]]) -> dict[str, float]:
    """Build {data_id: score} from the latest run file per data_id."""
    scores: dict[str, float] = {}
    for data_id, files in runs.items():
        if not files:
            continue
        # Use the last (latest) file
        score = _read_run_score(sorted(files)[-1])
        if score is not None:
            scores[data_id] = score
    return scores


def safe_listdir(path: str) -> list[str]:
    """List directory entries, excluding hidden files, sorted."""
    try:
        return sorted(e for e in os.listdir(path) if not e.startswith('.'))
    except FileNotFoundError:
        return []


def list_artifact_files(artifact_dir: str) -> list[str]:
    """Recursively list every file under artifact_dir, as absolute paths.

    Hidden files and directories (leading dot) are skipped — they're never part
    of the candidate's tunable artifacts, just editor / VCS noise. Order is deterministic
    (alphabetical full path) so the UI doesn't shuffle between requests.
    """
    if not os.path.isdir(artifact_dir):
        return []
    collected: list[str] = []
    for root, dirs, files in os.walk(artifact_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        for fname in sorted(f for f in files if not f.startswith('.')):
            collected.append(os.path.join(root, fname))
    return collected


def batch_run_scores(store: CandidateStore, candidate_ids: list[str]) -> dict[str, dict[str, float]]:
    """Return {candidate_id: {data_id: score}} for multiple candidates in one call."""
    result: dict[str, dict[str, float]] = {}
    for cid in candidate_ids:
        system_run_dir = store.system_run_dir(cid)
        if not os.path.isdir(system_run_dir):
            result[cid] = {}
            continue
        runs: dict[str, list[str]] = {}
        for data_id in safe_listdir(system_run_dir):
            data_dir = os.path.join(system_run_dir, data_id)
            if os.path.isdir(data_dir):
                files = [
                    os.path.join(data_dir, f)
                    for f in safe_listdir(data_dir)
                    if f.endswith('.json')
                ]
                if files:
                    runs[data_id] = files
        result[cid] = _build_run_scores(runs)
    return result


def open_store(workspace_path: str) -> CandidateStore | None:
    """Build a CandidateStore for read access.

    Returns None when the workspace or its candidates/ subdirectory is missing,
    so the route layer can answer with a 404 instead of silently creating empty
    directories.
    """
    if not os.path.isdir(workspace_path):
        return None
    if not os.path.isdir(os.path.join(workspace_path, 'candidates')):
        return None
    return LocalCandidateStore(workspace_path, cleanup_unavailable=False)


def candidates_payload(store: CandidateStore) -> list[dict]:
    """Serialize every candidate's meta + summary for the /api/candidates response."""
    payload: list[dict] = []
    for cid in store.get_all_candidate_id_list():
        meta = store.get_meta(cid)
        if meta is None:
            continue
        summary = store.get_summary(cid)
        payload.append({
            'meta': meta.model_dump(mode='json'),
            'summary': (
                summary.model_dump(mode='json')
                if summary is not None
                else {
                    'candidate_id': cid,
                    'score_list': [],
                    'avg_score': 0,
                    'last_evaluated_at': None,
                }
            ),
        })
    return payload


def candidate_detail_payload(store: CandidateStore, candidate_id: str) -> dict | None:
    """Build the /api/candidate/<id> response from the store's path helpers."""
    meta = store.get_meta(candidate_id)
    if meta is None:
        return None

    summary = store.get_summary(candidate_id)

    artifact_files = list_artifact_files(store.artifact_dir(candidate_id))

    changelog_path = store.changelog_path(candidate_id)
    changelog = changelog_path if os.path.isfile(changelog_path) else None

    system_run_dir = store.system_run_dir(candidate_id)
    system_runs: dict[str, list[str]] = {}
    if os.path.isdir(system_run_dir):
        for data_id in safe_listdir(system_run_dir):
            data_dir = os.path.join(system_run_dir, data_id)
            if os.path.isdir(data_dir):
                files = [
                    os.path.join(data_dir, f)
                    for f in safe_listdir(data_dir)
                    if f.endswith('.json')
                ]
                if files:
                    system_runs[data_id] = files

    val_system_run_dir = store.val_system_run_dir(candidate_id)
    val_system_runs: dict[str, list[str]] = {}
    if os.path.isdir(val_system_run_dir):
        for data_id in safe_listdir(val_system_run_dir):
            data_dir = os.path.join(val_system_run_dir, data_id)
            if os.path.isdir(data_dir):
                files = [
                    os.path.join(data_dir, f)
                    for f in safe_listdir(data_dir)
                    if f.endswith('.json')
                ]
                if files:
                    val_system_runs[data_id] = files

    analysis_result_dir = store.analysis_result_dir(candidate_id)
    analysis_traj_dir = store.analysis_trajectory_dir(candidate_id)
    mutation_dir = store.mutation_trajectory_dir(candidate_id)

    analysis_results = (
        [
            os.path.join(analysis_result_dir, f)
            for f in safe_listdir(analysis_result_dir)
            if f.endswith('.json')
        ]
        if os.path.isdir(analysis_result_dir)
        else []
    )
    analysis_trajectories = (
        [
            os.path.join(analysis_traj_dir, f)
            for f in safe_listdir(analysis_traj_dir)
            if f.endswith('.json')
        ]
        if os.path.isdir(analysis_traj_dir)
        else []
    )
    mutation_trajectories = (
        [
            os.path.join(mutation_dir, f)
            for f in safe_listdir(mutation_dir)
            if f.endswith('.json')
        ]
        if os.path.isdir(mutation_dir)
        else []
    )

    return {
        'meta': meta.model_dump(mode='json'),
        'summary': summary.model_dump(mode='json') if summary is not None else None,
        'artifact_files': artifact_files,
        'changelog': changelog,
        'system_runs': system_runs,
        'system_run_scores': _build_run_scores(system_runs),
        'val_system_runs': val_system_runs,
        'val_system_run_scores': _build_run_scores(val_system_runs),
        'proposer_runs': {
            'analysis_results': analysis_results,
            'analysis_trajectories': analysis_trajectories,
            'mutation_trajectories': mutation_trajectories,
        },
    }


def statistics_payload(store: CandidateStore) -> dict | None:
    """Return statistics + iteration records as a JSON-ready dict, or None if not initialized."""
    stats = store.get_statistics()
    if not stats or not stats.root_candidate_id:
        return None
    payload = stats.model_dump(mode='json')
    payload['iteration_record_list'] = [
        r.model_dump(mode='json') for r in store.read_iteration_records()
    ]
    return payload


def statistics_mtime(workspace_path: str) -> int:
    """Return max(mtime(statistics.json), mtime(iteration_records.jsonl)) in seconds.

    Returns 0 when neither file exists. Used by the cheap polling endpoint.
    """
    stats_path = os.path.join(workspace_path, 'logs', 'statistics.json')
    jsonl_path = os.path.join(workspace_path, 'logs', 'iteration_records.jsonl')
    mtime_s = 0
    with contextlib.suppress(FileNotFoundError):
        mtime_s = int(os.path.getmtime(stats_path))
    with contextlib.suppress(FileNotFoundError):
        mtime_s = max(mtime_s, int(os.path.getmtime(jsonl_path)))
    return mtime_s


# File reader for the on-demand viewer.
#
# Cap any single read to keep the UI responsive — anything bigger is almost
# always a debugging artifact (huge trajectory, accidental log dump). The viewer
# truncates and notifies; users can still find the file on disk if they need it.
MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MB


def read_workspace_file(workspace_path: str, target_path: str) -> dict:
    """Read a file from inside the workspace, with safety checks.

    Returns a dict shaped for the /api/file response:
        { 'path', 'rel_path', 'size', 'truncated', 'binary', 'content' }
    Binary or oversized content sets `binary`/`truncated` and may omit `content`.

    Raises:
        FileNotFoundError — path does not exist or is not a regular file.
        PermissionError   — path resolves outside the workspace (path-traversal guard).
    """
    workspace_real = os.path.realpath(workspace_path)
    target_real = os.path.realpath(target_path)

    # Path-traversal guard: refuse anything outside the workspace.
    common = os.path.commonpath([workspace_real, target_real]) if target_real else ''
    if common != workspace_real:
        raise PermissionError(f'Path is outside the workspace: {target_path}')

    if not os.path.isfile(target_real):
        raise FileNotFoundError(target_path)

    size = os.path.getsize(target_real)
    truncated = size > MAX_FILE_BYTES
    read_size = MAX_FILE_BYTES if truncated else size

    with open(target_real, 'rb') as f:
        raw = f.read(read_size)

    binary = b'\x00' in raw
    content: str | None
    if binary:
        content = None
    else:
        try:
            content = raw.decode('utf-8')
        except UnicodeDecodeError:
            try:
                content = raw.decode('latin-1')
            except UnicodeDecodeError:
                binary = True
                content = None

    return {
        'path': target_real,
        'rel_path': os.path.relpath(target_real, workspace_real),
        'size': size,
        'truncated': truncated,
        'binary': binary,
        'content': content,
    }

"""
AntOmniEvo Visualizer API Server.

Flask backend that serves workspace data. Routing / HTTP concerns only;
all workspace reading is delegated to workspace_reader.
"""

import argparse
import contextlib
import os
import signal
import subprocess
import threading

from flask import Flask, jsonify, request
from flask_cors import CORS

from antomnievo_visualizer.workspace_reader import (
    candidate_detail_payload,
    candidates_payload,
    open_store,
    read_workspace_file,
    statistics_mtime,
    statistics_payload,
)

app = Flask(__name__)
CORS(app)

# Workspace root path. Set via --workspace flag or POST /api/config/workspace.
# All endpoints read from this single global root — clients cannot specify a
# workspace per request (so the server never reads outside the configured root).
WORKSPACE_ROOT: str | None = None

# Frontend dev server port. Used by the /api/admin/stop endpoint to also
# tear down the Vite process. Overridable via --frontend-port.
FRONTEND_PORT: int = 5173


def get_workspace_root() -> str:
    """Return the configured workspace root, or raise if unset."""
    if not WORKSPACE_ROOT:
        raise ValueError(
            "Workspace not configured. Start with --workspace, "
            "or POST /api/config/workspace {\"path\": \"...\"}."
        )
    return WORKSPACE_ROOT


@app.route('/api/config/workspace', methods=['GET'])
def get_workspace_config():
    """Return the currently configured workspace root."""
    return jsonify({
        'workspace_root': WORKSPACE_ROOT,
        'exists': bool(WORKSPACE_ROOT and os.path.isdir(WORKSPACE_ROOT)),
    })


@app.route('/api/config/workspace', methods=['POST'])
def set_workspace_config():
    """Set the workspace root.

    Body: {"path": "/absolute/path/to/workspace"}.
    Pass an empty string or null to clear the config.
    """
    global WORKSPACE_ROOT

    data = request.get_json(silent=True) or {}
    path = data.get('path')

    if path in (None, ''):
        WORKSPACE_ROOT = None
        return jsonify({'workspace_root': None, 'exists': False})

    if not isinstance(path, str):
        return jsonify({'error': 'path must be a string'}), 400

    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        return jsonify({'error': f'path must be absolute: {path}'}), 400
    if not os.path.isdir(path):
        return jsonify({'error': f'path does not exist or is not a directory: {path}'}), 400

    WORKSPACE_ROOT = path
    print(f"[config] WORKSPACE_ROOT set to: {path}")
    return jsonify({'workspace_root': WORKSPACE_ROOT, 'exists': True})


@app.route('/api/candidates', methods=['GET'])
def get_current_candidates():
    """List all candidates in the current workspace via CandidateStore."""
    try:
        workspace_path = get_workspace_root()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    store = open_store(workspace_path)
    if store is None:
        return jsonify({'error': f'Workspace not found: {workspace_path}'}), 404

    return jsonify(candidates_payload(store))


@app.route('/api/statistics', methods=['GET'])
def get_current_statistics():
    """Return statistics + iteration records for the current workspace via CandidateStore."""
    try:
        workspace_path = get_workspace_root()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    store = open_store(workspace_path)
    if store is None:
        return jsonify({'error': f'Workspace not found: {workspace_path}'}), 404

    payload = statistics_payload(store)
    if payload is None:
        return jsonify({'error': 'Statistics not found'}), 404
    return jsonify(payload)


@app.route('/api/statistics/mtime', methods=['GET'])
def get_statistics_mtime():
    """Return statistics.json mtime in seconds — cheap polling endpoint.

    Frontend polls this and only re-fetches /api/statistics + /api/candidates
    when the value changes. Returns mtime=0 if the file does not exist.
    """
    try:
        workspace_path = get_workspace_root()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    return jsonify({'mtime': statistics_mtime(workspace_path)})


@app.route('/api/candidate/<candidate_id>', methods=['GET'])
def get_current_candidate_detail(candidate_id: str):
    """Return detail for one candidate via CandidateStore."""
    try:
        workspace_path = get_workspace_root()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    store = open_store(workspace_path)
    if store is None:
        return jsonify({'error': f'Workspace not found: {workspace_path}'}), 404

    detail = candidate_detail_payload(store, candidate_id)
    if detail is None:
        return jsonify({'error': f'Candidate not found: {candidate_id}'}), 404
    return jsonify(detail)


@app.route('/api/batch-scores', methods=['POST'])
def get_batch_scores():
    """Return {candidate_id: {data_id: score}} for a list of candidate IDs."""
    try:
        workspace_path = get_workspace_root()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    store = open_store(workspace_path)
    if store is None:
        return jsonify({'error': f'Workspace not found: {workspace_path}'}), 404

    body = request.get_json(silent=True) or {}
    candidate_ids = body.get('candidate_ids', [])
    if not isinstance(candidate_ids, list):
        return jsonify({'error': 'candidate_ids must be a list'}), 400

    from antomnievo_visualizer.workspace_reader import batch_run_scores
    result = batch_run_scores(store, candidate_ids)
    return jsonify(result)


@app.route('/api/file', methods=['GET'])
def get_file_content():
    """Return raw text content of a file inside the current workspace.

    Query: ?file=<absolute path>. The path must resolve under the workspace root
    or the request is rejected (path-traversal guard). Oversized files return a
    truncated head with `truncated: true`; binary files return no content.
    """
    try:
        workspace_path = get_workspace_root()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    target = request.args.get('file')
    if not target:
        return jsonify({'error': 'Missing ?file= parameter'}), 400

    try:
        payload = read_workspace_file(workspace_path, target)
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except FileNotFoundError:
        return jsonify({'error': f'File not found: {target}'}), 404
    except OSError as e:
        return jsonify({'error': f'Failed to read file: {e}'}), 500

    return jsonify(payload)


@app.route('/api/browse', methods=['GET'])
def browse_directory():
    """List subdirectories of a given path for workspace selection.

    Query: ?path=<absolute directory path>.  Defaults to the user's home
    directory when omitted.  Returns only directories (not files).
    """
    target = request.args.get('path', os.path.expanduser('~'))
    target = os.path.expanduser(target)

    if not os.path.isabs(target):
        return jsonify({'error': 'path must be absolute'}), 400
    if not os.path.isdir(target):
        return jsonify({'error': f'Not a directory: {target}'}), 400

    parent = os.path.dirname(target) if target != '/' else None
    try:
        entries = sorted(
            entry.name
            for entry in os.scandir(target)
            if entry.is_dir() and not entry.name.startswith('.')
        )
    except PermissionError:
        entries = []

    return jsonify({
        'path': target,
        'parent': parent,
        'dirs': entries,
    })


@app.route('/api/open-directory', methods=['POST'])
def open_directory():
    """Open a directory in the system file manager."""
    try:
        workspace_path = get_workspace_root()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    body = request.get_json(silent=True) or {}
    candidate_id = body.get('candidate_id')
    if not candidate_id or not isinstance(candidate_id, str):
        return jsonify({'error': 'candidate_id is required'}), 400

    target = os.path.join(workspace_path, 'candidates', candidate_id)
    target = os.path.realpath(target)
    if not target.startswith(os.path.realpath(workspace_path)):
        return jsonify({'error': 'path traversal rejected'}), 403
    if not os.path.isdir(target):
        return jsonify({'error': f'Directory not found: {target}'}), 404

    import sys
    if sys.platform == 'darwin':
        subprocess.Popen(['open', target])
    elif sys.platform == 'win32':
        subprocess.Popen(['explorer', target])
    else:
        subprocess.Popen(['xdg-open', target])

    return jsonify({'opened': target})


@app.route('/health', methods=['GET'])
def health():
    """Health check."""
    return jsonify({'status': 'ok'})


def _kill_port(port: int) -> list[str]:
    """SIGKILL every process listening on `port`; return the killed PIDs."""
    try:
        result = subprocess.run(
            ['lsof', '-ti', str(port)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []
    killed: list[str] = []
    for pid in result.stdout.strip().split('\n'):
        if not pid:
            continue
        try:
            os.kill(int(pid), signal.SIGKILL)
            killed.append(pid)
        except (ProcessLookupError, ValueError):
            pass
    return killed


@app.route('/api/admin/stop', methods=['POST'])
def admin_stop():
    """Stop the frontend dev server and then this API server itself.

    The response is returned BEFORE this process exits so the caller still
    sees the result. A background timer triggers SIGTERM on this PID a short
    moment later.
    """
    killed_frontend = _kill_port(FRONTEND_PORT)
    api_pid = os.getpid()

    def _self_terminate() -> None:
        with contextlib.suppress(ProcessLookupError):
            os.kill(api_pid, signal.SIGTERM)

    threading.Timer(0.3, _self_terminate).start()

    return jsonify({
        'stopping': True,
        'api_pid': api_pid,
        'frontend_port': FRONTEND_PORT,
        'frontend_killed_pids': killed_frontend,
    })


def main():
    global WORKSPACE_ROOT, FRONTEND_PORT

    parser = argparse.ArgumentParser(description='AntOmniEvo Visualizer API Server')
    parser.add_argument('--api-port', type=int, default=3001,
                        help='Backend (this API server) port [default: 3001]')
    parser.add_argument('--frontend-port', type=int, default=FRONTEND_PORT,
                        help='Frontend dev server port (used by /api/admin/stop) [default: 5173]')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--workspace', type=str, default=None,
                        help='Workspace root path')
    args = parser.parse_args()

    if args.workspace:
        workspace = os.path.expanduser(args.workspace)
        if not os.path.isabs(workspace):
            workspace = os.path.abspath(workspace)
        if not os.path.isdir(workspace):
            parser.error(f'--workspace path does not exist or is not a directory: {workspace}')
        WORKSPACE_ROOT = workspace
    FRONTEND_PORT = args.frontend_port

    print(f"Backend  (API): http://{args.host}:{args.api_port}")
    print(f"Frontend (dev): port {FRONTEND_PORT}  (killed by /api/admin/stop)")
    print(f"Workspace root: {WORKSPACE_ROOT or '(not set — provide via POST /api/config/workspace)'}")
    app.run(host=args.host, port=args.api_port, debug=False)


if __name__ == '__main__':
    main()

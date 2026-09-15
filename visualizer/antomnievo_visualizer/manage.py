#!/usr/bin/env python3
"""
AntOmniEvo Visualizer launcher script.

One-shot start/stop for the frontend and backend services.
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Project root = visualizer/ (one level up from this package).
PROJECT_ROOT = Path(__file__).parent.parent
FRONTEND_DIR = PROJECT_ROOT

# Default ports. Override via --api-port / --frontend-port on the CLI.
API_PORT = 3001
FRONTEND_PORT = 5173

# Tracked subprocesses.
processes = {}


def kill_port(port: int):
    """Kill any process listening on the given port."""
    try:
        # Use lsof to find the PID(s) bound to the port.
        result = subprocess.run(
            ['lsof', '-ti', f':{port}'],
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                try:
                    os.kill(int(pid), signal.SIGKILL)
                    print(f"✓ Killed process on port {port} (PID: {pid})")
                except ProcessLookupError:
                    pass
            return True
    except Exception as e:
        print(f"Warning: Failed to kill process on port {port}: {e}")
    return False


def assert_port_free(port: int, force: bool = False):
    """Ensure the port is free. With force=True, kill any occupier instead of raising."""
    result = subprocess.run(
        ['lsof', '-ti', f':{port}'],
        capture_output=True,
        text=True
    )
    if not result.stdout.strip():
        return
    pids = result.stdout.strip().split('\n')
    if force:
        print(f"⚠ Port {port} in use (PID: {', '.join(pids)}); --force killing.")
        kill_port(port)
        time.sleep(0.5)
        return
    raise RuntimeError(
        f"Port {port} is already in use (PID: {', '.join(pids)}). "
        f"Run 'python manage.py stop' to free it, or pass --force."
    )


def start_api(force: bool = False) -> subprocess.Popen:
    """Start the API server."""
    print(f"Starting backend API server on port {API_PORT}...")

    # Fail fast if the port is taken (unless --force).
    assert_port_free(API_PORT, force=force)

    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'

    proc = subprocess.Popen(
        [
            sys.executable, '-m', 'antomnievo_visualizer.server',
            '--api-port', str(API_PORT),
            '--frontend-port', str(FRONTEND_PORT),
        ],
        env=env,
    )
    processes['api'] = proc
    print(f"✓ Backend API server started (PID: {proc.pid})")
    return proc


def start_frontend(force: bool = False) -> subprocess.Popen:
    """Start the frontend dev server."""
    print(f"Starting frontend dev server on port {FRONTEND_PORT}...")

    # Fail fast if the port is taken (unless --force).
    assert_port_free(FRONTEND_PORT, force=force)

    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'

    proc = subprocess.Popen(
        ['npm', 'run', 'dev', '--', '--host', '0.0.0.0', '--port', str(FRONTEND_PORT)],
        env=env,
        cwd=str(FRONTEND_DIR),
    )
    processes['frontend'] = proc
    print(f"✓ Frontend dev server started (PID: {proc.pid})")
    return proc


def stop_all():
    """Stop all services."""
    print("\n🛑 Stopping all services...")

    # Free both ports.
    kill_port(API_PORT)
    kill_port(FRONTEND_PORT)

    time.sleep(1)
    print("✓ All services stopped")


def status():
    """Show service status."""
    print("\n📊 Service Status:")
    print(f"  Backend  (API):  http://localhost:{API_PORT}")
    print(f"  Frontend (dev):  http://localhost:{FRONTEND_PORT}")

    for name, port in [('Backend ', API_PORT), ('Frontend', FRONTEND_PORT)]:
        result = subprocess.run(
            ['lsof', '-ti', f':{port}'],
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            print(f"  {name}:  ✅ Running")
        else:
            print(f"  {name}:  ❌ Stopped")


def main():
    global API_PORT, FRONTEND_PORT
    parser = argparse.ArgumentParser(description='AntOmniEvo Visualizer Manager')
    parser.add_argument('action', choices=['start', 'stop', 'restart', 'status'],
                        help='Action to perform')
    parser.add_argument('--api-only', action='store_true',
                        help='Start only the backend API server')
    parser.add_argument('--frontend-only', action='store_true',
                        help='Start only the frontend dev server')
    parser.add_argument('--api-port', type=int, default=API_PORT,
                        help=f'Backend API server port [default: {API_PORT}]')
    parser.add_argument('--frontend-port', type=int, default=FRONTEND_PORT,
                        help=f'Frontend dev server port [default: {FRONTEND_PORT}]')
    parser.add_argument('--force', action='store_true',
                        help='If a target port is occupied, kill the occupier instead of failing')

    args = parser.parse_args()

    API_PORT = args.api_port
    FRONTEND_PORT = args.frontend_port

    if args.action == 'start':
        print("🚀 Starting AntOmniEvo Visualizer...")

        if not args.frontend_only:
            start_api(force=args.force)

        if not args.api_only:
            start_frontend(force=args.force)

        print("\n✅ All services started!")
        print(f"   Backend  (API):  http://localhost:{API_PORT}")
        print(f"   Frontend (dev):  http://localhost:{FRONTEND_PORT}")
        print("\nPress Ctrl+C (or POST /api/admin/stop) to stop all services")

        # Wait until either a subprocess exits or the user hits Ctrl+C.
        try:
            while True:
                time.sleep(1)
                dead = [name for name, p in processes.items() if p.poll() is not None]
                if dead:
                    print(f"\nSubprocess(es) exited: {', '.join(dead)}. Tearing down.")
                    stop_all()
                    break
        except KeyboardInterrupt:
            stop_all()

    elif args.action == 'stop':
        stop_all()

    elif args.action == 'restart':
        stop_all()
        time.sleep(2)
        print("\n🚀 Restarting...")
        if not args.frontend_only:
            start_api(force=args.force)
        if not args.api_only:
            start_frontend(force=args.force)
        print("\n✅ Services restarted!")

    elif args.action == 'status':
        status()


if __name__ == '__main__':
    main()

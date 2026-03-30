import subprocess
import sys
import os
import time


def kill_port_8000():
    print("Checking port 8000...", flush=True)
    try:
        result = subprocess.run(
            'netstat -ano | findstr :8000',
            shell=True, capture_output=True, text=True
        )
        pids_killed = set()
        for line in result.stdout.strip().split('\n'):
            parts = line.strip().split()
            if len(parts) >= 5 and ':8000' in parts[1]:
                pid = parts[-1]
                if pid not in ('0', '') and pid not in pids_killed:
                    subprocess.run(
                        f'taskkill /PID {pid} /F',
                        shell=True, capture_output=True
                    )
                    pids_killed.add(pid)
                    print(f"  Killed PID {pid}", flush=True)
        if pids_killed:
            time.sleep(2)
            print("Port 8000 is free.", flush=True)
        else:
            print("Port 8000 was already free.", flush=True)
    except Exception as e:
        print(f"Port cleanup error: {e}", flush=True)


if __name__ == "__main__":
    kill_port_8000()
    time.sleep(1)
    cmd = [
        sys.executable, "-m", "uvicorn",
        "api.server:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        # Intentionally no --reload to avoid subprocess output capture issues on Windows.
    ]
    print(f"Starting: {' '.join(cmd)}", flush=True)
    subprocess.call(cmd)


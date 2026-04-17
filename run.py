import subprocess
import sys
import os
import signal
import time

# Color codes for terminal output
class Colors:
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    RESET = '\033[0m'


def print_status(message, color=Colors.BLUE):
    print(f"{color}{message}{Colors.RESET}")


def run_servers():
    """Run both the Discord bot and web server."""
    processes = []

    try:
        # Start web server
        print_status("Starting Flask web server...", Colors.BLUE)
        web_process = subprocess.Popen(
            [sys.executable, "web.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        processes.append(("Web Server", web_process))
        time.sleep(2)

        # Start Discord bot
        print_status("Starting Discord bot...", Colors.BLUE)
        bot_process = subprocess.Popen(
            [sys.executable, "main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        processes.append(("Discord Bot", bot_process))

        print_status("\n✅ Both servers are running!", Colors.GREEN)
        print_status("  - Web Server: http://localhost:5000", Colors.YELLOW)
        print_status("  - Discord Bot: Connected", Colors.YELLOW)
        print_status("\nPress Ctrl+C to stop both servers\n", Colors.YELLOW)

        # Wait for processes
        while True:
            for name, process in processes:
                if process.poll() is not None:
                    print_status(f"\n❌ {name} has stopped!", Colors.RED)
                    return
            time.sleep(1)

    except KeyboardInterrupt:
        print_status("\n\nShutting down servers...", Colors.YELLOW)
        for name, process in processes:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        print_status("✅ All servers stopped.", Colors.GREEN)


if __name__ == "__main__":
    run_servers()
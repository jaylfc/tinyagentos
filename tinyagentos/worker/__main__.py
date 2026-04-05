"""TinyAgentOS Worker — connects this machine to a TinyAgentOS controller."""
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="TinyAgentOS Worker")
    parser.add_argument("controller", help="Controller URL (e.g. http://192.168.1.100:8888)")
    parser.add_argument("--name", help="Worker name (default: hostname)")
    parser.add_argument("--headless", action="store_true", help="Run without system tray (server mode)")
    args = parser.parse_args()

    if args.headless:
        import asyncio
        from tinyagentos.worker.agent import WorkerAgent
        agent = WorkerAgent(args.controller, args.name)
        try:
            asyncio.run(agent.run())
        except KeyboardInterrupt:
            agent.stop()
    else:
        from tinyagentos.worker.tray import run_tray
        run_tray(args.controller, args.name)


if __name__ == "__main__":
    main()

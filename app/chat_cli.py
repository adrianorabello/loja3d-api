import argparse
import asyncio
from pathlib import Path

from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser(description="Run the isolated, opt-in support chat.")
    parser.add_argument("service", choices=["api", "worker"])
    parser.add_argument("--env-file", default=".env.chat")
    args = parser.parse_args()
    if not Path(args.env_file).is_file():
        parser.error("Missing env file. Copy .env.chat.example to .env.chat first.")
    load_dotenv(args.env_file, override=True)
    if args.service == "api":
        import uvicorn
        uvicorn.run("main:app", host="127.0.0.1", port=8001,
                    ws_max_size=1024, ws_max_queue=8, limit_concurrency=64, access_log=False)
    else:
        from app.workers.chat import main as worker
        asyncio.run(worker())


if __name__ == "__main__":
    main()

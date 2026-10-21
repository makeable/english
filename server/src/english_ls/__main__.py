import argparse
import logging
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="english-ls", description="English prose language server")
    parser.add_argument("--stdio", action="store_true", help="talk LSP over stdin/stdout (default)")
    parser.add_argument("--tcp", action="store_true", help="listen on TCP instead of stdio")
    parser.add_argument("--port", type=int, default=2087)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    # stdout carries the LSP protocol, so logs go to stderr.
    logging.basicConfig(stream=sys.stderr, level=args.log_level.upper())

    from .server import server

    if args.tcp:
        server.start_tcp("127.0.0.1", args.port)
    else:
        server.start_io()


if __name__ == "__main__":
    main()

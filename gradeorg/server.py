"""Arranque do servidor local e abertura do navegador."""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser

from .app import create_app

DEFAULT_PORT = 8756
HOST = "127.0.0.1"


def find_port(preferred: int = DEFAULT_PORT, attempts: int = 40) -> int:
    """Primeira porta livre a partir da preferida."""
    for offset in range(attempts):
        port = preferred + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((HOST, port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((HOST, 0))
        return probe.getsockname()[1]


def _open_browser(url: str, delay: float = 1.0) -> None:
    def run():
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:                                  # noqa: BLE001
            pass

    threading.Thread(target=run, daemon=True).start()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="organizador-de-notas",
        description="Junta pautas em PDF, Excel ou texto numa listagem única de notas.",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"porta a usar (por omissão {DEFAULT_PORT})")
    parser.add_argument("--no-browser", action="store_true",
                        help="não abrir o navegador automaticamente")
    parser.add_argument("--debug", action="store_true", help="modo de desenvolvimento")
    args = parser.parse_args(argv)

    port = find_port(args.port)
    url = f"http://{HOST}:{port}/"

    print("=" * 62)
    print("  Organizador de Notas")
    print("=" * 62)
    print(f"  A aplicação está em:  {url}")
    print("  Os ficheiros nunca saem deste computador.")
    print("  Para fechar: Ctrl+C nesta janela.")
    print("=" * 62, flush=True)

    if not args.no_browser:
        _open_browser(url)

    app = create_app()
    try:
        app.run(host=HOST, port=port, debug=args.debug, use_reloader=False, threaded=True)
    except KeyboardInterrupt:
        print("\nServidor terminado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

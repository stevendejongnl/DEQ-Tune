#!/usr/bin/env python3
"""Terminates TLS for the web frontend, and nothing else on the Pi.

Chrome will not offer a real "Install app" prompt over plain HTTP on a LAN
address. Only `localhost` or HTTPS counts as a secure context. Without one,
the browser falls back to a plain shortcut with no service worker, no
offline cache, no standalone window. The backend itself stays on plain
HTTP on 8420. The Android Auto app, the BLE bridge, and the session
recorder all reach it there (see AppSettings.kt, deq_ble_bridge.py,
deq-session-record.sh). It makes no sense to ask any of them to trust a
self-signed cert for no benefit. The access point's own WPA2 key already
gates the amplifier, not TLS.

So this is a second listener, TLS-only, forwarding decrypted bytes
straight to the backend's existing HTTP port. It holds no state of its
own and never touches the gadget, the DEQ link, or the backend process.
If this crashes, the car app and the rest of the system keep working.
Only the browser loses its padlock.

Pure asyncio + the standard `ssl` module, deliberately: the Pi gets this
one extra listener, not an extra package (nginx, Caddy) with its own
config format and update cadence to track.

Usage:
    deq_tls_proxy.py <listen_port> <backend_port> <certfile> <keyfile>
"""

from __future__ import annotations

import asyncio
import ssl
import sys

# 64 KiB matches the chunk size the rest of this project already uses for
# the USB/BLE transports (see deq_ble_bridge.py). This proxy has no
# protocol framing to respect, so any size that keeps memory bounded works.
CHUNK_SIZE = 65536


async def pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Copies one direction of one connection until the source closes."""
    try:
        while True:
            chunk = await reader.read(CHUNK_SIZE)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        # The browser closed the tab, or the backend restarted mid-request.
        # Neither is this proxy's problem to report. The other side of the
        # pair gets the same treatment, and both ends close below.
        pass
    finally:
        writer.close()


def make_handler(backend_port: int):
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            backend_reader, backend_writer = await asyncio.open_connection(
                "127.0.0.1", backend_port
            )
        except OSError:
            # The backend is down (mid-deploy, mid-restart). Refusing the
            # browser's connection is the honest answer. Nothing here could
            # serve the request instead.
            writer.close()
            return
        await asyncio.gather(
            pump(reader, backend_writer),
            pump(backend_reader, writer),
        )

    return handle


async def main(listen_port: int, backend_port: int, certfile: str, keyfile: str) -> None:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile, keyfile)

    server = await asyncio.start_server(
        make_handler(backend_port), host="0.0.0.0", port=listen_port, ssl=context
    )
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(__doc__)
        sys.exit(2)
    asyncio.run(main(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4]))

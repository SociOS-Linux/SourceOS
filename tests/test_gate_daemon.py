import asyncio
import json
import tempfile
import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sourceos_gate.daemon import DaemonConfig, serve


async def _send(sock_path: str, msg: dict) -> dict:
    reader, writer = await asyncio.open_unix_connection(sock_path)
    writer.write((json.dumps(msg) + "\n").encode("utf-8"))
    await writer.drain()
    line = await reader.readline()
    writer.close()
    await writer.wait_closed()
    return json.loads(line.decode("utf-8"))


class GateDaemonTests(unittest.TestCase):
    def test_health_and_snapshot(self):
        async def run():
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                sock = root / "gate.sock"

                cfg = DaemonConfig(socket_path=sock, store_root=root)
                task = asyncio.create_task(serve(cfg))

                # wait for socket
                for _ in range(50):
                    if sock.exists():
                        break
                    await asyncio.sleep(0.02)

                resp = await _send(str(sock), {"id": "1", "method": "health", "params": {}})
                self.assertTrue(resp.get("ok"))

                snap = await _send(str(sock), {"id": "2", "method": "snapshot", "params": {}})
                self.assertTrue(snap.get("ok"))
                self.assertIn("active", snap.get("result", {}))

                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()

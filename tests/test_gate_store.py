import tempfile
import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sourceos_gate.store import GateStore
from sourceos_gate.errors import ReplayError, ExpiredGrantError


class GateStoreTests(unittest.TestCase):
    def test_install_and_list_active(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = GateStore(root)
            store.init()

            exp = 9999999999
            store.install_grant("tok", "n1", exp, ["10.0.0.1/32"], [443], "tcp")
            store.install_grant("tok2", "n2", exp, ["10.0.0.2/32"], [53], "udp")

            active = store.list_active()
            self.assertEqual(len(active), 2)

            addrs, tcp_ports, udp_ports = store.compute_active_sets()
            self.assertIn("10.0.0.1", addrs)
            self.assertIn("10.0.0.2", addrs)
            self.assertIn("443", tcp_ports)
            self.assertIn("53", udp_ports)

    def test_replay_detection(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = GateStore(root)
            exp = 9999999999
            store.install_grant("tok", "n1", exp, ["10.0.0.1/32"], [443], "tcp")
            with self.assertRaises(ReplayError):
                store.install_grant("tok", "n1", exp, ["10.0.0.1/32"], [443], "tcp")

    def test_expired_grant_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = GateStore(root)
            with self.assertRaises(ExpiredGrantError):
                store.install_grant("tok", "n1", 1, ["10.0.0.1/32"], [443], "tcp")


if __name__ == "__main__":
    unittest.main()

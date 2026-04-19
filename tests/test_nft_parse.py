import json
import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sourceos_gate import nft


class NftParseTests(unittest.TestCase):
    def _load(self, name: str) -> dict:
        p = REPO_ROOT / "tools" / "fixtures" / name
        return json.loads(p.read_text(encoding="utf-8"))

    def test_parse_v4(self):
        obj = self._load("nft_set_frontier_allow_v4.json")
        elems = nft.parse_nft_set_elements_json(obj)
        self.assertEqual(sorted(elems), ["10.0.0.1", "10.0.0.2"])

    def test_parse_ports_string(self):
        obj = self._load("nft_set_frontier_allow_tcp_ports.json")
        elems = nft.parse_nft_set_elements_json(obj)
        self.assertEqual(sorted(elems), ["443", "8443"])

    def test_parse_ports_int(self):
        obj = self._load("nft_set_frontier_allow_tcp_ports_int.json")
        elems = nft.parse_nft_set_elements_json(obj)
        self.assertEqual(sorted(elems), ["11", "17"])


if __name__ == "__main__":
    unittest.main()

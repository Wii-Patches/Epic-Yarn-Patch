import sys
from pathlib import Path
import struct
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import patcher

class DiscIdentityTests(unittest.TestCase):
    def test_iso_and_wbfs_mod_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / 'mod.img'
            for offset in (0, 0x200):
                for identity in patcher.REGIONS:
                    header = bytearray(offset + 0x20)
                    header[offset:offset + 6] = (identity[:4] + '99').encode()
                    struct.pack_into('>I', header, offset + 0x18, patcher.WII_MAGIC)
                    image.write_bytes(header)
                    self.assertEqual(patcher.identify(str(image)), identity)
            header[offset:offset + 6] = b'ZZZZ99'
            image.write_bytes(header)
            with self.assertRaises(RuntimeError):
                patcher.identify(str(image))

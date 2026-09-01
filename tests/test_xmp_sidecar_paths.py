from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ndex_common.rating import read_jpg_rating
from ndex_common.xmp import sidecar_path_for, sidecar_paths_for_read, write_xmp_sidecar


class XmpSidecarPathTests(unittest.TestCase):
    def test_raw_uses_stem_xmp_and_jpg_keeps_extension(self) -> None:
        self.assertEqual(sidecar_path_for(Path("IMG_0001.CR3")), Path("IMG_0001.xmp"))
        self.assertEqual(sidecar_path_for(Path("IMG_0001.JPG")), Path("IMG_0001.JPG.xmp"))
        self.assertEqual(sidecar_path_for(Path("IMG_0001.jpeg")), Path("IMG_0001.jpeg.xmp"))

    def test_paired_jpg_and_raw_do_not_share_sidecar_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "IMG_0001.CR3"
            jpg = root / "IMG_0001.JPG"
            raw.write_bytes(b"raw")
            jpg.write_bytes(b"jpg")

            raw_xmp = write_xmp_sidecar(raw, rating=5, label="RAW")
            jpg_xmp = write_xmp_sidecar(jpg, rating=2, label="JPG")

            self.assertEqual(raw_xmp, root / "IMG_0001.xmp")
            self.assertEqual(jpg_xmp, root / "IMG_0001.JPG.xmp")
            self.assertTrue(raw_xmp.exists())
            self.assertTrue(jpg_xmp.exists())
            self.assertIn('xmp:Rating="5"', raw_xmp.read_text(encoding="utf-8"))
            self.assertIn('xmp:Rating="2"', jpg_xmp.read_text(encoding="utf-8"))

    def test_rating_reads_canonical_and_legacy_jpg_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jpg = root / "IMG_0007.JPG"
            jpg.write_bytes(b"jpg")

            legacy = root / "IMG_0007.xmp"
            write_xmp_sidecar(jpg, rating=4)
            # Simulate older NDEX writing stem.xmp for JPG by keeping a legacy file.
            legacy.write_text(
                '<?xml version="1.0"?>\n'
                '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
                '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
                '<rdf:Description xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmp:Rating="1"/>'
                "</rdf:RDF></x:xmpmeta>",
                encoding="utf-8",
            )

            # Canonical JPG.xmp wins when both exist.
            self.assertEqual(read_jpg_rating(jpg), 4)
            self.assertEqual(
                sidecar_paths_for_read(jpg),
                [root / "IMG_0007.JPG.xmp", root / "IMG_0007.xmp"],
            )

            (root / "IMG_0007.JPG.xmp").unlink()
            self.assertEqual(read_jpg_rating(jpg), 1)


if __name__ == "__main__":
    unittest.main()

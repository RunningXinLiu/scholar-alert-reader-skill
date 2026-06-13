import json
import tempfile
import unittest
from pathlib import Path

from scholar_alert_reader.obsidian_graph import export_obsidian_graph


class ObsidianGraphTests(unittest.TestCase):
    def test_graph_export_writes_private_wikilink_notes_and_preserves_user_files(self) -> None:
        records = [
            {
                "paper_id": "p1",
                "title": "Surface wave tomography with neural operators",
                "year": 2026,
                "venue": "Geophysical Journal International",
                "doi": "10.1234/example",
                "url": "https://example.test/p1",
                "source_types": ["zotero", "scholar_alert"],
                "zotero_collections": ["Papers/Surface Wave"],
                "tags": ["tomography", "ai"],
                "matched_terms": ["surface wave tomography", "user:noise", "similar:old paper"],
                "abstract": "A useful abstract.",
                "tier": "Must read",
                "score": 17,
                "pdf_paths": ["/tmp/paper.pdf"],
            },
            {
                "paper_id": "p2",
                "title": "Receiver function imaging",
                "year": 2024,
                "venue": "Seismological Research Letters",
                "source_types": ["zotero"],
                "zotero_collections": ["Papers/Receiver Function"],
                "tags": ["receiver-function"],
                "abstract": "Another abstract.",
                "tier": "Skim",
                "score": 4,
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            export_dir = Path(tmp) / "vault" / "01_Literatures" / "20_Paper_Universe_Graph"
            user_file = export_dir / "01_Papers" / "my handwritten note.md"
            user_file.parent.mkdir(parents=True)
            user_file.write_text("# Keep me\n", encoding="utf-8")

            result = export_obsidian_graph(records, export_dir)

            self.assertEqual(result.paper_notes, 2)
            self.assertEqual(result.collection_notes, 2)
            self.assertEqual(result.topic_notes, 4)
            self.assertTrue(result.index.exists())
            self.assertTrue(user_file.exists())

            paper_notes = sorted((export_dir / "01_Papers").glob("Paper - *.md"))
            self.assertEqual(len(paper_notes), 2)
            paper_text = next(path for path in paper_notes if "[p1]" in path.name).read_text(encoding="utf-8")
            self.assertIn("source_tool: scholar-alert-reader", paper_text)
            self.assertIn("obsidian_import: paper_universe_graph", paper_text)
            self.assertIn("[[Collection - Papers Surface Wave", paper_text)
            self.assertIn("[[Topic - tomography", paper_text)
            self.assertIn("[[Venue - Geophysical Journal International", paper_text)

            manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
            self.assertEqual(manifest["marker"], "scholar-alert-reader:obsidian-graph-generated")
            self.assertTrue(manifest["files"])

            # Rerun pruning removes previous generated files but preserves user files.
            export_obsidian_graph(records[:1], export_dir)
            self.assertTrue(user_file.exists())
            self.assertEqual(len(sorted((export_dir / "01_Papers").glob("Paper - *.md"))), 1)

    def test_research_graph_uses_curated_concepts_not_collection_nodes(self) -> None:
        records = [
            {
                "paper_id": "p1",
                "title": "Surface wave tomography with neural operators",
                "abstract": "A method for surface wave inversion with neural operators.",
                "year": 2026,
                "venue": "Geophysical Journal International",
                "source_types": ["zotero"],
                "zotero_collections": ["Papers/Natural_earthquake_papers/surfacewave details"],
                "tags": ["tomography"],
                "tier": "Must read",
                "score": 17,
            },
            {
                "paper_id": "p2",
                "title": "Unrelated paper",
                "abstract": "No graph concept appears here.",
                "source_types": ["zotero"],
                "zotero_collections": ["Papers/Newly downloaded"],
                "tier": "Archive",
                "score": 0,
            },
        ]
        taxonomy = {
            "concepts": [
                {
                    "id": "surface-wave-tomography",
                    "name": "Surface Wave Tomography",
                    "type": "method",
                    "aliases": ["surface wave inversion"],
                    "terms": ["surface wave tomography", "surface wave inversion"],
                    "collections": ["surfacewave details"],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            export_dir = Path(tmp) / "21_Research_Knowledge_Graph"
            result = export_obsidian_graph(records, export_dir, graph_mode="research", taxonomy=taxonomy)

            self.assertEqual(result.graph_mode, "research")
            self.assertEqual(result.paper_notes, 1)
            self.assertEqual(result.concept_notes, 1)
            self.assertFalse((export_dir / "02_Collections").exists())
            self.assertFalse((export_dir / "04_Venues").exists())

            paper_text = next((export_dir / "01_Papers").glob("Paper - *.md")).read_text(encoding="utf-8")
            self.assertIn("obsidian_import: research_knowledge_graph", paper_text)
            self.assertIn("zotero_collections_raw:", paper_text)
            self.assertIn("Papers/Natural_earthquake_papers/surfacewave details", paper_text)
            self.assertIn("[[Concept - Surface Wave Tomography", paper_text)
            self.assertNotIn("[[Collection -", paper_text)
            self.assertNotIn("[[Venue -", paper_text)

            index = (export_dir / "00_Index" / "Research Knowledge Graph.md").read_text(encoding="utf-8")
            self.assertIn("[[Concept - Surface Wave Tomography", index)


if __name__ == "__main__":
    unittest.main()

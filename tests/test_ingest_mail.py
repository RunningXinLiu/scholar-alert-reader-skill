from __future__ import annotations

import mailbox
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path

from scholar_alert_reader import core
from scholar_alert_reader.ingest import mail


class IngestMailTests(unittest.TestCase):
    def test_parse_mbox_sample_extracts_scholar_entries(self) -> None:
        mbox_path = (
            Path(__file__).resolve().parents[1]
            / "scholar_alert_reader"
            / "resources"
            / "examples"
            / "sample_scholar_alerts.mbox.sample"
        )
        papers, counts = mail.parse_mbox(
            mbox_path,
            since_days=None,
            paper_factory=lambda **kwargs: core.Paper(**kwargs),
        )

        self.assertEqual(counts["messages"], 1)
        self.assertEqual(counts["scholar_messages"], 1)
        self.assertEqual(counts["entries"], 2)
        self.assertEqual(len(papers), 2)
        titles = sorted(paper.title for paper in papers)
        self.assertEqual(
            titles,
            [
                "Ambient noise tomography of plateau crustal structure",
                "Receiver function constraints on lithospheric discontinuities",
            ],
        )

    def test_parse_mbox_deduplicates_entries_with_same_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mbox_path = Path(tmp) / "dupe.mbox"
            mbox = mailbox.mbox(mbox_path)
            try:
                message = self._make_message("Shared paper title", "shared-paper")
                duplicate = self._make_message("Shared paper title", "shared-paper")
                unique = self._make_message("Another paper", "another")
                mbox.add(message)
                mbox.add(duplicate)
                mbox.add(unique)
            finally:
                mbox.close()

            papers, counts = mail.parse_mbox(
                mbox_path,
                paper_factory=lambda **kwargs: core.Paper(**kwargs),
            )

            self.assertEqual(counts["messages"], 3)
            self.assertEqual(counts["scholar_messages"], 3)
            self.assertEqual(counts["entries"], 3)
            self.assertEqual(len(papers), 2)

            papers_by_title = {paper.title: paper for paper in papers}
            shared = papers_by_title["Shared paper title"]
            self.assertEqual(shared.occurrences, 2)
            self.assertEqual(len(shared.alerts), 1)

    def test_parse_alert_name_sanitization(self) -> None:
        self.assertEqual(mail.parse_alert_name("Google Scholar Alert: ambient noise - new articles"), "ambient noise")
        self.assertEqual(mail.parse_alert_name("ambient noise - new related research"), "ambient noise")

    @staticmethod
    def _make_message(title: str, slug: str) -> EmailMessage:
        body = f"""
        <html>
          <body>
            <h3><a href="https://scholar.google.com/scholar_url?url=https%3A%2F%2Fexample.org%2F{slug}" class="gse_alrt_title">{title}</a></h3>
            <div style="color:#006621">Example Author - Demo Journal, 2026</div>
            <div class="gse_alrt_sni">Synthetic snippet for {slug}</div>
          </body>
        </html>
        """.strip()
        msg = EmailMessage()
        msg["From"] = "Google Scholar Alerts <scholaralerts-noreply@google.com>"
        msg["To"] = "researcher@example.com"
        msg["Subject"] = f"Google Scholar Alert: duplicate test - new articles"
        msg["Date"] = "Wed, 27 May 2026 09:00:00 +0000"
        msg.set_content(body, subtype="html")
        return msg


if __name__ == "__main__":
    unittest.main()

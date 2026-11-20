import unittest

import main


class SelectionTests(unittest.TestCase):
    def test_selection_varies_clip_lengths_when_candidates_allow(self):
        candidates = [
            (0.95, 10, 20),
            (0.93, 50, 30),
            (0.92, 100, 45),
            (0.90, 150, 60),
        ]
        chosen = main.select_diverse_candidates(candidates, 4, 240)
        lengths = [end - start for start, end, _ in chosen]
        self.assertEqual(len(chosen), 4)
        self.assertEqual(set(lengths), {20, 30, 45, 60})

    def test_fallback_selection_varies_durations_and_spreads_clips(self):
        chosen = main.build_fallback_ranges(240, 4, "test-video")
        lengths = {int(item["end_time"] - item["start_time"]) for item in chosen}
        self.assertEqual(len(chosen), 4)
        self.assertEqual(lengths, {20, 30, 45, 60})
        for previous, current in zip(chosen, chosen[1:]):
            self.assertLessEqual(previous["end_time"], current["start_time"])

    def test_selection_does_not_overlap(self):
        candidates = [(1.0, 10, 30), (0.99, 20, 30), (0.90, 80, 20), (0.85, 110, 20)]
        chosen = main.select_diverse_candidates(candidates, 3, 140)
        for previous, current in zip(chosen, chosen[1:]):
            self.assertLessEqual(previous[1], current[0])

    def test_selection_respects_previously_used_ranges(self):
        candidates = [(1.0, 10, 30), (0.9, 70, 30)]
        chosen = main.select_diverse_candidates(candidates, 2, 140, exclude_ranges=[[0, 50]])
        self.assertEqual(len(chosen), 1)
        self.assertEqual(chosen[0][0], 70)

    def test_url_validation_allows_only_supported_https_hosts(self):
        self.assertTrue(main.valid_source_url("https://kick.com/example/videos/123"))
        self.assertTrue(main.valid_source_url("https://youtu.be/abcdefghijk"))
        self.assertFalse(main.valid_source_url("http://kick.com/example"))
        self.assertFalse(main.valid_source_url("https://example.com/video"))
        self.assertFalse(main.valid_source_url("https://user:pass@kick.com/video"))

    def test_studio_ui_has_responsive_and_accessible_controls(self):
        self.assertIn('aria-live="polite"', main.HTML)
        self.assertIn("prefers-reduced-motion", main.HTML)
        self.assertIn(".clips-grid", main.HTML)
        self.assertIn('data-nav="history"', main.HTML)

    def test_job_state_dict_writes_atomic_history_snapshot(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "jobs-state.json"
            with (
                patch.object(main, "STATE_FILE", state_file),
                patch.object(main, "JOBS", main.PersistentStateDict()),
                patch.object(main, "JOB_CREATED_AT", main.PersistentStateDict(force_writes=True)),
            ):
                main.JOBS["a" * 32] = {"status": "done", "clips": []}
                main.JOB_CREATED_AT["a" * 32] = 123.0
                saved = json.loads(state_file.read_text(encoding="utf-8"))
                self.assertEqual(saved["jobs"]["a" * 32]["status"], "done")
                self.assertEqual(saved["created_at"]["a" * 32], 123.0)

    def test_restart_recovery_keeps_completed_clip_files(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        job_id = "b" * 32
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            job_folder = base / job_id
            job_folder.mkdir()
            (job_folder / "clip_01.mp4").write_bytes(b"test-video")
            state_file = base / "jobs-state.json"
            state_file.write_text(json.dumps({
                "version": 1,
                "jobs": {job_id: {"status": "processing", "clips": [
                    {"name": "Clip 1", "url": "/download/%s/clip_01.mp4" % job_id}
                ]}},
                "created_at": {job_id: 123.0}
            }), encoding="utf-8")
            with (
                patch.object(main, "BASE", base),
                patch.object(main, "STATE_FILE", state_file),
                patch.object(main, "JOBS", main.PersistentStateDict()),
                patch.object(main, "JOB_CREATED_AT", main.PersistentStateDict(force_writes=True)),
            ):
                main.restore_state()
                self.assertEqual(main.JOBS[job_id]["status"], "partial")
                self.assertEqual(len(main.JOBS[job_id]["clips"]), 1)
                self.assertTrue((job_folder / "clip_01.mp4").is_file())

    def test_job_archive_contains_only_registered_existing_clips(self):
        import tempfile
        import zipfile
        from pathlib import Path
        from unittest.mock import patch
        job_id = "c" * 32
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / job_id
            folder.mkdir()
            (folder / "clip_01.mp4").write_bytes(b"first")
            (folder / "clip_02.mp4").write_bytes(b"second")
            (folder / "clip_03.mp4").write_bytes(b"unregistered")
            with (
                patch.object(main, "BASE", Path(directory)),
                patch.object(main, "JOBS", {job_id: {"clips": [
                    {"url": "/download/%s/clip_01.mp4" % job_id},
                    {"url": "/download/%s/clip_02.mp4" % job_id},
                ]}}),
            ):
                archive_path = main.create_job_archive(job_id)
                with zipfile.ZipFile(archive_path) as archive:
                    self.assertEqual(archive.namelist(), ["CLIPS-ONTHE_01.mp4", "CLIPS-ONTHE_02.mp4"])
                    self.assertEqual(archive.read("CLIPS-ONTHE_01.mp4"), b"first")

    def test_retry_creates_new_job_for_only_missing_clips(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from fastapi import BackgroundTasks
        original_id = "d" * 32
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            folder = base / original_id
            folder.mkdir()
            (folder / "job-config.json").write_text(json.dumps({
                "url": "https://kick.com/channel/videos/example",
                "count": 5, "mode": "balanced", "follow_face": True
            }), encoding="utf-8")
            jobs = {original_id: {"status": "partial", "clips": [
                {"url": "/download/%s/clip_01.mp4" % original_id},
                {"url": "/download/%s/clip_02.mp4" % original_id},
            ]}}
            created = {}
            with (
                patch.object(main, "BASE", base),
                patch.object(main, "JOBS", jobs),
                patch.object(main, "JOB_CREATED_AT", created),
                patch.object(main, "ACTIVE_JOB", False),
            ):
                tasks = BackgroundTasks()
                result = main.retry_missing_clips(original_id, tasks)
                self.assertEqual(result["count"], 3)
                self.assertEqual(result["retry_of"], original_id)
                self.assertEqual(len(tasks.tasks), 1)
                self.assertEqual(tasks.tasks[0].args[2], 3)
                self.assertEqual(len(jobs), 2)

    def test_gemini_review_is_optional_without_an_api_key(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}, clear=False):
            self.assertIsNone(main.review_clip_with_gemini("unused.mp4", 30))

    def test_gemini_review_is_visible_in_clip_cards_and_history(self):
        self.assertIn("gemini_score", main.HTML)
        self.assertIn("gemini_reason", main.HTML)
        self.assertIn("clip-ai", main.HTML)


if __name__ == "__main__":
    unittest.main()

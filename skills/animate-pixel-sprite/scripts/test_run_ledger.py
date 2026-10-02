#!/usr/bin/env python3
"""Synthetic files only; no generator, network, credentials, or artwork calls."""
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import unittest

import run_ledger as ledger


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="run-ledger-tests-")
        self.root = Path(self.temp.name)
        self.addCleanup(self.cleanup)
        self.skill = self.root / "skill"
        self.skill.mkdir()
        (self.skill / "empty").mkdir()
        (self.skill / "SKILL.md").write_text("# Synthetic skill\nUse exact resources.\n")
        self.request = self.root / "request.txt"
        self.request.write_text("Make a synthetic test run.\n")
        self.prompt = self.root / "prompt.txt"
        self.prompt.write_text("Exact prompt, including Unicode: 雪\n\n")
        self.params = self.root / "params.json"
        self.params.write_text('{"size":"64x64","transparent_background":true}\n')
        self.reference = self.root / "reference.dat"
        self.reference.write_bytes(b"synthetic-reference\x00")
        self.output = self.root / "result.png"
        # Header-only synthetic bytes test metadata, not image validity or rendering.
        self.output.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 64, 64))
        self.run = self.root / "run-001"
        self.budgets = {"max_attempts": 8, "max_new_poses": 3, "max_stage_repairs": 2, "max_pose_repairs": 1}

    def cleanup(self):
        for base, dirs, files in os.walk(self.root):
            os.chmod(base, 0o755)
            for file in files:
                path = Path(base) / file
                if not path.is_symlink():
                    path.chmod(0o644)
        self.temp.cleanup()

    def init(self, **budgets):
        return ledger.init_run(self.run, [("test-skill", self.skill)], self.request, self.budgets | budgets)

    def start(self, stage="animate", pose="reading", repair_of=None):
        return ledger.generation_start(self.run, stage, pose, "synthetic-generator", self.prompt, self.params,
                                       [("approved-master", self.reference)], repair_of)

    def finish(self, attempt, outcome="success"):
        return ledger.generation_end(self.run, attempt, outcome,
                                     [("original", self.output)] if outcome == "success" else [],
                                     "Synthetic failure" if outcome != "success" else None)

    def test_optional_total_repair_cap_does_not_reset_at_stage_boundary(self):
        self.init(max_total_repairs=1, max_pose_repairs=4)
        first = self.start(stage="design", pose="identity")["attempt_id"]
        self.finish(first)
        self.finish(self.start(stage="design", pose="identity", repair_of=first)["attempt_id"], "failed")
        second = self.start(stage="native", pose="master")["attempt_id"]
        self.finish(second)
        with self.assertRaisesRegex(ledger.LedgerError, "total_repair_cap"):
            self.start(stage="native", pose="master", repair_of=second)

    def test_cumulative_mode_pose_repair_cap_does_not_reset_at_stage_boundary(self):
        self.init(max_total_repairs=6, max_pose_repairs=1)
        first = self.start(stage="study", pose="contact")["attempt_id"]
        self.finish(first)
        self.finish(self.start(stage="study", pose="contact", repair_of=first)["attempt_id"])
        second = self.start(stage="native", pose="contact")["attempt_id"]
        self.finish(second)
        with self.assertRaisesRegex(ledger.LedgerError, "pose_repair_cap"):
            self.start(stage="native", pose="contact", repair_of=second)

    def test_snapshot_exact_request_hashes_and_readonly(self):
        self.init()
        manifest, events, report = ledger.inspect(self.run)
        self.assertTrue(report["integrity_ok"])
        self.assertEqual(manifest["user_request"], self.request.read_text())
        self.assertEqual(manifest["skills"][0]["directories"], ["empty"])
        snap = self.run / "snapshots/test-skill/SKILL.md"
        self.assertEqual(snap.read_bytes(), (self.skill / "SKILL.md").read_bytes())
        self.assertFalse(snap.stat().st_mode & stat.S_IWUSR)
        self.assertEqual(events[0]["data"]["manifest_sha256"], ledger.digest((self.run / "run.json").read_bytes()))

    def test_existing_empty_directory_rejected(self):
        self.run.mkdir()
        with self.assertRaises(FileExistsError):
            self.init()
        self.assertEqual(list(self.run.iterdir()), [])

    def test_source_edit_does_not_change_pinned_snapshot(self):
        self.init()
        (self.skill / "SKILL.md").write_text("Changed installed copy")
        self.assertTrue(ledger.inspect(self.run)[2]["integrity_ok"])
        self.assertNotEqual((self.run / "snapshots/test-skill/SKILL.md").read_bytes(), (self.skill / "SKILL.md").read_bytes())

    def test_attempt_exact_input_copies_and_output(self):
        self.init()
        started = self.start()
        self.assertEqual(started["attempt_id"], "attempt-0001")
        self.assertEqual(ledger.inspect(self.run)[2]["missing_generation_completions"], ["attempt-0001"])
        ended = self.finish(started["attempt_id"])
        manifest, events, report = ledger.inspect(self.run)
        data = events[1]["data"]
        self.assertEqual(data["prompt"], self.prompt.read_text())
        self.assertEqual((self.run / data["prompt_file"]["path"]).read_bytes(), self.prompt.read_bytes())
        self.assertEqual(data["parameters"], json.loads(self.params.read_text()))
        self.assertEqual(data["references"][0]["sha256"], ledger.digest(self.reference.read_bytes()))
        self.assertEqual(ended["data"]["start_event_hash"], started["event_hash"])
        self.assertEqual(ended["data"]["outputs"][0]["dimensions"], [64, 64])
        self.assertGreaterEqual(ended["data"]["elapsed_seconds"], 0)
        self.assertEqual(report["missing_generation_completions"], [])
        self.output.write_bytes(b"overwritten external output")
        self.assertTrue(ledger.inspect(self.run)[2]["integrity_ok"])

    def test_failed_and_cancelled_calls_consume_global_budget(self):
        self.init(max_attempts=2)
        self.finish(self.start(pose="p1")["attempt_id"], "failed")
        self.finish(self.start(pose="p2")["attempt_id"], "cancelled")
        with self.assertRaisesRegex(ledger.LedgerError, "global_attempt_cap"):
            self.start(pose="p3")
        _, events, report = ledger.inspect(self.run)
        self.assertEqual(report["attempted_generation_calls"], 2)
        self.assertEqual(events[-1]["type"], "generation-blocked")

    def test_initial_concepts_do_not_consume_repair_caps(self):
        self.init(max_stage_repairs=0, max_pose_repairs=0)
        for _ in range(3):
            self.finish(self.start(stage="concept", pose=None)["attempt_id"])
        self.assertEqual(ledger.inspect(self.run)[2]["attempted_generation_calls"], 3)

    def test_distinct_new_pose_cap(self):
        self.init(max_new_poses=2)
        self.finish(self.start(pose="p1")["attempt_id"])
        self.finish(self.start(pose="p2")["attempt_id"])
        with self.assertRaisesRegex(ledger.LedgerError, "new_pose_cap"):
            self.start(pose="p3")

    def test_same_pose_requires_repair_link(self):
        self.init()
        self.finish(self.start()["attempt_id"])
        with self.assertRaisesRegex(ledger.LedgerError, "repair-of"):
            self.start()
        # A distinct stage creates a separately bounded stage/pose pair.
        self.finish(self.start(stage="native")["attempt_id"])

    def test_new_pose_budget_is_scoped_to_stage_pose_pair(self):
        self.init(max_new_poses=1)
        self.finish(self.start()["attempt_id"])
        with self.assertRaisesRegex(ledger.LedgerError, "new_pose_cap"):
            self.start(stage="native")

    def test_pose_repair_budget_is_scoped_to_stage_pose_pair(self):
        self.init()
        initial = self.start()["attempt_id"]
        self.finish(initial)
        self.finish(self.start(repair_of=initial)["attempt_id"])
        second_stage = self.start(stage="native")["attempt_id"]
        self.finish(second_stage)
        self.finish(self.start(stage="native", repair_of=second_stage)["attempt_id"])
        self.assertEqual(ledger.inspect(self.run)[2]["attempted_generation_calls"], 4)

    def test_repair_link_must_match_and_be_completed(self):
        self.init()
        attempt = self.start()["attempt_id"]
        with self.assertRaisesRegex(ledger.LedgerError, "Complete"):
            self.start(repair_of=attempt)
        self.finish(attempt, "failed")
        with self.assertRaisesRegex(ledger.LedgerError, "same stage and pose"):
            self.start(pose="other", repair_of=attempt)
        with self.assertRaisesRegex(ledger.LedgerError, "same stage and pose"):
            self.start(stage="other", repair_of=attempt)
        with self.assertRaises(ledger.LedgerError):
            self.start(repair_of="unknown")

    def test_per_pose_repair_cap_counts_failed_repairs(self):
        self.init()
        initial = self.start()["attempt_id"]
        self.finish(initial)
        repair = self.start(repair_of=initial)["attempt_id"]
        self.finish(repair, "failed")
        with self.assertRaisesRegex(ledger.LedgerError, "pose_repair_cap"):
            self.start(repair_of=repair)

    def test_stage_repair_cap_across_distinct_poses(self):
        self.init(max_stage_repairs=1)
        initial1 = self.start(pose="p1")["attempt_id"]
        self.finish(initial1)
        initial2 = self.start(pose="p2")["attempt_id"]
        self.finish(initial2)
        self.finish(self.start(pose="p1", repair_of=initial1)["attempt_id"])
        with self.assertRaisesRegex(ledger.LedgerError, "stage_repair_cap"):
            self.start(pose="p2", repair_of=initial2)

    def test_duplicate_unknown_completion_rejected(self):
        self.init()
        with self.assertRaisesRegex(ledger.LedgerError, "Unknown"):
            self.finish("missing")
        attempt = self.start()["attempt_id"]
        self.finish(attempt)
        with self.assertRaisesRegex(ledger.LedgerError, "already"):
            self.finish(attempt)

    def test_dimensions_check(self):
        self.init()
        attempt = self.start()["attempt_id"]
        with self.assertRaisesRegex(ledger.LedgerError, "disagree"):
            ledger.generation_end(self.run, attempt, "success", [("original", self.output)], output_dimensions={"original": [32, 64]})
        self.assertEqual(ledger.inspect(self.run)[2]["missing_generation_completions"], [attempt])
        self.finish(attempt)

    def test_general_evidence_and_failure_retained(self):
        self.init()
        for kind in ("decision", "check", "failure", "review"):
            ledger.general_event(self.run, kind, {"passed": False, "actual": "synthetic evidence"}, [("log", self.reference)])
        ledger.finalize(self.run, "failed", "Synthetic check did not pass")
        _, events, report = ledger.inspect(self.run)
        self.assertTrue(report["integrity_ok"])
        self.assertEqual(report["status"], "failed")
        self.assertEqual([e["type"] for e in events][1:-1], ["decision", "check", "failure", "review"])
        with self.assertRaisesRegex(ledger.LedgerError, "finalized"):
            ledger.general_event(self.run, "decision", {"why": "trying again"})
        with self.assertRaisesRegex(ledger.LedgerError, "finalized"):
            ledger.finalize(self.run, "succeeded", "Cannot erase failure")

    def test_incomplete_finalize_keeps_missing_completion(self):
        self.init()
        attempt = self.start()["attempt_id"]
        with self.assertRaisesRegex(ledger.LedgerError, "uncompleted"):
            ledger.finalize(self.run, "succeeded", "Not yet")
        ledger.finalize(self.run, "incomplete", "Tool result never arrived")
        report = ledger.inspect(self.run)[2]
        self.assertEqual(report["missing_generation_completions"], [attempt])
        self.assertEqual(report["status"], "incomplete")

    def test_snapshot_tampering_blocks_further_recording(self):
        self.init()
        snap = self.run / "snapshots/test-skill/SKILL.md"
        snap.chmod(0o644)
        snap.write_text("changed")
        self.assertFalse(ledger.inspect(self.run)[2]["integrity_ok"])
        with self.assertRaisesRegex(ledger.LedgerError, "integrity"):
            self.start()

    def test_extra_snapshot_file_detected(self):
        self.init()
        folder = self.run / "snapshots/test-skill"
        folder.chmod(0o755)
        (folder / "unrecorded.txt").write_text("extra")
        self.assertFalse(ledger.inspect(self.run)[2]["integrity_ok"])

    def test_chain_tampering_and_truncated_tail_detected(self):
        self.init()
        ledger.general_event(self.run, "decision", {"reason": "one"})
        path = self.run / "events.jsonl"
        original = path.read_bytes()
        path.write_bytes(original.replace(b'"one"', b'"two"'))
        with self.assertRaisesRegex(ledger.LedgerError, "chain"):
            ledger.inspect(self.run)
        path.write_bytes(original[:-1])
        with self.assertRaisesRegex(ledger.LedgerError, "tail"):
            ledger.inspect(self.run)

    def test_manifest_tampering_detected(self):
        self.init()
        path = self.run / "run.json"
        path.chmod(0o644)
        manifest = json.loads(path.read_text())
        manifest["budgets"]["max_attempts"] = 999
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ledger.LedgerError, "manifest"):
            ledger.inspect(self.run)

    def test_symlink_and_secret_files_rejected(self):
        (self.skill / "linked").symlink_to(self.reference)
        with self.assertRaisesRegex(ledger.LedgerError, "symlink"):
            self.init()
        self.assertTrue((self.run / "INITIALIZATION_FAILED.txt").exists())
        self.assertFalse((self.run / "run.json").exists())

    def test_secret_parameters_not_recorded(self):
        self.init()
        self.params.write_text(json.dumps({"api_" + "key": "synthetic-credential-placeholder"}))
        with self.assertRaisesRegex(ledger.LedgerError, "Credential"):
            self.start()
        self.assertEqual(ledger.inspect(self.run)[2]["attempted_generation_calls"], 0)
        self.assertNotIn(b"synthetic-credential-placeholder", (self.run / "events.jsonl").read_bytes())

    def test_arbitrary_check_metadata_is_not_mistaken_for_copied_evidence(self):
        self.init()
        ledger.general_event(self.run, "check", {"path": "/external/file", "sha256": "reported", "bytes": 5})
        self.assertTrue(ledger.inspect(self.run)[2]["integrity_ok"])

    def test_concurrent_start_cannot_overspend(self):
        self.init(max_attempts=1)
        script = Path(ledger.__file__)
        commands = []
        for pose in ("one", "two"):
            commands.append(subprocess.Popen([sys.executable, script, "generation-start", self.run,
                "--stage", "animate", "--pose", pose, "--tool", "synthetic",
                "--prompt-file", self.prompt, "--parameters-file", self.params],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        results = [(p.communicate(), p.returncode) for p in commands]
        self.assertEqual(sorted(code for _, code in results), [0, 2])
        self.assertEqual(ledger.inspect(self.run)[2]["attempted_generation_calls"], 1)

    def test_cli_smoke_and_exit_status(self):
        self.init()
        script = Path(ledger.__file__)
        result = subprocess.run([sys.executable, script, "verify", self.run], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["integrity_ok"])
        self.start()
        result = subprocess.run([sys.executable, script, "verify", self.run], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["missing_generation_completions"], ["attempt-0001"])


if __name__ == "__main__":
    unittest.main()

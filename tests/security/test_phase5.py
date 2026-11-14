"""Disposable, real shadow Git fixtures; never mutate the checkout's history."""

import json
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from crocodile.security import ApprovalSession
from crocodile.security.paths import atomic_write
from crocodile.security.undo import ShadowUndo, UndoConflict, UndoError, main


class Phase5Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "repo"
        self.root.mkdir()
        self.session = ApprovalSession(self.root, mode="confidential")
        self.manager = ShadowUndo(
            self.root, storage=self.base / "shadow", session=self.session
        )

    def tearDown(self):
        # Windows may briefly retain a killed job's files (only sharing violations).
        deadline = time.monotonic() + 2
        while True:
            try:
                self.temporary.cleanup()
                break
            except OSError as error:
                if (
                    getattr(error, "winerror", None) != 32
                    or time.monotonic() >= deadline
                ):
                    raise
                time.sleep(0.05)

    def apply(self, changes):
        identifier = self.manager.prepare(
            changes, reason="synthetic fixture", call_id="edit-1"
        )
        self.manager.validate(identifier)
        for raw, data in changes.items():
            path = self.root / raw
            mode = (
                stat.S_IMODE(path.stat().st_mode)
                if path.exists()
                else (0o666 if os.name == "nt" else 0o600)
            )
            if data is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(raw, data, root=self.root, mode="confidential")
                os.chmod(path, mode)
        self.manager.complete(identifier)
        return identifier

    def test_modified_created_deleted_binary_and_history_separation(self):
        (self.root / "modified.bin").write_bytes(b"before\x00\xff\r\n")
        (self.root / "removed.txt").write_bytes(b"restore me")
        # A target Git directory/index/config need not even be valid Git.
        target_git = self.root / ".git"
        target_git.mkdir()
        (target_git / "config").write_bytes(b"do not read or change")
        (target_git / "index").write_bytes(b"unchanged index")
        original = {p.name: p.read_bytes() for p in target_git.iterdir()}
        identifier = self.apply(
            {"modified.bin": b"after", "new.txt": b"new", "removed.txt": None}
        )
        fresh = ShadowUndo(
            self.root, storage=self.base / "shadow", session=self.session
        )
        self.assertEqual(fresh.list()[0]["id"], identifier)
        self.assertEqual(set(fresh.undo()), {"modified.bin", "new.txt", "removed.txt"})
        self.assertEqual(
            (self.root / "modified.bin").read_bytes(), b"before\x00\xff\r\n"
        )
        self.assertEqual((self.root / "removed.txt").read_bytes(), b"restore me")
        self.assertFalse((self.root / "new.txt").exists())
        self.assertEqual(
            {p.name: p.read_bytes() for p in target_git.iterdir()}, original
        )
        self.assertEqual(fresh.list()[0]["state"], "undone")
        self.assertTrue(
            (self.base / "shadow" / "git" / "refs" / "crocodile" / identifier).is_file()
        )

    def test_conflict_preflight_preserves_every_file(self):
        (self.root / "a").write_bytes(b"old a")
        (self.root / "b").write_bytes(b"old b")
        self.apply({"a": b"agent a", "b": b"agent b"})
        (self.root / "b").write_bytes(b"user's later work")
        with self.assertRaises(UndoConflict) as raised:
            self.manager.undo()
        self.assertEqual(raised.exception.paths, ["b"])
        self.assertEqual((self.root / "a").read_bytes(), b"agent a")
        self.assertEqual((self.root / "b").read_bytes(), b"user's later work")
        self.assertEqual(self.manager.list()[0]["state"], "applied")

    def test_multiple_steps_same_path_and_whole_batch_conflicts(self):
        (self.root / "a").write_bytes(b"initial")
        (self.root / "other").write_bytes(b"original")
        self.apply({"a": b"first", "other": b"agent"})
        self.apply({"a": b"second"})
        (self.root / "other").write_bytes(b"user")
        with self.assertRaises(UndoConflict):
            self.manager.undo(2)
        self.assertEqual((self.root / "a").read_bytes(), b"second")
        (self.root / "other").write_bytes(b"agent")
        self.assertEqual(set(self.manager.undo(2)), {"a", "other"})
        self.assertEqual((self.root / "a").read_bytes(), b"initial")

    def test_prepare_binding_and_complete_do_not_adopt_user_edits(self):
        path = self.root / "a"
        path.write_bytes(b"before")
        identifier = self.manager.prepare(
            {"a": b"intended"}, reason="test", call_id="call"
        )
        path.write_bytes(b"user edit before apply")
        with self.assertRaises(UndoConflict):
            self.manager.validate(identifier)
        with self.assertRaises(UndoConflict):
            self.manager.complete(identifier)
        with self.assertRaises(UndoConflict):
            self.manager.cancel(identifier)
        with self.assertRaises(UndoError):
            self.manager.prepare({"b": b"another"}, reason="test", call_id="call-2")
        with self.assertRaises(UndoError):
            self.manager.undo()
        path.write_bytes(b"before")
        self.manager.cancel(identifier)
        self.assertEqual(self.manager.list()[0]["state"], "cancelled")

    def test_created_and_removed_conflicts(self):
        (self.root / "removed").write_bytes(b"old")
        self.apply({"created": b"agent", "removed": None})
        (self.root / "created").unlink()
        (self.root / "removed").write_bytes(b"user recreated")
        with self.assertRaises(UndoConflict) as raised:
            self.manager.undo()
        self.assertEqual(set(raised.exception.paths), {"created", "removed"})
        self.assertEqual((self.root / "removed").read_bytes(), b"user recreated")

    def test_paths_limits_and_links(self):
        for raw in (
            "../outside",
            ".git/config",
            ".crocodile/state",
            ".env",
            "missing/file",
        ):
            with self.subTest(path=raw), self.assertRaises((UndoError, ValueError)):
                self.manager.prepare({raw: b"x"}, reason="test", call_id="call")
        for changes in ({}, {"a": "not bytes"}, {"a": b"x" * 11}):
            with (
                self.subTest(changes=str(changes)),
                patch("crocodile.security.undo.MAX_FILE", 10),
                self.assertRaises((UndoError, TypeError)),
            ):
                self.manager.prepare(changes, reason="test", call_id="call")
        path = self.root / "original"
        path.write_bytes(b"data")
        alias = self.root / "alias"
        os.link(path, alias)
        with self.assertRaises(ValueError):
            self.manager.prepare({"alias": b"replace"}, reason="test", call_id="call")
        with self.assertRaises(UndoError):
            ShadowUndo(self.root, storage=self.root / "shadow", session=self.session)

    def test_interrupted_restore_is_resumable(self):
        (self.root / "a").write_bytes(b"before a")
        (self.root / "b").write_bytes(b"before b")
        self.apply({"a": b"after a", "b": b"after b"})
        real_restore = self.manager._restore

        def fail_second(item):
            if item["path"] == "b":
                raise OSError("synthetic disk failure")
            return real_restore(item)

        with (
            patch.object(self.manager, "_restore", side_effect=fail_second),
            self.assertRaises(OSError),
        ):
            self.manager.undo()
        self.assertEqual(self.manager.list()[0]["state"], "restoring")
        self.assertEqual((self.root / "a").read_bytes(), b"before a")
        self.assertEqual((self.root / "b").read_bytes(), b"after b")
        self.manager.undo()
        self.assertEqual((self.root / "b").read_bytes(), b"before b")

    def test_metadata_tampering_lock_and_invalid_counts(self):
        for count in (0, -1, True, 1.5, "1"):
            with self.subTest(count=count), self.assertRaises(ValueError):
                self.manager.undo(count)
        with self.assertRaises(UndoError):
            self.manager.undo()
        lock = self.base / "shadow" / "operation.lock"
        lock.write_text("fixture")
        with self.assertRaises(UndoError):
            self.manager.list()
        lock.unlink()
        config = self.base / "shadow" / "git" / "config"
        config.write_text(config.read_text() + "\n[include]\n path = hostile\n")
        with self.assertRaises(UndoError):
            self.manager.list()

    def test_permissions_and_consent_invalidation(self):
        path = self.root / "a"
        path.write_bytes(b"original")
        os.chmod(path, 0o700 if os.name != "nt" else 0o666)
        mode = stat.S_IMODE(path.stat().st_mode)
        self.apply({"a": b"agent"})
        self.session._consent = "synthetic consent"
        self.session._permits["fixture"] = "permit"
        self.manager.undo()
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)
        self.assertIsNone(self.session._consent)
        self.assertFalse(self.session._permits)

    def test_user_replacement_with_directory_is_a_conflict(self):
        self.apply({"a": b"agent"})
        (self.root / "a").unlink()
        (self.root / "a").mkdir()
        with self.assertRaises(UndoConflict) as raised:
            self.manager.undo()
        self.assertEqual(raised.exception.paths, ["a"])
        self.assertTrue((self.root / "a").is_dir())

    def test_missing_parent_of_removed_file_is_a_conflict(self):
        parent = self.root / "folder"
        parent.mkdir()
        (parent / "removed").write_bytes(b"before")
        self.apply({"folder/removed": None})
        parent.rmdir()
        with self.assertRaises(UndoConflict) as raised:
            self.manager.undo()
        self.assertEqual(raised.exception.paths, ["folder/removed"])
        self.assertFalse(parent.exists())

    def test_final_revalidation_preserves_edit_during_staging(self):
        path = self.root / "a"
        path.write_bytes(b"before")
        self.apply({"a": b"agent"})
        real_chmod = os.chmod

        def intervene(name, mode):
            real_chmod(name, mode)
            path.write_bytes(b"intervening user change")

        with (
            patch("crocodile.security.undo.os.chmod", side_effect=intervene),
            self.assertRaises(UndoConflict),
        ):
            self.manager.undo()
        self.assertEqual(path.read_bytes(), b"intervening user change")
        self.assertEqual(self.manager.list()[0]["state"], "restoring")

    def test_manifest_and_cli_handoff(self):
        self.apply({"a": b"agent"})
        with (
            patch("crocodile.security.undo.ShadowUndo", return_value=self.manager),
            patch(
                "crocodile.security.confidential.mode_for", return_value="confidential"
            ),
            patch("builtins.print") as output,
        ):
            self.assertEqual(main(["--repo", str(self.root), "--list"]), 0)
            self.assertIn("applied", output.call_args[0][0])
            self.assertEqual(main(["--repo", str(self.root)]), 0)
            self.assertEqual(output.call_args[0][0], "Restored a")
            self.assertEqual(main(["--repo", str(self.root)]), 1)
        ledger = json.loads(self.manager.ledger.read_text())
        ledger["root"] = "another repo"
        self.manager.ledger.write_text(json.dumps(ledger))
        with self.assertRaises(UndoError):
            self.manager.list()


if __name__ == "__main__":
    unittest.main()

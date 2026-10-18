# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import os
import stat
import types
import unittest
from unittest import mock

from codejig import atomicwrite
from codejig.atomicwrite import atomic_write, resolve_inside
from tests.util import tree, write


class Inside(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.outside = tree(self)

    def swap_for_link(self, folder):
        folder.rename(folder.with_name(folder.name + "-moved"))
        try:
            folder.symlink_to(self.outside, target_is_directory=True)
        except OSError:
            self.skipTest("no symlinks here")

    def test_a_folder_swapped_for_a_link_after_the_check_is_never_written_through(self):
        target = resolve_inside(str(write(self.root / "sub" / "x.txt", "agent!\n")), self.root)
        target.read_bytes()
        victim = write(self.outside / "x.txt", "mine\n")
        self.swap_for_link(self.root / "sub")
        with self.assertRaises(OSError):
            atomic_write(target, b"agent\n")
        self.assertEqual(victim.read_text(encoding="utf-8"), "mine\n")
        self.assertEqual(sorted(p.name for p in self.outside.iterdir()), ["x.txt"])

    def test_a_folder_swapped_before_the_read_is_not_read_through(self):
        target = resolve_inside(str(write(self.root / "sub" / "x.txt", "agent\n")), self.root)
        write(self.outside / "x.txt", "secret\n")
        self.swap_for_link(self.root / "sub")
        with self.assertRaises(OSError):
            target.read_bytes()

    def test_a_concurrent_edit_in_place_is_kept(self):
        path = write(self.root / "x.txt", "first\n")
        target = resolve_inside(str(path), self.root)
        original = target.read_bytes()
        with open(path, "r+b") as f:
            f.write(b"other\n")
        with self.assertRaises(atomicwrite.Changed):
            atomic_write(target, original.upper())
        self.assertEqual(path.read_bytes(), b"other\n")

    def test_an_edit_in_place_during_the_write_is_kept(self):
        path = write(self.root / "x.txt", "first\n")
        target = resolve_inside(str(path), self.root)
        original = target.read_bytes()
        real_fsync = os.fsync

        def edit_then_sync(fd):
            with open(path, "r+b") as f:
                f.write(b"other\n")
            real_fsync(fd)

        with mock.patch.object(atomicwrite.os, "fsync", edit_then_sync), self.assertRaises(atomicwrite.Changed):
            atomic_write(target, original.upper())
        self.assertEqual(path.read_bytes(), b"other\n")
        self.assertEqual([p.name for p in path.parent.iterdir()], ["x.txt"])

    def test_a_file_replaced_after_the_check_is_kept(self):
        path = write(self.root / "x.txt", "first\n")
        target = resolve_inside(str(path), self.root)
        target.read_bytes()
        os.replace(write(self.root / "new.txt", "editor\n"), path)
        with self.assertRaises(atomicwrite.Changed):
            atomic_write(target, b"cleaned\n")
        self.assertEqual(path.read_bytes(), b"editor\n")

    def test_an_unchanged_file_is_rewritten_with_its_mode_and_no_temp(self):
        path = write(self.root / "sub" / "a.sh", "old\n")
        os.chmod(path, 0o750)
        target = resolve_inside(str(path), self.root)
        self.assertEqual(target.read_bytes(), b"old\n")
        atomic_write(target, b"new\n")
        self.assertEqual(path.read_bytes(), b"new\n")
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o750)
        self.assertEqual([p.name for p in path.parent.iterdir()], ["a.sh"])

    def test_without_dir_fds_the_path_is_checked_again_before_the_replace(self):
        with mock.patch.object(atomicwrite, "DIR_FDS", False):
            self.test_a_folder_swapped_for_a_link_after_the_check_is_never_written_through()
            self.test_a_concurrent_edit_in_place_is_kept()

    def test_derived_paths_are_plain_paths(self):
        target = resolve_inside(str(write(self.root / "sub" / "x.txt", "x\n")), self.root)
        write(self.root / "sub" / "y.txt", "y\n")
        self.assertEqual(target.with_name("y.txt").read_bytes(), b"y\n")


class HardLinks(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.outside = tree(self)

    def link(self, path):
        other = self.outside / "other.txt"
        try:
            os.link(path, other)
        except OSError:
            self.skipTest("no hard links here")
        return other

    def assert_refused(self, target, path, other):
        with self.assertRaisesRegex(atomicwrite.HardLinked, "hard link"):
            atomic_write(target, b"new\n")
        self.assertEqual(path.read_bytes(), b"old\n")
        self.assertEqual(os.stat(path).st_nlink, 2)
        self.assertTrue(os.path.samefile(path, other))
        self.assertEqual([p.name for p in path.parent.iterdir()], [path.name])

    def test_a_hard_linked_target_is_refused(self):
        path = write(self.root / "sub" / "x.txt", "old\n")
        other = self.link(path)
        self.assert_refused(path, path, other)

    def test_a_checked_file_hard_linked_after_the_check_is_refused(self):
        for dir_fds in (True, False):
            with self.subTest(dir_fds=dir_fds), mock.patch.object(atomicwrite, "DIR_FDS", dir_fds and atomicwrite.DIR_FDS):
                path = write(self.root / f"sub{dir_fds}" / "x.txt", "old\n")
                target = resolve_inside(str(path), self.root)
                target.read_bytes()
                other = self.link(path)
                self.assert_refused(target, path, other)
                os.unlink(other)

    def test_the_refusal_is_a_value_error_so_install_reports_it(self):
        self.assertTrue(issubclass(atomicwrite.HardLinked, ValueError))
        self.assertTrue(issubclass(atomicwrite.HardLinked, atomicwrite.Changed))


class WindowsHeldFolders(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.path = write(self.root / "sub" / "deeper" / "x.txt", "old\n")
        self.target = resolve_inside(str(self.path), self.root)
        self.target.read_bytes()
        self.opened = {}
        real = atomicwrite._open_dir if os.name == "nt" else (lambda p: os.open(p, os.O_RDONLY))

        def open_dir(path):
            fd = real(path)
            self.opened[path] = fd
            return fd

        for patcher in (mock.patch.object(atomicwrite, "DIR_FDS", False), mock.patch.object(atomicwrite, "_open_dir", open_dir)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def is_open(self, fd):
        try:
            os.fstat(fd)
        except OSError:
            return False
        return True

    def folders(self):
        root = str(self.target.checked_root)
        return [root, os.path.join(root, "sub"), os.path.join(root, "sub", "deeper")]

    def test_every_folder_from_the_root_to_the_file_is_held_through_the_replace(self):
        seen = []
        real_replace = os.replace

        def replace(src, dst):
            seen.append([self.is_open(fd) for fd in self.opened.values()])
            real_replace(src, dst)

        with mock.patch.object(atomicwrite.os, "replace", replace):
            atomic_write(self.target, b"new\n")
        self.assertEqual(list(self.opened), self.folders())
        self.assertEqual(seen, [[True, True, True]])
        self.assertFalse(any(self.is_open(fd) for fd in self.opened.values()))
        self.assertEqual(self.path.read_bytes(), b"new\n")

    def test_a_junction_or_link_on_the_way_is_refused(self):
        real_fstat = os.fstat
        junction = os.path.join(str(self.target.checked_root), "sub")

        def fstat(fd):
            if self.opened.get(junction) == fd:
                return types.SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
            return real_fstat(fd)

        with mock.patch.object(atomicwrite.os, "fstat", fstat), self.assertRaisesRegex(atomicwrite.Changed, "junction"):
            atomic_write(self.target, b"new\n")
        self.assertEqual(self.path.read_bytes(), b"old\n")
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["x.txt"])
        self.assertFalse(any(self.is_open(fd) for fd in self.opened.values()))

    @unittest.skipUnless(os.name == "nt", "folders held open block a rename only on Windows")
    def test_a_held_folder_cannot_be_moved_during_the_write(self):
        errors = []
        real_replace = os.replace

        def replace(src, dst):
            try:
                os.rename(self.root / "sub", self.root / "moved")
            except OSError as e:
                errors.append(e)
            real_replace(src, dst)

        with mock.patch.object(atomicwrite.os, "replace", replace):
            atomic_write(self.target, b"new\n")
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], PermissionError)
        self.assertEqual(self.path.read_bytes(), b"new\n")


class ResidualWindowBetweenTheLastCheckAndTheReplaceOnEveryPlatform(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.outside = tree(self)

    def write_with(self, dir_fds, before_replace):
        path = write(self.root / f"sub{dir_fds}" / "x.txt", "old\n")
        target = resolve_inside(str(path), self.root)
        target.read_bytes()
        real_replace, real_rename = os.replace, os.rename

        def replace(*args, **kwargs):
            before_replace(path)
            return real_replace(*args, **kwargs)

        def rename(*args, **kwargs):
            before_replace(path)
            return real_rename(*args, **kwargs)

        with (mock.patch.object(atomicwrite, "DIR_FDS", dir_fds and atomicwrite.DIR_FDS),
              mock.patch.object(atomicwrite.os, "replace", replace), mock.patch.object(atomicwrite.os, "rename", rename)):
            atomic_write(target, b"new\n")
        return path

    def test_an_edit_in_place_in_that_window_is_overwritten(self):
        for dir_fds in (True, False):
            with self.subTest(dir_fds=dir_fds):
                path = self.write_with(dir_fds, lambda p: p.write_bytes(b"editor\n"))
                self.assertEqual(path.read_bytes(), b"new\n")

    def test_the_file_swapped_for_a_link_in_that_window_replaces_the_link_and_writes_nothing_outside(self):
        victim = write(self.outside / "victim.txt", "mine\n")

        def swap(p):
            p.unlink()
            try:
                p.symlink_to(victim)
            except OSError:
                self.skipTest("no symlinks here")

        for dir_fds in (True, False):
            with self.subTest(dir_fds=dir_fds):
                path = self.write_with(dir_fds, swap)
                self.assertFalse(path.is_symlink())
                self.assertEqual(path.read_bytes(), b"new\n")
                self.assertEqual(victim.read_text(encoding="utf-8"), "mine\n")

if __name__ == "__main__":
    unittest.main()

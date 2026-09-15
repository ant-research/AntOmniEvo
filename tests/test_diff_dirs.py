"""Tests for diff_dirs script."""

import os
import tempfile

from antomnievo.proposer.scripts.diff_dirs import diff_dirs


class TestDiffDirs:
    def test_no_differences(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.path.join(tmpdir, "old")
            new = os.path.join(tmpdir, "new")
            os.makedirs(old)
            os.makedirs(new)
            with open(os.path.join(old, "a.txt"), "w") as f:
                f.write("hello")
            with open(os.path.join(new, "a.txt"), "w") as f:
                f.write("hello")

            result = diff_dirs(old, new)
            assert result == "" or "No differences" in result or result.strip() == ""

    def test_modified_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.path.join(tmpdir, "old")
            new = os.path.join(tmpdir, "new")
            os.makedirs(old)
            os.makedirs(new)
            with open(os.path.join(old, "a.txt"), "w") as f:
                f.write("hello\n")
            with open(os.path.join(new, "a.txt"), "w") as f:
                f.write("world\n")

            result = diff_dirs(old, new)
            assert "a.txt" in result
            assert "-hello" in result or "hello" in result

    def test_new_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.path.join(tmpdir, "old")
            new = os.path.join(tmpdir, "new")
            os.makedirs(old)
            os.makedirs(new)
            with open(os.path.join(old, "a.txt"), "w") as f:
                f.write("hello\n")
            with open(os.path.join(new, "a.txt"), "w") as f:
                f.write("hello\n")
            with open(os.path.join(new, "b.txt"), "w") as f:
                f.write("new file\n")

            result = diff_dirs(old, new)
            assert "b.txt" in result

    def test_deleted_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.path.join(tmpdir, "old")
            new = os.path.join(tmpdir, "new")
            os.makedirs(old)
            os.makedirs(new)
            with open(os.path.join(old, "a.txt"), "w") as f:
                f.write("hello\n")
            with open(os.path.join(old, "b.txt"), "w") as f:
                f.write("will be deleted\n")
            with open(os.path.join(new, "a.txt"), "w") as f:
                f.write("hello\n")

            result = diff_dirs(old, new)
            assert "b.txt" in result

    def test_max_lines_truncation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.path.join(tmpdir, "old")
            new = os.path.join(tmpdir, "new")
            os.makedirs(old)
            os.makedirs(new)
            with open(os.path.join(old, "big.txt"), "w") as f:
                f.writelines(f"old line {i}\n" for i in range(200))
            with open(os.path.join(new, "big.txt"), "w") as f:
                f.writelines(f"new line {i}\n" for i in range(200))

            result = diff_dirs(old, new, max_lines=50)
            assert "truncated" in result.lower()

    def test_max_lines_zero_unlimited(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.path.join(tmpdir, "old")
            new = os.path.join(tmpdir, "new")
            os.makedirs(old)
            os.makedirs(new)
            with open(os.path.join(old, "big.txt"), "w") as f:
                f.writelines(f"old line {i}\n" for i in range(200))
            with open(os.path.join(new, "big.txt"), "w") as f:
                f.writelines(f"new line {i}\n" for i in range(200))

            result = diff_dirs(old, new, max_lines=0)
            assert "truncated" not in result.lower()

    def test_nested_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.path.join(tmpdir, "old", "sub")
            new = os.path.join(tmpdir, "new", "sub")
            os.makedirs(old)
            os.makedirs(new)
            with open(os.path.join(old, "a.txt"), "w") as f:
                f.write("old\n")
            with open(os.path.join(new, "a.txt"), "w") as f:
                f.write("new\n")

            result = diff_dirs(os.path.join(tmpdir, "old"), os.path.join(tmpdir, "new"))
            assert "a.txt" in result

    def test_multiple_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.path.join(tmpdir, "old")
            new = os.path.join(tmpdir, "new")
            os.makedirs(old)
            os.makedirs(new)
            with open(os.path.join(old, "a.txt"), "w") as f:
                f.write("a\n")
            with open(os.path.join(old, "b.txt"), "w") as f:
                f.write("b\n")
            with open(os.path.join(new, "a.txt"), "w") as f:
                f.write("a_changed\n")
            with open(os.path.join(new, "b.txt"), "w") as f:
                f.write("b\n")

            result = diff_dirs(old, new)
            assert "a.txt" in result
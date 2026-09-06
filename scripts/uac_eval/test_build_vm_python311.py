"""Stdlib contract/helper tests only; never builds Python or touches VM paths."""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import io


SCRIPT = Path(__file__).with_name("build_vm_python311.sh")
TEXT = SCRIPT.read_text(encoding="utf-8")


def block(name):
    return re.search(r"<<'" + name + r"'[^\n]*\n(.*?)\n" + name + r"\n", TEXT, re.S).group(1)


def run_block(name, *args):
    return subprocess.run([sys.executable, "-I", "-B", "-c", block(name), *map(str, args)],
                          capture_output=True, text=True, timeout=20)


class BuildContracts(unittest.TestCase):
    def test_bash_syntax(self):
        bash = shutil.which("bash")
        if sys.platform == "win32":
            git_bash = Path("C:/Program Files/Git/bin/bash.exe")
            bash = str(git_bash) if git_bash.exists() else None
        if not bash:
            self.skipTest("Bash unavailable; not VM execution proof")
        result = subprocess.run([bash, "--noprofile", "--norc", "-n", str(SCRIPT)],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unknown_mode_rejected_before_preflight(self):
        bash = shutil.which("bash")
        if sys.platform == "win32":
            git_bash = Path("C:/Program Files/Git/bin/bash.exe")
            bash = str(git_bash) if git_bash.exists() else None
        if not bash:
            self.skipTest("Bash unavailable; not VM execution proof")
        result = subprocess.run([bash, "--noprofile", "--norc", str(SCRIPT), "--apply"],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage:", result.stderr)
        self.assertNotIn("PYTHON_BUILD_DIR", result.stdout)

    def test_explicit_build_and_fixed_verified_source(self):
        self.assertIn("MODE=${1:---check}", TEXT)
        self.assertIn('"$MODE" != --check && "$MODE" != --build', TEXT)
        self.assertIn("https://www.python.org/ftp/python/3.11.16/Python-3.11.16.tar.xz", TEXT)
        self.assertIn("91bcdebfdde239a003ae93738a7fce0f9230fee5c4bc2b86f6e6e8c6f98aabe8", TEXT)
        self.assertLess(TEXT.index("sha256sum --check"), TEXT.index("STEP=SAFE_SOURCE_EXTRACTION"))

    def test_read_only_check_exits_before_mutations(self):
        check_end = TEXT.index("STEP=PRIVATE_WORK_DIRECTORY")
        prefix = TEXT[:check_end]
        self.assertIn('if [[ "$MODE" == --check ]]', prefix)
        self.assertIn("exit 0", prefix)
        self.assertNotRegex(prefix, r"(?m)^clean (?:curl|mkdir|mktemp|make|timeout)\b")
        self.assertIn("-fsyntax-only -", prefix)
        self.assertIn("not os.path.lexists(prefix)", block("PY_PREFLIGHT"))

    def test_no_os_runtime_or_deletion_commands(self):
        code = "\n".join(line for line in TEXT.splitlines() if not line.lstrip().startswith("#"))
        self.assertNotRegex(code, r"(?m)^\s*(?:clean )?(?:sudo |/usr/(?:s?bin)/)?(?:apt(?:-get)?|dpkg|systemctl|service|reboot|rm|pip|chroma)\b")
        self.assertNotIn("update-alternatives", code)
        self.assertNotIn("--system-site-packages", code)
        self.assertIn("make -j1 altinstall", code)
        self.assertNotRegex(code, r"make[^\n]*\sinstall(?:\s|$)")
        self.assertIn('clean mkdir -m 755 "$PREFIX"', code)

    def test_clean_environment_and_bounded_work(self):
        self.assertIn("/usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C", TEXT)
        self.assertIn("curl --disable --proto '=https' --proto-redir '=https'", TEXT)
        self.assertNotIn("--insecure", TEXT)
        self.assertIn("--connect-timeout 30 --max-time 300 --retry 2", TEXT)
        self.assertIn("timeout --kill-after=30s 2400 make -j2", TEXT)
        self.assertIn("mktemp -d /root/aem-python-build-XXXXXXXX", TEXT)
        self.assertIn('"ro", "noexec"', block("PY_PREFLIGHT"))

    def test_original_interpreter_rechecked_and_compile_probe_precedes_install(self):
        self.assertIn('"/usr/bin/python3", "/usr/bin/python3.11"', block("PY_SYSTEM_HASH"))
        self.assertIn('path.resolve(strict=True)', block("PY_SYSTEM_HASH"))
        self.assertIn('clean cmp "$BUILD_ROOT/system-python-before.json" "$BUILD_ROOT/system-python-after.json"', TEXT)
        self.assertLess(TEXT.index("STEP=BUILT_STDLIB_PROBE"), TEXT.index("STEP=RESERVE_FRESH_PREFIX"))
        self.assertLess(TEXT.index("STEP=ORIGINAL_INTERPRETER_RECHECK"), TEXT.index("printf 'PASS_INTERPRETER_ONLY"))

    def test_probe_is_final_and_does_not_claim_rag(self):
        probe = block("PY_STDLIB")
        self.assertIn('(3, 11, 16, "final", 0)', probe)
        self.assertIn("get_int_max_str_digits", probe)
        self.assertIn('sqlite3.connect(":memory:")', probe)
        for module in ("ssl", "ctypes", "sqlite3", "bz2", "lzma", "zlib", "venv", "ensurepip"):
            self.assertIn("import " + module, probe)
        self.assertIn('"rag_repaired": False', probe)
        self.assertNotIn("sentence_transformers", probe)


class MakefileWorkerTests(unittest.TestCase):
    def fixture(self):
        return "unchanged\n" + "\t\t-j0 -d $(LIBDEST) -f \\\n" * 3 + "\t\t-j0 -d $(LIBDEST)/site-packages -f \\\n" * 3

    def test_only_six_compileall_lines_change(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Makefile"
            original = self.fixture()
            path.write_bytes(original.encode())
            result = run_block("PY_MAKEFILE", path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(path.read_text(), original.replace("-j0", "-j1"))
            self.assertIn('"replacements": 6', result.stdout)

    def test_unknown_layout_never_changes_file(self):
        for original in (self.fixture().replace("-j0", "-j9", 1), self.fixture() + "other -j0\n",
                         self.fixture().replace("/site-packages", "/unexpected", 1)):
            with self.subTest(original=original), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "Makefile"
                path.write_bytes(original.encode())
                result = run_block("PY_MAKEFILE", path)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(path.read_bytes(), original.encode())


class ArchiveTests(unittest.TestCase):
    def archive(self, path, names, kind=None):
        with tarfile.open(path, "w:xz") as handle:
            for name in names:
                item = tarfile.TarInfo(name)
                item.mode = 0o755
                if kind is not None:
                    item.type = kind
                    item.linkname = "../elsewhere"
                    handle.addfile(item)
                else:
                    item.size = 4
                    handle.addfile(item, io.BytesIO(b"test"))

    def test_extract_regular_official_tree(self):
        with tempfile.TemporaryDirectory() as folder:
            archive, dest = Path(folder) / "source.tar.xz", Path(folder) / "out"
            self.archive(archive, ["Python-3.11.16/configure", "Python-3.11.16/Lib/example.py"])
            result = run_block("PY_EXTRACT", archive, dest)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((dest / "Python-3.11.16/configure").read_bytes(), b"test")

    def test_bad_names_and_duplicate_members_fail_before_writes(self):
        cases = [["/outside"], ["Python-3.11.16/../../outside"], ["wrong/file"],
                 ["Python-3.11.16/one\\two"], ["Python-3.11.16/a", "Python-3.11.16/a"]]
        for names in cases:
            with self.subTest(names=names), tempfile.TemporaryDirectory() as folder:
                archive, dest = Path(folder) / "source.tar.xz", Path(folder) / "out"
                self.archive(archive, names)
                result = run_block("PY_EXTRACT", archive, dest)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(dest.exists())

    def test_links_and_devices_rejected(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                archive, dest = Path(folder) / "source.tar.xz", Path(folder) / "out"
                self.archive(archive, ["Python-3.11.16/link"], kind)
                result = run_block("PY_EXTRACT", archive, dest)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(dest.exists())

    def test_existing_destination_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            archive, dest = Path(folder) / "source.tar.xz", Path(folder) / "out"
            self.archive(archive, ["Python-3.11.16/a"])
            dest.mkdir()
            marker = dest / "keep"
            marker.write_bytes(b"keep")
            result = run_block("PY_EXTRACT", archive, dest)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(marker.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main(verbosity=2)

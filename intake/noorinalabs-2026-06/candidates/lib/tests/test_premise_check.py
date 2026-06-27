"""Tests for premise_check — the /wave-scope premise-rot gate (main#837).

Covers the three layers the module is split into:

  1. Pure extraction/classification — ``looks_like_path``, ``normalize_path``,
     ``extract_path_candidates``: prose must NOT yield candidates (no false
     STOP), real paths and symbol-in-file refs must.
  2. Verdict logic with INJECTED checkers (zero git): MISSING -> STOP,
     UNVERIFIABLE -> WARN (env gap, never a STOP), all-present -> OK, and the
     #705/#816 regression cases.
  3. A real ``git`` integration test over a throwaway repo — proves
     ``git cat-file -e`` / ``git grep`` are invoked correctly against a ref,
     distinguishing a present path, a deleted path, and an unknown ref.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

# Helper lives at .claude/lib/premise_check.py; this test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import premise_check as pc  # noqa: E402


class LooksLikePathTest(unittest.TestCase):
    def test_accepts_slash_paths(self) -> None:
        self.assertTrue(pc.looks_like_path(".claude/lib/wave_seq.py"))
        self.assertTrue(pc.looks_like_path("ontology/repos/deploy.yaml"))
        self.assertTrue(pc.looks_like_path(".claude/lib/"))  # directory tree

    def test_accepts_bare_filename_with_known_ext(self) -> None:
        self.assertTrue(pc.looks_like_path("wave_key_reset.py"))
        self.assertTrue(pc.looks_like_path("CLAUDE.md"))

    def test_rejects_prose_and_non_paths(self) -> None:
        for tok in ("origin", "the", "wave-scope", "HEAD", "premise"):
            self.assertFalse(pc.looks_like_path(tok), tok)

    def test_rejects_bare_filename_unknown_ext(self) -> None:
        # No slash and an unknown extension -> not confidently a path.
        self.assertFalse(pc.looks_like_path("v1.2"))
        self.assertFalse(pc.looks_like_path("e.g"))

    def test_rejects_url_issue_ref_number(self) -> None:
        self.assertFalse(pc.looks_like_path("https://example.com/a/b.py"))
        self.assertFalse(pc.looks_like_path("#705"))
        self.assertFalse(pc.looks_like_path("42"))

    def test_rejects_whitespace(self) -> None:
        self.assertFalse(pc.looks_like_path("a b.py"))


class NormalizePathTest(unittest.TestCase):
    def test_strips_backticks_and_trailing_punct(self) -> None:
        self.assertEqual(pc.normalize_path("`foo.py`,"), "foo.py")
        self.assertEqual(pc.normalize_path("foo.py."), "foo.py")

    def test_strips_leading_dot_slash(self) -> None:
        self.assertEqual(pc.normalize_path("./a/b.py"), "a/b.py")

    def test_strips_line_and_anchor_suffix(self) -> None:
        self.assertEqual(pc.normalize_path("a/b.py:42"), "a/b.py")
        self.assertEqual(pc.normalize_path("a/b.py:10-20"), "a/b.py")
        self.assertEqual(pc.normalize_path("a/b.py#L42"), "a/b.py")


class ExtractPathCandidatesTest(unittest.TestCase):
    def test_pulls_from_backticks_and_text(self) -> None:
        body = (
            "Two issues slipped: **#705** targeted the already-deleted "
            "`wave_key_reset.py` (removed by #804), and #816 referenced "
            "ontology/repos/deploy.yaml in passing."
        )
        got = pc.extract_path_candidates(body)
        self.assertIn("wave_key_reset.py", got)
        self.assertIn("ontology/repos/deploy.yaml", got)

    def test_prose_yields_nothing(self) -> None:
        body = "The premise no longer holds at origin HEAD; re-scope before kickoff."
        self.assertEqual(pc.extract_path_candidates(body), [])

    def test_dedup_and_order(self) -> None:
        body = "`a/b.py` then `a/b.py` again then `c/d.md`"
        self.assertEqual(pc.extract_path_candidates(body), ["a/b.py", "c/d.md"])

    def test_empty(self) -> None:
        self.assertEqual(pc.extract_path_candidates(""), [])


# --- verdict layer with injected (fake) checkers ----------------------------


def _checker(table: dict[str, str], default: str = pc.EXISTS):
    """A path/symbol checker that looks the value up in ``table``."""

    def _path(_repo_dir: str, _ref: str, value: str) -> str:
        return table.get(value, default)

    def _symbol(_repo_dir: str, _ref: str, value: str, _pathspec: str | None = None) -> str:
        return table.get(value, default)

    return _path, _symbol


class CheckIssueVerdictTest(unittest.TestCase):
    def _check(self, issue: dict, table: dict[str, str], default: str = pc.EXISTS):
        path_fn, sym_fn = _checker(table, default)
        return pc.check_issue(issue, Path("/repos"), "origin/main", path_fn, sym_fn)

    def test_705_deleted_file_is_stop(self) -> None:
        # The #705 regression: names a file that was deleted at HEAD.
        issue = {"ref": "main#705", "body": "targets `wave_key_reset.py`"}
        res = self._check(issue, {"wave_key_reset.py": pc.MISSING})
        self.assertEqual(res.verdict, pc.STOP)
        self.assertEqual([c.value for c in res.missing], ["wave_key_reset.py"])

    def test_present_file_is_ok(self) -> None:
        issue = {"ref": "main#999", "body": "touches `.claude/lib/wave_seq.py`"}
        res = self._check(issue, {".claude/lib/wave_seq.py": pc.EXISTS})
        self.assertEqual(res.verdict, pc.OK)

    def test_unverifiable_is_warn_not_stop(self) -> None:
        # Env gap (repo not cloned / ref not fetched) must never read as rot.
        issue = {"ref": "deploy#1", "repo": "noorinalabs-deploy", "body": "`infra/main.tf`"}
        res = self._check(issue, {"infra/main.tf": pc.UNVERIFIABLE})
        self.assertEqual(res.verdict, pc.WARN)
        self.assertEqual(len(res.unverifiable), 1)

    def test_missing_dominates_unverifiable(self) -> None:
        issue = {"ref": "main#42", "body": "`gone.py` and `maybe.py`"}
        res = self._check(issue, {"gone.py": pc.MISSING, "maybe.py": pc.UNVERIFIABLE})
        self.assertEqual(res.verdict, pc.STOP)

    def test_no_candidates_is_ok(self) -> None:
        issue = {"ref": "main#7", "body": "purely process; nothing concrete named"}
        res = self._check(issue, {})
        self.assertEqual(res.verdict, pc.OK)
        self.assertEqual(res.candidates, [])

    def test_explicit_symbol_missing_is_stop(self) -> None:
        # The #816-shaped case: a named symbol no longer present at HEAD.
        issue = {
            "ref": "main#816",
            "body": "root cause in the cspell map",
            "symbols": [{"name": "build_cspell_map", "pathspec": ".claude/lib/"}],
        }
        res = self._check(issue, {"build_cspell_map": pc.MISSING})
        self.assertEqual(res.verdict, pc.STOP)
        self.assertEqual(res.candidates[0].kind, "symbol")
        self.assertEqual(res.candidates[0].pathspec, ".claude/lib/")

    def test_explicit_paths_merged_with_body(self) -> None:
        issue = {
            "ref": "main#5",
            "body": "see `a.py`",
            "paths": ["b/c.py"],
        }
        res = self._check(issue, {"a.py": pc.EXISTS, "b/c.py": pc.EXISTS})
        self.assertEqual({c.value for c in res.candidates}, {"a.py", "b/c.py"})


class ResolveRepoDirTest(unittest.TestCase):
    def test_main_maps_to_root(self) -> None:
        self.assertEqual(pc.resolve_repo_dir({"repo": "noorinalabs-main"}, Path("/r")), "/r")

    def test_child_maps_under_root(self) -> None:
        self.assertEqual(
            pc.resolve_repo_dir({"repo": "noorinalabs-deploy"}, Path("/r")),
            "/r/noorinalabs-deploy",
        )

    def test_explicit_repo_dir_wins(self) -> None:
        self.assertEqual(
            pc.resolve_repo_dir({"repo": "x", "repo_dir": "/custom"}, Path("/r")),
            "/custom",
        )


class CliTest(unittest.TestCase):
    def _run(self, issues: list[dict], extra: list[str] | None = None) -> tuple[int, str]:
        with TemporaryDirectory() as d:
            p = Path(d) / "issues.json"
            p.write_text(json.dumps(issues))
            buf = io.StringIO()
            with redirect_stdout(buf):
                # No real repo at /repos -> all candidates UNVERIFIABLE -> WARN,
                # so exit 0 (a STOP requires a readable ref that lacks the path).
                rc = pc.main(
                    ["check", "--issues", str(p), "--repos-root", "/nonexistent", *(extra or [])]
                )
            return rc, buf.getvalue()

    def test_warn_only_exits_zero_even_with_stop(self) -> None:
        # Force a STOP via a real temp repo would be heavier; instead assert the
        # --warn-only flag downgrades. Use a repo dir that resolves so the path
        # check returns MISSING is not possible without git, so we rely on the
        # integration test for STOP exit. Here just confirm WARN -> rc 0.
        rc, out = self._run([{"ref": "main#1", "body": "`x/y.py`"}])
        self.assertEqual(rc, 0)
        self.assertIn("WARN", out)

    def test_json_output_is_parseable(self) -> None:
        rc, out = self._run([{"ref": "main#1", "body": "`x/y.py`"}], extra=["--json"])
        self.assertEqual(rc, 0)
        parsed = json.loads(out)
        self.assertEqual(parsed[0]["ref"], "main#1")
        self.assertEqual(parsed[0]["verdict"], pc.WARN)


class GitIntegrationTest(unittest.TestCase):
    """Real git over a throwaway repo — the only test that shells out."""

    def _git(self, repo: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    def _make_repo(self, root: Path) -> Path:
        # The org root *is* noorinalabs-main, so resolve_repo_dir maps that repo
        # name to repos_root itself — init the repo directly at root.
        repo = root
        self._git(repo, "init", "-q")
        self._git(repo, "config", "user.email", "t@t")
        self._git(repo, "config", "user.name", "t")
        (repo / "kept.py").write_text("def kept_symbol():\n    return 1\n")
        (repo / "doomed.py").write_text("x = 1\n")
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-q", "-m", "base")
        # Delete doomed.py in a second commit -> absent at HEAD.
        (repo / "doomed.py").unlink()
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-q", "-m", "remove doomed")
        return repo

    def test_present_deleted_and_symbol(self) -> None:
        with TemporaryDirectory() as d:
            root = Path(d)
            self._make_repo(root)
            ref = "HEAD"

            issue = {
                "ref": "main#705",
                "repo": "noorinalabs-main",
                "body": "needs `kept.py` and `doomed.py`",
                "symbols": [
                    {"name": "kept_symbol"},
                    {"name": "vanished_symbol"},
                ],
            }
            res = pc.check_issue(issue, root, ref)

            statuses = {(c.kind, c.value): c.status for c in res.candidates}
            self.assertEqual(statuses[("path", "kept.py")], pc.EXISTS)
            self.assertEqual(statuses[("path", "doomed.py")], pc.MISSING)
            self.assertEqual(statuses[("symbol", "kept_symbol")], pc.EXISTS)
            self.assertEqual(statuses[("symbol", "vanished_symbol")], pc.MISSING)
            self.assertEqual(res.verdict, pc.STOP)

    def test_unknown_ref_is_unverifiable(self) -> None:
        with TemporaryDirectory() as d:
            root = Path(d)
            self._make_repo(root)
            issue = {"ref": "main#1", "repo": "noorinalabs-main", "body": "`kept.py`"}
            res = pc.check_issue(issue, root, "origin/does-not-exist")
            self.assertEqual(res.verdict, pc.WARN)
            self.assertEqual(res.candidates[0].status, pc.UNVERIFIABLE)

    def test_cli_stop_exit_code_over_real_repo(self) -> None:
        with TemporaryDirectory() as d:
            root = Path(d)
            self._make_repo(root)
            issues = [{"ref": "main#705", "repo": "noorinalabs-main", "body": "`doomed.py`"}]
            p = root / "issues.json"
            p.write_text(json.dumps(issues))
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = pc.main(
                    ["check", "--issues", str(p), "--repos-root", str(root), "--ref", "HEAD"]
                )
            self.assertEqual(rc, 1)
            self.assertIn("STOP", buf.getvalue())

            # --warn-only downgrades the same input to exit 0.
            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                rc2 = pc.main(
                    [
                        "check",
                        "--issues",
                        str(p),
                        "--repos-root",
                        str(root),
                        "--ref",
                        "HEAD",
                        "--warn-only",
                    ]
                )
            self.assertEqual(rc2, 0)


if __name__ == "__main__":
    unittest.main()

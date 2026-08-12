# Git Repository Synchronization

Use this flow before treating a local product or automation clone as current evidence.

It is mandatory for product clones and automation clones alike, including `guides-ui-tests`, `dxml-it-tests`, editor E2E repositories, repository-specific integration suites, and any additional automation repository discovered from Jira, GitHub, environment variables, or local clone discovery.

## Required Command

Run from the skill directory:

```text
python scripts/sync_evidence_repo.py <absolute-repo-path> --stash-dirty
```

The script emits a compact JSON audit. Keep it internal and summarize the result under `Scope From Git`.

## Safe Flow

1. Resolve the Git root and record branch, HEAD SHA, upstream, ahead/behind counts, and porcelain status.
2. Reject an in-progress merge, rebase, cherry-pick, or revert without changing the worktree.
3. Run `git fetch --all --prune --tags`.
4. Reject detached, no-upstream, diverged, or dirty-submodule states without stashing or pulling.
5. When tracked or untracked developer files are dirty, create a unique stash using `git stash push --include-untracked`; never include ignored files.
6. Pull only when behind and not ahead, using `git pull --ff-only`.
7. Keep a successful synchronization stash intact as a safety copy. Do not pop, apply, or drop it automatically.
8. Inspect the synchronized clean worktree at the reported post-sync SHA. If local commits are ahead of upstream, use the verified upstream ref for current-remote claims and treat local commits separately.

## Blocked States

- **Detached HEAD or no upstream**: fetch only; use a verified remote/default ref with `git show`, `git grep`, or a temporary read-only worktree.
- **Diverged branch**: do not merge or rebase; inspect the upstream ref and report divergence.
- **Git operation in progress**: stop and report it; never continue or abort another developer's operation.
- **Dirty submodule**: stop because a superproject stash does not safely preserve nested work.
- **Fetch or pull failure**: do not claim the clone is current. If a stash was created before a failed pull, the script attempts to restore it and retains the stash if restoration cannot be proven safe.

## Required Evidence Record

For every cited clone retain:

- absolute repository path;
- branch and upstream;
- pre-sync and post-sync SHA;
- ahead/behind counts before and after fetch/pull;
- pre-sync and post-sync dirty state;
- fetch and pull outcome;
- inspected worktree or remote ref;
- named stash OID/ref and `git stash apply --index <OID>` restore command when developer work was preserved.

Never reset, merge, rebase, force-checkout, clean ignored files, drop stashes, or resolve conflicts automatically.

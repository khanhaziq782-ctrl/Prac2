# Correcting existing Git commit messages

The source files and repository contents are cleaned up, but commit messages are
stored in Git history. A ZIP archive cannot rename commits already pushed to
GitHub.

Use this only if you are allowed to rewrite the branch history:

```powershell
git checkout <your-branch>
git rebase -i origin/main
```

In the editor, change `pick` to `reword` for each non-conforming commit, then
replace its message with the Conventional Commits format:

```text
feat(config): add command-line configuration
feat(cargo): read package metadata from the Cargo index
feat(graph): build dependency graph using iterative BFS
feat(reverse): add reverse dependency lookup
feat(visualization): export Mermaid and SVG graphs
test: add dependency graph tests
docs: document usage and implementation
```

After checking the result with `git log --oneline`, update the remote branch
only if permitted:

```powershell
git push --force-with-lease
```

If rewriting shared history is not allowed, leave old commits unchanged and
make all new commits follow `type(scope): description`.

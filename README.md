# research-in-a-box

A kit for publishing a research data archive: a contract that describes an
archive package, a local tool (`cruise`) that builds and checks packages, and
an AWS backend, CDK construct and web app that serve them. Fork the repo, edit
one config file and deploy.

## Deploy your archive

1. Fork this repo on GitHub and clone your fork.
2. Open the clone in [Claude Code](https://claude.com/claude-code).
3. Ask it to set up the archive.

The `deploy-archive` skill (`.claude/skills/deploy-archive/`) checks what you need, writes
`archive.yaml` with you, connects GitHub Actions to your AWS account, and has CI deploy it. It
also updates your fork from upstream and tears a stage down.

## Layout

```
packages/
  contract/   Python: archive-contract, the Pydantic models
  tool/       Python: cruise, the local tool
  backend/    Python: the Lambda code
  infra/      TypeScript: the CDK construct (ResearchArchive) and default app
  web/        TypeScript: the React and Vite web app
docs/         specs, plans and user docs
```

Python packages form a uv workspace (`pyproject.toml`); TypeScript packages
form an npm workspace (`package.json`).

## Install cruise

With [uv](https://docs.astral.sh/uv/), at a release tag or the default branch:

```
uv tool install "git+https://github.com/schuettc/research-in-a-box@v0.1.0#subdirectory=packages/tool"
cruise --version
```

Inside a clone, `uv run cruise` runs it.

## Develop

Needs uv, Node 24 and [just](https://just.systems/).

```
uv sync --all-packages
npm ci
just check
```

`just check` runs every format check, lint, type check and test in both
languages, plus the schema drift check.

## License

MIT

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

## Use it from Claude Code

The `research-archive` plugin lets Claude Code find and download data in your
archive, check and fix a dataset package with the archive's own rules, submit
it, and review submissions as a curator. Nothing is written to a manifest or
sent to the archive without your yes. It needs uv. In Claude Code:

```
/plugin marketplace add schuettc/research-in-a-box
/plugin install research-archive@research-in-a-box
```

On Claude Code 2.1.275 or later, one line does both:

```
/plugin install research-archive --marketplace schuettc/research-in-a-box
```

The plugin's MCP server (`archive-mcp`, in `packages/agent`) runs on your own
machine. Its skills, `find-data`, `submit-dataset` and `review-submission`, ask
for your archive's address the first time they need it.

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

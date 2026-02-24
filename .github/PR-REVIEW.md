# PR Review Agent

The [PR Review workflow](.github/workflows/pr-review.yml) runs on every pull request and:

1. **Reviews** the code diff
2. **Runs tests** (`pytest tests/`)
3. **Recommends fixes** via an LLM (OpenAI)

## Setup

1. Add `OPENAI_API_KEY` as a repository secret:
   - Settings → Secrets and variables → Actions → New repository secret
   - Name: `OPENAI_API_KEY`
   - Value: your OpenAI API key

2. Push a PR — the workflow runs automatically and posts a comment.

## Without API Key

If `OPENAI_API_KEY` is not set (e.g. in forks), the workflow still runs tests and posts the test output. The LLM review is skipped.

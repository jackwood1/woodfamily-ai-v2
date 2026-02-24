#!/usr/bin/env python3
"""
PR Review Agent: Analyzes diff + test output, produces review and recommendations.
Run from GitHub Actions; reads diff and test output from files, writes markdown to stdout.
"""

import os
import sys
from pathlib import Path


def main() -> int:
    diff_path = os.environ.get("DIFF_FILE", "pr_diff.txt")
    test_path = os.environ.get("TEST_OUTPUT_FILE", "test_output.txt")
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()

    diff = ""
    if Path(diff_path).exists():
        diff = Path(diff_path).read_text(encoding="utf-8", errors="replace")
    else:
        print("<!-- No diff file found -->", file=sys.stderr)

    test_output = ""
    if Path(test_path).exists():
        test_output = Path(test_path).read_text(encoding="utf-8", errors="replace")
    else:
        print("<!-- No test output file found -->", file=sys.stderr)

    if not diff and not test_output:
        print("## PR Review\n\nNo diff or test output to review.")
        return 0

    if not api_key:
        # No API key (e.g. fork) - output test results only
        markdown = _format_test_only(test_output)
        print(markdown)
        return 0

    markdown = _call_llm_review(diff, test_output, api_key)
    print(markdown)
    return 0


def _format_test_only(test_output: str) -> str:
    """Format test output when LLM is not available."""
    lines = ["## PR Review", ""]
    if test_output:
        lines.append("### Test Results")
        lines.append("```")
        lines.append(test_output[-8000:] if len(test_output) > 8000 else test_output)
        lines.append("```")
    else:
        lines.append("*No test output captured.*")
    return "\n".join(lines)


def _call_llm_review(diff: str, test_output: str, api_key: str) -> str:
    """Call OpenAI to generate review and recommendations."""
    try:
        from openai import OpenAI
    except ImportError:
        return _format_test_only(test_output)

    client = OpenAI(api_key=api_key)

    diff_preview = (diff or "(no diff)")[:12000]
    test_preview = (test_output or "(no test output)")[:6000]

    prompt = f"""You are a code review agent. Analyze this PR and provide a concise review.

## Diff
```
{diff_preview}
```

## Test Output
```
{test_preview}
```

## Your Task
1. **Review**: Summarize the changes and assess code quality, readability, and potential issues.
2. **Tests**: Note if tests passed or failed. If failed, highlight the failures.
3. **Recommendations**: List specific, actionable fixes (with file:line when relevant). Be concise.

Format your response as markdown with these sections:
- ## Summary (1-2 sentences)
- ## Review (bullet points)
- ## Test Status (pass/fail + key failures if any)
- ## Recommended Fixes (numbered list, actionable)
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
        )
        content = resp.choices[0].message.content or ""
        if test_output and "## Test Status" not in content:
            content += f"\n\n## Test Output\n```\n{test_preview[:2000]}\n```"
        return f"## 🤖 PR Review Agent\n\n{content}"
    except Exception as e:
        return _format_test_only(test_output) + f"\n\n*LLM review failed: {e}*"


if __name__ == "__main__":
    sys.exit(main())

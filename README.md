# Prompt Regression Lab

A Python CLI that compares two versions of a Vietnamese support-ticket prompt.
Both prompts run on the same labeled cases and are checked for valid JSON, the
expected fields and types, correct category, and correct urgency.

## Quick start

Python 3.11 is sufficient. There are no third-party dependencies.

```powershell
python lab.py
Get-Content reports/comparison.json -Encoding utf8
```

Demo mode replays simulated outputs. It intentionally produces two regressions
and one improvement to exercise reporting and CI. Changing the prompt text does
not change demo outputs. Demo numbers measure fixture behavior only.

```powershell
python lab.py --fail-on-regression
$LASTEXITCODE
```

Exit 0 means the run completed and the gate did not block it. Exit 1 means the
gate was enabled and at least one baseline pass became a candidate failure.
Exit 2 means invalid configuration or an incomplete run. The gate does not
require every case to pass. GitHub Actions verifies the expected demo regression
IDs and exit status without API credentials.

## Live comparison

Set GROQ_API_KEY in the current PowerShell session. Use public or synthetic
tickets because live mode sends the ticket and prompt to Groq. The report
contains the tickets and model outputs. Do not publish private reports.

```powershell
$groqSecret = Read-Host "Groq API key" -AsSecureString
$env:GROQ_API_KEY = [System.Net.NetworkCredential]::new('', $groqSecret).Password
python lab.py --mode groq --model openai/gpt-oss-120b --output reports/live.json
Remove-Item Env:GROQ_API_KEY
```

Use a model available in your Groq account. The sample run makes 16 API requests.
Temperature zero reduces sampling variation but does not guarantee repeatability.
API errors stop the run rather than recording them as prompt quality failures.
Use distinct report paths across runs to distinguish old and new results.

## Read the report

- **Regression**: passed under the baseline and failed under the candidate.
- **Improvement**: failed under the baseline and passed under the candidate.
- **Stable pass/fail**: the outcome did not change.

Inspect the two raw outputs and error labels for each case. The SHA-256 values
identify the exact prompt and case content used for a run.

## Make it yours

Copy v2 to prompts/v3.txt, revise one instruction, and run with
`--mode groq --baseline prompts/v2.txt --candidate prompts/v3.txt`.
Expand the synthetic cases and keep a separate set for final verification.
In your portfolio, record the model, prompt versions, sample size and concrete
failures. Keep demo results and measured live results distinct.

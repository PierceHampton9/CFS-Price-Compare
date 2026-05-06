# CFS Price Compare

Repository/folder name: `CFS-Price-Compare`.

A command-line tool for estimating fair resale prices for donated computers.

Current status: Windows spec detection, initial query building, eBay active-listing search, basic listing condition normalization, standalone price aggregation, report formatting, and config-driven CLI defaults.

## Setup

Requires Python 3.11 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

## Detect Specs

Run this on the computer you want to inspect:

```powershell
pc_pricer detect
```

If Windows says `pc_pricer` is not recognized, use:

```powershell
python -m pc_pricer.cli detect
```

For machine-readable output:

```powershell
pc_pricer detect --json
```

To include the raw Windows hardware data:

```powershell
pc_pricer detect --json --raw
```

## eBay Smoke Test

After setting eBay credentials in your shell, you can manually test active eBay results:

```powershell
pc_pricer ebay-search "ThinkPad X13 Yoga" --limit 5
```

To run a draft active-listing price report from one search query:

```powershell
pc_pricer price-query "ThinkPad X13 Yoga i5-1135G7 16GB" --limit 10
```

`price-query` defaults to pricing against `good` condition listings and filters obvious parts/accessory results. Use `--condition any` only when you want to inspect unfiltered condition results.

To detect the current Windows PC and price it from generated tiered queries:

```powershell
pc_pricer price-detect --limit-per-query 10
```

Search, pricing, and eBay credential-check commands read defaults from `config.yaml`. Command-line flags still win:

```powershell
pc_pricer price-query "ThinkPad X13 Yoga i5-1135G7 16GB" --config config.yaml --condition good --limit 10
```

## Live eBay Validation

Use this checklist when testing real eBay API access on a trusted machine.

Option 1: set credentials for the current PowerShell session:

```powershell
$env:EBAY_CLIENT_ID="your-production-app-id"
$env:EBAY_CLIENT_SECRET="your-production-cert-id"
```

Verify that PowerShell has the variables without printing the secret:

```powershell
if ($env:EBAY_CLIENT_ID) { "EBAY_CLIENT_ID set" }
if ($env:EBAY_CLIENT_SECRET) { "EBAY_CLIENT_SECRET set" }
```

Option 2: create a local `.env` file in the repository root:

```powershell
Copy-Item .env.example .env
```

Then edit `.env`:

```text
EBAY_CLIENT_ID=your-production-app-id
EBAY_CLIENT_SECRET=your-production-cert-id
```

The CLI loads `.env` automatically. Shell variables still win if both are set.

In eBay's developer portal, `EBAY_CLIENT_ID` is usually shown as the App ID or Client ID, and `EBAY_CLIENT_SECRET` is usually shown as the Cert ID or Client Secret. You do not need Dev ID, RuName, refresh token, or a user access token for the current active-listing search flow.

Check credential setup:

```powershell
pc_pricer ebay-check
```

If `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` are set, `ebay-check` requests an OAuth token.

Run a small active-listing search:

```powershell
pc_pricer ebay-search "ThinkPad X13 Yoga" --limit 3
```

Then run a draft report:

```powershell
pc_pricer price-query "ThinkPad X13 Yoga i5-1135G7 16GB" --limit 10
```

For the first live pass, check:

- whether credentials authenticate successfully
- whether titles, prices, shipping, condition, URLs, and locations appear
- whether missing shipping is shown as unknown shipping, not as a total
- whether the query returns obviously wrong models or parts-only listings
- whether the supporting listings look relevant enough for human review

Do not paste real credentials into issues, pull requests, screenshots, logs, or committed files.

## Development

Run tests with:

```powershell
python -m unittest discover -s tests
```

## Local Credentials

Do not commit real API credentials. The eBay source reads credentials from environment variables:

```powershell
EBAY_CLIENT_ID
EBAY_CLIENT_SECRET
```

For live eBay testing, set these in your shell or in a local `.env` file. The program requests an access token automatically. Shell variables override `.env` values.

For the current production eBay API setup, use the Production App ID and Production Cert ID. Sandbox keys require sandbox API endpoints, which this project does not use yet.

`.env.example` is only a safe template for the names to use. Real values must stay out of committed files.

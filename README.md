# CFS Price Compare

Repository/folder name: `CFS-Price-Compare`.

A command-line tool for estimating fair resale prices for donated computers.

Current status: Windows spec detection, initial query building, eBay active-listing search, basic listing condition normalization, standalone price aggregation, and report formatting work.

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
EBAY_ACCESS_TOKEN
```

For now, set these in your shell before live eBay testing. The project does not automatically load `.env` files yet.

`.env.example` is only a safe template for the names to use. Real values must stay out of committed files.

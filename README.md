# CFS Price Compare

Repository/folder name: `CFS-Price-Compare`.

A command-line tool for estimating fair resale prices for donated devices.

Current status: Windows computer spec detection, manual device entry, tiered query building, eBay active-listing search, listing condition normalization, price aggregation, report formatting, and config-driven CLI defaults.

## Windows Release Setup

For normal use on pricing computers, just download the Windows release zip folder and reference the README-QUICKSTART.txt file within to setup and use the program.

## Developer Setup

Requires Python 3.11 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Launch the GUI skeleton during development with:

```powershell
pc_pricer_gui
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

## Price a Device

To price the current Windows PC from detected specs:

```powershell
pc_pricer price-detect --condition good --limit-per-query 10
```

Auto-detection is only for Windows computers. Phones, tablets, monitors, printers, and storage devices are priced by typing the identifying details from a computer that has the program installed.

To price a computer by typing the specs:

```powershell
pc_pricer price-manual --form-factor laptop --brand Lenovo --model "ThinkPad X13 Yoga" --cpu "i5-1135G7" --ram 16 --storage 512 --condition good
```

For desktops, include the specs which may contribute more to value than brand or model names on their own:

```powershell
pc_pricer price-manual --form-factor desktop --brand Dell --model "OptiPlex 7050" --cpu "i5-7500" --ram 16 --storage 256 --condition good
```

Other device examples:

```powershell
pc_pricer price-manual --device-type phone --brand Apple --model "iPhone 13" --storage 128 --carrier unlocked --condition good
pc_pricer price-manual --device-type phone --brand Apple --model "iPhone 13" --variant "Pro Max" --screen-size 6.7 --storage 128 --carrier unlocked --condition good
pc_pricer price-manual --device-type tablet --brand Samsung --model "Galaxy Tab S7" --screen-size 11 --storage 256 --connectivity "Wi-Fi" --condition good
pc_pricer price-manual --device-type tablet --brand Samsung --model "Galaxy Tab S7" --variant FE --screen-size 12.4 --storage 128 --connectivity "Wi-Fi" --condition good
pc_pricer price-manual --device-type monitor --brand Dell --model "U2419H" --size 24 --resolution 1080p --refresh-rate 60Hz --condition good
pc_pricer price-manual --device-type printer --brand Brother --model "HL-L2390DW" --printer-type laser --color mono --condition good
pc_pricer price-manual --device-type storage --brand Samsung --model "970 EVO Plus" --capacity 1TB --drive-type ssd --drive-form-factor m.2 --interface nvme --condition good
```

For phones and tablets, use `--variant` and `--screen-size` when those details distinguish meaningfully different models. The filter excludes obvious variant/screen-size mismatches from comparable listings when those details are provided.

For storage devices, `--drive-form-factor` accepts the internal values `1.8`, `2.5`, `3.5`, `m.2`, and `msata`, plus common aliases like `m2`, `M.2`, `2.5in`, `3.5"`, and `mSATA`.

To test one manually written search query without tiered query building:

```powershell
pc_pricer price-query "ThinkPad X13 Yoga i5-1135G7 16GB" --limit 10
```

For direct non-computer searches, include `--device-type` so the accessory/parts filter uses the right rules:

```powershell
pc_pricer price-query "iPhone 13 128GB unlocked" --device-type phone --limit 10
```

Search, pricing, and eBay credential-check commands read defaults from `config.yaml`. Command-line flags still win:

```powershell
pc_pricer price-query "ThinkPad X13 Yoga i5-1135G7 16GB" --config config.yaml --condition good --limit 10
```

Reports show the estimate, comparable range, sold/asking breakdown, source counts, generated queries, filter counts, confidence flags, pricing limitations, listing warnings, and up to 5 supporting listings. Current eBay pricing uses active asking listings; when no sold listings are available, the report shows the asking median plus a conservative estimate discounted 0-5%.

## eBay Smoke Test

After setting eBay credentials in your shell or local `.env`, you can manually test active eBay results:

```powershell
pc_pricer ebay-search "ThinkPad X13 Yoga" --limit 5
```

## Live eBay Validation

Use this checklist when testing real eBay API access on a trusted machine.

eBay Credentials Note:
For the eBay API setup, use the Production App ID and Production Cert ID. Sandbox keys require sandbox API endpoints, which this project does not use.

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

The CLI loads `.env` automatically. Shell variables take priority if both are set.

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
pc_pricer price-manual --form-factor laptop --brand Lenovo --model "ThinkPad X13 Yoga" --cpu "i5-1135G7" --ram 16 --storage 512 --limit-per-query 5
```

For the first live pass, check:

- whether credentials authenticate successfully
- whether titles, prices, shipping, condition, URLs, and locations appear
- whether missing shipping is shown as unknown shipping, not as a total
- whether high/unknown shipping and non-Canadian locations appear under listing warnings
- whether asking-only reports show both the asking median and conservative estimate
- whether the query returns obviously wrong models or parts-only listings
- whether the supporting listings look relevant enough for human review

Do not paste real credentials into issues, pull requests, screenshots, logs, or committed files.

## Development

Run tests with:

```powershell
python -m unittest discover -s tests
```

Build a Windows release zip from a development machine:

```powershell
.\scripts\build-windows.ps1
```

The build script installs `requirements-build.txt`, runs PyInstaller, copies `config.yaml`, `.env.example`, and `README-QUICKSTART.txt`, then creates a release zip under `dist\`.

Release checklist:

1. Merge the PR to `main`.
2. Run `git switch main` and `git pull --ff-only`.
3. Run `python -m unittest discover -s tests`.
4. Run `.\scripts\build-windows.ps1 -Version <version>`, using the release version you want.
5. Verify `dist\CFS-Price-Compare-v<version>-windows\pc_pricer.exe --help`.
6. Upload only the generated zip from `dist\` to GitHub Releases.
7. Do not upload `.env`, `build/`, or the unzipped release folder.

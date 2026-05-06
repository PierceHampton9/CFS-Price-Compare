CFS Price Compare - Windows Quickstart
======================================

This release is meant for Windows pricing computers. You do not need Python, Git, or developer tools on this computer.

First-time setup
----------------

1. Extract the release zip.
2. Keep the whole extracted folder together. Do not delete the _internal folder.
3. Open PowerShell in the extracted folder.
4. Run:

   .\pc_pricer.exe setup

5. Enter the eBay App ID / Client ID and Cert ID / Client Secret when prompted.
6. Run:

   .\pc_pricer.exe ebay-check

Price a computer by typing specs
--------------------------------

Laptop example:

   .\pc_pricer.exe price-manual --form-factor laptop --brand Lenovo --model "ThinkPad X13 Yoga" --cpu "i5-1135G7" --ram 16 --storage 512 --condition good

Desktop example:

   .\pc_pricer.exe price-manual --form-factor desktop --brand Dell --model "OptiPlex 7050" --cpu "i5-7500" --ram 16 --storage 256 --condition good

Price the current Windows PC
----------------------------

Run this on the computer being inspected:

   .\pc_pricer.exe price-detect --condition good

Sanity-check the report
-----------------------

- Start with Conservative est. when the report is based on active asking listings.
- Check the supporting listings before trusting the number.
- Titles should match the same computer class, generation, CPU range, RAM, storage, and form factor.
- Rerun with better specs if the supporting listings are mostly parts, accessories, wrong models, or wrong form factors.
- Confidence flags are about estimate strength, such as too few comparables or a wide price range.
- Pricing limitations explain what the data can and cannot prove, such as asking-only pricing.
- Listing warnings point out listing-level concerns, such as unknown shipping, high shipping, or non-Canadian locations.
- When shipping or location warnings dominate the supporting listings, use the lower end of the conservative estimate or review more listings manually.

Notes
-----

- The setup command creates a local .env file beside pc_pricer.exe.
- The .env file contains credentials in plaintext. Keep the release folder on trusted pricing computers only.
- config.yaml controls pricing defaults and can be edited without rebuilding the exe.
- Current eBay pricing uses active asking listings. When no sold listings are available, the report shows the asking median plus a conservative estimate discounted 5-10%.

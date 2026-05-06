CFS Price Compare - Windows Quickstart
======================================

This release is meant for Windows pricing computers. You do not need Python, Git, or developer tools on this computer.

First-time setup
----------------

1. Extract the release zip.
2. Keep the whole extracted folder together. Do not delete the _internal folder.
3. Open PowerShell in the extracted folder (into the directory which directly contains pc_pricer.exe).
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

Reading the report (Line-By-Line):
----------------------------------

The price estimate reads as follows...

Conservative est.: <A range of prices which account for asking prices possibly being inflated compared to sold prices>
Asking median:     <The value of the median listing price in the extracted listing set>
Comparable range:  <The range of prices in the exstracted listing set>
Comparables:       <The number of comparable listings extracted>
Query tier:        <Rank which represents the specificity of the query used to extract comparable listings with 1 as best, 3 as worst>
Sources:           <[Source] : [The number of extracted comparable listings from the respective source], ...>
Search results:    <[The number of total comparable listings extracted (raw)], [the number of comparable listings remaining after duplicates where removed]>
Pricing basis:    <An brief explanation of why the given price range isn't the pure median of the set of extracted comparable listings>
Manual specs:    <The list of specs given after being stripped of irrelevant characters>
Queries used:
  <[Query tier]: [Query details such as specs and model]
  ...>
Target condition: <The condition of the device. From best to worst mint (which is essentially new), excellent (like new, probably no visibl damage or hardware decay), good (most used devices, not destroyed but doesn't look or act new), parts (good only for parts or at best very, very short remaining lifespan)>
Filtered out:      <[Number of listings filtered out] [(condition mismatch: [X], parts/accessory listing: [Y])]
Confidence flags: <Reasons for why listings aren't sufficient to provide a confident set of comparisons>
Pricing limits:   Asking prices only; conservative estimate is discounted from active listings
Listing warnings: Unknown shipping on one or more comparables, High shipping on one or more comparables, Non-Canadian location on one or more comparables

Sanity-check the report
-----------------------

- Start with Conservative est. when the report is based on active asking listings.
- Check the supporting listings before trusting the number.
- Titles should match the same computer class, generation, CPU range, RAM, storage, and form factor.
- Ignore the estimate or rerun with better specs if the supporting listings are mostly parts, accessories, wrong models, or wrong form factors.
- Confidence flags are about estimate strength, such as too few comparables or a wide price range.
- Pricing limitations explain what the data can and cannot prove, such as asking-only pricing.
- Listing warnings point out listing-level concerns, such as unknown shipping, high shipping, or non-Canadian locations.
- When shipping or location warnings dominate the supporting listings, use the lower end of the conservative estimate or review more listings manually.

Notes
-----

- The setup command creates a local .env file beside pc_pricer.exe.
- The .env file contains credentials in plaintext. Keep the release folder on trusted pricing computers only.
- config.yaml controls pricing defaults and can be edited without rebuilding the exe.
- Current eBay pricing uses active asking listings. When no sold listings are available, the report shows the asking median plus a conservative estimate discounted 0-5%.

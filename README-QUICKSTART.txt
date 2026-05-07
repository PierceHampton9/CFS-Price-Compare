CFS Price Compare - Windows Quickstart
======================================

This release is meant for Windows pricing computers. You do not need Python, Git, or developer tools on this computer.

The eBay credentials needed for to run the program can be created by registering an "eBay Developer Program" account. Once your account is activated navigate to the "Application Keys" page and create a "Production" keyset. You can apply to be exempt from marketplace deletion requirements as long as you are using the keyset strictly for this program without further functional modifications. You can do this by choosing the "Not Persisting eBay data setting" in the marketplace deletion exemption form.

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

Price a device by typing specs
------------------------------

Laptop example:

   .\pc_pricer.exe price-manual --form-factor laptop --brand Lenovo --model "ThinkPad X13 Yoga" --cpu "i5-1135G7" --ram 16 --storage 512 --condition good

Desktop example:

   .\pc_pricer.exe price-manual --form-factor desktop --brand Dell --model "OptiPlex 7050" --cpu "i5-7500" --ram 16 --storage 256 --condition good

Phone example:

   .\pc_pricer.exe price-manual --device-type phone --brand Apple --model "iPhone 13" --storage 128 --carrier unlocked --condition good

Tablet example:

   .\pc_pricer.exe price-manual --device-type tablet --brand Samsung --model "Galaxy Tab S7" --storage 256 --connectivity "Wi-Fi" --condition good

Monitor example:

   .\pc_pricer.exe price-manual --device-type monitor --brand Dell --model "U2419H" --size 24 --resolution 1080p --refresh-rate 60Hz --condition good

Printer example:

   .\pc_pricer.exe price-manual --device-type printer --brand Brother --model "HL-L2390DW" --printer-type laser --color mono --condition good

Storage example:

   .\pc_pricer.exe price-manual --device-type storage --brand Samsung --model "970 EVO Plus" --capacity 1TB --drive-type ssd --drive-form-factor m.2 --interface nvme --condition good

For storage devices, drive form factor can be 1.8, 2.5, 3.5, m.2, or msata. Common aliases like m2, M.2, 2.5in, 3.5", and mSATA also work.

Price the current Windows PC
----------------------------

Auto-detection is only for Windows computers. Run this on the computer being inspected:

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
Confidence flags: <Indicators which can be used to evaluate the strength of the estimates>
Pricing limits:   <Indicators which explain what limitations exist when evaluating prices>
Listing warnings: <Reasons for why the details of the provided listings might be incomplete>

The supporting listings read as follows...

[x]. [Device information such as brand, model, generation, and hardware]
     Price:     <Total price in CAD> (<Total broken down into item and shipping price, both in CAD>)
     Source:    <What source the listing was found from>
     Status:    <If the listing is sold or asking>
     Condition: <The condition based on our internal grading system> (<Condition based on the sources grading system>)
     Tier:      <The query tier used to extract this listing>
     Query:     <Query details such as spec and model>
     Location:  <Location of the listing>
     URL:       <URL of the listing>

Sanity-check the report
-----------------------

- Start with Conservative estimate range when the report is based on active asking listings.
- Check the supporting listings to confirm they are comparable and contain reasonable information.
- Titles should match the same computer class, generation, CPU range, RAM, storage, and form factor.
- Ignore the estimate or rerun with better specs if the supporting listings are mostly parts, accessories, wrong models, or wrong form factors.
- Confidence flags are about estimate strength, such as too few comparables or a wide price range.
- Pricing limitations explain what the data can and cannot prove, such as asking-only pricing.
- Listing warnings point out listing-level concerns, such as unknown shipping, high shipping, or non-Canadian locations.
- When shipping or location warnings dominate the supporting listings, use the lower end of the conservative estimate or review more listings manually.

Notes
-----

- The setup command creates a local .env file beside pc_pricer.exe.
- The .env file contains credentials in plaintext. Keep the release folder in a trusted place.
- config.yaml controls pricing defaults and can be edited without rebuilding the executable.
- Current eBay pricing uses active asking listings. When no sold listings are available, the report shows the asking median plus a conservative estimate discounted 0-5%.

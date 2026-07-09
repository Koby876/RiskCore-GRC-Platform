RISKCORE GRC PLATFORM v1.5 — UPDATE GUIDE
==========================================

FIRST INSTALL
-------------
1. Extract this zip to any folder (e.g. C:\Users\micha\Downloads\RiskCore)
2. Run: pip install -r requirements.txt
3. Run: py main.py
4. Set your password on first launch.

UPDATING FROM A PREVIOUS VERSION
---------------------------------
YOUR PASSWORD AND DATA ARE IN riskcore.db
DO NOT delete or overwrite that file when updating.

Method 1 — Use the update script (recommended):
  1. Extract the new release to a TEMP folder
  2. Run update_riskcore.bat from the temp folder
  3. Point it to your existing RiskCore folder
  4. Done — your data is preserved

Method 2 — Manual update:
  1. Extract new release to a TEMP folder
  2. From the TEMP folder, copy everything EXCEPT:
       riskcore.db
       riskcore.log
       riskcore.key
       riskcore_apikey.txt
       backups\ folder
  3. Paste into your existing RiskCore folder
  4. Overwrite when prompted — these are code files only

YOUR DATA FILES (never delete these):
  riskcore.db          — all your risks, treatments, password, settings
  riskcore.key         — API key encryption key
  riskcore_apikey.txt  — encrypted API key
  backups\             — your database backups

If you accidentally overwrote riskcore.db:
  Check backups\ folder for the most recent .db backup file.
  Copy it to the RiskCore folder and rename to riskcore.db

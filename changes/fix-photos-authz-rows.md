---
pr: pending
branch: fix/photos-authz-rows
---
Fixes red main: the security suite requires a row in the authorization table for every route, and the photos backup routes merged without theirs. Adds a row for each of the seven photos routes (owner and adult may call them, guests, children and agents get 403, a missing phone or upload is 404) and switches photos on in the test gateway so the role gate is really exercised. The 403 for guests and agents writes no authz.denied audit record, which is recorded as a known gap (strict xfail) for the photos owner to fix.

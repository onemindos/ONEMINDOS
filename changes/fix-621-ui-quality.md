---
pr: pending
branch: fix-621/ui-quality
---
Browser tests follow the merged Home and sign-in work: the sign-in flow opens "Other ways to sign in" before typing the token (passkey-first sign-in), Home's heading no longer carries the role word owner, the signed-out page title may read Welcome to Home OneMind, and the A11Y-5 known finding is deleted because the History table now passes axe.

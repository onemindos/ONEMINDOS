---
pr: pending
branch: fix-621/e2e
---
The golden-path end-to-end test now opens "Other ways to sign in" before it uses the access-token form, because the new sign-in screen folds that section shut when the browser supports passkeys. The test follows the screen; no check was removed or loosened.

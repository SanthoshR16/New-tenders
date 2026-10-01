# Tender decision access

The `/bid` and `/dontbid` pages and their decision/manufacturer APIs require a
member access code. Set these three environment variables in the Render service
settings:

- `DEVELOPER_ACCESS_CODE`
- `KAMAL_SIR_ACCESS_CODE`
- `UDAY_SIR_ACCESS_CODE`

Use a different randomly generated ASCII value of at least 24 characters for
each member. Do not put the values in source control or share a member's code
with anyone else. The matching code determines the recorded name: `Developer`,
`Kamal Sir`, or `Uday Sir`.

Successful sign-in uses an HTTP-only, secure, same-site persistent session
cookie that recognizes the same browser for up to 10 years. Members do not
need to enter the code again for each tender or link in that browser. Clearing
browser cookies, using private browsing, or opening links in a separate
in-app browser may require signing in there too. The signing key is derived
from the three Render environment values, so sessions remain valid across app
restarts while those values stay unchanged. Changing any code signs out all
existing sessions, and all members must sign in again. The app does not need a
paid persistent disk for this access control.

These codes are bearer credentials, not SMS verification: anyone who obtains a
member's code can use that member's identity. The website cannot independently
verify which phone number is opening it. Scanner sync endpoints remain
available to the local automation service and are not protected by member
codes.

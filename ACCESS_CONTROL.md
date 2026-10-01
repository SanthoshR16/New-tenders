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

## Telegram decision notifications

Telegram receives only manager decisions and manufacturer allocations. Tender
documents and new-tender alerts remain on the existing local WhatsApp workflow.
Create a bot with Telegram's `@BotFather`, add it to a private group, and send
`/start@YourBotName` in that group. Run `setup_telegram_bot.py` from the local
project to find the group's chat ID; the script prompts for the bot token
without displaying or saving it. Set the following variables in the Render
service environment:

- `TELEGRAM_BOT_TOKEN`: the token returned by `@BotFather`
- `TELEGRAM_CHAT_ID`: the private group's numeric chat ID

Never add the bot token to source control or send it in chat. Decision
notifications are written to a SQLite outbox with the cloud decision and are
retried on subsequent scanner sync requests if Telegram is temporarily
unavailable. The notification is sent from the cloud when the manager submits
the choice; the local Excel/database update still waits for the scanner PC's
next sync. Render's local filesystem may be ephemeral, so pending cloud actions
and notification retries are only restart-safe when the service uses persistent
storage.

# SMS Setup (Twilio)

Woody can send SMS via Twilio. Receiving SMS is not implemented.

## 1. Create a Twilio account

1. Go to [twilio.com/try-twilio](https://www.twilio.com/try-twilio)
2. Sign up (free trial includes credit)
3. Verify your phone number if prompted

## 2. Get credentials

1. Open [Twilio Console](https://www.twilio.com/console)
2. Note your **Account SID** and **Auth Token**
3. Go to **Phone Numbers → Manage → Buy a number**
4. Buy a number (trial accounts get one free number in some regions)
5. Note the number in E.164 format (e.g. `+14155551234`)

## 3. Add to .env

```bash
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+14155551234
```

## 4. Restart

Restart Woody and the dashboard. The Integrations panel (Settings tab) will show "✓ SMS (Twilio) connected" when configured.

## 5. Use with Woody

Via Telegram or dashboard chat:

- *"Send SMS to +14155551234 saying I'll be there in 10 minutes"*
- *"Text Jane at +12025551234: Meeting moved to 3pm"*

Use E.164 format: `+` + country code + full number (e.g. US: +1 + 10 digits). Avoid 555 numbers—they're often invalid. Woody sends immediately.

## Trial limitations

Twilio trial accounts can only send to verified numbers. Add recipient numbers in the Twilio Console under **Phone Numbers → Manage → Verified Caller IDs**.

To send to any number, upgrade to a paid account.

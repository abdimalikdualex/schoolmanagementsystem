# SMS/STK Push Setup for Results Delivery

This document explains how to set up SMS functionality to send student results via SMS/STK push.

## Features Added

1. **Phone Number Field**: Added `phone_number` field to CustomUser model
2. **SMS Service**: Created SMS service supporting multiple providers:
   - Africa's Talking (Recommended for Kenya/East Africa)
   - Twilio (International)
   - Safaricom API (Kenya)
3. **SMS Sending Views**: 
   - Send results to individual students
   - Send results to all students at once
4. **UI Integration**: Added SMS buttons in the transcript view

## Setup Instructions

### Step 1: Run Database Migration

The phone_number field has been added to the CustomUser model. Run migrations:

```bash
python manage.py makemigrations
python manage.py migrate
```

### Step 2: Configure SMS Provider

Choose one of the following SMS providers and configure it:

#### Option A: Africa's Talking (Recommended for Kenya)

1. Sign up at: https://account.africastalking.com/
2. Create an app and get your API key
3. Set environment variables or add to `settings.py`:

```python
SMS_PROVIDER = 'africas_talking'
AFRICAS_TALKING_API_KEY = 'your_api_key_here'
AFRICAS_TALKING_USERNAME = 'your_username'  # Use 'sandbox' for testing
```

Or set as environment variables:
```bash
export SMS_PROVIDER=africas_talking
export AFRICAS_TALKING_API_KEY=your_api_key_here
export AFRICAS_TALKING_USERNAME=your_username
```

#### Option B: Twilio

1. Sign up at: https://www.twilio.com/
2. Get your Account SID and Auth Token
3. Set environment variables:

```bash
export SMS_PROVIDER=twilio
export TWILIO_ACCOUNT_SID=your_account_sid
export TWILIO_AUTH_TOKEN=your_auth_token
export TWILIO_PHONE_NUMBER=your_twilio_phone_number
```

#### Option C: Safaricom API

1. Register at: https://developer.safaricom.co.ke/
2. Get Consumer Key and Secret
3. Set environment variables:

```bash
export SMS_PROVIDER=safaricom
export SAFARICOM_CONSUMER_KEY=your_consumer_key
export SAFARICOM_CONSUMER_SECRET=your_consumer_secret
export SAFARICOM_SHORTCODE=your_shortcode
```

### Step 3: Add Phone Numbers to Students

1. Go to "Manage Students" in the admin dashboard
2. Edit each student and add their phone number
3. Phone number format: `254712345678` or `0712345678` (will be auto-converted)

### Step 4: Send Results via SMS

1. Navigate to "View Transcripts" page
2. For individual student: Click "Send SMS" button next to each transcript
3. For all students: Click "Send SMS to All Students" button at the top

## SMS Message Format

The SMS will include:
- Student name and registration number
- Top 3 results (if many subjects) or all results
- Total marks and average
- Number of passed subjects
- Pass/Fail status

Example:
```
SCHOOL MANAGEMENT SYSTEM
Results for John Doe
Reg: STU001

1. Mathematics: 85/100 (A)
2. English: 78/100 (B)
3. Physics: 72/100 (B)

Total: 235, Avg: 78.3
Passed: 3/3

Status: PASS
View full transcript online.
```

## Troubleshooting

### "No phone number registered"
- Solution: Add phone number to student profile

### "SMS provider not configured"
- Solution: Set SMS_PROVIDER and required credentials in settings.py or environment variables

### "Invalid phone number format"
- Solution: Ensure phone number is in format: 254712345678 or 0712345678

### SMS not sending
- Check API credentials are correct
- Verify phone number format
- Check SMS provider account balance (if applicable)
- Review server logs for error messages

## Testing

For testing, use Africa's Talking Sandbox:
- Username: `sandbox`
- Use sandbox API key
- Test with phone numbers provided in sandbox dashboard

## Notes

- SMS messages are limited to 160 characters (concise format used)
- Phone numbers are automatically formatted to international format (254XXXXXXXXX)
- SMS sending is logged in NotificationStudent model
- Failed SMS attempts are reported with error messages

## Security

- Never commit API keys to version control
- Use environment variables for sensitive credentials
- Consider using Django's `decouple` or `python-decouple` for managing secrets




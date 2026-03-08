# Email Setup for School Approval Notifications

When a school is approved by the system owner, an email is sent to the school admin. For this to work, you must configure a real SMTP email backend.

## Quick Fix: Configure Email

### Option 1: Gmail (for testing/small deployments)

1. Enable 2-factor authentication on your Gmail account
2. Create an [App Password](https://support.google.com/accounts/answer/185833)
3. Set these environment variables (e.g., in Render Dashboard → Environment):

```
EMAIL_HOST_USER=your-gmail@gmail.com
EMAIL_HOST_PASSWORD=your-16-char-app-password
DEFAULT_FROM_EMAIL=your-gmail@gmail.com
```

### Option 2: SendGrid (recommended for production)

1. Sign up at https://sendgrid.com/
2. Create an API key
3. Set environment variables:

```
EMAIL_HOST=smtp.sendgrid.net
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=your-sendgrid-api-key
EMAIL_PORT=587
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=noreply@yourdomain.com
```

### Option 3: Mailgun

1. Sign up at https://www.mailgun.com/
2. Get SMTP credentials from your domain
3. Set environment variables:

```
EMAIL_HOST=smtp.mailgun.org
EMAIL_HOST_USER=postmaster@your-domain.mailgun.org
EMAIL_HOST_PASSWORD=your-mailgun-password
EMAIL_PORT=587
EMAIL_USE_TLS=True
```

## Without Configuration

If `EMAIL_HOST_USER` is not set, Django uses the **console backend** – emails are printed to the server log only and **never reach the recipient**. The system will show a warning when approving a school: *"School approved, but the email could not be sent."*

## Verify

After setting environment variables, restart your application. When you approve a school, you should see:
- **Success**: "Approval email sent to admin@school.com"
- **Warning**: "Email could not be sent – configure EMAIL_HOST_USER..." (means SMTP is not configured)

# Employee Management App — Email Setup Version

## New features

- Administrator enters username, email, title, and access level.
- The system emails a one-time account-setup link.
- The user creates their own password.
- The user chooses three security questions.
- Forgot-password recovery verifies all three answers.
- Successful recovery signs the user in automatically.
- Employee job title and department are dropdown menus.
- Setup links expire after 24 hours.
- Administrators can resend an unused setup invitation.

## Render environment variables

Keep:
- `DATABASE_URL`
- `SECRET_KEY`

Add:
- `APP_URL` — your full Render URL, such as `https://employee-management-web.onrender.com`
- `RESEND_API_KEY` — your Resend API key
- `FROM_EMAIL` — a sender on your verified domain, such as `Employee App <accounts@yourdomain.com>`

## Important

Resend requires a verified sending domain for normal production sending. If email is not configured,
the application creates the user and displays the setup link in a message so the workflow can still
be tested.

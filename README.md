# Campusly

### Clubs, events, auditions. Your campus, your people. ❤️

Campusly is a club-first event management portal built with Django. It gives campus administrators, club coordinators, and students one colorful place to manage clubs, publish events, review auditions, register attendees, and stay up to date by email.

**Run Campusly locally:** [http://127.0.0.1:8765/](http://127.0.0.1:8765/)

> This is a local development address. It opens on the computer running Django; it is not a public website link.

## What you can do

- Create and manage clubs, teams, events, posters, and reports.
- Give administrators, coordinators, and students separate role-based dashboards.
- Let students apply or audition for clubs, then review applications through the club team.
- Let students register directly for published events without club membership approval.
- Send registration confirmations, club event announcements, event updates, and scheduled reminders by email.
- Send responsive HTML event emails with a plain-text fallback and event details.
- Start with a clean database and create accounts and campus data yourself.

## Roles

| Role | Main capabilities |
| --- | --- |
| **Campus administrator** | Manage campus accounts, roles, clubs, coordinators, events, and reports. |
| **Club administrator** | Manage assigned club details, its team, members, applications, events, and reports. |
| **Coordinator** | Create and update assigned-club events and posters, review auditions, and view attendees. |
| **Student** | Join clubs, apply or audition, browse published events, register, and receive email updates. |

The first account created through student sign-up becomes the campus administrator. Further public sign-ups create student accounts; administrators create coordinator and club-administrator accounts.

## Run locally on Windows

Open PowerShell in the project folder.

### 1. Create and activate the virtual environment

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, allow it for this terminal session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies and prepare the database

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
```

SQLite is used by default, so no separate database server or database password is needed.

### 3. Start the site

```powershell
python manage.py runserver 127.0.0.1:8765
```

Open the single local site: **[http://127.0.0.1:8765/](http://127.0.0.1:8765/)**. Keep the PowerShell window running while using the site. Press `Ctrl+C` in that window to stop Django.

If you do not have a virtual environment yet, the complete command sequence is:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 127.0.0.1:8765
```

## Email notifications

Without SMTP settings, Django prints email content in the server terminal instead of delivering it. To deliver messages through Gmail:

1. Enable 2-Step Verification for the Gmail account you will use to send portal email.
2. Create a Google App Password. Do not use your normal Gmail password, and revoke any app password that has been shared.
3. Create a local environment file and edit it:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

4. Fill in these values in `.env`. Use the same Gmail address for the username and sender, and paste the app password without spaces:

   ```dotenv
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_HOST_USER=your-gmail-address@gmail.com
   EMAIL_HOST_PASSWORD=your-google-app-password
   EMAIL_USE_TLS=True
   EMAIL_USE_SSL=False
   DEFAULT_FROM_EMAIL=your-gmail-address@gmail.com
   SITE_BASE_URL=http://127.0.0.1:8765
   ```

5. Save `.env` and send a test email:

   ```powershell
   python manage.py sendtestemail your-gmail-address@gmail.com
   ```

6. Restart Django after changing `.env`. New event registrations and published event updates send emails immediately.

The event link in local-development email works only on the computer running the local server, while that server is running. To send links that work from phones or other computers, deploy the portal at a publicly reachable HTTPS address and set `SITE_BASE_URL` to that address.

### Event reminders

The reminder command emails active registrants once when a published event is within the next 24 hours:

```powershell
python manage.py send_event_reminders
```

Schedule this command to run regularly (for example, hourly) using Windows Task Scheduler. Configure the same SMTP environment for the scheduled task. If an event is rescheduled, its active registrants become eligible for a new reminder.

## Project checks

```powershell
python manage.py check
python manage.py test portal
python manage.py makemigrations --check --dry-run
```

## Data and configuration safety

- The local SQLite database is `db.sqlite3`; it is created and migrated on your computer and is not included in Git.
- Vercel deployments require a persistent hosted database. Create a PostgreSQL database with a provider such as Neon or Supabase. Put its connection string in your ignored local `.env` as `DATABASE_URL` and run `python manage.py migrate` to create the tables. Add the same connection string as `DATABASE_URL` in the Vercel project's environment variables, set `DEBUG=False`, and redeploy.
- `DEBUG` defaults to `False` on Vercel and `True` for local development. Set `DEBUG=False` explicitly in Vercel as well.
- `.env` contains local settings and credentials. It is ignored by Git; only `.env.example` is intended to be shared.
- Uploaded event posters and generated static files are local runtime data and are excluded from Git.
- This project uses Django's development server for local use. Configure production hosting, HTTPS, a secure `SECRET_KEY`, and restricted `ALLOWED_HOSTS` before deployment.
- On Vercel, Django automatically allows the deployment host from `VERCEL_URL` and the production host from `VERCEL_PROJECT_PRODUCTION_URL`. If using a custom domain, add it to the comma-separated `ALLOWED_HOSTS` environment variable in the Vercel project settings.

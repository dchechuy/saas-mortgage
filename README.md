# saas-mortgage

Reusable Flask-based SaaS foundation for spinning up new internal or customer-facing prototypes quickly.

## Included

- Login and logout
- Dashboard
- User management
- Roles and permissions
- System configuration for LLM models, attributes, and integrations
- Help center backed by markdown docs
- Release notes with manual generation
- Avatar upload and user menu

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Default local URL: `http://127.0.0.1:5011`

Default admin account:

- Username: `admin`
- Password: `Changeme-123`

The app will prompt the admin to change the password after first login.

## Deployment

The repo includes a template `deploy.sh` for the server workflow:

```bash
chmod +x deploy.sh
./deploy.sh
```

What it does:

- creates `.venv` if missing
- installs `requirements.txt`
- runs `flask db upgrade` when a `migrations/` folder exists
- installs the included systemd service file
- reloads and restarts the `saas-mortgage` service

Included production files:

- `deploy.sh`
- `deploy/saas-mortgage.service`
- `wsgi.py`

Before using on a server, update `deploy/saas-mortgage.service` paths and user names to match that server.

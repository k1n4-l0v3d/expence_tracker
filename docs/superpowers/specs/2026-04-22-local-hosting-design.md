# Local Hosting — Design Spec

**Goal:** Allow running the Flask app locally with one command, accessible both on localhost and to other devices on the local network (LAN).

**Architecture:** Minimal changes — update `app.run()` to read host/port/debug from environment variables, add `.env.local` for local config, add `run.sh` as a one-command launcher. Production (Railway + gunicorn) is unaffected.

---

## Changes to `app.py`

Replace the existing `if __name__ == '__main__':` block at the bottom of the file:

```python
if __name__ == '__main__':
    host  = os.getenv('FLASK_HOST', '127.0.0.1')
    port  = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host=host, port=port, debug=debug)
```

- Default host `127.0.0.1` — safe, only localhost sees the server
- Set `FLASK_HOST=0.0.0.0` in `.env.local` to expose to LAN
- `gunicorn` on Railway does not use this block — production is unaffected

---

## New file: `.env.local`

Not committed to git. User creates it manually:

```
DATABASE_URL=postgresql://postgres:PASSWORD@localhost:5432/expense_tracker
SECRET_KEY=any-long-random-string
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
FLASK_DEBUG=false
```

- `FLASK_HOST=0.0.0.0` makes the server reachable from other LAN devices
- `DATABASE_URL` points to the user's existing local PostgreSQL instance

---

## New file: `run.sh`

One-command launcher:

```bash
#!/bin/bash
set -a
source .env.local
set +a
python3 app.py
```

- `set -a` auto-exports all variables from `.env.local` into the shell environment
- Run with: `./run.sh` (after `chmod +x run.sh` once)

---

## `.gitignore` update

Add `.env.local` so local credentials never reach GitHub:

```
.env.local
```

---

## Access URLs after launch

- **Localhost:** `http://localhost:5000`
- **LAN (other devices):** `http://<Mac-IP>:5000`
  - Find Mac IP: `ipconfig getifaddr en0` (Wi-Fi) or System Settings → Wi-Fi → Details

---

## Files

- Modify: `app.py` — last 2 lines (`if __name__ == '__main__':` block)
- Modify: `.gitignore` — add `.env.local`
- Create: `.env.local` — user fills in manually (not committed)
- Create: `run.sh` — launcher script

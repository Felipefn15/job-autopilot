# Deploy on Oracle Cloud Always Free

This deployment keeps the Playwright browser profile, SQLite database, logs, and
results on persistent disk. The application runs in a headed Chromium session
inside Xvfb so the same browser profile can be reused between scheduled runs.

## 1. Create the VM

Create an Ubuntu Ampere A1 VM with 2 OCPUs and 12 GB RAM when Always Free
capacity is available. Keep SSH as the only public inbound service. Port 6080
must not be exposed publicly.

Reserve a static public IP if possible. A stable profile and network location
reduce unnecessary authentication prompts, but do not change LinkedIn's terms
or make automated access undetectable.

## 2. Install Docker

Clone this repository on the VM, then run:

```bash
git clone git@github.com:Felipefn15/job-automation-engine.git
cd job-automation-engine
sudo ./deploy/oci/bootstrap.sh
```

Reconnect your SSH session so the new Docker group membership is active. Then:

```bash
cd ~/job-automation-engine
cp .env.example .env
```

Edit `.env` and supply the AI, SMTP, user, and deployment values. Never commit
that file.

Build the image:

```bash
docker compose build
```

## 3. Create the persistent LinkedIn session

From your computer, open an SSH tunnel:

```bash
ssh -L 6080:127.0.0.1:6080 ubuntu@YOUR_VM_IP
```

In another SSH terminal on the VM, run:

```bash
cd ~/job-automation-engine
docker compose run --rm --service-ports session-setup
```

Open <http://localhost:6080/vnc.html?autoconnect=true> locally and complete the
LinkedIn login and 2FA. The authenticated profile is written to
`runtime-data/playwright_profile` and reused by later runs.

Do not run session setup and the automation simultaneously because Chromium
allows only one process to own a persistent profile.

## 4. Test one bounded execution

Start with dry-run enabled:

```bash
docker compose run --rm -e DRY_RUN=True job-automation
```

Inspect:

```bash
docker compose run --rm job-automation python main.py --stats
cat runtime-data/last_run.json
```

Then run a small live batch:

```bash
docker compose run --rm job-automation
```

## 5. Enable the schedule

The included timer runs at 12:00 and 20:00 UTC, with up to five minutes of
random delay. Adjust `deploy/oci/job-automation.timer` before installation if
you need different times.

```bash
sudo ./deploy/oci/install-timer.sh
systemctl status job-automation.timer
journalctl -u job-automation.service -f
```

To stop scheduled runs:

```bash
sudo systemctl disable --now job-automation.timer
```

## Persistent and secret data

The following files stay below `runtime-data/` and are excluded from Git:

- `playwright_profile/`
- `jobs.db`
- `logs/`
- `application_results.json`
- `last_run.json`

Back up `runtime-data/` while the browser and automation are stopped. Protect
it as sensitive data because the browser profile contains an authenticated
session.

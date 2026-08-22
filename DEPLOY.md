# Deploying pushup_bot to a VM (Oracle Cloud / Google Cloud Always Free)

This covers running the bot on a small Ubuntu VM with the SQLite file
living directly on disk -- the setup discussed for Oracle Cloud's
Always Free ARM instance or Google Cloud's e2-micro Always Free VM.
Both give you a real, persistent Linux box with no time limit, so
this is a one-time setup.

## 1. Get a VM

- **Oracle Cloud**: create an "Always Free" Ampere A1 (ARM) instance,
  Ubuntu image, in the Oracle Cloud console.
- **Google Cloud**: create an `e2-micro` instance (Compute Engine),
  Ubuntu image, in one of the free-tier regions (e.g. `us-central1`).

Either way, note the VM's public IP and make sure you can SSH in.

## 2. SSH in and install prerequisites

```bash
ssh ubuntu@YOUR_VM_IP

sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

## 3. Create a dedicated user (avoid running the bot as root)

```bash
sudo useradd -m -s /bin/bash pushupbot
sudo mkdir -p /opt/pushup_bot
sudo chown pushupbot:pushupbot /opt/pushup_bot
```

## 4. Get the code onto the VM

Easiest is `scp` from your local machine (run this from your own
computer, not the VM):

```bash
scp -r ./pushup_bot/* ubuntu@YOUR_VM_IP:/tmp/pushup_bot_files
```

Then on the VM:

```bash
sudo mv /tmp/pushup_bot_files/* /opt/pushup_bot/
sudo chown -R pushupbot:pushupbot /opt/pushup_bot
```

(If you'd rather use git, push the folder to a private repo and
`git clone` it into `/opt/pushup_bot` as the `pushupbot` user instead.)

## 5. Set up the Python environment

```bash
sudo -u pushupbot bash -c '
  cd /opt/pushup_bot &&
  python3 -m venv venv &&
  venv/bin/pip install -r requirements.txt
'
```

## 6. Configure secrets

```bash
sudo -u pushupbot cp /opt/pushup_bot/.env.example /opt/pushup_bot/.env
sudo -u pushupbot nano /opt/pushup_bot/.env
```

Fill in `DISCORD_TOKEN` (and `GIPHY_API_KEY` if you're using live
gifs -- see README.md for how to get one).

## 7. Install it as a systemd service

```bash
sudo cp /opt/pushup_bot/pushup_bot.service /etc/systemd/system/pushup_bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now pushup_bot
```

## 8. Check it's running

```bash
sudo systemctl status pushup_bot
sudo journalctl -u pushup_bot -f      # live logs, Ctrl+C to stop watching
```

You should see the "pushup_bot is online as ..." log line. From here,
the service:
- starts automatically on every VM reboot
- restarts itself if the process ever crashes
- keeps `pushup_bot.db` on the VM's disk across all of that, since
  nothing about a service restart touches the filesystem

## Updating the bot later

```bash
# copy new files over (scp or git pull), then:
sudo systemctl restart pushup_bot
```

## Uninstalling

```bash
sudo systemctl disable --now pushup_bot
sudo rm /etc/systemd/system/pushup_bot.service
sudo systemctl daemon-reload
```

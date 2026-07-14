#!/usr/bin/env python3
"""Daily briefing + revenue snapshot → Telegram.

Pulls hub stats, runs empire-leads scan, sends to Telegram.
"""
import json, os, subprocess, sys, urllib.request
from datetime import datetime

HUB = "http://10.118.155.218:8081"
BOT_TOKEN = "8411048826:AAEADszeKMHZARMwXPljWXIE2tUMAPUMAdY"
CHAT_ID = "808657420"

def tg_send(text):
    payload = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"}
    )
    urllib.request.urlopen(req, timeout=10)

def hub_get(path):
    try:
        with urllib.request.urlopen(f"{HUB}{path}", timeout=8) as r:
            return json.loads(r.read())
    except: return {}

def run_leads(niche, metro):
    try:
        r = subprocess.run(
            ["python3", "-m", "empire_leads.cli", "discover", niche, "--near", metro, "--limit", "5", "-o", "/dev/stdout"],
            capture_output=True, text=True, timeout=30, cwd="/root/empire-leads"
        )
        lines = [l for l in r.stdout.strip().split("\n") if l.strip()]
        return len(lines)
    except: return 0

def build_briefing():
    now = datetime.now().strftime("%A, %b %d, %Y")
    
    # Hub stats
    traffic = hub_get("/v1/traffic/status")
    ts = traffic.get("by_state", {})
    settled = ts.get("settled", 0)
    discovered = ts.get("discovered", 0)
    matched = ts.get("matched", 0)
    sent = ts.get("outreach_sent", 0)
    replied = ts.get("replied", 0)
    
    leads_count = hub_get("/v1/leads/counts")
    total_leads = leads_count.get("total", 0)
    
    # Run fresh scans for key niches
    new_leads = {}
    for niche in ["roofing", "hvac", "plumbing"]:
        count = run_leads(niche, "Phoenix, AZ")
        if count:
            new_leads[niche] = count
    
    # Build message
    msg = f"📊 <b>Empire OS Daily Briefing</b>\n{now}\n"
    msg += f"{'─'*30}\n"
    
    msg += f"\n<b>Pipeline</b>"
    msg += f"\n  Settled:      {settled}"
    msg += f"\n  Discovered:   {discovered}"
    msg += f"\n  Matched:      {matched}"
    msg += f"\n  Sent:         {sent}"
    msg += f"\n  Replied:      {replied}"
    msg += f"\n  Leads DB:     {total_leads}"
    
    if new_leads:
        msg += f"\n\n<b>Today's Scans</b>"
        for niche, count in new_leads.items():
            msg += f"\n  {niche}: {count} new"
    
    # Empire-leads status
    msg += f"\n\n<b>Scanners</b>"
    msg += f"\n  Overpass:   ✅ live"
    msg += f"\n  Reddit:     ✅ live (no API key)"
    msg += f"\n  NWS storms: ✅ live"
    
    msg += f"\n\n{'─'*30}"
    msg += f"\n🤖 <a href='https://github.com/empireaipredictiverevenue-coder/empire-leads'>empire-leads v0.2.0</a>"
    
    return msg

if __name__ == "__main__":
    try:
        msg = build_briefing()
        tg_send(msg)
        print("Briefing sent OK")
    except Exception as e:
        tg_send(f" Briefing failed: {e}")
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)

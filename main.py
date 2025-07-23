import os
import json
import discord
import random
import asyncio
from discord.ext import commands, tasks
from dotenv import load_dotenv
from threading import Thread
from flask import Flask
from datetime import datetime, timezone
import pytz
import dropbox

# --- Dropbox config ---
DROPBOX_TOKEN = os.getenv("DROPBOX_TOKEN")
DROPBOX_PATH = "/players.json"

def upload_players_dropbox():
    if not DROPBOX_TOKEN:
        print("❌ No DROPBOX_TOKEN found in environment.")
        return
    dbx = dropbox.Dropbox(DROPBOX_TOKEN)
    with open("players.json", "rb") as f:
        dbx.files_upload(f.read(), DROPBOX_PATH, mode=dropbox.files.WriteMode.overwrite)
    print("☁️ players.json uploaded to Dropbox.")

def download_players_dropbox():
    if not DROPBOX_TOKEN:
        print("❌ No DROPBOX_TOKEN found in environment.")
        return
    dbx = dropbox.Dropbox(DROPBOX_TOKEN)
    try:
        md, res = dbx.files_download(DROPBOX_PATH)
        with open("players.json", "wb") as f:
            f.write(res.content)
        print("✅ players.json downloaded from Dropbox.")
    except dropbox.exceptions.ApiError:
        print("🆕 No players.json found on Dropbox. Will create new one on first save.")

# --- Keep-alive Flask server for Render ---
app = Flask('')

@app.route('/')
def home():
    return "MYİKKİ Domon Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- Discord & Global State ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

SAVE_FILE = "players.json"
CONFIG_FILE = "config.json"
STATE_FILE = "state.json"
players = None
config = None

# --- Async lock for scan/capture concurrency ---
scan_lock = asyncio.Lock()
scan_timer_task = None

# --- State management ---
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "active_spawn": False,
        "spawned_domon": None,  # stocke le numéro du DOMON
        "scan_claimed": None,
        "capture_attempted": None,
        "scan_timer_started": None  # iso string
    }

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def reset_state():
    state = {
        "active_spawn": False,
        "spawned_domon": None,
        "scan_claimed": None,
        "capture_attempted": None,
        "scan_timer_started": None
    }
    save_state(state)
    return state

state = load_state()

def get_current_domon():
    if state["spawned_domon"] is not None:
        return next((d for d in DOMON_LIST if d["num"] == state["spawned_domon"]), None)
    return None

def set_spawned_domon(domon):
    state["spawned_domon"] = domon["num"]
    state["active_spawn"] = True
    state["scan_claimed"] = None
    state["capture_attempted"] = None
    state["scan_timer_started"] = None
    save_state(state)

def clear_spawn():
    reset_state()

def claim_scan(user_id):
    state["scan_claimed"] = user_id
    state["capture_attempted"] = None
    state["scan_timer_started"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

def mark_attempt(user_id):
    state["capture_attempted"] = user_id
    save_state(state)

def fail_capture():
    clear_spawn()

def success_capture():
    clear_spawn()

def scan_expired():
    clear_spawn()

def is_scan_expired():
    if not state["scan_timer_started"]:
        return False
    started = datetime.fromisoformat(state["scan_timer_started"])
    now = datetime.now(timezone.utc)
    return (now - started).total_seconds() > 120

def load_players():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_players(players):
    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)
    upload_players_dropbox()

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"spawn_channel_id": None}

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# ------- Liste des 151 DOMON (évolutions incluses) -------
DOMON_LIST = [
    {
        "num": 1, "name": "Craquos", "type": "Structure", "rarity": "Common", "evolution": "Fissuron",
        "description": "Small crack spirit, dwells in old walls.",
        "stats": {"hp": 38, "atk": 10, "def": 8, "spd": 10},
        "moves": [
            {"name": "Wall Slam", "power": 10, "accuracy": 95, "desc": "Slams the wall at the enemy."},
            {"name": "Crack Shot", "power": 8, "accuracy": 100, "desc": "Shoots a fissure at the foe."},
            {"name": "Defensive Curl", "power": 0, "accuracy": 100, "desc": "Boosts defense for one turn."},
            {"name": "Shatter", "power": 14, "accuracy": 80, "desc": "A risky, powerful attack."}
        ]
    },
    {
        "num": 2, "name": "Fissuron", "type": "Structure", "rarity": "Uncommon", "evolution": "Seismorph",
        "description": "Its power shakes the foundations.",
        "stats": {"hp": 45, "atk": 13, "def": 10, "spd": 12},
        "moves": [
            {"name": "Quake Burst", "power": 14, "accuracy": 90, "desc": "A small quake hits the foe."},
            {"name": "Stone Shield", "power": 0, "accuracy": 100, "desc": "Increases defense sharply."},
            {"name": "Crackling Slam", "power": 11, "accuracy": 100, "desc": "Hits with a rumbling blow."},
            {"name": "Seismic Press", "power": 17, "accuracy": 75, "desc": "Crushing attack, low accuracy."}
        ]
    },
    {
        "num": 3, "name": "Seismorph", "type": "Structure", "rarity": "Rare", "evolution": None,
        "description": "The king of structural tremors.",
        "stats": {"hp": 52, "atk": 19, "def": 13, "spd": 14},
        "moves": [
            {"name": "Epic Quake", "power": 22, "accuracy": 85, "desc": "Massive quake rocks the field."},
            {"name": "Steel Guard", "power": 0, "accuracy": 100, "desc": "Raises defense sharply."},
            {"name": "Crush Down", "power": 16, "accuracy": 90, "desc": "Heavy blow lowers foe's defense."},
            {"name": "Rock Avalanche", "power": 15, "accuracy": 95, "desc": "Cascades of debris fall on the enemy."}
        ]
    },
    {
        "num": 4, "name": "Moldina", "type": "Bio-Parasite", "rarity": "Common", "evolution": "Moldarak",
        "description": "Mouldy spores haunt humid corners.",
        "stats": {"hp": 37, "atk": 9, "def": 8, "spd": 11},
        "moves": [
            {"name": "Spore Puff", "power": 9, "accuracy": 100, "desc": "A cloud of spores, may poison."},
            {"name": "Fungal Bite", "power": 8, "accuracy": 95, "desc": "A bite that saps HP."},
            {"name": "Mold Shield", "power": 0, "accuracy": 100, "desc": "Boosts defense for one turn."},
            {"name": "Musty Gust", "power": 11, "accuracy": 90, "desc": "A stinky wind, may reduce speed."}
        ]
    },
    {
        "num": 5, "name": "Moldarak", "type": "Bio-Parasite", "rarity": "Uncommon", "evolution": "Sporusor",
        "description": "Spreads rapidly when ignored.",
        "stats": {"hp": 44, "atk": 13, "def": 11, "spd": 12},
        "moves": [
            {"name": "Toxic Spores", "power": 13, "accuracy": 95, "desc": "May poison the enemy."},
            {"name": "Rapid Spread", "power": 11, "accuracy": 100, "desc": "Hits quickly, ignores defense boosts."},
            {"name": "Moldy Barrier", "power": 0, "accuracy": 100, "desc": "Absorbs next hit, raises defense."},
            {"name": "Rot Smack", "power": 14, "accuracy": 90, "desc": "Hard hit, may poison."}
        ]
    },
    {
        "num": 6, "name": "Sporusor", "type": "Bio-Parasite", "rarity": "Rare", "evolution": None,
        "description": "Toxic, can corrupt an entire block!",
        "stats": {"hp": 52, "atk": 18, "def": 13, "spd": 14},
        "moves": [
            {"name": "Corrupt Cloud", "power": 19, "accuracy": 90, "desc": "Poisonous gas engulfs the foe."},
            {"name": "Myco Drain", "power": 13, "accuracy": 100, "desc": "Drains enemy's HP."},
            {"name": "Toxic Guard", "power": 0, "accuracy": 100, "desc": "Greatly increases defense."},
            {"name": "Fungal Rage", "power": 20, "accuracy": 85, "desc": "All-out attack, low accuracy."}
        ]
    },
    {
        "num": 7, "name": "Voltus", "type": "Énergie", "rarity": "Common", "evolution": "Voltark",
        "description": "Loves electric wires, flickers the lights.",
        "stats": {"hp": 36, "atk": 11, "def": 8, "spd": 13},
        "moves": [
            {"name": "Zap", "power": 10, "accuracy": 95, "desc": "Sends a shock at the enemy."},
            {"name": "Short Circuit", "power": 7, "accuracy": 100, "desc": "Disrupts foe's attack (may lower atk)."},
            {"name": "Static Field", "power": 0, "accuracy": 100, "desc": "Boosts defense, may paralyze."},
            {"name": "Flicker Strike", "power": 12, "accuracy": 85, "desc": "Quick, but not always reliable."}
        ]
    },
    {
        "num": 8, "name": "Voltark", "type": "Énergie", "rarity": "Uncommon", "evolution": "Voltaura",
        "description": "Grows strong near overloaded panels.",
        "stats": {"hp": 42, "atk": 14, "def": 9, "spd": 14},
        "moves": [
            {"name": "Overload", "power": 13, "accuracy": 90, "desc": "Electric surge, may paralyze."},
            {"name": "Power Drain", "power": 10, "accuracy": 100, "desc": "Drains foe's energy."},
            {"name": "Amp Guard", "power": 0, "accuracy": 100, "desc": "Raises defense for 2 turns."},
            {"name": "Spark Burst", "power": 15, "accuracy": 85, "desc": "A sudden, strong jolt."}
        ]
    },
    {
        "num": 9, "name": "Voltaura", "type": "Énergie", "rarity": "Rare", "evolution": None,
        "description": "Can short-circuit an entire building.",
        "stats": {"hp": 49, "atk": 18, "def": 12, "spd": 16},
        "moves": [
            {"name": "Short Circuit", "power": 17, "accuracy": 85, "desc": "Massive surge, can paralyze."},
            {"name": "Electric Veil", "power": 0, "accuracy": 100, "desc": "Shields with electricity, raises defense."},
            {"name": "Thunder Crash", "power": 19, "accuracy": 80, "desc": "Huge power, but risky."},
            {"name": "Static Pulse", "power": 13, "accuracy": 95, "desc": "Paralyzes if it hits twice in a row."}
        ]
    },
    {
        "num": 10, "name": "Widowra", "type": "Spectre", "rarity": "Uncommon", "evolution": "Widowhex",
        "description": "Restless soul of a past owner.",
        "stats": {"hp": 37, "atk": 10, "def": 11, "spd": 13},
        "moves": [
            {"name": "Ghost Grip", "power": 12, "accuracy": 95, "desc": "Icy hands grip the foe."},
            {"name": "Spirit Veil", "power": 0, "accuracy": 100, "desc": "Raises defense for one turn."},
            {"name": "Whisper Strike", "power": 9, "accuracy": 100, "desc": "A quick haunting hit."},
            {"name": "Haunting Scream", "power": 15, "accuracy": 80, "desc": "Terrifies the foe, may lower defense."}
        ]
    },
    {
        "num": 11, "name": "Widowhex", "type": "Spectre", "rarity": "Rare", "evolution": None,
        "description": "Haunts corridors during renovations.",
        "stats": {"hp": 44, "atk": 15, "def": 13, "spd": 14},
        "moves": [
            {"name": "Eerie Wail", "power": 16, "accuracy": 85, "desc": "A bone-chilling shriek."},
            {"name": "Spectral Wall", "power": 0, "accuracy": 100, "desc": "Greatly boosts defense."},
            {"name": "Phantom Slash", "power": 12, "accuracy": 95, "desc": "Slashes with ghostly claws."},
            {"name": "Nightmare", "power": 18, "accuracy": 80, "desc": "May put the foe to sleep."}
        ]
    },
    {
        "num": 12, "name": "BIMbug", "type": "Numérique", "rarity": "Common", "evolution": "BIMphage",
        "description": "Digital glitch in the building's blueprint.",
        "stats": {"hp": 34, "atk": 10, "def": 7, "spd": 14},
        "moves": [
            {"name": "Bug Byte", "power": 9, "accuracy": 100, "desc": "Digital gnawing attack."},
            {"name": "Glitch Wave", "power": 8, "accuracy": 95, "desc": "Sends corrupt data to foe."},
            {"name": "Error Shield", "power": 0, "accuracy": 100, "desc": "Raises defense, avoids crits."},
            {"name": "Pixel Jam", "power": 12, "accuracy": 85, "desc": "Overloads the enemy."}
        ]
    },
    {
        "num": 13, "name": "BIMphage", "type": "Numérique", "rarity": "Uncommon", "evolution": "BIMgeist",
        "description": "Eats away at data models.",
        "stats": {"hp": 39, "atk": 13, "def": 8, "spd": 15},
        "moves": [
            {"name": "Data Drain", "power": 12, "accuracy": 100, "desc": "Siphons HP as data."},
            {"name": "Code Shield", "power": 0, "accuracy": 100, "desc": "Avoids one attack, raises defense."},
            {"name": "Bitstorm", "power": 14, "accuracy": 90, "desc": "Hits with a flurry of bits."},
            {"name": "System Crash", "power": 16, "accuracy": 80, "desc": "Chance to stun the enemy."}
        ]
    },
    {
        "num": 14, "name": "BIMgeist", "type": "Numérique", "rarity": "Rare", "evolution": None,
        "description": "Causes plans to vanish mysteriously.",
        "stats": {"hp": 45, "atk": 17, "def": 11, "spd": 17},
        "moves": [
            {"name": "Vanishing Code", "power": 18, "accuracy": 85, "desc": "Attack that may disable moves."},
            {"name": "Data Cloak", "power": 0, "accuracy": 100, "desc": "Boosts defense and evasion."},
            {"name": "Blueprint Break", "power": 14, "accuracy": 95, "desc": "Destroys enemy plans."},
            {"name": "Glitch Blast", "power": 19, "accuracy": 80, "desc": "Massive digital attack."}
        ]
    },
     {
        "num": 15, "name": "Humidon", "type": "Climat", "rarity": "Common", "evolution": "Humistorm",
        "description": "Dampens rooms with chilly mist.",
        "stats": {"hp": 39, "atk": 9, "def": 9, "spd": 12},
        "moves": [
            {"name": "Mist Spray", "power": 9, "accuracy": 100, "desc": "Blinds foe with cold mist."},
            {"name": "Chill Touch", "power": 10, "accuracy": 95, "desc": "Saps some attack power."},
            {"name": "Condense", "power": 0, "accuracy": 100, "desc": "Raises defense with damp air."},
            {"name": "Humidity Pulse", "power": 13, "accuracy": 90, "desc": "A sudden burst of moist air."}
        ]
    },
    {
        "num": 16, "name": "Humistorm", "type": "Climat", "rarity": "Uncommon", "evolution": "Humicrypt",
        "description": "Makes paint peel from the walls.",
        "stats": {"hp": 44, "atk": 13, "def": 10, "spd": 13},
        "moves": [
            {"name": "Storm Surge", "power": 14, "accuracy": 90, "desc": "Hits all enemies with damp storm."},
            {"name": "Soak", "power": 10, "accuracy": 100, "desc": "Reduces foe's defense."},
            {"name": "Rain Veil", "power": 0, "accuracy": 100, "desc": "Protects with a veil of water."},
            {"name": "Peel Blast", "power": 15, "accuracy": 85, "desc": "Blasts paint chips at foe."}
        ]
    },
    {
        "num": 17, "name": "Humicrypt", "type": "Climat", "rarity": "Rare", "evolution": None,
        "description": "Turns entire homes into wet tombs.",
        "stats": {"hp": 52, "atk": 16, "def": 13, "spd": 15},
        "moves": [
            {"name": "Tomb Mist", "power": 17, "accuracy": 90, "desc": "Drains HP with cryptic fog."},
            {"name": "Flood Wall", "power": 0, "accuracy": 100, "desc": "Doubles defense for 1 turn."},
            {"name": "Waterlogged", "power": 15, "accuracy": 95, "desc": "Slows and damages foe."},
            {"name": "Seepage", "power": 20, "accuracy": 80, "desc": "Strong attack, low accuracy."}
        ]
    },
    {
        "num": 18, "name": "Crackmite", "type": "Structure", "rarity": "Common", "evolution": "Crumblex",
        "description": "Microscopic crack-maker.",
        "stats": {"hp": 35, "atk": 11, "def": 8, "spd": 14},
        "moves": [
            {"name": "Tiny Fissure", "power": 9, "accuracy": 100, "desc": "Creates a small crack in foe."},
            {"name": "Micro Bite", "power": 8, "accuracy": 95, "desc": "Fast, tiny attack."},
            {"name": "Hide in Wall", "power": 0, "accuracy": 100, "desc": "Raises defense by burrowing."},
            {"name": "Crackle Rush", "power": 13, "accuracy": 85, "desc": "Quick multi-hit attack."}
        ]
    },
    {
        "num": 19, "name": "Crumblex", "type": "Structure", "rarity": "Uncommon", "evolution": None,
        "description": "Causes tiles to snap underfoot.",
        "stats": {"hp": 42, "atk": 14, "def": 10, "spd": 13},
        "moves": [
            {"name": "Tile Snap", "power": 14, "accuracy": 95, "desc": "Can break the foe's defense."},
            {"name": "Ground Shake", "power": 11, "accuracy": 100, "desc": "Affects all foes slightly."},
            {"name": "Fortify", "power": 0, "accuracy": 100, "desc": "Boosts own defense."},
            {"name": "Dust Cloud", "power": 13, "accuracy": 90, "desc": "Reduces foe's accuracy."}
        ]
    },
    {
        "num": 20, "name": "Mycosor", "type": "Bio-Parasite", "rarity": "Uncommon", "evolution": None,
        "description": "Mould roots as tough as concrete.",
        "stats": {"hp": 41, "atk": 12, "def": 12, "spd": 12},
        "moves": [
            {"name": "Root Whip", "power": 13, "accuracy": 95, "desc": "Strikes with strong roots."},
            {"name": "Fungal Armor", "power": 0, "accuracy": 100, "desc": "Greatly boosts defense."},
            {"name": "Parasite Lash", "power": 10, "accuracy": 100, "desc": "Saps a little HP."},
            {"name": "Spore Flare", "power": 15, "accuracy": 85, "desc": "Chance to paralyze."}
        ]
    },
    {
        "num": 21, "name": "Cablon", "type": "Énergie", "rarity": "Common", "evolution": "Cablast",
        "description": "Bites through any cable.",
        "stats": {"hp": 37, "atk": 12, "def": 8, "spd": 13},
        "moves": [
            {"name": "Cable Bite", "power": 10, "accuracy": 100, "desc": "Hits foe with a bite."},
            {"name": "Spark Snap", "power": 9, "accuracy": 95, "desc": "May paralyze enemy."},
            {"name": "Wire Wrap", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Power Chew", "power": 13, "accuracy": 85, "desc": "Strong bite, but risky."}
        ]
    },
    {
        "num": 22, "name": "Cablast", "type": "Énergie", "rarity": "Uncommon", "evolution": None,
        "description": "Sparks fly in its wake.",
        "stats": {"hp": 42, "atk": 15, "def": 10, "spd": 14},
        "moves": [
            {"name": "Blast Spark", "power": 13, "accuracy": 95, "desc": "A surge of electricity."},
            {"name": "Live Wire", "power": 12, "accuracy": 100, "desc": "May lower foe's defense."},
            {"name": "Power Shell", "power": 0, "accuracy": 100, "desc": "Boosts defense for 2 turns."},
            {"name": "Shockwave", "power": 15, "accuracy": 85, "desc": "All-out electric attack."}
        ]
    },
    {
        "num": 23, "name": "Echoz", "type": "Spectre", "rarity": "Common", "evolution": "Echomire",
        "description": "Leaves behind whispers and chills.",
        "stats": {"hp": 35, "atk": 10, "def": 9, "spd": 13},
        "moves": [
            {"name": "Echo Hit", "power": 9, "accuracy": 100, "desc": "Hits with echoing force."},
            {"name": "Haunt", "power": 11, "accuracy": 95, "desc": "May lower enemy's defense."},
            {"name": "Chill Veil", "power": 0, "accuracy": 100, "desc": "Boosts defense."},
            {"name": "Spectral Pulse", "power": 14, "accuracy": 90, "desc": "Strong spectral attack."}
        ]
    },
    {
        "num": 24, "name": "Echomire", "type": "Spectre", "rarity": "Uncommon", "evolution": None,
        "description": "Makes every noise seem haunted.",
        "stats": {"hp": 42, "atk": 13, "def": 11, "spd": 15},
        "moves": [
            {"name": "Haunted Blast", "power": 13, "accuracy": 95, "desc": "A ghostly explosion."},
            {"name": "Wail", "power": 12, "accuracy": 100, "desc": "Lowers foe's attack stat."},
            {"name": "Night Shroud", "power": 0, "accuracy": 100, "desc": "Boosts defense and evasion."},
            {"name": "Echo Storm", "power": 16, "accuracy": 85, "desc": "Loud, multi-hit attack."}
        ]
    },
    {
        "num": 25, "name": "Glitchum", "type": "Numérique", "rarity": "Common", "evolution": "Glitchurn",
        "description": "Digital static entity.",
        "stats": {"hp": 34, "atk": 10, "def": 8, "spd": 14},
        "moves": [
            {"name": "Static Jab", "power": 9, "accuracy": 100, "desc": "Jabs with digital static."},
            {"name": "Code Glitch", "power": 8, "accuracy": 95, "desc": "Causes random effects."},
            {"name": "Firewall", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Data Surge", "power": 13, "accuracy": 85, "desc": "Powerful but risky."}
        ]
    },
    {
        "num": 26, "name": "Glitchurn", "type": "Numérique", "rarity": "Uncommon", "evolution": None,
        "description": "Causes screens to flicker.",
        "stats": {"hp": 40, "atk": 12, "def": 9, "spd": 15},
        "moves": [
            {"name": "Flicker Hit", "power": 12, "accuracy": 95, "desc": "May reduce foe's accuracy."},
            {"name": "System Error", "power": 10, "accuracy": 100, "desc": "Chance to confuse."},
            {"name": "Data Guard", "power": 0, "accuracy": 100, "desc": "Boosts defense and accuracy."},
            {"name": "Crash Loop", "power": 14, "accuracy": 85, "desc": "Powerful digital attack."}
        ]
    },
    {
        "num": 27, "name": "Condensaur", "type": "Climat", "rarity": "Common", "evolution": "Condenshade",
        "description": "Brings indoor rain.",
        "stats": {"hp": 37, "atk": 10, "def": 9, "spd": 12},
        "moves": [
            {"name": "Rain Drop", "power": 9, "accuracy": 100, "desc": "Hits with falling water."},
            {"name": "Humidity Burst", "power": 11, "accuracy": 95, "desc": "May reduce foe's defense."},
            {"name": "Misty Veil", "power": 0, "accuracy": 100, "desc": "Boosts defense by dampening."},
            {"name": "Flood Attack", "power": 13, "accuracy": 90, "desc": "May confuse enemy."}
        ]
    },
    {
        "num": 28, "name": "Condenshade", "type": "Climat", "rarity": "Rare", "evolution": None,
        "description": "Causes mysterious puddles everywhere.",
        "stats": {"hp": 46, "atk": 14, "def": 11, "spd": 13},
        "moves": [
            {"name": "Puddle Trap", "power": 15, "accuracy": 95, "desc": "Slows foe for next turn."},
            {"name": "Drench", "power": 14, "accuracy": 100, "desc": "Heavy soaking attack."},
            {"name": "Slipstream", "power": 0, "accuracy": 100, "desc": "Boosts own speed."},
            {"name": "Steam Cloud", "power": 16, "accuracy": 85, "desc": "Obscures foe's vision."}
        ]
    },
    {
        "num": 29, "name": "Rotophan", "type": "Structure", "rarity": "Uncommon", "evolution": None,
        "description": "Rusts any metal structure.",
        "stats": {"hp": 43, "atk": 13, "def": 12, "spd": 10},
        "moves": [
            {"name": "Rust Flake", "power": 12, "accuracy": 95, "desc": "May lower foe's defense."},
            {"name": "Corrode", "power": 14, "accuracy": 90, "desc": "A heavy, damaging attack."},
            {"name": "Metal Guard", "power": 0, "accuracy": 100, "desc": "Raises defense a lot."},
            {"name": "Rot Storm", "power": 13, "accuracy": 85, "desc": "Hits with a storm of rust."}
        ]
    },
    {
        "num": 30, "name": "Smolder", "type": "Énergie", "rarity": "Rare", "evolution": None,
        "description": "Hidden fire risk, burns unseen.",
        "stats": {"hp": 47, "atk": 16, "def": 10, "spd": 16},
        "moves": [
            {"name": "Smolder Strike", "power": 16, "accuracy": 95, "desc": "A powerful burning hit."},
            {"name": "Burn Veil", "power": 0, "accuracy": 100, "desc": "Boosts defense for 2 turns."},
            {"name": "Fire Flicker", "power": 14, "accuracy": 100, "desc": "Quick fire attack."},
            {"name": "Blaze Up", "power": 18, "accuracy": 80, "desc": "Very strong, but risky."}
        ]
    },
      {
        "num": 31, "name": "Drafton", "type": "Climat", "rarity": "Common", "evolution": "Drafterror",
        "description": "Summons sudden cold drafts.",
        "stats": {"hp": 36, "atk": 11, "def": 8, "spd": 15},
        "moves": [
            {"name": "Cold Draft", "power": 10, "accuracy": 100, "desc": "Hits foe with cold air."},
            {"name": "Whistling Wind", "power": 11, "accuracy": 95, "desc": "May lower foe's speed."},
            {"name": "Air Shield", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Shiver Blast", "power": 13, "accuracy": 90, "desc": "High chance to chill."}
        ]
    },
    {
        "num": 32, "name": "Drafterror", "type": "Climat", "rarity": "Uncommon", "evolution": None,
        "description": "Slams doors at random times.",
        "stats": {"hp": 44, "atk": 13, "def": 12, "spd": 15},
        "moves": [
            {"name": "Door Slam", "power": 14, "accuracy": 95, "desc": "Hits hard, can stun foe."},
            {"name": "Sudden Gust", "power": 12, "accuracy": 100, "desc": "Knocks enemy back."},
            {"name": "Draft Armor", "power": 0, "accuracy": 100, "desc": "Boosts own defense."},
            {"name": "Wind Howl", "power": 16, "accuracy": 85, "desc": "Loud multi-hit attack."}
        ]
    },
    {
        "num": 33, "name": "Spookbyte", "type": "Spectre", "rarity": "Common", "evolution": "Spookraft",
        "description": "Digital ghost in surveillance cams.",
        "stats": {"hp": 34, "atk": 10, "def": 9, "spd": 15},
        "moves": [
            {"name": "Phantom Shock", "power": 9, "accuracy": 100, "desc": "Frightens foe with static."},
            {"name": "Cam Flicker", "power": 11, "accuracy": 95, "desc": "May lower foe's accuracy."},
            {"name": "Specter Veil", "power": 0, "accuracy": 100, "desc": "Boosts evasion."},
            {"name": "Pixel Curse", "power": 14, "accuracy": 90, "desc": "Curse of corrupted data."}
        ]
    },
    {
        "num": 34, "name": "Spookraft", "type": "Spectre", "rarity": "Rare", "evolution": None,
        "description": "Freezes all camera feeds.",
        "stats": {"hp": 44, "atk": 13, "def": 10, "spd": 17},
        "moves": [
            {"name": "Freeze Frame", "power": 15, "accuracy": 95, "desc": "May paralyze foe."},
            {"name": "Ghost Glitch", "power": 13, "accuracy": 100, "desc": "Unpredictable effects."},
            {"name": "Nightmare Lens", "power": 0, "accuracy": 100, "desc": "Boosts critical rate."},
            {"name": "Surveillance Swarm", "power": 18, "accuracy": 85, "desc": "Heavy, multi-hit attack."}
        ]
    },
    {
        "num": 35, "name": "Netflux", "type": "Numérique", "rarity": "Common", "evolution": "Netfreak",
        "description": "Interferes with WiFi signals.",
        "stats": {"hp": 36, "atk": 10, "def": 8, "spd": 13},
        "moves": [
            {"name": "WiFi Jam", "power": 10, "accuracy": 100, "desc": "Reduces enemy speed."},
            {"name": "Signal Crash", "power": 12, "accuracy": 95, "desc": "Can confuse foe."},
            {"name": "Data Shield", "power": 0, "accuracy": 100, "desc": "Boosts defense and accuracy."},
            {"name": "Packet Burst", "power": 14, "accuracy": 90, "desc": "Powerful digital strike."}
        ]
    },
    {
        "num": 36, "name": "Netfreak", "type": "Numérique", "rarity": "Uncommon", "evolution": None,
        "description": "Blocks all remote connections.",
        "stats": {"hp": 42, "atk": 14, "def": 9, "spd": 15},
        "moves": [
            {"name": "Firewall Lock", "power": 13, "accuracy": 95, "desc": "Can block foe's next attack."},
            {"name": "Network Snarl", "power": 13, "accuracy": 100, "desc": "Heavy hit, may confuse."},
            {"name": "Code Cloak", "power": 0, "accuracy": 100, "desc": "Raises defense and evasion."},
            {"name": "Total Blackout", "power": 16, "accuracy": 85, "desc": "Crippling, high-risk attack."}
        ]
    },
    {
        "num": 37, "name": "Thermora", "type": "Climat", "rarity": "Common", "evolution": "Thermogone",
        "description": "Shifts temperatures at random.",
        "stats": {"hp": 38, "atk": 10, "def": 9, "spd": 12},
        "moves": [
            {"name": "Heat Wave", "power": 11, "accuracy": 100, "desc": "May burn foe."},
            {"name": "Cold Snap", "power": 10, "accuracy": 95, "desc": "May freeze foe."},
            {"name": "Tempest Guard", "power": 0, "accuracy": 100, "desc": "Raises defense by 2."},
            {"name": "Thermo Blast", "power": 14, "accuracy": 90, "desc": "Unleashes temperature chaos."}
        ]
    },
    {
        "num": 38, "name": "Thermogone", "type": "Climat", "rarity": "Rare", "evolution": None,
        "description": "Causes heating bills to explode.",
        "stats": {"hp": 46, "atk": 16, "def": 10, "spd": 15},
        "moves": [
            {"name": "Bill Shock", "power": 17, "accuracy": 90, "desc": "Heavy energy drain."},
            {"name": "Thermal Crash", "power": 13, "accuracy": 100, "desc": "Damages both sides a bit."},
            {"name": "Overheat", "power": 0, "accuracy": 100, "desc": "Boosts attack, lowers defense."},
            {"name": "Winter Burst", "power": 14, "accuracy": 85, "desc": "Freezes foe, low accuracy."}
        ]
    },
    {
        "num": 39, "name": "Crustorn", "type": "Structure", "rarity": "Rare", "evolution": None,
        "description": "Turns bricks into fragile shells.",
        "stats": {"hp": 48, "atk": 14, "def": 15, "spd": 11},
        "moves": [
            {"name": "Shell Smash", "power": 16, "accuracy": 95, "desc": "Lowers foe's defense."},
            {"name": "Brick Blast", "power": 15, "accuracy": 100, "desc": "A strong physical hit."},
            {"name": "Reinforce", "power": 0, "accuracy": 100, "desc": "Greatly boosts own defense."},
            {"name": "Crumble Down", "power": 18, "accuracy": 80, "desc": "Heavy damage, low accuracy."}
        ]
    },
    {
        "num": 40, "name": "Surgebite", "type": "Énergie", "rarity": "Common", "evolution": "Surgerage",
        "description": "Causes sudden power spikes.",
        "stats": {"hp": 36, "atk": 11, "def": 8, "spd": 14},
        "moves": [
            {"name": "Power Surge", "power": 11, "accuracy": 100, "desc": "May paralyze enemy."},
            {"name": "Voltage Snap", "power": 10, "accuracy": 95, "desc": "Fast and accurate."},
            {"name": "Static Shield", "power": 0, "accuracy": 100, "desc": "Boosts defense by 1."},
            {"name": "Fuse Burn", "power": 15, "accuracy": 90, "desc": "Burns foe's attack stat."}
        ]
    },
    {
        "num": 41, "name": "Surgerage", "type": "Énergie", "rarity": "Uncommon", "evolution": None,
        "description": "Melts fuses with rage.",
        "stats": {"hp": 42, "atk": 14, "def": 11, "spd": 15},
        "moves": [
            {"name": "Rage Strike", "power": 14, "accuracy": 95, "desc": "Critical hit possible."},
            {"name": "Overcharge", "power": 12, "accuracy": 100, "desc": "May boost own attack."},
            {"name": "Shockwave", "power": 0, "accuracy": 100, "desc": "Raises own speed."},
            {"name": "Meltdown", "power": 17, "accuracy": 85, "desc": "High power, may self-hurt."}
        ]
    },
    {
        "num": 42, "name": "Airspectra", "type": "Climat", "rarity": "Uncommon", "evolution": None,
        "description": "Haunts air vents and ducts.",
        "stats": {"hp": 38, "atk": 13, "def": 10, "spd": 17},
        "moves": [
            {"name": "Vent Slash", "power": 12, "accuracy": 95, "desc": "Hits through defense."},
            {"name": "Spectral Breeze", "power": 13, "accuracy": 100, "desc": "May confuse foe."},
            {"name": "Air Cloak", "power": 0, "accuracy": 100, "desc": "Evasion up for 2 turns."},
            {"name": "Haunted Wind", "power": 16, "accuracy": 85, "desc": "Heavy ghostly gust."}
        ]
    },
    {
        "num": 43, "name": "Funglint", "type": "Bio-Parasite", "rarity": "Common", "evolution": "Fungloom",
        "description": "Shiny mold with a bad attitude.",
        "stats": {"hp": 37, "atk": 11, "def": 9, "spd": 12},
        "moves": [
            {"name": "Spore Flash", "power": 9, "accuracy": 100, "desc": "Can stun the foe."},
            {"name": "Mold Shield", "power": 0, "accuracy": 100, "desc": "Raises defense."},
            {"name": "Fungal Burst", "power": 12, "accuracy": 95, "desc": "Hits all enemies a little."},
            {"name": "Lichen Lash", "power": 14, "accuracy": 90, "desc": "Poisons foe sometimes."}
        ]
    },
    {
        "num": 44, "name": "Fungloom", "type": "Bio-Parasite", "rarity": "Rare", "evolution": None,
        "description": "Can darken a whole attic.",
        "stats": {"hp": 45, "atk": 15, "def": 12, "spd": 13},
        "moves": [
            {"name": "Dark Spores", "power": 15, "accuracy": 95, "desc": "Reduces foe's accuracy."},
            {"name": "Attic Shroud", "power": 0, "accuracy": 100, "desc": "Boosts own evasion."},
            {"name": "Rot Lash", "power": 14, "accuracy": 100, "desc": "Strong, always hits."},
            {"name": "Parasite Wave", "power": 17, "accuracy": 85, "desc": "Can drain HP."}
        ]
    },
    {
        "num": 45, "name": "Polterwatt", "type": "Énergie", "rarity": "Rare", "evolution": None,
        "description": "Ghost of an old electric generator.",
        "stats": {"hp": 44, "atk": 17, "def": 10, "spd": 16},
        "moves": [
            {"name": "Spirit Spark", "power": 16, "accuracy": 95, "desc": "May paralyze."},
            {"name": "Generator Shock", "power": 14, "accuracy": 100, "desc": "High damage."},
            {"name": "Watt Veil", "power": 0, "accuracy": 100, "desc": "Boosts defense and speed."},
            {"name": "Ghost Current", "power": 19, "accuracy": 80, "desc": "Huge, low accuracy."}
        ]
    },
    {
        "num": 46, "name": "Betonghost", "type": "Structure", "rarity": "Uncommon", "evolution": None,
        "description": "Concrete spirit, impossible to exorcise.",
        "stats": {"hp": 43, "atk": 14, "def": 14, "spd": 9},
        "moves": [
            {"name": "Cement Slam", "power": 14, "accuracy": 95, "desc": "Powerful physical hit."},
            {"name": "Haunt Block", "power": 0, "accuracy": 100, "desc": "Boosts defense for 2 turns."},
            {"name": "Spirit Brick", "power": 13, "accuracy": 100, "desc": "May stun foe."},
            {"name": "Dust Veil", "power": 12, "accuracy": 90, "desc": "Reduces foe's accuracy."}
        ]
    },
    {
        "num": 47, "name": "Sootveil", "type": "Climat", "rarity": "Uncommon", "evolution": None,
        "description": "Makes windows gray overnight.",
        "stats": {"hp": 40, "atk": 12, "def": 11, "spd": 14},
        "moves": [
            {"name": "Soot Swipe", "power": 12, "accuracy": 95, "desc": "Covers foe in soot."},
            {"name": "Gray Out", "power": 13, "accuracy": 100, "desc": "Blinds foe for 1 turn."},
            {"name": "Veil of Ash", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Nightfall", "power": 14, "accuracy": 85, "desc": "Strong, low accuracy."}
        ]
    },
    {
        "num": 48, "name": "Filtrix", "type": "Structure", "rarity": "Rare", "evolution": None,
        "description": "Hides in ventilation, clogs air filters.",
        "stats": {"hp": 48, "atk": 13, "def": 16, "spd": 12},
        "moves": [
            {"name": "Filter Block", "power": 15, "accuracy": 95, "desc": "Reduces foe's speed."},
            {"name": "Air Clog", "power": 14, "accuracy": 100, "desc": "May poison foe."},
            {"name": "Dust Armor", "power": 0, "accuracy": 100, "desc": "Greatly raises defense."},
            {"name": "Smother", "power": 16, "accuracy": 85, "desc": "High damage, low accuracy."}
        ]
    },
    {
        "num": 49, "name": "Netrust", "type": "Numérique", "rarity": "Uncommon", "evolution": None,
        "description": "Disables all smart locks.",
        "stats": {"hp": 39, "atk": 13, "def": 10, "spd": 14},
        "moves": [
            {"name": "Lock Break", "power": 13, "accuracy": 95, "desc": "Breaks through defense."},
            {"name": "Hack Pulse", "power": 13, "accuracy": 100, "desc": "May confuse foe."},
            {"name": "Lockdown", "power": 0, "accuracy": 100, "desc": "Prevents foe switching."},
            {"name": "Jam Signal", "power": 15, "accuracy": 85, "desc": "Reduces enemy accuracy."}
        ]
    },
    {
        "num": 50, "name": "Chillume", "type": "Climat", "rarity": "Common", "evolution": "Chillumeon",
        "description": "Frosty, likes to freeze pipes.",
        "stats": {"hp": 38, "atk": 10, "def": 10, "spd": 12},
        "moves": [
            {"name": "Pipe Freeze", "power": 11, "accuracy": 100, "desc": "Can freeze foe."},
            {"name": "Snow Spray", "power": 12, "accuracy": 95, "desc": "Reduces enemy speed."},
            {"name": "Frost Armor", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Winter Blast", "power": 13, "accuracy": 90, "desc": "Chilling, high power."}
        ]
    },
    {
        "num": 51, "name": "Chillumeon", "type": "Climat", "rarity": "Rare", "evolution": None,
        "description": "Can burst an entire plumbing system.",
        "stats": {"hp": 48, "atk": 15, "def": 11, "spd": 14},
        "moves": [
            {"name": "Burst Pipe", "power": 15, "accuracy": 95, "desc": "Massive freezing blow."},
            {"name": "Frost Storm", "power": 13, "accuracy": 100, "desc": "May freeze foe."},
            {"name": "Glacier Wall", "power": 0, "accuracy": 100, "desc": "Huge defense boost."},
            {"name": "Ice Age", "power": 17, "accuracy": 85, "desc": "Hits all enemies."}
        ]
    },
    {
        "num": 52, "name": "Thermold", "type": "Climat", "rarity": "Common", "evolution": "Thermoldra",
        "description": "Feeds on steam and hot showers.",
        "stats": {"hp": 38, "atk": 10, "def": 10, "spd": 12},
        "moves": [
            {"name": "Steam Shot", "power": 12, "accuracy": 95, "desc": "Burns foe a bit."},
            {"name": "Hot Wash", "power": 11, "accuracy": 100, "desc": "Boosts attack slightly."},
            {"name": "Mildew Shield", "power": 0, "accuracy": 100, "desc": "Raises defense."},
            {"name": "Sauna Surge", "power": 13, "accuracy": 90, "desc": "Scalding attack."}
        ]
    },
    {
        "num": 53, "name": "Thermoldra", "type": "Climat", "rarity": "Uncommon", "evolution": None,
        "description": "Leaves mildew everywhere.",
        "stats": {"hp": 43, "atk": 14, "def": 12, "spd": 13},
        "moves": [
            {"name": "Mildew Wave", "power": 14, "accuracy": 95, "desc": "Can paralyze foe."},
            {"name": "Heat Armor", "power": 0, "accuracy": 100, "desc": "Raises own defense a lot."},
            {"name": "Stale Air", "power": 12, "accuracy": 100, "desc": "Reduces foe's defense."},
            {"name": "Steam Crash", "power": 16, "accuracy": 85, "desc": "Heavy, low accuracy."}
        ]
    },
    {
        "num": 54, "name": "Screamroot", "type": "Spectre", "rarity": "Common", "evolution": "Screamora",
        "description": "Screams when floors creak.",
        "stats": {"hp": 35, "atk": 10, "def": 8, "spd": 14},
        "moves": [
            {"name": "Haunt Cry", "power": 9, "accuracy": 100, "desc": "Screeches to scare foe."},
            {"name": "Floor Creak", "power": 11, "accuracy": 95, "desc": "Can lower foe's defense."},
            {"name": "Shadow Shroud", "power": 0, "accuracy": 100, "desc": "Boosts evasion."},
            {"name": "Root Wail", "power": 13, "accuracy": 90, "desc": "Hits all enemies a bit."}
        ]
    },
    {
        "num": 55, "name": "Screamora", "type": "Spectre", "rarity": "Rare", "evolution": None,
        "description": "Turns creaks into ghostly howls.",
        "stats": {"hp": 44, "atk": 14, "def": 10, "spd": 15},
        "moves": [
            {"name": "Howl Storm", "power": 15, "accuracy": 95, "desc": "Loud, damages all."},
            {"name": "Wraith Scream", "power": 13, "accuracy": 100, "desc": "Reduces foe's speed."},
            {"name": "Banshee Veil", "power": 0, "accuracy": 100, "desc": "Boosts defense."},
            {"name": "Phantom Fury", "power": 17, "accuracy": 85, "desc": "Heavy ghostly blow."}
        ]
    },
    {
        "num": 56, "name": "Gutteron", "type": "Structure", "rarity": "Common", "evolution": "Guttergeist",
        "description": "Hides in gutters, blocks water flow.",
        "stats": {"hp": 37, "atk": 11, "def": 9, "spd": 11},
        "moves": [
            {"name": "Block Flow", "power": 10, "accuracy": 100, "desc": "Reduces foe's speed."},
            {"name": "Gutter Bite", "power": 12, "accuracy": 95, "desc": "Strong hit."},
            {"name": "Splash Guard", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Flood Burst", "power": 14, "accuracy": 90, "desc": "May confuse enemy."}
        ]
    },
    {
        "num": 57, "name": "Guttergeist", "type": "Structure", "rarity": "Rare", "evolution": None,
        "description": "Causes sudden floods during storms.",
        "stats": {"hp": 46, "atk": 14, "def": 12, "spd": 13},
        "moves": [
            {"name": "Flood Wave", "power": 15, "accuracy": 95, "desc": "Hits all enemies."},
            {"name": "Drainage Crash", "power": 13, "accuracy": 100, "desc": "Reduces foe's defense."},
            {"name": "Overflow", "power": 0, "accuracy": 100, "desc": "Raises attack for 2 turns."},
            {"name": "Storm Surge", "power": 17, "accuracy": 85, "desc": "High power, low accuracy."}
        ]
    },
    {
        "num": 58, "name": "Virugrime", "type": "Bio-Parasite", "rarity": "Common", "evolution": "Virulurk",
        "description": "Infects every nook and cranny.",
        "stats": {"hp": 36, "atk": 11, "def": 8, "spd": 12},
        "moves": [
            {"name": "Germ Burst", "power": 10, "accuracy": 100, "desc": "May poison foe."},
            {"name": "Infect", "power": 12, "accuracy": 95, "desc": "Saps foe's HP."},
            {"name": "Pathogen Guard", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Sickly Wave", "power": 14, "accuracy": 90, "desc": "High chance to poison."}
        ]
    },
    {
        "num": 59, "name": "Virulurk", "type": "Bio-Parasite", "rarity": "Uncommon", "evolution": None,
        "description": "Turns rooms into biohazards.",
        "stats": {"hp": 43, "atk": 13, "def": 11, "spd": 13},
        "moves": [
            {"name": "Biohazard Bash", "power": 13, "accuracy": 95, "desc": "Strong, may poison."},
            {"name": "Toxic Cloud", "power": 14, "accuracy": 100, "desc": "Hits all foes."},
            {"name": "Hazmat Armor", "power": 0, "accuracy": 100, "desc": "Greatly raises defense."},
            {"name": "Spore Storm", "power": 16, "accuracy": 85, "desc": "High risk, high reward."}
        ]
    },
    {
        "num": 60, "name": "Insulight", "type": "Énergie", "rarity": "Common", "evolution": "Insulash",
        "description": "Grows strong inside faulty insulation.",
        "stats": {"hp": 36, "atk": 10, "def": 9, "spd": 14},
        "moves": [
            {"name": "Insulate", "power": 0, "accuracy": 100, "desc": "Raises own defense a lot."},
            {"name": "Wire Shock", "power": 11, "accuracy": 100, "desc": "Can paralyze enemy."},
            {"name": "Foam Bash", "power": 12, "accuracy": 95, "desc": "Fast, bouncy hit."},
            {"name": "Current Jump", "power": 14, "accuracy": 90, "desc": "Electric leap attack."}
        ]
    },
    {
        "num": 61, "name": "Insulash", "type": "Énergie", "rarity": "Rare", "evolution": None,
        "description": "Releases sparks when cornered.",
        "stats": {"hp": 44, "atk": 15, "def": 12, "spd": 14},
        "moves": [
            {"name": "Spark Lash", "power": 16, "accuracy": 95, "desc": "Strong shock, may paralyze."},
            {"name": "Insulation Burst", "power": 14, "accuracy": 100, "desc": "High damage."},
            {"name": "Protective Layer", "power": 0, "accuracy": 100, "desc": "Raises defense by 2."},
            {"name": "Jolt Crash", "power": 18, "accuracy": 85, "desc": "Massive hit, low accuracy."}
        ]
    },
    {
        "num": 62, "name": "Drainox", "type": "Climat", "rarity": "Common", "evolution": "Drainshade",
        "description": "Loves to clog pipes and drains.",
        "stats": {"hp": 36, "atk": 11, "def": 10, "spd": 11},
        "moves": [
            {"name": "Clog Strike", "power": 10, "accuracy": 100, "desc": "Can lower enemy speed."},
            {"name": "Pipe Sludge", "power": 12, "accuracy": 95, "desc": "May poison foe."},
            {"name": "Drain Guard", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Overflow", "power": 14, "accuracy": 90, "desc": "Hits all enemies a little."}
        ]
    },
    {
        "num": 63, "name": "Drainshade", "type": "Climat", "rarity": "Uncommon", "evolution": None,
        "description": "Causes mysterious foul odors.",
        "stats": {"hp": 44, "atk": 13, "def": 13, "spd": 12},
        "moves": [
            {"name": "Odor Wave", "power": 13, "accuracy": 95, "desc": "May lower foe's defense."},
            {"name": "Toxic Drain", "power": 14, "accuracy": 100, "desc": "May poison."},
            {"name": "Pipe Shield", "power": 0, "accuracy": 100, "desc": "Greatly boosts defense."},
            {"name": "Gutter Flood", "power": 16, "accuracy": 85, "desc": "Massive water strike."}
        ]
    },
    {
        "num": 64, "name": "Shadowdust", "type": "Spectre", "rarity": "Uncommon", "evolution": None,
        "description": "Darkens lightbulbs, chills air.",
        "stats": {"hp": 38, "atk": 13, "def": 11, "spd": 15},
        "moves": [
            {"name": "Dust Swirl", "power": 12, "accuracy": 95, "desc": "May blind foe."},
            {"name": "Night Haze", "power": 13, "accuracy": 100, "desc": "Reduces accuracy of enemy."},
            {"name": "Shadow Veil", "power": 0, "accuracy": 100, "desc": "Raises own evasion."},
            {"name": "Ghost Pulse", "power": 16, "accuracy": 85, "desc": "Strong, spectral hit."}
        ]
    },
    {
        "num": 65, "name": "Glimmette", "type": "Numérique", "rarity": "Common", "evolution": "Glimmark",
        "description": "Makes lights flicker on and off.",
        "stats": {"hp": 35, "atk": 10, "def": 9, "spd": 14},
        "moves": [
            {"name": "Flicker", "power": 10, "accuracy": 100, "desc": "May confuse foe."},
            {"name": "Blink Shot", "power": 12, "accuracy": 95, "desc": "Hits fast."},
            {"name": "Light Screen", "power": 0, "accuracy": 100, "desc": "Raises defense."},
            {"name": "Flash Burst", "power": 14, "accuracy": 90, "desc": "Bright, hard to dodge."}
        ]
    },
    {
        "num": 66, "name": "Glimmark", "type": "Numérique", "rarity": "Uncommon", "evolution": None,
        "description": "Causes total blackouts.",
        "stats": {"hp": 42, "atk": 14, "def": 11, "spd": 15},
        "moves": [
            {"name": "Blackout", "power": 13, "accuracy": 95, "desc": "May stun foe."},
            {"name": "Dark Flash", "power": 13, "accuracy": 100, "desc": "Powerful light attack."},
            {"name": "Glow Guard", "power": 0, "accuracy": 100, "desc": "Boosts defense."},
            {"name": "Laser Crash", "power": 16, "accuracy": 85, "desc": "High damage, low accuracy."}
        ]
    },
    {
        "num": 67, "name": "Frigilix", "type": "Climat", "rarity": "Common", "evolution": "Frigilune",
        "description": "Grows on cold windowsills.",
        "stats": {"hp": 36, "atk": 10, "def": 10, "spd": 12},
        "moves": [
            {"name": "Frost Bite", "power": 11, "accuracy": 100, "desc": "Can freeze foe."},
            {"name": "Chill Wave", "power": 12, "accuracy": 95, "desc": "May reduce speed."},
            {"name": "Ice Coat", "power": 0, "accuracy": 100, "desc": "Raises defense."},
            {"name": "Winter Beam", "power": 14, "accuracy": 90, "desc": "Icy strike, high power."}
        ]
    },
    {
        "num": 68, "name": "Frigilune", "type": "Climat", "rarity": "Rare", "evolution": None,
        "description": "Invites frost indoors.",
        "stats": {"hp": 46, "atk": 14, "def": 12, "spd": 14},
        "moves": [
            {"name": "Frost Nova", "power": 15, "accuracy": 95, "desc": "Hits all enemies."},
            {"name": "Snowstorm", "power": 13, "accuracy": 100, "desc": "May freeze foe."},
            {"name": "Polar Wall", "power": 0, "accuracy": 100, "desc": "Raises own defense a lot."},
            {"name": "Crystal Hail", "power": 17, "accuracy": 85, "desc": "Heavy, low accuracy."}
        ]
    },
    {
        "num": 69, "name": "Termitix", "type": "Bio-Parasite", "rarity": "Rare", "evolution": None,
        "description": "Eats through wooden beams.",
        "stats": {"hp": 44, "atk": 16, "def": 10, "spd": 14},
        "moves": [
            {"name": "Wood Gnaw", "power": 15, "accuracy": 95, "desc": "Can lower defense."},
            {"name": "Rot Swarm", "power": 13, "accuracy": 100, "desc": "Multi-hit bug attack."},
            {"name": "Infest Armor", "power": 0, "accuracy": 100, "desc": "Raises defense by 2."},
            {"name": "Decay Bite", "power": 18, "accuracy": 85, "desc": "Huge, but risky."}
        ]
    },
    {
        "num": 70, "name": "Wispulse", "type": "Spectre", "rarity": "Common", "evolution": "Wisphere",
        "description": "Appears when lights fail.",
        "stats": {"hp": 34, "atk": 10, "def": 8, "spd": 15},
        "moves": [
            {"name": "Pulse Ray", "power": 9, "accuracy": 100, "desc": "May paralyze foe."},
            {"name": "Ghost Flicker", "power": 11, "accuracy": 95, "desc": "Reduces foe's accuracy."},
            {"name": "Specter Shield", "power": 0, "accuracy": 100, "desc": "Boosts own defense."},
            {"name": "Light Drain", "power": 13, "accuracy": 90, "desc": "Drains foe's HP."}
        ]
    },
    {
        "num": 71, "name": "Wisphere", "type": "Spectre", "rarity": "Rare", "evolution": None,
        "description": "Makes LED bulbs explode.",
        "stats": {"hp": 44, "atk": 13, "def": 10, "spd": 16},
        "moves": [
            {"name": "LED Burst", "power": 15, "accuracy": 95, "desc": "High power light blast."},
            {"name": "Ghostly Pop", "power": 13, "accuracy": 100, "desc": "Stuns foe sometimes."},
            {"name": "Phantom Mist", "power": 0, "accuracy": 100, "desc": "Raises evasion."},
            {"name": "Pulse Chain", "power": 16, "accuracy": 85, "desc": "Multi-hit energy."}
        ]
    },
    {
        "num": 72, "name": "Statibit", "type": "Numérique", "rarity": "Common", "evolution": "Statiburst",
        "description": "Static shock on every touch.",
        "stats": {"hp": 35, "atk": 10, "def": 9, "spd": 15},
        "moves": [
            {"name": "Shock Touch", "power": 10, "accuracy": 100, "desc": "May paralyze foe."},
            {"name": "Static Jolt", "power": 12, "accuracy": 95, "desc": "Quick, reliable hit."},
            {"name": "Jitter Shield", "power": 0, "accuracy": 100, "desc": "Boosts own speed."},
            {"name": "Burst Byte", "power": 14, "accuracy": 90, "desc": "Electric digital attack."}
        ]
    },
    {
        "num": 73, "name": "Statiburst", "type": "Numérique", "rarity": "Rare", "evolution": None,
        "description": "Can fry entire server rooms.",
        "stats": {"hp": 43, "atk": 15, "def": 11, "spd": 15},
        "moves": [
            {"name": "Power Surge", "power": 16, "accuracy": 95, "desc": "Very strong attack."},
            {"name": "Bit Bomb", "power": 14, "accuracy": 100, "desc": "Explosive data hit."},
            {"name": "Electro Cloak", "power": 0, "accuracy": 100, "desc": "Raises defense."},
            {"name": "Static Blast", "power": 17, "accuracy": 85, "desc": "Massive, but risky."}
        ]
    },
    {
        "num": 74, "name": "Leakroot", "type": "Climat", "rarity": "Common", "evolution": "Leakshade",
        "description": "Leaks water into random spots.",
        "stats": {"hp": 36, "atk": 10, "def": 10, "spd": 12},
        "moves": [
            {"name": "Leak Jet", "power": 11, "accuracy": 100, "desc": "May reduce foe's defense."},
            {"name": "Puddle Trap", "power": 12, "accuracy": 95, "desc": "Can slow enemy."},
            {"name": "Flood Guard", "power": 0, "accuracy": 100, "desc": "Raises defense."},
            {"name": "Aqua Slam", "power": 14, "accuracy": 90, "desc": "Water-type smash."}
        ]
    },
    {
        "num": 75, "name": "Leakshade", "type": "Climat", "rarity": "Uncommon", "evolution": None,
        "description": "Floods basements with gloom.",
        "stats": {"hp": 44, "atk": 13, "def": 13, "spd": 12},
        "moves": [
            {"name": "Basement Flood", "power": 15, "accuracy": 95, "desc": "Hits all enemies."},
            {"name": "Moist Grip", "power": 14, "accuracy": 100, "desc": "Reduces foe's attack."},
            {"name": "Water Veil", "power": 0, "accuracy": 100, "desc": "Boosts own defense."},
            {"name": "Gloom Strike", "power": 16, "accuracy": 85, "desc": "Dark water hit."}
        ]
    },
    {
        "num": 76, "name": "Creepad", "type": "Structure", "rarity": "Common", "evolution": "Creepath",
        "description": "Makes floors squeak eerily.",
        "stats": {"hp": 36, "atk": 11, "def": 9, "spd": 12},
        "moves": [
            {"name": "Squeak Hit", "power": 10, "accuracy": 100, "desc": "Quick, annoying strike."},
            {"name": "Wood Rattle", "power": 12, "accuracy": 95, "desc": "May confuse foe."},
            {"name": "Plank Shield", "power": 0, "accuracy": 100, "desc": "Raises defense."},
            {"name": "Groan Attack", "power": 14, "accuracy": 90, "desc": "Creepy, strong blow."}
        ]
    },
    {
        "num": 77, "name": "Creepath", "type": "Structure", "rarity": "Rare", "evolution": None,
        "description": "Warps floorboards like a wave.",
        "stats": {"hp": 44, "atk": 14, "def": 12, "spd": 13},
        "moves": [
            {"name": "Warp Smash", "power": 15, "accuracy": 95, "desc": "Distorts enemy defense."},
            {"name": "Floor Wave", "power": 13, "accuracy": 100, "desc": "Strong, reliable."},
            {"name": "Bend Barrier", "power": 0, "accuracy": 100, "desc": "Boosts own defense."},
            {"name": "Collapse", "power": 17, "accuracy": 85, "desc": "Heavy, low accuracy."}
        ]
    },
    {
        "num": 78, "name": "Radonis", "type": "Climat", "rarity": "Rare", "evolution": None,
        "description": "Emits mysterious energies.",
        "stats": {"hp": 44, "atk": 15, "def": 13, "spd": 14},
        "moves": [
            {"name": "Radon Burst", "power": 15, "accuracy": 95, "desc": "May poison foe."},
            {"name": "Mysterious Ray", "power": 14, "accuracy": 100, "desc": "Strange effects."},
            {"name": "Energy Veil", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Radiate", "power": 18, "accuracy": 85, "desc": "Huge, unpredictable hit."}
        ]
    },
    {
        "num": 79, "name": "Crackrune", "type": "Structure", "rarity": "Common", "evolution": "Crackryst",
        "description": "Carves runes into concrete.",
        "stats": {"hp": 38, "atk": 10, "def": 12, "spd": 10},
        "moves": [
            {"name": "Rune Hit", "power": 11, "accuracy": 100, "desc": "Hits with energy."},
            {"name": "Etch Strike", "power": 12, "accuracy": 95, "desc": "May lower foe's defense."},
            {"name": "Concrete Shield", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Crack Pulse", "power": 14, "accuracy": 90, "desc": "Strong, causes confusion."}
        ]
    },
    {
        "num": 80, "name": "Crackryst", "type": "Structure", "rarity": "Uncommon", "evolution": None,
        "description": "Runes glow in the dark.",
        "stats": {"hp": 46, "atk": 13, "def": 15, "spd": 11},
        "moves": [
            {"name": "Crystal Beam", "power": 14, "accuracy": 95, "desc": "Blinding attack."},
            {"name": "Shine Guard", "power": 0, "accuracy": 100, "desc": "Boosts defense a lot."},
            {"name": "Energy Engrave", "power": 13, "accuracy": 100, "desc": "Strong energy strike."},
            {"name": "Dark Shatter", "power": 17, "accuracy": 85, "desc": "Heavy, can lower defense."}
        ]
    },
    {
        "num": 81, "name": "Spoorine", "type": "Bio-Parasite", "rarity": "Common", "evolution": "Spoorage",
        "description": "Spreads via contaminated dust.",
        "stats": {"hp": 37, "atk": 11, "def": 10, "spd": 12},
        "moves": [
            {"name": "Spore Shot", "power": 11, "accuracy": 100, "desc": "May paralyze."},
            {"name": "Fungal Growth", "power": 12, "accuracy": 95, "desc": "Boosts own attack."},
            {"name": "Dust Guard", "power": 0, "accuracy": 100, "desc": "Raises defense."},
            {"name": "Contaminate", "power": 14, "accuracy": 90, "desc": "May poison enemy."}
        ]
    },
    {
        "num": 82, "name": "Spoorage", "type": "Bio-Parasite", "rarity": "Rare", "evolution": None,
        "description": "Colonizes ventilation systems.",
        "stats": {"hp": 46, "atk": 14, "def": 13, "spd": 13},
        "moves": [
            {"name": "Spore Swarm", "power": 15, "accuracy": 95, "desc": "Hits all enemies."},
            {"name": "Fungus Strike", "power": 14, "accuracy": 100, "desc": "Strong, reliable."},
            {"name": "Vent Shield", "power": 0, "accuracy": 100, "desc": "Boosts own defense."},
            {"name": "Toxic Haze", "power": 17, "accuracy": 85, "desc": "Poisons all foes."}
        ]
    },
    {
        "num": 83, "name": "Pestflare", "type": "Bio-Parasite", "rarity": "Uncommon", "evolution": None,
        "description": "Attracts swarms of bugs.",
        "stats": {"hp": 41, "atk": 13, "def": 10, "spd": 15},
        "moves": [
            {"name": "Bug Swarm", "power": 13, "accuracy": 95, "desc": "Hits multiple times."},
            {"name": "Bite Strike", "power": 14, "accuracy": 100, "desc": "Strong attack."},
            {"name": "Insect Shell", "power": 0, "accuracy": 100, "desc": "Boosts defense."},
            {"name": "Plague", "power": 17, "accuracy": 85, "desc": "May poison all foes."}
        ]
    },
    {
        "num": 84, "name": "Magnetide", "type": "Énergie", "rarity": "Rare", "evolution": None,
        "description": "Interferes with all appliances.",
        "stats": {"hp": 45, "atk": 16, "def": 13, "spd": 12},
        "moves": [
            {"name": "Magnetic Pull", "power": 15, "accuracy": 95, "desc": "Draws enemy close."},
            {"name": "Field Crash", "power": 14, "accuracy": 100, "desc": "Damages all electronics."},
            {"name": "Polarity Shift", "power": 0, "accuracy": 100, "desc": "Switches attack/defense."},
            {"name": "Appliance Zap", "power": 18, "accuracy": 85, "desc": "Overloads circuits."}
        ]
    },
    {
        "num": 85, "name": "Shiverun", "type": "Climat", "rarity": "Common", "evolution": "Shiveroll",
        "description": "Creates sudden chills.",
        "stats": {"hp": 36, "atk": 10, "def": 10, "spd": 13},
        "moves": [
            {"name": "Cold Snap", "power": 11, "accuracy": 100, "desc": "May freeze foe."},
            {"name": "Shiver Strike", "power": 12, "accuracy": 95, "desc": "Chilling attack."},
            {"name": "Ice Veil", "power": 0, "accuracy": 100, "desc": "Raises defense."},
            {"name": "Winter Grasp", "power": 14, "accuracy": 90, "desc": "Strong cold hit."}
        ]
    },
    {
        "num": 86, "name": "Shiveroll", "type": "Climat", "rarity": "Uncommon", "evolution": None,
        "description": "Ices up windows instantly.",
        "stats": {"hp": 44, "atk": 14, "def": 12, "spd": 14},
        "moves": [
            {"name": "Frost Rush", "power": 14, "accuracy": 95, "desc": "Fast, chilling attack."},
            {"name": "Snow Blanket", "power": 0, "accuracy": 100, "desc": "Raises defense a lot."},
            {"name": "Blizzard", "power": 15, "accuracy": 100, "desc": "May freeze all enemies."},
            {"name": "Freeze Ray", "power": 17, "accuracy": 85, "desc": "Massive ice attack."}
        ]
    },
    {
        "num": 87, "name": "Luminoir", "type": "Numérique", "rarity": "Rare", "evolution": None,
        "description": "Overloads smart lighting.",
        "stats": {"hp": 45, "atk": 16, "def": 13, "spd": 15},
        "moves": [
            {"name": "Light Surge", "power": 16, "accuracy": 95, "desc": "Blinding, may stun."},
            {"name": "Lumen Crash", "power": 15, "accuracy": 100, "desc": "Bright, high damage."},
            {"name": "Photon Veil", "power": 0, "accuracy": 100, "desc": "Raises evasion."},
            {"name": "Strobe Burst", "power": 18, "accuracy": 85, "desc": "Massive light attack."}
        ]
    },
    {
        "num": 88, "name": "Smogshade", "type": "Climat", "rarity": "Uncommon", "evolution": None,
        "description": "Smothers rooms with gray fog.",
        "stats": {"hp": 39, "atk": 12, "def": 13, "spd": 13},
        "moves": [
            {"name": "Smog Wave", "power": 13, "accuracy": 95, "desc": "May poison foe."},
            {"name": "Haze Cloak", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Gray Mist", "power": 14, "accuracy": 100, "desc": "Blinds enemies."},
            {"name": "Chokehold", "power": 16, "accuracy": 85, "desc": "Damages all, may stun."}
        ]
    },
    {
        "num": 89, "name": "Plumbgeist", "type": "Spectre", "rarity": "Uncommon", "evolution": None,
        "description": "Possesses old plumbing pipes.",
        "stats": {"hp": 41, "atk": 13, "def": 14, "spd": 12},
        "moves": [
            {"name": "Pipe Haunt", "power": 13, "accuracy": 95, "desc": "May cause confusion."},
            {"name": "Water Wail", "power": 12, "accuracy": 100, "desc": "Spectral water hit."},
            {"name": "Haunt Armor", "power": 0, "accuracy": 100, "desc": "Raises defense a lot."},
            {"name": "Ghost Flow", "power": 16, "accuracy": 85, "desc": "Damages all, high power."}
        ]
    },
    {
        "num": 90, "name": "Brixis", "type": "Structure", "rarity": "Common", "evolution": "Brixiant",
        "description": "Brick dust forms its body.",
        "stats": {"hp": 38, "atk": 11, "def": 12, "spd": 11},
        "moves": [
            {"name": "Brick Bash", "power": 11, "accuracy": 100, "desc": "Solid, reliable hit."},
            {"name": "Dust Crash", "power": 12, "accuracy": 95, "desc": "May blind foe."},
            {"name": "Mortar Wall", "power": 0, "accuracy": 100, "desc": "Raises defense."},
            {"name": "Brick Toss", "power": 14, "accuracy": 90, "desc": "Heavy, can stun."}
        ]
    },
        {
        "num": 91, "name": "Brixiant", "type": "Structure", "rarity": "Uncommon", "evolution": None,
        "description": "Can strengthen weak walls.",
        "stats": {"hp": 46, "atk": 13, "def": 16, "spd": 11},
        "moves": [
            {"name": "Wall Crush", "power": 14, "accuracy": 95, "desc": "Strong, can lower defense."},
            {"name": "Dust Guard", "power": 0, "accuracy": 100, "desc": "Boosts own defense sharply."},
            {"name": "Reinforce", "power": 13, "accuracy": 100, "desc": "Raises both defense and HP a little."},
            {"name": "Brick Quake", "power": 17, "accuracy": 85, "desc": "Heavy, shakes the field."}
        ]
    },
    {
        "num": 92, "name": "Sporalux", "type": "Bio-Parasite", "rarity": "Rare", "evolution": None,
        "description": "Glows in the dark, feeds on paint.",
        "stats": {"hp": 45, "atk": 16, "def": 11, "spd": 14},
        "moves": [
            {"name": "Lumen Spores", "power": 16, "accuracy": 95, "desc": "May paralyze all foes."},
            {"name": "Paint Drain", "power": 14, "accuracy": 100, "desc": "Absorbs HP."},
            {"name": "Glow Up", "power": 0, "accuracy": 100, "desc": "Boosts own attack."},
            {"name": "Dark Bloom", "power": 18, "accuracy": 85, "desc": "Massive, risky attack."}
        ]
    },
    {
        "num": 93, "name": "Datashade", "type": "Numérique", "rarity": "Uncommon", "evolution": None,
        "description": "Hides in data cables, erases files.",
        "stats": {"hp": 39, "atk": 14, "def": 12, "spd": 14},
        "moves": [
            {"name": "Data Siphon", "power": 14, "accuracy": 95, "desc": "Steals enemy energy."},
            {"name": "Erase", "power": 13, "accuracy": 100, "desc": "Can lower enemy attack."},
            {"name": "File Guard", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Digital Smog", "power": 16, "accuracy": 85, "desc": "Confuses all enemies."}
        ]
    },
    {
        "num": 94, "name": "Gasphex", "type": "Climat", "rarity": "Uncommon", "evolution": None,
        "description": "Fills rooms with untraceable gas.",
        "stats": {"hp": 40, "atk": 13, "def": 13, "spd": 14},
        "moves": [
            {"name": "Toxic Mist", "power": 14, "accuracy": 95, "desc": "May poison all."},
            {"name": "Invisible Veil", "power": 0, "accuracy": 100, "desc": "Boosts evasion."},
            {"name": "Fume Crash", "power": 13, "accuracy": 100, "desc": "Can confuse foe."},
            {"name": "Gas Blast", "power": 17, "accuracy": 85, "desc": "Powerful, risky attack."}
        ]
    },
    {
        "num": 95, "name": "Cracklin", "type": "Structure", "rarity": "Common", "evolution": "Cracklash",
        "description": "Jumps from crack to crack.",
        "stats": {"hp": 36, "atk": 11, "def": 10, "spd": 15},
        "moves": [
            {"name": "Crackle Hit", "power": 11, "accuracy": 100, "desc": "Fast, can lower defense."},
            {"name": "Quick Dash", "power": 12, "accuracy": 95, "desc": "Raises own speed."},
            {"name": "Brick Chip", "power": 0, "accuracy": 100, "desc": "Raises defense."},
            {"name": "Crack Jump", "power": 14, "accuracy": 90, "desc": "Can cause confusion."}
        ]
    },
    {
        "num": 96, "name": "Cracklash", "type": "Structure", "rarity": "Rare", "evolution": None,
        "description": "Causes structural chain reactions.",
        "stats": {"hp": 44, "atk": 15, "def": 13, "spd": 14},
        "moves": [
            {"name": "Chain Quake", "power": 16, "accuracy": 95, "desc": "May lower all foes' defense."},
            {"name": "Fracture", "power": 14, "accuracy": 100, "desc": "Strong, reliable attack."},
            {"name": "Wall Up", "power": 0, "accuracy": 100, "desc": "Greatly boosts own defense."},
            {"name": "Crack Bomb", "power": 18, "accuracy": 85, "desc": "Huge, but risky."}
        ]
    },
    {
        "num": 97, "name": "Damphex", "type": "Climat", "rarity": "Common", "evolution": "Damptide",
        "description": "Dampens the air with cold mist.",
        "stats": {"hp": 35, "atk": 10, "def": 11, "spd": 12},
        "moves": [
            {"name": "Mist Shot", "power": 10, "accuracy": 100, "desc": "May blind foe."},
            {"name": "Chill Pulse", "power": 12, "accuracy": 95, "desc": "Slows enemy."},
            {"name": "Moist Shield", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Damp Strike", "power": 14, "accuracy": 90, "desc": "Strong, cold hit."}
        ]
    },
    {
        "num": 98, "name": "Damptide", "type": "Climat", "rarity": "Uncommon", "evolution": None,
        "description": "Swells wood, ruins parquet floors.",
        "stats": {"hp": 43, "atk": 13, "def": 14, "spd": 12},
        "moves": [
            {"name": "Flood Bash", "power": 15, "accuracy": 95, "desc": "Can lower foe's speed."},
            {"name": "Wood Swell", "power": 14, "accuracy": 100, "desc": "Reduces enemy defense."},
            {"name": "Moisture Veil", "power": 0, "accuracy": 100, "desc": "Greatly boosts own defense."},
            {"name": "Parquet Slam", "power": 17, "accuracy": 85, "desc": "Heavy, floor-damaging hit."}
        ]
    },
    {
        "num": 99, "name": "Buggbyte", "type": "Numérique", "rarity": "Common", "evolution": "BuggbyteX",
        "description": "Causes error pop-ups everywhere.",
        "stats": {"hp": 36, "atk": 11, "def": 10, "spd": 15},
        "moves": [
            {"name": "Pop-up Spam", "power": 11, "accuracy": 100, "desc": "Confuses foe."},
            {"name": "Bit Hit", "power": 12, "accuracy": 95, "desc": "Digital strike."},
            {"name": "Crash Guard", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Error Glitch", "power": 14, "accuracy": 90, "desc": "May stun enemy."}
        ]
    },
    {
        "num": 100, "name": "BuggbyteX", "type": "Numérique", "rarity": "Rare", "evolution": None,
        "description": "Triggers system-wide meltdowns.",
        "stats": {"hp": 44, "atk": 15, "def": 12, "spd": 15},
        "moves": [
            {"name": "System Crash", "power": 16, "accuracy": 95, "desc": "Can paralyze enemy."},
            {"name": "Bit Explosion", "power": 14, "accuracy": 100, "desc": "Huge digital hit."},
            {"name": "Blue Screen", "power": 0, "accuracy": 100, "desc": "Boosts own evasion."},
            {"name": "Fatal Error", "power": 18, "accuracy": 85, "desc": "Ultimate, risky."}
        ]
    },
    {
        "num": 101, "name": "Creepflow", "type": "Structure", "rarity": "Uncommon", "evolution": None,
        "description": "Walls seem to 'breathe' when it's near.",
        "stats": {"hp": 42, "atk": 13, "def": 15, "spd": 12},
        "moves": [
            {"name": "Wall Squeeze", "power": 14, "accuracy": 95, "desc": "May paralyze."},
            {"name": "Breath Strike", "power": 13, "accuracy": 100, "desc": "Odd, may confuse."},
            {"name": "Warp Barrier", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Pressure Wave", "power": 17, "accuracy": 85, "desc": "Strong, defense down."}
        ]
    },
    {
        "num": 102, "name": "Dustshade", "type": "Climat", "rarity": "Common", "evolution": "Dustloom",
        "description": "Covers every surface in fine dust.",
        "stats": {"hp": 37, "atk": 11, "def": 11, "spd": 13},
        "moves": [
            {"name": "Dust Swirl", "power": 11, "accuracy": 100, "desc": "Blinds foe."},
            {"name": "Powder Hit", "power": 12, "accuracy": 95, "desc": "Soft, reliable attack."},
            {"name": "Fine Shield", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Silt Blast", "power": 14, "accuracy": 90, "desc": "Earthy, can lower speed."}
        ]
    },
    {
        "num": 103, "name": "Dustloom", "type": "Climat", "rarity": "Rare", "evolution": None,
        "description": "Turns rooms pitch black.",
        "stats": {"hp": 45, "atk": 14, "def": 13, "spd": 13},
        "moves": [
            {"name": "Pitch Veil", "power": 16, "accuracy": 95, "desc": "May blind all enemies."},
            {"name": "Dark Dust", "power": 14, "accuracy": 100, "desc": "Heavy, slow attack."},
            {"name": "Veil Guard", "power": 0, "accuracy": 100, "desc": "Boosts own defense."},
            {"name": "Blackout Slam", "power": 17, "accuracy": 85, "desc": "Huge, rare miss."}
        ]
    },
    {
        "num": 104, "name": "Coblite", "type": "Structure", "rarity": "Common", "evolution": "Coblumine",
        "description": "Masonry dust forms its cloak.",
        "stats": {"hp": 36, "atk": 12, "def": 12, "spd": 11},
        "moves": [
            {"name": "Stone Throw", "power": 11, "accuracy": 100, "desc": "Simple rock hit."},
            {"name": "Masonry Bash", "power": 12, "accuracy": 95, "desc": "Hits hard."},
            {"name": "Brick Guard", "power": 0, "accuracy": 100, "desc": "Raises defense."},
            {"name": "Dust Pulse", "power": 14, "accuracy": 90, "desc": "Cloud of dust blinds foe."}
        ]
    },
    {
        "num": 105, "name": "Coblumine", "type": "Structure", "rarity": "Uncommon", "evolution": None,
        "description": "Glows in ruins at night.",
        "stats": {"hp": 44, "atk": 13, "def": 15, "spd": 12},
        "moves": [
            {"name": "Glow Strike", "power": 14, "accuracy": 95, "desc": "Blinding blow."},
            {"name": "Ruins Veil", "power": 0, "accuracy": 100, "desc": "Boosts defense sharply."},
            {"name": "Night Slam", "power": 13, "accuracy": 100, "desc": "Strong at night."},
            {"name": "Lumino Blast", "power": 17, "accuracy": 85, "desc": "High power, risky."}
        ]
    },
    {
        "num": 106, "name": "Sputterix", "type": "Énergie", "rarity": "Common", "evolution": "Sputterox",
        "description": "Makes outlets spark for fun.",
        "stats": {"hp": 35, "atk": 11, "def": 10, "spd": 15},
        "moves": [
            {"name": "Outlet Zap", "power": 12, "accuracy": 100, "desc": "May paralyze foe."},
            {"name": "Sputter Jolt", "power": 11, "accuracy": 95, "desc": "Annoying shock."},
            {"name": "Plug Guard", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Short Circuit", "power": 14, "accuracy": 90, "desc": "Low accuracy, strong hit."}
        ]
    },
    {
        "num": 107, "name": "Sputterox", "type": "Énergie", "rarity": "Rare", "evolution": None,
        "description": "Can short out an entire grid.",
        "stats": {"hp": 43, "atk": 15, "def": 12, "spd": 15},
        "moves": [
            {"name": "Grid Shock", "power": 16, "accuracy": 95, "desc": "Paralyzes all foes."},
            {"name": "Ox Surge", "power": 15, "accuracy": 100, "desc": "Very strong shock."},
            {"name": "Ground Guard", "power": 0, "accuracy": 100, "desc": "Reduces damage next turn."},
            {"name": "Power Out", "power": 18, "accuracy": 85, "desc": "Biggest attack."}
        ]
    },
    {
        "num": 108, "name": "Vaporgale", "type": "Climat", "rarity": "Uncommon", "evolution": None,
        "description": "Hot breath fogs up every mirror.",
        "stats": {"hp": 40, "atk": 13, "def": 12, "spd": 14},
        "moves": [
            {"name": "Steam Blast", "power": 14, "accuracy": 95, "desc": "Hot, may burn foe."},
            {"name": "Mirror Mist", "power": 13, "accuracy": 100, "desc": "Can blind."},
            {"name": "Fog Screen", "power": 0, "accuracy": 100, "desc": "Boosts own defense."},
            {"name": "Gale Strike", "power": 17, "accuracy": 85, "desc": "Hits hard, low accuracy."}
        ]
    },
    {
        "num": 109, "name": "Nocrypt", "type": "Spectre", "rarity": "Rare", "evolution": None,
        "description": "Guards ancient blueprints.",
        "stats": {"hp": 44, "atk": 14, "def": 14, "spd": 14},
        "moves": [
            {"name": "Crypt Guard", "power": 16, "accuracy": 95, "desc": "Protects team, may boost defense."},
            {"name": "Ancient Curse", "power": 15, "accuracy": 100, "desc": "Haunted strike."},
            {"name": "Blueprint Veil", "power": 0, "accuracy": 100, "desc": "Boosts defense a lot."},
            {"name": "Lost Scream", "power": 18, "accuracy": 85, "desc": "Huge spectral attack."}
        ]
    },
    {
        "num": 110, "name": "Fibergeist", "type": "Numérique", "rarity": "Rare", "evolution": None,
        "description": "Corrupts fiber optic cables.",
        "stats": {"hp": 45, "atk": 15, "def": 14, "spd": 16},
        "moves": [
            {"name": "Fiber Lash", "power": 17, "accuracy": 95, "desc": "Fast, damaging strike."},
            {"name": "Corrupt Data", "power": 14, "accuracy": 100, "desc": "May paralyze foe."},
            {"name": "Light Guard", "power": 0, "accuracy": 100, "desc": "Boosts own evasion."},
            {"name": "Data Ruin", "power": 19, "accuracy": 85, "desc": "Ultimate, low accuracy."}
        ]
    },
    {
        "num": 111, "name": "Mosslash", "type": "Bio-Parasite", "rarity": "Common", "evolution": "Mosslurk",
        "description": "Green and invasive.",
        "stats": {"hp": 35, "atk": 10, "def": 11, "spd": 13},
        "moves": [
            {"name": "Moss Bite", "power": 11, "accuracy": 100, "desc": "May lower defense."},
            {"name": "Spore Spray", "power": 12, "accuracy": 95, "desc": "Fungal attack."},
            {"name": "Root Guard", "power": 0, "accuracy": 100, "desc": "Raises defense."},
            {"name": "Creep Growth", "power": 14, "accuracy": 90, "desc": "Boosts own attack."}
        ]
    },
    {
        "num": 112, "name": "Mosslurk", "type": "Bio-Parasite", "rarity": "Rare", "evolution": None,
        "description": "Grows behind wallpaper silently.",
        "stats": {"hp": 44, "atk": 14, "def": 13, "spd": 13},
        "moves": [
            {"name": "Wall Creep", "power": 15, "accuracy": 95, "desc": "Strong, may poison."},
            {"name": "Lurk Strike", "power": 13, "accuracy": 100, "desc": "Sneaky attack."},
            {"name": "Wallpaper Veil", "power": 0, "accuracy": 100, "desc": "Raises defense and evasion."},
            {"name": "Silent Spread", "power": 17, "accuracy": 85, "desc": "Slow, very strong."}
        ]
    },
    {
        "num": 113, "name": "Fractorn", "type": "Structure", "rarity": "Rare", "evolution": None,
        "description": "Shatters glass with ultrasonic screams.",
        "stats": {"hp": 46, "atk": 16, "def": 12, "spd": 14},
        "moves": [
            {"name": "Glass Break", "power": 17, "accuracy": 95, "desc": "Destroys barriers."},
            {"name": "Ultrasonic Scream", "power": 15, "accuracy": 100, "desc": "Can stun foes."},
            {"name": "Fracture Guard", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Mirror Burst", "power": 19, "accuracy": 85, "desc": "Powerful but rare."}
        ]
    },
    {
        "num": 114, "name": "Chitterra", "type": "Bio-Parasite", "rarity": "Common", "evolution": "Chitterrusk",
        "description": "Scratches at insulation.",
        "stats": {"hp": 36, "atk": 11, "def": 10, "spd": 13},
        "moves": [
            {"name": "Scratch", "power": 11, "accuracy": 100, "desc": "Basic, reliable hit."},
            {"name": "Bite", "power": 12, "accuracy": 95, "desc": "May lower defense."},
            {"name": "Insulate", "power": 0, "accuracy": 100, "desc": "Raises defense."},
            {"name": "Quick Chew", "power": 14, "accuracy": 90, "desc": "May stun foe."}
        ]
    },
    {
        "num": 115, "name": "Chitterrusk", "type": "Bio-Parasite", "rarity": "Uncommon", "evolution": None,
        "description": "Invites real bugs inside.",
        "stats": {"hp": 42, "atk": 13, "def": 13, "spd": 13},
        "moves": [
            {"name": "Bug Call", "power": 15, "accuracy": 95, "desc": "Summons help."},
            {"name": "Insulate Strike", "power": 13, "accuracy": 100, "desc": "Boosted if hit after."},
            {"name": "Guard Swarm", "power": 0, "accuracy": 100, "desc": "Raises defense and attack."},
            {"name": "Frenzy Chomp", "power": 16, "accuracy": 85, "desc": "Very strong bite."}
        ]
    },
    {
        "num": 116, "name": "Luminel", "type": "Numérique", "rarity": "Common", "evolution": "Luminisk",
        "description": "Makes LEDs flash patterns.",
        "stats": {"hp": 37, "atk": 11, "def": 10, "spd": 14},
        "moves": [
            {"name": "Flash", "power": 11, "accuracy": 100, "desc": "May stun enemy."},
            {"name": "Light Trick", "power": 12, "accuracy": 95, "desc": "Confuses foe."},
            {"name": "Glow Guard", "power": 0, "accuracy": 100, "desc": "Boosts own defense."},
            {"name": "Flicker Hit", "power": 14, "accuracy": 90, "desc": "May lower enemy speed."}
        ]
    },
    {
        "num": 117, "name": "Luminisk", "type": "Numérique", "rarity": "Uncommon", "evolution": None,
        "description": "Hypnotizes building occupants.",
        "stats": {"hp": 44, "atk": 13, "def": 13, "spd": 15},
        "moves": [
            {"name": "Hypno Beam", "power": 15, "accuracy": 95, "desc": "Can confuse foe."},
            {"name": "Light Wave", "power": 13, "accuracy": 100, "desc": "Solid digital hit."},
            {"name": "Guard Light", "power": 0, "accuracy": 100, "desc": "Greatly boosts defense."},
            {"name": "Lumin Crash", "power": 17, "accuracy": 85, "desc": "Big, risky."}
        ]
    },
    {
        "num": 118, "name": "Venturoar", "type": "Structure", "rarity": "Common", "evolution": "VenturoarX",
        "description": "Hides in ventilation shafts.",
        "stats": {"hp": 37, "atk": 11, "def": 11, "spd": 14},
        "moves": [
            {"name": "Vent Whirl", "power": 12, "accuracy": 100, "desc": "Can blind foe."},
            {"name": "Echo Strike", "power": 11, "accuracy": 95, "desc": "Quick hit."},
            {"name": "Air Guard", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Roar Blast", "power": 15, "accuracy": 90, "desc": "Loud, may stun."}
        ]
    },
    {
        "num": 119, "name": "VenturoarX", "type": "Structure", "rarity": "Rare", "evolution": None,
        "description": "Roars like a beast in ducts.",
        "stats": {"hp": 45, "atk": 15, "def": 13, "spd": 13},
        "moves": [
            {"name": "Mega Roar", "power": 17, "accuracy": 95, "desc": "Can stun all enemies."},
            {"name": "Steel Bash", "power": 14, "accuracy": 100, "desc": "Strong metallic hit."},
            {"name": "Guard Shell", "power": 0, "accuracy": 100, "desc": "Greatly boosts defense."},
            {"name": "Duct Quake", "power": 18, "accuracy": 85, "desc": "Field shaking."}
        ]
    },
    {
        "num": 120, "name": "Infestine", "type": "Bio-Parasite", "rarity": "Uncommon", "evolution": None,
        "description": "Grows only in hidden spaces.",
        "stats": {"hp": 40, "atk": 13, "def": 12, "spd": 14},
        "moves": [
            {"name": "Hidden Growth", "power": 14, "accuracy": 95, "desc": "Sneaky, may poison."},
            {"name": "Secret Strike", "power": 13, "accuracy": 100, "desc": "Fast, undetectable."},
            {"name": "Stealth Guard", "power": 0, "accuracy": 100, "desc": "Boosts defense and evasion."},
            {"name": "Infest Wave", "power": 17, "accuracy": 85, "desc": "Strong, random effect."}
        ]
    },
    {
        "num": 121, "name": "Flickshade", "type": "Spectre", "rarity": "Common", "evolution": "Flickphant",
        "description": "Flickers the lights just before storms.",
        "stats": {"hp": 38, "atk": 12, "def": 11, "spd": 13},
        "moves": [
            {"name": "Flicker Hit", "power": 12, "accuracy": 100, "desc": "May blind foe."},
            {"name": "Phantom Jab", "power": 13, "accuracy": 95, "desc": "Quick spectral strike."},
            {"name": "Shade Guard", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Lightning Scream", "power": 15, "accuracy": 90, "desc": "May paralyze."}
        ]
    },
    {
        "num": 122, "name": "Flickphant", "type": "Spectre", "rarity": "Uncommon", "evolution": None,
        "description": "Appears in thunderstorms.",
        "stats": {"hp": 45, "atk": 14, "def": 13, "spd": 14},
        "moves": [
            {"name": "Phantom Crash", "power": 16, "accuracy": 95, "desc": "Strong, may confuse."},
            {"name": "Thunder Shade", "power": 15, "accuracy": 100, "desc": "Shock and fear."},
            {"name": "Veil Guard", "power": 0, "accuracy": 100, "desc": "Boosts own defense."},
            {"name": "Flicker Doom", "power": 18, "accuracy": 85, "desc": "Huge attack, rare miss."}
        ]
    },
    {
        "num": 123, "name": "Brickurn", "type": "Structure", "rarity": "Rare", "evolution": None,
        "description": "Turns broken bricks to dust.",
        "stats": {"hp": 46, "atk": 15, "def": 15, "spd": 12},
        "moves": [
            {"name": "Dust Eruption", "power": 17, "accuracy": 95, "desc": "Clouds all enemies."},
            {"name": "Brick Bash", "power": 15, "accuracy": 100, "desc": "Heavy structural hit."},
            {"name": "Fortify", "power": 0, "accuracy": 100, "desc": "Greatly boosts defense."},
            {"name": "Wall Break", "power": 19, "accuracy": 85, "desc": "Very strong, risky."}
        ]
    },
    {
        "num": 124, "name": "Cryptmoss", "type": "Bio-Parasite", "rarity": "Uncommon", "evolution": None,
        "description": "Hides under loose floorboards.",
        "stats": {"hp": 39, "atk": 13, "def": 12, "spd": 14},
        "moves": [
            {"name": "Hidden Spread", "power": 13, "accuracy": 95, "desc": "May poison."},
            {"name": "Moss Ambush", "power": 14, "accuracy": 100, "desc": "Sneaky, undetectable."},
            {"name": "Rot Guard", "power": 0, "accuracy": 100, "desc": "Boosts defense."},
            {"name": "Creep Swarm", "power": 16, "accuracy": 85, "desc": "Many little attacks."}
        ]
    },
    {
        "num": 125, "name": "Toxiburst", "type": "Climat", "rarity": "Rare", "evolution": None,
        "description": "Releases poisonous air in old basements.",
        "stats": {"hp": 43, "atk": 16, "def": 12, "spd": 13},
        "moves": [
            {"name": "Toxic Wave", "power": 17, "accuracy": 95, "desc": "Can poison all."},
            {"name": "Basement Cloud", "power": 15, "accuracy": 100, "desc": "Lingering poison."},
            {"name": "Aero Shield", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Poison Blast", "power": 19, "accuracy": 85, "desc": "Extremely risky, huge."}
        ]
    },
    {
        "num": 126, "name": "Siltgeist", "type": "Spectre", "rarity": "Rare", "evolution": None,
        "description": "Makes concrete vibrate with fear.",
        "stats": {"hp": 45, "atk": 15, "def": 13, "spd": 15},
        "moves": [
            {"name": "Silt Shock", "power": 16, "accuracy": 95, "desc": "May paralyze."},
            {"name": "Vibration", "power": 15, "accuracy": 100, "desc": "Can lower foe defense."},
            {"name": "Ghost Guard", "power": 0, "accuracy": 100, "desc": "Boosts defense sharply."},
            {"name": "Hauntquake", "power": 18, "accuracy": 85, "desc": "Massive attack."}
        ]
    },
    {
        "num": 127, "name": "Paraspore", "type": "Bio-Parasite", "rarity": "Rare", "evolution": None,
        "description": "Fills vents with hallucinogenic spores.",
        "stats": {"hp": 41, "atk": 15, "def": 12, "spd": 15},
        "moves": [
            {"name": "Spore Dream", "power": 16, "accuracy": 95, "desc": "May confuse."},
            {"name": "Mushroom Fog", "power": 14, "accuracy": 100, "desc": "Reduces enemy defense."},
            {"name": "Psyche Shield", "power": 0, "accuracy": 100, "desc": "Boosts evasion."},
            {"name": "Hallucinate", "power": 18, "accuracy": 85, "desc": "Random powerful effect."}
        ]
    },
    {
        "num": 128, "name": "Pylonix", "type": "Structure", "rarity": "Uncommon", "evolution": None,
        "description": "Merges with metal beams.",
        "stats": {"hp": 44, "atk": 13, "def": 15, "spd": 12},
        "moves": [
            {"name": "Metal Bash", "power": 14, "accuracy": 95, "desc": "Solid metal hit."},
            {"name": "Fusion Slam", "power": 13, "accuracy": 100, "desc": "Strong, reliable."},
            {"name": "Pylon Guard", "power": 0, "accuracy": 100, "desc": "Greatly boosts defense."},
            {"name": "Steel Shout", "power": 17, "accuracy": 85, "desc": "Loud, stuns enemy."}
        ]
    },
    {
        "num": 129, "name": "Rotoglyph", "type": "Structure", "rarity": "Rare", "evolution": None,
        "description": "Etches warning symbols in steel.",
        "stats": {"hp": 45, "atk": 16, "def": 13, "spd": 12},
        "moves": [
            {"name": "Glyph Etch", "power": 17, "accuracy": 95, "desc": "May paralyze."},
            {"name": "Warning Slam", "power": 15, "accuracy": 100, "desc": "Solid, heavy hit."},
            {"name": "Steel Guard", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Iron Burst", "power": 19, "accuracy": 85, "desc": "Massive, risky."}
        ]
    },
    {
        "num": 130, "name": "Neoncrypt", "type": "Numérique", "rarity": "Rare", "evolution": None,
        "description": "Hides in neon signs, corrupts their glow.",
        "stats": {"hp": 44, "atk": 15, "def": 14, "spd": 16},
        "moves": [
            {"name": "Neon Strike", "power": 17, "accuracy": 95, "desc": "May confuse."},
            {"name": "Glow Hack", "power": 15, "accuracy": 100, "desc": "Digital glow hit."},
            {"name": "Flash Guard", "power": 0, "accuracy": 100, "desc": "Boosts evasion."},
            {"name": "Sign Burst", "power": 19, "accuracy": 85, "desc": "Loud and risky."}
        ]
    },
    {
        "num": 131, "name": "Glitchara", "type": "Numérique", "rarity": "Rare", "evolution": None,
        "description": "Generates endless error messages.",
        "stats": {"hp": 45, "atk": 16, "def": 13, "spd": 15},
        "moves": [
            {"name": "Error Spam", "power": 16, "accuracy": 95, "desc": "Can paralyze."},
            {"name": "Crash Flood", "power": 15, "accuracy": 100, "desc": "Big digital hit."},
            {"name": "Glitch Guard", "power": 0, "accuracy": 100, "desc": "Boosts own defense."},
            {"name": "Infinite Loop", "power": 18, "accuracy": 85, "desc": "Devastating, rare hit."}
        ]
    },
    {
        "num": 132, "name": "Dampraze", "type": "Climat", "rarity": "Rare", "evolution": None,
        "description": "Causes steam explosions.",
        "stats": {"hp": 45, "atk": 16, "def": 13, "spd": 13},
        "moves": [
            {"name": "Steam Burst", "power": 17, "accuracy": 95, "desc": "May burn all foes."},
            {"name": "Pressure Shock", "power": 15, "accuracy": 100, "desc": "Strong hit."},
            {"name": "Boil Guard", "power": 0, "accuracy": 100, "desc": "Reduces next attack's power."},
            {"name": "Explosion", "power": 20, "accuracy": 80, "desc": "Ultimate, very risky."}
        ]
    },
    {
        "num": 133, "name": "Fraywatt", "type": "Énergie", "rarity": "Uncommon", "evolution": None,
        "description": "Can unravel whole circuits.",
        "stats": {"hp": 44, "atk": 13, "def": 15, "spd": 13},
        "moves": [
            {"name": "Unravel Hit", "power": 14, "accuracy": 95, "desc": "Can lower defense."},
            {"name": "Circuit Bite", "power": 13, "accuracy": 100, "desc": "Sharp attack."},
            {"name": "Spark Guard", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Fry Surge", "power": 17, "accuracy": 85, "desc": "Strong, may paralyze."}
        ]
    },
    {
        "num": 134, "name": "Patchmoss", "type": "Bio-Parasite", "rarity": "Common", "evolution": "Patchmourn",
        "description": "Patches cracks with living moss.",
        "stats": {"hp": 36, "atk": 11, "def": 12, "spd": 13},
        "moves": [
            {"name": "Patch Up", "power": 11, "accuracy": 100, "desc": "Heals self slightly."},
            {"name": "Moss Wrap", "power": 12, "accuracy": 95, "desc": "May poison foe."},
            {"name": "Green Guard", "power": 0, "accuracy": 100, "desc": "Boosts own defense."},
            {"name": "Crack Trap", "power": 14, "accuracy": 90, "desc": "Can trap enemy."}
        ]
    },
    {
        "num": 135, "name": "Patchmourn", "type": "Bio-Parasite", "rarity": "Uncommon", "evolution": None,
        "description": "Haunts patched walls.",
        "stats": {"hp": 44, "atk": 13, "def": 13, "spd": 13},
        "moves": [
            {"name": "Mourn Lash", "power": 15, "accuracy": 95, "desc": "Sad, but strong."},
            {"name": "Haunt Guard", "power": 0, "accuracy": 100, "desc": "Raises defense and attack."},
            {"name": "Patch Slam", "power": 13, "accuracy": 100, "desc": "Reliable."},
            {"name": "Revenant Bite", "power": 17, "accuracy": 85, "desc": "Risky, huge damage."}
        ]
    },
    {
        "num": 136, "name": "Thermiwisp", "type": "Climat", "rarity": "Uncommon", "evolution": None,
        "description": "Swirls of warm and cold air.",
        "stats": {"hp": 41, "atk": 13, "def": 13, "spd": 14},
        "moves": [
            {"name": "Thermal Wave", "power": 14, "accuracy": 95, "desc": "May burn or chill foe."},
            {"name": "Swirl Strike", "power": 13, "accuracy": 100, "desc": "Fast, reliable."},
            {"name": "Wisp Guard", "power": 0, "accuracy": 100, "desc": "Boosts evasion."},
            {"name": "Mix Blast", "power": 16, "accuracy": 85, "desc": "Random effect."}
        ]
    },
    {
        "num": 137, "name": "Hackgeist", "type": "Numérique", "rarity": "Rare", "evolution": None,
        "description": "Haunts smart home systems.",
        "stats": {"hp": 45, "atk": 15, "def": 14, "spd": 15},
        "moves": [
            {"name": "Hack Pulse", "power": 16, "accuracy": 95, "desc": "Can paralyze."},
            {"name": "Ghost Data", "power": 15, "accuracy": 100, "desc": "May confuse."},
            {"name": "Firewall Guard", "power": 0, "accuracy": 100, "desc": "Boosts own defense."},
            {"name": "Crash Storm", "power": 18, "accuracy": 85, "desc": "Major damage, rare hit."}
        ]
    },
    {
        "num": 138, "name": "Moldwraith", "type": "Bio-Parasite", "rarity": "Rare", "evolution": None,
        "description": "Possesses abandoned apartments.",
        "stats": {"hp": 45, "atk": 16, "def": 13, "spd": 14},
        "moves": [
            {"name": "Wraith Lash", "power": 17, "accuracy": 95, "desc": "Haunted, strong."},
            {"name": "Mold Mist", "power": 15, "accuracy": 100, "desc": "Poisonous."},
            {"name": "Spoil Guard", "power": 0, "accuracy": 100, "desc": "Raises own defense."},
            {"name": "Haunt Rage", "power": 19, "accuracy": 85, "desc": "Huge, may stun."}
        ]
    },
    {
        "num": 139, "name": "Vitralisk", "type": "Structure", "rarity": "Rare", "evolution": None,
        "description": "Controls colored glass windows.",
        "stats": {"hp": 45, "atk": 16, "def": 14, "spd": 13},
        "moves": [
            {"name": "Glass Crash", "power": 16, "accuracy": 95, "desc": "Cuts foe's defense."},
            {"name": "Prism Slash", "power": 15, "accuracy": 100, "desc": "Colorful, powerful."},
            {"name": "Light Guard", "power": 0, "accuracy": 100, "desc": "Boosts own evasion."},
            {"name": "Crystal Burst", "power": 18, "accuracy": 85, "desc": "Very risky, huge."}
        ]
    },
    {
        "num": 140, "name": "Furnaceek", "type": "Climat", "rarity": "Rare", "evolution": None,
        "description": "Appears only during winter storms.",
        "stats": {"hp": 46, "atk": 16, "def": 13, "spd": 13},
        "moves": [
            {"name": "Blizzard Breath", "power": 16, "accuracy": 95, "desc": "May freeze."},
            {"name": "Storm Strike", "power": 15, "accuracy": 100, "desc": "Strong, relentless."},
            {"name": "Fire Guard", "power": 0, "accuracy": 100, "desc": "Greatly raises defense."},
            {"name": "Inferno", "power": 19, "accuracy": 85, "desc": "Burns all."}
        ]
    },
    {
        "num": 141, "name": "Basalgon", "type": "Structure", "rarity": "Legendary", "evolution": None,
        "description": "Ancient and nearly indestructible.",
        "stats": {"hp": 62, "atk": 20, "def": 22, "spd": 12},
        "moves": [
            {"name": "Basalt Smash", "power": 22, "accuracy": 95, "desc": "Colossal hit."},
            {"name": "Titan Guard", "power": 0, "accuracy": 100, "desc": "Raises defense sharply."},
            {"name": "Seismic Quake", "power": 20, "accuracy": 90, "desc": "May stun."},
            {"name": "Eternal Wall", "power": 0, "accuracy": 100, "desc": "Negates one attack."}
        ]
    },
    {
        "num": 142, "name": "Miasmax", "type": "Climat", "rarity": "Legendary", "evolution": None,
        "description": "Its breath is pure toxicity.",
        "stats": {"hp": 58, "atk": 21, "def": 18, "spd": 17},
        "moves": [
            {"name": "Toxic Tempest", "power": 22, "accuracy": 95, "desc": "Poisons all foes."},
            {"name": "Poison Shield", "power": 0, "accuracy": 100, "desc": "Heals and raises defense."},
            {"name": "Gas Wave", "power": 19, "accuracy": 100, "desc": "May confuse."},
            {"name": "Final Breath", "power": 25, "accuracy": 80, "desc": "Ultimate, low accuracy."}
        ]
    },
    {
        "num": 143, "name": "Overlordis", "type": "Énergie", "rarity": "Legendary", "evolution": None,
        "description": "Can power or destroy entire buildings.",
        "stats": {"hp": 60, "atk": 22, "def": 20, "spd": 18},
        "moves": [
            {"name": "Power Surge", "power": 23, "accuracy": 95, "desc": "Major damage."},
            {"name": "Overdrive", "power": 0, "accuracy": 100, "desc": "Boosts all stats."},
            {"name": "Shockquake", "power": 21, "accuracy": 100, "desc": "Stuns all enemies."},
            {"name": "Absolute Strike", "power": 26, "accuracy": 75, "desc": "Can KO in one hit."}
        ]
    },
    {
        "num": 144, "name": "Holohex", "type": "Numérique", "rarity": "Legendary", "evolution": None,
        "description": "Glitch so rare it exists in two places at once.",
        "stats": {"hp": 57, "atk": 18, "def": 19, "spd": 23},
        "moves": [
            {"name": "Duality Glitch", "power": 21, "accuracy": 90, "desc": "Hits twice, may confuse."},
            {"name": "Data Wrap", "power": 0, "accuracy": 100, "desc": "Boosts defense and speed."},
            {"name": "Holo Beam", "power": 20, "accuracy": 100, "desc": "Blinding light."},
            {"name": "Reality Split", "power": 25, "accuracy": 80, "desc": "May stun, may miss."}
        ]
    },
    {
        "num": 145, "name": "Necrocrypt", "type": "Spectre", "rarity": "Legendary", "evolution": None,
        "description": "Brings old blueprints back to life.",
        "stats": {"hp": 59, "atk": 21, "def": 19, "spd": 19},
        "moves": [
            {"name": "Blueprint Bind", "power": 20, "accuracy": 95, "desc": "Can trap enemy."},
            {"name": "Soul Rise", "power": 0, "accuracy": 100, "desc": "Heals and boosts own stats."},
            {"name": "Crypt Wail", "power": 22, "accuracy": 100, "desc": "Ghostly damage."},
            {"name": "Afterlife Pulse", "power": 24, "accuracy": 85, "desc": "Might KO."}
        ]
    },
    {
        "num": 146, "name": "Rotolyth", "type": "Structure", "rarity": "Legendary", "evolution": None,
        "description": "Rewrites the rules of gravity in ruins.",
        "stats": {"hp": 62, "atk": 20, "def": 22, "spd": 14},
        "moves": [
            {"name": "Gravity Flip", "power": 23, "accuracy": 90, "desc": "May confuse."},
            {"name": "Ruins Guard", "power": 0, "accuracy": 100, "desc": "Negates next attack."},
            {"name": "Collapse", "power": 21, "accuracy": 100, "desc": "All foes hit."},
            {"name": "Endless Fall", "power": 25, "accuracy": 80, "desc": "Ultimate risk."}
        ]
    },
    {
        "num": 147, "name": "Paradoxul", "type": "Bio-Parasite", "rarity": "Legendary", "evolution": None,
        "description": "Can both heal and corrupt a building.",
        "stats": {"hp": 58, "atk": 19, "def": 20, "spd": 20},
        "moves": [
            {"name": "Heal/Corrupt", "power": 0, "accuracy": 100, "desc": "Heals self, hurts foe."},
            {"name": "Paradox Bite", "power": 23, "accuracy": 95, "desc": "Wild effect each use."},
            {"name": "Dual Spore", "power": 20, "accuracy": 100, "desc": "May poison or heal enemy."},
            {"name": "Time Loop", "power": 24, "accuracy": 85, "desc": "Can attack twice."}
        ]
    },
    {
        "num": 148, "name": "Etherwatt", "type": "Énergie", "rarity": "Legendary", "evolution": None,
        "description": "Pure energy, impossible to trap.",
        "stats": {"hp": 56, "atk": 23, "def": 18, "spd": 22},
        "moves": [
            {"name": "Ether Shock", "power": 25, "accuracy": 90, "desc": "Massive power, rare miss."},
            {"name": "Light Shield", "power": 0, "accuracy": 100, "desc": "Immune one turn."},
            {"name": "Energy Burst", "power": 22, "accuracy": 100, "desc": "Speed-based."},
            {"name": "Endless Current", "power": 26, "accuracy": 75, "desc": "Ultimate, huge risk."}
        ]
    },
    {
        "num": 149, "name": "Binalis", "type": "Numérique", "rarity": "Legendary", "evolution": None,
        "description": "Exists only in code, but affects the real world.",
        "stats": {"hp": 58, "atk": 19, "def": 21, "spd": 21},
        "moves": [
            {"name": "Code Crash", "power": 23, "accuracy": 95, "desc": "May stun foe."},
            {"name": "Digital Guard", "power": 0, "accuracy": 100, "desc": "Raises all stats."},
            {"name": "Reality Warp", "power": 21, "accuracy": 100, "desc": "Hits all enemies."},
            {"name": "Binary Storm", "power": 25, "accuracy": 80, "desc": "Risky, multi-hit."}
        ]
    },
    {
        "num": 150, "name": "Spectrion", "type": "Spectre", "rarity": "Legendary", "evolution": None,
        "description": "The king of all hauntings.",
        "stats": {"hp": 59, "atk": 21, "def": 19, "spd": 19},
        "moves": [
            {"name": "Haunt King", "power": 23, "accuracy": 95, "desc": "Can terrify."},
            {"name": "Specter Guard", "power": 0, "accuracy": 100, "desc": "Negates one attack."},
            {"name": "Nightmare Pulse", "power": 21, "accuracy": 100, "desc": "May put foe to sleep."},
            {"name": "Eternal Gloom", "power": 27, "accuracy": 70, "desc": "Ultimate, very risky."}
        ]
    },
    {
        "num": 151, "name": "MYİKKİMONE", "type": "Climat", "rarity": "Legendary", "evolution": None,
        "description": "Legendary spirit, protects homes forever.",
        "stats": {"hp": 64, "atk": 20, "def": 22, "spd": 20},
        "moves": [
            {"name": "Sanctuary", "power": 0, "accuracy": 100, "desc": "Heals all allies, boosts defense."},
            {"name": "MYİKKİ Wrath", "power": 26, "accuracy": 90, "desc": "Signature move, massive power."},
            {"name": "Memory Storm", "power": 23, "accuracy": 100, "desc": "May stun and confuse."},
            {"name": "Infinity Shield", "power": 0, "accuracy": 100, "desc": "Invincible for one turn."}
        ]
    }
    ]

def patch_collections_with_stats(players, domon_list):
    name2domon = {d['name']: d for d in domon_list}
    updated = 0
    for player in players.values():
        collection = player.get("collection", [])
        for d in collection:
            ref = name2domon.get(d.get("name"))
            if ref:
                for field in ["num", "type", "rarity", "evolution", "description", "stats", "moves"]:
                    d[field] = ref[field]
                updated += 1
    return updated

# ---- Initialisation & PATCH ----
print("Downloading player data from Dropbox (startup)...")
download_players_dropbox()
players = load_players()
config = load_config()

nb = patch_collections_with_stats(players, DOMON_LIST)
if nb > 0:
    save_players(players)
    print(f"✅ PATCH collections: {nb} DOMON(s) mis à jour avec stats/moves.")
else:
    print("✅ PATCH collections: aucun DOMON à mettre à jour ou déjà au bon format.")

print("Player and config data loaded.")

# --- Other constants ---
RARITY_PROBA = {"Common": 55, "Uncommon": 24, "Rare": 14, "Legendary": 7}
STARTER_PACK = {"Domoball": 5, "Scan Tool": 1, "PerfectDomoball": 0}
DAILY_REWARDS = {
    "Domoball": 6,
    "bonus_items": [
        "Scan Tool", "Small Repair Kit", "CryptoStamp", "Architectrap",
        "SpectraSeal", "BIMNet", "PerfectDomoball"
    ]
}

def domon_intro_message(domon):
    rare = domon['rarity']
    name = domon['name']
    intro_common = f"A wild DOMON appeared!\n**#{domon['num']:03d} {name}**"
    intro_uncommon = f"⚡ An uncommon DOMON has emerged!\n**#{domon['num']:03d} {name}**"
    intro_rare = f"✨ A rare DOMON materializes before you!\n**#{domon['num']:03d} {name}**"
    intro_legendary = (
        f"🌟🌟🌟 LEGENDARY ALERT! 🌟🌟🌟\n"
        f"🔥 A **LEGENDARY DOMON** has appeared!\n"
        f"**#{domon['num']:03d} {name}**"
    )
    return {
        "Common": intro_common,
        "Uncommon": intro_uncommon,
        "Rare": intro_rare,
        "Legendary": intro_legendary
    }.get(rare, intro_common)

bot_ready = False

@bot.event
async def on_ready():
    global bot_ready
    print(f"Bot ready as {bot.user}!")
    await asyncio.sleep(2)
    bot_ready = True
    spawn_task.start()

def not_ready(ctx):
    return not bot_ready or players is None or config is None

async def timeout_scan(ctx):
    global scan_timer_task
    await asyncio.sleep(120)
    s = load_state()
    if s["active_spawn"] and s["scan_claimed"]:
        scan_expired()
        await ctx.send("⏰ Time's up! The DOMON was not captured. Anyone can !scan again.")
    scan_timer_task = None
    
# === COMMANDS ===

@bot.command(name="commands")
async def commands_cmd(ctx):
    if not_ready(ctx):
        await ctx.send("Bot is still initializing. Try again in a few seconds!")
        return
    embed = discord.Embed(title="MYİKKİ DOMON Commands", color=0x82eefd)
    embed.description = """
**!start** : Start your DOMON adventure  
**!daily** : Get your daily Domoballs (6/day) + 1 bonus item  
**!inventory** : Show your inventory  
**!collection** : View your captured DOMON  
**!domodex** : Complete DOMON list  
**!info <name/num>** : Info on a DOMON  
**!use <item>** : Use an item (all items have a use!)  
**!scan** : Scan the DOMON (required before capture!)  
**!capture** : Attempt to catch (only first scanner can capture)  
**!addballs <amount>** : (Admin) Add Domoballs  
**!setspawn** : (Admin) Set current channel for DOMON spawns  
**!forcespawn** : (Admin) Force a DOMON to appear  
    """
    await ctx.send(embed=embed)

@bot.command(name="setspawn")
async def set_spawn_channel(ctx):
    if not_ready(ctx):
        await ctx.send("Bot is still initializing. Try again in a few seconds!")
        return
    authorized_id = "865185894197887018"
    if str(ctx.author.id) != authorized_id:
        await ctx.send("❌ Only the bot owner can use this command.")
        return
    config["spawn_channel_id"] = ctx.channel.id
    save_config(config)
    await ctx.send("✅ This channel is now the official DOMON spawn point!")

@bot.command(name="addballs")
async def addballs(ctx, amount: int):
    if not_ready(ctx):
        await ctx.send("Bot is still initializing. Try again in a few seconds!")
        return
    authorized_id = "865185894197887018"
    if str(ctx.author.id) != authorized_id:
        await ctx.send("❌ Only the bot owner can use this command.")
        return
    user_id = str(ctx.author.id)
    if user_id not in players:
        await ctx.send("Start the game first with !start")
        return
    players[user_id]["inventory"]["Domoball"] = players[user_id]["inventory"].get("Domoball", 0) + amount
    save_players(players)
    await ctx.send(f"✅ You received {amount} Domoballs.")

@bot.command(name="start")
async def start_game(ctx):
    if not_ready(ctx):
        await ctx.send("Bot is still initializing. Try again in a few seconds!")
        return
    user_id = str(ctx.author.id)
    if user_id not in players:
        players[user_id] = {
            "inventory": STARTER_PACK.copy(),
            "collection": [],
            "xp": 0,
            "captures": {},
            "daily": None,
            "evolutions": {},
        }
        save_players(players)
        await ctx.send(f"{ctx.author.mention} Welcome to MYİKKİ DOMON HUNT!\nYou receive: 5 Domoballs and 1 Scan Tool! Type !inventory to see your items.")
    else:
        await ctx.send("You already have an account! Use !inventory.")

@bot.command(name="daily")
async def daily(ctx):
    if not_ready(ctx):
        await ctx.send("Bot is still initializing. Try again in a few seconds!")
        return
    tz = pytz.timezone("Europe/Paris")
    now = datetime.now(tz).date()
    user_id = str(ctx.author.id)
    player = players.get(user_id)
    if not player:
        await ctx.send("Type !start to begin your hunt!")
        return
    if player["daily"] == str(now):
        await ctx.send("You already claimed your daily reward today!")
        return
    player["daily"] = str(now)
    player["inventory"]["Domoball"] = player["inventory"].get("Domoball", 0) + DAILY_REWARDS["Domoball"]
    if random.randint(1, 100) == 1:
        bonus = "PerfectDomoball"
    else:
        bonus = random.choice([i for i in DAILY_REWARDS["bonus_items"] if i != "PerfectDomoball"])
    player["inventory"][bonus] = player["inventory"].get(bonus, 0) + 1
    save_players(players)
    if bonus == "PerfectDomoball":
        await ctx.send(f"{ctx.author.mention} received 6 Domoballs and... 🟣 **A PERFECTDOMOBALL!** Ultra-rare!")
    else:
        await ctx.send(f"{ctx.author.mention} received 6 Domoballs and 1 bonus item: **{bonus}**!")

@bot.command(name="inventory")
async def inventory(ctx):
    if not_ready(ctx):
        await ctx.send("Bot is still initializing. Try again in a few seconds!")
        return
    user_id = str(ctx.author.id)
    player = players.get(user_id)
    if not player:
        await ctx.send("Type !start to begin your hunt!")
        return
    embed = discord.Embed(title=f"{ctx.author.display_name}'s Inventory", color=0xFFD700)
    for k, v in player["inventory"].items():
        embed.add_field(name=k, value=str(v), inline=True)
    await ctx.send(embed=embed)

@bot.command(name="collection")
async def collection(ctx):
    if not_ready(ctx):
        await ctx.send("Bot is still initializing. Try again in a few seconds!")
        return
    user_id = str(ctx.author.id)
    player = players.get(user_id)
    if not player:
        await ctx.send("Type !start to begin your hunt!")
        return
    if not player["collection"]:
        await ctx.send("You haven't captured any DOMON yet!")
        return
    embed = discord.Embed(title=f"{ctx.author.display_name}'s Domon Collection", color=0x7DF9FF)
    txt = ""
    for d in player["collection"]:
        txt += f"#{d['num']} {d['name']} ({d['rarity']})\n"
    embed.description = txt
    await ctx.send(embed=embed)

@bot.command(name="domodex")
async def domodex(ctx):
    if not_ready(ctx):
        await ctx.send("Bot is still initializing. Try again in a few seconds!")
        return
    embed = discord.Embed(title="DOMODEX – Complete List", color=0x6e34ff)
    domotxt = ""
    for d in DOMON_LIST:
        domotxt += f"#{d['num']:03d} {d['name']} ({d['type']}, {d['rarity']})\n"
    embed.description = domotxt[:4000]
    await ctx.send(embed=embed)

@bot.command(name="info")
async def domon_info(ctx, *, name_or_num: str):
    if not_ready(ctx):
        await ctx.send("Bot is still initializing. Try again in a few seconds!")
        return
    domon = next((d for d in DOMON_LIST if d["name"].lower() == name_or_num.lower() or str(d["num"]) == name_or_num), None)
    if not domon:
        await ctx.send("Unknown DOMON.")
        return
    embed = discord.Embed(title=f"DOMODEX #{domon['num']:03d} — {domon['name']}", color=0x8effa2)
    embed.add_field(name="Type", value=domon['type'])
    embed.add_field(name="Rarity", value=domon['rarity'])
    if domon.get("evolution"):
        embed.add_field(name="Evolution", value=domon['evolution'])
    embed.add_field(name="Description", value=domon['description'], inline=False)
    await ctx.send(embed=embed)

@bot.command(name="use")
async def use_item(ctx, *, item_name: str):
    if not_ready(ctx):
        await ctx.send("Bot is still initializing. Try again in a few seconds!")
        return
    user_id = str(ctx.author.id)
    player = players.get(user_id)
    if not player:
        await ctx.send("Type !start to begin your hunt!")
        return
    inv = player["inventory"]
    normalized = item_name.strip().title().replace("Perfectdomoball", "PerfectDomoball")
    if normalized not in inv or inv[normalized] <= 0:
        await ctx.send(f"You don't have any **{normalized}**.")
        return
    if normalized == "Scan Tool":
        await ctx.send("Use !scan instead! The scan tool is always available for scanning DOMONs.")
    elif normalized == "Small Repair Kit":
        player["xp"] += 1
        await ctx.send(f"🔧 {ctx.author.mention} used a **Small Repair Kit** and gained +1 XP!")
    elif normalized == "CryptoStamp":
        bonus = random.choice([i for i in DAILY_REWARDS["bonus_items"] if i != "PerfectDomoball"])
        player["inventory"][bonus] = player["inventory"].get(bonus, 0) + 1
        await ctx.send(f"📦 {ctx.author.mention} used a **CryptoStamp** and received 1 bonus item: **{bonus}**!")
    elif normalized == "Architectrap":
        player["xp"] += 1
        await ctx.send(f"🪤 {ctx.author.mention} used an **Architectrap**! Next DOMON you capture has double XP!")
    elif normalized == "SpectraSeal":
        await ctx.send(f"🔒 {ctx.author.mention} used a **SpectraSeal**! Your next DOMON can't escape if you succeed.")
    elif normalized == "BIMNet":
        await ctx.send(f"🕸️ {ctx.author.mention} used a **BIMNet**! DOMON spawn rate doubled for 30 min. (Effect simulation)")
    elif normalized == "PerfectDomoball":
        await ctx.send("Use the PerfectDomoball directly during capture with !capture! It will always succeed.")
    else:
        await ctx.send("This item has no defined use yet.")
    inv[normalized] -= 1
    if inv[normalized] <= 0:
        del inv[normalized]
    save_players(players)

@tasks.loop(minutes=15)
async def spawn_task():
    if not bot_ready or state["active_spawn"] or not config.get("spawn_channel_id"):
        return
    domon = random.choices(DOMON_LIST, weights=[RARITY_PROBA.get(d["rarity"], 10) for d in DOMON_LIST], k=1)[0]
    set_spawned_domon(domon)
    channel = bot.get_channel(config["spawn_channel_id"])
    if channel:
        intro_msg = domon_intro_message(domon)
        await channel.send(
            f"{intro_msg}\n"
            f"Type: {domon['type']} | Rarity: {domon['rarity']}\n_Description_: {domon['description']}\n"
            "Type !scan to be the first to scan and unlock the right to capture it!"
        )

@bot.command(name="scan")
async def scan(ctx):
    global scan_timer_task
    async with scan_lock:
        s = load_state()
        if not s["active_spawn"] or not s["spawned_domon"]:
            await ctx.send("No DOMON to scan right now.")
            return
        if s["scan_claimed"]:
            await ctx.send("Someone already scanned this DOMON! Only the first scanner can attempt capture.")
            return
        if str(ctx.author.id) not in players:
            await ctx.send("Type !start to begin your hunt!")
            return
        claim_scan(str(ctx.author.id))
        domon = get_current_domon()
        await ctx.send(
            f"🔍 {ctx.author.mention} scanned the DOMON first!\n"
            f"DOMON: **{domon['name']}**\n"
            f"Type: {domon['type']} | Rarity: {domon['rarity']}\n_Description_: {domon['description']}\n"
            "You are now the only one able to use !capture for this DOMON!\n"
            "⏰ You have **2 minutes** to capture it, or the DOMON will escape and scanning will reset!"
        )
        if scan_timer_task is None:
            scan_timer_task = asyncio.create_task(timeout_scan(ctx))

@bot.command(name="capture")
async def capture(ctx):
    global scan_timer_task
    async with scan_lock:
        s = load_state()
        user_id = str(ctx.author.id)
        player = players.get(user_id)
        domon = get_current_domon()
        # Gestion timer expiré (fail safe, jamais bloqué)
        if is_scan_expired():
            scan_expired()
            await ctx.send("⏰ Time's up! The DOMON was not captured. Anyone can !scan again.")
            scan_timer_task = None
            return
        if not s["active_spawn"] or not domon:
            await ctx.send("No DOMON to capture.")
            clear_spawn()
            return
        if not player:
            await ctx.send("Type !start to begin your hunt!")
            clear_spawn()
            return
        if s["scan_claimed"] != user_id:
            await ctx.send("Only the **first** player who scanned this DOMON can try to capture it!")
            clear_spawn()
            return
        if s["capture_attempted"] == user_id:
            await ctx.send("You have already tried to capture this DOMON. Wait for another scan!")
            clear_spawn()
            return
        if s["capture_attempted"] is not None:
            await ctx.send("A capture attempt has already been made for this DOMON. Wait for the next scan!")
            clear_spawn()
            return
        mark_attempt(user_id)

        has_perfect = player["inventory"].get("PerfectDomoball", 0) > 0
        has_regular = player["inventory"].get("Domoball", 0) > 0
        if not has_perfect and not has_regular:
            await ctx.send(
                f"{ctx.author.mention} you have no Domoballs or PerfectDomoball left! "
                "You lose the right to capture this DOMON. Someone else can now !scan and try!"
            )
            clear_spawn()
            return

        # Résultat direct
        if has_perfect:
            player["inventory"]["PerfectDomoball"] -= 1
            if player["inventory"]["PerfectDomoball"] == 0:
                del player["inventory"]["PerfectDomoball"]
            player["collection"].append(domon)
            player["xp"] += 2
            save_players(players)
            msg = (
                f"✨✨ **CRITICAL SUCCESS!** The DOMON can't resist!\n"
                f"{ctx.author.mention} used a **PerfectDomoball** and INSTANTLY captured **{domon['name']}**! +2 XP!"
            )
            evolution_msg = check_evolution(user_id)
            if evolution_msg:
                msg += f"\n{evolution_msg}"
            await ctx.send(msg)
            success_capture()
            return
        else:
            rates = {"Common": 0.90, "Uncommon": 0.65, "Rare": 0.30, "Legendary": 0.10}
            success = random.random() < rates.get(domon["rarity"], 0.5)
            player["inventory"]["Domoball"] -= 1
            if player["inventory"]["Domoball"] == 0:
                del player["inventory"]["Domoball"]
            if success:
                player["collection"].append(domon)
                player["xp"] += 1
                save_players(players)
                msg = f"🎉 {ctx.author.mention} captured **{domon['name']}**! Added to your collection. +1 XP."
                evolution_msg = check_evolution(user_id)
                if evolution_msg:
                    msg += f"\n{evolution_msg}"
                if player["xp"] % 10 == 0:
                    item = random.choice([i for i in DAILY_REWARDS["bonus_items"] if i != "PerfectDomoball"])
                    player["inventory"][item] = player["inventory"].get(item, 0) + 1
                    msg += f"\nYou reached {player['xp']} XP and received a bonus item: **{item}**!"
                await ctx.send(msg)
                success_capture()
                return
            else:
                fail_msgs = [
                    "❌ Oh no! The DOMON broke free!",
                    "The ball opened... The DOMON escaped!",
                    "So close... but it’s gone!",
                    "❌ The DOMON got away!"
                ]
                fail_msg = f"{random.choice(fail_msgs)}"
                await ctx.send(fail_msg)
                fail_capture()
                return

@bot.command(name="forcespawn")
async def forcespawn(ctx):
    authorized_id = "865185894197887018"
    if str(ctx.author.id) != authorized_id:
        await ctx.send("❌ Only the bot owner can use this command.")
        return
    if state["active_spawn"]:
        await ctx.send("⚠️ A DOMON is already spawned.")
        return
    domon = random.choice(DOMON_LIST)
    set_spawned_domon(domon)
    intro_msg = domon_intro_message(domon)
    await ctx.send(
        f"**(Admin)** {intro_msg}\n"
        f"Type: {domon['type']} | Rarity: {domon['rarity']}\n_Description_: {domon['description']}\n"
        "Type !scan to be the first to scan and unlock the right to capture it!"
    )

def check_evolution(user_id):
    player = players[user_id]
    collection = player["collection"]
    evolved_names = {d["name"] for d in collection}
    counts = {}
    for domon in collection:
        counts[domon["name"]] = counts.get(domon["name"], 0) + 1
    for domon in DOMON_LIST:
        if domon["evolution"] and domon["evolution"] not in evolved_names:
            base_name = domon["name"]
            evo_name = domon["evolution"]
            required = 3
            if counts.get(base_name, 0) >= required:
                evolved_domon = next((d for d in DOMON_LIST if d["name"] == evo_name), None)
                if evolved_domon:
                    collection.append(evolved_domon)
                    player["xp"] += 2
                    save_players(players)
                    return f"✨ Your {base_name} evolved into {evo_name}!"
    return None

keep_alive()
bot.run(TOKEN)

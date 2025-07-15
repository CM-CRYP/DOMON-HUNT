import os
import json
import discord
import random
import asyncio
from discord.ext import commands, tasks
from dotenv import load_dotenv

# === Pour keep-alive sur Render (anti-sommeil) ===
from threading import Thread
from flask import Flask

app = Flask('')

@app.route('/')
def home():
    return "MYİKKİ Domon Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# === Token Discord ===
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ====== BASE DE DONNÉES PERSISTANTE (JSON) ======
SAVE_FILE = "players.json"

def load_players():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {}

def save_players(players):
    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)

players = load_players()  # {user_id: {...infos joueur...}}
spawned_domon = None      # DOMON actuel dans le salon
spawn_channel_id = None   # Pour configurer où les DOMON spawnent
active_spawn = False

# ------- Liste des 151 DOMON (évolutions incluses) -------
DOMON_LIST = [
    {"num": 1, "name": "Craquos", "type": "Structure", "rarity": "Common", "evolution": "Fissuron", "description": "Small crack spirit, dwells in old walls."},
    {"num": 2, "name": "Fissuron", "type": "Structure", "rarity": "Uncommon", "evolution": "Seismorph", "description": "Its power shakes the foundations."},
    {"num": 3, "name": "Seismorph", "type": "Structure", "rarity": "Rare", "evolution": None, "description": "The king of structural tremors."},
    {"num": 4, "name": "Moldina", "type": "Bio-Parasite", "rarity": "Common", "evolution": "Moldarak", "description": "Mouldy spores haunt humid corners."},
    {"num": 5, "name": "Moldarak", "type": "Bio-Parasite", "rarity": "Uncommon", "evolution": "Sporusor", "description": "Spreads rapidly when ignored."},
    {"num": 6, "name": "Sporusor", "type": "Bio-Parasite", "rarity": "Rare", "evolution": None, "description": "Toxic, can corrupt an entire block!"},
    {"num": 7, "name": "Voltus", "type": "Énergie", "rarity": "Common", "evolution": "Voltark", "description": "Loves electric wires, flickers the lights."},
    {"num": 8, "name": "Voltark", "type": "Énergie", "rarity": "Uncommon", "evolution": "Voltaura", "description": "Grows strong near overloaded panels."},
    {"num": 9, "name": "Voltaura", "type": "Énergie", "rarity": "Rare", "evolution": None, "description": "Can short-circuit an entire building."},
    {"num": 10, "name": "Widowra", "type": "Spectre", "rarity": "Uncommon", "evolution": "Widowhex", "description": "Restless soul of a past owner."},
    {"num": 11, "name": "Widowhex", "type": "Spectre", "rarity": "Rare", "evolution": None, "description": "Haunts corridors during renovations."},
    {"num": 12, "name": "BIMbug", "type": "Numérique", "rarity": "Common", "evolution": "BIMphage", "description": "Digital glitch in the building's blueprint."},
    {"num": 13, "name": "BIMphage", "type": "Numérique", "rarity": "Uncommon", "evolution": "BIMgeist", "description": "Eats away at data models."},
    {"num": 14, "name": "BIMgeist", "type": "Numérique", "rarity": "Rare", "evolution": None, "description": "Causes plans to vanish mysteriously."},
    {"num": 15, "name": "Humidon", "type": "Climat", "rarity": "Common", "evolution": "Humistorm", "description": "Dampens rooms with chilly mist."},
    {"num": 16, "name": "Humistorm", "type": "Climat", "rarity": "Uncommon", "evolution": "Humicrypt", "description": "Makes paint peel from the walls."},
    {"num": 17, "name": "Humicrypt", "type": "Climat", "rarity": "Rare", "evolution": None, "description": "Turns entire homes into wet tombs."},
    {"num": 18, "name": "Crackmite", "type": "Structure", "rarity": "Common", "evolution": "Crumblex", "description": "Microscopic crack-maker."},
    {"num": 19, "name": "Crumblex", "type": "Structure", "rarity": "Uncommon", "evolution": None, "description": "Causes tiles to snap underfoot."},
    {"num": 20, "name": "Mycosor", "type": "Bio-Parasite", "rarity": "Uncommon", "evolution": None, "description": "Mould roots as tough as concrete."},
    {"num": 21, "name": "Cablon", "type": "Énergie", "rarity": "Common", "evolution": "Cablast", "description": "Bites through any cable."},
    {"num": 22, "name": "Cablast", "type": "Énergie", "rarity": "Uncommon", "evolution": None, "description": "Sparks fly in its wake."},
    {"num": 23, "name": "Echoz", "type": "Spectre", "rarity": "Common", "evolution": "Echomire", "description": "Leaves behind whispers and chills."},
    {"num": 24, "name": "Echomire", "type": "Spectre", "rarity": "Uncommon", "evolution": None, "description": "Makes every noise seem haunted."},
    {"num": 25, "name": "Glitchum", "type": "Numérique", "rarity": "Common", "evolution": "Glitchurn", "description": "Digital static entity."},
    {"num": 26, "name": "Glitchurn", "type": "Numérique", "rarity": "Uncommon", "evolution": None, "description": "Causes screens to flicker."},
    {"num": 27, "name": "Condensaur", "type": "Climat", "rarity": "Common", "evolution": "Condenshade", "description": "Brings indoor rain."},
    {"num": 28, "name": "Condenshade", "type": "Climat", "rarity": "Rare", "evolution": None, "description": "Causes mysterious puddles everywhere."},
    {"num": 29, "name": "Rotophan", "type": "Structure", "rarity": "Uncommon", "evolution": None, "description": "Rusts any metal structure."},
    {"num": 30, "name": "Smolder", "type": "Énergie", "rarity": "Rare", "evolution": None, "description": "Hidden fire risk, burns unseen."},
    {"num": 31, "name": "Drafton", "type": "Climat", "rarity": "Common", "evolution": "Drafterror", "description": "Summons sudden cold drafts."},
    {"num": 32, "name": "Drafterror", "type": "Climat", "rarity": "Uncommon", "evolution": None, "description": "Slams doors at random times."},
    {"num": 33, "name": "Spookbyte", "type": "Spectre", "rarity": "Common", "evolution": "Spookraft", "description": "Digital ghost in surveillance cams."},
    {"num": 34, "name": "Spookraft", "type": "Spectre", "rarity": "Rare", "evolution": None, "description": "Freezes all camera feeds."},
    {"num": 35, "name": "Netflux", "type": "Numérique", "rarity": "Common", "evolution": "Netfreak", "description": "Interferes with WiFi signals."},
    {"num": 36, "name": "Netfreak", "type": "Numérique", "rarity": "Uncommon", "evolution": None, "description": "Blocks all remote connections."},
    {"num": 37, "name": "Thermora", "type": "Climat", "rarity": "Common", "evolution": "Thermogone", "description": "Shifts temperatures at random."},
    {"num": 38, "name": "Thermogone", "type": "Climat", "rarity": "Rare", "evolution": None, "description": "Causes heating bills to explode."},
    {"num": 39, "name": "Crustorn", "type": "Structure", "rarity": "Rare", "evolution": None, "description": "Turns bricks into fragile shells."},
    {"num": 40, "name": "Surgebite", "type": "Énergie", "rarity": "Common", "evolution": "Surgerage", "description": "Causes sudden power spikes."},
    {"num": 41, "name": "Surgerage", "type": "Énergie", "rarity": "Uncommon", "evolution": None, "description": "Melts fuses with rage."},
    {"num": 42, "name": "Airspectra", "type": "Climat", "rarity": "Uncommon", "evolution": None, "description": "Haunts air vents and ducts."},
    {"num": 43, "name": "Funglint", "type": "Bio-Parasite", "rarity": "Common", "evolution": "Fungloom", "description": "Shiny mold with a bad attitude."},
    {"num": 44, "name": "Fungloom", "type": "Bio-Parasite", "rarity": "Rare", "evolution": None, "description": "Can darken a whole attic."},
    {"num": 45, "name": "Polterwatt", "type": "Énergie", "rarity": "Rare", "evolution": None, "description": "Ghost of an old electric generator."},
    {"num": 46, "name": "Betonghost", "type": "Structure", "rarity": "Uncommon", "evolution": None, "description": "Concrete spirit, impossible to exorcise."},
    {"num": 47, "name": "Sootveil", "type": "Climat", "rarity": "Uncommon", "evolution": None, "description": "Makes windows gray overnight."},
    {"num": 48, "name": "Filtrix", "type": "Structure", "rarity": "Rare", "evolution": None, "description": "Hides in ventilation, clogs air filters."},
    {"num": 49, "name": "Netrust", "type": "Numérique", "rarity": "Uncommon", "evolution": None, "description": "Disables all smart locks."},
    {"num": 50, "name": "Chillume", "type": "Climat", "rarity": "Common", "evolution": "Chillumeon", "description": "Frosty, likes to freeze pipes."},
    {"num": 51, "name": "Chillumeon", "type": "Climat", "rarity": "Rare", "evolution": None, "description": "Can burst an entire plumbing system."},
    {"num": 52, "name": "Thermold", "type": "Climat", "rarity": "Common", "evolution": "Thermoldra", "description": "Feeds on steam and hot showers."},
    {"num": 53, "name": "Thermoldra", "type": "Climat", "rarity": "Uncommon", "evolution": None, "description": "Leaves mildew everywhere."},
    {"num": 54, "name": "Screamroot", "type": "Spectre", "rarity": "Common", "evolution": "Screamora", "description": "Screams when floors creak."},
    {"num": 55, "name": "Screamora", "type": "Spectre", "rarity": "Rare", "evolution": None, "description": "Turns creaks into ghostly howls."},
    {"num": 56, "name": "Gutteron", "type": "Structure", "rarity": "Common", "evolution": "Guttergeist", "description": "Hides in gutters, blocks water flow."},
    {"num": 57, "name": "Guttergeist", "type": "Structure", "rarity": "Rare", "evolution": None, "description": "Causes sudden floods during storms."},
    {"num": 58, "name": "Virugrime", "type": "Bio-Parasite", "rarity": "Common", "evolution": "Virulurk", "description": "Infects every nook and cranny."},
    {"num": 59, "name": "Virulurk", "type": "Bio-Parasite", "rarity": "Uncommon", "evolution": None, "description": "Turns rooms into biohazards."},
    {"num": 60, "name": "Insulight", "type": "Énergie", "rarity": "Common", "evolution": "Insulash", "description": "Grows strong inside faulty insulation."},
    {"num": 61, "name": "Insulash", "type": "Énergie", "rarity": "Rare", "evolution": None, "description": "Releases sparks when cornered."},
    {"num": 62, "name": "Drainox", "type": "Climat", "rarity": "Common", "evolution": "Drainshade", "description": "Loves to clog pipes and drains."},
    {"num": 63, "name": "Drainshade", "type": "Climat", "rarity": "Uncommon", "evolution": None, "description": "Causes mysterious foul odors."},
    {"num": 64, "name": "Shadowdust", "type": "Spectre", "rarity": "Uncommon", "evolution": None, "description": "Darkens lightbulbs, chills air."},
    {"num": 65, "name": "Glimmette", "type": "Numérique", "rarity": "Common", "evolution": "Glimmark", "description": "Makes lights flicker on and off."},
    {"num": 66, "name": "Glimmark", "type": "Numérique", "rarity": "Uncommon", "evolution": None, "description": "Causes total blackouts."},
    {"num": 67, "name": "Frigilix", "type": "Climat", "rarity": "Common", "evolution": "Frigilune", "description": "Grows on cold windowsills."},
    {"num": 68, "name": "Frigilune", "type": "Climat", "rarity": "Rare", "evolution": None, "description": "Invites frost indoors."},
    {"num": 69, "name": "Termitix", "type": "Bio-Parasite", "rarity": "Rare", "evolution": None, "description": "Eats through wooden beams."},
    {"num": 70, "name": "Wispulse", "type": "Spectre", "rarity": "Common", "evolution": "Wisphere", "description": "Appears when lights fail."},
    {"num": 71, "name": "Wisphere", "type": "Spectre", "rarity": "Rare", "evolution": None, "description": "Makes LED bulbs explode."},
    {"num": 72, "name": "Statibit", "type": "Numérique", "rarity": "Common", "evolution": "Statiburst", "description": "Static shock on every touch."},
    {"num": 73, "name": "Statiburst", "type": "Numérique", "rarity": "Rare", "evolution": None, "description": "Can fry entire server rooms."},
    {"num": 74, "name": "Leakroot", "type": "Climat", "rarity": "Common", "evolution": "Leakshade", "description": "Leaks water into random spots."},
    {"num": 75, "name": "Leakshade", "type": "Climat", "rarity": "Uncommon", "evolution": None, "description": "Floods basements with gloom."},
    {"num": 76, "name": "Creepad", "type": "Structure", "rarity": "Common", "evolution": "Creepath", "description": "Makes floors squeak eerily."},
    {"num": 77, "name": "Creepath", "type": "Structure", "rarity": "Rare", "evolution": None, "description": "Warps floorboards like a wave."},
    {"num": 78, "name": "Radonis", "type": "Climat", "rarity": "Rare", "evolution": None, "description": "Emits mysterious energies."},
    {"num": 79, "name": "Crackrune", "type": "Structure", "rarity": "Common", "evolution": "Crackryst", "description": "Carves runes into concrete."},
    {"num": 80, "name": "Crackryst", "type": "Structure", "rarity": "Uncommon", "evolution": None, "description": "Runes glow in the dark."},
    {"num": 81, "name": "Spoorine", "type": "Bio-Parasite", "rarity": "Common", "evolution": "Spoorage", "description": "Spreads via contaminated dust."},
    {"num": 82, "name": "Spoorage", "type": "Bio-Parasite", "rarity": "Rare", "evolution": None, "description": "Colonizes ventilation systems."},
    {"num": 83, "name": "Pestflare", "type": "Bio-Parasite", "rarity": "Uncommon", "evolution": None, "description": "Attracts swarms of bugs."},
    {"num": 84, "name": "Magnetide", "type": "Énergie", "rarity": "Rare", "evolution": None, "description": "Interferes with all appliances."},
    {"num": 85, "name": "Shiverun", "type": "Climat", "rarity": "Common", "evolution": "Shiveroll", "description": "Creates sudden chills."},
    {"num": 86, "name": "Shiveroll", "type": "Climat", "rarity": "Uncommon", "evolution": None, "description": "Ices up windows instantly."},
    {"num": 87, "name": "Luminoir", "type": "Numérique", "rarity": "Rare", "evolution": None, "description": "Overloads smart lighting."},
    {"num": 88, "name": "Smogshade", "type": "Climat", "rarity": "Uncommon", "evolution": None, "description": "Smothers rooms with gray fog."},
    {"num": 89, "name": "Plumbgeist", "type": "Spectre", "rarity": "Uncommon", "evolution": None, "description": "Possesses old plumbing pipes."},
    {"num": 90, "name": "Brixis", "type": "Structure", "rarity": "Common", "evolution": "Brixiant", "description": "Brick dust forms its body."},
    {"num": 91, "name": "Brixiant", "type": "Structure", "rarity": "Uncommon", "evolution": None, "description": "Can strengthen weak walls."},
    {"num": 92, "name": "Sporalux", "type": "Bio-Parasite", "rarity": "Rare", "evolution": None, "description": "Glows in the dark, feeds on paint."},
    {"num": 93, "name": "Datashade", "type": "Numérique", "rarity": "Uncommon", "evolution": None, "description": "Hides in data cables, erases files."},
    {"num": 94, "name": "Gasphex", "type": "Climat", "rarity": "Uncommon", "evolution": None, "description": "Fills rooms with untraceable gas."},
    {"num": 95, "name": "Cracklin", "type": "Structure", "rarity": "Common", "evolution": "Cracklash", "description": "Jumps from crack to crack."},
    {"num": 96, "name": "Cracklash", "type": "Structure", "rarity": "Rare", "evolution": None, "description": "Causes structural chain reactions."},
    {"num": 97, "name": "Damphex", "type": "Climat", "rarity": "Common", "evolution": "Damptide", "description": "Dampens the air with cold mist."},
    {"num": 98, "name": "Damptide", "type": "Climat", "rarity": "Uncommon", "evolution": None, "description": "Swells wood, ruins parquet floors."},
    {"num": 99, "name": "Buggbyte", "type": "Numérique", "rarity": "Common", "evolution": "BuggbyteX", "description": "Causes error pop-ups everywhere."},
    {"num": 100, "name": "BuggbyteX", "type": "Numérique", "rarity": "Rare", "evolution": None, "description": "Triggers system-wide meltdowns."},
    {"num": 101, "name": "Creepflow", "type": "Structure", "rarity": "Uncommon", "evolution": None, "description": "Walls seem to 'breathe' when it's near."},
    {"num": 102, "name": "Dustshade", "type": "Climat", "rarity": "Common", "evolution": "Dustloom", "description": "Covers every surface in fine dust."},
    {"num": 103, "name": "Dustloom", "type": "Climat", "rarity": "Rare", "evolution": None, "description": "Turns rooms pitch black."},
    {"num": 104, "name": "Coblite", "type": "Structure", "rarity": "Common", "evolution": "Coblumine", "description": "Masonry dust forms its cloak."},
    {"num": 105, "name": "Coblumine", "type": "Structure", "rarity": "Uncommon", "evolution": None, "description": "Glows in ruins at night."},
    {"num": 106, "name": "Sputterix", "type": "Énergie", "rarity": "Common", "evolution": "Sputterox", "description": "Makes outlets spark for fun."},
    {"num": 107, "name": "Sputterox", "type": "Énergie", "rarity": "Rare", "evolution": None, "description": "Can short out an entire grid."},
    {"num": 108, "name": "Vaporgale", "type": "Climat", "rarity": "Uncommon", "evolution": None, "description": "Hot breath fogs up every mirror."},
    {"num": 109, "name": "Nocrypt", "type": "Spectre", "rarity": "Rare", "evolution": None, "description": "Guards ancient blueprints."},
    {"num": 110, "name": "Fibergeist", "type": "Numérique", "rarity": "Rare", "evolution": None, "description": "Corrupts fiber optic cables."},
    {"num": 111, "name": "Mosslash", "type": "Bio-Parasite", "rarity": "Common", "evolution": "Mosslurk", "description": "Green and invasive."},
    {"num": 112, "name": "Mosslurk", "type": "Bio-Parasite", "rarity": "Rare", "evolution": None, "description": "Grows behind wallpaper silently."},
    {"num": 113, "name": "Fractorn", "type": "Structure", "rarity": "Rare", "evolution": None, "description": "Shatters glass with ultrasonic screams."},
    {"num": 114, "name": "Chitterra", "type": "Bio-Parasite", "rarity": "Common", "evolution": "Chitterrusk", "description": "Scratches at insulation."},
    {"num": 115, "name": "Chitterrusk", "type": "Bio-Parasite", "rarity": "Uncommon", "evolution": None, "description": "Invites real bugs inside."},
    {"num": 116, "name": "Luminel", "type": "Numérique", "rarity": "Common", "evolution": "Luminisk", "description": "Makes LEDs flash patterns."},
    {"num": 117, "name": "Luminisk", "type": "Numérique", "rarity": "Uncommon", "evolution": None, "description": "Hypnotizes building occupants."},
    {"num": 118, "name": "Venturoar", "type": "Structure", "rarity": "Common", "evolution": "VenturoarX", "description": "Hides in ventilation shafts."},
    {"num": 119, "name": "VenturoarX", "type": "Structure", "rarity": "Rare", "evolution": None, "description": "Roars like a beast in ducts."},
    {"num": 120, "name": "Infestine", "type": "Bio-Parasite", "rarity": "Uncommon", "evolution": None, "description": "Grows only in hidden spaces."},
    {"num": 121, "name": "Flickshade", "type": "Spectre", "rarity": "Common", "evolution": "Flickphant", "description": "Flickers the lights just before storms."},
    {"num": 122, "name": "Flickphant", "type": "Spectre", "rarity": "Uncommon", "evolution": None, "description": "Appears in thunderstorms."},
    {"num": 123, "name": "Brickurn", "type": "Structure", "rarity": "Rare", "evolution": None, "description": "Turns broken bricks to dust."},
    {"num": 124, "name": "Cryptmoss", "type": "Bio-Parasite", "rarity": "Uncommon", "evolution": None, "description": "Hides under loose floorboards."},
    {"num": 125, "name": "Toxiburst", "type": "Climat", "rarity": "Rare", "evolution": None, "description": "Releases poisonous air in old basements."},
    {"num": 126, "name": "Siltgeist", "type": "Spectre", "rarity": "Rare", "evolution": None, "description": "Makes concrete vibrate with fear."},
    {"num": 127, "name": "Paraspore", "type": "Bio-Parasite", "rarity": "Rare", "evolution": None, "description": "Fills vents with hallucinogenic spores."},
    {"num": 128, "name": "Pylonix", "type": "Structure", "rarity": "Uncommon", "evolution": None, "description": "Merges with metal beams."},
    {"num": 129, "name": "Rotoglyph", "type": "Structure", "rarity": "Rare", "evolution": None, "description": "Etches warning symbols in steel."},
    {"num": 130, "name": "Neoncrypt", "type": "Numérique", "rarity": "Rare", "evolution": None, "description": "Hides in neon signs, corrupts their glow."},
    {"num": 131, "name": "Glitchara", "type": "Numérique", "rarity": "Rare", "evolution": None, "description": "Generates endless error messages."},
    {"num": 132, "name": "Dampraze", "type": "Climat", "rarity": "Rare", "evolution": None, "description": "Causes steam explosions."},
    {"num": 133, "name": "Fraywatt", "type": "Énergie", "rarity": "Uncommon", "evolution": None, "description": "Can unravel whole circuits."},
    {"num": 134, "name": "Patchmoss", "type": "Bio-Parasite", "rarity": "Common", "evolution": "Patchmourn", "description": "Patches cracks with living moss."},
    {"num": 135, "name": "Patchmourn", "type": "Bio-Parasite", "rarity": "Uncommon", "evolution": None, "description": "Haunts patched walls."},
    {"num": 136, "name": "Thermiwisp", "type": "Climat", "rarity": "Uncommon", "evolution": None, "description": "Swirls of warm and cold air."},
    {"num": 137, "name": "Hackgeist", "type": "Numérique", "rarity": "Rare", "evolution": None, "description": "Haunts smart home systems."},
    {"num": 138, "name": "Moldwraith", "type": "Bio-Parasite", "rarity": "Rare", "evolution": None, "description": "Possesses abandoned apartments."},
    {"num": 139, "name": "Vitralisk", "type": "Structure", "rarity": "Rare", "evolution": None, "description": "Controls colored glass windows."},
    {"num": 140, "name": "Furnaceek", "type": "Climat", "rarity": "Rare", "evolution": None, "description": "Appears only during winter storms."},
    {"num": 141, "name": "Basalgon", "type": "Structure", "rarity": "Legendary", "evolution": None, "description": "Ancient and nearly indestructible."},
    {"num": 142, "name": "Miasmax", "type": "Climat", "rarity": "Legendary", "evolution": None, "description": "Its breath is pure toxicity."},
    {"num": 143, "name": "Overlordis", "type": "Énergie", "rarity": "Legendary", "evolution": None, "description": "Can power or destroy entire buildings."},
    {"num": 144, "name": "Holohex", "type": "Numérique", "rarity": "Legendary", "evolution": None, "description": "Glitch so rare it exists in two places at once."},
    {"num": 145, "name": "Necrocrypt", "type": "Spectre", "rarity": "Legendary", "evolution": None, "description": "Brings old blueprints back to life."},
    {"num": 146, "name": "Rotolyth", "type": "Structure", "rarity": "Legendary", "evolution": None, "description": "Rewrites the rules of gravity in ruins."},
    {"num": 147, "name": "Paradoxul", "type": "Bio-Parasite", "rarity": "Legendary", "evolution": None, "description": "Can both heal and corrupt a building."},
    {"num": 148, "name": "Etherwatt", "type": "Énergie", "rarity": "Legendary", "evolution": None, "description": "Pure energy, impossible to trap."},
    {"num": 149, "name": "Binalis", "type": "Numérique", "rarity": "Legendary", "evolution": None, "description": "Exists only in code, but affects the real world."},
    {"num": 150, "name": "Spectrion", "type": "Spectre", "rarity": "Legendary", "evolution": None, "description": "The king of all hauntings."},
    {"num": 151, "name": "MYİKKİMONE", "type": "Climat", "rarity": "Legendary", "evolution": None, "description": "Legendary spirit, protects homes forever."}
]


RARITY_PROBA = {
    "Common": 55,
    "Uncommon": 24,
    "Rare": 14,
    "Legendary": 7
}

STARTER_PACK = {"Domoball": 5, "Scan Tool": 1}

DAILY_REWARDS = {
    "Domoball": 3,
    "bonus_items": ["Scan Tool", "Small Repair Kit", "CryptoStamp", "Architectrap", "SpectraSeal", "BIMNet"]
}

# ====== COMMANDES DISCORD ======

@bot.event
async def on_ready():
    print(f'Bot connecté comme {bot.user} !')
    spawn_task.start()

@commands.has_permissions(administrator=True)
@bot.command(name="setspawn")
async def set_spawn_channel(ctx):
    global spawn_channel_id
    spawn_channel_id = ctx.channel.id
    await ctx.send("Ce salon est désormais le canal de spawn des DOMON !")

@bot.command(name="start")
async def start_game(ctx):
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
        await ctx.send(f"{ctx.author.mention} Welcome to MYİKKİ DOMON HUNT!\nYou receive: 5 Domoballs and 1 Scan Tool! Type `!inventory` to see your items.")
    else:
        await ctx.send("You already have an account! Use `!inventory`.")

@bot.command(name="daily")
async def daily(ctx):
    user_id = str(ctx.author.id)
    from datetime import datetime, timedelta
    import pytz
    tz = pytz.timezone("Europe/Paris")
    now = datetime.now(tz).date()
    player = players.get(user_id)
    if not player:
        await ctx.send("Type `!start` to begin your hunt!")
        return
    if player["daily"] == str(now):
        await ctx.send("You already claimed your daily reward today!")
        return
    player["daily"] = str(now)
    player["inventory"]["Domoball"] = player["inventory"].get("Domoball",0) + DAILY_REWARDS["Domoball"]
    bonus = random.choice(DAILY_REWARDS["bonus_items"])
    player["inventory"][bonus] = player["inventory"].get(bonus,0) + 1
    save_players(players)
    await ctx.send(f"{ctx.author.mention} received 3 Domoballs and 1 bonus item: **{bonus}**!")

@bot.command(name="inventory")
async def inventory(ctx):
    user_id = str(ctx.author.id)
    player = players.get(user_id)
    if not player:
        await ctx.send("Type `!start` to begin your hunt!")
        return
    embed = discord.Embed(title=f"{ctx.author.display_name}'s Inventory", color=0xFFD700)
    for k, v in player["inventory"].items():
        embed.add_field(name=k, value=str(v), inline=True)
    await ctx.send(embed=embed)

@bot.command(name="collection")
async def collection(ctx):
    user_id = str(ctx.author.id)
    player = players.get(user_id)
    if not player:
        await ctx.send("Type `!start` to begin your hunt!")
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
    embed = discord.Embed(title="DOMODEX – Complete List", color=0x6e34ff)
    domotxt = ""
    for d in DOMON_LIST:
        domotxt += f"#{d['num']:03d} {d['name']} ({d['type']}, {d['rarity']})\n"
    embed.description = domotxt[:4000]
    await ctx.send(embed=embed)

@bot.command(name="info")
async def domon_info(ctx, *, name_or_num:str):
    domon = None
    for d in DOMON_LIST:
        if d["name"].lower() == name_or_num.lower() or str(d["num"]) == name_or_num:
            domon = d
            break
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

# ======= SYSTÈME DE SPAWN, SCAN ET CAPTURE =======
@tasks.loop(minutes=15)
async def spawn_task():
    global spawned_domon, active_spawn
    if not spawn_channel_id:
        return
    if active_spawn:
        return
    domon = random.choices(DOMON_LIST, weights=[RARITY_PROBA.get(d["rarity"],10) for d in DOMON_LIST], k=1)[0]
    spawned_domon = domon
    active_spawn = True
    channel = bot.get_channel(spawn_channel_id)
    if channel:
        await channel.send(f"A wild DOMON appeared!\n**#{domon['num']:03d} {domon['name']}**\nType: {domon['type']} | Rarity: {domon['rarity']}\n_Description_: {domon['description']}\nType `!scan` to try to detect it!")

@bot.command(name="scan")
async def scan(ctx):
    global spawned_domon, active_spawn
    if not active_spawn or not spawned_domon:
        await ctx.send("No DOMON to scan right now.")
        return
    user_id = str(ctx.author.id)
    player = players.get(user_id)
    if not player:
        await ctx.send("Type `!start` to begin your hunt!")
        return
    await ctx.send(f"{ctx.author.mention} detected the DOMON!\nType `!capture` to try and catch it!")

@bot.command(name="capture")
async def capture(ctx):
    global spawned_domon, active_spawn
    user_id = str(ctx.author.id)
    player = players.get(user_id)
    if not active_spawn or not spawned_domon:
        await ctx.send("No DOMON to capture.")
        return
    if not player:
        await ctx.send("Type `!start` to begin your hunt!")
        return
    if player["inventory"].get("Domoball",0) < 1:
        await ctx.send("You have no Domoballs left! Claim with `!daily`.")
        return
    rates = {"Common": 0.90, "Uncommon": 0.65, "Rare": 0.30, "Legendary": 0.10}
    success = random.random() < rates.get(spawned_domon["rarity"], 0.5)
    player["inventory"]["Domoball"] -= 1
    if success:
        player["collection"].append(spawned_domon)
        player["xp"] += 1
        save_players(players)
        name = spawned_domon['name']
        await ctx.send(f"🎉 {ctx.author.mention} captured **{name}**! Added to your collection. +1 XP.")
        # Gérer évolutions (si besoin, à compléter selon ta logique)
        for d in DOMON_LIST:
            if d["evolution"] == name and name not in [dom['name'] for dom in player["collection"]]:
                n = sum(1 for dom in player["collection"] if dom['name']==name)
                if n >= 3:
                    next_dom = [dom for dom in DOMON_LIST if dom['name'] == d["evolution"]]
                    if next_dom:
                        player["collection"].append(next_dom[0])
                        save_players(players)
                        await ctx.send(f"✨ Your {name} evolved into {next_dom[0]['name']}!")
        if player["xp"] % 10 == 0:
            item = random.choice(DAILY_REWARDS["bonus_items"])
            player["inventory"][item] = player["inventory"].get(item,0)+1
            save_players(players)
            await ctx.send(f"You reached {player['xp']} XP and received a bonus item: **{item}**!")
        active_spawn = False
        spawned_domon = None
    else:
        active_spawn = False
        spawned_domon = None
        await ctx.send(f"❌ {ctx.author.mention} failed to capture the DOMON... It escaped!")

@commands.has_permissions(administrator=True)
@bot.command(name="forcespawn")
async def forcespawn(ctx):
    global spawned_domon, active_spawn
    if active_spawn:
        await ctx.send("A DOMON is already spawned.")
        return
    domon = random.choice(DOMON_LIST)
    spawned_domon = domon
    active_spawn = True
    await ctx.send(f"**(Admin)** A wild DOMON appeared!\n**#{domon['num']:03d} {domon['name']}**\nType: {domon['type']} | Rarity: {domon['rarity']}\n_Description_: {domon['description']}\nType `!scan` to try to detect it!")

# ===== LANCEMENT DU BOT (avec keep-alive) =====
keep_alive()
bot.run(TOKEN)

import random
import streamlit as st
import sqlite3
import bcrypt
from PIL import Image
import time

def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password BLOB,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def register_user(username, password):
    hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password, xp, level, wins, losses) VALUES (?, ?, 0, 1, 0, 0)", 
                 (username, hashed_pw))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def authenticate_user(username, password):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    if result and bcrypt.checkpw(password.encode(), result[0]):
        return True
    return False


def get_user_stats(username):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT xp, level, wins, losses FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    if result:
        return {
            "xp": result[0],
            "level": result[1],
            "wins": result[2],
            "losses": result[3]
        }
    return {"xp": 0, "level": 1, "wins": 0, "losses": 0}


def update_user_xp_fixed(username, xp_earned, won=False):
    """Update user XP, wins, and losses with better error handling"""
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    # Check if user exists
    c.execute("SELECT COUNT(*) FROM users WHERE username = ?", (username,))
    user_exists = c.fetchone()[0] > 0

    if not user_exists:
        # Create new user
        c.execute("INSERT INTO users (username, xp, level, wins, losses) VALUES (?, ?, ?, ?, ?)", 
                 (username, xp_earned, 1, 1 if won else 0, 0 if won else 1))
        conn.commit()
        conn.close()
        return False  # No level up for new user

    # Get current stats
    c.execute("SELECT xp, level, wins, losses FROM users WHERE username = ?", (username,))
    result = c.fetchone()

    if result is None:
        # This shouldn't happen but handle it just in case
        c.execute("INSERT INTO users (username, xp, level, wins, losses) VALUES (?, ?, ?, ?, ?)", 
                 (username, xp_earned, 1, 1 if won else 0, 0 if won else 1))
        conn.commit()
        conn.close()
        return False

    current_xp, current_level, wins, losses = result

    # Update wins or losses
    if won:
        wins += 1
    else:
        losses += 1

    # Add XP
    new_xp = current_xp + xp_earned

    # Check if level up
    new_level = current_level
    while new_level < 60 and new_xp >= xp_required_for_level(new_level + 1):
        new_level += 1

    # Update database with explicit column names
    c.execute("""
        UPDATE users 
        SET xp = ?, level = ?, wins = ?, losses = ? 
        WHERE username = ?
    """, (new_xp, new_level, wins, losses, username))

    conn.commit()
    conn.close()

    return new_level > current_level

# Set page configuration
st.set_page_config(
    page_title="LeBron Boss Battle",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# --------------------- Game Classes and Functions --------------------- #

class Player:
    def __init__(self, name, health, stamina, special_meter=0):
        self.name = name
        self.max_health = health
        self.health = health
        self.max_stamina = 100
        self.stamina = stamina
        self.special_meter = special_meter
        self.is_defending = False
        self.buffs = []
        self.debuffs = []

    def attack(self):
        if self.stamina < 15:
            return (0, f"{self.name} is too tired to attack!")
        self.stamina -= 15
        self.special_meter += 10
        if self.special_meter > 100:
            self.special_meter = 100
        base_damage = random.randint(15, 30)
        critical = random.random() < 0.2
        if critical:
            base_damage = int(base_damage * 1.5)
            return (base_damage, f"{self.name} lands a CRITICAL hit for {base_damage} damage!")
        return (base_damage, f"{self.name} attacks for {base_damage} damage!")

    def special_attack(self):
        if self.special_meter < 100:
            return (0, f"{self.name} doesn't have enough energy for a special attack!")
        self.special_meter = 0
        self.stamina -= 25
        if self.stamina < 0:
            self.stamina = 0
        damage = random.randint(40, 60)
        return (damage, f"{self.name} unleashes a SPECIAL ATTACK for {damage} massive damage!")

    def defend(self):
        self.stamina -= 10
        if self.stamina < 0:
            self.stamina = 0
        self.is_defending = True  # Set defending state
        self.special_meter += 15
        if self.special_meter > 100:
            self.special_meter = 100
        return f"{self.name} takes a defensive stance, ready to reduce and heal from incoming damage!"

    def rest(self):
        gained = random.randint(25, 40)
        self.stamina += gained
        if self.stamina > self.max_stamina:
            self.stamina = self.max_stamina
        self.special_meter += 5
        if self.special_meter > 100:
            self.special_meter = 100
        return f"{self.name} rests and recovers {gained} stamina."

    def take_damage(self, damage):
        if self.is_defending:
            damage = int(damage * 0.5)
            result = f"{self.name} blocks and reduces damage to {damage}!"
            self.is_defending = False
        else:
            result = f"{self.name} takes {damage} damage!"
        self.health -= damage
        if self.health < 0:
            self.health = 0
        return result

    def is_alive(self):
        return self.health > 0

    def reset_turn(self):
        self.is_defending = False

class LeBron(Player):
    def __init__(self, difficulty):
        health = 100 if difficulty == "Easy" else 160 if difficulty == "Medium" else 180
        stamina = 100
        super().__init__("LeBron James", health, stamina)
        self.difficulty = difficulty
        self.special_move_name = "Signature Slam Dunk"
        self.abilities = {
            "POSTERIZER": "Quick attack that has a chance to lower opponent's stamina",
            "BLOCKED BY JAMES": "Strong defensive move that also recovers stamina",
            "ALLEY-OOP TO DAVIS": "Tactical move that increases special meter gain",
            f"{self.special_move_name}": "Devastating special attack that deals massive damage"
        }
        self.move_patterns = self.set_move_patterns()
        self.consecutive_attacks = 0
        self.consecutive_defends = 0
        self.player_last_hp = 140  # Store opponent's last HP to track damage dealt
        self.player_pattern_memory = []  # Remember opponent's last 3 moves
        self.turn_count = 0

    def set_move_patterns(self):
        """Define LeBron's move patterns based on difficulty."""
        if self.difficulty == "Easy":
            return {"attack": 0.4, "defend": 0.3, "rest": 0.25, "special": 0.05}
        elif self.difficulty == "Medium":
            return {"attack": 0.45, "defend": 0.25, "rest": 0.2, "special": 0.1}
        else:  # Hard difficulty
            return {"attack": 0.5, "defend": 0.2, "rest": 0.15, "special": 0.15}

    def analyze_player_pattern(self, player):
        """Analyze player's pattern and adjust strategy accordingly (for Medium and Hard only)"""
        if self.difficulty == "Easy":
            return  # Skip analysis for Easy mode

        # Track player health changes to detect attacks
        damage_taken = self.player_last_hp - player.health
        self.player_last_hp = player.health

        # Record player's apparent move
        player_move = None
        if damage_taken > 0:
            if damage_taken > 35:  # Likely a special attack
                player_move = "special"
            else:
                player_move = "attack"
        elif player.stamina > self.player_last_stamina:
            player_move = "rest"
        elif player.is_defending:
            player_move = "defend"

        self.player_last_stamina = player.stamina

        # Add to pattern memory (keep last 3 moves)
        if player_move:
            self.player_pattern_memory.append(player_move)
            if len(self.player_pattern_memory) > 3:
                self.player_pattern_memory.pop(0)

    def predict_player_action(self):
        """Try to predict player's next action based on pattern"""
        if len(self.player_pattern_memory) < 2 or self.difficulty == "Easy":
            return None

        # Look for patterns like "attack, attack, special" or "rest, attack"
        if self.difficulty == "Hard":
            # Check for "rest then attack" pattern
            if self.player_pattern_memory[-1] == "rest":
                return "attack"  # Player might attack after resting

            # Check for "multiple attacks" pattern
            attack_count = self.player_pattern_memory.count("attack")
            if attack_count >= 2:
                return "special"  # Player might be building special meter

            # Check for special meter buildup
            if "special" in self.player_pattern_memory:
                return "rest"  # Player used special, likely needs to rest

        return None

    def choose_action(self, player=None):
        """Choose LeBron's action based on strategy, difficulty and game state."""
        self.turn_count += 1

        # Update pattern analysis if we have player information
        if player:
            self.analyze_player_pattern(player)

        # Initialize base weights from move patterns
        weights = {
            "attack": self.move_patterns["attack"],
            "defend": self.move_patterns["defend"],
            "rest": self.move_patterns["rest"],
            "special": 0 if self.special_meter < 100 else self.move_patterns["special"]
        }

        # EMERGENCY RESPONSES (highest priority)
        # Only rest if stamina is below threshold (25-30)
        if self.stamina <= 30:
            # The lower the stamina, the higher the chance to rest
            rest_urgency = (30 - self.stamina) / 30  # 0.0 to 1.0 scale
            weights["rest"] *= (1 + 2 * rest_urgency)  # Up to 3x more likely to rest when critically low

            # Force rest if extremely low stamina (below 15)
            if self.stamina < 15:
                return "rest"
        else:
            # Significantly reduce chance of resting when stamina is high
            weights["rest"] *= 0.2  # 80% reduction in rest probability when above threshold

        # TACTICAL DECISIONS (based on difficulty)
        if self.difficulty == "Hard" or self.difficulty == "Medium":
            # If health is very low, increase chance of defensive move
            if self.health < self.max_health * 0.3:
                weights["defend"] *= 2.0

            # If player has high special meter and we predict special attack
            predicted_move = self.predict_player_action()
            if predicted_move == "special" and player and player.special_meter >= 75:
                weights["defend"] *= 3.0  # Very likely to defend

            # If we have special meter full and player is low on health, use special
            if self.special_meter >= 100 and player and player.health < player.max_health * 0.4:
                return "special"  # Go for the kill

            # Avoid predictable patterns
            if self.consecutive_attacks >= 2:
                weights["attack"] *= 0.5  # Reduce chance of third consecutive attack

            if self.consecutive_defends >= 2:
                weights["defend"] *= 0.3  # Reduce chance of third consecutive defense

            # Enhanced special attack strategy
            if self.special_meter >= 100:
                special_threshold = 0.8 if self.difficulty == "Hard" else 0.6
                if random.random() < special_threshold:
                    return "special"

            # If player is defending, consider resting instead of attacking
            if player and player.is_defending:
                weights["attack"] *= 0.4
                weights["rest"] *= 1.5

        # Hard mode specific enhancements
        if self.difficulty == "Hard":
            # Hard mode should be more conservative with stamina, but not rest unnecessarily
            if 15 < self.stamina < 40:
                weights["rest"] *= 1.5

            # More aggressive when player is low on health
            if player and player.health < player.max_health * 0.3:
                weights["attack"] *= 1.5

            # Use stamina efficiently at the beginning of the battle
            if self.turn_count < 5 and self.health > self.max_health * 0.8:
                weights["defend"] *= 1.3  # Defend early to build special meter

        # Prefer attacking over resting when stamina is decent
        if self.stamina > 50:
            weights["attack"] *= 1.3

        # Calculate the final decision
        actions = list(weights.keys())
        weights_list = list(weights.values())

        chosen_action = random.choices(actions, weights=weights_list)[0]

        # Double-check resting logic - only rest if truly needed (below 30 stamina)
        if chosen_action == "rest" and self.stamina > 30:
            # Reconsider with reduced rest weight
            weights["rest"] = 0.1  # Very low chance
            actions = list(weights.keys())
            weights_list = list(weights.values())
            chosen_action = random.choices(actions, weights=weights_list)[0]

        # Update consecutive action counters
        if chosen_action == "attack":
            self.consecutive_attacks += 1
            self.consecutive_defends = 0
        elif chosen_action == "defend":
            self.consecutive_defends += 1
            self.consecutive_attacks = 0
        else:
            self.consecutive_attacks = 0
            self.consecutive_defends = 0

        return chosen_action

    def attack(self):
        """Perform an attack with a chance to lower opponent's stamina."""
        damage, msg = super().attack()
        # Higher chance of bonus effect on harder difficulties
        poster_chance = 0.2 if self.difficulty == "Easy" else 0.35 if self.difficulty == "Medium" else 0.5
        if random.random() < poster_chance:
            return (damage, "LeBron POSTERS YOU for " + str(damage) + " damage and reduces your stamina!")
        return (damage, msg)

    def special_attack(self):
        """Perform a devastating special attack."""
        damage, _ = super().special_attack()
        # Scaling damage based on difficulty
        if self.difficulty == "Medium":
            damage = int(damage * 1.1)  # 10% damage boost
        elif self.difficulty == "Hard":
            damage = int(damage * 1.2)  # 20% damage boost
        return (damage, f"LeBron unleashes his {self.special_move_name} for {damage} MASSIVE damage!")

    def take_damage(self, damage):
        if self.is_defending:
            # Damage reduction scales with difficulty
            reduction = 0.5
            reduced_damage = int(damage * (1 - reduction))

            # Healing scales with difficulty
            heal_percent = 0.5
            heal_amount = int(reduced_damage * heal_percent)

            self.health += heal_amount
            # Ensure health doesn't exceed max health
            if self.health > self.max_health:
                self.health = self.max_health
            # Apply the reduced damage
            self.health -= reduced_damage
            if self.health < 0:
                self.health = 0
            # Reset defending state AFTER processing damage
            self.is_defending = False
            return f"{self.name} blocks and reduces damage to {reduced_damage}, then heals {heal_amount} health!"
        else:
            # Apply full damage if not defending
            self.health -= damage
            if self.health < 0:
                self.health = 0
            return f"{self.name} takes {damage} damage!"

def display_character_card(character, is_player=True):
    card_class = "player-card" if is_player else "lebron-card"
    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown("<div class='custom-avatar-container'>", unsafe_allow_html=True)
        if is_player:
            st.image("https://is1-ssl.mzstatic.com/image/thumb/Music126/v4/04/62/e6/0462e6b9-45b0-f229-afc0-d2f79cce2cf4/artwork.jpg/632x632bb.webp", caption=character.name, width=150)
        else:
            st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/c/cf/LeBron_James_%2851960276445%29_%28cropped%29.jpg/1024px-LeBron_James_%2851960276445%29_%28cropped%29.jpg", caption=character.name, width=150)
        st.markdown("</div>", unsafe_allow_html=True)
    with col2:
        st.markdown(f"<div class='stat-label'>Health: {character.health}/{character.max_health}</div>", unsafe_allow_html=True)
        health_percentage = character.health / character.max_health if character.max_health > 0 else 0
        st.progress(health_percentage)
        st.markdown(f"<div class='stat-label'>Stamina: {character.stamina}/{character.max_stamina}</div>", unsafe_allow_html=True)
        stamina_percentage = character.stamina / character.max_stamina if character.max_stamina > 0 else 0
        st.progress(stamina_percentage)
        st.markdown(f"<div class='stat-label'>Special Meter: {character.special_meter}/100</div>", unsafe_allow_html=True)
        special_percentage = character.special_meter / 100
        st.progress(special_percentage)
        if character.is_defending:
            st.markdown("🛡️ **Defending**")

def initialize_session_state():
    if "game_started" not in st.session_state:
        st.session_state.game_started = False
    if "difficulty" not in st.session_state:
        st.session_state.difficulty = "Medium"
    if "player" not in st.session_state or st.session_state.get("restart_game", False):
        st.session_state.player = Player("You", 140, 100)
    if "lebron" not in st.session_state or st.session_state.get("restart_game", False):
        st.session_state.lebron = LeBron(st.session_state.difficulty)
    if st.session_state.get("restart_game", False):
        st.session_state.restart_game = False
    if "turn" not in st.session_state:
        st.session_state.turn = 0
    if "round" not in st.session_state:
        st.session_state.round = 1
    if "log" not in st.session_state:
        st.session_state.log = []
    if "current_player_action" not in st.session_state:
        st.session_state.current_player_action = None
    if "action_taken" not in st.session_state:
        st.session_state.action_taken = False
    if "animation_state" not in st.session_state:
        st.session_state.animation_state = None
    if "tutorial_shown" not in st.session_state:
        st.session_state.tutorial_shown = False

def add_log_entry(message, entry_type="system"):
    timestamp = time.strftime("%H:%M:%S")
    st.session_state.log.append({
        "message": message,
        "type": entry_type,
        "timestamp": timestamp
    })

def display_battle_log():
    st.markdown("### 📜 Battle Log")
    with st.container():
        for entry in reversed(st.session_state.log):
            if isinstance(entry, dict) and 'type' in entry and 'message' in entry:
                entry_class = f"log-entry {entry['type']}-log"
                st.markdown(f"<div class='{entry_class}'><small>{entry['timestamp']}</small> {entry['message']}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='log-entry system-log'><small>Unknown time</small> {entry}</div>", unsafe_allow_html=True)

def lebron_turn():
    lebron = st.session_state.lebron
    player = st.session_state.player
    action = lebron.choose_action()
    st.session_state.animation_state = f"lebron_{action}"
    if action == "attack":
        dmg, msg = lebron.attack()
        add_log_entry(msg, "lebron")
        if dmg > 0:
            result = player.take_damage(dmg)
            add_log_entry(result, "player")
    elif action == "defend":
        result = lebron.defend()
        add_log_entry(result, "lebron")
    elif action == "rest":
        result = lebron.rest()
        add_log_entry(result, "lebron")
    elif action == "special":
        dmg, msg = lebron.special_attack()
        add_log_entry(msg, "lebron")
        if dmg > 0:
            result = player.take_damage(dmg)
            add_log_entry(result, "player")
    st.session_state.turn += 1
    st.session_state.action_taken = False
    if st.session_state.turn % 2 == 0:
        player.reset_turn()
        lebron.reset_turn()
        st.session_state.round += 1
        add_log_entry(f"Round {st.session_state.round} begins!", "system")
    return True

def process_round():
    """Process both player and LeBron actions simultaneously in one round"""
    player = st.session_state.player
    lebron = st.session_state.lebron

    # Store player's chosen action in session state
    # This is set by the button that was clicked
    player_action = st.session_state.current_player_action
    player_damage = 0

    # Initialize lebron's player_last_stamina attribute if it doesn't exist
    if not hasattr(lebron, 'player_last_stamina'):
        lebron.player_last_stamina = player.stamina

    # Get LeBron's chosen action - pass player object for smarter decisions
    lebron_action = lebron.choose_action(player)
    lebron_damage = 0

    # Record intentions in log
    add_log_entry(f"Round {st.session_state.round} begins - both fighters prepare their moves!", "system")

    # First, process defensive moves for both
    if player_action == "defend":
        result = player.defend()
        add_log_entry(result, "player")
        st.session_state.animation_state = "player_defend"

    if lebron_action == "defend":
        result = lebron.defend()
        add_log_entry(result, "lebron")
        st.session_state.animation_state = "lebron_defend"

    # Then process attacks and calculate damage
    if player_action == "attack":
        player_damage, msg = player.attack()
        add_log_entry(msg, "player")
        st.session_state.animation_state = "player_attack"
    elif player_action == "special":
        player_damage, msg = player.special_attack()
        add_log_entry(msg, "player")
        st.session_state.animation_state = "player_special"
    elif player_action == "rest":
        result = player.rest()
        add_log_entry(result, "player")
        st.session_state.animation_state = "player_rest"

    if lebron_action == "attack":
        lebron_damage, msg = lebron.attack()
        add_log_entry(msg, "lebron")
    elif lebron_action == "special":
        lebron_damage, msg = lebron.special_attack()
        add_log_entry(msg, "lebron")
    elif lebron_action == "rest":
        result = lebron.rest()
        add_log_entry(result, "lebron")

    # Finally, apply damage to both sides
    if player_damage > 0:
        result = lebron.take_damage(player_damage)
        add_log_entry(result, "lebron")

    if lebron_damage > 0:
        result = player.take_damage(lebron_damage)
        add_log_entry(result, "player")

    # Reset for next round
    player.reset_turn()
    lebron.reset_turn()
    st.session_state.round += 1
    st.session_state.action_taken = False

    return True

def xp_required_for_level(level):
    """
    Calculate XP required for a given level with tiered progression:
    - Levels 1-10: Increase by 100 XP per level
    - Levels 11-20: Increase by 200 XP per level
    - Levels 21-30: Increase by 300 XP per level
    - Levels 31-40: Increase by 400 XP per level
    - Levels 41-49: Increase by 500 XP per level
    - Levels 50-60: Exponential progression (unchanged)
    """
    if level <= 1:
        return 0
    elif level <= 10:
        return (level - 1) * 100
    elif level <= 20:
        base_xp = 900  # XP for level 10
        return base_xp + (level - 10) * 200
    elif level <= 30:
        base_xp = 900 + 10 * 200  # XP for level 20
        return base_xp + (level - 20) * 300
    elif level <= 40:
        base_xp = 900 + 10 * 200 + 10 * 300  # XP for level 30
        return base_xp + (level - 30) * 400
    elif level <= 49:
        base_xp = 900 + 10 * 200 + 10 * 300 + 10 * 400  # XP for level 40
        return base_xp + (level - 40) * 500
    else:
        # Keep the original exponential progression for levels 50-60
        base_xp = 900 + 10 * 200 + 10 * 300 + 10 * 400 + 9 * 500  # XP for level 49
        if level == 50:
            return base_xp + 500  # Level 50 continues the 500 XP pattern
        else:
            # Exponential progression for levels 51-60
            multiplier = 1.5 ** (level - 50)
            return int(base_xp + 500 + (level - 50) * 200 * multiplier)

def calculate_xp_reward(player_health, lebron_health, difficulty, won):
    """
    Calculate XP based on:
    - Battle outcome (win/loss)
    - Health margin
    - Difficulty level
    """
    # Base XP for participation
    base_xp = 25

    # Difficulty multiplier
    diff_multiplier = 1.0
    if difficulty == "Medium":
        diff_multiplier = 1.5
    elif difficulty == "Hard":
        diff_multiplier = 2.0

    # Victory bonus
    victory_bonus = 50 if won else 0

    # Health margin bonus (only for wins)
    margin_bonus = 0
    if won:
        margin_bonus = int((player_health / 140) * 30)  # Up to 30 extra XP based on remaining health

    # Calculate total XP
    total_xp = int((base_xp + victory_bonus + margin_bonus) * diff_multiplier)

    # Ensure minimum XP for participation
    return max(10, total_xp)

def get_level_progress(current_xp, current_level):
    """Calculate progress percentage to next level"""
    current_level_xp = xp_required_for_level(current_level)
    next_level_xp = xp_required_for_level(current_level + 1)

    xp_for_this_level = next_level_xp - current_level_xp
    xp_gained_in_level = current_xp - current_level_xp

    progress = xp_gained_in_level / xp_for_this_level if xp_for_this_level > 0 else 1.0
    return min(1.0, max(0.0, progress))  # Ensure between 0 and 1

def get_lebron_image_url(level):
    """Get the LeBron image URL for a specific level"""
    # This function would return different LeBron images based on level
    # In a real implementation, you'd have a list of 60 LeBron image URLs
    # For now, we'll use 6 example images and cycle through them

    # Example LeBron image URLs (you would replace these with 60 different images)
    lebron_images = [
        "https://media.cnn.com/api/v1/images/stellar/prod/230206130746-39-lebron-james-gallery-restricted.jpg?q=w_1576,c_fill",
        "https://www.the-sun.com/wp-content/uploads/sites/6/2023/10/AS_LEBRON-MEMES_OP.jpg?strip=all&quality=100&w=1080&h=1080&crop=1",
        "https://cdn-wp.thesportsrush.com/2021/10/faeeadb8-untitled-design-22.jpg?format=auto&w=3840&q=75",
        "https://www.nickiswift.com/img/gallery/the-transformation-of-lebron-james-from-childhood-to-36-years-old/l-intro-1625330663.jpg",
        "https://wompimages.ampify.care/fetchimage?siteId=7575&v=2&jpgQuality=100&width=700&url=https%3A%2F%2Fi.kym-cdn.com%2Fentries%2Ficons%2Ffacebook%2F000%2F049%2F004%2Flebronsunshinecover.jpg",
        "https://pbs.twimg.com/media/E_sz6efVIAIXSmP.jpg",
        "https://i.ytimg.com/vi/aVw1YW98jZA/hqdefault.jpg",
        "https://i.ytimg.com/vi/uDwhrlTKF-I/maxresdefault.jpg",
        "https://pbs.twimg.com/media/FwnezIzagAEePH9.jpg",
        "https://img.bleacherreport.net/img/images/photos/003/732/611/hi-res-d8f1a4e7bd2be467c9aa1773ce8e43d3_crop_north.jpg?1522365299&w=630&h=420",
        "https://cdn.vox-cdn.com/thumbor/gQT1Wnno4e1duuZWEJQQr1FHiOQ=/0x259:1079x824/fit-in/1200x630/cdn.vox-cdn.com/uploads/chorus_asset/file/22240625/lebron_space_jam_meme.jpeg",
        "https://i1.sndcdn.com/artworks-uTmppMOoZmuhdyt5-Y2IbLA-t500x500.png",
        "https://www.the-sun.com/wp-content/uploads/sites/6/2023/10/taken-without-permission-lebron-james-850585681-1.jpg?strip=all&w=960",
        "https://cdn.vox-cdn.com/thumbor/FGIcZPrV7TBL2qI3aHrX9Volw4w=/1400x1050/filters:format(png)/cdn.vox-cdn.com/uploads/chorus_asset/file/9631797/lebron_meme.png",
        "https://staticg.sportskeeda.com/editor/2023/04/69f5f-16824247788019-1920.jpg?w=640",
        "https://www.bardown.com/polopoly_fs/1.878128!/fileimage/httpImage/image.JPG_gen/derivatives/landscape_620/lebron-james.JPG",
        "https://i.pinimg.com/474x/c0/bd/7a/c0bd7acdf89a7419ca8f31846392a35d.jpg",
        "https://pbs.twimg.com/media/ClH3OtMUkAAClkt.jpg:large",
        "https://static01.nyt.com/images/2020/03/09/sports/09nba-topteams1/merlin_170229057_ce4be847-c57c-41fc-9a4d-70008084dff7-articleLarge.jpg?quality=75&auto=webp&disable=upscale",
        "https://cdn.nba.com/headshots/nba/latest/1040x760/2544.png",
        "https://cdn.nba.com/teams/uploads/sites/1610612747/2023/02/lebron-scoring-record-1000x1000-GettyImages-3061773.jpg",
        "https://media.gettyimages.com/id/2180392115/photo/los-angeles-california-lebron-james-and-bronny-james-of-the-los-angeles-lakers-on-defense.jpg?s=612x612&w=gi&k=20&c=tBm-y-V5LKjl1dgx8Hdar5q14_sqXYtJ5h60TlqFXl4=",
        "https://www.reuters.com/resizer/v2/YUU4FUVGT5P57DT5E5RNJLCACM.jpg?auth=6f23bb8600e7386478005a0560c017aedb6b6b9a6f9b8e81070ddec107e2ada9&width=8640&quality=80",
        "https://cdn.nba.com/teams/uploads/sites/1610612747/2023/02/lebron-scoring-record-1000x1000-GettyImages-74935297-1.jpg",
        "https://a.espncdn.com/photo/2009/1223/nba_g_kobe-lebron11_200.jpg",
        "https://cdn.nba.com/teams/uploads/sites/1610612747/2023/02/lebron-scoring-record-1000x1000-GettyImages-2837856.jpg",
        "https://cdn.nba.com/teams/uploads/sites/1610612747/2025/02/2425_lal_highlight_thumb_250206_reaves_2000.jpg",
        "https://cdn.nba.com/teams/uploads/sites/1610612747/2025/02/lbj0227.png",
        "https://cdn.nba.com/manage/2020/12/lebron-ring-1-1568x882.jpg",
        "https://media.cnn.com/api/v1/images/stellar/prod/ap25004231580012.jpg?c=16x9&q=h_833,w_1480,c_fill",
        "https://cdn.nba.com/manage/2021/12/USATSI_15452777-scaled-e1639236310885-784x462.jpg",
        "https://cdn.nba.com/teams/uploads/sites/1610612747/2025/02/2425_lal_highlight_thumb_250204_reaves_2000.jpg",
        "https://cdn.nba.com/teams/uploads/sites/1610612747/2024/03/240302-the-legend-of-lebron-james-continues-IMG_9980-2.jpg",
        "https://cdn.nba.com/manage/2022/11/lebron-james-passes-iso-784x441.jpg",
        "https://cdn.nba.com/teams/uploads/sites/1610612747/2025/02/2425_lal_highlight_thumb_250220_james_2000.jpg",
        "https://cdn.nba.com/manage/2023/10/lebron-james-kevin-durant-iso.jpg",
        "https://www.newsnationnow.com/wp-content/uploads/sites/108/2024/09/66fb2a98703a66.99021156.jpeg?w=2560&h=1440&crop=1",
        "https://vz.cnwimg.com/thumb-900x/wp-content/uploads/2009/09/LeBron-James1.jpg",
        "https://www.sportsnet.ca/wp-content/uploads/2024/12/LBJ-1-768x432.jpg",
        "https://i.pinimg.com/736x/1c/4a/41/1c4a413dcb6983d0f92fa16e33783ff4.jpg",
        "https://i.pinimg.com/736x/bb/fb/0e/bbfb0e244e8220170e2431b129407bd5.jpg",
        "https://i.pinimg.com/originals/6f/0e/f1/6f0ef1cf662bbca49c1f88e570beaab7.jpg",
        "https://i.pinimg.com/736x/85/2c/26/852c266a80f77bf71a32ed2991a2091c.jpg",
        "https://i.pinimg.com/736x/0e/1e/da/0e1eda26928191ac820127f6bb6a2d35.jpg",
        "https://i.pinimg.com/736x/8c/ed/fc/8cedfcc48d33338b161c503fc895b435.jpg",
        "https://creatorset.com/cdn/shop/files/preview_images/Green_Screen_lebron_james_screaming-0_530x@2x.jpg?v=1730634951",
        "https://cdn.nba.com/manage/2021/09/lebron-block-2016-finals.jpg",
        "https://miro.medium.com/v2/resize:fit:2400/1*GRhI0b3sO9YWJbfxwX5Ulg.jpeg",
        "https://www.si.com/.image/t_share/MTk1NjkzMjQ0OTgwNDA2MjA5/si_lebron_james_00001.jpg",
        "https://media.cnn.com/api/v1/images/stellar/prod/230202223003-05b-lebron-james-gallery.jpg?q=w_1576,c_fill",
        "https://media.cnn.com/api/v1/images/stellar/prod/230202214307-06-lebron-games-gallery-restricted.jpg?q=w_1576,c_fill",
        "https://media.cnn.com/api/v1/images/stellar/prod/230202214311-09-lebron-games-gallery-restricted.jpg?q=w_1576,c_fill",
        "https://media.cnn.com/api/v1/images/stellar/prod/230202220410-17-lebron-games-gallery-restricted.jpg?q=w_1576,c_fill",
        "https://media.cnn.com/api/v1/images/stellar/prod/230202230158-22-lebron-james-gallery.jpg?q=w_1576,c_fill",
        "https://media.cnn.com/api/v1/images/stellar/prod/160620131355-lebron-tears-tease.jpg?q=w_1576,c_fill",
        "https://media.cnn.com/api/v1/images/stellar/prod/230202232006-36-lebron-james-gallery-restricted.jpg?q=w_1576,c_fill",
        "https://media.cnn.com/api/v1/images/stellar/prod/230208001805-01b-lebron-james-scoring-record-0207.jpg?q=w_1576,c_fill",
        "https://media.cnn.com/api/v1/images/stellar/prod/ap24297270749301.jpg?q=w_1576,c_fill",
        "https://media.cnn.com/api/v1/images/stellar/prod/230202231119-28-lebron-james-gallery.jpg?q=w_1576,c_fill",
        "https://media.cnn.com/api/v1/images/stellar/prod/230206141741-41-lebron-james-gallery.jpg?q=w_1576,c_fill",
        "https://media.cnn.com/api/v1/images/stellar/prod/230202231630-32-lebron-james-gallery-restricted.jpg?q=w_1576,c_fill",
    ]

    # Calculate which image to use based on level
    # For now, cycle through the available images
    image_index = (level - 1) % len(lebron_images)

    return lebron_images[image_index]

# In the end_battle_with_xp function, add a flag to check if XP was already awarded
def end_battle_with_xp(player, lebron, won):
    """Update XP, wins, and losses after battle completion"""
    # Check if XP was already awarded for this battle
    if hasattr(st.session_state, 'xp_already_awarded') and st.session_state.xp_already_awarded:
        # Just return the current stats without updating
        return get_user_stats(st.session_state.username)

    difficulty = st.session_state.difficulty
    username = st.session_state.username

    # Calculate XP reward
    xp_earned = calculate_xp_reward(player.health, lebron.health, difficulty, won)

    # Make sure we have current user stats before updating
    current_stats = get_user_stats(username)

    # Now update the user's XP, wins, and losses
    leveled_up = update_user_xp_fixed(username, xp_earned, won)

    # Get updated stats
    updated_stats = get_user_stats(username)

    # Store results in session state
    st.session_state.battle_results = {
        "xp_earned": xp_earned,
        "leveled_up": leveled_up,
        "new_level": updated_stats["level"],
        "total_xp": updated_stats["xp"],
        "wins": updated_stats["wins"],
        "losses": updated_stats["losses"]
    }

    # Mark that XP has been awarded for this battle
    st.session_state.xp_already_awarded = True

    return updated_stats


def add_lepass_css():
    """Add LePASS-specific CSS styles"""

    st.markdown("""
    <style>
        /* LePASS Progress Bar */
        .lepass-progress-container {
            width: 100%;
            height: 30px;
            background-color: #eee;
            border-radius: 15px;
            margin: 10px 0;
            position: relative;
            overflow: hidden;
            box-shadow: inset 0 1px 3px rgba(0,0,0,0.2);
        }

        .lepass-progress-bar {
            height: 100%;
            background: linear-gradient(90deg, #4880EC, #019CAD);
            border-radius: 15px;
            transition: width 0.5s ease;
        }

        .lepass-progress-text {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            color: #333;
            font-weight: bold;
            text-shadow: 0 0 3px rgba(255,255,255,0.5);
        }

        /* LePASS Level Cards */
        .level-card {
            background-color: white;
            border-radius: 10px;
            padding: 15px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 15px;
            border-left: 4px solid #4880EC;
        }

        .current-level-card {
            border-left: 4px solid #FF416C;
            background-color: #fff9f9;
        }

        /* LePASS Section Headers */
        .lepass-section-header {
            border-bottom: 2px solid #4880EC;
            padding-bottom: 8px;
            margin-top: 30px;
            margin-bottom: 20px;
            color: #333;
        }

        /* LeBron Gallery */
        .lebron-gallery-container {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            justify-content: center;
        }

        .lebron-gallery-item {
            position: relative;
            width: 120px;
            text-align: center;
            margin-bottom: 15px;
        }

        .lebron-gallery-item img {
            border-radius: 8px;
            box-shadow: 0 3px 6px rgba(0,0,0,0.1);
            transition: transform 0.2s ease;
        }

        .lebron-gallery-item img:hover {
            transform: scale(1.05);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }

        .lebron-gallery-caption {
            margin-top: 5px;
            font-size: 0.9rem;
            color: #333;
        }

        /* Rarity colors */
        .rarity-common {
            border-left: 4px solid #7E7F7E; /* Gray */
        }

        .rarity-uncommon {
            border-left: 4px solid #4AAA4E; /* Green */
        }

        .rarity-rare {
            border-left: 4px solid #3B78DB; /* Blue */
        }

        .rarity-epic {
            border-left: 4px solid #9D43D9; /* Purple */
        }

        .rarity-legendary {
            border-left: 4px solid #FFA500; /* Orange */
        }
    </style>
    """, unsafe_allow_html=True)

def display_game():
    st.markdown("<h1 class='game-title'>🏀 LeBron Boss Battle</h1>", unsafe_allow_html=True)
    player = st.session_state.player
    lebron = st.session_state.lebron
    st.markdown(f"### Round {st.session_state.round}")
    col1, col2 = st.columns(2)
    with col1:
        display_character_card(player, is_player=True)
    with col2:
        display_character_card(lebron, is_player=False)

    if player.is_alive() and lebron.is_alive():
        # Player chooses action for this round
        st.markdown("### Choose Your Action")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            attack_disabled = player.stamina < 15
            if st.button("🏀 Attack", disabled=attack_disabled, use_container_width=True,
                         help="Basic attack (Cost: 15 Stamina, +10 Special Meter)"):
                st.session_state.current_player_action = "attack"
                process_round()
                st.rerun()
            st.markdown("<div class='move-info'>Costs 15 stamina<br>+10 special meter</div>", unsafe_allow_html=True)
        with col2:
            defend_disabled = player.stamina < 10
            if st.button("🛡️ Defend", disabled=defend_disabled, use_container_width=True,
                         help="Reduce incoming damage by 50% (Cost: 10 Stamina, +15 Special Meter)"):
                st.session_state.current_player_action = "defend"
                process_round()
                st.rerun()
            st.markdown("<div class='move-info'>Costs 10 stamina<br>+15 special meter<br>Reduces damage by 50%</div>", unsafe_allow_html=True)
        with col3:
            if st.button("💤 Rest", use_container_width=True,
                         help="Recover 25-40 Stamina (+5 Special Meter)"):
                st.session_state.current_player_action = "rest"
                process_round()
                st.rerun()
            st.markdown("<div class='move-info'>Recover 25-40 stamina<br>+5 special meter</div>", unsafe_allow_html=True)
        with col4:
            special_disabled = player.special_meter < 100 or player.stamina < 25
            if st.button("⭐ Special Attack", disabled=special_disabled, use_container_width=True,
                         help="Powerful attack that deals massive damage (Requires: Full Special Meter, Costs: 25 Stamina)"):
                st.session_state.current_player_action = "special"
                process_round()
                st.rerun()
            st.markdown("<div class='move-info'>Requires 100% special meter<br>Costs 25 stamina<br>Deals 40-60 damage</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='game-over-container'>", unsafe_allow_html=True)

        # ------------------- TIE CHECK -------------------
        if st.session_state.player.health == 0 and st.session_state.lebron.health == 0:
            st.markdown("## 🤝 TIE! 🤝")
            st.markdown("### It's a draw! You and LeBron both fell at the same time.")

            tie_xp = 70
            if not hasattr(st.session_state, 'username'):
                st.session_state.username = "Guest"
            username = st.session_state.username

            conn = sqlite3.connect("users.db")
            c = conn.cursor()
            c.execute("SELECT xp, level FROM users WHERE username = ?", (username,))
            result = c.fetchone()
            if result:
                current_xp, current_level = result
                new_xp = current_xp + tie_xp
                new_level = current_level
                while new_level < 60 and new_xp >= xp_required_for_level(new_level + 1):
                    new_level += 1
                c.execute("UPDATE users SET xp = ?, level = ? WHERE username = ?", (new_xp, new_level, username))
                conn.commit()
            conn.close()

            st.markdown(f"**TIE XP:** +{tie_xp} (No W/L changes)")

            updated_stats = get_user_stats(username)
            st.markdown(f"**Total XP:** {updated_stats['xp']} XP")
            st.markdown(f"**Current Level:** {updated_stats['level']}")
            st.markdown(f"**Record:** {updated_stats['wins']}W - {updated_stats['losses']}L")
            st.session_state.xp_already_awarded = True

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Play Again", use_container_width=True):
                    st.session_state.game_started = False
                    st.session_state.log = []
                    st.session_state.restart_game = True
                    st.session_state.round = 1
                    st.rerun()
            with col2:
                if st.button("View LePASS", use_container_width=True):
                    st.session_state.page = "LePASS"
                    st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)
            return
        # ------------------- END TIE CHECK ----------------

        # Determine battle outcome and award XP
        won = player.is_alive()

        # Set a default username if not present (for testing)
        if not hasattr(st.session_state, 'username'):
            st.session_state.username = "Guest"

        # Call end_battle_with_xp to process battle results and store in session_state
        updated_stats = end_battle_with_xp(player, lebron, won)

        # Get battle results from session state
        battle_results = st.session_state.battle_results
        xp_earned = battle_results["xp_earned"]
        leveled_up = battle_results["leveled_up"]
        new_level = battle_results["new_level"]

        if won:
            st.markdown("## 🏆 VICTORY! 🏆")
            st.markdown("### You defeated LeBron James!")
            st.balloons()
        else:
            st.markdown("## 💀 DEFEAT! 💀")
            st.markdown("### LeBron traded you!")

        st.markdown(f"**Final Score:** Round {st.session_state.round}")
        st.markdown("**Battle Stats:**")
        st.markdown(f"- Your remaining health: {player.health}/{player.max_health}")
        st.markdown(f"- LeBron's remaining health: {lebron.health}/{lebron.max_health}")

        # Display XP gained and current stats
        st.markdown(f"**XP Earned:** +{xp_earned} XP")
        st.markdown(f"**Total XP:** {battle_results['total_xp']} XP")
        st.markdown(f"**Current Level:** {new_level}")
        st.markdown(f"**Record:** {battle_results['wins']}W - {battle_results['losses']}L")

        if leveled_up:
            st.success(f"🎉 LEVEL UP! You reached Level {new_level}!")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Play Again", use_container_width=True):
                st.session_state.game_started = False
                st.session_state.log = []
                st.session_state.restart_game = True
                st.session_state.round = 1
                st.rerun()
        with col2:
            if st.button("View LePASS", use_container_width=True):
                st.session_state.page = "LePASS"
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    display_battle_log()

def display_difficulty_selection():
    st.markdown("<h1 class='game-title'>LeBron Boss Battle</h1>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image("https://wompimages.ampify.care/fetchimage?siteId=7575&v=2&jpgQuality=100&width=700&url=https%3A%2F%2Fi.kym-cdn.com%2Fentries%2Ficons%2Ffacebook%2F000%2F049%2F004%2Flebronsunshinecover.jpg", width=500)
    st.markdown("<div class='difficulty-card'>", unsafe_allow_html=True)
    st.markdown("<h2>Choose Your Difficulty</h2>", unsafe_allow_html=True)
    difficulty_options = {
        "Easy": "LeBron has 100 HP and uses basic moves mostly at random.",
        "Medium": "LeBron has 160 HP and plays more strategically.",
        "Hard": "LeBron has 180 HP and uses advanced tactics and powerful combos."
    }
    selected_difficulty = st.select_slider(
        "Select difficulty:",
        options=list(difficulty_options.keys()),
        value=st.session_state.difficulty
    )
    st.info(difficulty_options[selected_difficulty])
    st.session_state.difficulty = selected_difficulty
    show_tutorial = st.checkbox("Show Tutorial", value=not st.session_state.tutorial_shown)
    if show_tutorial:
        st.markdown("### How to Play:")
        st.markdown("""
        1. **Attack** - Deal damage but costs stamina  
        2. **Defend** - Reduce incoming damage by 50%  
        3. **Rest** - Recover stamina  
        4. **Special Attack** - Powerful move that requires a full special meter

        Fill your special meter by performing actions. Win by reducing LeBron's health to zero!
        """)
        st.session_state.tutorial_shown = True
    if st.button("Start Game", use_container_width=True):
        st.session_state.player = Player("You", 140, 100)
        st.session_state.lebron = LeBron(st.session_state.difficulty)
        st.session_state.turn = 0
        st.session_state.round = 1
        st.session_state.log = []
        st.session_state.action_taken = False
        st.session_state.game_started = True
        st.session_state.xp_already_awarded = False  # Reset flag when starting new game
        add_log_entry("The battle begins! Your turn first.", "system")
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# --------------------- Page UIs --------------------- #

def login_ui():
    st.markdown("<h1 class='auth-title'>Welcome Back</h1>", unsafe_allow_html=True)
    st.markdown("<p class='auth-subtitle'>Sign in to continue your battle</p>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='auth-logo'>", unsafe_allow_html=True)
    st.image("https://cdn-wp.thesportsrush.com/2021/10/faeeadb8-untitled-design-22.jpg?format=auto&w=3840&q=75", width=350)
    st.markdown("</div>", unsafe_allow_html=True)

    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")

    col1, col2, col3 = st.columns([1,3,1])
    with col2:
        if st.button("Sign In", use_container_width=True):
            if authenticate_user(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username
                st.success(f"Welcome, {username}!")
                st.session_state.page = "LePlay"
                st.rerun()
            else:
                st.error("Incorrect username or password")

    st.markdown("<div class='auth-footer'>", unsafe_allow_html=True)
    st.markdown("Don't have an account? Register an account now!", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # JavaScript to handle the register link click
    st.markdown("""
    <script>
        document.getElementById('register-link').addEventListener('click', function(e) {
            e.preventDefault();
            window.location.href = window.location.pathname + "?page=Register";
        });
    </script>
    """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

def lepass_ui():
    """Display the LePASS progression UI with gallery of unlocked LeBron images"""

    # Only allow access if logged in
    if not st.session_state.get("logged_in", False):
        st.error("You must be logged in to view LePASS!")
        st.session_state.page = "Login"
        st.rerun()

    # Add LePASS-specific CSS
    add_lepass_css()

    username = st.session_state.username
    user_stats = get_user_stats(username)
    current_level = user_stats["level"]
    current_xp = user_stats["xp"]
    wins = user_stats["wins"]
    losses = user_stats["losses"]

    # Calculate progress to next level
    progress = get_level_progress(current_xp, current_level)
    next_level_xp = xp_required_for_level(current_level + 1)
    xp_needed = next_level_xp - current_xp

    # Get current LeBron image
    current_image_url = get_lebron_image_url(current_level)
    next_image_url = get_lebron_image_url(current_level + 1) if current_level < 60 else current_image_url

    # UI Header
    st.markdown("<h1 class='game-title'>LePASS™ Battle Pass</h1>", unsafe_allow_html=True)

    # Player Stats Section
    col1, col2 = st.columns([1, 2])

    with col1:
        st.image(current_image_url, caption=f"Level {current_level} LeBron", width=250)

    with col2:
        st.markdown(f"### Welcome to your LePASS, {username}!")
        st.markdown(f"**Current Level:** {current_level}/60")

        # Progress bar with custom styling
        st.markdown(
            f"""
            <div class="lepass-progress-container">
                <div class="lepass-progress-bar" style="width: {progress * 100}%"></div>
                <div class="lepass-progress-text">{current_xp} / {next_level_xp} XP</div>
            </div>
            """, 
            unsafe_allow_html=True
        )

        if current_level < 60:
            st.markdown(f"**XP needed for Level {current_level + 1}:** {xp_needed} XP")
        else:
            st.markdown("**MAX LEVEL REACHED!** You've collected all LeBron images!")

        st.markdown(f"**Battle Record:** {wins} Wins / {losses} Losses")

    # Rewards Preview Section
    st.markdown("### Next Reward")
    if current_level < 60:
        col1, col2 = st.columns([1, 2])
        with col1:
            st.image(next_image_url, caption=f"Level {current_level + 1} LeBron", width=200)
        with col2:
            st.markdown(f"**Unlock at Level {current_level + 1}**")
            st.markdown(f"Earn **{xp_needed}** more XP to unlock!")
            st.markdown("Win battles against LeBron to earn XP. Higher difficulties and better performance grant more XP!")
    else:
        st.success("CONGRATULATIONS! You've reached MAX LEVEL and collected all 60 LeBron images!")

    # NEW SECTION: LeBron Gallery
    st.markdown("<h3 class='lepass-section-header'>Your LeBron Collection</h3>", unsafe_allow_html=True)

    # Add a gallery filter option
    view_options = ["All Unlocked", "By Rarity"]
    view_mode = st.radio("View mode:", view_options, horizontal=True)

    # Generate the gallery of unlocked LeBron images
    if view_mode == "All Unlocked":
        st.markdown("### Unlocked LeBrons")

        # Create a 5-column grid for displaying unlocked LeBron images
        column_count = 5
        gallery_cols = st.columns(column_count)

        # Determine which levels have been unlocked
        # All levels <= current_level are unlocked
        for level in range(1, current_level + 1):
            image_url = get_lebron_image_url(level)
            col_index = (level - 1) % column_count

            with gallery_cols[col_index]:
                st.image(image_url, caption=f"Level {level}", width=100)

    else:  # By Rarity
        # Group LeBron images by rarity tiers
        st.markdown("### Collection By Rarity")

        # Define rarity tiers (adjust ranges as needed)
        rarity_tiers = {
            "Common (Levels 1-15)": range(1, min(16, current_level + 1)),
            "Uncommon (Levels 16-30)": range(16, min(31, current_level + 1)),
            "Rare (Levels 31-45)": range(31, min(46, current_level + 1)),
            "Epic (Levels 46-55)": range(46, min(56, current_level + 1)),
            "Legendary (Levels 56-60)": range(56, min(61, current_level + 1))
        }

        # Display images grouped by rarity
        for rarity, level_range in rarity_tiers.items():
            if len(list(level_range)) > 0:  # Only show rarities that have unlocked items
                st.markdown(f"#### {rarity}")

                # Create expandable section for each rarity tier
                with st.expander("Show Collection", expanded=rarity == "Legendary (Levels 56-60)"):
                    column_count = 5
                    gallery_cols = st.columns(column_count)

                    for i, level in enumerate(level_range):
                        image_url = get_lebron_image_url(level)
                        col_index = i % column_count

                        with gallery_cols[col_index]:
                            st.image(image_url, caption=f"Level {level}", width=100)

    # Locked images section
    if current_level < 60:
        remaining = 60 - current_level
        st.markdown(f"### Locked LeBrons ({remaining} remaining)")
        st.info(f"You still have {remaining} LeBron images to unlock! Continue winning battles to unlock more.")

        # Show a teaser of what's to come
        teaser_level = min(current_level + 10, 60)
        st.markdown(f"Reach level {teaser_level} to unlock:")
        teaser_image = get_lebron_image_url(teaser_level)
        st.image(teaser_image, caption=f"Level {teaser_level} Preview", width=150)

    # XP Earning Guide
    st.markdown("<h3 class='lepass-section-header'>How to Earn XP</h3>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("#### Easy Difficulty")
        st.markdown("- Win: 75-100 XP")
        st.markdown("- Loss: 25-50 XP")
    with col2:
        st.markdown("#### Medium Difficulty")
        st.markdown("- Win: 112-150 XP")
        st.markdown("- Loss: 37-75 XP")
    with col3:
        st.markdown("#### Hard Difficulty")
        st.markdown("- Win: 150-200 XP")
        st.markdown("- Loss: 50-100 XP")

    st.info("💡 **TIP:** Higher health at the end of battle = more XP!")

    # Level Progression Chart
    st.markdown("<h3 class='lepass-section-header'>Level Progression</h3>", unsafe_allow_html=True)

    # Create data for level progression chart
    levels = list(range(1, 61))
    xp_requirements = [xp_required_for_level(level) for level in levels]

    # Highlight current level in chart
    st.vega_lite_chart({
        "data": {"values": [{"level": i, "xp": xp_requirements[i-1], "current": i == current_level} for i in levels]},
        "mark": {"type": "line", "point": True},
        "encoding": {
            "x": {"field": "level", "type": "quantitative", "title": "Level"},
            "y": {"field": "xp", "type": "quantitative", "title": "XP Required"},
            "color": {"field": "current", "type": "nominal", "scale": {"range": ["#4880EC", "#FF416C"]}, "legend": None},
            "size": {"field": "current", "type": "nominal", "scale": {"range": [2, 5]}, "legend": None}
        },
        "width": 700,
        "height": 300
    })

    # Note about final levels
    st.markdown("""
        **Note:** Levels 1-50 increase linearly, while levels 51-60 require exponentially more XP.
        The final 10 levels are meant to be challenging to achieve!
    """)

    # Return to game button
    if st.button("Return to Game", use_container_width=True):
        st.session_state.page = "LePlay"
        st.rerun()

def lecareer_ui():
    """Display the LeCareer page showing LeBron's career journey with text and images"""
    
    # Only allow access if logged in
    if not st.session_state.get("logged_in", False):
        st.error("You must be logged in to view LeCareer!")
        st.session_state.page = "Login"
        st.rerun()
    
    # Add custom CSS for LeCareer page
    st.markdown("""
    <style>
        /* LeCareer specific styling */
        .career-header {
            text-align: center;
            margin-bottom: 30px;
        }
        
        .career-section {
            background-color: white;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 30px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            border-left: 6px solid #4880EC;
        }
        
        .career-section.cavaliers-1 {
            border-left-color: #860038; /* Cavaliers wine color */
        }
        
        .career-section.heat {
            border-left-color: #98002E; /* Heat red */
        }
        
        .career-section.cavaliers-2 {
            border-left-color: #FDBB30; /* Cavaliers gold */
        }
        
        .career-section.lakers {
            border-left-color: #552583; /* Lakers purple */
        }
        
        .career-title {
            font-size: 1.8rem;
            margin-bottom: 15px;
            font-weight: bold;
        }
        
        .career-years {
            font-size: 1.2rem;
            color: #666;
            margin-bottom: 15px;
        }
        
        .career-stats {
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            margin: 15px 0;
        }
        
        .career-achievements {
            margin-top: 15px;
        }
        
        .career-image-placeholder {
            background-color: #eee;
            height: 250px;
            border-radius: 10px;
            display: flex;
            justify-content: center;
            align-items: center;
            margin: 15px 0;
            position: relative;
            overflow: hidden;
        }
        
        .achievement-badge {
            display: inline-block;
            background-color: #4880EC;
            color: white;
            border-radius: 20px;
            padding: 5px 10px;
            margin-right: 8px;
            margin-bottom: 8px;
            font-size: 0.9rem;
        }
        
        .achievement-badge.championship {
            background-color: #FFD700; /* Gold for championships */
            color: #333;
        }
        
        .achievement-badge.mvp {
            background-color: #C0C0C0; /* Silver for MVPs */
            color: #333;
        }
        
        .timeline-container {
            position: relative;
            padding-left: 20px;
            margin: 30px 0;
        }
        
        .timeline-bar {
            position: absolute;
            top: 0;
            bottom: 0;
            left: 0;
            width: 4px;
            background: linear-gradient(to bottom, #4880EC, #019CAD);
        }
        
        .timeline-point {
            position: absolute;
            left: -8px;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background-color: #4880EC;
            border: 3px solid white;
            box-shadow: 0 0 0 3px rgba(72, 128, 236, 0.2);
        }
    </style>
    """, unsafe_allow_html=True)
    
    # UI Header
    st.markdown("<h1 class='game-title'>LeCareer Journey</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; margin-bottom: 30px;'>The storied career path of King James</p>", unsafe_allow_html=True)
    
    # Timeline Overview
    st.markdown("<div class='timeline-container'>", unsafe_allow_html=True)
    st.markdown("<div class='timeline-bar'></div>", unsafe_allow_html=True)
    
    timeline_points = [
        {"year": "2003", "top": "0%", "text": "Drafted #1 Overall"},
        {"year": "2010", "top": "20%", "text": "The Decision"},
        {"year": "2014", "top": "40%", "text": "Return to Cleveland"},
        {"year": "2016", "top": "60%", "text": "Cleveland Championship"},
        {"year": "2018", "top": "80%", "text": "Joins Lakers"},
        {"year": "2020", "top": "100%", "text": "Lakers Championship"}
    ]
    
    for point in timeline_points:
        st.markdown(f"""
        <div class='timeline-point' style='top: {point["top"]};'></div>
        <div style='margin-left: 25px; padding: 10px 0; position: relative; top: calc({point["top"]} - 10px);'>
            <strong>{point["year"]}</strong> - {point["text"]}
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Career Section 1: First Cleveland Stint
    st.markdown("<div class='career-section cavaliers-1'>", unsafe_allow_html=True)
    st.markdown("<h2 class='career-title'>Cleveland Cavaliers (First Stint)</h2>", unsafe_allow_html=True)
    st.markdown("<div class='career-years'>2003-2010</div>", unsafe_allow_html=True)
    
    col1, col2 = st.columns([3, 2])
    
    with col1:
        st.markdown("""
        LeBron James began his NBA journey with his hometown team after being selected as the #1 overall pick in the 2003 NBA Draft. Coming straight out of St. Vincent-St. Mary High School in Akron, Ohio, James was heralded as "The Chosen One" and faced immense pressure to deliver.
        
        During his first stint with the Cavaliers, James transformed the franchise from lottery regulars to championship contenders. He led the team to their first NBA Finals appearance in 2007, though they were swept by the San Antonio Spurs.
        
        Despite his individual brilliance, James couldn't secure a championship in Cleveland during this period, leading to his controversial departure in 2010 via "The Decision" television special.
        """)
        
        st.markdown("<div class='career-stats'>", unsafe_allow_html=True)
        st.markdown("**First Cleveland Stint Stats:**", unsafe_allow_html=True)
        st.markdown("- Games: 548", unsafe_allow_html=True)
        st.markdown("- Points: 15,251 (27.8 PPG)", unsafe_allow_html=True)
        st.markdown("- Rebounds: 3,861 (7.0 RPG)", unsafe_allow_html=True)
        st.markdown("- Assists: 3,810 (6.9 APG)", unsafe_allow_html=True)
        st.markdown("- Field Goal %: 47.5%", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("<div class='career-achievements'>", unsafe_allow_html=True)
        st.markdown("**Key Achievements:**", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge mvp'>MVP (2009, 2010)</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge'>Rookie of the Year (2004)</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge'>6× All-Star</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge'>6× All-NBA</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge'>2× All-Defensive Team</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge'>Scoring Champion (2008)</span>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col2:
        st.image('https://upload.wikimedia.org/wikipedia/commons/thumb/b/bf/LebronWizards2.jpg/1200px-LebronWizards2.jpg')
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Career Section 2: Miami Heat
    st.markdown("<div class='career-section heat'>", unsafe_allow_html=True)
    st.markdown("<h2 class='career-title'>Miami Heat</h2>", unsafe_allow_html=True)
    st.markdown("<div class='career-years'>2010-2014</div>", unsafe_allow_html=True)
    
    col1, col2 = st.columns([3, 2])
    
    with col1:
        st.markdown("""
        In the summer of 2010, LeBron made the controversial decision to join forces with Dwyane Wade and Chris Bosh in Miami, forming what became known as "The Big Three." His famous words "I'm taking my talents to South Beach" became an instant cultural phenomenon.
        
        This move marked a turning point in his career. After a disappointing loss to the Dallas Mavericks in the 2011 Finals, James responded with perhaps the most dominant stretch of his career, winning back-to-back championships in 2012 and 2013 against the Oklahoma City Thunder and San Antonio Spurs respectively.
        
        During his time in Miami, LeBron evolved as both a player and a leader. He expanded his game, becoming more efficient while developing his post skills and three-point shooting. His defensive prowess reached its peak during this period, as he regularly guarded multiple positions and anchored Miami's aggressive defensive schemes.
        """)
        
        st.markdown("<div class='career-stats'>", unsafe_allow_html=True)
        st.markdown("**Miami Heat Stats:**", unsafe_allow_html=True)
        st.markdown("- Games: 294", unsafe_allow_html=True)
        st.markdown("- Points: 7,919 (26.9 PPG)", unsafe_allow_html=True)
        st.markdown("- Rebounds: 2,280 (7.8 RPG)", unsafe_allow_html=True)
        st.markdown("- Assists: 1,968 (6.7 APG)", unsafe_allow_html=True)
        st.markdown("- Field Goal %: 54.3%", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("<div class='career-achievements'>", unsafe_allow_html=True)
        st.markdown("**Key Achievements:**", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge championship'>NBA Champion (2012, 2013)</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge mvp'>Finals MVP (2012, 2013)</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge mvp'>Regular Season MVP (2012, 2013)</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge'>4× All-Star</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge'>4× All-NBA First Team</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge'>4× All-Defensive First Team</span>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col2:
        st.image('https://upload.wikimedia.org/wikipedia/commons/thumb/7/7d/LeBron_James_vs_Washington_3-30-11.jpg/800px-LeBron_James_vs_Washington_3-30-11.jpg')
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Career Section 3: Cleveland Return
    st.markdown("<div class='career-section cavaliers-2'>", unsafe_allow_html=True)
    st.markdown("<h2 class='career-title'>Cleveland Cavaliers (Return)</h2>", unsafe_allow_html=True)
    st.markdown("<div class='career-years'>2014-2018</div>", unsafe_allow_html=True)
    
    col1, col2 = st.columns([3, 2])
    
    with col1:
        st.markdown("""
        In 2014, LeBron made the emotional decision to return to Cleveland, declaring in a famous Sports Illustrated essay that "I'm coming home." His stated goal was clear: bring a championship to Cleveland, a city that hadn't won a major sports title in over 50 years.
        
        Teaming up with Kyrie Irving and later Kevin Love, James led the Cavaliers to four consecutive NBA Finals appearances against the Golden State Warriors dynasty. The pinnacle of this run came in 2016 when the Cavaliers completed a historic comeback from a 3-1 deficit to win the NBA Finals, with James delivering the iconic chase-down block on Andre Iguodala in Game 7.
        
        This championship fulfilled his promise to Cleveland and cemented his legacy as one of the greatest players of all time. Despite falling short in his other Finals appearances during this period, James continued to elevate his game, particularly in the playoffs where he routinely put up historic performances.
        """)
        
        st.markdown("<div class='career-stats'>", unsafe_allow_html=True)
        st.markdown("**Cleveland Return Stats:**", unsafe_allow_html=True)
        st.markdown("- Games: 301", unsafe_allow_html=True)
        st.markdown("- Points: 7,868 (26.1 PPG)", unsafe_allow_html=True)
        st.markdown("- Rebounds: 2,391 (7.9 RPG)", unsafe_allow_html=True)
        st.markdown("- Assists: 2,279 (7.6 APG)", unsafe_allow_html=True)
        st.markdown("- Field Goal %: 52.0%", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("<div class='career-achievements'>", unsafe_allow_html=True)
        st.markdown("**Key Achievements:**", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge championship'>NBA Champion (2016)</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge mvp'>Finals MVP (2016)</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge'>4× All-Star</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge'>4× All-NBA First Team</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge'>3× All-Defensive Team</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge'>4× Eastern Conference Championships</span>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col2:
        st.image('https://scontent.fyyz1-1.fna.fbcdn.net/v/t39.30808-6/464428141_8297619890365839_2314504659794794456_n.jpg?_nc_cat=109&ccb=1-7&_nc_sid=0b6b33&_nc_ohc=IJxGRrIFw2EQ7kNvgFXmTpH&_nc_oc=Adkb2OuJ5YaUUf1yLG762rkKEWVMYw57S09XciGgilJu45nrOQOOuYdZTjnN2d87sH4a5x7gRHJ0GiVLLiOS817Z&_nc_zt=23&_nc_ht=scontent.fyyz1-1.fna&_nc_gid=X9OikiEnGqva6R9dS-eGXQ&oh=00_AYG3aMcnzXeExfTojbaLAyVTSj-zPhLB-4SLkfQtdQHfbw&oe=67E655FD')
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Career Section 4: Los Angeles Lakers
    st.markdown("<div class='career-section lakers'>", unsafe_allow_html=True)
    st.markdown("<h2 class='career-title'>Los Angeles Lakers</h2>", unsafe_allow_html=True)
    st.markdown("<div class='career-years'>2018-Present</div>", unsafe_allow_html=True)
    
    col1, col2 = st.columns([3, 2])
    
    with col1:
        st.markdown("""
        In 2018, LeBron decided to join the storied Los Angeles Lakers franchise, signing a four-year contract. This move represented both a basketball decision and a lifestyle/business choice, as James expanded his media company and entertainment ventures in Hollywood.
        
        After a challenging first season marred by injury, the Lakers acquired Anthony Davis in 2019, forming a dominant duo. During the pandemic-interrupted 2019-20 season, James led the Lakers to the NBA championship in the Orlando "bubble," earning his fourth NBA title and fourth Finals MVP award.
        
        In Los Angeles, James has continued to defy age, remaining one of the league's premier players well into his late 30s. He became the NBA's all-time leading scorer in February 2023, surpassing Kareem Abdul-Jabbar's long-standing record, and has continued to adapt his game as he's aged.
        
        His tenure with the Lakers has also seen him embrace his role as one of the game's elder statesmen and most influential voices, using his platform to address social issues while still competing at the highest level.
        """)
        
        st.markdown("<div class='career-stats'>", unsafe_allow_html=True)
        st.markdown("**Lakers Stats (through 2024):**", unsafe_allow_html=True)
        st.markdown("- Games: 342", unsafe_allow_html=True)
        st.markdown("- Points: 9,650 (27.1 PPG)", unsafe_allow_html=True)
        st.markdown("- Rebounds: 3,168 (8.1 RPG)", unsafe_allow_html=True)
        st.markdown("- Assists: 3,091 (8.0 APG)", unsafe_allow_html=True)
        st.markdown("- Field Goal %: 51.2%", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("<div class='career-achievements'>", unsafe_allow_html=True)
        st.markdown("**Key Achievements:**", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge championship'>NBA Champion (2020)</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge mvp'>Finals MVP (2020)</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge'>NBA All-Time Scoring Leader</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge'>All-Star Game MVP (2023)</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge'>6× All-Star</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge'>5× All-NBA Team</span>", unsafe_allow_html=True)
        st.markdown("<span class='achievement-badge'>Assists Leader (2020)</span>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col2:
        st.image('https://cdn.nba.com/manage/2020/10/lebron-james-lakers-687x588.jpg')
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Legacy Section
    st.markdown("<div class='career-section'>", unsafe_allow_html=True)
    st.markdown("<h2 class='career-title'>Career Legacy</h2>", unsafe_allow_html=True)
    
    st.markdown("""
    Throughout his illustrious career spanning over two decades, LeBron James has transcended basketball to become a global icon. His impact extends far beyond his on-court achievements:

    **Basketball Evolution**: James redefined the modern NBA superstar with his unique combination of size, strength, skill, and basketball IQ. His versatility as a playmaker and scorer created a blueprint for future generations.

    **Business Empire**: Beyond basketball, LeBron has built a massive business portfolio including media production (SpringHill Company), investments, endorsements, and ownership stakes in sports teams.

    **Social Impact**: Using his platform for activism and social change, James established the I PROMISE School in Akron, the LeBron James Family Foundation, and has been outspoken on social justice issues.

    **Cultural Influence**: From "The Decision" to "More Than An Athlete," LeBron has shaped cultural conversations and redefined athlete empowerment in the modern era.

    No matter where one stands in the endless GOAT debates, LeBron James' career represents one of the most remarkable athletic journeys in sports history—from a teenage phenom to a global icon who has consistently exceeded the enormous expectations placed upon him.
    """)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Career Points", "40,000+", "All-time leader")
    with col2:
        st.metric("Championships", "4", "with 3 different teams")
    with col3:
        st.metric("MVP Awards", "4", "Regular Season")
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Return to game button
    if st.button("Return to Game", use_container_width=True):
        st.session_state.page = "LePlay"
        st.rerun()

def register_ui():
    st.markdown("<h1 class='auth-title'>Create Account</h1>", unsafe_allow_html=True)
    st.markdown("<p class='auth-subtitle'>Join the battle against LeBron</p>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='auth-logo'>", unsafe_allow_html=True)
    st.image("https://www.the-sun.com/wp-content/uploads/sites/6/2023/10/AS_LEBRON-MEMES_OP.jpg?strip=all&quality=100&w=1080&h=1080&crop=1", width=250)
    st.markdown("</div>", unsafe_allow_html=True)

    username = st.text_input("Choose a Username", key="register_username")
    password = st.text_input("Create Password", type="password", key="register_password")

    col1, col2, col3 = st.columns([1,3,1])
    with col2:
        if st.button("Create Account", use_container_width=True):
            if register_user(username, password):
                st.success("Account created successfully!")
                st.session_state.page = "Login"
                st.rerun()
            else:
                st.error("Username already exists.")

    st.markdown("<div class='auth-footer'>", unsafe_allow_html=True)
    st.markdown("Already have an account? Sign in!", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # JavaScript to handle the login link click
    st.markdown("""
    <script>
        document.getElementById('login-link').addEventListener('click', function(e) {
            e.preventDefault();
            window.location.href = window.location.pathname + "?page=Login";
        });
    </script>
    """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

def logout_ui():
    st.markdown("<h1 class='auth-title'>Log Out</h1>", unsafe_allow_html=True)
    st.markdown("<p class='auth-subtitle'>Are you sure you want to leave?</p>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='text-align: center; margin: 30px 0;'>", unsafe_allow_html=True)
    st.image("https://www.nickiswift.com/img/gallery/the-transformation-of-lebron-james-from-childhood-to-36-years-old/l-intro-1625330663.jpg", width=700)
    st.markdown("</div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Cancel", use_container_width=True):
            st.session_state.page = "LePlay"
            st.rerun()
    with col2:
        if st.button("Confirm LeLogout", use_container_width=True):
            for key in list(st.session_state.keys()):
                if key != "page":
                    del st.session_state[key]
            st.success("Logged out successfully!")
            st.session_state.page = "Login"
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

def play_ui():
    # Only allow access if logged in
    if not st.session_state.get("logged_in", False):
        st.error("You must be logged in to play!")
        st.session_state.page = "Login"
        st.rerun()
    initialize_session_state()
    if not st.session_state.game_started:
        display_difficulty_selection()
    else:
        display_game()

# --------------------- Custom CSS --------------------- #

st.markdown("""
<style>
    [data-testid="stAppViewContainer"] {
        background-image: url("https://i.imgur.com/v5gUNvA.png");
        background-size: 90%;
        background-position: 300% ;
        background-repeat: no-repeat;
        background-attachment: local;
    }

    /* Add a semi-transparent overlay to reduce the image opacity */
    [data-testid="stAppViewContainer"]::after {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-color: rgba(255, 255, 255, 0.7); /* White overlay with 70% opacity */
        z-index: -1;
        pointer-events: none;
    }

    .game-title {
        font-size: 3rem;
        font-weight: 800;
        background: linear-gradient(45deg, #4880EC, #019CAD);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 30px;
    }
    .player-card, .lebron-card {
        background-color: white;
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    .custom-avatar-container {
        border-radius: 15px;
        overflow: hidden;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        margin-bottom: 10px;
    }
    .stat-label {
        font-weight: bold;
        margin-bottom: 5px;
    }
    .move-info {
        font-size: 0.9rem;
        color: #666;
        margin-top: 4px;
    }
    .log-entry {
        padding: 8px 12px;
        margin: 8px 0;
        border-radius: 8px;
    }
    .player-log {
        background-color: #e6f7ff;
        border-left: 4px solid #4880EC;
    }
    .lebron-log {
        background-color: #fff1f0;
        border-left: 4px solid #FF416C;
    }
    .system-log {
        background-color: #f6ffed;
        border-left: 4px solid #52c41a;
    }
    .auth-container {
        max-width: 450px;
        margin: 0 auto;
        padding: 30px;
        background: white;
        border-radius: 12px;
        box-shadow: 0 6px 20px rgba(0,0,0,0.1);
    }
    .auth-header {
        text-align: center;
        margin-bottom: 25px;
    }
    .auth-title {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(45deg, #4880EC, #019CAD);
        -webkit-background-clip: text;
        -webkit-text-fill-color: #A70EC9;
        margin-bottom: 5px;
    }
    .auth-subtitle {
        color: #666;
        font-size: 1.1rem;
    }
    .auth-input {
        margin-bottom: 20px;
    }
    .auth-button {
        width: 100%;
        background: linear-gradient(45deg, #4880EC, #019CAD);
        color: white;
        border: none;
        padding: 12px;
        border-radius: 6px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
    }
    .auth-button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    .auth-footer {
        text-align: center;
        margin-top: 20px;
        font-size: 0.9rem;
        color: #666;
    }
    .auth-link {
        color: #4880EC;
        text-decoration: none;
        font-weight: 600;
    }
    .auth-logo {
        text-align: center;
        margin-bottom: 20px;
    }
    .sidebar-header {
        display: flex;
        align-items: center;
        padding: 10px 0;
        margin-bottom: 20px;
    }
    .sidebar-logo {
        width: 1500px;
        height: 80px;
        border-radius: 50%;
        margin-right: 20px;
        object-fit: cover;
    }
    .sidebar-title {
        font-weight: 1600;
        color: #eeff40;
    }
    /* Target the entire sidebar container */
    [data-testid="stSidebar"] {
        background-image: url('https://pbs.twimg.com/media/E_sz6efVIAIXSmP.jpg');
        background-size: cover;
        background-position: 90%;
        background-repeat: no-repeat;
        position: relative;
    }

    /* Create an overlay */
    [data-testid="stSidebar"]::before {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-color: rgba(0, 0, 0, 0.6);
        z-index: 0;
    }

    /* Make sure sidebar content is above the overlay */
    [data-testid="stSidebar"] > div {
        position: relative;
        z-index: 1;
    }

    /* Style for sidebar text */
    [data-testid="stSidebar"] .stRadio label,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] div {
        color: white !important;
        font-weight: 500;
        text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.8);
    }
</style>
""", unsafe_allow_html=True)

# --------------------- Main Navigation --------------------- #

def main():
    init_db()

    # Set default page based on login state
    if "page" not in st.session_state:
        st.session_state.page = "Login" if not st.session_state.get("logged_in", False) else "LePlay"

    # Sidebar navigation
    if st.session_state.get("logged_in", False):
        nav_options = ["LePlay", "LePASS", "LeLogout", "LeCareer"]
    else:
        nav_options = ["Login", "Register"]


    # Add some space at the top of the sidebar for the image effect
    st.sidebar.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)

    # Sidebar navigation with styled title
    st.sidebar.markdown("<h2 style='color: white; text-align: center; text-shadow: 2px 2px 4px black;'>LeBattle Sim</h2>", unsafe_allow_html=True)

    selected_page = st.sidebar.radio("", nav_options, index=nav_options.index(st.session_state.page) if st.session_state.page in nav_options else 0)
    st.session_state.page = selected_page

    # User status
    if st.session_state.get("logged_in", False):
        st.sidebar.markdown(f"<div style='color: white; text-align: center; margin-top: 20px; padding: 10px; background-color: rgba(0,0,0,0.3); border-radius: 5px;'>Logged in as: <b>{st.session_state['username']}</b></div>", unsafe_allow_html=True)

    if st.session_state.page == "Login":
        login_ui()
    elif st.session_state.page == "Register":
        register_ui()
    elif st.session_state.page == "LePlay":
        play_ui()
    elif st.session_state.page == "LePASS":
        lepass_ui()  # This calls the LePASS UI function you defined.
    elif st.session_state.page == "LeLogout":
        logout_ui()
    elif st.session_state.page == "LeCareer":
        lecareer_ui()


if __name__ == "__main__":
    main()
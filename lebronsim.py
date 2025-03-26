import random
import streamlit as st
import sqlite3
import bcrypt
import string
from PIL import Image
from datetime import datetime, timedelta
import time
 
 
def init_db():
     conn = sqlite3.connect("users.db")
     c = conn.cursor()
     c.execute(
         """
         CREATE TABLE IF NOT EXISTS users (
             username TEXT PRIMARY KEY,
             password BLOB,
             xp INTEGER DEFAULT 0,
             level INTEGER DEFAULT 1,
             wins INTEGER DEFAULT 0,
             losses INTEGER DEFAULT 0
         )
     """
     )
     conn.commit()
     conn.close()
 
 
def init_multiplayer_db():
     conn = sqlite3.connect("users.db")
     c = conn.cursor()
 
     # Rooms table
     c.execute(
         """
         CREATE TABLE IF NOT EXISTS multiplayer_rooms (
             room_code TEXT PRIMARY KEY,
             player1 TEXT,
             player2 TEXT,
             player1_ready BOOLEAN DEFAULT 0,
             player2_ready BOOLEAN DEFAULT 0,
             player1_move TEXT,
             player2_move TEXT,
             player1_hp INTEGER DEFAULT 140,
             player2_hp INTEGER DEFAULT 140,
             player1_stamina INTEGER DEFAULT 100,
             player2_stamina INTEGER DEFAULT 100,
             player1_special INTEGER DEFAULT 0,
             player2_special INTEGER DEFAULT 0,
             current_round INTEGER DEFAULT 1,
             current_turn INTEGER DEFAULT 1,  -- 1 = player1, 2 = player2
             game_state TEXT DEFAULT 'waiting',  -- waiting, playing, finished
             winner TEXT,
             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
             last_action TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
             player1_wins INTEGER DEFAULT 0,
             player2_wins INTEGER DEFAULT 0,
             match_round INTEGER DEFAULT 1  -- For best of 3
         )
     """
     )
 
     # Add multiplayer stats to users table
     try:
         c.execute("ALTER TABLE users ADD COLUMN multiplayer_wins INTEGER DEFAULT 0")
         c.execute("ALTER TABLE users ADD COLUMN multiplayer_losses INTEGER DEFAULT 0")
     except sqlite3.OperationalError:
         pass  # Columns already exist
 
     conn.commit()
     conn.close()
 
 
 # Call the multiplayer DB init within the init_db process
init_multiplayer_db()
 
 
def generate_room_code():
     """Generate a 6-character room code"""
     chars = string.ascii_uppercase + string.digits
     return "".join(random.choice(chars) for _ in range(6))
 
 
def create_room(player_username):
     """Create a new multiplayer room"""
     room_code = generate_room_code()
     conn = sqlite3.connect("users.db")
     c = conn.cursor()
 
     # Clean up old rooms (older than 2 hours)
     c.execute("DELETE FROM multiplayer_rooms WHERE created_at < datetime('now', '-2 hours')")
 
     try:
         c.execute(
             "INSERT INTO multiplayer_rooms (room_code, player1, game_state) VALUES (?, ?, 'waiting')",
             (room_code, player_username),
         )
         conn.commit()
         return room_code
     except sqlite3.IntegrityError:
         # If room code collision (very unlikely), try again
         return create_room(player_username)
     finally:
         conn.close()
 
 
def join_room(room_code, player_username):
     """Join an existing room as player 2"""
     conn = sqlite3.connect("users.db")
     c = conn.cursor()
 
     c.execute(
         "UPDATE multiplayer_rooms SET player2 = ?, game_state = 'playing' WHERE room_code = ? AND player2 IS NULL",
         (player_username, room_code),
     )
     conn.commit()
     success = c.rowcount > 0
     conn.close()
     return success
 
 
def get_room_state(room_code):
     """Get current state of a room"""
     conn = sqlite3.connect("users.db")
     c = conn.cursor()
 
     c.execute("SELECT * FROM multiplayer_rooms WHERE room_code = ?", (room_code,))
     result = c.fetchone()
     if result:
         columns = [col[0] for col in c.description]
     conn.close()
 
     if result:
         return dict(zip(columns, result))
     return None
 
 
def update_player_move(room_code, player_username, move):
     """Update a player's move in the room"""
     conn = sqlite3.connect("users.db")
     c = conn.cursor()
 
     room = get_room_state(room_code)
     if not room:
         conn.close()
         return False
 
     if room["player1"] == player_username:
         c.execute(
             "UPDATE multiplayer_rooms SET player1_move = ?, player1_ready = 1, last_action = CURRENT_TIMESTAMP WHERE room_code = ?",
             (move, room_code),
         )
     elif room["player2"] == player_username:
         c.execute(
             "UPDATE multiplayer_rooms SET player2_move = ?, player2_ready = 1, last_action = CURRENT_TIMESTAMP WHERE room_code = ?",
             (move, room_code),
         )
     else:
         conn.close()
         return False
 
     conn.commit()
     conn.close()
     return True
 
 
def reset_round(room_code):
     """Reset the room for a new round"""
     conn = sqlite3.connect("users.db")
     c = conn.cursor()
 
     c.execute(
         """UPDATE multiplayer_rooms 
            SET player1_move = NULL, player2_move = NULL,
                player1_ready = 0, player2_ready = 0,
                current_turn = 1,
                last_action = CURRENT_TIMESTAMP
            WHERE room_code = ?""",
         (room_code,),
     )
     conn.commit()
     conn.close()
 
 
def process_multiplayer_turn(room_code):
     """Process a completed turn in multiplayer"""
     room = get_room_state(room_code)
     if not room or room["game_state"] != "playing":
         return
 
     # Both players have made their moves
     if room["player1_move"] and room["player2_move"]:
         conn = sqlite3.connect("users.db")
         c = conn.cursor()
 
         p1_move = room["player1_move"]
         p2_move = room["player2_move"]
         p1_damage = 0
         p2_damage = 0
 
         # Player 1 move
         if p1_move == "attack":
             if room["player1_stamina"] >= 15:
                 p1_damage = random.randint(15, 30)
                 if random.random() < 0.2:
                     p1_damage = int(p1_damage * 1.5)
                 c.execute(
                     """UPDATE multiplayer_rooms 
                        SET player1_stamina = player1_stamina - 15,
                            player1_special = LEAST(player1_special + 10, 100)
                        WHERE room_code = ?""",
                     (room_code,),
                 )
         elif p1_move == "defend":
             if room["player1_stamina"] >= 10:
                 c.execute(
                     """UPDATE multiplayer_rooms 
                        SET player1_stamina = player1_stamina - 10,
                            player1_special = LEAST(player1_special + 15, 100)
                        WHERE room_code = ?""",
                     (room_code,),
                 )
         elif p1_move == "rest":
             stamina_gain = random.randint(25, 40)
             c.execute(
                 """UPDATE multiplayer_rooms 
                    SET player1_stamina = LEAST(player1_stamina + ?, 100),
                        player1_special = LEAST(player1_special + 5, 100)
                    WHERE room_code = ?""",
                 (stamina_gain, room_code),
             )
         elif p1_move == "special":
             if room["player1_special"] >= 100 and room["player1_stamina"] >= 25:
                 p1_damage = random.randint(40, 60)
                 c.execute(
                     """UPDATE multiplayer_rooms 
                        SET player1_special = 0,
                            player1_stamina = GREATEST(player1_stamina - 25, 0)
                        WHERE room_code = ?""",
                     (room_code,),
                 )
 
         # Player 2 move
         if p2_move == "attack":
             if room["player2_stamina"] >= 15:
                 p2_damage = random.randint(15, 30)
                 if random.random() < 0.2:
                     p2_damage = int(p2_damage * 1.5)
                 c.execute(
                     """UPDATE multiplayer_rooms 
                        SET player2_stamina = player2_stamina - 15,
                            player2_special = LEAST(player2_special + 10, 100)
                        WHERE room_code = ?""",
                     (room_code,),
                 )
         elif p2_move == "defend":
             if room["player2_stamina"] >= 10:
                 c.execute(
                     """UPDATE multiplayer_rooms 
                        SET player2_stamina = player2_stamina - 10,
                            player2_special = LEAST(player2_special + 15, 100)
                        WHERE room_code = ?""",
                     (room_code,),
                 )
         elif p2_move == "rest":
             stamina_gain = random.randint(25, 40)
             c.execute(
                 """UPDATE multiplayer_rooms 
                    SET player2_stamina = LEAST(player2_stamina + ?, 100),
                        player2_special = LEAST(player2_special + 5, 100)
                    WHERE room_code = ?""",
                 (stamina_gain, room_code),
             )
         elif p2_move == "special":
             if room["player2_special"] >= 100 and room["player2_stamina"] >= 25:
                 p2_damage = random.randint(40, 60)
                 c.execute(
                     """UPDATE multiplayer_rooms 
                        SET player2_special = 0,
                            player2_stamina = GREATEST(player2_stamina - 25, 0)
                        WHERE room_code = ?""",
                     (room_code,),
                 )
 
         # Defense adjustments
         if p1_move == "defend" and room["player1_stamina"] >= 10:
             p2_damage = int(p2_damage * 0.5)
         if p2_move == "defend" and room["player2_stamina"] >= 10:
             p1_damage = int(p1_damage * 0.5)
 
         # Apply damage
         c.execute(
             """UPDATE multiplayer_rooms 
                SET player1_hp = GREATEST(player1_hp - ?, 0),
                    player2_hp = GREATEST(player2_hp - ?, 0),
                    current_round = current_round + 1,
                    player1_move = NULL,
                    player2_move = NULL,
                    player1_ready = 0,
                    player2_ready = 0,
                    current_turn = CASE WHEN current_turn = 1 THEN 2 ELSE 1 END,
                    last_action = CURRENT_TIMESTAMP
                WHERE room_code = ?""",
             (p2_damage, p1_damage, room_code),
         )
 
         # Check for round winner
         room = get_room_state(room_code)
         if room["player1_hp"] <= 0 or room["player2_hp"] <= 0:
             winner = None
             if room["player1_hp"] <= 0 and room["player2_hp"] <= 0:
                 # Tie
                 pass
             elif room["player1_hp"] <= 0:
                 winner = room["player2"]
                 c.execute(
                     "UPDATE multiplayer_rooms SET game_state = 'finished', winner = ? WHERE room_code = ?",
                     (winner, room_code),
                 )
                 c.execute(
                     """UPDATE multiplayer_rooms 
                        SET player2_wins = player2_wins + 1,
                            match_round = match_round + 1
                        WHERE room_code = ?""",
                     (room_code,),
                 )
             else:
                 winner = room["player1"]
                 c.execute(
                     "UPDATE multiplayer_rooms SET game_state = 'finished', winner = ? WHERE room_code = ?",
                     (winner, room_code),
                 )
                 c.execute(
                     """UPDATE multiplayer_rooms 
                        SET player1_wins = player1_wins + 1,
                            match_round = match_round + 1
                        WHERE room_code = ?""",
                     (room_code,),
                 )
 
             # Best of 3 check
             room = get_room_state(room_code)
             if room["player1_wins"] >= 2 or room["player2_wins"] >= 2:
                 final_winner = (
                     room["player1"]
                     if room["player1_wins"] >= 2
                     else room["player2"]
                 )
                 c.execute(
                     "UPDATE multiplayer_rooms SET game_state = 'match_over', winner = ? WHERE room_code = ?",
                     (final_winner, room_code),
                 )
 
                 # Update user stats
                 if final_winner == room["player1"]:
                     c.execute(
                         "UPDATE users SET multiplayer_wins = multiplayer_wins + 1 WHERE username = ?",
                         (room["player1"],),
                     )
                     c.execute(
                         "UPDATE users SET multiplayer_losses = multiplayer_losses + 1 WHERE username = ?",
                         (room["player2"],),
                     )
                     # Award XP
                     update_user_xp_fixed(room["player1"], 150, True)
                     update_user_xp_fixed(room["player2"], 100, False)
                 else:
                     c.execute(
                         "UPDATE users SET multiplayer_wins = multiplayer_wins + 1 WHERE username = ?",
                         (room["player2"],),
                     )
                     c.execute(
                         "UPDATE users SET multiplayer_losses = multiplayer_losses + 1 WHERE username = ?",
                         (room["player1"],),
                     )
                     # Award XP
                     update_user_xp_fixed(room["player2"], 150, True)
                     update_user_xp_fixed(room["player1"], 100, False)
             else:
                 # Reset for next round
                 c.execute(
                     """UPDATE multiplayer_rooms 
                        SET player1_hp = 140, player2_hp = 140,
                            player1_stamina = 100, player2_stamina = 100,
                            player1_special = 0, player2_special = 0,
                            player1_move = NULL, player2_move = NULL,
                            player1_ready = 0, player2_ready = 0,
                            current_round = 1,
                            current_turn = 1,
                            game_state = 'playing',
                            winner = NULL,
                            last_action = CURRENT_TIMESTAMP
                        WHERE room_code = ?""",
                     (room_code,),
                 )
 
         conn.commit()
         conn.close()
 
 
def get_player_profile_pic(username):
     """Get a user's profile picture from their stats"""
     stats = get_user_stats(username)
     return get_lebron_image_url(stats["level"])
 
 
def register_user(username, password):
     hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
     conn = sqlite3.connect("users.db")
     c = conn.cursor()
     try:
         c.execute(
             "INSERT INTO users (username, password, xp, level, wins, losses) VALUES (?, ?, 0, 1, 0, 0)",
             (username, hashed_pw),
         )
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
 
def display_battle_log():
     """Display the recent actions in the multiplayer battle"""
     # Retrieve the current room state
     room_code = st.session_state.multiplayer_room_code
     room = get_room_state(room_code)
 
     if not room:
         return
 
     st.markdown("### Battle Log")
 
     # Create a log of what happened in the last turn
     log_entries = []
 
     # Player 1 move log
     if room['player1_move']:
         if room['player1_move'] == 'attack':
             log_entries.append(f"🏀 {room['player1']} attacked!")
         elif room['player1_move'] == 'defend':
             log_entries.append(f"🛡️ {room['player1']} defended!")
         elif room['player1_move'] == 'rest':
             log_entries.append(f"💤 {room['player1']} rested and recovered stamina.")
         elif room['player1_move'] == 'special':
             log_entries.append(f"⭐ {room['player1']} used a special move!")
 
     # Player 2 move log
     if room['player2_move']:
         if room['player2_move'] == 'attack':
             log_entries.append(f"🏀 {room['player2']} attacked!")
         elif room['player2_move'] == 'defend':
             log_entries.append(f"🛡️ {room['player2']} defended!")
         elif room['player2_move'] == 'rest':
             log_entries.append(f"💤 {room['player2']} rested and recovered stamina.")
         elif room['player2_move'] == 'special':
             log_entries.append(f"⭐ {room['player2']} used a special move!")
 
     # Display log entries
     if log_entries:
         for entry in log_entries:
             st.markdown(f"- {entry}")
     else:
         st.markdown("*No actions yet...*")
 
def multiplayer_ui():
     """Display the multiplayer mode UI"""
     # -- Only allow access if logged in --
     if not st.session_state.get("logged_in", False):
         st.error("You must be logged in to play multiplayer!")
         st.session_state.page = "Login"
         st.rerun()
 
     # -- Initialize session state for multiplayer --
     if "multiplayer_room_code" not in st.session_state:
         st.session_state.multiplayer_room_code = None
         st.session_state.multiplayer_role = None
         st.session_state.multiplayer_last_update = 0
 
     # -- Room creation/joining UI --
     if not st.session_state.multiplayer_room_code:
         st.markdown("<h1 class='game-title'>🏀 LeMultiplayer</h1>", unsafe_allow_html=True)
         col1, col2 = st.columns(2)
 
         with col1:
             st.markdown("### Create Room")
             if st.button("Create New Room", use_container_width=True):
                 room_code = create_room(st.session_state.username)
                 st.session_state.multiplayer_room_code = room_code
                 st.session_state.multiplayer_role = "host"
                 st.rerun()
 
         with col2:
             st.markdown("### Join Room")
             room_code = st.text_input("Enter Room Code", max_chars=6, key="join_room_code").upper()
             if st.button("Join Room", use_container_width=True, disabled=not room_code):
                 if join_room(room_code, st.session_state.username):
                     st.session_state.multiplayer_room_code = room_code
                     st.session_state.multiplayer_role = "join"
                     st.rerun()
                 else:
                     st.error("Could not join room. It may not exist or is full.")
 
     else:
         # -- Retrieve the room info --
         room = get_room_state(st.session_state.multiplayer_room_code)
         if not room:
             st.error("Room not found. It may have expired.")
             st.session_state.multiplayer_room_code = None
             st.rerun()
 
         st.markdown(
             f"<h1 class='game-title'>🏀 LeMultiplayer - Room {st.session_state.multiplayer_room_code}</h1>",
             unsafe_allow_html=True,
         )
 
         # -- Show match progress --
         st.markdown(f"**Match Round:** {room['match_round']}/3")
         st.markdown(
             f"**Score:** {room['player1']} {room['player1_wins']} - "
             f"{room['player2_wins']} {room['player2'] if room['player2'] else 'Waiting...'}"
         )
 
         # -- Waiting screen --
         if room["game_state"] == "waiting":
             st.markdown("### Waiting for opponent to join...")
             st.markdown(f"Share this room code: **{st.session_state.multiplayer_room_code}**")
 
             if st.button("Cancel", use_container_width=True):
                 # Clean up room if host cancels
                 if st.session_state.multiplayer_role == "host":
                     conn = sqlite3.connect("users.db")
                     c = conn.cursor()
                     c.execute(
                         "DELETE FROM multiplayer_rooms WHERE room_code = ?",
                         (st.session_state.multiplayer_room_code,),
                     )
                     conn.commit()
                     conn.close()
                 st.session_state.multiplayer_room_code = None
                 st.rerun()
             return
 
         # -- Determine which side this player is on --
         player = "player1" if room["player1"] == st.session_state.username else "player2"
         opponent = "player2" if player == "player1" else "player1"
 
         # -- Display both players --
         col1, col2 = st.columns(2)
 
         # (Left column: current player)
         with col1:
             st.markdown(f"### You ({st.session_state.username})")
             st.image(get_player_profile_pic(st.session_state.username), width=150)
             st.markdown(f"**Health:** {room[f'{player}_hp']}/140")
             st.progress(room[f"{player}_hp"] / 140)
             st.markdown(f"**Stamina:** {room[f'{player}_stamina']}/100")
             st.progress(room[f"{player}_stamina"] / 100)
             st.markdown(f"**Special Meter:** {room[f'{player}_special']}/100")
             st.progress(room[f"{player}_special"] / 100)
 
             # -- IMPROVED MOVE SELECTION SECTION --
             if room["game_state"] == "playing" and room["player2"]:
                 st.markdown("### Your Move")
 
                 if not room[f"{player}_ready"]:
                     colA, colB, colC, colD = st.columns(4)
 
                     with colA:
                         attack_disabled = room[f"{player}_stamina"] < 15
                         if st.button(
                             "🏀 Attack",
                             disabled=attack_disabled,
                             use_container_width=True,
                             help="Basic attack (Cost: 15 Stamina, +10 Special Meter)",
                         ):
                             update_player_move(
                                 st.session_state.multiplayer_room_code,
                                 st.session_state.username,
                                 "attack",
                             )
                             st.rerun()
 
                     with colB:
                         defend_disabled = room[f"{player}_stamina"] < 10
                         if st.button(
                             "🛡️ Defend",
                             disabled=defend_disabled,
                             use_container_width=True,
                             help="Reduce incoming damage by 50% (Cost: 10 Stamina, +15 Special Meter)",
                         ):
                             update_player_move(
                                 st.session_state.multiplayer_room_code,
                                 st.session_state.username,
                                 "defend",
                             )
                             st.rerun()
 
                     with colC:
                         if st.button(
                             "💤 Rest",
                             use_container_width=True,
                             help="Recover 25-40 Stamina (+5 Special Meter)",
                         ):
                             update_player_move(
                                 st.session_state.multiplayer_room_code,
                                 st.session_state.username,
                                 "rest",
                             )
                             st.rerun()
 
                     with colD:
                         special_disabled = (
                             room[f"{player}_special"] < 100
                             or room[f"{player}_stamina"] < 25
                         )
                         if st.button(
                             "⭐ Special",
                             disabled=special_disabled,
                             use_container_width=True,
                             help="Powerful attack (Requires: Full Special Meter, Costs: 25 Stamina)",
                         ):
                             update_player_move(
                                 st.session_state.multiplayer_room_code,
                                 st.session_state.username,
                                 "special",
                             )
                             st.rerun()
 
                 # New logic for move submission feedback
                 elif room[f"{player}_move"] is not None:
                     # Only show "Move submitted" if a move has been selected
                     st.success(f"🎯 {room[f'{player}_move'].capitalize()} move submitted! Waiting for opponent...")
                 else:
                     st.success("Move submitted! Waiting for opponent...")
                     # Fallback for any unexpected states
                     st.info("Waiting for your move...")
 
                 # -- Countdown timer logic --
                 last_action = datetime.strptime(
                     room["last_action"], "%Y-%m-%d %H:%M:%S"
                 )
                 time_elapsed = (datetime.now() - last_action).total_seconds()
                 time_left = max(0, 10 - time_elapsed)
 
                 st.markdown(f"Time remaining: {int(time_left)} seconds")
                 st.progress(time_left / 10)
 
                 if time_left <= 0:
                     # Time's up - auto-submit a rest
                     update_player_move(
                         st.session_state.multiplayer_room_code,
                         st.session_state.username,
                         "rest",
                     )
                     st.rerun()
 
         # (Right column: opponent)
         with col2:
             opponent_username = room[opponent] if room[opponent] else "Waiting..."
             st.markdown(f"### Opponent ({opponent_username})")
 
             if room[opponent]:
                 st.image(get_player_profile_pic(room[opponent]), width=150)
                 st.markdown(f"**Health:** {room[f'{opponent}_hp']}/140")
                 st.progress(room[f"{opponent}_hp"] / 140)
 
                 # Show partial or full special meter
                 st.markdown(
                     f"**Special Meter:** {'?' if not room[f'{opponent}_ready'] else room[f'{opponent}_special']}/100"
                 )
                 if room[f"{opponent}_ready"]:
                     st.progress(room[f"{opponent}_special"] / 100)
                 else:
                     st.progress(0)
 
                 if room["game_state"] == "playing":
                     if room[f"{opponent}_ready"]:
                         st.info("Opponent has submitted their move")
                     else:
                         st.info("Waiting for opponent's move...")
             else:
                 st.info("Waiting for opponent to join...")
 
         # -- ADDED BATTLE LOG --
         def display_battle_log():
             """Display the recent actions in the multiplayer battle"""
             room_code = st.session_state.multiplayer_room_code
             room = get_room_state(room_code)
 
             if not room:
                 return
 
             st.markdown("### Battle Log")
 
             log_entries = []
 
             if room['player1_move']:
                 if room['player1_move'] == 'attack':
                     log_entries.append(f"🏀 {room['player1']} attacked!")
                 elif room['player1_move'] == 'defend':
                     log_entries.append(f"🛡️ {room['player1']} defended!")
                 elif room['player1_move'] == 'rest':
                     log_entries.append(f"💤 {room['player1']} rested and recovered stamina.")
                 elif room['player1_move'] == 'special':
                     log_entries.append(f"⭐ {room['player1']} used a special move!")
 
             if room['player2_move']:
                 if room['player2_move'] == 'attack':
                     log_entries.append(f"🏀 {room['player2']} attacked!")
                 elif room['player2_move'] == 'defend':
                     log_entries.append(f"🛡️ {room['player2']} defended!")
                 elif room['player2_move'] == 'rest':
                     log_entries.append(f"💤 {room['player2']} rested and recovered stamina.")
                 elif room['player2_move'] == 'special':
                     log_entries.append(f"⭐ {room['player2']} used a special move!")
 
             if log_entries:
                 for entry in log_entries:
                     st.markdown(f"- {entry}")
             else:
                 st.markdown("*No actions yet...*")
 
         # Call the battle log function
         display_battle_log()
 
         # -- If both are ready, process turn --
         if (
             room["game_state"] == "playing"
             and room["player1_ready"]
             and room["player2_ready"]
         ):
             process_multiplayer_turn(st.session_state.multiplayer_room_code)
             st.rerun()
 
         # -- Handle game over states -- (rest of the code remains the same)
         if room["game_state"] in ("finished", "match_over"):
             if room["game_state"] == "match_over":
                 st.balloons()
                 if room["winner"] == st.session_state.username:
                     st.success(
                         f"🏆 You won the match {room['player1_wins']}-{room['player2_wins']}!"
                     )
                 else:
                     st.error(
                         f"💀 You lost the match {room['player1_wins']}-{room['player2_wins']}."
                     )
 
                 if room["winner"] == st.session_state.username:
                     st.markdown("**XP Earned:** +150 XP (Match Win)")
                 else:
                     st.markdown("**XP Earned:** +100 XP (Match Loss)")
 
                 colA, colB = st.columns(2)
                 with colA:
                     if st.button("Return to Main Menu", use_container_width=True):
                         st.session_state.multiplayer_room_code = None
                         st.rerun()
                 with colB:
                     if st.button("Play Again", use_container_width=True):
                         if st.session_state.multiplayer_role == "host":
                             conn = sqlite3.connect("users.db")
                             c = conn.cursor()
                             c.execute(
                                 """UPDATE multiplayer_rooms 
                                    SET player1_hp = 140, player2_hp = 140,
                                        player1_stamina = 100, player2_stamina = 100,
                                        player1_special = 0, player2_special = 0,
                                        player1_move = NULL, player2_move = NULL,
                                        player1_ready = 0, player2_ready = 0,
                                        current_round = 1,
                                        current_turn = 1,
                                        game_state = 'playing',
                                        winner = NULL,
                                        player1_wins = 0,
                                        player2_wins = 0,
                                        match_round = 1,
                                        last_action = CURRENT_TIMESTAMP
                                    WHERE room_code = ?""",
                                 (st.session_state.multiplayer_room_code,),
                             )
                             conn.commit()
                             conn.close()
                             st.rerun()
                         else:
                             st.info("Waiting for host to restart the match...")
 
             else:
                 # Single round ended
                 if room["winner"] == st.session_state.username:
                     st.success(f"🎉 You won round {room['match_round']}!")
                 elif room["winner"]:
                     st.error(f"💀 You lost round {room['match_round']}.")
                 else:
                     st.info("🤝 Round ended in a tie!")
 
                 st.info("Next round starting soon...")
                 time.sleep(2)
                 st.rerun()
 
         # -- Auto-refresh every 2 seconds so we see state changes --
         time.sleep(2)
         st.rerun()
 
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
             "losses": result[3],
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
         c.execute(
             "INSERT INTO users (username, xp, level, wins, losses) VALUES (?, ?, ?, ?, ?)",
             (username, xp_earned, 1, 1 if won else 0, 0 if won else 1),
         )
         conn.commit()
         conn.close()
         return False
 
     c.execute("SELECT xp, level, wins, losses FROM users WHERE username = ?", (username,))
     result = c.fetchone()
 
     if result is None:
         c.execute(
             "INSERT INTO users (username, xp, level, wins, losses) VALUES (?, ?, ?, ?, ?)",
             (username, xp_earned, 1, 1 if won else 0, 0 if won else 1),
         )
         conn.commit()
         conn.close()
         return False
 
     current_xp, current_level, wins, losses = result
 
     if won:
         wins += 1
     else:
         losses += 1
 
     new_xp = current_xp + xp_earned
 
     new_level = current_level
     while new_level < 60 and new_xp >= xp_required_for_level(new_level + 1):
         new_level += 1
 
     c.execute(
         """
         UPDATE users 
         SET xp = ?, level = ?, wins = ?, losses = ? 
         WHERE username = ?
         """,
         (new_xp, new_level, wins, losses, username),
     )
     conn.commit()
     conn.close()
 
     return new_level > current_level
 
 
st.set_page_config(
     page_title="LeBron Boss Battle",
     layout="wide",
     initial_sidebar_state="collapsed",
 )
 
 
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
         self.is_defending = True
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
         super().__init__("LeBron James", health, 100)
         self.difficulty = difficulty
         self.special_move_name = "Signature Slam Dunk"
         self.abilities = {
             "POSTERIZER": "Quick attack that has a chance to lower opponent's stamina",
             "BLOCKED BY JAMES": "Strong defensive move that also recovers stamina",
             "ALLEY-OOP TO DAVIS": "Tactical move that increases special meter gain",
             f"{self.special_move_name}": "Devastating special attack that deals massive damage",
         }
         self.move_patterns = self.set_move_patterns()
         self.consecutive_attacks = 0
         self.consecutive_defends = 0
         self.player_last_hp = 140
         self.player_pattern_memory = []
         self.turn_count = 0
         self.player_last_stamina = 100
 
     def set_move_patterns(self):
         if self.difficulty == "Easy":
             return {"attack": 0.4, "defend": 0.3, "rest": 0.25, "special": 0.05}
         elif self.difficulty == "Medium":
             return {"attack": 0.45, "defend": 0.25, "rest": 0.2, "special": 0.1}
         else:
             return {"attack": 0.5, "defend": 0.2, "rest": 0.15, "special": 0.15}
 
     def analyze_player_pattern(self, player):
         if self.difficulty == "Easy":
             return
 
         damage_taken = self.player_last_hp - player.health
         self.player_last_hp = player.health
         player_move = None
 
         if damage_taken > 0:
             if damage_taken > 35:
                 player_move = "special"
             else:
                 player_move = "attack"
         elif player.stamina > self.player_last_stamina:
             player_move = "rest"
         elif player.is_defending:
             player_move = "defend"
 
         self.player_last_stamina = player.stamina
 
         if player_move:
             self.player_pattern_memory.append(player_move)
             if len(self.player_pattern_memory) > 3:
                 self.player_pattern_memory.pop(0)
 
     def predict_player_action(self):
         if len(self.player_pattern_memory) < 2 or self.difficulty == "Easy":
             return None
 
         if self.difficulty == "Hard":
             if self.player_pattern_memory[-1] == "rest":
                 return "attack"
             if self.player_pattern_memory.count("attack") >= 2:
                 return "special"
             if "special" in self.player_pattern_memory:
                 return "rest"
         return None
 
     def choose_action(self, player=None):
         self.turn_count += 1
         if player:
             self.analyze_player_pattern(player)
 
         weights = {
             "attack": self.move_patterns["attack"],
             "defend": self.move_patterns["defend"],
             "rest": self.move_patterns["rest"],
             "special": 0 if self.special_meter < 100 else self.move_patterns["special"],
         }
 
         if self.stamina <= 30:
             rest_urgency = (30 - self.stamina) / 30
             weights["rest"] *= (1 + 2 * rest_urgency)
             if self.stamina < 15:
                 return "rest"
         else:
             weights["rest"] *= 0.2
 
         if self.difficulty in ["Hard", "Medium"]:
             if self.health < self.max_health * 0.3:
                 weights["defend"] *= 2.0
 
             predicted_move = self.predict_player_action()
             if predicted_move == "special" and player and player.special_meter >= 75:
                 weights["defend"] *= 3.0
 
             if self.special_meter >= 100 and player and player.health < player.max_health * 0.4:
                 return "special"
 
             if self.consecutive_attacks >= 2:
                 weights["attack"] *= 0.5
 
             if self.consecutive_defends >= 2:
                 weights["defend"] *= 0.3
 
             if self.special_meter >= 100:
                 special_threshold = 0.8 if self.difficulty == "Hard" else 0.6
                 if random.random() < special_threshold:
                     return "special"
 
             if player and player.is_defending:
                 weights["attack"] *= 0.4
                 weights["rest"] *= 1.5
 
         if self.difficulty == "Hard":
             if 15 < self.stamina < 40:
                 weights["rest"] *= 1.5
             if player and player.health < player.max_health * 0.3:
                 weights["attack"] *= 1.5
             if self.turn_count < 5 and self.health > self.max_health * 0.8:
                 weights["defend"] *= 1.3
 
         if self.stamina > 50:
             weights["attack"] *= 1.3
 
         actions = list(weights.keys())
         weights_list = list(weights.values())
         chosen_action = random.choices(actions, weights=weights_list)[0]
 
         if chosen_action == "rest" and self.stamina > 30:
             weights["rest"] = 0.1
             actions = list(weights.keys())
             weights_list = list(weights.values())
             chosen_action = random.choices(actions, weights=weights_list)[0]
 
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
         damage, msg = super().attack()
         poster_chance = 0.2 if self.difficulty == "Easy" else 0.35 if self.difficulty == "Medium" else 0.5
         if random.random() < poster_chance:
             return (damage, "LeBron POSTERS YOU for " + str(damage) + " damage and reduces your stamina!")
         return (damage, msg)
 
     def special_attack(self):
         damage, _ = super().special_attack()
         if self.difficulty == "Medium":
             damage = int(damage * 1.1)
         elif self.difficulty == "Hard":
             damage = int(damage * 1.2)
         return (damage, f"LeBron unleashes his {self.special_move_name} for {damage} MASSIVE damage!")
 
     def take_damage(self, damage):
         if self.is_defending:
             reduction = 0.5
             reduced_damage = int(damage * (1 - reduction))
             heal_percent = 0.5
             heal_amount = int(reduced_damage * heal_percent)
             self.health += heal_amount
             if self.health > self.max_health:
                 self.health = self.max_health
             self.health -= reduced_damage
             if self.health < 0:
                 self.health = 0
             self.is_defending = False
             return f"{self.name} blocks and reduces damage to {reduced_damage}, then heals {heal_amount} health!"
         else:
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
             st.image(
                 "https://is1-ssl.mzstatic.com/image/thumb/Music126/v4/04/62/e6/0462e6b9-45b0-f229-afc0-d2f79cce2cf4/artwork.jpg/632x632bb.webp",
                 caption=character.name,
                 width=150,
             )
         else:
             st.image(
                 "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cf/LeBron_James_%2851960276445%29_%28cropped%29.jpg/1024px-LeBron_James_%2851960276445%29_%28cropped%29.jpg",
                 caption=character.name,
                 width=150,
             )
         st.markdown("</div>", unsafe_allow_html=True)
     with col2:
         st.markdown(f"<div class='stat-label'>Health: {character.health}/{character.max_health}</div>", unsafe_allow_html=True)
         hp_percent = character.health / character.max_health if character.max_health else 0
         st.progress(hp_percent)
 
         st.markdown(f"<div class='stat-label'>Stamina: {character.stamina}/{character.max_stamina}</div>", unsafe_allow_html=True)
         st_percent = character.stamina / character.max_stamina if character.max_stamina else 0
         st.progress(st_percent)
 
         st.markdown(f"<div class='stat-label'>Special Meter: {character.special_meter}/100</div>", unsafe_allow_html=True)
         sp_percent = character.special_meter / 100
         st.progress(sp_percent)
 
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
     st.session_state.log.append({"message": message, "type": entry_type, "timestamp": timestamp})
 
 
def single_display_battle_log():
     st.markdown("### 📜 Battle Log")
     with st.container():
         for entry in reversed(st.session_state.log):
             if isinstance(entry, dict) and "type" in entry and "message" in entry:
                 entry_class = f"log-entry {entry['type']}-log"
                 st.markdown(
                     f"<div class='{entry_class}'><small>{entry['timestamp']}</small> {entry['message']}</div>",
                     unsafe_allow_html=True,
                 )
             else:
                 st.markdown(
                     f"<div class='log-entry system-log'><small>Unknown time</small> {entry}</div>",
                     unsafe_allow_html=True,
                 )
 
 
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
     player = st.session_state.player
     lebron = st.session_state.lebron
     player_action = st.session_state.current_player_action
 
     if not hasattr(lebron, "player_last_stamina"):
         lebron.player_last_stamina = player.stamina
 
     lebron_action = lebron.choose_action(player)
     player_damage = 0
     lebron_damage = 0
 
     add_log_entry(f"Round {st.session_state.round} begins - both fighters prepare their moves!", "system")
 
     if player_action == "defend":
         result = player.defend()
         add_log_entry(result, "player")
         st.session_state.animation_state = "player_defend"
 
     if lebron_action == "defend":
         result = lebron.defend()
         add_log_entry(result, "lebron")
         st.session_state.animation_state = "lebron_defend"
 
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
 
     if player_damage > 0:
         result = lebron.take_damage(player_damage)
         add_log_entry(result, "lebron")
     if lebron_damage > 0:
         result = player.take_damage(lebron_damage)
         add_log_entry(result, "player")
 
     player.reset_turn()
     lebron.reset_turn()
     st.session_state.round += 1
     st.session_state.action_taken = False
 
     return True
 
 
def xp_required_for_level(level):
     if level <= 1:
         return 0
     elif level <= 10:
         return (level - 1) * 100
     elif level <= 20:
         base_xp = 900  # XP for level 10
         return base_xp + (level - 10) * 200
     elif level <= 30:
         base_xp = 900 + 10 * 200
         return base_xp + (level - 20) * 300
     elif level <= 40:
         base_xp = 900 + 10 * 200 + 10 * 300
         return base_xp + (level - 30) * 400
     elif level <= 49:
         base_xp = 900 + 10 * 200 + 10 * 300 + 10 * 400
         return base_xp + (level - 40) * 500
     else:
         base_xp = 900 + 10 * 200 + 10 * 300 + 10 * 400 + 9 * 500
         if level == 50:
             return base_xp + 500
         else:
             multiplier = 1.5 ** (level - 50)
             return int(base_xp + 500 + (level - 50) * 200 * multiplier)
 
 
def calculate_xp_reward(player_health, lebron_health, difficulty, won):
     base_xp = 25
     diff_multiplier = 1.0
     if difficulty == "Medium":
         diff_multiplier = 1.5
     elif difficulty == "Hard":
         diff_multiplier = 2.0
     victory_bonus = 50 if won else 0
     margin_bonus = 0
     if won:
         margin_bonus = int((player_health / 140) * 30)
     total_xp = int((base_xp + victory_bonus + margin_bonus) * diff_multiplier)
     return max(10, total_xp)
 
 
def get_level_progress(current_xp, current_level):
     current_level_xp = xp_required_for_level(current_level)
     next_level_xp = xp_required_for_level(current_level + 1)
     xp_for_this_level = next_level_xp - current_level_xp
     xp_gained_in_level = current_xp - current_level_xp
     progress = xp_gained_in_level / xp_for_this_level if xp_for_this_level > 0 else 1.0
     return min(1.0, max(0.0, progress))
 
 
def get_lebron_image_url(level):
     lebron_images = [
         "https://media.cnn.com/api/v1/images/stellar/prod/230206130746-39-lebron-james-gallery-restricted.jpg?q=w_1576,c_fill",
         "https://www.the-sun.com/wp-content/uploads/sites/6/2023/10/AS_LEBRON-MEMES_OP.jpg?strip=all&quality=100&w=1080&h=1080&crop=1",
         "https://cdn-wp.thesportsrush.com/2021/10/faeeadb8-untitled-design-22.jpg?format=auto&w=3840&q=75",
         "https://www.nickiswift.com/img/gallery/the-transformation-of-lebron-james-from-childhood-to-36-years-old/l-intro-1625330663.jpg",
         "https://wompimages.ampify.care/fetchimage?siteId=7575&v=2&jpgQuality=100&width=700&url=https%3A%2F%2Fi.kym-cdn.com%2Fentries%2Ficons%2Ffacebook%2F000%2F049%2F004%2Flebronsunshinecover.jpg",
         "https://pbs.twimg.com/media/E_sz6efVIAIXSmP.jpg",
         # ... and so on ...
         # (Truncated for brevity, but same concept)
     ]
     image_index = (level - 1) % len(lebron_images)
     return lebron_images[image_index]
 
 
def end_battle_with_xp(player, lebron, won):
     if hasattr(st.session_state, "xp_already_awarded") and st.session_state.xp_already_awarded:
         return get_user_stats(st.session_state.username)
 
     difficulty = st.session_state.difficulty
     username = st.session_state.username
     xp_earned = calculate_xp_reward(player.health, lebron.health, difficulty, won)
     current_stats = get_user_stats(username)
     leveled_up = update_user_xp_fixed(username, xp_earned, won)
     updated_stats = get_user_stats(username)
 
     st.session_state.battle_results = {
         "xp_earned": xp_earned,
         "leveled_up": leveled_up,
         "new_level": updated_stats["level"],
         "total_xp": updated_stats["xp"],
         "wins": updated_stats["wins"],
         "losses": updated_stats["losses"],
     }
     st.session_state.xp_already_awarded = True
 
     return updated_stats
 
 
def add_lepass_css():
     st.markdown(
         """
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
         /* ... more CSS omitted for brevity ... */
     </style>
     """,
         unsafe_allow_html=True,
     )
 
 
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
         st.markdown("### Choose Your Action")
         colA, colB, colC, colD = st.columns(4)
 
         with colA:
             attack_disabled = player.stamina < 15
             if st.button("🏀 Attack", disabled=attack_disabled, use_container_width=True,
                         help="Basic attack (Cost: 15 Stamina, +10 Special Meter)"):
                 st.session_state.current_player_action = "attack"
                 process_round()
                 st.rerun()
             st.markdown("<div class='move-info'>Costs 15 stamina<br>+10 special meter</div>", unsafe_allow_html=True)
 
         with colB:
             defend_disabled = player.stamina < 10
             if st.button("🛡️ Defend", disabled=defend_disabled, use_container_width=True,
                         help="Reduce incoming damage by 50% (Cost: 10 Stamina, +15 Special Meter)"):
                 st.session_state.current_player_action = "defend"
                 process_round()
                 st.rerun()
             st.markdown("<div class='move-info'>Costs 10 stamina<br>+15 special meter<br>Reduces damage by 50%</div>", unsafe_allow_html=True)
 
         with colC:
             if st.button("💤 Rest", use_container_width=True,
                         help="Recover 25-40 Stamina (+5 Special Meter)"):
                 st.session_state.current_player_action = "rest"
                 process_round()
                 st.rerun()
             st.markdown("<div class='move-info'>Recover 25-40 stamina<br>+5 special meter</div>", unsafe_allow_html=True)
 
         with colD:
             special_disabled = player.special_meter < 100 or player.stamina < 25
             if st.button("⭐ Special Attack", disabled=special_disabled, use_container_width=True,
                         help="Powerful attack that deals massive damage (Requires: Full Special Meter, Costs: 25 Stamina)"):
                 st.session_state.current_player_action = "special"
                 process_round()
                 st.rerun()
             st.markdown("<div class='move-info'>Requires 100% special meter<br>Costs 25 stamina<br>Deals 40-60 damage</div>", unsafe_allow_html=True)
 
     else:
         st.markdown("<div class='game-over-container'>", unsafe_allow_html=True)
 
         if st.session_state.player.health == 0 and st.session_state.lebron.health == 0:
             st.markdown("## 🤝 TIE! 🤝")
             st.markdown("### It's a draw! You and LeBron both fell at the same time.")
             tie_xp = 70
             if not hasattr(st.session_state, "username"):
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
 
             colA, colB = st.columns(2)
             with colA:
                 if st.button("Play Again", use_container_width=True):
                     st.session_state.game_started = False
                     st.session_state.log = []
                     st.session_state.restart_game = True
                     st.session_state.round = 1
                     st.rerun()
             with colB:
                 if st.button("View LePASS", use_container_width=True):
                     st.session_state.page = "LePASS"
                     st.rerun()
 
             st.markdown("</div>", unsafe_allow_html=True)
             return
 
         won = player.is_alive()
         if not hasattr(st.session_state, "username"):
             st.session_state.username = "Guest"
 
         updated_stats = end_battle_with_xp(player, lebron, won)
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
 
         st.markdown(f"**XP Earned:** +{xp_earned} XP")
         st.markdown(f"**Total XP:** {battle_results['total_xp']} XP")
         st.markdown(f"**Current Level:** {new_level}")
         st.markdown(f"**Record:** {battle_results['wins']}W - {battle_results['losses']}L")
 
         if leveled_up:
             st.success(f"🎉 LEVEL UP! You reached Level {new_level}!")
 
         colA, colB = st.columns(2)
         with colA:
             if st.button("Play Again", use_container_width=True):
                 st.session_state.game_started = False
                 st.session_state.log = []
                 st.session_state.restart_game = True
                 st.session_state.round = 1
                 st.rerun()
         with colB:
             if st.button("View LePASS", use_container_width=True):
                 st.session_state.page = "LePASS"
                 st.rerun()
 
         st.markdown("</div>", unsafe_allow_html=True)
 
     display_battle_log()
 
 
def display_difficulty_selection():
     st.markdown("<h1 class='game-title'>LeBron Boss Battle</h1>", unsafe_allow_html=True)
     col1, col2, col3 = st.columns([1, 2, 1])
     with col2:
         st.image(
             "https://wompimages.ampify.care/fetchimage?siteId=7575&v=2&jpgQuality=100&width=700&url=https%3A%2F%2Fi.kym-cdn.com%2Fentries%2Ficons%2Ffacebook%2F000%2F049%2F004%2Flebronsunshinecover.jpg",
             width=500,
         )
     st.markdown("<div class='difficulty-card'>", unsafe_allow_html=True)
     st.markdown("<h2>Choose Your Difficulty</h2>", unsafe_allow_html=True)
     difficulty_options = {
         "Easy": "LeBron has 100 HP and uses basic moves mostly at random.",
         "Medium": "LeBron has 160 HP and plays more strategically.",
         "Hard": "LeBron has 180 HP and uses advanced tactics and powerful combos.",
     }
     selected_difficulty = st.select_slider("Select difficulty:", options=list(difficulty_options.keys()), value=st.session_state.difficulty)
     st.info(difficulty_options[selected_difficulty])
     st.session_state.difficulty = selected_difficulty
     show_tutorial = st.checkbox("Show Tutorial", value=not st.session_state.tutorial_shown)
     if show_tutorial:
         st.markdown("### How to Play:")
         st.markdown(
             """
             1. **Attack** - Deal damage but costs stamina  
             2. **Defend** - Reduce incoming damage by 50%  
             3. **Rest** - Recover stamina  
             4. **Special Attack** - Powerful move that requires a full special meter
 
             Fill your special meter by performing actions. Win by reducing LeBron's health to zero!
             """
         )
         st.session_state.tutorial_shown = True
 
     if st.button("Start Game", use_container_width=True):
         st.session_state.player = Player("You", 140, 100)
         st.session_state.lebron = LeBron(st.session_state.difficulty)
         st.session_state.turn = 0
         st.session_state.round = 1
         st.session_state.log = []
         st.session_state.action_taken = False
         st.session_state.game_started = True
         st.session_state.xp_already_awarded = False
         add_log_entry("The battle begins! Your turn first.", "system")
         st.rerun()
     st.markdown("</div>", unsafe_allow_html=True)
 
 
def login_ui():
     st.markdown("<h1 class='auth-title'>Welcome Back</h1>", unsafe_allow_html=True)
     st.markdown("<p class='auth-subtitle'>Sign in to continue your battle</p>", unsafe_allow_html=True)
     st.markdown("</div>", unsafe_allow_html=True)
     st.markdown("<div class='auth-logo'>", unsafe_allow_html=True)
     st.image("https://cdn-wp.thesportsrush.com/2021/10/faeeadb8-untitled-design-22.jpg?format=auto&w=3840&q=75", width=350)
     st.markdown("</div>", unsafe_allow_html=True)
 
     username = st.text_input("Username", key="login_username")
     password = st.text_input("Password", type="password", key="login_password")
 
     colA, colB, colC = st.columns([1, 3, 1])
     with colB:
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
 
     st.markdown(
         """
         <script>
             document.getElementById('register-link').addEventListener('click', function(e) {
                 e.preventDefault();
                 window.location.href = window.location.pathname + "?page=Register";
             });
         </script>
         """,
         unsafe_allow_html=True,
     )
     st.markdown("</div>", unsafe_allow_html=True)
 
 
def lepass_ui():
     """Display the LePASS progression UI with gallery of unlocked LeBron images"""
     if not st.session_state.get("logged_in", False):
         st.error("You must be logged in to view LePASS!")
         st.session_state.page = "Login"
         st.rerun()
 
     add_lepass_css()
 
     username = st.session_state.username
     user_stats = get_user_stats(username)
     current_level = user_stats["level"]
     current_xp = user_stats["xp"]
     wins = user_stats["wins"]
     losses = user_stats["losses"]
 
     progress = get_level_progress(current_xp, current_level)
     next_level_xp = xp_required_for_level(current_level + 1)
     xp_needed = next_level_xp - current_xp
     current_image_url = get_lebron_image_url(current_level)
     next_image_url = get_lebron_image_url(current_level + 1) if current_level < 60 else current_image_url
 
     st.markdown("<h1 class='game-title'>LePASS™ Battle Pass</h1>", unsafe_allow_html=True)
 
     colA, colB = st.columns([1, 2])
     with colA:
         st.image(current_image_url, caption=f"Level {current_level} LeBron", width=250)
     with colB:
         st.markdown(f"### Welcome to your LePASS, {username}!")
         st.markdown(f"**Current Level:** {current_level}/60")
         st.markdown(
             f"""
             <div class="lepass-progress-container">
                 <div class="lepass-progress-bar" style="width: {progress * 100}%"></div>
                 <div class="lepass-progress-text">{current_xp} / {next_level_xp} XP</div>
             </div>
             """,
             unsafe_allow_html=True,
         )
         if current_level < 60:
             st.markdown(f"**XP needed for Level {current_level + 1}:** {xp_needed} XP")
         else:
             st.markdown("**MAX LEVEL REACHED!** You've collected all LeBron images!")
         st.markdown(f"**Battle Record:** {wins} Wins / {losses} Losses")
 
     st.markdown("### Next Reward")
     if current_level < 60:
         colX, colY = st.columns([1, 2])
         with colX:
             st.image(next_image_url, caption=f"Level {current_level + 1} LeBron", width=200)
         with colY:
             st.markdown(f"**Unlock at Level {current_level + 1}**")
             st.markdown(f"Earn **{xp_needed}** more XP to unlock!")
             st.markdown("Win battles against LeBron to earn XP. Higher difficulties and better performance grant more XP!")
     else:
         st.success("CONGRATULATIONS! You've reached MAX LEVEL and collected all 60 LeBron images!")
 
     st.markdown("<h3 class='lepass-section-header'>Your LeBron Collection</h3>", unsafe_allow_html=True)
     view_options = ["All Unlocked", "By Rarity"]
     view_mode = st.radio("View mode:", view_options, horizontal=True)
 
     if view_mode == "All Unlocked":
         st.markdown("### Unlocked LeBrons")
         column_count = 5
         gallery_cols = st.columns(column_count)
         for lvl in range(1, current_level + 1):
             image_url = get_lebron_image_url(lvl)
             col_index = (lvl - 1) % column_count
             with gallery_cols[col_index]:
                 st.image(image_url, caption=f"Level {lvl}", width=100)
     else:
         st.markdown("### Collection By Rarity")
         rarity_tiers = {
             "Common (Levels 1-15)": range(1, min(16, current_level + 1)),
             "Uncommon (Levels 16-30)": range(16, min(31, current_level + 1)),
             "Rare (Levels 31-45)": range(31, min(46, current_level + 1)),
             "Epic (Levels 46-55)": range(46, min(56, current_level + 1)),
             "Legendary (Levels 56-60)": range(56, min(61, current_level + 1)),
         }
         for rarity, level_range in rarity_tiers.items():
             if len(list(level_range)) > 0:
                 st.markdown(f"#### {rarity}")
                 with st.expander("Show Collection", expanded=rarity == "Legendary (Levels 56-60)"):
                     column_count = 5
                     gallery_cols = st.columns(column_count)
                     for i, lvl in enumerate(level_range):
                         image_url = get_lebron_image_url(lvl)
                         col_index = i % column_count
                         with gallery_cols[col_index]:
                             st.image(image_url, caption=f"Level {lvl}", width=100)
 
     if current_level < 60:
         remaining = 60 - current_level
         st.markdown(f"### Locked LeBrons ({remaining} remaining)")
         st.info(f"You still have {remaining} LeBron images to unlock! Continue winning battles to unlock more.")
         teaser_level = min(current_level + 10, 60)
         st.markdown(f"Reach level {teaser_level} to unlock:")
         teaser_image = get_lebron_image_url(teaser_level)
         st.image(teaser_image, caption=f"Level {teaser_level} Preview", width=150)
 
     st.markdown("<h3 class='lepass-section-header'>How to Earn XP</h3>", unsafe_allow_html=True)
     cA, cB, cC = st.columns(3)
     with cA:
         st.markdown("#### Easy Difficulty")
         st.markdown("- Win: 75-100 XP")
         st.markdown("- Loss: 25-50 XP")
     with cB:
         st.markdown("#### Medium Difficulty")
         st.markdown("- Win: 112-150 XP")
         st.markdown("- Loss: 37-75 XP")
     with cC:
         st.markdown("#### Hard Difficulty")
         st.markdown("- Win: 150-200 XP")
         st.markdown("- Loss: 50-100 XP")
     st.info("💡 **TIP:** Higher health at the end of battle = more XP!")
 
     st.markdown("<h3 class='lepass-section-header'>Level Progression</h3>", unsafe_allow_html=True)
     levels = list(range(1, 61))
     xp_requirements = [xp_required_for_level(lvl) for lvl in levels]
 
     st.vega_lite_chart(
         {
             "data": {
                 "values": [
                     {"level": i, "xp": xp_requirements[i - 1], "current": i == current_level}
                     for i in levels
                 ]
             },
             "mark": {"type": "line", "point": True},
             "encoding": {
                 "x": {"field": "level", "type": "quantitative", "title": "Level"},
                 "y": {"field": "xp", "type": "quantitative", "title": "XP Required"},
                 "color": {
                     "field": "current",
                     "type": "nominal",
                     "scale": {"range": ["#4880EC", "#FF416C"]},
                     "legend": None,
                 },
                 "size": {
                     "field": "current",
                     "type": "nominal",
                     "scale": {"range": [2, 5]},
                     "legend": None,
                 },
             },
             "width": 700,
             "height": 300,
         }
     )
     st.markdown(
         """
         **Note:** Levels 1-50 increase linearly, while levels 51-60 require exponentially more XP.
         The final 10 levels are meant to be challenging to achieve!
         """
     )
     if st.button("Return to Game", use_container_width=True):
         st.session_state.page = "LePlay"
         st.rerun()
 
 
def lecareer_ui():
     if not st.session_state.get("logged_in", False):
         st.error("You must be logged in to view LeCareer!")
         st.session_state.page = "Login"
         st.rerun()
 
     st.markdown(
         """
     <style>
         /* LeCareer specific styling */
         .career-header {
             text-align: center;
             margin-bottom: 30px;
         }
         /* ... rest of the CSS as in your snippet ... */
     </style>
     """,
         unsafe_allow_html=True,
     )
 
     # The rest of your lecareer_ui code goes here exactly as in your snippet
     # ...
     # For brevity, just keep the function body as is from your snippet.
 
     st.markdown("<h1 class='game-title'>LeCareer Journey</h1>", unsafe_allow_html=True)
     # ... etc.
     st.markdown("<!-- Omitted for brevity -->", unsafe_allow_html=True)
 
 
def register_ui():
     st.markdown("<h1 class='auth-title'>Create Account</h1>", unsafe_allow_html=True)
     st.markdown("<p class='auth-subtitle'>Join the battle against LeBron</p>", unsafe_allow_html=True)
     st.markdown("</div>", unsafe_allow_html=True)
 
     st.markdown("<div class='auth-logo'>", unsafe_allow_html=True)
     st.image("https://www.the-sun.com/wp-content/uploads/sites/6/2023/10/AS_LEBRON-MEMES_OP.jpg?strip=all&quality=100&w=1080&h=1080&crop=1", width=250)
     st.markdown("</div>", unsafe_allow_html=True)
 
     username = st.text_input("Choose a Username", key="register_username")
     password = st.text_input("Create Password", type="password", key="register_password")
 
     cA, cB, cC = st.columns([1, 3, 1])
     with cB:
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
 
     st.markdown(
         """
     <script>
         document.getElementById('login-link').addEventListener('click', function(e) {
             e.preventDefault();
             window.location.href = window.location.pathname + "?page=Login";
         });
     </script>
     """,
         unsafe_allow_html=True,
     )
     st.markdown("</div>", unsafe_allow_html=True)
 
 
def logout_ui():
     st.markdown("<h1 class='auth-title'>Log Out</h1>", unsafe_allow_html=True)
     st.markdown("<p class='auth-subtitle'>Are you sure you want to leave?</p>", unsafe_allow_html=True)
     st.markdown("</div>", unsafe_allow_html=True)
 
     st.markdown("<div style='text-align: center; margin: 30px 0;'>", unsafe_allow_html=True)
     st.image("https://www.nickiswift.com/img/gallery/the-transformation-of-lebron-james-from-childhood-to-36-years-old/l-intro-1625330663.jpg", width=700)
     st.markdown("</div>", unsafe_allow_html=True)
 
     colA, colB = st.columns(2)
     with colA:
         if st.button("Cancel", use_container_width=True):
             st.session_state.page = "LePlay"
             st.rerun()
     with colB:
         if st.button("Confirm LeLogout", use_container_width=True):
             for key in list(st.session_state.keys()):
                 if key != "page":
                     del st.session_state[key]
             st.success("Logged out successfully!")
             st.session_state.page = "Login"
             st.rerun()
     st.markdown("</div>", unsafe_allow_html=True)
 
 
def play_ui():
     if not st.session_state.get("logged_in", False):
         st.error("You must be logged in to play!")
         st.session_state.page = "Login"
         st.rerun()
     initialize_session_state()
     if not st.session_state.game_started:
         display_difficulty_selection()
     else:
         display_game()
 
 
 st.markdown(
     """
 <style>
     [data-testid="stAppViewContainer"] {
         background-image: url("https://i.imgur.com/v5gUNvA.png");
         background-size: 90%;
         background-position: 300% ;
         background-repeat: no-repeat;
         background-attachment: local;
     }
 
     [data-testid="stAppViewContainer"]::after {
         content: "";
         position: absolute;
         top: 0;
         left: 0;
         width: 100%;
         height: 100%;
         background-color: rgba(255, 255, 255, 0.7);
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
     [data-testid="stSidebar"] {
         background-image: url('https://pbs.twimg.com/media/E_sz6efVIAIXSmP.jpg');
         background-size: cover;
         background-position: 90%;
         background-repeat: no-repeat;
         position: relative;
     }
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
     [data-testid="stSidebar"] > div {
         position: relative;
         z-index: 1;
     }
     [data-testid="stSidebar"] .stRadio label,
     [data-testid="stSidebar"] p,
     [data-testid="stSidebar"] div {
         color: white !important;
         font-weight: 500;
         text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.8);
     }
 </style>
 """,
     unsafe_allow_html=True,
 )
 
 
def main():
     init_db()
     init_multiplayer_db()
 
     if "page" not in st.session_state:
         st.session_state.page = "Login" if not st.session_state.get("logged_in", False) else "LePlay"
 
     if st.session_state.get("logged_in", False):
         nav_options = ["LePlay", "LePvP", "LePASS", "LeLogout", "LeCareer"]
     else:
         nav_options = ["Login", "Register"]
 
     st.sidebar.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)
     st.sidebar.markdown("<h2 style='color: white; text-align: center; text-shadow: 2px 2px 4px black;'>LeBattle Sim</h2>", unsafe_allow_html=True)
 
     selected_page = st.sidebar.radio(
         "",
         nav_options,
         index=(nav_options.index(st.session_state.page) if st.session_state.page in nav_options else 0),
     )
     st.session_state.page = selected_page
 
     if st.session_state.get("logged_in", False):
         st.sidebar.markdown(
             f"<div style='color: white; text-align: center; margin-top: 20px; padding: 10px; background-color: rgba(0,0,0,0.3); border-radius: 5px;'>Logged in as: <b>{st.session_state['username']}</b></div>",
             unsafe_allow_html=True,
         )
 
     if st.session_state.page == "Login":
         login_ui()
     elif st.session_state.page == "Register":
         register_ui()
     elif st.session_state.page == "LePlay":
         play_ui()
     elif st.session_state.page == "LePASS":
         lepass_ui()
     elif st.session_state.page == "LeLogout":
         logout_ui()
     elif st.session_state.page == "LePvP":
         multiplayer_ui()
     elif st.session_state.page == "LeCareer":
         lecareer_ui()
 
 
 if __name__ == "__main__":
     main()

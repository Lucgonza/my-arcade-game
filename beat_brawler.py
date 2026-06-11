import pygame
import numpy as np
import sys

# ── Constants ──────────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 800, 420
FPS           = 60
FLOOR_Y       = 360          # y-coordinate of the floor

BPM            = 100
BEAT_DUR       = 60.0 / BPM        # 0.6 s  per quarter note
SUBDIV_DUR     = BEAT_DUR / 2      # 0.3 s  per eighth note (subdivision tick)
BEAT_BUFFER    = 0.20              # accept kick within 200 ms of any subdivision

PLAYER_SPEED      = 120   # px / s  (auto-walk, world units)
# Spawn offset target: just past screen edge (~430 px from player screen centre)
# Right enemy screen speed = ENEMY_R_SPEED + PLAYER_SPEED  → world spawn offset = (R+P)*lead*T
# Left  enemy screen speed = ENEMY_L_SPEED - PLAYER_SPEED  → world spawn offset = (L-P)*lead*T
LEAD_BEATS        = 4                  # same for both sides
ENEMY_R_SPEED     = 60    # px / s    (120+60)*4*0.6 = 432 px → screen_x ≈ 832  ✓
ENEMY_L_SPEED     = 300   # px / s    (300-120)*4*0.6 = 432 px → screen_x ≈ -32 ✓
# Low runner: short and fast — must be jumped over
LOW_R_SPEED       = 160   # px / s   closing (120+160)=280 → spawns 672 px right
LOW_L_SPEED       = 400   # px / s   closing (400-120)=280 → spawns 672 px left
LOW_W, LOW_H      = 34, 24
GRAVITY           = 1800  # px / s²  — snappy, not floaty
JUMP_VEL          = -400  # px / s   apex = 400²/(2·1800) ≈ 44 px > LOW_H=24 ✓, airtime ≈ 0.44 s

PLAYER_W, PLAYER_H = 28, 50
ENEMY_W,  ENEMY_H  = 28, 50
KICK_REACH  = 40             # px from player centre to kick box edge (visual AND logic)
HIT_RANGE   = KICK_REACH + ENEMY_W // 2  # enemy centre must be within this

PLAYER_START_X   = 160       # world x at t=0
PLAYER_SCREEN_X  = WIDTH // 2  # player fixed at horizontal centre

PLAYER_MAX_HP = 4

# Colours
BLACK  = (10,  10,  22)
WHITE  = (235, 235, 235)
CYAN   = (0,   210, 220)
RED    = (220,  45,  45)
ORANGE = (220, 130,  30)
GREEN  = ( 55, 200,  75)
YELLOW = (255, 220,   0)
GRAY   = ( 75,  75,  95)
PURPLE = (150,  55, 200)
DKGRAY = ( 30,  30,  45)

# ── Level generation ───────────────────────────────────────────────────────────
import random

def generate_level(num_enemies=14, start_subdiv=12, min_gap=3, max_gap=9):
    """
    Arrivals in subdivision units (1 subdiv = 1 eighth note).
    Even subdivisions = quarter-note beat, odd = off-beat eighth note.
    Each entry: (subdiv, side, kind)  kind = "kick" | "low"
    """
    enemies  = []
    subdiv   = start_subdiv   # start_subdiv=12 → beat 6
    for _ in range(num_enemies):
        side = random.choice(["left", "right"])
        kind = "low" if random.random() < 0.25 else "kick"   # ~1 in 4 is a low runner
        enemies.append((subdiv, side, kind))
        subdiv += random.randint(min_gap, max_gap)
    return enemies

LEVEL_SPIKE_BEATS = set()   # disabled for now

# ── Audio helpers ──────────────────────────────────────────────────────────────
SAMPLE_RATE = 44100

def _make_wave(freq, duration, volume, wave_fn):
    n = int(duration * SAMPLE_RATE)
    t = np.linspace(0, duration, n, endpoint=False)
    raw = wave_fn(freq, t)
    fade = np.linspace(1.0, 0.0, n) ** 0.4
    data = (raw * fade * volume * 32767).astype(np.int16)
    return np.ascontiguousarray(np.column_stack([data, data]))

def _sine(f, t): return np.sin(2 * np.pi * f * t)
def _square(f, t): return np.sign(np.sin(2 * np.pi * f * t))

def init_sounds():
    pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=2, buffer=512)
    return {
        "tick":       pygame.sndarray.make_sound(_make_wave(220,  0.07, 0.12, _sine)),
        "beat":       pygame.sndarray.make_sound(_make_wave(440,  0.10, 0.22, _sine)),
        "kick_l":     pygame.sndarray.make_sound(_make_wave(130,  0.08, 0.12, _square)),  # deep thud
        "kick_r":     pygame.sndarray.make_sound(_make_wave(520,  0.06, 0.10, _sine)),    # sharp snap
        "enemy_die":  pygame.sndarray.make_sound(_make_wave(660,  0.18, 0.45, _square)), # punchy hit
        "damage":     pygame.sndarray.make_sound(_make_wave(110,  0.22, 0.38, _square)),
        "spike_dodge":pygame.sndarray.make_sound(_make_wave(550,  0.10, 0.20, _sine)),   # light ding
        "low_dodge":  pygame.sndarray.make_sound(_make_wave(750,  0.12, 0.28, _sine)),   # rising zip for low runner
    }

# ── Music loop ─────────────────────────────────────────────────────────────────
# Original chiptune melody in arcade kung-fu style (A minor pentatonic).
# 4 bars of 4/4 at BPM — loops seamlessly. Notes in eighth-note grid.

NOTE = {  # frequencies (Hz)
    "A3": 220.00, "C4": 261.63, "D4": 293.66, "E4": 329.63, "G4": 392.00,
    "A4": 440.00, "C5": 523.25, "D5": 587.33, "E5": 659.26, "G5": 783.99,
    "A2": 110.00, "E3": 164.81, "G3": 196.00, "D3": 146.83,
    "R":  0.0,    # rest
}

# Melody: 4 bars × 8 eighth notes = 32 slots (square lead)
MELODY = [
    "A4","R", "C5","A4", "E5","R", "D5","C5",
    "A4","R", "C5","D5", "E5","D5", "C5","A4",
    "G4","R", "A4","C5", "D5","R", "C5","A4",
    "E4","G4", "A4","R", "A4","R", "R", "R",
]
# Bass: one note per quarter note = 16 slots (low square)
BASS = [
    "A2","A2","E3","E3",
    "A2","A2","G3","G3",
    "D3","D3","E3","E3",
    "A2","E3","A2","A2",
]

def _tone(freq, dur, vol, wave_fn, sustain=0.85):
    """Note with quick attack and release inside its slot."""
    n = int(dur * SAMPLE_RATE)
    if freq <= 0:
        return np.zeros(n)
    t   = np.linspace(0, dur, n, endpoint=False)
    raw = wave_fn(freq, t)
    env = np.ones(n)
    a   = max(1, int(0.008 * SAMPLE_RATE))      # 8 ms attack
    r   = max(1, int((1 - sustain) * n))        # release tail
    env[:a]  = np.linspace(0, 1, a)
    env[-r:] = np.linspace(1, 0, r)
    return raw * env * vol

def _kick_drum(vol):
    """Low thump: pitch-swept sine 120→50 Hz, 90 ms."""
    dur = 0.09
    n   = int(dur * SAMPLE_RATE)
    t   = np.linspace(0, dur, n, endpoint=False)
    freq = np.linspace(120, 50, n)
    raw  = np.sin(2 * np.pi * np.cumsum(freq) / SAMPLE_RATE)
    env  = np.linspace(1, 0, n) ** 2
    return raw * env * vol

def _hat_tick(vol):
    """Soft noise tick, 30 ms."""
    dur = 0.03
    n   = int(dur * SAMPLE_RATE)
    rng = np.random.default_rng(7)        # fixed seed → identical every loop
    raw = rng.uniform(-1, 1, n)
    env = np.linspace(1, 0, n) ** 2
    return raw * env * vol

def build_music_loop():
    """Render the full 4-bar loop into one stereo Sound."""
    eighth  = SUBDIV_DUR                 # one melody slot
    quarter = BEAT_DUR                   # one bass slot
    total_n = int(32 * eighth * SAMPLE_RATE)
    mix = np.zeros(total_n)

    for i, name in enumerate(MELODY):
        seg = _tone(NOTE[name], eighth, 0.16, _square)
        s   = int(i * eighth * SAMPLE_RATE)
        mix[s:s+len(seg)] += seg

    for i, name in enumerate(BASS):
        seg = _tone(NOTE[name], quarter, 0.13, _square, sustain=0.7)
        s   = int(i * quarter * SAMPLE_RATE)
        mix[s:s+len(seg)] += seg

    # Percussion: 16 quarter notes, compass accents per 4-beat bar
    #   beat 1 → kick (strong) | beat 3 → kick (medium) | beats 2,4 → hat (weak)
    for q in range(16):
        pos_in_bar = q % 4
        if pos_in_bar == 0:
            seg = _kick_drum(0.12)
        elif pos_in_bar == 2:
            seg = _kick_drum(0.06)
        else:
            seg = _hat_tick(0.04)
        s = int(q * quarter * SAMPLE_RATE)
        mix[s:s+len(seg)] += seg

    mix  = np.clip(mix, -1, 1)
    data = (mix * 32767).astype(np.int16)
    return pygame.sndarray.make_sound(
        np.ascontiguousarray(np.column_stack([data, data])))

# ── World position helpers ─────────────────────────────────────────────────────
def player_x_at_beat(beat):
    return PLAYER_START_X + PLAYER_SPEED * beat * BEAT_DUR

def calc_enemy_world_x(arrival_beat, side):
    """Enemy placed so it walks into HIT_RANGE exactly on arrival_beat."""
    px = player_x_at_beat(arrival_beat)
    if side == "right":
        # spawns ahead, walks left → starts far to the right
        return px + ENEMY_R_SPEED * LEAD_BEATS * BEAT_DUR
    else:
        # spawns behind, walks right faster than player → starts to the left
        return px - ENEMY_L_SPEED * LEAD_BEATS * BEAT_DUR

def calc_spike_world_x(beat):
    return player_x_at_beat(beat)

# ── Entity classes ─────────────────────────────────────────────────────────────
class Player:
    def __init__(self):
        self.world_x  = float(PLAYER_START_X)
        self.y        = float(FLOOR_Y - PLAYER_H)
        self.vy       = 0.0
        self.on_ground = True
        self.hp        = PLAYER_MAX_HP
        self.kick_side  = None   # "left" | "right" | None
        self.kick_timer = 0      # frames left for kick visual
        self.dmg_timer  = 0      # frames left for damage flash

    def try_jump(self):
        if self.on_ground:
            self.vy = JUMP_VEL
            self.on_ground = False

    def kick(self, side):
        self.kick_side  = side
        self.kick_timer = 10

    def take_damage(self):
        self.hp        -= 1
        self.dmg_timer  = 25

    def update(self, dt):
        self.world_x += PLAYER_SPEED * dt
        if not self.on_ground:
            self.vy += GRAVITY * dt
            self.y  += self.vy * dt
            if self.y >= FLOOR_Y - PLAYER_H:
                self.y = float(FLOOR_Y - PLAYER_H)
                self.vy = 0.0
                self.on_ground = True
        self.kick_timer = max(0, self.kick_timer - 1)
        self.dmg_timer  = max(0, self.dmg_timer  - 1)

    def draw(self, surf):
        sx = PLAYER_SCREEN_X
        sy = int(self.y)
        color = RED if self.dmg_timer > 0 else CYAN
        pygame.draw.rect(surf, color,
                         (sx - PLAYER_W//2, sy, PLAYER_W, PLAYER_H),
                         border_radius=5)
        # head circle
        pygame.draw.circle(surf, color, (sx, sy - 10), 12)
        # kick box — only on the active side, tight to the player
        if self.kick_timer > 0:
            kx = sx + (PLAYER_W // 2 if self.kick_side == "right" else -(PLAYER_W // 2 + KICK_REACH))
            ky = int(self.y) + PLAYER_H // 2 - 10
            pygame.draw.rect(surf, YELLOW, (kx, ky, KICK_REACH, 22), border_radius=4)


class Enemy:
    DYING_FRAMES = 72   # ~1.2 s at 60 fps

    # colours: on-beat = orange, off-beat = purple
    COLOR_ON  = (220, 130,  30)
    COLOR_OFF = (160,  60, 210)

    def __init__(self, world_x, side, arrival_subdiv, kind="kick"):
        self.world_x        = float(world_x)
        self.side           = side
        self.alive          = True
        self.dying          = 0
        self.arrival_subdiv = arrival_subdiv
        self.on_beat        = (arrival_subdiv % 2 == 0)   # even = quarter note
        self.kind           = kind        # "kick" (normal) | "low" (jump over)
        self.passed         = False       # low runner already resolved

    def speed(self):
        if self.kind == "low":
            return LOW_R_SPEED if self.side == "right" else LOW_L_SPEED
        return ENEMY_R_SPEED if self.side == "right" else ENEMY_L_SPEED

    def update(self, dt):
        v = self.speed()
        if self.side == "right":
            self.world_x -= v * dt
        else:
            self.world_x += v * dt
        if self.dying > 0:
            self.dying -= 1

    def draw(self, surf, cam_x):
        if not self.alive and self.dying == 0:
            return
        sx = int(self.world_x - cam_x)
        if not (-80 < sx < WIDTH + 80):
            return

        base = Enemy.COLOR_ON if self.on_beat else Enemy.COLOR_OFF

        if self.dying > 0:
            if (self.dying // 6) % 2 == 0:
                return                    # blink off
            color = WHITE if self.dying > Enemy.DYING_FRAMES - 4 else base
        else:
            color = base

        if self.kind == "low":
            # short fast runner — wide, low rectangle with small head
            sy = FLOOR_Y - LOW_H
            pygame.draw.rect(surf, color, (sx - LOW_W//2, sy, LOW_W, LOW_H),
                             border_radius=6)
            head_x = sx + (LOW_W//2 - 4 if self.side == "left" else -(LOW_W//2 - 4))
            pygame.draw.circle(surf, color, (head_x, sy - 4), 7)
            return

        sy = FLOOR_Y - ENEMY_H
        pygame.draw.rect(surf, color, (sx - ENEMY_W//2, sy, ENEMY_W, ENEMY_H),
                         border_radius=5)
        pygame.draw.circle(surf, color, (sx, sy - 10), 12)
        if self.dying == 0:
            tip_x = sx + (22 if self.side == "left" else -22)
            mid_y = sy + ENEMY_H // 2
            pygame.draw.polygon(surf, BLACK, [
                (tip_x,           mid_y),
                (tip_x - (16 if self.side == "left" else -16), mid_y - 9),
                (tip_x - (16 if self.side == "left" else -16), mid_y + 9),
            ])


class Spike:
    def __init__(self, world_x):
        self.world_x = world_x

    def draw(self, surf, cam_x):
        sx = int(self.world_x - cam_x)
        if not (-30 < sx < WIDTH + 30):
            return
        pygame.draw.polygon(surf, RED, [
            (sx - 14, FLOOR_Y),
            (sx + 14, FLOOR_Y),
            (sx,      FLOOR_Y - 28),
        ])


# ── HUD ────────────────────────────────────────────────────────────────────────
def draw_hud(surf, font, sm_font, player, pulse, beat_num, score):
    # HP pips
    for i in range(PLAYER_MAX_HP):
        c = GREEN if i < player.hp else DKGRAY
        pygame.draw.rect(surf, c, (20 + i * 38, 18, 28, 18), border_radius=3)

    # Score
    surf.blit(sm_font.render(f"SCORE  {score:05d}", True, YELLOW), (20, 44))

    # Beat metronome dot
    r = int(10 + pulse * 12)
    col = (255, int(255 * (1 - pulse)), 0)
    pygame.draw.circle(surf, col, (WIDTH - 35, 28), r)
    pygame.draw.circle(surf, WHITE, (WIDTH - 35, 28), 14, 2)

    # Beat label
    surf.blit(sm_font.render(f"beat {beat_num // 2}", True, GRAY), (WIDTH - 115, 46))

    # Controls
    surf.blit(sm_font.render("Z: left kick   X: right kick   SPACE: jump", True, GRAY),
              (20, HEIGHT - 22))


# ── Main ───────────────────────────────────────────────────────────────────────
# ── Parallax background ────────────────────────────────────────────────────────
# Three layers, deterministic from world position (no state needed):
#   far  mountains (0.2× scroll), mid buildings (0.5×), near posts (0.8×)

def draw_parallax(surf, cam_x):
    # Layer 1 — far mountains (triangles every 300 px, scroll 0.2×)
    off = cam_x * 0.2
    spacing = 300
    first = int(off // spacing) - 1
    for i in range(first, first + WIDTH // spacing + 3):
        sx = int(i * spacing - off)
        h  = 90 + (i * 53 % 60)            # deterministic pseudo-random height
        pygame.draw.polygon(surf, (24, 24, 44), [
            (sx - 160, FLOOR_Y),
            (sx,        FLOOR_Y - h),
            (sx + 160, FLOOR_Y),
        ])

    # Layer 2 — mid pagoda-ish buildings (every 220 px, scroll 0.5×)
    off = cam_x * 0.5
    spacing = 220
    first = int(off // spacing) - 1
    for i in range(first, first + WIDTH // spacing + 3):
        sx = int(i * spacing - off)
        w  = 70 + (i * 37 % 40)
        h  = 55 + (i * 71 % 45)
        pygame.draw.rect(surf, (38, 34, 60), (sx, FLOOR_Y - h, w, h))
        # roof line
        pygame.draw.polygon(surf, (50, 44, 76), [
            (sx - 10,     FLOOR_Y - h),
            (sx + w + 10, FLOOR_Y - h),
            (sx + w // 2, FLOOR_Y - h - 22),
        ])

    # Layer 3 — near posts (every 130 px, scroll 0.8×)
    off = cam_x * 0.8
    spacing = 130
    first = int(off // spacing) - 1
    for i in range(first, first + WIDTH // spacing + 3):
        sx = int(i * spacing - off)
        pygame.draw.rect(surf, (52, 52, 78), (sx, FLOOR_Y - 42, 8, 42))
        pygame.draw.rect(surf, (52, 52, 78), (sx - 6, FLOOR_Y - 46, 20, 6))


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Beat Brawler")
    clock  = pygame.time.Clock()
    font   = pygame.font.SysFont("monospace", 36, bold=True)
    sm_fnt = pygame.font.SysFont("monospace", 13)

    sounds = init_sounds()
    music  = build_music_loop()
    music.play(loops=-1)   # seamless loop, length = exact multiple of subdivision

    # New pattern every run
    level   = generate_level()
    last_b  = max(s for s, _, _ in level) + 8   # 4 quarter beats grace in subdivisions
    pending = list(level)
    enemies = []
    spikes  = [Spike(calc_spike_world_x(b)) for b in LEVEL_SPIKE_BEATS]

    player     = Player()
    beat_timer = 0.0
    beat_num   = 0
    beat_pulse = 0.0
    total_time = 0.0

    # Per-beat input buffers (time of last press; negative = stale)
    kick_l_time = -999.0
    kick_r_time = -999.0

    game_over = False
    win       = False
    score     = 0

    while True:
        dt = clock.tick(FPS) / 1000.0
        total_time += dt

        # ── Events ──────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    main(); return          # restart
                if not game_over:
                    if event.key == pygame.K_z:
                        kick_l_time = total_time
                        player.kick("left")
                        sounds["kick_l"].play()
                    if event.key == pygame.K_x:
                        kick_r_time = total_time
                        player.kick("right")
                        sounds["kick_r"].play()
                    if event.key == pygame.K_SPACE:
                        player.try_jump()

        if not game_over:
            player.update(dt)

            for e in enemies:
                if e.alive:
                    e.update(dt)

            # ── Subdivision tick (eighth-note grid) ─────────────────────────
            beat_timer += dt
            if beat_timer >= SUBDIV_DUR:
                beat_timer -= SUBDIV_DUR
                beat_num   += 1          # counts eighth notes now

                is_quarter = (beat_num % 2 == 0)
                if is_quarter:
                    beat_pulse = 1.0
                    # music carries the rhythm; soft tick only on bar downbeat
                    if beat_num % 8 == 0:
                        sounds["tick"].play()

                # Spawn enemies due on this subdivision
                LEAD_SUBDIVS = LEAD_BEATS * 2   # 4 quarter beats = 8 eighth notes
                T = LEAD_SUBDIVS * SUBDIV_DUR   # travel time (same 2.4 s)
                still_pending = []
                for arrival_subdiv, side, kind in pending:
                    if beat_num == arrival_subdiv - LEAD_SUBDIVS:
                        if kind == "low":
                            r_spd, l_spd = LOW_R_SPEED, LOW_L_SPEED
                        else:
                            r_spd, l_spd = ENEMY_R_SPEED, ENEMY_L_SPEED
                        if side == "right":
                            spawn_x = player.world_x + (PLAYER_SPEED + r_spd) * T
                        else:
                            spawn_x = player.world_x - (l_spd - PLAYER_SPEED) * T
                        enemies.append(Enemy(spawn_x, side, arrival_subdiv, kind))
                    else:
                        still_pending.append((arrival_subdiv, side, kind))
                pending = still_pending

                # Did player kick recently enough?
                kick_l_valid = (0 < total_time - kick_l_time < BEAT_BUFFER)
                kick_r_valid = (0 < total_time - kick_r_time < BEAT_BUFFER)

                # Resolve enemies only on their exact arrival subdivision
                for e in enemies:
                    if not e.alive or e.passed or beat_num != e.arrival_subdiv:
                        continue

                    if e.kind == "low":
                        # must be airborne when it arrives
                        e.passed = True
                        if player.on_ground:
                            e.alive = False
                            player.take_damage()
                            sounds["damage"].play()
                            if player.hp <= 0:
                                game_over = True
                                music.stop()
                        else:
                            sounds["low_dodge"].play()
                            score += 150
                            # runner keeps going and exits the screen
                        continue

                    e.alive = False
                    kicked = (e.side == "right" and kick_r_valid) or \
                             (e.side == "left"  and kick_l_valid)
                    if kicked:
                        e.dying = Enemy.DYING_FRAMES
                        sounds["enemy_die"].play()
                        score += 100
                    else:
                        player.take_damage()
                        sounds["damage"].play()
                        if player.hp <= 0:
                            game_over = True
                            music.stop()

                # Check spike on this beat (player must be in the air)
                if beat_num in LEVEL_SPIKE_BEATS:
                    if player.on_ground:
                        player.take_damage()
                        sounds["damage"].play()
                        if player.hp <= 0:
                            game_over = True
                            music.stop()
                    else:
                        sounds["spike_dodge"].play()

                # Invalidate used inputs
                kick_l_time = -999.0
                kick_r_time = -999.0

                # Win condition (passed low runners count as resolved)
                if beat_num >= last_b and not pending and \
                   all((not e.alive) or e.passed for e in enemies):
                    win = game_over = True
                    music.stop()

        # Beat pulse decay
        beat_pulse = max(0.0, beat_pulse - dt * 5)

        # Camera
        cam_x = player.world_x - PLAYER_SCREEN_X

        # ── Draw ────────────────────────────────────────────────────────────
        screen.fill(BLACK)

        # Parallax background
        draw_parallax(screen, cam_x)

        # Floor
        pygame.draw.line(screen, GRAY, (0, FLOOR_Y), (WIDTH, FLOOR_Y), 2)
        # Floor fill
        pygame.draw.rect(screen, DKGRAY, (0, FLOOR_Y + 2, WIDTH, HEIGHT - FLOOR_Y - 2))

        # Spikes
        for sp in spikes:
            sp.draw(screen, cam_x)

        # Enemies
        for e in enemies:
            if e.alive or e.dying > 0:
                e.draw(screen, cam_x)

        # Player
        player.draw(screen)

        # HUD
        draw_hud(screen, font, sm_fnt, player, beat_pulse, beat_num, score)

        # ── Game-over / win overlay ──────────────────────────────────────────
        if game_over:
            msg   = "YOU WIN!"   if win else "GAME OVER"
            color = GREEN        if win else RED
            txt   = font.render(msg, True, color)
            screen.blit(txt, (WIDTH//2 - txt.get_width()//2, HEIGHT//2 - 40))
            sc    = sm_fnt.render(f"Score: {score:05d}", True, YELLOW)
            screen.blit(sc,  (WIDTH//2 - sc.get_width()//2,  HEIGHT//2 + 5))
            hint  = sm_fnt.render("Press R to restart", True, WHITE)
            screen.blit(hint, (WIDTH//2 - hint.get_width()//2, HEIGHT//2 + 28))

        pygame.display.flip()


if __name__ == "__main__":
    main()
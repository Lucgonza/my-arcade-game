"""
Horse Runner - Chrome T-Rex style endless runner.
A horse jumps over bushes and ducks under birds.
Conventions: single file, procedural graphics, synthetic audio, parallax.

Controls:
  SPACE / UP  - jump
  DOWN        - duck
  R           - restart after game over
  ESC         - quit
"""

import json
import math
import os
import random
import sys

import numpy as np
import pygame

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
WIDTH, HEIGHT = 900, 400
FPS = 60
GROUND_Y = HEIGHT - 60

GRAVITY = 2400.0
JUMP_VELOCITY = -880.0

START_SPEED = 320.0        # px/s world scroll speed
SPEED_RAMP = 6.0           # px/s gained per second
MAX_SPEED = 900.0

BIRD_MIN_SCORE = 300       # birds appear after this score
MILESTONE = 100            # beep every N points

HIGHSCORE_FILE = "horse_highscore.json"

# Palette (monochrome, Guernica-inspired: blacks, whites, newsprint greys)
SKY_TOP = (225, 225, 220)
SKY_BOTTOM = (190, 190, 185)
SUN = (245, 245, 240)            # drawn as a bulb-eye with rays
HILL_FAR = (150, 150, 148)
HILL_NEAR = (110, 110, 108)
GROUND_COL = (70, 70, 68)
GROUND_LINE = (25, 25, 25)
HORSE_LIGHT = (240, 240, 235)    # faceted body planes
HORSE_MID = (185, 185, 180)
HORSE_DARK = (120, 120, 118)
HORSE_LINE = (15, 15, 15)        # black outlines
BUSH_GREEN = (30, 30, 30)        # black shard bushes
BUSH_DARK = (15, 15, 15)
BUSH_BERRY = (235, 235, 230)     # white accents
BIRD_COL = (235, 235, 230)
BIRD_WING = (170, 170, 168)
TEXT_COL = (15, 15, 15)
CLOUD_COL = (240, 240, 238)

# ----------------------------------------------------------------------------
# Synthetic audio
# ----------------------------------------------------------------------------
SAMPLE_RATE = 22050


def make_sound(samples: np.ndarray) -> pygame.mixer.Sound:
    samples = np.clip(samples, -1.0, 1.0)
    mono = (samples * 32767 * 0.5).astype(np.int16)   # conservative volume
    stereo = np.column_stack((mono, mono))
    return pygame.sndarray.make_sound(np.ascontiguousarray(stereo))


def sfx_jump():
    # Dramatic whinny-like jump: sweep with vibrato over a low thump
    t = np.linspace(0, 0.35, int(SAMPLE_RATE * 0.35), False)
    sweep = 220 + 660 * (t / 0.35)                       # rising sweep
    vib = 1 + 0.04 * np.sin(2 * np.pi * 24 * t)          # fast vibrato
    voice = np.sign(np.sin(2 * np.pi * sweep * vib * t)) * 0.35  # square, brash
    voice *= np.exp(-t * 6)
    thump = np.sin(2 * np.pi * 70 * t) * np.exp(-t * 22) * 0.8
    return make_sound(voice + thump)


def sfx_hit():
    t = np.linspace(0, 0.35, int(SAMPLE_RATE * 0.35), False)
    noise = np.random.uniform(-1, 1, t.size)
    tone = np.sin(2 * np.pi * 110 * t)
    wave = (0.6 * noise + 0.4 * tone) * np.exp(-t * 9)
    return make_sound(wave)


def sfx_milestone():
    t = np.linspace(0, 0.12, int(SAMPLE_RATE * 0.12), False)
    w1 = np.sin(2 * np.pi * 880 * t) * np.exp(-t * 18)
    w2 = np.sin(2 * np.pi * 1320 * t) * np.exp(-t * 18)
    return make_sound(np.concatenate((w1, w2)))


def make_music() -> pygame.mixer.Sound:
    """Somber D-minor loop: bass drone + sparse melody. ~9.6 s, loops."""
    bpm = 100
    beat = 60.0 / bpm
    n_beats = 16
    total = int(SAMPLE_RATE * beat * n_beats)
    mix = np.zeros(total)
    D2, F2, A2, C3 = 73.42, 87.31, 110.0, 130.81
    D4, E4, F4, G4, A4, Bb4, C5 = (293.66, 329.63, 349.23, 392.0,
                                   440.0, 466.16, 523.25)

    def add(freq, start_beat, dur_beats, vol, shape="sine"):
        n0 = int(start_beat * beat * SAMPLE_RATE)
        n = int(dur_beats * beat * SAMPLE_RATE)
        if n0 + n > total:
            n = total - n0
        t = np.arange(n) / SAMPLE_RATE
        if shape == "saw":
            w = 2 * ((freq * t) % 1.0) - 1.0
        else:
            w = np.sin(2 * np.pi * freq * t)
        env = np.minimum(1.0, t / 0.02) * np.exp(-t * (2.2 / (dur_beats * beat)))
        mix[n0:n0 + n] += w * env * vol

    # Bass: Dm - Bb(F) - Am - Dm, two beats each note (8 x 2 = 16 beats)
    bass = [D2, D2, F2, F2, A2, A2, D2, C3]
    for i, f in enumerate(bass):
        add(f, i * 2, 2, 0.30)
    # Sparse melody (D natural minor), enters on beat 4
    melody = [(D4, 4, 1.5), (F4, 6, 1), (E4, 7, 1), (D4, 8, 2),
              (A4, 10, 1.5), (G4, 11.5, 0.5), (F4, 12, 2), (E4, 14, 2)]
    for f, s, d in melody:
        add(f, s, d, 0.16, "saw")
    # Low pulse every beat (heartbeat)
    for b in range(n_beats):
        add(D2 / 2, b, 0.2, 0.22)
    return make_sound(mix * 0.6)


# ----------------------------------------------------------------------------
# High score persistence
# ----------------------------------------------------------------------------
def load_highscore() -> int:
    try:
        with open(HIGHSCORE_FILE, "r") as f:
            return int(json.load(f).get("highscore", 0))
    except (OSError, ValueError, json.JSONDecodeError):
        return 0


def save_highscore(score: int) -> None:
    try:
        with open(HIGHSCORE_FILE, "w") as f:
            json.dump({"highscore": int(score)}, f)
    except OSError:
        pass


# ----------------------------------------------------------------------------
# Horse - cubist (angular planes, black outlines)
# ----------------------------------------------------------------------------
class Horse:
    def __init__(self):
        self.x = 110
        self.w, self.h = 74, 52
        self.duck_h = 34
        self.y = GROUND_Y - self.h
        self.vy = 0.0
        self.on_ground = True
        self.ducking = False
        self.leg_phase = 0.0
        self.bob = 0.0
        self.tilt = 0.0

    @property
    def rect(self) -> pygame.Rect:
        h = self.duck_h if self.ducking else self.h
        return pygame.Rect(int(self.x), int(GROUND_Y - h) if self.on_ground
                           else int(self.y + (self.h - h)), self.w, h)

    def jump(self, snd):
        if self.on_ground:
            self.vy = JUMP_VELOCITY
            self.on_ground = False
            self.ducking = False
            snd.play()

    def update(self, dt: float, speed: float, duck_pressed: bool):
        if self.on_ground:
            self.ducking = duck_pressed
            self.leg_phase += dt * speed * 0.045
            self.bob = math.sin(self.leg_phase * 2) * 3
            self.tilt = 0.0
        else:
            self.bob = 0.0
            self.tilt = max(-0.35, min(0.35, -self.vy / 2600.0))
            self.vy += GRAVITY * dt
            self.y += self.vy * dt
            if self.y >= GROUND_Y - self.h:
                self.y = GROUND_Y - self.h
                self.vy = 0.0
                self.on_ground = True

    def _leg(self, surf, hip, phase, reach=0.8, airborne_pose=None):
        """Angular two-segment leg, straight black strokes."""
        if airborne_pose is None:
            hip_ang = math.sin(phase) * reach
            fold = max(0.0, -math.sin(phase - 0.9)) * 1.1
        else:
            hip_ang, fold = airborne_pose
        upper, lower = 14, 14
        knee = (hip[0] + math.sin(hip_ang) * upper,
                hip[1] + math.cos(hip_ang) * upper)
        shin_ang = hip_ang - fold
        hoof = (knee[0] + math.sin(shin_ang) * lower,
                knee[1] + math.cos(shin_ang) * lower)
        # Faceted leg: light plane with black edge
        pygame.draw.line(surf, HORSE_LINE, hip, knee, 8)
        pygame.draw.line(surf, HORSE_MID, hip, knee, 4)
        pygame.draw.line(surf, HORSE_LINE, knee, hoof, 7)
        pygame.draw.line(surf, HORSE_LIGHT, knee, hoof, 3)
        # Angular hoof: small black triangle
        pygame.draw.polygon(surf, HORSE_LINE, [
            (hoof[0] - 4, hoof[1] + 2), (hoof[0] + 5, hoof[1] + 2),
            (hoof[0] + 1, hoof[1] - 4)])

    def draw(self, surf):
        r = self.rect
        ducking = self.ducking and self.on_ground
        bob = self.bob if self.on_ground else 0.0
        by = r.y + 6 + bob
        body = pygame.Rect(r.x, int(by), r.w, r.h - 18)
        hind_hip = (r.x + 16, body.bottom - 6)
        fore_hip = (r.right - 18, body.bottom - 6)
        p = self.leg_phase

        # Legs
        if self.on_ground:
            self._leg(surf, hind_hip, p, 0.9)
            self._leg(surf, (hind_hip[0] + 9, hind_hip[1]), p - 0.5, 0.9)
            self._leg(surf, fore_hip, p + math.pi * 0.75, 0.8)
            self._leg(surf, (fore_hip[0] - 9, fore_hip[1]),
                      p + math.pi * 0.75 - 0.5, 0.8)
        else:
            if self.vy < 0:
                self._leg(surf, fore_hip, 0, airborne_pose=(1.0, 1.6))
                self._leg(surf, (fore_hip[0] - 9, fore_hip[1]), 0,
                          airborne_pose=(0.8, 1.5))
                self._leg(surf, hind_hip, 0, airborne_pose=(-0.9, 0.2))
                self._leg(surf, (hind_hip[0] + 9, hind_hip[1]), 0,
                          airborne_pose=(-0.7, 0.2))
            else:
                self._leg(surf, fore_hip, 0, airborne_pose=(0.5, 0.1))
                self._leg(surf, (fore_hip[0] - 9, fore_hip[1]), 0,
                          airborne_pose=(0.3, 0.1))
                self._leg(surf, hind_hip, 0, airborne_pose=(-0.5, 1.3))
                self._leg(surf, (hind_hip[0] + 9, hind_hip[1]), 0,
                          airborne_pose=(-0.4, 1.2))

        # --- Body: fragmented angular planes ---
        tilt_px = self.tilt * 26
        t, b_ = body.top, body.bottom
        l, rt = body.left, body.right
        cx = body.centerx
        outline = [
            (l - 4, t + 10 + tilt_px * 0.5),          # rump top corner
            (l + 14, t - 4 + tilt_px * 0.3),
            (cx + 6, t + 2),
            (rt - 10, t - 6 - tilt_px * 0.5),         # withers
            (rt + 2, t + 8 - tilt_px * 0.5),          # chest point
            (rt - 6, b_ - 2 - tilt_px * 0.3),
            (cx - 4, b_ + 2),
            (l + 6, b_ - 2 + tilt_px * 0.3),
        ]
        pygame.draw.polygon(surf, HORSE_LIGHT, outline)
        # Interior facets (cubist planes in greys)
        pygame.draw.polygon(surf, HORSE_MID, [
            outline[0], outline[1], (cx - 8, t + 16), (l + 8, b_ - 8)])
        pygame.draw.polygon(surf, HORSE_DARK, [
            (cx - 8, t + 16), (cx + 6, t + 2), (cx + 10, b_ - 6),
            (cx - 4, b_ + 2)])
        pygame.draw.polygon(surf, HORSE_LINE, outline, 3)
        # Facet edges (thin black interior lines)
        pygame.draw.line(surf, HORSE_LINE, outline[1], (l + 8, b_ - 8), 2)
        pygame.draw.line(surf, HORSE_LINE, (cx + 6, t + 2), (cx - 4, b_ + 2), 2)

        # --- Neck + head: upward wedge (Guernica-like thrown-back head) ---
        if ducking:
            head_tip = (r.right + 22, by + 10)
            neck_pts = [(rt - 26, by + 4), (head_tip[0], head_tip[1] - 4),
                        (head_tip[0] - 2, head_tip[1] + 6), (rt - 24, by + 18)]
            pygame.draw.polygon(surf, HORSE_LIGHT, neck_pts)
            pygame.draw.polygon(surf, HORSE_LINE, neck_pts, 3)
            eye_c = (head_tip[0] - 14, head_tip[1] - 1)
            jaw = None
        else:
            top_y = by - 30 - tilt_px
            head_tip = (rt + 16 + self.tilt * 10, top_y + 2)
            neck_pts = [(rt - 26, by + 12), (rt - 14, by - 8),
                        (head_tip[0] - 8, top_y), (head_tip[0], top_y + 8),
                        (rt - 2, by + 16)]
            pygame.draw.polygon(surf, HORSE_MID, neck_pts)
            pygame.draw.polygon(surf, HORSE_LINE, neck_pts, 3)
            # Open angular jaw (upward wedge mouth)
            jaw = [(head_tip[0] - 6, top_y + 4),
                   (head_tip[0] + 10, top_y - 6),
                   (head_tip[0] + 10, top_y + 10)]
            pygame.draw.polygon(surf, HORSE_LIGHT, jaw)
            pygame.draw.polygon(surf, HORSE_LINE, jaw, 2)
            eye_c = (head_tip[0] - 2, top_y + 2)
        # Almond eye: outline + dot
        pygame.draw.circle(surf, HORSE_LIGHT, eye_c, 5)
        pygame.draw.circle(surf, HORSE_LINE, eye_c, 5, 2)
        pygame.draw.circle(surf, HORSE_LINE, eye_c, 2)
        # Ear: black triangle
        pygame.draw.polygon(surf, HORSE_LINE, [
            (eye_c[0] - 10, eye_c[1] - 4), (eye_c[0] - 4, eye_c[1] - 16),
            (eye_c[0] - 1, eye_c[1] - 5)])

        # --- Mane: black triangle spikes along the neck ---
        if not ducking:
            for i in range(3):
                mx = rt - 22 + i * 9
                my = by - 2 - i * 8 - tilt_px * (i / 3)
                pygame.draw.polygon(surf, HORSE_LINE, [
                    (mx, my), (mx - 8, my - 10), (mx + 3, my - 4)])

        # --- Tail: angular zigzag ---
        if self.on_ground:
            sway = math.sin(p * 0.7) * 5
            tail = [(l + 2, by + 4), (l - 8 + sway, by + 10),
                    (l - 4 + sway, by + 18), (l - 14 + sway, by + 26)]
        else:
            tail = [(l + 2, by + 4), (l - 10, by + 4 + tilt_px),
                    (l - 8, by + 12 + tilt_px), (l - 20, by + 14 + tilt_px)]
        pygame.draw.lines(surf, HORSE_LINE, False, tail, 5)


# ----------------------------------------------------------------------------
# Obstacles
# ----------------------------------------------------------------------------
class Bush:
    def __init__(self, x: float, big: bool):
        self.big = big
        self.w = 56 if big else 34
        self.h = 44 if big else 30
        self.x = x
        self.blobs = [(random.uniform(0.15, 0.85), random.uniform(0.2, 0.6),
                       random.uniform(0.25, 0.45)) for _ in range(4 if big else 3)]
        self.berries = [(random.uniform(0.2, 0.8), random.uniform(0.2, 0.7))
                        for _ in range(3 if big else 2)]

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x) + 4, GROUND_Y - self.h + 4,
                           self.w - 8, self.h - 4)   # forgiving hitbox

    def draw(self, surf):
        x, y = int(self.x), GROUND_Y - self.h
        # Angular black shards (cubist bush)
        pygame.draw.polygon(surf, BUSH_DARK, [
            (x, GROUND_Y), (x + self.w // 4, y + self.h // 4),
            (x + self.w // 2, y), (x + 3 * self.w // 4, y + self.h // 3),
            (x + self.w, GROUND_Y)])
        pygame.draw.polygon(surf, BUSH_GREEN, [
            (x + 6, GROUND_Y), (x + self.w // 2, y + self.h // 5),
            (x + self.w - 6, GROUND_Y)])
        # White accent edges
        pygame.draw.line(surf, BUSH_BERRY, (x + self.w // 2, y + self.h // 5),
                         (x + self.w // 3, GROUND_Y - 4), 2)
        for fx, fy in self.berries:
            px_, py_ = x + int(fx * self.w), y + int(fy * self.h)
            pygame.draw.polygon(surf, BUSH_BERRY, [
                (px_, py_ - 3), (px_ + 3, py_ + 2), (px_ - 3, py_ + 2)])


class Bird:
    HEIGHTS = (GROUND_Y - 34, GROUND_Y - 78, GROUND_Y - 120)  # low/duck/high

    def __init__(self, x: float):
        self.x = x
        self.y = random.choice(self.HEIGHTS)
        self.w, self.h = 46, 24
        self.flap = random.uniform(0, math.tau)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x) + 4, int(self.y) + 4,
                           self.w - 8, self.h - 6)

    def update(self, dt: float):
        self.flap += dt * 14

    def draw(self, surf):
        x, y = int(self.x), int(self.y)
        # Angular body wedge
        body = [(x, y + 10), (x + self.w - 12, y + 4),
                (x + self.w - 12, y + 16), (x + 6, y + 18)]
        pygame.draw.polygon(surf, BIRD_COL, body)
        pygame.draw.polygon(surf, (15, 15, 15), body, 2)
        # Head: small triangle + open beak
        pygame.draw.polygon(surf, BIRD_COL, [
            (x + self.w - 14, y + 2), (x + self.w - 2, y + 8),
            (x + self.w - 14, y + 16)])
        pygame.draw.polygon(surf, (15, 15, 15), [
            (x + self.w - 4, y + 6), (x + self.w + 6, y + 2),
            (x + self.w - 2, y + 10)], 2)
        # Wing: black angular flap
        wing = math.sin(self.flap) * 12
        pygame.draw.polygon(surf, (15, 15, 15), [
            (x + 12, y + 10), (x + 30, y + 10), (x + 20, y + 10 - wing)])
        pygame.draw.circle(surf, (15, 15, 15), (x + self.w - 10, y + 7), 2)


# ----------------------------------------------------------------------------
# Parallax background
# ----------------------------------------------------------------------------
class Background:
    def __init__(self):
        self.clouds = [[random.uniform(0, WIDTH), random.uniform(30, 130),
                        random.uniform(0.7, 1.3)] for _ in range(5)]
        random.seed(7)
        self.far_hills = self._hills(120, 60)
        self.near_hills = self._hills(80, 90)
        random.seed()
        self.off_far = 0.0
        self.off_near = 0.0

    @staticmethod
    def _hills(step, amp):
        pts = []
        x = -step
        while x < WIDTH * 2 + step:
            pts.append((x, random.uniform(0.3, 1.0) * amp))
            x += step
        return pts

    def update(self, dt, speed):
        self.off_far = (self.off_far + speed * 0.15 * dt) % (WIDTH * 2)
        self.off_near = (self.off_near + speed * 0.35 * dt) % (WIDTH * 2)
        for c in self.clouds:
            c[0] -= speed * 0.05 * dt * c[2]
            if c[0] < -120:
                c[0] = WIDTH + random.uniform(20, 120)
                c[1] = random.uniform(30, 130)

    def _draw_hills(self, surf, pts, offset, color, base_y):
        poly = [(-10, base_y)]
        for x, h in pts:
            sx = (x - offset) % (WIDTH * 2) - WIDTH // 2
            if -200 < sx < WIDTH + 200:
                poly.append((sx, base_y - h))
        poly.sort(key=lambda p: p[0])
        poly = [(-10, base_y)] + poly + [(WIDTH + 10, base_y)]
        if len(poly) > 3:
            pygame.draw.polygon(surf, color, poly)

    def draw(self, surf):
        # Sky gradient
        for i in range(HEIGHT):
            t = i / HEIGHT
            col = tuple(int(SKY_TOP[c] + (SKY_BOTTOM[c] - SKY_TOP[c]) * t)
                        for c in range(3))
            pygame.draw.line(surf, col, (0, i), (WIDTH, i))
        # Bulb-eye in the sky (Guernica-style light)
        bx, by_ = WIDTH - 110, 70
        for a in range(12):
            ang = a * math.tau / 12
            pygame.draw.polygon(surf, (30, 30, 30), [
                (bx + math.cos(ang) * 38, by_ + math.sin(ang) * 38),
                (bx + math.cos(ang + 0.12) * 52, by_ + math.sin(ang + 0.12) * 52),
                (bx + math.cos(ang - 0.12) * 52, by_ + math.sin(ang - 0.12) * 52)])
        pygame.draw.circle(surf, SUN, (bx, by_), 34)
        pygame.draw.circle(surf, (30, 30, 30), (bx, by_), 34, 3)
        pygame.draw.circle(surf, (30, 30, 30), (bx, by_), 10)
        for cx, cy, s in self.clouds:
            for ox, oy, r in ((0, 0, 22), (18, 6, 16), (-18, 6, 16)):
                pygame.draw.circle(surf, CLOUD_COL,
                                   (int(cx + ox * s), int(cy + oy * s)),
                                   int(r * s))
        self._draw_hills(surf, self.far_hills, self.off_far, HILL_FAR, GROUND_Y)
        self._draw_hills(surf, self.near_hills, self.off_near, HILL_NEAR, GROUND_Y)


# ----------------------------------------------------------------------------
# Game
# ----------------------------------------------------------------------------
class Game:
    def __init__(self, screen):
        self.screen = screen
        self.font = pygame.font.SysFont("menlo,monospace", 22)
        self.big_font = pygame.font.SysFont("menlo,monospace", 40, bold=True)
        self.snd_jump = sfx_jump()
        self.snd_hit = sfx_hit()
        self.snd_milestone = sfx_milestone()
        self.music = make_music()
        self.music.play(loops=-1)
        self.highscore = load_highscore()
        self.bg = Background()
        self.reset()

    def reset(self):
        self.horse = Horse()
        self.obstacles = []
        self.speed = START_SPEED
        self.score = 0.0
        self.next_milestone = MILESTONE
        self.next_spawn_x = WIDTH + 200
        self.game_over = False
        self.ground_off = 0.0

    def spawn(self):
        gap = random.uniform(0.55, 1.1) * self.speed + 220
        x = self.next_spawn_x
        if self.score >= BIRD_MIN_SCORE and random.random() < 0.3:
            self.obstacles.append(Bird(x))
        else:
            self.obstacles.append(Bush(x, random.random() < 0.4))
            if random.random() < 0.25:                     # double bush combo
                self.obstacles.append(Bush(x + 40, False))
        self.next_spawn_x = x + gap

    def update(self, dt):
        if self.game_over:
            return
        keys = pygame.key.get_pressed()
        self.speed = min(MAX_SPEED, self.speed + SPEED_RAMP * dt)
        self.horse.update(dt, self.speed, keys[pygame.K_DOWN])
        self.bg.update(dt, self.speed)
        self.ground_off = (self.ground_off + self.speed * dt) % 40

        self.next_spawn_x -= self.speed * dt
        if self.next_spawn_x < WIDTH + 100:
            self.spawn()

        hrect = self.horse.rect
        for ob in self.obstacles:
            ob.x -= self.speed * dt
            if isinstance(ob, Bird):
                ob.update(dt)
            if ob.rect.colliderect(hrect):
                self.game_over = True
                self.snd_hit.play()
                if self.score > self.highscore:
                    self.highscore = int(self.score)
                    save_highscore(self.highscore)
        self.obstacles = [o for o in self.obstacles if o.x > -100]

        self.score += self.speed * dt * 0.02
        if self.score >= self.next_milestone:
            self.snd_milestone.play()
            self.next_milestone += MILESTONE

    def draw(self):
        self.bg.draw(self.screen)
        # Ground
        pygame.draw.rect(self.screen, GROUND_COL,
                         (0, GROUND_Y, WIDTH, HEIGHT - GROUND_Y))
        pygame.draw.line(self.screen, GROUND_LINE,
                         (0, GROUND_Y), (WIDTH, GROUND_Y), 3)
        x = -self.ground_off
        while x < WIDTH:
            pygame.draw.line(self.screen, GROUND_LINE,
                             (x, GROUND_Y + 20), (x + 14, GROUND_Y + 20), 2)
            x += 40

        for ob in self.obstacles:
            ob.draw(self.screen)
        self.horse.draw(self.screen)

        # HUD
        s = self.font.render(f"SCORE {int(self.score):05d}", True, TEXT_COL)
        h = self.font.render(f"HI {self.highscore:05d}", True, TEXT_COL)
        self.screen.blit(s, (WIDTH - s.get_width() - 16, 12))
        self.screen.blit(h, (WIDTH - s.get_width() - h.get_width() - 40, 12))

        if self.game_over:
            t1 = self.big_font.render("GAME OVER", True, (180, 40, 40))
            t2 = self.font.render("Press R to restart", True, TEXT_COL)
            self.screen.blit(t1, (WIDTH // 2 - t1.get_width() // 2, 140))
            self.screen.blit(t2, (WIDTH // 2 - t2.get_width() // 2, 195))


def main():
    pygame.mixer.pre_init(SAMPLE_RATE, -16, 2, 512)
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Horse Runner")
    clock = pygame.time.Clock()
    game = Game(screen)

    while True:
        dt = min(clock.tick(FPS) / 1000.0, 1 / 30)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                if ev.key in (pygame.K_SPACE, pygame.K_UP):
                    if game.game_over:
                        pass
                    else:
                        game.horse.jump(game.snd_jump)
                if ev.key == pygame.K_r and game.game_over:
                    game.reset()
        game.update(dt)
        game.draw()
        pygame.display.flip()


if __name__ == "__main__":
    main()
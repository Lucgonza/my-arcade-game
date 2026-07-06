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

# Palette (colorful)
SKY_TOP = (110, 190, 240)
SKY_BOTTOM = (200, 235, 250)
SUN = (255, 220, 100)
HILL_FAR = (150, 205, 150)
HILL_NEAR = (100, 175, 110)
GROUND_COL = (215, 170, 110)
GROUND_LINE = (150, 110, 70)
HORSE_COAT = (245, 242, 235)     # white pinto base
HORSE_PATCH = (150, 90, 45)      # brown patches
HORSE_MANE = (45, 35, 30)        # dark mane/tail
HORSE_HOOF = (35, 30, 25)
HORSE_MUZZLE = (120, 110, 105)
BUSH_GREEN = (60, 140, 60)
BUSH_DARK = (40, 105, 45)
BUSH_BERRY = (220, 60, 80)
BIRD_COL = (70, 90, 200)
BIRD_WING = (110, 130, 235)
TEXT_COL = (40, 40, 60)
CLOUD_COL = (255, 255, 255)

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
    t = np.linspace(0, 0.15, int(SAMPLE_RATE * 0.15), False)
    freq = 300 + 500 * t / 0.15                      # rising chirp
    wave = np.sin(2 * np.pi * freq * t) * np.exp(-t * 12)
    return make_sound(wave)


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
# Horse - embedded pixel-art sprites
# Chars: . transparent  W white coat  B brown patch  M mane/outline
#        H hoof  E eye  N muzzle
# ----------------------------------------------------------------------------
SPRITE_PX = 4          # screen pixels per art pixel
SPRITE_PALETTE = {
    "W": (245, 242, 235),
    "B": (150, 89, 45),
    "M": (45, 35, 30),
    "H": (35, 30, 25),
    "E": (20, 20, 20),
    "N": (138, 128, 120),
}

# Shared upper body (head, neck, torso, tail) - 22 wide x 9 rows
HORSE_BASE = [
    "......................",
    "............MMM.......",
    "...........MWWWM......",
    "...........BBWWEM.....",
    "....M......MWWWNN.....",
    "...MMWWWWWWWWWWN......",
    "..MWBBWWWWWWWBW.......",
    "..MWBBWWWWWWWWW.......",
    "...WWWWWWWWWWWW.......",
]

# Leg variants - 4 rows each (gallop cycle + jump poses)
LEGS_GALLOP = [
    [   # 1: full extension - hind swept back, fore reaching
        "..WW........WW........",
        ".WW..........WW.......",
        "WW............WW......",
        "HH............HH......",
    ],
    [   # 2: gathering under
        "...WW.....WW..........",
        "...WW......WW.........",
        "...WW.......WW........",
        "...HH.......HH........",
    ],
    [   # 3: tucked, legs cross under body
        "....WW...WW...........",
        ".....WW.WW............",
        ".....WW.WW............",
        ".....HH.HH............",
    ],
    [   # 4: push-off
        "...WW......WW.........",
        "..WW........WW........",
        "..WW.........WW.......",
        "..HH.........HH.......",
    ],
]
LEGS_RISE = [   # take-off: fore folded up, hind stretched back
    ".WW.........WWWH......",
    "WW....................",
    "WW....................",
    "HH....................",
]
LEGS_FALL = [   # landing: fore extended down, hind folded
    "....WWWH.....WW.......",
    ".............WW.......",
    "..............WW......",
    "..............HH......",
]

HORSE_DUCK = [
    "........................",
    "...MM..............MMM..",
    "..MMWWWWWWWWWWWWWWWWWEM.",
    ".MWBBWWWWWWWBWWWWWWWWNN.",
    ".MWBBWWWWWWWWWWWWWWWN...",
    "..WWWWWWWWWWWWWW........",
    "...WW.......WW..........",
    "...WW........WW.........",
    "...HH........HH.........",
    "........................",
]


def build_sprite(grid) -> pygame.Surface:
    w, h = len(grid[0]), len(grid)
    surf = pygame.Surface((w * SPRITE_PX, h * SPRITE_PX), pygame.SRCALPHA)
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            col = SPRITE_PALETTE.get(ch)
            if col:
                surf.fill(col, (x * SPRITE_PX, y * SPRITE_PX,
                                SPRITE_PX, SPRITE_PX))
    return surf


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
        # Pre-render all frames once
        self.frames_gallop = [build_sprite(HORSE_BASE + legs)
                              for legs in LEGS_GALLOP]
        self.frame_rise = build_sprite(HORSE_BASE + LEGS_RISE)
        self.frame_fall = build_sprite(HORSE_BASE + LEGS_FALL)
        self.frame_duck = build_sprite(HORSE_DUCK)

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
            self.leg_phase += dt * speed * 0.02   # gallop frame rate
            self.bob = math.sin(self.leg_phase * math.pi) * 2
        else:
            self.bob = 0.0
            self.vy += GRAVITY * dt
            self.y += self.vy * dt
            if self.y >= GROUND_Y - self.h:
                self.y = GROUND_Y - self.h
                self.vy = 0.0
                self.on_ground = True

    def draw(self, surf):
        r = self.rect
        if self.ducking and self.on_ground:
            img = self.frame_duck
        elif self.on_ground:
            img = self.frames_gallop[int(self.leg_phase) % 4]
        else:
            img = self.frame_rise if self.vy < 0 else self.frame_fall
        # Align sprite bottom to hitbox bottom, slight left overhang for tail
        surf.blit(img, (r.x - 8, r.bottom - img.get_height() + self.bob))


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
        base = pygame.Rect(x, y + self.h // 3, self.w, self.h - self.h // 3)
        pygame.draw.ellipse(surf, BUSH_DARK, base)
        for fx, fy, fr in self.blobs:
            pygame.draw.circle(surf, BUSH_GREEN,
                               (x + int(fx * self.w), y + int(fy * self.h)),
                               int(fr * self.h))
        for fx, fy in self.berries:
            pygame.draw.circle(surf, BUSH_BERRY,
                               (x + int(fx * self.w), y + int(fy * self.h)), 3)


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
        pygame.draw.ellipse(surf, BIRD_COL, (x, y + 6, self.w - 10, 14))
        pygame.draw.circle(surf, BIRD_COL, (x + self.w - 12, y + 10), 7)
        pygame.draw.polygon(surf, (255, 180, 60), [
            (x + self.w - 6, y + 8), (x + self.w + 4, y + 11),
            (x + self.w - 6, y + 14)])
        wing = math.sin(self.flap) * 12
        pygame.draw.polygon(surf, BIRD_WING, [
            (x + 12, y + 10), (x + 30, y + 10), (x + 20, y + 10 - wing)])
        pygame.draw.circle(surf, (20, 20, 20), (x + self.w - 10, y + 8), 2)


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
        pygame.draw.circle(surf, SUN, (WIDTH - 110, 70), 34)
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
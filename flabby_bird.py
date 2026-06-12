"""
Flabby Bird — Multiplayer (1-4 players, shared course, last-one-standing)
Keys: P1=A, P2=F, P3=J, P4=; (flap)
Start screen: press 1-4 to choose number of players. R to restart after game over.
"""

import pygame
import random
import array
import math

# ---------- Config ----------
WIDTH, HEIGHT = 800, 600
FPS = 60

GRAVITY = 0.45
FLAP_IMPULSE = -8.0
BIRD_RADIUS = 14

PIPE_W = 70
PIPE_GAP = 170
PIPE_SPEED = 3.0
PIPE_INTERVAL = 1600        # ms between pipes
GAP_MARGIN = 80             # min distance of gap center from top/bottom

DEATH_FRAMES = 72           # blink-and-vanish duration

PLAYERS = [
    {"name": "Yellow", "color": (255, 210, 60),  "key": pygame.K_a,         "label": "A"},
    {"name": "Red",    "color": (235, 80, 80),   "key": pygame.K_f,         "label": "F"},
    {"name": "Green",  "color": (90, 200, 120),  "key": pygame.K_j,         "label": "J"},
    {"name": "Blue",   "color": (90, 150, 255),  "key": pygame.K_SEMICOLON, "label": ";"},
]
BIRD_X = [180, 220, 260, 300]   # staggered X per player

BG = (25, 28, 40)
PIPE_COLOR = (70, 170, 90)
PIPE_EDGE = (50, 130, 70)

# ---------- Procedural SFX ----------
def make_tone(freq, ms, volume=0.5, wave="sine"):
    rate = 22050
    n = int(rate * ms / 1000)
    buf = array.array("h")
    amp = int(32767 * volume)
    for i in range(n):
        t = i / rate
        fade = 1.0 - i / n  # linear fade-out
        if wave == "sine":
            v = math.sin(2 * math.pi * freq * t)
        else:  # square
            v = 1.0 if math.sin(2 * math.pi * freq * t) >= 0 else -1.0
        buf.append(int(amp * v * fade))
    return pygame.mixer.Sound(buffer=buf.tobytes())

# ---------- Bird ----------
class Bird:
    def __init__(self, idx):
        p = PLAYERS[idx]
        self.idx = idx
        self.name = p["name"]
        self.color = p["color"]
        self.key = p["key"]
        self.label = p["label"]
        self.x = BIRD_X[idx]
        self.y = HEIGHT // 2
        self.vy = 0.0
        self.alive = True
        self.death_timer = 0
        self.score = 0

    def flap(self):
        if self.alive:
            self.vy = FLAP_IMPULSE

    def update(self):
        if self.alive:
            self.vy += GRAVITY
            self.y += self.vy
        elif self.death_timer > 0:
            self.death_timer -= 1

    def kill(self):
        self.alive = False
        self.death_timer = DEATH_FRAMES

    def visible(self):
        if self.alive:
            return True
        # blink during death animation
        return self.death_timer > 0 and (self.death_timer // 4) % 2 == 0

    def draw(self, surf):
        if not self.visible():
            return
        pygame.draw.circle(surf, self.color, (int(self.x), int(self.y)), BIRD_RADIUS)
        # eye
        pygame.draw.circle(surf, (20, 20, 20), (int(self.x) + 5, int(self.y) - 4), 3)

# ---------- Pipe ----------
class Pipe:
    def __init__(self, x):
        self.x = x
        self.gap_y = random.randint(GAP_MARGIN + PIPE_GAP // 2,
                                    HEIGHT - GAP_MARGIN - PIPE_GAP // 2)
        self.scored = [False] * 4

    def update(self):
        self.x -= PIPE_SPEED

    def offscreen(self):
        return self.x + PIPE_W < 0

    def rects(self):
        top = pygame.Rect(self.x, 0, PIPE_W, self.gap_y - PIPE_GAP // 2)
        bot = pygame.Rect(self.x, self.gap_y + PIPE_GAP // 2,
                          PIPE_W, HEIGHT - (self.gap_y + PIPE_GAP // 2))
        return top, bot

    def draw(self, surf):
        for r in self.rects():
            pygame.draw.rect(surf, PIPE_COLOR, r)
            pygame.draw.rect(surf, PIPE_EDGE, r, 3)

# ---------- Game ----------
def main():
    pygame.mixer.pre_init(22050, -16, 1, 256)
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Flabby Bird — Multiplayer")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 32)
    bigfont = pygame.font.SysFont(None, 64)

    # one flap blip per player, rising pitch; one crash thud
    flap_snd = [make_tone(440 + 120 * i, 70, 0.35, "sine") for i in range(4)]
    crash_snd = make_tone(110, 220, 0.5, "square")

    state = "menu"          # menu -> playing -> gameover
    num_players = 0
    birds, pipes = [], []
    last_pipe = 0
    winner = None

    def start_game(n):
        nonlocal birds, pipes, last_pipe, state, num_players, winner
        num_players = n
        birds = [Bird(i) for i in range(n)]
        pipes = []
        last_pipe = pygame.time.get_ticks()
        winner = None
        state = "playing"

    running = True
    while running:
        clock.tick(FPS)
        now = pygame.time.get_ticks()

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if state == "menu":
                    if ev.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                        start_game(ev.key - pygame.K_0)
                elif state == "playing":
                    for b in birds:
                        if ev.key == b.key and b.alive:
                            b.flap()
                            flap_snd[b.idx].play()
                elif state == "gameover":
                    if ev.key == pygame.K_r:
                        state = "menu"

        if state == "playing":
            # spawn pipes
            if now - last_pipe >= PIPE_INTERVAL:
                pipes.append(Pipe(WIDTH))
                last_pipe = now

            for p in pipes:
                p.update()
            pipes = [p for p in pipes if not p.offscreen()]

            for b in birds:
                b.update()
                if not b.alive:
                    continue
                # bounds
                if b.y - BIRD_RADIUS < 0 or b.y + BIRD_RADIUS > HEIGHT:
                    b.kill()
                    crash_snd.play()
                    continue
                # pipes
                brect = pygame.Rect(b.x - BIRD_RADIUS, b.y - BIRD_RADIUS,
                                    BIRD_RADIUS * 2, BIRD_RADIUS * 2)
                for p in pipes:
                    top, bot = p.rects()
                    if brect.colliderect(top) or brect.colliderect(bot):
                        b.kill()
                        crash_snd.play()
                        break
                    if not p.scored[b.idx] and p.x + PIPE_W < b.x:
                        p.scored[b.idx] = True
                        b.score += 1

            # win check (last one standing; solo play = survive as long as you can)
            alive = [b for b in birds if b.alive]
            if num_players > 1 and len(alive) == 1:
                winner = alive[0]
                state = "gameover"
            elif len(alive) == 0:
                winner = None  # draw / solo death
                state = "gameover"

        # ---------- Draw ----------
        screen.fill(BG)

        if state == "menu":
            title = bigfont.render("FLABBY BIRD", True, (255, 255, 255))
            screen.blit(title, title.get_rect(center=(WIDTH // 2, 160)))
            sub = font.render("Press 1-4 to choose number of players", True, (200, 200, 200))
            screen.blit(sub, sub.get_rect(center=(WIDTH // 2, 260)))
            for i, p in enumerate(PLAYERS):
                t = font.render(f"P{i+1} {p['name']}: flap with [{p['label']}]", True, p["color"])
                screen.blit(t, t.get_rect(center=(WIDTH // 2, 330 + i * 40)))
        else:
            for p in pipes:
                p.draw(screen)
            for b in birds:
                b.draw(screen)
            # HUD
            for i, b in enumerate(birds):
                status = str(b.score) if b.alive else "X"
                t = font.render(f"{b.name}: {status}", True, b.color)
                screen.blit(t, (15, 12 + i * 30))

            if state == "gameover":
                if winner:
                    msg = bigfont.render(f"{winner.name} WINS!", True, winner.color)
                else:
                    msg = bigfont.render("GAME OVER", True, (255, 255, 255))
                screen.blit(msg, msg.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 30)))
                sub = font.render("Press R to return to menu", True, (200, 200, 200))
                screen.blit(sub, sub.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 30)))

        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    main()
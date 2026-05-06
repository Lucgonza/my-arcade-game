import pygame
import math
import sys
import random

WIDTH, HEIGHT = 800, 600
FPS = 60
G = 500
BALL_RADIUS = 6
MIN_GAP = 40
MAX_DRAG = 150
BOUNCE_DAMPING = 0.55
MIN_SPEED = 40
SCROLL_SPEED = 350
INITIAL_START_X = 120
USABLE_WIDTH = WIDTH - INITIAL_START_X  # 680px of playable space after start

BLACK  = (0, 0, 0)
WHITE  = (255, 255, 255)
YELLOW = (255, 215, 0)
GREEN  = (0, 200, 0)

OBSTACLE_COLORS = [
    (150, 150, 150),
    (150, 80,  200),
    (80,  200, 150),
    (200, 150, 80),
]

STATE_PLAYING   = "playing"
STATE_SCROLLING = "scrolling"

def make_planet(pos, radius, color):
    return {"pos": list(pos), "radius": radius,
            "mass": radius ** 2 * 2, "color": color}

def overlaps(p1, p2):
    return math.hypot(p1["pos"][0] - p2["pos"][0],
                      p1["pos"][1] - p2["pos"][1]) < p1["radius"] + p2["radius"] + MIN_GAP

def generate_level(start_planet):
    planets = [start_planet]
    colors  = OBSTACLE_COLORS[:]
    random.shuffle(colors)
    base_x  = start_planet["pos"][0]

    for i in range(random.randint(1, 4)):
        for _ in range(200):
            r = random.randint(35, 80)
            x = base_x + random.randint(100, USABLE_WIDTH - r - 20)
            y = random.randint(r + 20, HEIGHT - r - 20)
            c = make_planet((x, y), r, colors[i % len(colors)])
            if not any(overlaps(c, p) for p in planets):
                planets.append(c); break

    for _ in range(500):
        r = 25
        x = base_x + random.randint(USABLE_WIDTH // 2, USABLE_WIDTH - r - 20)
        y = random.randint(r + 20, HEIGHT - r - 20)
        c = make_planet((x, y), r, (220, 80, 80))
        if not any(overlaps(c, p) for p in planets):
            planets.append(c); break

    return planets

def initial_planets():
    start  = make_planet((INITIAL_START_X, 480), 25, (100, 149, 237))
    obs1   = make_planet((330, 280), 50, (150, 150, 150))
    obs2   = make_planet((560, 400), 70, (150, 80,  200))
    target = make_planet((680, 120), 25, (220, 80,  80))
    return [start, obs1, obs2, target]


class Ball:
    def __init__(self, planets):
        self.pos = [float(planets[0]["pos"][0]), float(planets[0]["pos"][1])]
        self.vel = [0.0, 0.0]
        self.launched = False
        self.current_planet = 0
        self.surface_angle  = -math.pi / 2
        self._snap(planets[0])

    def _snap(self, planet):
        r = planet["radius"] + BALL_RADIUS
        self.pos = [planet["pos"][0] + r * math.cos(self.surface_angle),
                    planet["pos"][1] + r * math.sin(self.surface_angle)]

    def land_on(self, planets, idx):
        self.launched = False
        self.vel = [0.0, 0.0]
        self.current_planet = idx
        p = planets[idx]
        dx = self.pos[0] - p["pos"][0]
        dy = self.pos[1] - p["pos"][1]
        self.surface_angle = math.atan2(dy, dx) if (dx or dy) else -math.pi / 2
        self._snap(p)

    def go_to_start(self, planets):
        self.surface_angle  = -math.pi / 2
        self.current_planet = 0
        self.launched = False
        self.vel = [0.0, 0.0]
        self._snap(planets[0])

    def place_on_new_start(self, planet, angle):
        self.launched = False
        self.vel = [0.0, 0.0]
        self.current_planet = 0
        self.surface_angle  = angle
        self._snap(planet)

    def launch(self, direction, power):
        speed = (power / MAX_DRAG) * 400
        self.vel = [direction[0] * speed, direction[1] * speed]
        self.launched = True

    def update(self, dt, planets, camera_x):
        if not self.launched:
            return
        for p in planets:
            sx = p["pos"][0] - camera_x
            if sx + p["radius"] < 0:   # fully off left — skip gravity
                continue
            dx = p["pos"][0] - self.pos[0]
            dy = p["pos"][1] - self.pos[1]
            dist = math.hypot(dx, dy)
            if dist < 1: continue
            f = G * p["mass"] / (dist * dist)
            self.vel[0] += f * (dx / dist) * dt
            self.vel[1] += f * (dy / dist) * dt
        self.pos[0] += self.vel[0] * dt
        self.pos[1] += self.vel[1] * dt

    def check_collision(self, planets):
        for i, p in enumerate(planets):
            if math.hypot(self.pos[0] - p["pos"][0],
                          self.pos[1] - p["pos"][1]) <= p["radius"] + BALL_RADIUS:
                return i
        return None

    def out_of_bounds(self, camera_x):
        sx = self.pos[0] - camera_x
        return sx < -100 or sx > WIDTH + 100 or self.pos[1] < -100 or self.pos[1] > HEIGHT + 100

    def screen_pos(self, camera_x):
        return (int(self.pos[0] - camera_x), int(self.pos[1]))

    def is_clicked(self, mouse_pos, camera_x):
        sp = self.screen_pos(camera_x)
        return math.hypot(mouse_pos[0] - sp[0], mouse_pos[1] - sp[1]) <= BALL_RADIUS + 10

    def draw(self, screen, camera_x):
        pygame.draw.circle(screen, YELLOW, self.screen_pos(camera_x), BALL_RADIUS)


def draw_flag(screen, planet, camera_x):
    cx = int(planet["pos"][0] - camera_x)
    cy = int(planet["pos"][1])
    r  = planet["radius"]
    pole_bottom = cy - r
    pole_top    = cy - r - 28
    pygame.draw.line(screen, WHITE, (cx, pole_bottom), (cx, pole_top), 2)
    pygame.draw.polygon(screen, (220, 80, 80), [
        (cx,      pole_top),
        (cx + 14, pole_top + 7),
        (cx,      pole_top + 14),
    ])

def draw_arrow(screen, ball_sp, mouse_pos):
    dx = mouse_pos[0] - ball_sp[0]
    dy = mouse_pos[1] - ball_sp[1]
    dist = math.hypot(dx, dy)
    if dist < 5: return

    ratio = min(dist, MAX_DRAG) / MAX_DRAG
    ex = ball_sp[0] + (dx / dist) * min(dist, MAX_DRAG)
    ey = ball_sp[1] + (dy / dist) * min(dist, MAX_DRAG)
    color = (int(255 * ratio), int(255 * (1 - ratio)), 0)

    pygame.draw.line(screen, color, ball_sp, (int(ex), int(ey)), 2)
    angle = math.atan2(dy, dx)
    for sign in (-1, 1):
        ax = ex - 12 * math.cos(angle + sign * 0.4)
        ay = ey - 12 * math.sin(angle + sign * 0.4)
    pygame.draw.polygon(screen, color, [
        (int(ex), int(ey)),
        (int(ex - 12 * math.cos(angle - 0.4)), int(ey - 12 * math.sin(angle - 0.4))),
        (int(ex - 12 * math.cos(angle + 0.4)), int(ey - 12 * math.sin(angle + 0.4))),
    ])

    bx, by, bw, bh = 20, HEIGHT - 40, 200, 20
    pygame.draw.rect(screen, WHITE, (bx, by, bw, bh), 2)
    bar_color = GREEN if ratio < 0.7 else (255, 165, 0) if ratio < 0.9 else (220, 80, 80)
    pygame.draw.rect(screen, bar_color, (bx, by, int(ratio * bw), bh))


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Space Golf")
    clock = pygame.time.Clock()
    font  = pygame.font.SysFont(None, 36)
    small = pygame.font.SysFont(None, 24)

    planets       = initial_planets()
    ball          = Ball(planets)
    camera_x      = 0.0
    scroll_target = 0.0
    state         = STATE_PLAYING
    dragging      = False
    mouse_pos     = (0, 0)
    shots         = 0
    level         = 1
    message       = ""
    msg_timer     = 0.0

    while True:
        dt         = clock.tick(FPS) / 1000.0
        target_idx = len(planets) - 1

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                planets       = initial_planets()
                ball          = Ball(planets)
                camera_x      = 0.0; scroll_target = 0.0
                state         = STATE_PLAYING; dragging = False
                shots         = 0;   level = 1; message = ""

            if state == STATE_PLAYING:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if not ball.launched and ball.is_clicked(event.pos, camera_x):
                        dragging  = True
                        mouse_pos = event.pos
                if event.type == pygame.MOUSEMOTION and dragging:
                    mouse_pos = event.pos
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if dragging and not ball.launched:
                        sp   = ball.screen_pos(camera_x)
                        dx   = mouse_pos[0] - sp[0]
                        dy   = mouse_pos[1] - sp[1]
                        dist = math.hypot(dx, dy)
                        if dist > 5:
                            ball.launch((dx / dist, dy / dist), min(dist, MAX_DRAG))
                            shots += 1
                    dragging = False

        # --- Update ---
        if state == STATE_SCROLLING:
            camera_x = min(camera_x + SCROLL_SPEED * dt, scroll_target)
            if camera_x >= scroll_target:
                state = STATE_PLAYING

        elif state == STATE_PLAYING:
            ball.update(dt, planets, camera_x)

            if ball.launched:
                hit = ball.check_collision(planets)
                if hit is not None:
                    p  = planets[hit]
                    nx = ball.pos[0] - p["pos"][0]
                    ny = ball.pos[1] - p["pos"][1]
                    ln = math.hypot(nx, ny)
                    nx /= ln; ny /= ln

                    ball.pos[0] = p["pos"][0] + nx * (p["radius"] + BALL_RADIUS)
                    ball.pos[1] = p["pos"][1] + ny * (p["radius"] + BALL_RADIUS)

                    dot = ball.vel[0] * nx + ball.vel[1] * ny
                    ball.vel[0] = (ball.vel[0] - 2 * dot * nx) * BOUNCE_DAMPING
                    ball.vel[1] = (ball.vel[1] - 2 * dot * ny) * BOUNCE_DAMPING

                    if math.hypot(ball.vel[0], ball.vel[1]) < MIN_SPEED:
                        landing_angle = math.atan2(ny, nx)
                        if hit == target_idx:
                            level    += 1
                            new_start = make_planet(planets[target_idx]["pos"], 25, (100, 149, 237))
                            planets   = generate_level(new_start)
                            ball.place_on_new_start(new_start, landing_angle)
                            scroll_target = new_start["pos"][0] - INITIAL_START_X
                            state     = STATE_SCROLLING
                            message   = f"Level {level}!  Shots: {shots}"
                            msg_timer = 3.0
                        else:
                            ball.land_on(planets, hit)
                            message   = f"Landed on planet {hit + 1}"
                            msg_timer = 1.0

                elif ball.out_of_bounds(camera_x):
                    ball.go_to_start(planets)
                    message   = "Out of bounds — back to start!"
                    msg_timer = 1.5

            if msg_timer > 0:
                msg_timer -= dt

        # --- Draw ---
        screen.fill(BLACK)

        for i, p in enumerate(planets):
            sx = int(p["pos"][0] - camera_x)
            sy = int(p["pos"][1])
            if sx + p["radius"] < 0:        # fully off left — skip
                continue
            if sx - p["radius"] > WIDTH:    # fully off right — skip
                continue
            pygame.draw.circle(screen, p["color"], (sx, sy), p["radius"])
            if i == target_idx or i == 0:
                pygame.draw.circle(screen, WHITE, (sx, sy), p["radius"], 2)
            if i == target_idx:
                draw_flag(screen, p, camera_x)

        ball.draw(screen, camera_x)

        if state == STATE_PLAYING and not ball.launched and not dragging:
            hint = small.render("Click ball and drag to aim — release to shoot | R: restart", True, WHITE)
            screen.blit(hint, (20, HEIGHT - 65))

        if state == STATE_PLAYING and dragging and not ball.launched:
            draw_arrow(screen, ball.screen_pos(camera_x), mouse_pos)

        screen.blit(font.render(f"Level: {level}  Shots: {shots}", True, WHITE), (10, 10))

        if message and msg_timer > 0:
            msg = font.render(message, True, YELLOW)
            screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2))

        pygame.display.flip()

if __name__ == "__main__":
    main()
import pygame
import math
import sys
import random

WIDTH, HEIGHT = 800, 600
FPS = 60
G = 500
BALL_RADIUS = 6
MIN_GAP = 40

BLACK  = (0, 0, 0)
WHITE  = (255, 255, 255)
GREEN  = (0, 200, 0)
YELLOW = (255, 215, 0)

OBSTACLE_COLORS = [
    (150, 150, 150),
    (150, 80,  200),
    (80,  200, 150),
    (200, 150, 80),
]

def make_planet(pos, radius, color):
    return {"pos": list(pos), "radius": radius,
            "mass": radius ** 2 * 2, "color": color}

def overlaps(p1, p2):
    dx = p1["pos"][0] - p2["pos"][0]
    dy = p1["pos"][1] - p2["pos"][1]
    return math.hypot(dx, dy) < p1["radius"] + p2["radius"] + MIN_GAP

def generate_level(start_planet):
    planets = [start_planet]
    colors = OBSTACLE_COLORS[:]
    random.shuffle(colors)

    for i in range(random.randint(1, 4)):
        for _ in range(200):
            r = random.randint(35, 80)
            x = random.randint(r + 20, WIDTH  - r - 20)
            y = random.randint(r + 20, HEIGHT - r - 20)
            c = make_planet((x, y), r, colors[i % len(colors)])
            if not any(overlaps(c, p) for p in planets):
                planets.append(c)
                break

    for _ in range(500):
        r = 25
        x = random.randint(r + 20, WIDTH  - r - 20)
        y = random.randint(r + 20, HEIGHT - r - 20)
        c = make_planet((x, y), r, (220, 80, 80))
        if not any(overlaps(c, p) for p in planets):
            planets.append(c)
            break

    return planets

def initial_planets():
    start = make_planet((120, 480), 25, (100, 149, 237))
    obs1  = make_planet((330, 280), 50, (150, 150, 150))
    obs2  = make_planet((560, 400), 70, (150, 80,  200))
    target= make_planet((680, 120), 25, (220, 80,  80))
    return [start, obs1, obs2, target]

class Ball:
    def __init__(self, planets):
        self.current_planet = 0
        self.land_on(planets, 0)

    def land_on(self, planets, idx):
        self.launched = False
        self.vel = [0.0, 0.0]
        self.current_planet = idx
        p = planets[idx]
        dx = self.pos[0] - p["pos"][0] if hasattr(self, "pos") else 0
        dy = self.pos[1] - p["pos"][1] if hasattr(self, "pos") else -1
        self.surface_angle = math.atan2(dy, dx) if (dx or dy) else -math.pi / 2
        r = p["radius"] + BALL_RADIUS
        self.pos = [p["pos"][0] + r * math.cos(self.surface_angle),
                    p["pos"][1] + r * math.sin(self.surface_angle)]

    def go_to_start(self, planets):
        self.pos = [0.0, 0.0]
        self.land_on(planets, 0)

    def launch(self, direction, power):
        angle = self.surface_angle + direction * math.pi / 4
        speed = power * 4
        self.vel = [speed * math.cos(angle), speed * math.sin(angle)]
        self.launched = True

    def update(self, dt, planets):
        if not self.launched:
            return
        for p in planets:
            dx = p["pos"][0] - self.pos[0]
            dy = p["pos"][1] - self.pos[1]
            dist = math.hypot(dx, dy)
            if dist < 1:
                continue
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

    def out_of_bounds(self):
        return (self.pos[0] < -100 or self.pos[0] > WIDTH  + 100 or
                self.pos[1] < -100 or self.pos[1] > HEIGHT + 100)

    def draw(self, screen):
        pygame.draw.circle(screen, YELLOW,
                           (int(self.pos[0]), int(self.pos[1])), BALL_RADIUS)

def draw_power_bar(screen, power):
    bx, by, bw, bh = 20, HEIGHT - 40, 200, 20
    pygame.draw.rect(screen, WHITE, (bx, by, bw, bh), 2)
    fill  = int(power / 100 * bw)
    color = GREEN if power < 70 else (255, 165, 0) if power < 90 else (220, 80, 80)
    pygame.draw.rect(screen, color, (bx, by, fill, bh))

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Space Golf")
    clock  = pygame.time.Clock()
    font   = pygame.font.SysFont(None, 36)
    small  = pygame.font.SysFont(None, 24)

    planets = initial_planets()
    ball    = Ball(planets)
    power   = 0.0
    charging= False
    shots   = 0
    level   = 1
    message = ""
    msg_timer = 0.0

    while True:
        dt = clock.tick(FPS) / 1000.0
        target_idx = len(planets) - 1

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE and not ball.launched:
                    charging = True
                if event.key == pygame.K_r:
                    planets = initial_planets()
                    ball = Ball(planets)
                    power = 0.0; charging = False
                    shots = 0;   level = 1; message = ""
            if event.type == pygame.KEYUP:
                if event.key == pygame.K_SPACE:
                    charging = False
                if not ball.launched and power > 0:
                    if event.key == pygame.K_LEFT:
                        ball.launch(-1, power); shots += 1; power = 0.0
                    elif event.key == pygame.K_RIGHT:
                        ball.launch( 1, power); shots += 1; power = 0.0

        if charging and not ball.launched:
            power = min(100.0, power + 60 * dt)

        ball.update(dt, planets)

        if ball.launched:
            hit = ball.check_collision(planets)
            if hit == target_idx:
                level += 1
                new_start = make_planet(planets[target_idx]["pos"],
                                        25, (100, 149, 237))
                planets = generate_level(new_start)
                ball.pos = list(new_start["pos"])
                ball.land_on(planets, 0)
                message = f"Level {level}!  Total shots: {shots}"
                msg_timer = 3.0
            elif hit is not None:
                ball.land_on(planets, hit)
                message = f"Landed on planet {hit + 1}"
                msg_timer = 1.0
            elif ball.out_of_bounds():
                ball.go_to_start(planets)
                message = "Out of bounds — back to start!"
                msg_timer = 1.5

        if msg_timer > 0:
            msg_timer -= dt

        screen.fill(BLACK)
        for i, p in enumerate(planets):
            pygame.draw.circle(screen, p["color"], p["pos"], p["radius"])
            if i == target_idx:
                pygame.draw.circle(screen, WHITE, p["pos"], p["radius"], 2)
            if i == 0:
                pygame.draw.circle(screen, WHITE, p["pos"], p["radius"], 2)

        ball.draw(screen)

        if not ball.launched:
            draw_power_bar(screen, power)
            hint = small.render("SPACE: charge | LEFT/RIGHT: launch | R: restart", True, WHITE)
            screen.blit(hint, (20, HEIGHT - 65))

        screen.blit(font.render(f"Level: {level}  Shots: {shots}", True, WHITE), (10, 10))

        if message and msg_timer > 0:
            msg = font.render(message, True, YELLOW)
            screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2))

        pygame.display.flip()

if __name__ == "__main__":
    main()
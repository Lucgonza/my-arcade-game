import pygame
import math
import sys

WIDTH, HEIGHT = 800, 600
FPS = 60
G = 500

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
BLUE = (100, 149, 237)
RED = (220, 80, 80)
YELLOW = (255, 215, 0)
GREEN = (0, 200, 0)

planets = [
    {"pos": [200, 400], "radius": 50, "mass": 3000, "color": BLUE},
    {"pos": [600, 200], "radius": 50, "mass": 3000, "color": RED},
]

START_PLANET = 0
TARGET_PLANET = 1

class Ball:
    def __init__(self):
        self.reset()

    def reset(self):
        self.launched = False
        self.vel = [0.0, 0.0]
        self.place_on_planet()

    def place_on_planet(self):
        p = planets[START_PLANET]
        self.surface_angle = -math.pi / 2
        r = p["radius"] + 8
        self.pos = [
            p["pos"][0] + r * math.cos(self.surface_angle),
            p["pos"][1] + r * math.sin(self.surface_angle)
        ]

    def launch(self, direction, power):
        angle = self.surface_angle + direction * math.pi / 4
        speed = power * 4
        self.vel = [speed * math.cos(angle), speed * math.sin(angle)]
        self.launched = True

    def update(self, dt):
        if not self.launched:
            return
        for planet in planets:
            dx = planet["pos"][0] - self.pos[0]
            dy = planet["pos"][1] - self.pos[1]
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < 1:
                continue
            force = G * planet["mass"] / (dist * dist)
            self.vel[0] += force * (dx / dist) * dt
            self.vel[1] += force * (dy / dist) * dt
        self.pos[0] += self.vel[0] * dt
        self.pos[1] += self.vel[1] * dt

    def check_collision(self):
        for i, planet in enumerate(planets):
            dx = self.pos[0] - planet["pos"][0]
            dy = self.pos[1] - planet["pos"][1]
            if math.sqrt(dx * dx + dy * dy) <= planet["radius"] + 8:
                return i
        return None

    def draw(self, screen):
        pygame.draw.circle(screen, YELLOW, (int(self.pos[0]), int(self.pos[1])), 8)


def draw_power_bar(screen, power):
    bx, by, bw, bh = 20, HEIGHT - 40, 200, 20
    pygame.draw.rect(screen, WHITE, (bx, by, bw, bh), 2)
    fill = int(power / 100 * bw)
    color = GREEN if power < 70 else (255, 165, 0) if power < 90 else RED
    pygame.draw.rect(screen, color, (bx, by, fill, bh))


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Space Golf")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 36)
    small_font = pygame.font.SysFont(None, 24)

    ball = Ball()
    power = 0.0
    charging = False
    shots = 0
    message = ""
    message_timer = 0.0

    while True:
        dt = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE and not ball.launched:
                    charging = True
                if event.key == pygame.K_r:
                    ball.reset()
                    power = 0.0
                    charging = False
                    shots = 0
                    message = ""
            if event.type == pygame.KEYUP:
                if event.key == pygame.K_SPACE:
                    charging = False
                if not ball.launched:
                    if event.key == pygame.K_LEFT and power > 0:
                        ball.launch(-1, power)
                        shots += 1
                        power = 0.0
                    elif event.key == pygame.K_RIGHT and power > 0:
                        ball.launch(1, power)
                        shots += 1
                        power = 0.0

        if charging and not ball.launched:
            power = min(100.0, power + 60 * dt)

        ball.update(dt)

        if ball.launched:
            hit = ball.check_collision()
            if hit == TARGET_PLANET:
                message = f"HOLE IN {shots}!"
                message_timer = 3.0
                ball.reset()
                shots = 0
            elif hit == START_PLANET:
                ball.reset()
                message = "Try again!"
                message_timer = 1.5
            elif (ball.pos[0] < -100 or ball.pos[0] > WIDTH + 100 or
                  ball.pos[1] < -100 or ball.pos[1] > HEIGHT + 100):
                ball.reset()
                message = "Out of bounds!"
                message_timer = 1.5

        if message_timer > 0:
            message_timer -= dt

        screen.fill(BLACK)

        for i, planet in enumerate(planets):
            pygame.draw.circle(screen, planet["color"], planet["pos"], planet["radius"])
            if i == TARGET_PLANET:
                pygame.draw.circle(screen, WHITE, planet["pos"], planet["radius"], 2)

        ball.draw(screen)

        if not ball.launched:
            draw_power_bar(screen, power)
            hint = small_font.render("SPACE: charge power | LEFT / RIGHT: launch", True, WHITE)
            screen.blit(hint, (20, HEIGHT - 65))

        shots_text = font.render(f"Shots: {shots}", True, WHITE)
        screen.blit(shots_text, (WIDTH - 150, 20))

        if message and message_timer > 0:
            msg = font.render(message, True, YELLOW)
            screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2))

        pygame.display.flip()

if __name__ == "__main__":
    main()
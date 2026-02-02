import paho.mqtt.client as mqtt
import json
import time
import threading
import random
import uuid
import sys
import pygame 

# ==========================================
#              CONFIGURATION
# ==========================================
# 1. Network Settings
BROKER = "127.0.0.1"
PORT = 1883
USERNAME = "dc25"
PASSWORD = "kmitl-dc25"

# 2. Pond Settings
MY_POND_NAME = "GroupA_Pond"
MAX_FISH = 10                  # The limit of fish in your pond
SPAWN_RATE = 2.0               # Seconds between new fish
TARGET_POND_TOPIC = "fishhaven/Biggy_Pond/in" 
MY_INBOX_TOPIC = f"fishhaven/{MY_POND_NAME}/in"

# 3. GUI Settings
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60
BG_COLOR = (20, 40, 60)      
FISH_COLOR = (255, 165, 0)   
TEXT_COLOR = (255, 255, 255)

# ==========================================
#               FISH CLASS
# ==========================================
class Fish:
    def __init__(self, origin, life=60.0, name=None, visual_type=1):
        self.id = name if name else str(uuid.uuid4())[:8]
        self.origin = origin
        self.life = float(life)
        self.visual_type = visual_type 
        self.posture_frame = 0 
        self.status = "SWIMMING"
        
        # --- FIX 1: IMMUNITY TIMER ---
        # Record when the fish entered/spawned. 
        # It cannot be kicked out until it has been here for X seconds.
        self.arrival_time = time.time()

        # Movement Properties
        self.x = random.randint(50, SCREEN_WIDTH - 50)
        self.vx = random.choice([-2, -1, 1, 2])
        self.y = random.randint(50, SCREEN_HEIGHT - 50)
        self.vy = random.choice([-2, -1, 1, 2])
        self.anim_timer = 0

    def age(self, dt):
        if self.status == "SWIMMING":
            self.life -= dt

    def move(self):
        """Handle movement and bouncing off walls"""
        if self.status == "SWIMMING":
            self.x += self.vx
            self.y += self.vy

            # Bounce off walls
            if self.x < 20 or self.x > SCREEN_WIDTH - 20:
                self.vx *= -1
            if self.y < 20 or self.y > SCREEN_HEIGHT - 20:
                self.vy *= -1

    def animate(self):
        self.anim_timer += 1
        if self.anim_timer > 10:
            self.posture_frame = (self.posture_frame + 1) % 4
            self.anim_timer = 0

    def draw(self, screen, font):
        if self.status == "MIGRATING":
            color = (100, 100, 100) # Grey indicates waiting for network
            label = "MIGRATING..."
        else:
            color = FISH_COLOR
            # Visual debug: Show immunity status
            if time.time() - self.arrival_time < 5.0:
                label = f"{int(self.life)}s (Immune)"
            else:
                label = f"{int(self.life)}s | {self.origin}"

        # Draw Body
        pygame.draw.ellipse(screen, color, (self.x, self.y, 40, 20))

        # Draw Tail
        tail_offset_y = 0
        if self.posture_frame == 1: tail_offset_y = -5
        elif self.posture_frame == 3: tail_offset_y = 5

        tail_points = [
            (self.x, self.y + 10),
            (self.x - 10, self.y + 5 + tail_offset_y),
            (self.x - 10, self.y + 15 + tail_offset_y)
        ]
        pygame.draw.polygon(screen, color, tail_points)

        # Draw Info Text
        text_surf = font.render(label, True, TEXT_COLOR)
        screen.blit(text_surf, (self.x - 10, self.y - 15))

    def to_json(self):
        return json.dumps({
            "name": self.id,
            "origin": self.origin,
            "life": self.life,
            "type": self.visual_type
        })

# ==========================================
#            POND APPLICATION
# ==========================================
class PondApp:
    def __init__(self):
        self.fishes = []
        self.running = True
        self.pending_migrations = {} 

        self.client = mqtt.Client()
        if USERNAME and PASSWORD:
            self.client.username_pw_set(USERNAME, PASSWORD)
        
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_publish = self.on_publish 

    # --- NETWORK CALLBACKS ---
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f" [Net] Connected! Listening on {MY_INBOX_TOPIC}")
            client.subscribe(MY_INBOX_TOPIC)
        else:
            print(f" [Net] Connection Failed: {rc}")

    def on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode()
            data = json.loads(payload)
            
            # --- FIX 3: PREVENT SELF-MESSAGING ---
            # If I accidentally sent a fish to myself, ignore it.
            if data.get("origin") == MY_POND_NAME:
                return 

            new_fish = Fish(
                origin=data["origin"], 
                life=data["life"], 
                name=data["name"]
            )
            self.fishes.append(new_fish)
            print(f" -> SPLASH! Fish {new_fish.id} arrived!")
        except Exception as e:
            print(f" [Err] Corrupt fish: {e}")

    def on_publish(self, client, userdata, mid):
        """Called when Broker confirms receipt (QoS 1)."""
        if mid in self.pending_migrations:
            fish = self.pending_migrations[mid]
            print(f" [Net] Fish {fish.id} successfully migrated.")
            if fish in self.fishes:
                self.fishes.remove(fish)
            del self.pending_migrations[mid]

    def attempt_migration(self, fish):
        if fish.status == "MIGRATING": return

        # --- FIX 1 (LOGIC): CHECK IMMUNITY ---
        # If fish arrived less than 5 seconds ago, it is too tired to move.
        if time.time() - fish.arrival_time < 5.0:
            return 

        print(f" <- Fish {fish.id} waiting to migrate...")
        fish.status = "MIGRATING"
        
        msg_info = self.client.publish(TARGET_POND_TOPIC, fish.to_json(), qos=1)
        if msg_info.rc == mqtt.MQTT_ERR_SUCCESS:
            self.pending_migrations[msg_info.mid] = fish
        else:
            fish.status = "SWIMMING" 

    # --- MAIN LOOP ---
    def start(self):
        # 1. Start Network
        try:
            self.client.connect(BROKER, PORT, 60) 
            self.client.loop_start() 
        except Exception as e:
            print(f"CRITICAL ERROR: {e}")
            return

        # 2. Init GUI
        pygame.init()
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(f"{MY_POND_NAME} - Fish Haven")
        clock = pygame.time.Clock()
        font = pygame.font.SysFont("Arial", 12)
        header_font = pygame.font.SysFont("Arial", 20)

        spawn_timer = 0
        
        # 3. Game Loop
        try:
            while self.running:
                dt = clock.tick(FPS) / 1000.0 
                spawn_timer += dt

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False

                # --- SPAWNING LOGIC ---
                if spawn_timer > SPAWN_RATE:
                    if len(self.fishes) < MAX_FISH:
                        self.fishes.append(Fish(origin=MY_POND_NAME))
                        spawn_timer = 0
                    else:
                        spawn_timer = SPAWN_RATE + 0.1

                # --- FISH UPDATES ---
                # FIX 2: Single-File Migration Flag
                # Ensures we don't dump 10 fish into the network in 1 frame
                crowd_migration_triggered = False 

                for fish in self.fishes[:]:
                    if fish.life <= 0:
                        self.fishes.remove(fish)
                        continue
                    
                    if fish.status == "SWIMMING":
                        fish.age(dt)
                        fish.move()
                        fish.animate()

                        # --- MIGRATION LOGIC ---
                        # 1. Random Chance (Independent)
                        if random.random() < 0.05 * dt:
                            self.attempt_migration(fish)
                        
                        # 2. Crowd Control (Hysteresis)
                        # Only allow migration if (A) We are over limit AND (B) No one else left this frame
                        elif len(self.fishes) > MAX_FISH and not crowd_migration_triggered:
                            self.attempt_migration(fish)
                            # If this fish successfully started migration process (passed immunity check),
                            # set the flag so no one else leaves this frame.
                            if fish.status == "MIGRATING":
                                crowd_migration_triggered = True

                # --- DRAWING ---
                screen.fill(BG_COLOR)

                for fish in self.fishes:
                    fish.draw(screen, font)

                # Update Dashboard
                stats = f"Fish: {len(self.fishes)}/{MAX_FISH} | Broker: {BROKER}"
                screen.blit(header_font.render(stats, True, (255, 255, 255)), (10, 10))

                pygame.display.flip()

        except KeyboardInterrupt:
            pass
        finally:
            print("Shutting down...")
            self.client.loop_stop()
            pygame.quit()
            sys.exit()

if __name__ == "__main__":
    app = PondApp()
    app.start()
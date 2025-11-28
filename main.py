import os
import random
import argparse
import statistics as stats
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Tuple

import pygame
from sprite_manager import SpriteManager

class Action(Enum):
    NONE = 0        # No hacer nada (acción neutra)
    JUMP = auto()   # Saltar
    DUCK = auto()   # Agacharse
    STAND = auto()  # Levantarse desde estado agachado


class ObstacleKind(Enum):
    LOW = "low"     # Obstáculo en el suelo (cactus)
    MID = "mid"     # Obstáculo volador alto (no requiere salto)
    HIGH = "high"   # Obstáculo volador bajo (requiere agacharse)


class PlayerState(Enum):
    RUN = auto()    # Corriendo en el suelo
    JUMP = auto()   # En el aire
    DUCK = auto()   # Agachado


@dataclass
class Config:
    # Parametros de simulacion, fisica y discretizacion para DP.
    
    # Parámetros visuales y del entorno
    width: int = 960        # Ancho de la ventana del juego en píxeles.
    height: int = 360       # Alto de la ventana del juego en píxeles.
    player_x: int = 120     # Posición horizontal fija del jugador (el mundo se mueve, no el jugador).
    ground_y: int = 300     # Coordenada vertical del suelo; define dónde el jugador "pisa".

    # Física del jugador
    gravity: float = 2400.0        # Aceleración vertical aplicada al jugador (px/s^2); controla la caída.
    jump_velocity: float = -1050.0 # Velocidad inicial del salto (negativa porque hacia arriba en el eje Y).
    player_width: int = 52         # Ancho del hitbox del jugador.
    run_height: int = 70           # Altura del jugador cuando está corriendo/normal.
    duck_height: int = 40          # Altura del jugador cuando está agachado.

    # Velocidad y dificultad progresiva
    base_speed: float = 280.0     # Velocidad inicial del desplazamiento del escenario (px/s).
    speed_growth: float = 24.0    # Tasa a la que aumenta la velocidad del juego con el tiempo.
    min_difficulty: float = 0.35  # Dificultad mínima inicial; afecta la frecuencia y tipo de obstáculos.
    ramp_time: float = 35.0       # Tiempo (s) que tarda la dificultad en aumentar linealmente hasta 1.0.
    warmup_time: float = 1.6      # Período inicial sin obstáculos para permitir un arranque limpio.

    # Generación de obstáculos
    short_gap: int = 190        # Distancia base corta entre spawns de obstáculos (antes de aplicar aleatoriedad).
    long_gap: int = 320         # Distancia base larga para intervalos más amplios entre obstáculos.
    obstacle_max: int = 3       # Máximo de obstáculos simultáneos permitidos en pantalla.
    spawn_delay_scale: float = 1.25  # Factor >1 alarga la distancia/tiempo entre spawns (1.0 = default).

    # Parámetros del agente DP
    dp_dt: float = 0.05          # Paso temporal usado en la simulación interna del DP (más pequeño y rápido que el dt real).
    dp_depth: int = 12           # Profundidad máxima del árbol de búsqueda recursivo para el backup Bellman.
    rollout_steps: int = 2       # Cantidad de pasos simulados antes de evaluar el futuro (pre–lookahead).
    gamma: float = 0.98          # Factor de descuento para recompensas futuras en el backup Bellman.
    reward_alive: float = 1.0    # Recompensa otorgada por cada paso de tiempo sobreviviendo.
    reward_progress: float = 0.05 # Recompensa adicional por avanzar horizontalmente (mayor velocidad = mayor puntaje).

    max_time: float = 60.0       # Tiempo máximo permitido por episodio antes de forzar su término.
    fast_dt: float = 0.008       # Paso temporal usado en modo headless rápido (~125 FPS), permite simulación acelerada.
    
    # Discretización para iteración de valor (DP)
    y_bucket: int = 4            # Tamaño de los intervalos para cuantizar la posición vertical del jugador.
    vy_bucket: int = 40          # Tamaño de los intervalos para cuantizar la velocidad vertical.
    x_bucket: int = 8            # Tamaño de los intervalos para discretizar la distancia a los obstáculos.
    speed_bucket: int = 20       # Intervalos para discretizar la velocidad del juego.

    y_bucket_max: int = 80       # Límite máximo permitido para la posición vertical discretizada.
    vy_bucket_min: int = -30     # Límite mínimo para la velocidad vertical discretizada.
    vy_bucket_max: int = 30      # Límite máximo para la velocidad vertical discretizada.
    x_bucket_max: int = 200      # Máxima distancia discretizable a los obstáculos.
    speed_bucket_max: int = 120  # Velocidad máxima discretizable del entorno.



BLACK = (20, 20, 20)        # Color negro suave (usado para obstáculos y textos).
WHITE = (240, 240, 240)     # Fondo blanco grisáceo de la pantalla.
GREEN = (48, 204, 130)      # Verde para representar al jugador cuando está corriendo.
ORANGE = (255, 170, 64)     # Naranja para el jugador agachado o algunos obstáculos.
RED = (230, 70, 70)         # Rojo (no muy usado), útil para resaltar eventos o errores.
GRAY = (90, 90, 90)         # Gris para la línea del suelo y elementos secundarios.

class Player:
    def __init__(self, cfg: Config):
        # Referencia a la configuración global del juego
        self.cfg = cfg
        
        # Posición y dimensiones iniciales del jugador
        self.x = cfg.player_x                    # Posición horizontal fija
        self.height = cfg.run_height             # Altura inicial (corriendo)
        self.width = cfg.player_width            # Ancho del hitbox
        self.y = cfg.ground_y - self.height      # Posición vertical ajustada al suelo
        
        # Variables dinámicas del movimiento
        self.vy = 0.0                            # Velocidad vertical inicial
        self.state = PlayerState.RUN             # Estado inicial del jugador
        self.on_ground = True                    # Indica si está en el suelo (puede saltar)

    def rect(self) -> pygame.Rect:
        # Retorna el rectángulo (hitbox) actual del jugador para detección de colisiones
        return pygame.Rect(int(self.x), int(self.y), self.width, self.height)

    def _set_height(self, height: int):
        # Ajusta la altura del jugador (run/duck) conservando la posición del "techo"
        delta = self.height - height
        self.height = height
        self.y += delta

    def update(self, action: Action, dt: float):
        # Actualiza postura y movimiento vertical del jugador en un paso de simulación
        
        # --- Manejo de acciones ---
        if action == Action.JUMP and self.on_ground:
            # Inicio del salto: velocidad vertical inicial y cambio de estado
            if self.state == PlayerState.DUCK:
                self._set_height(self.cfg.run_height)  # No se puede saltar agachado
            self.vy = self.cfg.jump_velocity
            self.state = PlayerState.JUMP
            self.on_ground = False

        elif action == Action.DUCK and self.on_ground and self.state != PlayerState.DUCK:
            # Agacharse (solo si está en el suelo)
            self.state = PlayerState.DUCK
            self._set_height(self.cfg.duck_height)

        elif action == Action.STAND and self.on_ground and self.state == PlayerState.DUCK:
            # Volver a postura de correr
            self.state = PlayerState.RUN
            self._set_height(self.cfg.run_height)

        # --- Integración de la física vertical ---
        self.vy += self.cfg.gravity * dt       # Aplicación de gravedad
        self.y += self.vy * dt                 # Actualización de posición

        # --- Detección de aterrizaje ---
        if self.y >= self.cfg.ground_y - self.height:
            # Corrección para mantenerlo en el suelo
            self.y = self.cfg.ground_y - self.height
            self.vy = 0
            self.on_ground = True

            # Si venía saltando, vuelve al estado RUN
            if self.state == PlayerState.JUMP:
                self.state = PlayerState.RUN
        else:
            # Está en el aire en este frame
            self.on_ground = False

class Obstacle:
    def __init__(self, kind: ObstacleKind, x: float, cfg: Config):
        # Tipo de obstáculo (LOW, MID, HIGH)
        self.kind = kind
        
        # Dimensiones y posición vertical según el tipo
        self.width, self.height, self.y = self._spec(cfg)
        
        # Posición horizontal inicial del obstáculo
        self.x = x

    def _spec(self, cfg: Config) -> Tuple[int, int, int]:
        # Retorna (ancho, alto, y) dependiendo del tipo de obstáculo
        
        if self.kind == ObstacleKind.LOW:
            h = 38                                 # Altura del cactus bajo
            y = cfg.ground_y - h                   # Pegado al suelo
            w = 32                                 # Ancho del cactus

        elif self.kind == ObstacleKind.MID:
            h = 34                                 # Obstáculo volador alto
            y = cfg.ground_y - 140                 # No requiere salto
            w = 46

        else:
            h = 34                                 # Obstáculo volador bajo
            y = cfg.ground_y - 90                  # Requiere agacharse
            w = 46

        return w, h, y

    def rect(self) -> pygame.Rect:
        # Hitbox del obstáculo para detección de colisiones
        return pygame.Rect(int(self.x), int(self.y), self.width, self.height)


class ObstacleManager:
    def __init__(self, cfg: Config, rng: random.Random):
        # Referencia a la configuración global del entorno
        self.cfg = cfg
        
        # Generador de números aleatorios (permite reproducibilidad)
        self.rng = rng
        
        # Lista de obstáculos activos en pantalla
        self.obstacles: List[Obstacle] = []
        
        # Distancia recorrida desde el último spawn de obstáculo
        self.distance_since_last = 0.0
        
        # Nivel actual de dificultad (parte en la dificultad mínima)
        self.difficulty = cfg.min_difficulty
        
        # Tiempo acumulado desde el inicio del episodio
        self.elapsed = 0.0
        
        # Distancia objetivo hasta el próximo obstáculo (incluye aleatoriedad)
        self.next_gap = self._next_gap()
        
    def _next_gap(self) -> float:
        # Selecciona una distancia base entre obstáculos (corta o larga)
        base = self.rng.choice([self.cfg.short_gap, self.cfg.long_gap])
        
        # Factor que reduce el espacio a medida que aumenta la dificultad
        gap_scale = 1.8 - 0.8 * self.difficulty
        
        # Distancia final al próximo spawn, con aleatoriedad adicional
        return base * gap_scale * self.rng.uniform(0.9, 1.15) * self.cfg.spawn_delay_scale
        
    def reset(self):
        # Limpia todos los obstáculos activos
        self.obstacles.clear()
        
        # Reinicia la distancia desde el último spawn
        self.distance_since_last = 0.0
        
        # Restablece dificultad al valor mínimo definido
        self.difficulty = self.cfg.min_difficulty
        
        # Reinicia el tiempo transcurrido del episodio
        self.elapsed = 0.0
        
        # Calcula un nuevo gap inicial para el próximo obstáculo
        self.next_gap = self._next_gap()

    def set_difficulty(self, difficulty: float):
        # Ajusta la dificultad dentro del rango permitido [min_difficulty, 1.0]
        self.difficulty = max(self.cfg.min_difficulty, min(1.0, difficulty))
        
    def update(self, dt: float, speed: float):
        # Mueve obstáculos existentes y decide nuevos spawns según la dificultad
        self.elapsed += dt

        # --- Movimiento horizontal de todos los obstáculos ---
        for ob in self.obstacles:
            ob.x -= speed * dt                     # Se desplazan hacia la izquierda según la velocidad actual
        
        # Elimina obstáculos que ya salieron completamente de pantalla
        self.obstacles = [ob for ob in self.obstacles if ob.x + ob.width > 0]

        # --- Acumula distancia recorrida desde el último spawn ---
        self.distance_since_last += speed * dt

        # Fase inicial sin obstáculos (warmup)
        if self.elapsed < self.cfg.warmup_time:
            self.distance_since_last = 0.0
            return

        # --- Condición de spawn: suficiente distancia + control de cupos ---
        # Para LOW en serie, permitimos usar 2 slots extra para que un trío cuente como "uno".
        can_spawn_low = len(self.obstacles) < self.cfg.obstacle_max + 2
        can_spawn_other = len(self.obstacles) < self.cfg.obstacle_max

        if self.distance_since_last >= self.next_gap:

            # Posición horizontal del próximo obstáculo (ligero desplazamiento aleatorio)
            spawn_x = self.cfg.width + self.rng.randint(0, 60)

            # Selección del tipo de obstáculo
            kind = self.rng.choice([ObstacleKind.LOW, ObstacleKind.MID, ObstacleKind.HIGH])

            if kind == ObstacleKind.LOW and not can_spawn_low:
                return
            if kind != ObstacleKind.LOW and not can_spawn_other:
                return

            # --- Caso especial: cactus bajos pueden venir en grupos de 1 a 3 ---
            if kind == ObstacleKind.LOW:
                roll = self.rng.random()
                # Aumenta probabilidad de series: 20% uno, 40% dos, 40% tres
                count = 1 if roll < 0.20 else 2 if roll < 0.60 else 3
                gap_px = 2                                           # Pequeño espacio entre ellos
                x_pos = spawn_x

                for _ in range(count):
                    ob = Obstacle(kind, x_pos, self.cfg)
                    self.obstacles.append(ob)
                    x_pos += ob.width + gap_px                       # Avanza para el siguiente cactus

            # --- Obstáculos voladores: solo uno por spawn ---
            else:
                self.obstacles.append(Obstacle(kind, spawn_x, self.cfg))

            # Reinicia distancia y calcula el próximo gap
            self.distance_since_last = 0.0
            self.next_gap = self._next_gap()

class DPAgent:
    def __init__(self, cfg: Config):
        # Referencia a la configuración global del agente y del entorno
        self.cfg = cfg
        
        # Diccionario para memoización de estados evaluados en la búsqueda DP
        self.memo = {}

    def decide(self, player: Player, obstacles: List[Obstacle], speed: float) -> Action:
        # Determina la acción óptima usando búsqueda DP con backup Bellman sobre un estado discretizado
        
        # Genera una representación compacta del estado actual (jugador + obstáculos)
        snapshot = self._snapshot(player, obstacles)
        
        # Limpia la memoria de estados evaluados (nueva decisión = nuevo árbol)
        self.memo.clear()
        
        # Ejecuta la búsqueda recursiva desde la profundidad máxima definida
        action, _ = self._search(snapshot, speed, self.cfg.dp_depth)
        
        # Retorna únicamente la acción elegida
        return action

    def _snapshot(self, player: Player, obstacles: List[Obstacle]):
        # Construye un estado compacto para el agente:
        # (posición y, velocidad vertical, si está agachado, obstáculos próximos)
        
        # Ordena obstáculos por posición horizontal (los más cercanos primero)
        obs = sorted(obstacles, key=lambda o: o.x)
        
        # Guarda las propiedades relevantes de hasta los 3 obstáculos más cercanos
        obs_state = []
        for o in obs[:3]:
            obs_state.append((o.x, o.y, o.width, o.height, o.kind))
        
        # Retorna el estado en formato túpla para que sea hashable (usable en memo)
        return (player.y, 
                player.vy, 
                player.state == PlayerState.DUCK, 
                tuple(obs_state))

    def _player_rect_from_state(self, y: float, duck: bool) -> pygame.Rect:
        # Genera el rectángulo (hitbox) del jugador a partir de un estado simulado (y, postura)
        height = self.cfg.duck_height if duck else self.cfg.run_height
        return pygame.Rect(self.cfg.player_x, int(y), self.cfg.player_width, height)

    def _collides(self, y: float, duck: bool, obstacles) -> bool:
        # Verifica colisión entre el jugador simulado y la lista de obstáculos simulados
        
        rect = self._player_rect_from_state(y, duck)   # Hitbox del jugador en el estado simulado
        
        for ob in obstacles:
            x, oy, w, h, _ = ob                        # Desempaqueta cada obstáculo (formato snapshot)
            ob_rect = pygame.Rect(int(x), int(oy), w, h)
            
            if rect.colliderect(ob_rect):              # Colisión detectada
                return True
        
        return False                                    # No hubo colisiones

    def _step_player(self, y: float, vy: float, duck: bool, action: Action) -> Tuple[float, float, bool]:
        # Simula un paso de la física del jugador usando el dt reducido del DP
        
        # Determina la altura actual según la postura
        height = self.cfg.duck_height if duck else self.cfg.run_height
        
        # Chequea si el jugador simulado está en el suelo
        on_ground = y >= self.cfg.ground_y - height - 1e-3

        # --- Manejo de acciones (solo afectan si está en el suelo) ---
        if action == Action.JUMP and on_ground:
            vy = self.cfg.jump_velocity     # Inicio del salto
            duck = False
        elif action == Action.DUCK and on_ground:
            duck = True                     # Se agacha
        elif action == Action.STAND and on_ground:
            duck = False                    # Se vuelve a levantar

        # --- Integración de la física con el dt interno del DP ---
        vy += self.cfg.gravity * self.cfg.dp_dt
        y += vy * self.cfg.dp_dt

        # --- Corrección si cae al suelo ---
        height = self.cfg.duck_height if duck else self.cfg.run_height
        if y >= self.cfg.ground_y - height:
            y = self.cfg.ground_y - height  # Reposiciona exactamente en el suelo
            vy = 0.0                        # Velocidad vertical se anula

        return y, vy, duck                  # Retorna el estado simulado

    def _step_obstacles(self, obstacles, speed: float):
        # Simula un paso de movimiento horizontal de los obstáculos con el dt interno del DP
        
        next_obs = []
        for x, y, w, h, kind in obstacles:
            x -= speed * self.cfg.dp_dt            # Avanza el obstáculo hacia la izquierda
            
            # Mantiene solo los obstáculos que aún están dentro de la pantalla simulada
            if x + w > 0:
                next_obs.append((x, y, w, h, kind))
        
        return next_obs                             # Retorna la lista actualizada


    def _state_key(self, y: float, vy: float, duck: bool, obstacles, speed: float):
        # Genera una clave discretizada del estado para usar en memoización (hashable)
        
        def bucket(val: float, size: float) -> int:
            # Cuantiza un valor continuo usando el tamaño de bucket dado
            return int(round(val / size))

        # Discretiza la información de hasta 2 obstáculos cercanos
        obs_key = []
        for x, _, _, _, kind in list(obstacles)[:2]:
            obs_key.append((bucket(x, 8), kind.value))

        # Retorna el estado completo discretizado:
        # (pos_y, vel_y, postura, obstáculos, velocidad)
        return (
            bucket(y, 4),
            bucket(vy, 40),
            duck,
            tuple(obs_key),
            bucket(speed, 20)
        )


    def _search(self, state, speed: float, depth: int) -> Tuple[Action, float]:
        # Búsqueda recursiva estilo Bellman para estimar el mejor valor/acción desde un estado discretizado.
        
        y, vy, duck, obstacles = state
        
        # Genera clave del estado + profundidad para memoización
        key = (self._state_key(y, vy, duck, obstacles, speed), depth)
        if key in self.memo:
            return self.memo[key]     # Retorna resultado almacenado si ya fue calculado

        # Inicialización del mejor resultado
        best_action = Action.NONE
        best_score = -1e9             # Valor muy bajo para poder comparar
        actions = (Action.NONE, Action.JUMP, Action.DUCK, Action.STAND)

        # Evalúa todas las acciones posibles
        for action in actions:
            sim_y, sim_vy, sim_duck = y, vy, duck          # Copia del estado del jugador
            sim_obs = list(obstacles)                      # Copia de obstáculos simulados
            alive = True
            gained = 0.0                                   # Recompensa acumulada durante el rollout

            # --- Rollout corto desde el estado actual (primer paso usa la acción, luego NONE) ---
            for _ in range(self.cfg.rollout_steps):
                sim_y, sim_vy, sim_duck = self._step_player(
                    sim_y, sim_vy, sim_duck,
                    action if _ == 0 else Action.NONE
                )
                sim_obs = self._step_obstacles(sim_obs, speed)

                # Si muere en el rollout, se corta
                if self._collides(sim_y, sim_duck, sim_obs):
                    alive = False
                    break

                # Recompensa por seguir vivo + progresar
                gained += (
                    self.cfg.reward_alive * self.cfg.dp_dt +
                    self.cfg.reward_progress * speed * self.cfg.dp_dt
                )

            # Si muere, penalización fuerte
            total_score = -1000.0 if not alive else gained

            # --- Llamada recursiva (si quedan niveles de profundidad y sigue vivo) ---
            if alive and depth > 1:
                next_state = (sim_y, sim_vy, sim_duck, tuple(sim_obs))
                _, child_score = self._search(next_state, speed, depth - 1)
                total_score += self.cfg.gamma * child_score     # Descuento Bellman

            # Actualiza el mejor resultado encontrado
            if total_score > best_score:
                best_score = total_score
                best_action = action

        # Guarda en memo la mejor acción y valor para este estado
        self.memo[key] = (best_action, best_score)
        return best_action, best_score


class RandomPolicy:
    def decide(self, player: Player) -> Action:
        # Política base muy simple: elige una acción aleatoria solo cuando el jugador está en el suelo
        if player.on_ground:
            return random.choice([Action.NONE, Action.JUMP, Action.DUCK])
        
        # En el aire no toma ninguna acción
        return Action.NONE



class Game:
    def __init__(self, cfg: Config, mode: str, episodes: int, headless: bool = False, rng: random.Random | None = None, fast: bool = False):
        # Configuración general del juego
        self.cfg = cfg
        self.mode = mode                          # Modo de control: human / agent / random
        self.episodes = episodes
        self.rng = rng or random.Random()         # Generador de aleatoriedad (permite reproducibilidad)
        self.fast = fast                          # Modo rápido (sin limitación de FPS)
        self.animation_time = 0.0                 #   Para animaciones

        # Configuración para ejecución sin ventana (modo evaluación)
        if headless:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

        # Inicializa Pygame y la ventana del juego
        pygame.init()
        flags = pygame.HIDDEN if headless else 0
        self.screen = pygame.display.set_mode((cfg.width, cfg.height), flags=flags)
        pygame.display.set_caption("Dino (POO + DP)")

        # Reloj para controlar el tiempo real del juego
        self.clock = pygame.time.Clock()

        # Fuente usada para mostrar estadísticas en pantalla
        self.font = pygame.font.SysFont("consolas", 18)

        # Inicializa agentes: DP y política random
        self.agent = DPAgent(cfg)
        self.random_policy = RandomPolicy()
        self.sprite_manager = SpriteManager()  #   Gestor de sprites para gráficos mejorados


    def run(self):
        # Ejecuta el juego por la cantidad de episodios especificada
        scores = []
        durations = []

        for ep in range(self.episodes):
            print(f"[EP {ep+1}/{self.episodes}] inicio")

            # Corre un episodio completo y obtiene puntaje y duración
            score, duration = self._run_episode(ep)
            scores.append(score)
            durations.append(duration)

            print(f"[EP {ep+1}/{self.episodes}] fin - score={score:.1f}, tiempo={duration:.2f}s")

        # Devuelve listas con puntajes y tiempos de todos los episodios
        return scores, durations

    def _run_episode(self, episode_idx: int) -> float:
        # Bucle principal de simulación por episodio
        
        player = Player(self.cfg)                         # Jugador del episodio
        obstacles = ObstacleManager(self.cfg, self.rng)   # Administrador de obstáculos
        speed = self.cfg.base_speed                       # Velocidad inicial del escenario
        t = 0.0                                            # Tiempo transcurrido
        alive = True                                       # Estado del jugador
        score = 0.0                                        # Puntaje acumulado

        # --- Loop principal del episodio ---
        while alive and t < self.cfg.max_time:

            # Tiempo por frame (dt) según modo rápido o normal
            if self.fast:
                dt = self.cfg.fast_dt
                pygame.event.pump()                       # Evita bloqueo del sistema en headless
            else:
                dt = self.clock.tick(60) / 1000.0         # Limita a 60 FPS

            t += dt
            self.animation_time += dt  #   Actualizar tiempo de animación para sprites

            # Actualización de dificultad creciente con el tiempo
            difficulty = min(1.0, self.cfg.min_difficulty + t / self.cfg.ramp_time)

            # Ajuste del factor de velocidad según dificultad
            speed_factor = 0.55 + 0.45 * difficulty
            speed = self.cfg.base_speed + self.cfg.speed_growth * t * speed_factor

            # Acción por defecto
            action = Action.NONE

            # --- Manejo de eventos del sistema (cerrar ventana) ---
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    raise SystemExit

            # --- Selección de acción según el modo de juego ---
            if self.mode == "human":
                keys = pygame.key.get_pressed()
                if keys[pygame.K_SPACE] or keys[pygame.K_UP]:
                    action = Action.JUMP
                elif keys[pygame.K_DOWN]:
                    action = Action.DUCK
                elif player.state == PlayerState.DUCK and not keys[pygame.K_DOWN]:
                    action = Action.STAND

            elif self.mode == "agent":
                action = self.agent.decide(player, obstacles.obstacles, speed)

            elif self.mode == "random":
                action = self.random_policy.decide(player)

            # --- Actualización del estado del jugador y obstáculos ---
            player.update(action, dt)
            obstacles.set_difficulty(difficulty)
            obstacles.update(dt, speed)

            # --- Detección de colisiones ---
            for ob in obstacles.obstacles:
                if player.rect().colliderect(ob.rect()):
                    alive = False
                    break

            # --- Actualización del puntaje ---
            score += dt * 100.0 + speed * dt * 0.05

            # --- Render del frame ---
            self._render(player, obstacles, score, episode_idx, t, speed, difficulty)

        # Retorna puntaje total y duración del episodio
        return score, t

    def _get_dino_sprite(self, player: Player) -> pygame.Surface:
        """  Obtiene el sprite correcto del dinosaurio según su estado"""
        if player.state == PlayerState.JUMP:
            # Saltando - usar dino con patas normales (sprite estático)
            return self.sprite_manager.get_sprite('dino_run1')
        elif player.state == PlayerState.DUCK:
            # Agachado - alternar entre los 2 sprites de agachado
            frame = int(self.animation_time * 10) % 2  # Cambia cada 0.1 segundos
            return self.sprite_manager.get_sprite(f'dino_duck{frame + 1}')
        else:
            # Corriendo - alternar entre los 3 sprites de carrera
            frame = int(self.animation_time * 10) % 3  # Cambia cada 0.1 segundos
            return self.sprite_manager.get_sprite(f'dino_run{frame + 1}')

    def _render(self, player: Player, obstacles: ObstacleManager, score: float, episode_idx: int, t: float, speed: float, difficulty: float):
        # No renderiza si la ventana está oculta o inactiva (modo headless)
        if not pygame.display.get_active() and pygame.display.get_surface().get_flags() & pygame.HIDDEN:
            return

        # Limpia la pantalla
        self.screen.fill(WHITE)

        # Línea del suelo
        pygame.draw.line(self.screen, GRAY, (0, self.cfg.ground_y + 2), (self.cfg.width, self.cfg.ground_y + 2), 2)

        #   Dibuja al jugador con sprite animado en lugar de rectángulo simple
        dino_sprite = self._get_dino_sprite(player)
        self.screen.blit(dino_sprite, (int(player.x), int(player.y)))

        # Dibuja los obstáculos en pantalla con sprites
        for ob in obstacles.obstacles:
            if ob.kind == ObstacleKind.LOW:
                #   Cactus - sprite estático
                cactus_sprite = self.sprite_manager.get_sprite('cactus')
                self.screen.blit(cactus_sprite, (int(ob.x), int(ob.y)))
            elif ob.kind == ObstacleKind.MID or ob.kind == ObstacleKind.HIGH:
                #   Pájaros - alternar entre alas arriba/abajo para animación de vuelo
                frame = int(self.animation_time * 8) % 2  # Cambia cada 0.125 segundos
                bird_sprite = self.sprite_manager.get_sprite('bird_up' if frame == 0 else 'bird_down')
                self.screen.blit(bird_sprite, (int(ob.x), int(ob.y)))
            else:
                # Fallback: dibujar rectángulo si no hay sprite disponible
                ob_color = BLACK if ob.kind == ObstacleKind.LOW else ORANGE
                pygame.draw.rect(self.screen, ob_color, ob.rect(), border_radius=4)

        # Información de estado mostrada en pantalla
        info_lines = [
            f"Modo: {self.mode} | Episodio {episode_idx + 1}/{self.episodes} | Dificultad: {difficulty:0.2f}",
            f"Puntaje: {score:7.1f}   Velocidad: {speed:5.0f} px/s",
            f"Tiempo vivo: {t:4.2f}s   Obstaculos: {len(obstacles.obstacles)}",
            "Teclas: SPACE/UP saltar, DOWN agacharse, Cerrar ventana para salir",
        ]

        # Dibuja cada línea de texto en pantalla
        for i, text in enumerate(info_lines):
            surface = self.font.render(text, True, BLACK)
            self.screen.blit(surface, (16, 12 + 22 * i))

        # Actualiza la ventana
        pygame.display.flip()


def parse_args():
    # Parser de argumentos para ejecutar el juego desde consola
    parser = argparse.ArgumentParser(description="Dino de Google con POO + Programacion Dinamica")
    
    parser.add_argument("--mode", choices=["human", "agent", "random"], default="human",
                        help="Control del jugador (teclado / agente DP / política aleatoria)")
    
    parser.add_argument("--episodes", type=int, default=1,
                        help="Cantidad de episodios a jugar")
    
    parser.add_argument("--headless", action="store_true",
                        help="Ejecuta sin ventana (útil para evaluar agentes)")
    
    parser.add_argument("--seed", type=int, default=None,
                        help="Semilla para reproducibilidad")
    
    parser.add_argument("--save_csv", type=str, default=None,
                        help="Ruta para guardar resultados de puntaje en formato CSV")
    
    parser.add_argument("--max_time", type=float, default=None,
                        help="Tiempo máximo por episodio en segundos")
    
    parser.add_argument("--fast", action="store_true",
                        help="Modo rápido (omite limitación de FPS en modo headless)")
    
    return parser.parse_args()

def main():
    # Lee argumentos desde la línea de comandos
    args = parse_args()

    # Configura semillas para reproducibilidad si corresponde
    if args.seed is not None:
        random.seed(args.seed)
        os.environ["PYTHONHASHSEED"] = str(args.seed)
    
    # Generador de aleatoriedad (reproducible si se entrega seed)
    rng = random.Random(args.seed) if args.seed is not None else random.Random()

    # Carga configuración base del juego
    cfg = Config()

    # Permite modificar el tiempo máximo desde argumentos
    if args.max_time is not None:
        cfg.max_time = args.max_time

    # Crea la instancia del juego según los parámetros entregados
    game = Game(cfg, args.mode, args.episodes, headless=args.headless, rng=rng, fast=args.fast)

    # Ejecuta episodios y asegura liberar Pygame al terminar
    try:
        scores, durations = game.run()
    finally:
        pygame.quit()

    # Métricas finales de desempeño del agente/jugador
    avg = sum(scores) / len(scores)
    med = stats.median(scores)
    best = max(scores)
    worst = min(scores)

    print(
        f"Episodios: {len(scores)} | Puntajes: {[round(s,1) for s in scores]} | "
        f"Promedio: {avg:.1f} | Mediana: {med:.1f} | Max: {best:.1f} | Min: {worst:.1f}"
    )

    # Guardado opcional de resultados a CSV
    if args.save_csv:
        try:
            import csv

            with open(args.save_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["episode", "score", "duration_sec"])

                # Escribe puntaje y duración por episodio
                for i, (s, d) in enumerate(zip(scores, durations), start=1):
                    writer.writerow([i, f"{s:.3f}", f"{d:.3f}"])

            print(f"Resultados guardados en {args.save_csv}")

        except Exception as exc:
            print(f"No se pudo guardar CSV: {exc}")
            
if __name__ == "__main__":
    # Punto de entrada del programa cuando se ejecuta directamente desde la consola
    main()

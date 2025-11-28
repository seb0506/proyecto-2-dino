import pygame
import os

class SpriteManager:
    """
    Gestiona la carga y almacenamiento de sprites graficos para el juego.
    Utiliza una hoja de sprites unica y extrae cada elemento mediante coordenadas.
    """
    def __init__(self):
        # Diccionario para almacenar todos los sprites cargados
        self.sprites = {}
        # Cargar los sprites al inicializar el gestor
        self.load_sprites()
    
    def load_sprites(self):
        """
        Carga y procesa todos los sprites desde la hoja de sprites principal.
        Extrae cada elemento usando coordenadas especificas y aplica transformaciones.
        """
        try:
            # Cargar la hoja de sprites completa con transparencia
            sprite_sheet = pygame.image.load("assets/100-offline-sprite.png").convert_alpha()
            
            # --- CARGAR SPRITE DE CACTUS ---
            # Coordenadas y dimensiones del cactus en la hoja de sprites
            cactus_rect = pygame.Rect(332, 2, 25, 49)
            # Extraer la superficie del cactus
            cactus_surface = sprite_sheet.subsurface(cactus_rect)
            # Aplicar color verde al cactus
            cactus_surface = self._apply_green_tint(cactus_surface)
            # Escalar a las dimensiones finales y guardar
            self.sprites['cactus'] = pygame.transform.scale(cactus_surface, (32, 38))
            
            # --- CARGAR SPRITES DE DINOSAURIO CORRIENDO ---
            # Primer frame de dinosaurio corriendo
            dino1_rect = pygame.Rect(847, 1, 45, 48)
            dino1_surface = sprite_sheet.subsurface(dino1_rect)
            dino1_surface = self._apply_dark_gray_tint(dino1_surface)
            self.sprites['dino_run1'] = pygame.transform.scale(dino1_surface, (50, 70))
            
            # Segundo frame de dinosaurio corriendo
            dino2_rect = pygame.Rect(936, 1, 43, 48)
            dino2_surface = sprite_sheet.subsurface(dino2_rect)
            dino2_surface = self._apply_dark_gray_tint(dino2_surface)
            self.sprites['dino_run2'] = pygame.transform.scale(dino2_surface, (50, 70))
            
            # Tercer frame de dinosaurio corriendo
            dino3_rect = pygame.Rect(980, 1, 44, 48)
            dino3_surface = sprite_sheet.subsurface(dino3_rect)
            dino3_surface = self._apply_dark_gray_tint(dino3_surface)
            self.sprites['dino_run3'] = pygame.transform.scale(dino3_surface, (50, 70))
            
            # --- CARGAR SPRITES DE DINOSAURIO AGACHADO ---
            # Primer frame de dinosaurio agachado
            dino_duck1_rect = pygame.Rect(1111, 18, 61, 31)
            dino_duck1_surface = sprite_sheet.subsurface(dino_duck1_rect)
            dino_duck1_surface = self._apply_dark_gray_tint(dino_duck1_surface)
            self.sprites['dino_duck1'] = pygame.transform.scale(dino_duck1_surface, (52, 40))
            
            # Segundo frame de dinosaurio agachado
            dino_duck2_rect = pygame.Rect(1172, 18, 58, 31)
            dino_duck2_surface = sprite_sheet.subsurface(dino_duck2_rect)
            dino_duck2_surface = self._apply_dark_gray_tint(dino_duck2_surface)
            self.sprites['dino_duck2'] = pygame.transform.scale(dino_duck2_surface, (52, 40))
            
            # --- CARGAR SPRITES DE PAJAROS ---
            # Pajaro con alas en posicion baja (vista lateral)
            bird1_rect = pygame.Rect(133, 7, 47, 35)
            bird1_surface = sprite_sheet.subsurface(bird1_rect)
            bird1_surface = self._apply_dark_gray_tint(bird1_surface)
            self.sprites['bird_down'] = pygame.transform.scale(bird1_surface, (46, 34))
            
            # Pajaro con alas en posicion alta (vista lateral)
            bird2_rect = pygame.Rect(180, 2, 46, 30)
            bird2_surface = sprite_sheet.subsurface(bird2_rect)
            bird2_surface = self._apply_dark_gray_tint(bird2_surface)
            self.sprites['bird_up'] = pygame.transform.scale(bird2_surface, (46, 34))
            
            # Confirmacion de carga exitosa
            print("Sprites cargados exitosamente: cactus, 3 frames de dinosaurio corriendo, 2 frames de dinosaurio agachado, 2 frames de pajaros")
            
        except pygame.error as e:
            print(f"Error al cargar los sprites: {e}")
            print("Asegurese de que el archivo assets/100-offline-sprite.png existe")
        except Exception as e:
            print(f"Error inesperado al cargar sprites: {e}")
    
    def _apply_green_tint(self, surface):
        """
        Aplica un tinte verde a una superficie grafica.
        
        Args:
            surface: Superficie de pygame a modificar
            
        Returns:
            Nueva superficie con tinte verde aplicado
        """
        # Crear una copia de la superficie original
        green_surface = surface.copy()
        # Aplicar color verde multiplicando los canales RGB
        green_surface.fill((0, 255, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return green_surface
    
    def _apply_dark_gray_tint(self, surface):
        """
        Aplica un tinte gris oscuro a una superficie grafica.
        
        Args:
            surface: Superficie de pygame a modificar
            
        Returns:
            Nueva superficie con tinte gris oscuro aplicado
        """
        # Crear una copia de la superficie original
        gray_surface = surface.copy()
        # Aplicar color gris oscuro multiplicando los canales RGB
        gray_surface.fill((120, 120, 120), special_flags=pygame.BLEND_RGBA_MULT)
        return gray_surface
    
    def get_sprite(self, name):
        """
        Recupera un sprite por su nombre identificador.
        
        Args:
            name: String con el nombre del sprite a recuperar
            
        Returns:
            Superficie de pygame con el sprite solicitado, o None si no existe
        """
        return self.sprites.get(name)

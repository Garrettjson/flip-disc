"""Conway's Game of Life animation."""

import numpy as np

from .base import Animation, register_animation


@register_animation("life")
class Life(Animation):
    """Conway's Game of Life cellular automaton."""

    def __init__(self, width: int, height: int):
        super().__init__(width, height)

        # Game state
        self.grid = np.zeros((height, width), dtype=bool)
        self.next_grid = np.zeros((height, width), dtype=bool)

        # Timing
        self.update_interval = 0.5  # Seconds between generations
        self.last_update = 0.0
        self.generation = 0

        # Initialize with random pattern
        self._randomize(density=0.3)

    def configure(self, **params):
        """Configure Life parameters."""
        super().configure(**params)

        if "update_interval" in params:
            self.update_interval = float(params["update_interval"])
        if "density" in params:
            self._randomize(float(params["density"]))
        if "pattern" in params:
            self._load_pattern(params["pattern"])

    def step(self, dt: float) -> None:
        """Advance Game of Life simulation."""
        self.current_time += dt

        if self.current_time - self.last_update >= self.update_interval:
            self._update_generation()
            self.last_update = self.current_time

    def render_gray(self) -> np.ndarray:
        """Render current Life state to grayscale."""
        # Convert boolean grid to float with some visual enhancement
        frame = self.grid.astype(np.float32)

        # Add slight glow effect for living cells
        if np.any(self.grid):
            # Dilate to create glow
            kernel = np.array([[0.1, 0.2, 0.1], [0.2, 1.0, 0.2], [0.1, 0.2, 0.1]])

            # Simple convolution for glow
            padded = np.pad(frame, 1, mode="constant")
            glowed = np.zeros_like(frame)

            for y in range(self.height):
                for x in range(self.width):
                    glowed[y, x] = np.sum(padded[y : y + 3, x : x + 3] * kernel)

            frame = np.clip(glowed, 0, 1)

        return frame

    def _update_generation(self):
        """Apply Conway's Game of Life rules."""
        self.generation += 1

        # Count neighbors for each cell
        for y in range(self.height):
            for x in range(self.width):
                neighbors = self._count_neighbors(x, y)
                current = self.grid[y, x]

                # Conway's rules:
                # 1. Live cell with 2-3 neighbors survives
                # 2. Dead cell with exactly 3 neighbors becomes alive
                # 3. All other cells die or remain dead
                if current:
                    self.next_grid[y, x] = neighbors in [2, 3]
                else:
                    self.next_grid[y, x] = neighbors == 3

        # Swap grids
        self.grid, self.next_grid = self.next_grid, self.grid
        self.next_grid.fill(False)

        # Check for stagnation and re-seed if needed
        if self.generation % 100 == 0:
            alive_count = np.sum(self.grid)
            if alive_count < 5:  # Too few cells, re-seed
                self._randomize(density=0.2)

    def _count_neighbors(self, x: int, y: int) -> int:
        """Count living neighbors around cell (x, y)."""
        count = 0
        for dy in [-1, 0, 1]:
            for dx in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue

                nx, ny = x + dx, y + dy

                # Wrap around edges (toroidal topology)
                nx = nx % self.width
                ny = ny % self.height

                if self.grid[ny, nx]:
                    count += 1

        return count

    def _randomize(self, density: float = 0.3):
        """Initialize with random pattern."""
        self.grid = np.random.random((self.height, self.width)) < density
        self.generation = 0

    def _load_pattern(self, pattern_name: str):
        """Load a predefined pattern."""
        self.grid.fill(False)
        self.generation = 0

        center_x, center_y = self.width // 2, self.height // 2

        if pattern_name == "glider":
            # Classic glider pattern
            pattern = [(1, 0), (2, 1), (0, 2), (1, 2), (2, 2)]
            for dx, dy in pattern:
                x, y = center_x + dx - 1, center_y + dy - 1
                if 0 <= x < self.width and 0 <= y < self.height:
                    self.grid[y, x] = True

        elif pattern_name == "blinker":
            # Oscillating blinker
            for dx in [-1, 0, 1]:
                x = center_x + dx
                if 0 <= x < self.width:
                    self.grid[center_y, x] = True

        elif pattern_name == "block":
            # Stable block
            pattern = [(0, 0), (0, 1), (1, 0), (1, 1)]
            for dx, dy in pattern:
                x, y = center_x + dx, center_y + dy
                if 0 <= x < self.width and 0 <= y < self.height:
                    self.grid[y, x] = True

        elif pattern_name == "beacon":
            # Oscillating beacon
            pattern = [(0, 0), (0, 1), (1, 0), (2, 3), (3, 2), (3, 3)]
            for dx, dy in pattern:
                x, y = center_x + dx - 1, center_y + dy - 1
                if 0 <= x < self.width and 0 <= y < self.height:
                    self.grid[y, x] = True
        else:
            # Default to random
            self._randomize()

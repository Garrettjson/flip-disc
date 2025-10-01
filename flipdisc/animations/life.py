"""Conway's Game of Life animation."""

import numpy as np

from .base import Animation, register_animation


@register_animation("life")
class Life(Animation):
    """Conway's Game of Life cellular automaton."""

    def __init__(self, width: int, height: int):
        super().__init__(width, height, output_format="gray", processing_steps=("dither",))

        # Game state
        self.grid = np.zeros((height, width), dtype=bool)
        self.next_grid = np.zeros((height, width), dtype=bool)

        # Timing
        self.generation = 0

        # Initialize with random pattern
        self._randomize(density=0.3)

    def configure(self, **params):
        """Configure Life parameters."""
        super().configure(**params)

        if "density" in params:
            self._randomize(float(params["density"]))
        if "pattern" in params:
            self._load_pattern(params["pattern"])

    def step(self, dt: float) -> None:
        """Advance Game of Life simulation."""
        self.current_time += dt
        self._update_generation()

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

    def _place_pattern(
        self, pattern: list[tuple[int, int]], offset_x: int = 0, offset_y: int = 0
    ):
        """Place a pattern on the grid with given offset."""
        center_x, center_y = self.width // 2, self.height // 2
        for dx, dy in pattern:
            x, y = center_x + dx + offset_x, center_y + dy + offset_y
            if 0 <= x < self.width and 0 <= y < self.height:
                self.grid[y, x] = True

    def _load_glider(self):
        pattern = [(1, 0), (2, 1), (0, 2), (1, 2), (2, 2)]
        self._place_pattern(pattern, offset_x=-1, offset_y=-1)

    def _load_blinker(self):
        pattern = [(-1, 0), (0, 0), (1, 0)]
        self._place_pattern(pattern)

    def _load_block(self):
        pattern = [(0, 0), (0, 1), (1, 0), (1, 1)]
        self._place_pattern(pattern)

    def _load_beacon(self):
        pattern = [(0, 0), (0, 1), (1, 0), (2, 3), (3, 2), (3, 3)]
        self._place_pattern(pattern, offset_x=-1, offset_y=-1)

    def _load_pattern(self, pattern_name: str):
        """Load a predefined pattern."""
        self.grid.fill(False)
        self.generation = 0

        pattern_loaders = {
            "glider": self._load_glider,
            "blinker": self._load_blinker,
            "block": self._load_block,
            "beacon": self._load_beacon,
        }

        loader = pattern_loaders.get(pattern_name)
        if loader:
            loader()
        else:
            self._randomize()

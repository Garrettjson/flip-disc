from __future__ import annotations
from dataclasses import dataclass, InitVar, field
import numpy as np
import numpy.typing as npt
from animations.animation import Animation
from frame import Frame
from itertools import combinations
from typing import List, Iterator


@ dataclass
class Particle:
    """
    TODO: comment
    """
    pos_x: InitVar[float]
    pos_y: InitVar[float]
    density: float = 1.
    radius: float = 1.
    mass: float = density * np.pi * radius**3
    vel: npt.NDArray[np.float64] = field(default_factory=lambda: np.array([0., 0.]))  # (x, y)
    pos: npt.NDArray[np.float64] = field(default_factory=lambda: np.array([0., 0.]))  # (x, y)

    def __post_init__(self, pos_x, pos_y):
        self.pos = np.array([pos_x, pos_y], dtype=float)
            

class NBody(Animation):
    """
    TODO: comment
    """

    def __init__(self, particles: List[Particle],  grav: float=1, **kwargs):
        super().__init__(**kwargs)
        self.particles = particles
        self.grav = grav


    @classmethod
    def from_number(cls, n: int, grav: float=1) -> NBody:
        """
        Creates a list of n particle objects at random (x,y) coordinates within
        within the bounds of the frame
        """
        # TODO: replace hard-coded 28 with panel size from config file
        x = np.random.randint(28, size=n)
        y = np.random.randint(28, size=n)
        particles = [Particle(x[i], y[i]) for i in range(n)]
        return cls(particles, grav)

    
    def _calc_velocity(self, p1: Particle, p2: Particle, G: float) -> None:
        """
        Caclulates a particle's velocity based on gravitational attraction with another particle.

        The force F of the attraction can be caclulated as: F = G*M1*M2 / R, where:
            - G : force of gravity
            - M1: mass of particle 1
            - M2: mass of particle 2
            - R : euclidean distance between particles

        We then turn our force into a vector: Fv = F * (P1 - P2) / R^2, where:
            - F : force from above step
            - P1: (x,y) position of particle 1
            - p2: (x,y) position of particle 2
            - R : euclidean distance between particles

        Lastly, we caclulate the particle's change in velocity: Dv = Fv / M1, where:
            - Fv: force vector from above step
            - M1: mass of particle 1

        Some of the terms in these equations can be simplifed into this final formula:
        G * M2 * (P1 - P2) / R^3
        """
        dp = p1.pos - p2.pos
        r = np.dot(dp.T, dp)
        p1.vel += -G * p2.mass * dp / r**3
        # TODO: logic to avoid collisions and bounce off walls


    def _update_velocties(self) -> None:
        for p1, p2 in combinations(self.particles, 2):
            self._calc_velocity(p1, p2, self.grav)
            self._calc_velocity(p2, p1, self.grav)


    def _update_positions(self) -> None:
        for p in self.particles:
            p.pos += p.vel


    def next_frame(self) -> Iterator[Frame]: 
        while True:
            self._update_velocties()
            self._update_positions()
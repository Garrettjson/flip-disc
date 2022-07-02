import numpy as np
from frame import Frame

def main():
    r = np.random.rand(28, 28)
    rnd = Frame(np.around(r))
    rnd.show()

main()
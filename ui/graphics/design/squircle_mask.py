import numpy as np
from PIL import Image

t = np.linspace(-1, 1, 1024)
x, y = np.meshgrid(t, t)

p = 4
r = (abs(x)**p + abs(y)**p)**(1/p)
h = 80  # Edge hardness
mask = np.clip((1 - r)*h, 0, 1)
mask = (255 * mask).astype(np.uint8)
Image.fromarray(mask).save("squircle_mask.png")

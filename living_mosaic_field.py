"""Motion-adaptive triangle mosaic. Fixed memory; no recording or person detector."""
import cv2
import numpy as np


class LivingMosaic:
    def __init__(self, width=640, height=360):
        self.width, self.height = width, height
        self.previous = None
        self.activity = np.zeros((height, width), np.float32)
        self.maps = None
        self.map_time = -1.

    def update_motion(self, frame, dt):
        gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (7, 7), 0)
        if self.previous is not None:
            difference = cv2.absdiff(gray, self.previous).astype(np.float32)
            signal = np.clip((difference - 5) / 15, 0, 1)
            signal = cv2.dilate(signal, np.ones((31, 31), np.uint8))
            signal = cv2.GaussianBlur(signal, (31, 31), 0)
            # Fast coarse response; about three seconds to lose most of the trail.
            dt = min(max(dt, 0), .2)
            rate = np.where(signal > self.activity, 18., 1.1)
            self.activity += (signal - self.activity) * (1 - np.exp(-rate * dt))
        self.previous = gray

    def labels(self, cell, now):
        cols, rows = int(np.ceil(self.width / cell)), int(np.ceil(self.height / cell))
        yy, xx = np.mgrid[:rows + 1, :cols + 1].astype(np.float32)
        x = xx * self.width / cols
        y = yy * self.height / rows
        # Shared vertices: edges remain joined as individual triangle shapes drift.
        x += np.sin(xx * 1.7 + yy * .8 + now * .28) * cell * .18 * ((xx > 0) & (xx < cols))
        y += np.sin(yy * 1.3 - xx * .7 + now * .23) * cell * .18 * ((yy > 0) & (yy < rows))
        labels = np.zeros((self.height, self.width), np.int32)
        vertices = np.rint(np.stack([x,y],axis=-1)).astype(np.int32)
        a,b,c,d = vertices[:-1,:-1],vertices[:-1,1:],vertices[1:,:-1],vertices[1:,1:]
        triangles = np.stack([np.stack([a,b,c],axis=-2),np.stack([b,d,c],axis=-2)],axis=-3).reshape(-1,3,2)
        for index, tri in enumerate(triangles):
            cv2.fillConvexPoly(labels, tri, index)
        return labels

    @staticmethod
    def color_faces(frame, labels):
        flat = labels.ravel()
        counts = np.bincount(flat).clip(1)
        colors = np.stack([np.bincount(flat, weights=frame[:,:,channel].ravel(), minlength=len(counts)) / counts
                           for channel in range(3)], axis=1)
        return (255 - colors[labels]).astype(np.uint8)

    def render(self, frame, now, dt):
        self.update_motion(frame, dt)
        if self.maps is None or now - self.map_time >= .1:
            self.maps = (self.labels(8, now), self.labels(48, now))
            self.map_time = now
        fine = self.color_faces(frame, self.maps[0])
        coarse = self.color_faces(frame, self.maps[1])
        weight = np.clip(self.activity * 2, 0, 1)[:,:,None]
        return (fine * (1-weight) + coarse * weight).astype(np.uint8)

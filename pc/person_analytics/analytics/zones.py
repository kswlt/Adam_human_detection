from dataclasses import dataclass
@dataclass(frozen=True)
class Zone:
    zone_id: str
    name: str
    polygon: tuple[tuple[float,float], ...]
def point_zone(point,zones):
    x,y=point
    for z in zones:
        inside=False; j=len(z.polygon)-1
        for i,(xi,yi) in enumerate(z.polygon):
            xj,yj=z.polygon[j]
            if ((yi>y)!=(yj>y)) and x < (xj-xi)*(y-yi)/(yj-yi)+xi: inside=not inside
            j=i
        if inside:return z
    return None


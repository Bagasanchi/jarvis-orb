"""Procedural network sphere and animated instrument rings."""
import math

class OrbRenderer:
    def __init__(self, pygame):
        self.pg = pygame
        self.surface = pygame.Surface((760,820))
        self.glow = pygame.Surface((760,820))
        self.small = pygame.font.SysFont('Consolas', 13)
        self.medium = pygame.font.SysFont('Segoe UI', 18)
        self.large = pygame.font.SysFont('Segoe UI', 31)
        self.amber = False
        self.subtitle = None
        self.footer = "SPACE / ENTER  WAKE OR INTERRUPT     T  PALETTE     ESC  QUIT"
        self.points = []
        count = 300
        for i in range(count):
            y = 1 - 2*(i+0.5)/count
            r = math.sqrt(1-y*y)
            phi = i*math.pi*(3-math.sqrt(5))
            self.points.append((r*math.cos(phi), y, r*math.sin(phi)))
        edges = set()
        for i, p in enumerate(self.points):
            neighbors = sorted((sum((a-b)**2 for a,b in zip(p,q)),j) for j,q in enumerate(self.points) if i!=j)
            for _, j in neighbors[:4]:
                edges.add(tuple(sorted((i,j))))
        self.edges = sorted(edges)

    def text(self, text, pos, color, font=None, center=False):
        image = (font or self.small).render(text, True, color)
        if center:
            pos = (pos[0]-image.get_width()/2, pos[1])
        self.surface.blit(image,pos)

    def project(self, point, angle, radius):
        x,y,z = point
        x,z = x*math.cos(angle)+z*math.sin(angle), -x*math.sin(angle)+z*math.cos(angle)
        tilt = 0.20
        y,z = y*math.cos(tilt)-z*math.sin(tilt), y*math.sin(tilt)+z*math.cos(tilt)
        perspective = 3.8/(3.8-z)
        return (380+x*radius*perspective, 366+y*radius*perspective, z)

    @staticmethod
    def tint(color, fraction):
        return tuple(max(0,min(255,int(c*fraction))) for c in color)

    def draw(self,t,state):
        pg = self.pg
        surface = self.surface
        surface.fill((3,9,15))
        self.glow.fill((0,0,0))
        cyan = (88,205,231)
        amber = (247,177,77)
        main = amber if self.amber or state == 2 else cyan
        white = (199,231,236)
        dim = (66,101,115)
        names = ('STANDBY','LISTENING','THINKING','SPEAKING')
        subtitles = ('Awaiting your signal','Ready for your next question',
                     'Connecting ideas','Voice output active')
        self.text('J A R V I S', (42,37), white, self.large)
        self.text('PERSONAL INTELLIGENCE', (44,81), dim)
        self.text('VOICE INTERFACE / ORB', (530,52), dim)
        pg.draw.line(surface,(19,38,48),(42,113),(718,113))
        center = (380,366)
        # Quiet bloom around the projected spherical network.
        for radius,strength in ((200,.018),(192,.028),(185,.038)):
            pg.draw.circle(self.glow,self.tint(main,strength),center,radius,16)
        # Concentric instrument rings, asymmetric dashes and sweeping segments.
        for radius in (258,249,231,218):
            pg.draw.circle(surface,self.tint(main,.21 if radius in (249,218) else .13),center,radius,1)
        for i in range(144):
            a=i*math.tau/144
            major=i%12==0
            r0=238 if major else 244
            r1=250
            p0=(380+math.cos(a)*r0,366+math.sin(a)*r0)
            p1=(380+math.cos(a)*r1,366+math.sin(a)*r1)
            pg.draw.line(surface,self.tint(main,.65 if major else .25),p0,p1,2 if major else 1)
        for i in range(12):
            a=i*math.tau/12-math.pi/2
            self.text(str(i+1).zfill(2),(380+274*math.cos(a),360+274*math.sin(a)),dim,center=True)
        speed = (0.10,0.19,0.53,0.25)[state]
        rotation=t*speed
        for i,(radius,length) in enumerate(((258,.53),(230,.84),(218,.29))):
            a=rotation*(1 if i%2 else -1)+i*1.7
            rect=(380-radius,366-radius,radius*2,radius*2)
            for offset in (0,math.pi):
                pg.draw.arc(surface,main,rect,a+offset,a+offset+length,2)
                pg.draw.arc(self.glow,self.tint(main,.35),rect,a+offset,a+offset+length,4)
        pg.draw.arc(surface,amber,(160,146,440,440),.7+rotation*.25,1.75+rotation*.25,3)
        # Four cardinal targeting markers stay outside the sphere.
        for i in range(4):
            a=i*math.pi/2+math.pi/4
            px,py=380+223*math.cos(a),366+223*math.sin(a)
            pg.draw.circle(surface,white,(px,py),2)
        pulse = (1 + .022*math.sin(t*4)) if state==1 else 1
        if state==3:
            pulse = 1 + .045*(.5+.5*math.sin(t*12))*(.6+.4*math.sin(t*3))
        radius=159*pulse
        projected=[self.project(p,t*.24,radius) for p in self.points]
        # Sparse, depth-shaded triangular network; no facial features.
        for i,j in self.edges:
            a,b=projected[i],projected[j]
            depth=(a[2]+b[2])/2
            strength=.10+.34*(depth+1)/2
            pg.draw.aaline(surface,self.tint(main,strength),a[:2],b[:2])
        # Latitude and longitude wire curves add a holographic globe structure.
        for latitude in (-.65,0,.65):
            rr=math.sqrt(1-latitude*latitude)
            points=[self.project((rr*math.cos(k*math.tau/80),latitude,rr*math.sin(k*math.tau/80)),t*.24,radius)[:2] for k in range(81)]
            pg.draw.aalines(surface,self.tint(main,.24),False,points)
        for index,p in sorted(enumerate(projected),key=lambda item:item[1][2]):
            depth=(p[2]+1)/2
            strength=.24+.75*depth
            r=2 if depth>.85 else 1
            pg.draw.circle(surface,self.tint(main,strength),(p[0],p[1]),r)
            if index%19==0 and depth>.5:
                pg.draw.circle(self.glow,self.tint(main,.23),(p[0],p[1]),4)
        # A small orbital satellite and animated signal trace.
        a=t*.6
        dot=(380+math.cos(a)*230,366+math.sin(a)*230)
        pg.draw.circle(surface,white,dot,3)
        pg.draw.circle(self.glow,self.tint(main,.4),dot,7)
        glow=pg.transform.smoothscale(pg.transform.smoothscale(self.glow,(190,205)),(760,820))
        surface.blit(glow,(0,0),special_flags=pg.BLEND_RGB_ADD)
        self.text(names[state],(380,671),main,self.large,center=True)
        self.text(self.clip(self.subtitle or subtitles[state], 650), (380,718),(124,158,172),self.medium,center=True)
        for i in range(35):
            x=278+i*6
            level=2
            if state==1:
                level=3+4*abs(math.sin(t*2+i*.35))
            elif state==2:
                level=3+(5 if int(t*12)%35==i else 0)
            elif state==3:
                level=3+12*abs(math.sin(t*11+i*.51))*math.sin((i+1)*math.pi/36)
            pg.draw.line(surface,self.tint(main,.7),(x,647-level/2),(x,647+level/2),2)
        pg.draw.line(surface,(19,38,48),(42,764),(718,764))
        self.text(self.footer,(380,784),dim,center=True)

    def clip(self, text, width):
        text = ' '.join(text.split())
        if self.medium.size(text)[0] <= width:
            return text
        while text and self.medium.size(text + '...')[0] > width:
            text = text[:-1]
        return text + '...'

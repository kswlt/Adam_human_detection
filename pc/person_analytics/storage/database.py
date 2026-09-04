import sqlite3
class AnalyticsDatabase:
    def __init__(self,path='runtime/person_analytics.db'):
        self.db=sqlite3.connect(path,check_same_thread=False); self.db.execute('PRAGMA journal_mode=WAL'); self.init()
    def init(self):
        self.db.executescript('''CREATE TABLE IF NOT EXISTS persons(id TEXT PRIMARY KEY,name TEXT NOT NULL,created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS tracks(track_id INTEGER PRIMARY KEY,person_id TEXT,first_seen REAL,last_seen REAL,state TEXT);
        CREATE TABLE IF NOT EXISTS person_sessions(id INTEGER PRIMARY KEY,person_id TEXT,track_id INTEGER,start_time REAL,end_time REAL,duration REAL,max_gap REAL);
        CREATE TABLE IF NOT EXISTS trajectory_points(id INTEGER PRIMARY KEY,timestamp REAL,person_id TEXT,track_id INTEGER,x_image REAL,y_image REAL,x_world REAL,y_world REAL,zone TEXT);
        CREATE TABLE IF NOT EXISTS zone_events(id INTEGER PRIMARY KEY,timestamp REAL,person_id TEXT,track_id INTEGER,zone TEXT,event TEXT);
        CREATE TABLE IF NOT EXISTS daily_statistics(day TEXT,person_id TEXT,metric TEXT,seconds REAL,PRIMARY KEY(day,person_id,metric));
        CREATE INDEX IF NOT EXISTS idx_traj_person_time ON trajectory_points(person_id,timestamp);
        CREATE INDEX IF NOT EXISTS idx_traj_track_time ON trajectory_points(track_id,timestamp);'''); self.db.commit()
    def add_trajectory(self,point):
        self.db.execute('INSERT INTO trajectory_points(timestamp,person_id,track_id,x_image,y_image,x_world,y_world,zone) VALUES(?,?,?,?,?,?,?,?)',point)
    def upsert_person(self,person_id,name,created_at):
        self.db.execute('INSERT INTO persons(id,name,created_at) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name',(person_id,name,created_at))
    def upsert_track(self,track_id,person_id,first_seen,last_seen,state):
        self.db.execute('INSERT INTO tracks(track_id,person_id,first_seen,last_seen,state) VALUES(?,?,?,?,?) ON CONFLICT(track_id) DO UPDATE SET person_id=excluded.person_id,last_seen=excluded.last_seen,state=excluded.state',(track_id,person_id,first_seen,last_seen,state))
    def add_zone_event(self,event):
        self.db.execute('INSERT INTO zone_events(timestamp,person_id,track_id,zone,event) VALUES(?,?,?,?,?)',event)
    def add_session(self,person_id,track_id,start,end,max_gap):
        self.db.execute('INSERT INTO person_sessions(person_id,track_id,start_time,end_time,duration,max_gap) VALUES(?,?,?,?,?,?)',(person_id,track_id,start,end,end-start,max_gap))
    def add_daily_stat(self,day,person_id,metric,seconds):
        self.db.execute('INSERT INTO daily_statistics(day,person_id,metric,seconds) VALUES(?,?,?,?) ON CONFLICT(day,person_id,metric) DO UPDATE SET seconds=excluded.seconds',(day,person_id,metric,seconds))
    def commit(self):self.db.commit()
    def close(self):self.db.close()

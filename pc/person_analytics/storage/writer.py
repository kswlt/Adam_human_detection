import queue, threading
class BatchWriter:
    def __init__(self,database,batch_size=32): self.database=database; self.batch_size=batch_size; self.queue=queue.Queue(); self.stop=threading.Event(); self.thread=threading.Thread(target=self.run,daemon=True); self.errors=0
    def submit(self,row):
        try:self.queue.put_nowait(row)
        except queue.Full:self.errors+=1
    def run(self):
        while not self.stop.is_set() or not self.queue.empty():
            rows=[]
            try: rows.append(self.queue.get(timeout=.1))
            except queue.Empty: continue
            while len(rows)<self.batch_size:
                try:rows.append(self.queue.get_nowait())
                except queue.Empty:break
            try:
                for row in rows:
                    if isinstance(row,tuple) and row and row[0] == '__person__': self.database.upsert_person(*row[1:])
                    elif isinstance(row,tuple) and row and row[0] == '__track__': self.database.upsert_track(*row[1:])
                    elif isinstance(row,tuple) and row and row[0] == '__zone__': self.database.add_zone_event(row[1:])
                    else: self.database.add_trajectory(row)
                self.database.commit()
            except Exception:self.errors+=1
            finally:
                for _ in rows:self.queue.task_done()
    def flush(self): self.queue.join()

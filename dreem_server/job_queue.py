import sqlite3
import json
import os
from collections import namedtuple
from time import gmtime, strftime


class Job (object):
    def __init__(self, id, status, type, args, email, time, num, name):
        self.id = id
        self.status = status
        self.type = type
        self.args = json.loads(args)
        self.email = email
        self.time = time
        self.num = num
        self.name = name


    def status_str(self):
        str_status = "QUEUED"
        if self.status == JobStatus.FINISHED:
            str_status = "FINISHED"
        if self.status == JobStatus.ERROR:
            str_status = "ERROR"
        return str_status

    def type_str(self):
        str_type = "ONED_ANALYSIS"
        if self.type == JobType.ONED_ANALYSIS:
            str_type = "ONED_ANALYSIS"
        return str_type

    def __str__(self):
        str_status = self.status_str()
        str_type = self.type_str()

        s = "Job(id:%s, status:%s, type:%s, submitted:%s, args:%s)" %\
            (self.id, str_status, str_type, self.time, json.dumps(self.args))

        return s

class JobStatus:
    QUEUED = 0
    FINISHED = 1
    ERROR = 2


class JobType:
    ONED_ANALYSIS=0


class JobQueue(object):
    def __init__(self, db_name='jobs.db'):
        self._setup_sqlite_connection(db_name)
        self.current_pos = self.get_last_num() + 1

    def _setup_sqlite_connection(self, db_name):
        self.connection = sqlite3.connect(db_name, check_same_thread=False)

        try:
            self.connection.execute('CREATE TABLE jobs( id TEXT, status INT, \
                                     type INT, args TEXT, email TEXT, time TEXT, \
                                     num INT, name TEXT, PRIMARY KEY(id));')
        except:
            pass



    def add_job(self, job_id, job_type, args, email='', name=''):
        num = self.get_last_num() + 1

        time_str = strftime("%Y-%m-%d %H:%M:%S", gmtime())
        job = [job_id, int(JobStatus.QUEUED), int(job_type), args, email, time_str, num, name]
        self.connection.execute('INSERT INTO jobs (id,status,type,args,email,time,num,name) \
                                 VALUES(?,?,?,?,?,?,?,?)', job)
        self.connection.commit()
        self.current_pos += 1

    # only use for testing!!!
    def delete_job(self, nid):
        try:
            self.connection.execute("DELETE FROM jobs WHERE id=?", (nid,))
            self.connection.commit()
        except:
            return None

    def get_job(self, nid):
        try:
            r = self.connection.execute("SELECT * FROM jobs WHERE id=:Id", {"Id":nid}).fetchone()
        except:
            return None

        if r is None:
            return None

        r_obj = Job(*r)
        return r_obj

    def get_last_num(self):
        index = self.connection.execute('SELECT MAX(num) FROM jobs').fetchone()
        if index[0] is None:
            return 0
        else:
            return int(index[0])

    def get_next_queued_job(self):
        index = self.connection.execute('SELECT MIN(num) FROM jobs WHERE status=0').fetchone()
        if index[0] is None:
            return None
        else:
            r = self.connection.execute('SELECT * FROM jobs WHERE num = '+str(index[0])).fetchone()
            return Job(*r)

    def get_queue_position(self, id):
        return self.connection.execute('SELECT COUNT(*) FROM jobs WHERE status=0 AND num < (SELECT num FROM jobs WHERE id=?)', (id,)).fetchone()[0]

    def has_queued_jobs(self):
        c = len(self.connection.execute("SELECT * FROM jobs WHERE status=0").fetchall())
        if c > 0:
            return True
        else:
            return False

    def update_job_status(self, id, status):
        self.connection.execute('''UPDATE jobs SET status = ? WHERE id = ?''', (int(status), id))
        self.connection.commit()


    def get_queued(self):
        jobs = self.connection.execute('SELECT * FROM jobs WHERE status=0').fetchall()
        j_obs = []
        for j in jobs:
            j_obs.append(Job(*j))
        return j_obs

    def get_all(self):
        jobs = self.connection.execute('SELECT * FROM jobs').fetchall()
        j_obs = []
        for j in jobs:
            j_obs.append(Job(*j))
        return j_obs



if __name__ == '__main__':
    queue = JobQueue()
    #queue.add_job("c32af6417fb183e71c662232091ce548", JobType.SCAFFOLD, json.dumps(args))
    #print queue.get_queue_position("c32af6417fb183e71c662232091ce548")
    #print queue.get_last_run_job_num()
    #print queue.has_queued_jobs()
    #print queue.get_next_queued_job()
    #queue.update_job_status("c32af6417fb183e71c662232091ce548", JobStatus.FINISHED)
    #print queue.has_queued_jobs()
    #print queue.get_next_queued_job()


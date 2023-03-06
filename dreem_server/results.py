import sqlite3
import json
import pandas as pd
import glob
import os
from collections import namedtuple
from pathlib import Path
from time import gmtime, strftime


class Result(object):
    class __SummaryRow(object):
        def __init__(self, name, reads, aligned, sn):
            self.name = name
            self.reads = reads
            self.aligned = aligned
            self.sn = sn

    def __init__(self, id, type, data, time, num):
        self.id = id
        self.type = type
        self.data = json.loads(data)
        self.rows = []
        self.time = time
        self.num = num
        self.plotly_strs = []
        print(self.data)
        if id == '6bbf2ee23cd15f4be689907c611c5e8f':
           self.data['error'] = 'please contact me at jyesselm@unl.edu, there are a couple things wrong that I can help you with'
        if self.data.get("summary") is None:
            return
        path = Path(self.data["summary"]).parent
        df = pd.read_csv(self.data["summary"])
        df['score'] = df['reads']*df['aligned']
        df = df.sort_values("score", ascending=False)
        if len(df) > 50:
            df = df[:50]
        seen = []
        for i, row in df.iterrows():
            seen.append(row["name"])
            self.rows.append(
                self.__SummaryRow(row["name"], row["reads"], row["aligned"], row["sn"])
            )
        html_files = glob.glob(str(path) + "/*.html")
        for hf in html_files:
            name = "_".join(Path(hf).stem.split("_")[0:-4])
            if name not in seen:
                continue
            f = open(hf)
            lines = f.readlines()
            f.close()
            s = "".join(lines)
            spl = s.split("</script>")
            keep_str = spl[2] + "</script>"
            self.plotly_strs.append(keep_str)

    def type_str(self):
        str_type = "ONED_ANALYSIS"
        if self.type == ResultType.ONED_ANALYSIS:
            str_type = "ONED_ANALYSIS"
        return str_type

    def __str__(self):
        str_type = self.type_str()

        s = "Result(id:%s, type:%s, submitted:%s, data:%s)" % (
            self.id,
            str_type,
            self.time,
            json.dumps(self.data),
        )

        return s


class ResultType:
    ONED_ANALYSIS = 0


class ResultsDB(object):
    def __init__(self, db_name="results.db"):
        self._setup_sqlite_connection(db_name)
        self.current_pos = self.get_last_num() + 1

    def _setup_sqlite_connection(self, db_name):
        self.connection = sqlite3.connect(db_name, check_same_thread=False)

        try:
            self.connection.execute(
                "CREATE TABLE results( id TEXT, type INT, \
                                     data TEXT, time TEXT, num INT, PRIMARY KEY(id));"
            )
        except:
            pass

    def add_result(self, job_id, job_type, data):
        num = self.get_last_num() + 1

        time_str = strftime("%Y-%m-%d %H:%M:%S", gmtime())
        job = [job_id, int(job_type), data, time_str, num]
        self.connection.execute(
            "INSERT INTO results (id,type,data,time,num) \
                                 VALUES(?,?,?,?,?)",
            job,
        )
        self.connection.commit()
        self.current_pos += 1

    # only use for testing!!!
    def delete_result(self, nid):
        try:
            self.connection.execute("DELETE FROM results WHERE id=?", (nid,))
            self.connection.commit()
        except:
            return None

    def get_result(self, nid):
        try:
            r = self.connection.execute(
                "SELECT * FROM results WHERE id=:Id", {"Id": nid}
            ).fetchone()
        except:
            return None

        if r is None:
            return None

        r_obj = Result(*r)
        return r_obj

    def get_last_num(self):
        index = self.connection.execute("SELECT MAX(num) FROM results").fetchone()
        if index[0] is None:
            return 0
        else:
            return int(index[0])

    def get_all(self):
        jobs = self.connection.execute("SELECT * FROM results").fetchall()
        j_obs = []
        for j in jobs:
            j_obs.append(Result(*j))
        return j_obs


if __name__ == "__main__":
    pass
    # queue.add_job("c32af6417fb183e71c662232091ce548", JobType.SCAFFOLD, json.dumps(args))
    # print queue.get_queue_position("c32af6417fb183e71c662232091ce548")
    # print queue.get_last_run_job_num()
    # print queue.has_queued_jobs()
    # print queue.get_next_queued_job()
    # queue.update_job_status("c32af6417fb183e71c662232091ce548", JobStatus.FINISHED)
    # print queue.has_queued_jobs()
    # print queue.get_next_queued_job()

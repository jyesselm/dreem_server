import os
import argparse
import threading
import cherrypy
import cherrypy.lib.static
import json
import time
import csv
import io
import shutil
from pathlib import Path
from subprocess import CalledProcessError

import dreem.run
from jinja2 import Environment, FileSystemLoader, select_autoescape

import mimetypes

mimetypes.types_map['.svg'] = 'image/svg+xml'

from dreem_server import job_queue, results, email_client


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-mode', help='what mode is the server being run in', required=True,
                        choices=['devel', 'release'], type=str)
    parser.add_argument('-no_job_creation', required=False, action="store_true")

    args = parser.parse_args()

    return args


FILE_DIR = os.path.abspath(os.path.dirname(__file__))
MEDIA_DIR = os.path.join(FILE_DIR, 'media')

os.makedirs(os.path.join(MEDIA_DIR, 'static', 'job-data'), exist_ok=True)

jenv = Environment(
        loader=FileSystemLoader(os.path.join(MEDIA_DIR, 'templates')),
        autoescape=select_autoescape(['html', 'xml'])
)

templates = {
    'index'      : lambda: jenv.get_template('index.html'),
    'about'      : lambda: jenv.get_template('about.html'),
    'result'     : lambda: jenv.get_template('result.html'),
    'result_rows': lambda: jenv.get_template('result_rows.html')
}


def get_default_dreem_args():
    args = {
        'fasta'                : '',
        'fastq1'               : '',
        'fastq2'               : '',
        'dot_bracket'          : None,
        'param_file'           : None,
        'overwrite'            : False,
        'log_level'            : 'INFO',
        'restore_org_behavior' : False,
        'map_overwrite'        : False,
        'skip'                 : False,
        'skip_fastqc'          : False,
        'skip_trim_galore'     : False,
        'bt2_alignment_args'   : None,
        'bv_overwrite'         : False,
        'qscore_cutoff'        : None,
        'num_of_surbases'      : None,
        'map_score_cutoff'     : None,
        'mutation_count_cutoff': None,
        'percent_length_cutoff': None
    }
    return args


class JobRunner(cherrypy.process.plugins.SimplePlugin):
    def plog(self, message):
        self.bus.log('[JobRunner PLUGIN]: {}'.format(message))

    def start(self):
        self.plog('Starting JobRunner plugin')
        cherrypy.engine.subscribe('queue_job', self.queue_job)
        self.job_queue = job_queue.JobQueue()
        self.result_db = results.ResultsDB()

        self.plog('Starting job processor thread')
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.job_running_daemon)
        self.thread.start()

    start.priority = 150

    def stop(self):
        self.plog('Stopping JobRunner plugin')
        self.stopping.set()

    def queue_job(self, job_id, job_type, args, email, name):
        self.job_queue.add_job(job_id, job_type, args, email, name)

    def job_running_daemon(self):
        while True:
            if self.stopping.is_set():
                return
            if not self.job_queue.has_queued_jobs():
                time.sleep(5)
                continue

            j = self.job_queue.get_next_queued_job()
            args = get_default_dreem_args()
            args['fasta'] = j.args['fasta']
            args['fastq1'] = j.args['fastq1']
            args['fastq2'] = j.args['fastq2']
            new_path = Path(j.args['fasta']).parent
            dreem.run.run(args)
            path = FILE_DIR + "/output/BitVector_Files/"
            if not os.path.isfile(path + "summary.csv"):
                raise ValueError("DREEM did not run properly")
            shutil.move(path, new_path)
            # clean up other stuff not Used
            try:
                shutil.rmtree('input')
                shutil.rmtree('output')
                shutil.rmtree('log')
            except:
                pass
            data = {
                'summary' : str(new_path) + "/BitVector_Files/summary.csv"
            }
            data.update(args)
            self.result_db.add_result(j.id, j.type, json.dumps(data))
            self.job_queue.update_job_status(j.id, job_queue.JobStatus.FINISHED)

            """errstring = f'{e}'
            if getattr(e, 'stderr', None) is not None:
                errstring += f'\n------------\nSTDOUT:\n{e.stderr}'
            self.result_db.add_result(j.id, j.type, json.dumps(errstring))
            self.job_queue.update_job_status(j.id, job_queue.JobStatus.ERROR)"""

            if j.email:
                email_client.send_email(j.email, j.id, j.name)


class App:
    def __init__(self):
        # We need to do this AFTER we drop privilages. Otherwise, we'll still be root
        # when connecting to the results DB, meaning if it doesn't exist yet,
        # the permissions will be set as owned by root, and we can't open it afterwords
        cherrypy.engine.subscribe('main', self.init_resdb)

    def init_resdb(self):
        self.resdb = results.ResultsDB()
        self.jobdb = job_queue.JobQueue()

    @cherrypy.expose
    def index(self):
        return templates['index']().render(page='home')

    @cherrypy.expose
    def request(self, fasta_file, fastq1_file, fastq2_file, email=None, name=None):

        job_id = os.urandom(16).hex()
        path = os.path.join(MEDIA_DIR, 'static', 'job-data', job_id)
        os.mkdir(path)
        self.__write_file_to_static(path, fasta_file)
        self.__write_file_to_static(path, fastq1_file)
        self.__write_file_to_static(path, fastq2_file)

        args = {
            "fasta" : path + "/" + fasta_file.filename,
            "fastq1": path + "/" + fastq1_file.filename,
            "fastq2": path + "/" + fastq2_file.filename,
            "fasta_name" : fasta_file.filename,
            "fastq1_name" : fastq1_file.filename,
            "fastq2_name" : fastq2_file.filename
        }

        cherrypy.engine.publish('queue_job', job_id,
                                job_queue.JobType.ONED_ANALYSIS, json.dumps(args), email, name)

        raise cherrypy.HTTPRedirect('/result/' + job_id)

    @cherrypy.expose
    def result(self, job_id):
        job = self.jobdb.get_job(job_id)
        res = self.resdb.get_result(job_id)
        error = job.status == job_queue.JobStatus.ERROR
        return templates['result']().render(results=res, job=job, error=error,
                                            queue_position=self.jobdb.get_queue_position(job_id))

    @cherrypy.expose
    def resultembedded(self, job_id):
        job = self.jobdb.get_job(job_id)
        res = self.resdb.get_result(job_id)

        if job.status == job_queue.JobStatus.QUEUED:
            return 'WAITING ' + str(self.jobdb.get_queue_position(job_id))
        elif job.status == job_queue.JobStatus.ERROR:
            return 'ERROR'
        elif job.status == job_queue.JobStatus.FINISHED:
            return templates['result_rows']().render(results=res, job=job)

    @cherrypy.expose
    def resultdownload(self, job_id, file_type):
        job = self.jobdb.get_job(job_id)

        if file_type == "fasta":
            return cherrypy.lib.static.serve_file(
                    job.args['fasta'], "application/x-download",
                    "attachment", os.path.basename(job.args['fasta']))

        if job.status != job_queue.JobStatus.ERROR:
            res = self.resdb.get_result(job_id)

            cherrypy.response.headers['Content-Disposition'] = f'attachment; filename="eternabot-{res.id}.csv"'
            return cherrypy.lib.file_generator(csvfile)

    @cherrypy.expose
    def about(self):
        return templates['about']().render(page='about')

    def __write_file_to_static(self, path, file_obj):
        f_path = path + "/" + file_obj.filename
        with open(f_path, 'wb') as out:
            while True:
                data = file_obj.file.read(8192)
                if not data:
                    break
                out.write(data)


def start_server():
    args = parse_args()

    server_state = args.mode
    if server_state == "devel":
        socket_host = "127.0.0.1"
        socket_port = 8080
    else:
        socket_host = "0.0.0.0"
        socket_port = 80

    JobRunner(cherrypy.engine).subscribe()

    cherrypy.config.update({
        "server.socket_host": socket_host,
        "server.socket_port": socket_port,
        "server.thread_pool": 100,
        "server.max_request_body_size": 0,
        'server.socket_timeout': 60
    })

    cherrypy.quickstart(App(), '', config={
        '/static': {
            'tools.staticdir.on' : True,
            'tools.staticdir.dir': os.path.join(MEDIA_DIR, 'static'),
        },
    })


if __name__ == "__main__":
    start_server()

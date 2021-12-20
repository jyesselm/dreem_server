import os
import argparse
import threading
import cherrypy
import cherrypy.lib.static
import json
import time
import shutil
import re
from pathlib import Path
from subprocess import CalledProcessError
from zipfile import ZipFile

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
    'index'   : lambda: jenv.get_template('index.html'),
    'about'   : lambda: jenv.get_template('about.html'),
    'result'  : lambda: jenv.get_template('result.html'),
    'tutorial': lambda: jenv.get_template('tutorial.html')
}


def get_default_dreem_args():
    args = {
        'fasta'                : '',
        'fastq1'               : '',
        'fastq2'               : None,
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

    def zip_results(self):
        with ZipFile('results.zip', 'w') as zip_obj:
            for folderName, subfolders, filenames in os.walk('output/BitVector_Files'):
                for filename in filenames:
                    filePath = os.path.join(folderName, filename)
                    zip_obj.write(filePath, os.path.basename(filePath))

    def get_bowtie_results(self, bowtie_log_path):
        f = open(bowtie_log_path)
        lines = f.readlines()[6:]
        f.close()
        nums = []
        for l in lines:
            spl = l.rstrip().lstrip().split()
            try:
                nums.append(spl[0])
            except:
                pass
        bowtie_results = {
            'total_reads' : nums[0],
            'paired_type_reads' : nums[1],
            'not_aligned' : nums[2],
            'aligned' : nums[3],
            'mult_aligned' : nums[4],
            'not_aligned_per' : round(float(nums[2]) / float(nums[0]) * 100, 2),
            'aligned_per' : round(float(nums[3]) / float(nums[0]) * 100, 2),
            'mult_aligned_per': round(float(nums[4]) / float(nums[0]) * 100, 2),
        }
        return bowtie_results

    def check_fasta_format(self, fasta_path):
        f = open(fasta_path)
        lines = f.readlines()
        f.close()
        msg = None
        for i, l in enumerate(lines):
            l = l.rstrip().lstrip()
            if i % 2 == 0:
                if l[0] != '>':
                    msg = "every other fasta line must start with '>' no space than reference name"
                if l[1] == ' ':
                    msg = "every other fasta line must start with '>' no space than reference name"
            else:
                if l.find("U") != -1:
                    msg = "reference sequences must be DNA not RNA"
                if re.search(r"[^AGCT]", l):
                    msg = "reference sequences must contain AGCT or characters"
        return msg

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
            if j.args['run_type'] == 'PAIRED':
                args['fastq2'] = j.args['fastq2']
            new_path = Path(j.args['fasta']).parent
            try:
                error_msg = self.check_fasta_format(args['fasta'])
                self.plog(error_msg)
                if error_msg is not None:
                    raise ValueError(error_msg)
                dreem.run.run(args)
                path = FILE_DIR + "/output/BitVector_Files/"
                if not os.path.isfile(path + "summary.csv"):
                    raise ValueError("DREEM did not run properly")
                self.zip_results()
                shutil.move(path, new_path)
                shutil.move(FILE_DIR + "/results.zip", new_path)
                data = {
                    'summary': str(new_path) + "/BitVector_Files/summary.csv",
                    'bowtie' : self.get_bowtie_results(FILE_DIR + "/log/bowtie2 alignment.log")
                }
                data.update(args)
                self.result_db.add_result(j.id, j.type, json.dumps(data))
                self.job_queue.update_job_status(j.id, job_queue.JobStatus.FINISHED)
                self.plog('finished job succesfully!')
            except Exception as e:
                errstring = ''
                for l in str(e).split('\n'):
                    errstring += l.replace(MEDIA_DIR, '/datadir') + "<br>"
                #if getattr(e, 'stderr', None) is not None:
                #    errstring += f'\n------------\nSTDOUT:\n'

                self.result_db.add_result(j.id, j.type, json.dumps(errstring))
                self.job_queue.update_job_status(j.id, job_queue.JobStatus.ERROR)

            try:
                shutil.rmtree('input')
                shutil.rmtree('output')
                shutil.rmtree('log')
            except:
                pass

            if j.email:
                email_client.send_email(j.email, j.id, j.name)


class App:
    def __init__(self, host_name):
        # We need to do this AFTER we drop privilages. Otherwise, we'll still be root
        # when connecting to the results DB, meaning if it doesn't exist yet,
        # the permissions will be set as owned by root, and we can't open it afterwords
        cherrypy.engine.subscribe('main', self.init_resdb)
        self.host_name = host_name
        # check to make sure there is a demo job!

    def init_resdb(self):
        self.resdb = results.ResultsDB()
        self.jobdb = job_queue.JobQueue()
        new_dir = MEDIA_DIR + "/static/job-data/demo"
        if not os.path.isdir(new_dir):
            start_dir = MEDIA_DIR + "/static/examples/example-input"
            shutil.copytree(start_dir, new_dir)
            args = {
                "run_type"   : "PAIRED",
                "fasta"      : new_dir + "/test.fasta",
                "fastq1"     : new_dir + "/test_mate1.fastq",
                "fastq2"     : new_dir + "/test_mate2.fastq",
                "fasta_name" : "test.fasta",
                "fastq1_name": "test_mate1.fastq",
                "fastq2_name": "test_mate2.fastq"
            }
            cherrypy.engine.publish('queue_job', 'demo',
                                    job_queue.JobType.ONED_ANALYSIS, json.dumps(args),
                                    None, None)

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
        args = {
            "fasta"      : path + "/" + fasta_file.filename,
            "fastq1"     : path + "/" + fastq1_file.filename,
            "fasta_name" : fasta_file.filename,
            "fastq1_name": fastq1_file.filename,
        }
        # did we get one or two fastq files
        run_type = 'PAIRED'
        if len(fastq2_file.filename) > 5:
            self.__write_file_to_static(path, fastq2_file)
            args['fastq2'] = path + "/" + fastq2_file.filename
            args['fastq2_name'] = fastq2_file.filename
        else:
            run_type = 'SINGLE'
            args['fastq2'] = ''
            args['fastq2_name'] = ''
        args['run_type'] = run_type
        cherrypy.engine.publish('queue_job', job_id,
                                job_queue.JobType.ONED_ANALYSIS, json.dumps(args), email, name)
        raise cherrypy.HTTPRedirect('/result/' + job_id)

    @cherrypy.expose
    def result(self, job_id):
        job = self.jobdb.get_job(job_id)
        res = self.resdb.get_result(job_id)
        error = job.status == job_queue.JobStatus.ERROR
        return templates['result']().render(results=res, job=job, error=error, host_name=self.host_name,
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
    def download(self, type):
        path = MEDIA_DIR + "/static/examples"
        if type == 'example-input':
            return cherrypy.lib.static.serve_file(
                    f"{path}/example-input.zip", "application/x-download", "attachment")

        if type == 'example-fasta-file':
            return cherrypy.lib.static.serve_file(
                    f"{path}/example-input/test.fasta", "application/x-download", "attachment")

        if type == 'example-fastq-file':
            return cherrypy.lib.static.serve_file(
                    f"{path}/example-input/test_mate1.fastq", "application/x-download", "attachment")

    @cherrypy.expose
    def resultdownload(self, job_id, file_type):
        job = self.jobdb.get_job(job_id)

        if file_type == "fasta":
            return cherrypy.lib.static.serve_file(
                    job.args['fasta'], "application/x-download",
                    "attachment", os.path.basename(job.args['fasta']))

        elif file_type == 'fastq1':
            return cherrypy.lib.static.serve_file(
                    job.args['fastq1'], "application/x-download", "attachment")

        elif file_type == 'fastq2':
            return cherrypy.lib.static.serve_file(
                    job.args['fastq2'], "application/x-download", "attachment")

        elif file_type == 'zip':
            return cherrypy.lib.static.serve_file(
                    f"{MEDIA_DIR}/static/job-data/{job.id}/results.zip", "application/x-download",
                    "attachment")

    @cherrypy.expose
    def about(self):
        return templates['about']().render(page='about')

    @cherrypy.expose
    def tutorial(self):
        return templates['tutorial']().render(page='tutorial')

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
        host_name = 'http://localhost:8080'

    else:
        socket_host = "0.0.0.0"
        socket_port = 80
        host_name = 'http://dreemrna.org'

    JobRunner(cherrypy.engine).subscribe()

    cherrypy.config.update({
        "server.socket_host"   : socket_host,
        "server.socket_port"   : socket_port,
        "server.thread_pool"   : 100,
        'server.socket_timeout': 60
    })

    cherrypy.quickstart(App(host_name), '', config={
        '/static': {
            'tools.staticdir.on' : True,
            'tools.staticdir.dir': os.path.join(MEDIA_DIR, 'static'),
        }
    })


if __name__ == "__main__":
    start_server()

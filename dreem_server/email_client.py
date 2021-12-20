# Via https://github.com/jyesselm/RNA_Redesign_Server/blob/174ad72c3c109ab5b87fa07caba4c386b573eebf/rna_design/email_client.py
from email.mime.text import MIMEText
from datetime import date
import smtplib
from textwrap import dedent

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = "rnadreem.results@gmail.com"
SMTP_PASSWORD = "Ppq7Jf6M$&YN"

EMAIL_FROM = "rnadreem.results@gmail.com"
EMAIL_SUBJECT = "DREEM Job Finished : "

DATE_FORMAT = "%d/%m/%Y"
EMAIL_SPACE = ", "

DATA='This is the content of the email.'


def send_email(user_email, job_id, job_name):
    DATA = dedent("""
    Dear %s,

    Your DREEM job %sis finished. You can the results at http://rnadreem.org/result/%s
    """ % (user_email, ('"%s" ' % job_name) if job_name else '', job_id)).strip()

    EMAIL_TO = [user_email]

    msg = MIMEText(DATA)
    msg['Subject'] = (EMAIL_SUBJECT + " %s %s" % (date.today().strftime(DATE_FORMAT), job_name)).strip()
    msg['To'] = EMAIL_SPACE.join(EMAIL_TO)
    msg['From'] = EMAIL_FROM
    mail = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    mail.starttls()
    mail.login(SMTP_USERNAME, SMTP_PASSWORD)
    mail.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
    mail.quit()

def main():
    #send_email('jyesselm@unl.edu', 'demo', 'demo')
    pass

if __name__ == "__main__":
    main()
